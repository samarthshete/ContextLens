"""Idempotent seed + per-config corpus variants for ``rag_systems_retrieval_engineering_v1``.

Each pipeline config is tied to its own ingested document (same combined text, different
chunk_size / overlap) via ``metadata_json["scoped_document_id"]`` so retrieval reflects
real chunking trade-offs without mixing chunk scales in one index.

Dataset files live under ``backend/benchmark_data/rag_systems_retrieval_engineering_v1/``.
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

RAG_SYSTEMS_DATASET_NAME = "rag_systems_retrieval_engineering_v1"
RAG_SYSTEMS_SEED_META = {
    "seed": "rag_systems_retrieval_engineering_v1",
    "dataset_slug": "rag_systems_retrieval_engineering_v1",
}

# (config_name, ingest_chunk_size, ingest_chunk_overlap, top_k)
# Ingest sizes approximate requested ~380 / ~720 / ~1200 char chunks; top_k as specified.
RAG_SYSTEMS_VARIANTS: tuple[tuple[str, int, int, int], ...] = (
    ("baseline_fast_small", 380, 40, 3),
    ("balanced_medium", 720, 80, 5),
    ("context_heavy_large", 1200, 120, 7),
)


def default_rag_systems_dataset_dir() -> Path:
    """``backend/benchmark_data/rag_systems_retrieval_engineering_v1``."""
    return Path(__file__).resolve().parents[2] / "benchmark_data" / "rag_systems_retrieval_engineering_v1"


def load_manifest(data_dir: Path) -> dict:
    path = data_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_queries(data_dir: Path) -> list[dict[str, str | int]]:
    path = data_dir / "queries.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing queries: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("queries.json must be a non-empty list")
    out: list[dict[str, str | int]] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"queries.json[{i}] must be an object")
        qt = row.get("query_text") or row.get("query")
        ea = row.get("expected_answer")
        if not isinstance(qt, str) or not isinstance(ea, str):
            raise ValueError(f"queries.json[{i}] needs query_text (or query) and expected_answer strings")
        out.append({"query_text": qt, "expected_answer": ea, **({"id": row["id"]} if "id" in row else {})})
    return out


def build_combined_corpus_text(data_dir: Path, manifest: dict | None = None) -> str:
    manifest = manifest or load_manifest(data_dir)
    files = manifest.get("corpus_files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest.json corpus_files must be a non-empty list")
    parts: list[str] = []
    for rel in files:
        p = data_dir / rel
        if not p.is_file():
            raise FileNotFoundError(f"Corpus file missing: {p}")
        parts.append(p.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


def variant_document_title(variant_name: str) -> str:
    return f"RAG Systems Retrieval Engineering v1 — {variant_name}"


@dataclass(frozen=True, slots=True)
class RAGSystemsSeedResult:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    """(config_name, pipeline_config_id, scoped_document_id) in variant order."""
    run_plan: tuple[tuple[str, int, int], ...]


async def _get_dataset_by_name(session: AsyncSession, name: str) -> Dataset | None:
    r = await session.execute(select(Dataset).where(Dataset.name == name))
    return r.scalar_one_or_none()


async def _get_pipeline_by_name(session: AsyncSession, name: str) -> PipelineConfig | None:
    r = await session.execute(select(PipelineConfig).where(PipelineConfig.name == name))
    return r.scalar_one_or_none()


async def _ensure_variant_document(
    session: AsyncSession,
    *,
    combined_text: str,
    variant_name: str,
    chunk_size: int,
    chunk_overlap: int,
    commit: bool,
) -> Document:
    title = variant_document_title(variant_name)
    r = await session.execute(
        select(Document).where(
            Document.title == title,
            Document.status == "processed",
        )
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    return await ingest_plain_text(
        session,
        title=title,
        text=combined_text,
        chunk_strategy=ChunkStrategy.FIXED,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata_json={
            **RAG_SYSTEMS_SEED_META,
            "variant": variant_name,
            "ingest_chunk_size": chunk_size,
            "ingest_chunk_overlap": chunk_overlap,
        },
        commit=commit,
    )


async def ensure_rag_systems_benchmark_seed(
    session: AsyncSession,
    data_dir: Path | None = None,
    *,
    commit: bool = True,
) -> RAGSystemsSeedResult:
    """Create dataset, query cases, three ingested corpus variants, and three pipeline configs."""
    data_dir = data_dir or default_rag_systems_dataset_dir()
    manifest = load_manifest(data_dir)
    combined = build_combined_corpus_text(data_dir, manifest)
    queries = load_queries(data_dir)
    n_expected = len(queries)
    model = settings.embedding_model_name

    ds = await _get_dataset_by_name(session, RAG_SYSTEMS_DATASET_NAME)
    if ds is None:
        ds = await tp.create_dataset(
            session,
            name=RAG_SYSTEMS_DATASET_NAME,
            description=(
                "RAG systems & retrieval engineering benchmark (8 docs, 8 queries). "
                "See backend/benchmark_data/rag_systems_retrieval_engineering_v1/."
            ),
            metadata_json=dict(RAG_SYSTEMS_SEED_META),
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
                query_text=str(row["query_text"]),
                expected_answer=str(row["expected_answer"]),
                metadata_json={**RAG_SYSTEMS_SEED_META, **({"source_id": row["id"]} if "id" in row else {})},
            )
        await session.flush()
        qcs = (
            await session.execute(
                select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
            )
        ).scalars().all()
    elif len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {RAG_SYSTEMS_DATASET_NAME!r} exists with {len(qcs)} query cases; "
            f"expected 0 or {n_expected}. Rename/remove the dataset to re-seed."
        )

    query_case_ids = tuple(qc.id for qc in qcs[:n_expected])

    run_plan_parts: list[tuple[str, int, int]] = []
    for variant_name, chunk_size, chunk_overlap, top_k in RAG_SYSTEMS_VARIANTS:
        doc = await _ensure_variant_document(
            session,
            combined_text=combined,
            variant_name=variant_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            commit=False,
        )
        pc = await _get_pipeline_by_name(session, variant_name)
        meta_base = {
            **RAG_SYSTEMS_SEED_META,
            "variant": variant_name,
            "scoped_document_id": doc.id,
            "ingest_chunk_size": chunk_size,
            "ingest_chunk_overlap": chunk_overlap,
        }
        if pc is None:
            pc = await tp.create_pipeline_config(
                session,
                name=variant_name,
                embedding_model=model,
                chunk_strategy="fixed",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k=top_k,
                metadata_json=meta_base,
            )
        else:
            # Keep row aligned with scoped corpus for reruns / repaired DBs.
            pc.chunk_size = chunk_size
            pc.chunk_overlap = chunk_overlap
            pc.top_k = top_k
            merged = dict(pc.metadata_json or {})
            merged.update(meta_base)
            pc.metadata_json = merged
            await session.flush()

        run_plan_parts.append((variant_name, pc.id, doc.id))

    if commit:
        await session.commit()

    return RAGSystemsSeedResult(
        dataset_id=ds.id,
        query_case_ids=query_case_ids,
        run_plan=tuple(run_plan_parts),
    )


async def get_rag_systems_benchmark_ready(
    session: AsyncSession,
    data_dir: Path | None = None,
) -> RAGSystemsSeedResult:
    """Return IDs and run plan; raise if registry or documents are incomplete."""
    data_dir = data_dir or default_rag_systems_dataset_dir()
    queries = load_queries(data_dir)
    n_expected = len(queries)

    ds = await _get_dataset_by_name(session, RAG_SYSTEMS_DATASET_NAME)
    if ds is None:
        raise ValueError(
            f"Dataset {RAG_SYSTEMS_DATASET_NAME!r} not found. "
            "Run: python scripts/seed_rag_systems_benchmark.py"
        )
    qcs = (
        await session.execute(
            select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id)
        )
    ).scalars().all()
    if len(qcs) != n_expected:
        raise ValueError(
            f"Dataset {RAG_SYSTEMS_DATASET_NAME!r} has {len(qcs)} query cases; expected {n_expected}."
        )

    run_plan_parts: list[tuple[str, int, int]] = []
    for variant_name, _cs, _co, _tk in RAG_SYSTEMS_VARIANTS:
        pc = await _get_pipeline_by_name(session, variant_name)
        if pc is None:
            raise ValueError(
                f"Pipeline {variant_name!r} missing. Run: python scripts/seed_rag_systems_benchmark.py"
            )
        meta = pc.metadata_json or {}
        doc_id = meta.get("scoped_document_id")
        if doc_id is None:
            raise ValueError(
                f"Pipeline {variant_name!r} missing metadata_json.scoped_document_id. Re-run seed script."
            )
        run_plan_parts.append((variant_name, pc.id, int(doc_id)))

    return RAGSystemsSeedResult(
        dataset_id=ds.id,
        query_case_ids=tuple(qc.id for qc in qcs),
        run_plan=tuple(run_plan_parts),
    )
