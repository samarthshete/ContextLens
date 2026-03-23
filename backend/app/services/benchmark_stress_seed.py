"""Idempotent seed + corpus for evidence-stress-v1 (harder retrieval / completeness stress).

Corpus is intentionally **narrow** (Redis memory/eviction only). Several queries are **off-topic**
(Istio, PostgreSQL, gRPC) so lexical overlap and embedding retrieval often score poorly — realistic
failure modes without fabricating LLM outputs.

Data lives at repo ``benchmark-datasets/evidence-stress-v1/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Dataset, Document, PipelineConfig, QueryCase
from app.services import trace_persistence as tp
from app.services.benchmark_evidence_seed import (
    build_combined_corpus_text,
    load_manifest,
    load_queries,
)
from app.services.chunker import ChunkStrategy
from app.services.text_document_ingest import ingest_plain_text

STRESS_DATASET_NAME = "evidence_stress_retrieval_v1"
STRESS_DOC_TITLE = "Evidence stress v1 — Redis memory corpus (narrow)"
STRESS_SEED_META = {"seed": "evidence_stress_v1", "dataset_slug": "evidence-stress-v1"}

STRESS_PIPELINE_SPECS: tuple[dict[str, int | str | dict], ...] = (
    {
        "name": "stress_topk3",
        "top_k": 3,
        "chunk_size": 256,
        "chunk_overlap": 0,
        "metadata_json": {**STRESS_SEED_META, "role": "narrow_topk"},
    },
    {
        "name": "stress_topk8",
        "top_k": 8,
        "chunk_size": 256,
        "chunk_overlap": 0,
        "metadata_json": {**STRESS_SEED_META, "role": "wide_topk"},
    },
)


def default_stress_dataset_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmark-datasets" / "evidence-stress-v1"


@dataclass(frozen=True, slots=True)
class StressBenchmarkSeedResult:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    pipeline_config_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StressBenchmarkReady:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    pipeline_config_ids: tuple[int, ...]
    document_id: int


async def _get_dataset_by_name(session: AsyncSession, name: str) -> Dataset | None:
    r = await session.execute(select(Dataset).where(Dataset.name == name))
    return r.scalar_one_or_none()


async def _get_pipeline_by_name(session: AsyncSession, name: str) -> PipelineConfig | None:
    r = await session.execute(select(PipelineConfig).where(PipelineConfig.name == name))
    return r.scalar_one_or_none()


async def ensure_stress_benchmark_seed(
    session: AsyncSession,
    stress_dir: Path | None = None,
    *,
    commit: bool = True,
) -> StressBenchmarkSeedResult:
    stress_dir = stress_dir or default_stress_dataset_dir()
    queries = load_queries(stress_dir)
    n_expected = len(queries)
    model = settings.embedding_model_name

    ds = await _get_dataset_by_name(session, STRESS_DATASET_NAME)
    if ds is None:
        ds = await tp.create_dataset(
            session,
            name=STRESS_DATASET_NAME,
            description=(
                "Stress benchmark: narrow Redis memory corpus + off-topic queries "
                "(benchmark-datasets/evidence-stress-v1/)."
            ),
            metadata_json=dict(STRESS_SEED_META),
        )

    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()

    if len(qcs) == 0:
        for row in queries:
            await tp.create_query_case(
                session,
                dataset_id=ds.id,
                query_text=row["query_text"],
                expected_answer=row["expected_answer"],
                metadata_json=dict(STRESS_SEED_META),
            )
        await session.flush()
        qcs = (
            await session.execute(
                select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
            )
        ).scalars().all()
    elif len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {STRESS_DATASET_NAME!r} exists with {len(qcs)} query cases; "
            f"expected 0 or {n_expected}. Rename/remove the dataset to re-seed."
        )

    query_case_ids = tuple(qc.id for qc in qcs[:n_expected])
    pipeline_config_ids: list[int] = []
    for spec in STRESS_PIPELINE_SPECS:
        name = str(spec["name"])
        pc = await _get_pipeline_by_name(session, name)
        if pc is None:
            pc = await tp.create_pipeline_config(
                session,
                name=name,
                embedding_model=model,
                chunk_strategy="fixed",
                chunk_size=int(spec["chunk_size"]),
                chunk_overlap=int(spec["chunk_overlap"]),
                top_k=int(spec["top_k"]),
                metadata_json=dict(spec["metadata_json"]),  # type: ignore[arg-type]
            )
        pipeline_config_ids.append(pc.id)

    if commit:
        await session.commit()

    return StressBenchmarkSeedResult(
        dataset_id=ds.id,
        query_case_ids=query_case_ids,
        pipeline_config_ids=tuple(pipeline_config_ids),
    )


async def ensure_stress_corpus_document(
    session: AsyncSession,
    stress_dir: Path | None = None,
    *,
    commit: bool = True,
) -> Document:
    stress_dir = stress_dir or default_stress_dataset_dir()
    manifest = load_manifest(stress_dir)
    text = build_combined_corpus_text(stress_dir, manifest)

    r = await session.execute(
        select(Document).where(
            Document.title == STRESS_DOC_TITLE,
            Document.status == "processed",
        )
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    return await ingest_plain_text(
        session,
        title=STRESS_DOC_TITLE,
        text=text,
        chunk_strategy=ChunkStrategy.FIXED,
        chunk_size=256,
        chunk_overlap=0,
        metadata_json={**STRESS_SEED_META, "artifact": "evidence_stress_corpus_v1"},
        commit=commit,
    )


async def get_stress_benchmark_ready(
    session: AsyncSession,
    stress_dir: Path | None = None,
) -> StressBenchmarkReady:
    stress_dir = stress_dir or default_stress_dataset_dir()
    queries = load_queries(stress_dir)
    n_expected = len(queries)

    ds = await _get_dataset_by_name(session, STRESS_DATASET_NAME)
    if ds is None:
        raise ValueError(
            f"Dataset {STRESS_DATASET_NAME!r} not found. "
            "Run: python scripts/seed_evidence_stress_benchmark.py"
        )
    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()
    if len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {STRESS_DATASET_NAME!r} has {len(qcs)} query cases; expected {n_expected}."
        )
    pipeline_config_ids: list[int] = []
    for spec in STRESS_PIPELINE_SPECS:
        pc = await _get_pipeline_by_name(session, str(spec["name"]))
        if pc is None:
            raise ValueError(
                f"Pipeline {spec['name']!r} missing. Run: python scripts/seed_evidence_stress_benchmark.py"
            )
        pipeline_config_ids.append(pc.id)

    r = await session.execute(
        select(Document).where(
            Document.title == STRESS_DOC_TITLE,
            Document.status == "processed",
        )
    )
    doc = r.scalar_one_or_none()
    if doc is None:
        raise ValueError(
            "Stress corpus document missing. Run: python scripts/seed_evidence_stress_benchmark.py"
        )

    return StressBenchmarkReady(
        dataset_id=ds.id,
        query_case_ids=tuple(qc.id for qc in qcs),
        pipeline_config_ids=tuple(pipeline_config_ids),
        document_id=doc.id,
    )
