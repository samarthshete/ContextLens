#!/usr/bin/env python3
"""Print Markdown summary of completed evidence benchmark runs from the database.

Joins ``runs`` for query cases in ``evidence_rag_technical_v1`` with evaluation rows.
Requires prior ``run_evidence_benchmark.py``. Numbers are read from stored rows only.

Usage (from ``backend/``)::

    python scripts/export_evidence_benchmark_summary.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models import Dataset, EvaluationResult, PipelineConfig, QueryCase, Run  # noqa: E402
from app.services.benchmark_evidence_seed import EVIDENCE_DATASET_NAME  # noqa: E402


async def _gather(session: AsyncSession) -> None:
    stmt = (
        select(
            PipelineConfig.name.label("pc_name"),
            PipelineConfig.top_k,
            Run.id,
            Run.retrieval_latency_ms,
            Run.total_latency_ms,
            EvaluationResult.failure_type,
            EvaluationResult.retrieval_relevance,
            EvaluationResult.context_coverage,
            EvaluationResult.completeness,
        )
        .join(QueryCase, Run.query_case_id == QueryCase.id)
        .join(Dataset, QueryCase.dataset_id == Dataset.id)
        .join(PipelineConfig, Run.pipeline_config_id == PipelineConfig.id)
        .outerjoin(EvaluationResult, EvaluationResult.run_id == Run.id)
        .where(
            Dataset.name == EVIDENCE_DATASET_NAME,
            Run.status == "completed",
        )
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        print("# Evidence benchmark — no completed runs found\n")
        print(f"Dataset `{EVIDENCE_DATASET_NAME}` has no completed runs. Run:")
        print("  python scripts/run_evidence_benchmark.py")
        return

    by_pc: dict[str, list] = {}
    for r in rows:
        by_pc.setdefault(r.pc_name, []).append(r)

    print("# Evidence benchmark — measured summary\n")
    print("Source: PostgreSQL rows for dataset `" + EVIDENCE_DATASET_NAME + "`.\n")

    for pc_name in sorted(by_pc.keys(), key=lambda n: (by_pc[n][0].top_k, n)):
        chunk = by_pc[pc_name]
        n = len(chunk)
        rel_ms = [x.retrieval_latency_ms for x in chunk if x.retrieval_latency_ms is not None]
        tot_ms = [x.total_latency_ms for x in chunk if x.total_latency_ms is not None]
        failures = [x.failure_type for x in chunk if x.failure_type and x.failure_type != "NO_FAILURE"]
        rel_scores = [x.retrieval_relevance for x in chunk if x.retrieval_relevance is not None]

        avg_rel = sum(rel_ms) / len(rel_ms) if rel_ms else None
        avg_tot = sum(tot_ms) / len(tot_ms) if tot_ms else None
        fail_rate = len(failures) / n if n else 0.0
        avg_rr = sum(rel_scores) / len(rel_scores) if rel_scores else None

        ft_counts = Counter(failures)
        dominant = ft_counts.most_common(2)

        print(f"## `{pc_name}` (top_k={chunk[0].top_k})\n")
        print(f"- **Runs (completed):** {n}")
        if avg_rel is not None:
            print(f"- **Avg retrieval latency (ms):** {avg_rel:.1f}")
        if avg_tot is not None:
            print(f"- **Avg total latency (ms):** {avg_tot:.1f}")
        print(f"- **Failure rate** (failure_type ≠ NO_FAILURE): **{fail_rate:.1%}**")
        if avg_rr is not None:
            print(f"- **Avg retrieval_relevance:** {avg_rr:.4f}")
        if dominant:
            lines = ", ".join(f"`{k}` × {v}" for k, v in dominant)
            print(f"- **Top failure types (non-NO_FAILURE):** {lines}")
        print()

    print("## Comparison notes\n")
    print("_Interpretation depends on environment (CPU, embedder cold start, DB size)._")
    print("Higher **top_k** typically increases retrieval work and can change which chunks")
    print("enter the heuristic context, affecting relevance/coverage scores and failure mix.\n")


async def _main() -> None:
    async with async_session_maker() as session:
        await _gather(session)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
