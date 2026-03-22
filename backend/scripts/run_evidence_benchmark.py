#!/usr/bin/env python3
"""Seed (if needed), ingest combined evidence corpus, run heuristic benchmark for all pairs.

Uses real retrieval + ``minimal_retrieval_heuristic_v1`` (no LLM). Retrieval is scoped to
the evidence document only so other ingested corpora do not affect scores.

Usage (from ``backend/``)::

    python scripts/run_evidence_benchmark.py
    python scripts/run_evidence_benchmark.py --skip-seed
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
from app.services.benchmark_evidence_seed import (  # noqa: E402
    ensure_evidence_benchmark_seed,
    ensure_evidence_corpus_document,
    get_evidence_benchmark_ready,
)
from app.services.benchmark_run import execute_retrieval_benchmark_run  # noqa: E402
from app.services.evaluation_persistence import persist_evaluation_and_complete_run  # noqa: E402
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
    print(
        f"run_id={rid} qc={qc_id} pc={pc_id} mode=heuristic "
        f"retrieval_ms={retrieval_ms} eval_ms={eval_ms} failure={ev.failure_type or 'NO_FAILURE'}"
    )


async def _main(*, skip_seed: bool, evidence_dir: Path | None) -> None:
    async with async_session_maker() as session:
        if not skip_seed:
            await ensure_evidence_benchmark_seed(session, evidence_dir, commit=True)
        doc = await ensure_evidence_corpus_document(session, evidence_dir, commit=True)
        doc_id = doc.id

    async with async_session_maker() as session:
        ready = await get_evidence_benchmark_ready(session, evidence_dir)
    assert ready.document_id == doc_id

    n_runs = 0
    for pc_id in ready.pipeline_config_ids:
        for qc_id in ready.query_case_ids:
            await _run_heuristic_pair(qc_id=qc_id, pc_id=pc_id, doc_id=doc_id)
            n_runs += 1

    print(f"Done. Completed {n_runs} evidence traced runs (document_id={doc_id}).")
    print("Summary: python scripts/export_evidence_benchmark_summary.py")


def main() -> None:
    p = argparse.ArgumentParser(description="Run evidence-rag-v1 heuristic benchmark.")
    p.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip registry creation; require existing evidence dataset and corpus.",
    )
    p.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="Path to benchmark-datasets/evidence-rag-v1 (default: repo default).",
    )
    args = p.parse_args()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    asyncio.run(_main(skip_seed=args.skip_seed, evidence_dir=evidence_dir))


if __name__ == "__main__":
    main()
