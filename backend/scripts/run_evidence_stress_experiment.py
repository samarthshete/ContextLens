#!/usr/bin/env python3
"""Run batch heuristic (+ optional one LLM) stress experiment and print evidence summary.

Uses ``evidence_stress_retrieval_v1`` (see ``benchmark-datasets/evidence-stress-v1/``).

Heuristic grid: all queries × both stress configs × ``--reps`` with ``--realism`` by default.

Optional ``--llm-one`` runs **one** full RAG cell (first query × first config) when the active
provider API key is configured; otherwise prints a skip line (**no fake LLM**).

Writes ``_local/docs/evidence-stress-experiment-last-run.md`` unless ``--no-write-doc``.

Usage (from ``backend/``)::

    alembic upgrade head
    python scripts/seed_evidence_stress_benchmark.py
    python scripts/run_evidence_stress_experiment.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models import EvaluationResult, Run  # noqa: E402
from app.services.batch_runner import run_batch_benchmark  # noqa: E402
from app.services.benchmark_realism import BenchmarkRealismProfile  # noqa: E402
from app.services.benchmark_stress_seed import (  # noqa: E402
    ensure_stress_benchmark_seed,
    ensure_stress_corpus_document,
    get_stress_benchmark_ready,
)
from app.services.config_comparison import compare_pipeline_configs  # noqa: E402
from app.services.run_create import (  # noqa: E402
    FullModeNotConfiguredError,
    run_full_benchmark_pipeline,
    validate_run_create_prerequisites,
)
from app.services import trace_persistence as tp  # noqa: E402
from app.services.run_lifecycle import STATUS_RUNNING  # noqa: E402


def _batch_filter(batch_id: str):
    return Run.metadata_json.contains({"batch_id": batch_id})


async def _pick_extreme_runs(
    session: AsyncSession,
    *,
    batch_id: str,
    want_lowest_relevance: bool,
) -> int | None:
    stmt = (
        select(Run.id, EvaluationResult.retrieval_relevance)
        .join(EvaluationResult, EvaluationResult.run_id == Run.id)
        .where(_batch_filter(batch_id))
        .where(EvaluationResult.used_llm_judge.is_(False))
        .where(EvaluationResult.retrieval_relevance.isnot(None))
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return None

    def key(t: tuple) -> float:
        return float(t[1] or 0.0)

    rid, _ = min(rows, key=key) if want_lowest_relevance else max(rows, key=key)
    return int(rid)


async def _failure_histogram(session: AsyncSession, *, batch_id: str) -> Counter[str]:
    stmt = (
        select(EvaluationResult.failure_type)
        .join(Run, Run.id == EvaluationResult.run_id)
        .where(_batch_filter(batch_id))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return Counter(str(ft) for ft in rows)


async def _run_llm_one_shot(
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None,
    batch_id_base: str,
) -> tuple[int | None, str]:
    meta = {
        "batch_id": f"{batch_id_base}_llm_subset",
        "experiment_name": "evidence_stress_llm_one_shot",
        "batch_evaluator_type": "llm",
        "batch_repetition": 0,
    }
    try:
        async with async_session_maker() as session:
            await validate_run_create_prerequisites(
                session,
                query_case_id=query_case_id,
                pipeline_config_id=pipeline_config_id,
                document_id=document_id,
                eval_mode="full",
            )
            run = await tp.create_run(
                session,
                query_case_id=query_case_id,
                pipeline_config_id=pipeline_config_id,
                status=STATUS_RUNNING,
                metadata_json=meta,
            )
            await session.commit()
            rid = run.id
        await run_full_benchmark_pipeline(rid, document_id)
        async with async_session_maker() as session:
            r = await session.get(Run, rid)
            st = r.status if r else "missing"
        return rid, str(st)
    except FullModeNotConfiguredError as e:
        return None, f"skipped_no_llm_key: {e}"
    except Exception as e:
        return None, f"failed: {e}"


def _fmt_comparison(comp) -> str:
    return json.dumps(comp.model_dump(mode="json"), indent=2)


async def _async_main(ns: argparse.Namespace) -> int:
    stress_dir = ns.stress_dir.resolve() if ns.stress_dir else None

    async with async_session_maker() as session:
        await ensure_stress_benchmark_seed(session, stress_dir, commit=True)
        await ensure_stress_corpus_document(session, stress_dir, commit=True)

    async with async_session_maker() as session:
        ready = await get_stress_benchmark_ready(session, stress_dir)

    document_id: int | None = None if ns.all_chunks else ready.document_id
    realism = BenchmarkRealismProfile() if ns.realism else None

    async with async_session_maker() as session:
        batch = await run_batch_benchmark(
            session,
            [ready.dataset_id],
            list(ready.pipeline_config_ids),
            queries_per_dataset=len(ready.query_case_ids),
            runs_per_query=ns.reps,
            evaluator_type="heuristic",
            random_seed=ns.seed,
            document_id=document_id,
            experiment_name=ns.experiment_name,
            config_group_tag=ns.config_group_tag,
            realism_profile=realism,
            commit=True,
        )

    llm_run_id: int | None = None
    llm_note = "not_requested"
    if ns.llm_one:
        llm_run_id, llm_note = await _run_llm_one_shot(
            query_case_id=ready.query_case_ids[0],
            pipeline_config_id=ready.pipeline_config_ids[0],
            document_id=document_id,
            batch_id_base=batch.batch_id,
        )

    async with async_session_maker() as session:
        fails = await _failure_histogram(session, batch_id=batch.batch_id)
        bad_rid = await _pick_extreme_runs(session, batch_id=batch.batch_id, want_lowest_relevance=True)
        good_rid = await _pick_extreme_runs(session, batch_id=batch.batch_id, want_lowest_relevance=False)
        comp = await compare_pipeline_configs(
            session,
            list(ready.pipeline_config_ids),
            evaluator_type="heuristic",
            dataset_id=ready.dataset_id,
            include_benchmark_realism=ns.realism,
        )

    lines: list[str] = []
    lines.append("## Evidence stress experiment (automated capture)")
    lines.append("")
    lines.append(f"- **UTC time:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- **Host:** `{os.uname().nodename if hasattr(os, 'uname') else 'unknown'}`")
    lines.append(f"- **Dataset:** `evidence_stress_retrieval_v1` (id={ready.dataset_id})")
    lines.append(f"- **Configs:** stress_topk3 / stress_topk8 (ids={list(ready.pipeline_config_ids)})")
    lines.append(f"- **Queries:** {len(ready.query_case_ids)} (same set across configs via batch_runner)")
    lines.append(f"- **Heuristic batch_id:** `{batch.batch_id}`")
    lines.append(
        f"- **Heuristic grid:** total_runs={batch.total_runs}, successes={batch.successes}, "
        f"failures={batch.failures}, success_rate={batch.success_rate:.4f}"
    )
    lines.append(f"- **Failure types (heuristic batch):** `{dict(fails)}`")
    lines.append(f"- **Example weak run (lowest retrieval_relevance):** run_id={bad_rid}")
    lines.append(f"- **Example strong run (highest retrieval_relevance):** run_id={good_rid}")
    lines.append(f"- **LLM one-shot:** run_id={llm_run_id}, note={llm_note}")
    lines.append("")
    lines.append("### Config comparison (heuristic, dataset-scoped)")
    lines.append("")
    lines.append("```json")
    lines.append(_fmt_comparison(comp))
    lines.append("```")
    lines.append("")
    lines.append("### Statistical reliability")
    lines.append("")
    lines.append(
        f"- **comparison_statistically_reliable:** {comp.comparison_statistically_reliable} "
        f"(min_traced_runs_across_configs={comp.min_traced_runs_across_configs}; "
        f"recommended≥{comp.recommended_min_traced_runs_for_valid_comparison})"
    )
    lines.append(f"- **comparison_confidence:** {comp.comparison_confidence}")
    lines.append("")
    lines.append("### Dashboard / UI")
    lines.append("")
    lines.append("- Open **`/dashboard`** after this run for time series + failure bars + config insights.")
    lines.append(f"- Filter **`/runs`** by `dataset_id={ready.dataset_id}` for volume scoped to this dataset.")
    lines.append("")
    text = "\n".join(lines)

    print(text)

    if ns.write_doc:
        out = _REPO_ROOT / "_local" / "docs" / "evidence-stress-experiment-last-run.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"\nWrote {out}", file=sys.stderr)

    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Run evidence-stress-v1 batch + capture summary.")
    p.add_argument("--stress-dir", type=Path, default=None)
    p.add_argument("--reps", type=int, default=2, help="runs_per_query per (query×config)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--experiment-name", default="evidence_stress_batch")
    p.add_argument("--config-group-tag", default="stress_topk_ab")
    p.add_argument(
        "--all-chunks",
        action="store_true",
        help="Do not scope retrieval to stress document (default: scope to stress corpus doc)",
    )
    p.add_argument("--no-realism", action="store_true", help="Disable heuristic perturbations")
    p.add_argument("--llm-one", action="store_true", help="Attempt one full RAG run if API key present")
    p.add_argument("--no-write-doc", action="store_true", help="Skip writing _local/docs fragment")
    ns = p.parse_args()

    asyncio.run(
        _async_main(
            argparse.Namespace(
                stress_dir=ns.stress_dir,
                reps=ns.reps,
                seed=ns.seed,
                experiment_name=ns.experiment_name,
                config_group_tag=ns.config_group_tag,
                all_chunks=ns.all_chunks,
                realism=not ns.no_realism,
                llm_one=ns.llm_one,
                write_doc=not ns.no_write_doc,
            )
        )
    )


if __name__ == "__main__":
    main()
