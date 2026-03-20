"""Idempotent benchmark dataset / query case / pipeline config seeding.

Does not invent timings or evaluation scores — only registry rows for runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Dataset, Document, PipelineConfig, QueryCase
from app.services import trace_persistence as tp
from app.services.chunker import ChunkStrategy
from app.services.text_document_ingest import ingest_plain_text

# Stable names for idempotency and runner discovery
BENCHMARK_DATASET_NAME = "contextlens_quickstart"
QUICKSTART_CORPUS_TITLE = "ContextLens quickstart corpus"
PIPELINE_TOP5_NAME = "quickstart_top5"
PIPELINE_TOP8_NAME = "quickstart_top8"

# Shared synthetic corpus: topics are consistent with query cases below.
BENCHMARK_CORPUS_TEXT = """
ContextLens is a retrieval and evaluation harness for RAG systems.
Dense vector retrieval embeds documents and queries with the same model, then
ranks chunks by cosine similarity in pgvector.

Benchmark runs store one row per query case and pipeline configuration.
Measured retrieval latency is written when vector search finishes.
Evaluation rows may use heuristic scorers that read persisted retrieval scores
without calling an external LLM API.

Latency aggregates in metrics reports include only runs whose corresponding
latency column is non-null in the database.
""".strip()

# Query cases: expected_answer strings are taken verbatim from the corpus text
# for lexical completeness checks (not hand-picked numeric scores).
QUICKSTART_QUERY_CASES: list[dict[str, str]] = [
    {
        "query_text": "How does ContextLens rank chunks?",
        "expected_answer": "ranks chunks by cosine similarity in pgvector",
    },
    {
        "query_text": "What embedding approach is described?",
        "expected_answer": "Dense vector retrieval embeds documents and queries",
    },
    {
        "query_text": "Where is retrieval latency stored?",
        "expected_answer": "Measured retrieval latency is written when vector search finishes",
    },
]


@dataclass(frozen=True, slots=True)
class BenchmarkSeedResult:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    pipeline_config_ids: tuple[int, ...]


async def _get_dataset_by_name(session: AsyncSession, name: str) -> Dataset | None:
    r = await session.execute(select(Dataset).where(Dataset.name == name))
    return r.scalar_one_or_none()


async def _get_pipeline_by_name(session: AsyncSession, name: str) -> PipelineConfig | None:
    r = await session.execute(select(PipelineConfig).where(PipelineConfig.name == name))
    return r.scalar_one_or_none()


async def ensure_benchmark_seed(session: AsyncSession, *, commit: bool = True) -> BenchmarkSeedResult:
    """Create or reuse the quickstart dataset, query cases, and two pipeline configs."""
    model = settings.embedding_model_name
    ds = await _get_dataset_by_name(session, BENCHMARK_DATASET_NAME)
    if ds is None:
        ds = await tp.create_dataset(
            session,
            name=BENCHMARK_DATASET_NAME,
            description="Minimal benchmark seed for ContextLens metrics (idempotent).",
            metadata_json={"seed": "contextlens_quickstart_v1"},
        )

    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()

    n_expected = len(QUICKSTART_QUERY_CASES)
    if len(qcs) == 0:
        for spec in QUICKSTART_QUERY_CASES:
            await tp.create_query_case(
                session,
                dataset_id=ds.id,
                query_text=spec["query_text"],
                expected_answer=spec["expected_answer"],
                metadata_json={"seed": "contextlens_quickstart_v1"},
            )
        await session.flush()
        qcs = (
            await session.execute(
                select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
            )
        ).scalars().all()
    elif len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {BENCHMARK_DATASET_NAME!r} exists with {len(qcs)} query cases; "
            f"expected 0 or {n_expected}. Remove or rename the dataset to re-seed."
        )

    query_case_ids = tuple(qc.id for qc in qcs[:n_expected])

    pc5 = await _get_pipeline_by_name(session, PIPELINE_TOP5_NAME)
    if pc5 is None:
        pc5 = await tp.create_pipeline_config(
            session,
            name=PIPELINE_TOP5_NAME,
            embedding_model=model,
            chunk_strategy="fixed",
            chunk_size=256,
            chunk_overlap=0,
            top_k=5,
            metadata_json={"seed": "contextlens_quickstart_v1"},
        )

    pc8 = await _get_pipeline_by_name(session, PIPELINE_TOP8_NAME)
    if pc8 is None:
        pc8 = await tp.create_pipeline_config(
            session,
            name=PIPELINE_TOP8_NAME,
            embedding_model=model,
            chunk_strategy="fixed",
            chunk_size=256,
            chunk_overlap=0,
            top_k=8,
            metadata_json={"seed": "contextlens_quickstart_v1"},
        )

    pipeline_config_ids = (pc5.id, pc8.id)

    if commit:
        await session.commit()

    return BenchmarkSeedResult(
        dataset_id=ds.id,
        query_case_ids=query_case_ids,
        pipeline_config_ids=pipeline_config_ids,
    )


async def get_benchmark_seed_result(session: AsyncSession) -> BenchmarkSeedResult:
    """Return IDs for an existing quickstart seed; raise if missing or incomplete."""
    ds = await _get_dataset_by_name(session, BENCHMARK_DATASET_NAME)
    if ds is None:
        raise ValueError(
            f"Dataset {BENCHMARK_DATASET_NAME!r} not found. Run: python scripts/seed_benchmark.py"
        )
    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()
    n_expected = len(QUICKSTART_QUERY_CASES)
    if len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {BENCHMARK_DATASET_NAME!r} has {len(qcs)} query cases; expected {n_expected}."
        )
    pc5 = await _get_pipeline_by_name(session, PIPELINE_TOP5_NAME)
    pc8 = await _get_pipeline_by_name(session, PIPELINE_TOP8_NAME)
    if pc5 is None or pc8 is None:
        raise ValueError("Quickstart pipeline configs missing. Run: python scripts/seed_benchmark.py")
    return BenchmarkSeedResult(
        dataset_id=ds.id,
        query_case_ids=tuple(qc.id for qc in qcs),
        pipeline_config_ids=(pc5.id, pc8.id),
    )


async def ensure_quickstart_corpus_document(
    session: AsyncSession,
    *,
    commit: bool = True,
) -> Document:
    """Ingest ``BENCHMARK_CORPUS_TEXT`` once; reuse an existing processed doc with the same title."""
    r = await session.execute(
        select(Document).where(
            Document.title == QUICKSTART_CORPUS_TITLE,
            Document.status == "processed",
        )
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    return await ingest_plain_text(
        session,
        title=QUICKSTART_CORPUS_TITLE,
        text=BENCHMARK_CORPUS_TEXT,
        chunk_strategy=ChunkStrategy.FIXED,
        chunk_size=256,
        chunk_overlap=0,
        metadata_json={"benchmark_artifact": "quickstart_corpus_v1"},
        commit=commit,
    )
