#!/usr/bin/env python3
"""Execute quickstart benchmark runs and evaluation for metrics.

Modes:

- **heuristic** (default): retrieval + ``minimal_retrieval_heuristic_v1`` (no LLM).
- **full**: retrieval → Claude generation → Claude LLM judge + ``cost_usd`` (gen+judge estimate; **NULL** when both Anthropic per-M rates ≤ 0 or usage unknown).

Usage (from ``backend/``)::

    python scripts/run_benchmark.py
    python scripts/run_benchmark.py --eval-mode full
    python scripts/run_benchmark.py --skip-seed --document-id 42
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.models import Run  # noqa: E402
from app.services.benchmark_run import execute_retrieval_benchmark_run  # noqa: E402
from app.services.benchmark_seed import (  # noqa: E402
    ensure_benchmark_seed,
    ensure_quickstart_corpus_document,
    get_benchmark_seed_result,
)
from app.services.evaluation_persistence import persist_evaluation_and_complete_run  # noqa: E402
from app.services.full_rag_evaluation import execute_llm_judge_and_complete_run  # noqa: E402
from app.services.generation_phase import execute_generation_for_run  # noqa: E402
from app.services.minimal_retrieval_evaluation import compute_minimal_retrieval_evaluation  # noqa: E402


async def _run_heuristic_pair(
    *,
    qc_id: int,
    pc_id: int,
    doc_id: int,
) -> None:
    async with async_session_maker() as session:
        run = await execute_retrieval_benchmark_run(
            session,
            query_case_id=qc_id,
            pipeline_config_id=pc_id,
            document_id=doc_id,
            commit=True,
        )
        rid = run.id
        retrieval_ms = run.retrieval_latency_ms or 0

    t0 = time.perf_counter()
    async with async_session_maker() as session:
        ev = await compute_minimal_retrieval_evaluation(session, run_id=rid)
    eval_ms = max(0, int((time.perf_counter() - t0) * 1000))
    total_ms = retrieval_ms + eval_ms

    async with async_session_maker() as session:
        await persist_evaluation_and_complete_run(
            session,
            run_id=rid,
            evaluation_latency_ms=eval_ms,
            total_latency_ms=total_ms,
            faithfulness=ev.faithfulness,
            completeness=ev.completeness,
            retrieval_relevance=ev.retrieval_relevance,
            context_coverage=ev.context_coverage,
            failure_type=ev.failure_type,
            used_llm_judge=ev.used_llm_judge,
            cost_usd=None,
            metadata_json=ev.metadata_json,
            commit=True,
        )
    print(f"run_id={rid} qc={qc_id} pc={pc_id} mode=heuristic retrieval_ms={retrieval_ms} eval_ms={eval_ms}")


async def _run_full_rag_pair(
    *,
    qc_id: int,
    pc_id: int,
    doc_id: int,
) -> None:
    async with async_session_maker() as session:
        run = await execute_retrieval_benchmark_run(
            session,
            query_case_id=qc_id,
            pipeline_config_id=pc_id,
            document_id=doc_id,
            commit=True,
        )
        rid = run.id
        retrieval_ms = run.retrieval_latency_ms or 0

    async with async_session_maker() as session:
        await execute_generation_for_run(session, run_id=rid, commit=True)

    async with async_session_maker() as session:
        await execute_llm_judge_and_complete_run(session, run_id=rid, commit=True)

    async with async_session_maker() as session:
        run = await session.get(Run, rid)
        assert run is not None
        g_ms = run.generation_latency_ms or 0
        e_ms = run.evaluation_latency_ms or 0
        tot = run.total_latency_ms or 0

    print(
        f"run_id={rid} qc={qc_id} pc={pc_id} mode=full "
        f"retrieval_ms={retrieval_ms} generation_ms={g_ms} eval_ms={e_ms} total_ms={tot}"
    )


async def _main(
    *,
    skip_seed: bool,
    document_id: int | None,
    eval_mode: str,
) -> None:
    if eval_mode == "full":
        from app.services.llm_provider_keys import require_llm_api_key_for_full_mode

        try:
            require_llm_api_key_for_full_mode()
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    async with async_session_maker() as session:
        if skip_seed:
            seed = await get_benchmark_seed_result(session)
        else:
            seed = await ensure_benchmark_seed(session, commit=True)

        if document_id is not None:
            doc_id = document_id
        else:
            doc = await ensure_quickstart_corpus_document(session, commit=True)
            doc_id = doc.id

    n_runs = 0
    for pc_id in seed.pipeline_config_ids:
        for qc_id in seed.query_case_ids:
            if eval_mode == "heuristic":
                await _run_heuristic_pair(qc_id=qc_id, pc_id=pc_id, doc_id=doc_id)
            else:
                await _run_full_rag_pair(qc_id=qc_id, pc_id=pc_id, doc_id=doc_id)
            n_runs += 1

    print(f"Done. Completed {n_runs} traced runs.")
    print("Regenerate metrics: python scripts/generate_contextlens_metrics.py --format markdown")


def main() -> None:
    p = argparse.ArgumentParser(description="Run quickstart benchmark.")
    p.add_argument(
        "--skip-seed",
        action="store_true",
        help="Do not create seed rows; require existing quickstart dataset and configs.",
    )
    p.add_argument(
        "--document-id",
        type=int,
        default=None,
        help="Restrict retrieval to this document; skip corpus ingest when set.",
    )
    p.add_argument(
        "--eval-mode",
        choices=("heuristic", "full"),
        default="heuristic",
        help="heuristic: no LLM. full: Claude generation + LLM judge (requires API key).",
    )
    args = p.parse_args()
    asyncio.run(
        _main(
            skip_seed=args.skip_seed,
            document_id=args.document_id,
            eval_mode=args.eval_mode,
        )
    )


if __name__ == "__main__":
    main()
