"""Idempotent seed + corpus ingest for the evidence-rag-v1 benchmark dataset.

Reads files from ``benchmark-datasets/evidence-rag-v1/`` at the repository root.
Does not invent metrics — only registry rows, document ingest, and chunk embeddings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Dataset, Document, PipelineConfig, QueryCase
from app.services import trace_persistence as tp
from app.services.chunker import ChunkStrategy
from app.services.text_document_ingest import ingest_plain_text

EVIDENCE_DATASET_NAME = "evidence_rag_technical_v1"
EVIDENCE_DOC_TITLE = "Evidence RAG v1 — combined technical corpus"
EVIDENCE_SEED_META = {"seed": "evidence_rag_v1", "dataset_slug": "evidence-rag-v1"}

# Distinct top_k values drive measurable retrieval/latency/heuristic differences.
EVIDENCE_PIPELINE_SPECS: tuple[dict[str, int | str | dict], ...] = (
    {
        "name": "evidence_topk3",
        "top_k": 3,
        "chunk_size": 256,
        "chunk_overlap": 0,
        "metadata_json": {**EVIDENCE_SEED_META, "role": "narrow_retrieval"},
    },
    {
        "name": "evidence_topk6",
        "top_k": 6,
        "chunk_size": 384,
        "chunk_overlap": 64,
        "metadata_json": {**EVIDENCE_SEED_META, "role": "balanced_retrieval"},
    },
    {
        "name": "evidence_topk10",
        "top_k": 10,
        "chunk_size": 512,
        "chunk_overlap": 128,
        "metadata_json": {**EVIDENCE_SEED_META, "role": "broad_retrieval"},
    },
)


def default_evidence_dataset_dir() -> Path:
    """``ContextLens/benchmark-datasets/evidence-rag-v1`` from ``backend/app/services``."""
    return Path(__file__).resolve().parents[3] / "benchmark-datasets" / "evidence-rag-v1"


def load_manifest(evidence_dir: Path) -> dict:
    path = evidence_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_queries(evidence_dir: Path) -> list[dict[str, str]]:
    path = evidence_dir / "queries.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing queries: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("queries.json must be a non-empty list")
    for i, row in enumerate(raw):
        if not isinstance(row, dict) or "query_text" not in row or "expected_answer" not in row:
            raise ValueError(f"queries.json[{i}] needs query_text and expected_answer")
    return raw


def build_combined_corpus_text(evidence_dir: Path, manifest: dict | None = None) -> str:
    manifest = manifest or load_manifest(evidence_dir)
    files = manifest.get("corpus_files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest.json corpus_files must be a non-empty list")
    parts: list[str] = []
    for rel in files:
        p = evidence_dir / rel
        if not p.is_file():
            raise FileNotFoundError(f"Corpus file missing: {p}")
        parts.append(p.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


@dataclass(frozen=True, slots=True)
class EvidenceBenchmarkSeedResult:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    pipeline_config_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EvidenceBenchmarkReady:
    """Registry + combined corpus document (after ``ensure_evidence_corpus_document``)."""

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


async def ensure_evidence_benchmark_seed(
    session: AsyncSession,
    evidence_dir: Path | None = None,
    *,
    commit: bool = True,
) -> EvidenceBenchmarkSeedResult:
    """Create or reuse evidence dataset, query cases, and three pipeline configs."""
    evidence_dir = evidence_dir or default_evidence_dataset_dir()
    queries = load_queries(evidence_dir)
    n_expected = len(queries)

    model = settings.embedding_model_name
    ds = await _get_dataset_by_name(session, EVIDENCE_DATASET_NAME)
    if ds is None:
        ds = await tp.create_dataset(
            session,
            name=EVIDENCE_DATASET_NAME,
            description=(
                "Evidence-backed benchmark: eight technical queries over a combined "
                "multi-topic corpus (see benchmark-datasets/evidence-rag-v1/)."
            ),
            metadata_json=dict(EVIDENCE_SEED_META),
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
                metadata_json=dict(EVIDENCE_SEED_META),
            )
        await session.flush()
        qcs = (
            await session.execute(
                select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
            )
        ).scalars().all()
    elif len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {EVIDENCE_DATASET_NAME!r} exists with {len(qcs)} query cases; "
            f"expected 0 or {n_expected}. Rename/remove the dataset to re-seed."
        )

    query_case_ids = tuple(qc.id for qc in qcs[:n_expected])

    pipeline_config_ids: list[int] = []
    for spec in EVIDENCE_PIPELINE_SPECS:
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

    return EvidenceBenchmarkSeedResult(
        dataset_id=ds.id,
        query_case_ids=query_case_ids,
        pipeline_config_ids=tuple(pipeline_config_ids),
    )


async def ensure_evidence_corpus_document(
    session: AsyncSession,
    evidence_dir: Path | None = None,
    *,
    commit: bool = True,
) -> Document:
    """Ingest combined corpus once; reuse existing processed doc with the evidence title."""
    evidence_dir = evidence_dir or default_evidence_dataset_dir()
    manifest = load_manifest(evidence_dir)
    text = build_combined_corpus_text(evidence_dir, manifest)

    r = await session.execute(
        select(Document).where(
            Document.title == EVIDENCE_DOC_TITLE,
            Document.status == "processed",
        )
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    return await ingest_plain_text(
        session,
        title=EVIDENCE_DOC_TITLE,
        text=text,
        chunk_strategy=ChunkStrategy.FIXED,
        chunk_size=384,
        chunk_overlap=64,
        metadata_json={**EVIDENCE_SEED_META, "artifact": "evidence_combined_corpus_v1"},
        commit=commit,
    )


async def get_evidence_benchmark_ready(
    session: AsyncSession,
    evidence_dir: Path | None = None,
) -> EvidenceBenchmarkReady:
    """Return seed IDs and evidence document id; raise if registry or corpus is missing."""
    evidence_dir = evidence_dir or default_evidence_dataset_dir()
    queries = load_queries(evidence_dir)
    n_expected = len(queries)

    ds = await _get_dataset_by_name(session, EVIDENCE_DATASET_NAME)
    if ds is None:
        raise ValueError(
            f"Dataset {EVIDENCE_DATASET_NAME!r} not found. "
            "Run: python scripts/seed_evidence_benchmark.py"
        )
    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()
    if len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {EVIDENCE_DATASET_NAME!r} has {len(qcs)} query cases; expected {n_expected}."
        )
    pipeline_config_ids: list[int] = []
    for spec in EVIDENCE_PIPELINE_SPECS:
        pc = await _get_pipeline_by_name(session, str(spec["name"]))
        if pc is None:
            raise ValueError(
                f"Pipeline {spec['name']!r} missing. Run: python scripts/seed_evidence_benchmark.py"
            )
        pipeline_config_ids.append(pc.id)

    r = await session.execute(
        select(Document).where(
            Document.title == EVIDENCE_DOC_TITLE,
            Document.status == "processed",
        )
    )
    doc = r.scalar_one_or_none()
    if doc is None:
        raise ValueError(
            "Evidence corpus document missing. Run: python scripts/run_evidence_benchmark.py "
            "(or ingest via ensure_evidence_corpus_document)."
        )

    return EvidenceBenchmarkReady(
        dataset_id=ds.id,
        query_case_ids=tuple(qc.id for qc in qcs),
        pipeline_config_ids=tuple(pipeline_config_ids),
        document_id=doc.id,
    )
