"""52+ query scale benchmark: deterministic corpus + query cases (no fabricated run metrics)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, Document, PipelineConfig, QueryCase
from app.config import settings
from app.services import trace_persistence as tp
from app.services.chunker import ChunkStrategy
from app.services.text_document_ingest import ingest_plain_text

SCALE_DATASET_NAME = "scale_rag_engineering_v1"
SCALE_DOC_TITLE = "ContextLens scale RAG corpus v1"
SCALE_SEED_META = {"seed": "scale_rag_v1", "dataset_slug": "scale-rag-v1"}

SCALE_PIPELINE_SPECS: tuple[dict[str, int | str | dict], ...] = (
    {
        "name": "scale_baseline_topk4",
        "top_k": 4,
        "chunk_size": 320,
        "chunk_overlap": 48,
        "metadata_json": {**SCALE_SEED_META, "role": "baseline"},
    },
    {
        "name": "scale_broader_topk8",
        "top_k": 8,
        "chunk_size": 384,
        "chunk_overlap": 64,
        "metadata_json": {**SCALE_SEED_META, "role": "broader_context"},
    },
)


def scale_topic_labels() -> tuple[str, ...]:
    """52 short topic labels; paired with deterministic answers in ``build_scale_corpus_markdown``."""
    bases = (
        "Redis persistence",
        "Postgres WAL",
        "Kubernetes probes",
        "Kafka partitions",
        "Nginx buffering",
        "Docker layers",
        "gRPC deadlines",
        "OpenTelemetry spans",
        "SQLite locking",
        "MongoDB oplog",
        "Elasticsearch shards",
        "RabbitMQ acks",
        "Cassandra compaction",
        "MySQL binlog",
        "HAProxy timeouts",
        "Terraform state",
        "Prometheus histograms",
        "Grafana alerts",
        "JWT rotation",
        "OAuth2 PKCE",
        "S3 multipart upload",
        "CloudFront caching",
        "Lambda cold start",
        "Step Functions retries",
        "VPC flow logs",
        "IAM policy evaluation",
        "CDN cache keys",
        "WebSocket backpressure",
        "HTTP/2 multiplexing",
        "TLS session resumption",
        "DNS TTL",
        "BGP path selection",
        "IPv6 neighbor discovery",
        "Linux cgroups",
        "systemd units",
        "eBPF maps",
        "iptables conntrack",
        "ZFS snapshots",
        "LUKS encryption",
        "RAID parity",
        "NVMe queues",
        "CPU branch prediction",
        "L3 cache coherency",
        "Page table walks",
        "Memory ballooning",
        "NUMA locality",
        "GPU memory barriers",
        "SIMD lanes",
        "Rust ownership",
        "Go garbage collection",
        "Python GIL",
        "Node.js event loop",
    )
    # --- benchmark contract: exactly 52 unique, non-blank topics in stable order ---
    _EXPECTED = 52
    if len(bases) != _EXPECTED:
        raise RuntimeError(
            f"scale topics must stay at {_EXPECTED} for benchmark contract, "
            f"but found {len(bases)}. Check for accidental additions or removals."
        )
    seen: set[str] = set()
    for t in bases:
        if not t or not t.strip():
            raise RuntimeError(f"Blank topic label at index {list(bases).index(t)}")
        if t in seen:
            raise RuntimeError(f"Duplicate topic label: {t!r}")
        seen.add(t)
    return bases


def canonical_answer_for_index(i: int, topic: str) -> str:
    """1-based index i matching ``## {i}.`` sections in the corpus."""
    return (
        f"Canonical answer line {i}: {topic} is documented in ContextLens scale corpus section {i}."
    )


def build_scale_corpus_markdown() -> str:
    lines: list[str] = ["# ContextLens scale RAG corpus v1", ""]
    for i, topic in enumerate(scale_topic_labels(), start=1):
        ans = canonical_answer_for_index(i, topic)
        lines.append(f"## {i}. {topic}")
        lines.append(ans)
        lines.append("")
    return "\n".join(lines)


def build_scale_query_dicts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for i, topic in enumerate(scale_topic_labels(), start=1):
        rows.append(
            {
                "query_text": f"What is the canonical answer for scale section {i} ({topic})?",
                "expected_answer": canonical_answer_for_index(i, topic),
            }
        )
    return rows


@dataclass(frozen=True, slots=True)
class ScaleBenchmarkSeedResult:
    dataset_id: int
    query_case_ids: tuple[int, ...]
    pipeline_config_ids: tuple[int, ...]
    document_id: int


async def ensure_scale_benchmark_dataset(session: AsyncSession) -> tuple[int, tuple[int, ...], tuple[int, ...]]:
    """Idempotent registry: one dataset, 52 query cases, two pipeline configs."""
    model = settings.embedding_model_name
    stmt = select(Dataset).where(Dataset.name == SCALE_DATASET_NAME).limit(1)
    ds = (await session.execute(stmt)).scalar_one_or_none()
    if ds is None:
        ds = await tp.create_dataset(
            session,
            name=SCALE_DATASET_NAME,
            description="52-query scale benchmark for traced runs + dashboard scale metrics.",
            metadata_json=SCALE_SEED_META,
        )
        await session.flush()

    existing_qc = (
        await session.execute(select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id))
    ).scalars().all()
    target_rows = build_scale_query_dicts()
    n_exp = len(target_rows)
    if len(existing_qc) == 0:
        for j, row in enumerate(target_rows):
            await tp.create_query_case(
                session,
                dataset_id=ds.id,
                query_text=row["query_text"],
                expected_answer=row["expected_answer"],
                metadata_json={"scale_index": j + 1},
            )
        await session.flush()
    elif len(existing_qc) != n_exp:
        raise ValueError(
            f"Dataset {SCALE_DATASET_NAME!r} has {len(existing_qc)} query cases; expected 0 or {n_exp}."
        )

    qc_ids = tuple(
        r.id
        for r in (
            await session.execute(select(QueryCase).where(QueryCase.dataset_id == ds.id).order_by(QueryCase.id))
        ).scalars().all()
    )

    pc_ids: list[int] = []
    for spec in SCALE_PIPELINE_SPECS:
        name = str(spec["name"])
        p_stmt = select(PipelineConfig).where(PipelineConfig.name == name).limit(1)
        pc = (await session.execute(p_stmt)).scalar_one_or_none()
        if pc is None:
            pc = await tp.create_pipeline_config(
                session,
                name=name,
                embedding_model=model,
                chunk_strategy="fixed",
                chunk_size=int(spec["chunk_size"]),
                chunk_overlap=int(spec["chunk_overlap"]),
                top_k=int(spec["top_k"]),
                metadata_json=dict(spec["metadata_json"]),
            )
            await session.flush()
        pc_ids.append(pc.id)

    await session.commit()

    return ds.id, qc_ids, tuple(pc_ids)


async def ingest_scale_corpus_document(session: AsyncSession, *, commit: bool = True) -> Document:
    """Single processed document covering all 52 canonical answers (chunked + embedded)."""
    text = build_scale_corpus_markdown()
    r = await session.execute(
        select(Document).where(
            Document.title == SCALE_DOC_TITLE,
            Document.status == "processed",
        )
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing
    return await ingest_plain_text(
        session,
        title=SCALE_DOC_TITLE,
        text=text,
        chunk_strategy=ChunkStrategy.FIXED,
        chunk_size=320,
        chunk_overlap=48,
        metadata_json={**SCALE_SEED_META, "artifact": "scale_corpus_v1"},
        commit=commit,
    )


async def ensure_scale_benchmark_ready(session: AsyncSession) -> ScaleBenchmarkSeedResult:
    """Dataset + queries + configs + one ingested corpus document."""
    dataset_id, qc_ids, pc_ids = await ensure_scale_benchmark_dataset(session)
    doc = await ingest_scale_corpus_document(session)
    return ScaleBenchmarkSeedResult(
        dataset_id=dataset_id,
        query_case_ids=qc_ids,
        pipeline_config_ids=pc_ids,
        document_id=doc.id,
    )
