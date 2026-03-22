#!/usr/bin/env python3
"""Print Markdown summary of completed rag_systems_retrieval_engineering_v1 runs.

Requires prior ``run_rag_systems_benchmark.py``. Numbers are read from stored rows only.

Usage (from ``backend/``)::

    python scripts/export_rag_systems_benchmark_summary.py
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
from app.services.benchmark_rag_systems_seed import (  # noqa: E402
    RAG_SYSTEMS_DATASET_NAME,
    RAG_SYSTEMS_VARIANTS,
)


def _variant_order() -> dict[str, int]:
    return {name: i for i, (name, _a, _b, _c) in enumerate(RAG_SYSTEMS_VARIANTS)}


async def _gather(session: AsyncSession) -> None:
    stmt = (
        select(
            PipelineConfig.name.label("pc_name"),
            PipelineConfig.top_k,
            PipelineConfig.chunk_size,
            PipelineConfig.metadata_json,
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
            Dataset.name == RAG_SYSTEMS_DATASET_NAME,
            Run.status == "completed",
        )
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        print("# RAG systems retrieval engineering v1 — no completed runs found\n")
        print(f"Dataset `{RAG_SYSTEMS_DATASET_NAME}` has no completed runs. Run:")
        print("  python scripts/run_rag_systems_benchmark.py")
        return

    order = _variant_order()
    by_pc: dict[str, list] = {}
    for r in rows:
        by_pc.setdefault(r.pc_name, []).append(r)

    print("# RAG systems retrieval engineering v1 — measured summary\n")
    print("Source: PostgreSQL rows for dataset `" + RAG_SYSTEMS_DATASET_NAME + "`.\n")

    def sort_key(n: str) -> tuple[int, str]:
        return (order.get(n, 99), n)

    for pc_name in sorted(by_pc.keys(), key=sort_key):
        chunk = by_pc[pc_name]
        n = len(chunk)
        rel_ms = [x.retrieval_latency_ms for x in chunk if x.retrieval_latency_ms is not None]
        tot_ms = [x.total_latency_ms for x in chunk if x.total_latency_ms is not None]
        failures = [x.failure_type for x in chunk if x.failure_type and x.failure_type != "NO_FAILURE"]
        rel_scores = [x.retrieval_relevance for x in chunk if x.retrieval_relevance is not None]
        cov_scores = [x.context_coverage for x in chunk if x.context_coverage is not None]
        comp_scores = [x.completeness for x in chunk if x.completeness is not None]

        avg_rel = sum(rel_ms) / len(rel_ms) if rel_ms else None
        avg_tot = sum(tot_ms) / len(tot_ms) if tot_ms else None
        fail_rate = len(failures) / n if n else 0.0
        avg_rr = sum(rel_scores) / len(rel_scores) if rel_scores else None
        avg_cov = sum(cov_scores) / len(cov_scores) if cov_scores else None
        avg_comp = sum(comp_scores) / len(comp_scores) if comp_scores else None

        ft_counts = Counter(failures)
        dominant = ft_counts.most_common(2)
        meta = chunk[0].metadata_json or {}
        ingest_cs = meta.get("ingest_chunk_size")

        print(f"## `{pc_name}` (top_k={chunk[0].top_k}, ingest chunk_size≈{ingest_cs or chunk[0].chunk_size})\n")
        print(f"- **Runs (completed):** {n}")
        if avg_rel is not None:
            print(f"- **Avg retrieval latency (ms):** {avg_rel:.1f}")
        if avg_tot is not None:
            print(f"- **Avg total latency (ms):** {avg_tot:.1f}")
        print(f"- **Failure rate** (failure_type ≠ NO_FAILURE): **{fail_rate:.1%}**")
        if avg_rr is not None:
            print(f"- **Avg retrieval_relevance:** {avg_rr:.4f}")
        if avg_cov is not None:
            print(f"- **Avg context_coverage:** {avg_cov:.4f}")
        if avg_comp is not None:
            print(f"- **Avg completeness:** {avg_comp:.4f}")
        if dominant:
            lines = ", ".join(f"`{k}` × {v}" for k, v in dominant)
            print(f"- **Top failure types (non-NO_FAILURE):** {lines}")
        print()

    print("## Comparison notes\n")
    print("_Heuristic evaluator; cost_usd is NULL. Latency varies with embedder warm-up and DB load._")
    print("Configs differ by **ingest chunk size** (scoped document per config) and **top_k**.\n")


async def _main() -> None:
    async with async_session_maker() as session:
        await _gather(session)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
