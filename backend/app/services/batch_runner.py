"""Large-scale batch benchmark execution: same query set × configs × repetitions.

Intended for scripts and internal tooling (not a public HTTP contract). Each run stores
``runs.metadata_json`` with ``batch_id``, optional ``experiment_name`` / ``config_group_tag``,
and indices for traceability.

**Heuristic** mode runs the inline retrieval + minimal-eval pipeline.
**LLM** mode runs the full RAG pipeline in-process (same code path as the RQ worker).

Optional :class:`BenchmarkRealismProfile` applies **only** to heuristic batch cells (retrieval
perturbation + score noise + low-score failure classification). Full LLM runs use provider
outputs without synthetic corruption.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import PipelineConfig, QueryCase, Run
from app.services import trace_persistence as tp
from app.services.benchmark_realism import (
    BenchmarkRealismProfile,
    apply_heuristic_score_noise,
    classify_low_quality_failure,
    perturb_search_chunk_hits,
)
from app.services.evaluation_persistence import persist_evaluation_and_complete_run
from app.services.minimal_retrieval_evaluation import compute_minimal_retrieval_evaluation
from app.services.retrieval import search_chunks
from app.services.run_create import (
    FullModeNotConfiguredError,
    run_full_benchmark_pipeline,
    validate_run_create_prerequisites,
)
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RETRIEVAL_COMPLETED,
    STATUS_RUNNING,
)

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class BatchBenchmarkResult:
    batch_id: str
    total_runs: int
    failures: int
    successes: int
    success_rate: float


def _stable_rng(base: int | None, *parts: int) -> random.Random:
    """Deterministic RNG from optional global seed + integer parts."""
    s = 0x9E3779B9
    if base is not None:
        s ^= (base * 1_000_003) & 0xFFFFFFFF
    for p in parts:
        s = (s * 1_000_003) ^ (p * 0x85EBCA6B)
        s &= 0xFFFFFFFF
    return random.Random(s)


async def _load_ordered_query_cases(session: AsyncSession, dataset_id: int) -> list[QueryCase]:
    stmt = select(QueryCase).where(QueryCase.dataset_id == dataset_id).order_by(QueryCase.id)
    return list((await session.execute(stmt)).scalars().all())


async def _mark_run_failed(session: AsyncSession, run_id: int) -> None:
    run = await session.get(Run, run_id)
    if run is None:
        return
    if run.status in (STATUS_COMPLETED, STATUS_FAILED):
        return
    run.status = STATUS_FAILED
    await session.flush()


async def _execute_heuristic_cell(
    session: AsyncSession,
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None,
    run_metadata: dict,
    realism: BenchmarkRealismProfile | None,
    rng: random.Random,
    commit: bool,
) -> None:
    await validate_run_create_prerequisites(
        session,
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        document_id=document_id,
        eval_mode="heuristic",
    )

    qc = await session.get(QueryCase, query_case_id)
    pc = await session.get(PipelineConfig, pipeline_config_id)
    if qc is None or pc is None:
        raise ValueError("query case or pipeline config missing")

    meta_base = dict(run_metadata)
    if realism is not None:
        meta_base = {**meta_base, **realism.extra_metadata, "benchmark_realism": True}

    run = await tp.create_run(
        session,
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        status=STATUS_RUNNING,
        metadata_json=meta_base,
    )
    await session.flush()
    run_id = run.id
    if commit:
        await session.commit()
        await session.refresh(run)

    t0 = time.perf_counter()
    hits = await search_chunks(
        qc.query_text,
        session,
        top_k=pc.top_k,
        document_id=document_id,
    )
    if realism is not None:
        hits = perturb_search_chunk_hits(hits, rng, profile=realism)

    rows = [(h["chunk_id"], i + 1, float(h["score"])) for i, h in enumerate(hits)]
    await tp.store_retrieval_results(session, run_id=run_id, chunk_scores=rows)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    run = await session.get(Run, run_id)
    if run is None:
        raise RuntimeError("run disappeared")
    run.retrieval_latency_ms = elapsed_ms
    run.status = STATUS_RETRIEVAL_COMPLETED
    await session.flush()

    t_eval0 = time.perf_counter()
    ev = await compute_minimal_retrieval_evaluation(session, run_id=run_id)
    faithfulness = ev.faithfulness
    completeness = ev.completeness
    retrieval_relevance = ev.retrieval_relevance
    context_coverage = ev.context_coverage
    failure_type = ev.failure_type
    meta = dict(ev.metadata_json or {})

    if realism is not None:
        rr, cc, comp, ff = apply_heuristic_score_noise(
            retrieval_relevance,
            context_coverage,
            completeness,
            faithfulness,
            rng,
            profile=realism,
        )
        retrieval_relevance, context_coverage, completeness, faithfulness = rr, cc, comp, ff
        failure_type = classify_low_quality_failure(
            retrieval_relevance=retrieval_relevance,
            context_coverage=context_coverage,
            completeness=completeness,
            current_failure=failure_type or "",
            profile=realism,
        )
        meta["benchmark_realism"] = True

    eval_ms = max(0, int((time.perf_counter() - t_eval0) * 1000))
    retrieval_ms = run.retrieval_latency_ms or 0
    total_ms = retrieval_ms + eval_ms

    await persist_evaluation_and_complete_run(
        session,
        run_id=run_id,
        evaluation_latency_ms=eval_ms,
        total_latency_ms=total_ms,
        faithfulness=faithfulness,
        completeness=completeness,
        retrieval_relevance=retrieval_relevance,
        context_coverage=context_coverage,
        failure_type=failure_type,
        used_llm_judge=ev.used_llm_judge,
        cost_usd=None,
        metadata_json=meta,
        commit=commit,
    )


async def _execute_llm_cell(
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None,
    run_metadata: dict,
) -> bool:
    """Returns True if terminal status is ``completed``."""
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
            metadata_json=run_metadata,
        )
        await session.commit()
        rid = run.id

    await run_full_benchmark_pipeline(rid, document_id)

    async with async_session_maker() as session:
        r = await session.get(Run, rid)
        return r is not None and r.status == STATUS_COMPLETED


async def run_batch_benchmark(
    session: AsyncSession,
    dataset_ids: list[int],
    config_ids: list[int],
    queries_per_dataset: int,
    runs_per_query: int,
    evaluator_type: str,
    *,
    random_seed: int | None = None,
    document_id: int | None = None,
    experiment_name: str | None = None,
    config_group_tag: str | None = None,
    realism_profile: BenchmarkRealismProfile | None = None,
    commit: bool = True,
) -> BatchBenchmarkResult:
    """Execute ``datasets × (up to N queries) × configs × runs_per_query`` benchmark runs.

    Query cases are chosen **per dataset** in stable ``id`` order, optionally shuffled with
    ``random_seed`` (same ordering used for **every** pipeline config so comparisons align).

    ``evaluator_type``:
    - ``"heuristic"`` — synchronous retrieval + minimal evaluation (uses *session*).
    - ``"llm"`` — full RAG in-process via ``run_full_benchmark_pipeline`` (requires provider keys).

    Raises ``FullModeNotConfiguredError`` on the first LLM cell if keys are missing.
    """
    et = evaluator_type.strip().lower()
    if et not in ("heuristic", "llm"):
        raise ValueError("evaluator_type must be 'heuristic' or 'llm'")

    if queries_per_dataset < 1 or runs_per_query < 1:
        raise ValueError("queries_per_dataset and runs_per_query must be >= 1")
    if not dataset_ids or not config_ids:
        raise ValueError("dataset_ids and config_ids must be non-empty")

    batch_id = str(uuid.uuid4())
    successes = 0
    failures = 0
    total = 0

    for ds_id in dataset_ids:
        qcs = await _load_ordered_query_cases(session, ds_id)
        if random_seed is not None:
            r0 = random.Random((random_seed * 1_000_003) ^ (ds_id * 0x9E3779B9))
            qcs = qcs.copy()
            r0.shuffle(qcs)
        qcs = qcs[:queries_per_dataset]
        if len(qcs) < queries_per_dataset:
            logger.warning(
                "batch %s: dataset_id=%s only has %s query cases (requested %s)",
                batch_id,
                ds_id,
                len(qcs),
                queries_per_dataset,
            )

        for qc in qcs:
            for cfg_id in config_ids:
                for rep in range(runs_per_query):
                    total += 1
                    rng = _stable_rng(random_seed, ds_id, qc.id, cfg_id, rep)
                    meta = {
                        "batch_id": batch_id,
                        "batch_dataset_id": ds_id,
                        "batch_query_case_id": qc.id,
                        "batch_pipeline_config_id": cfg_id,
                        "batch_repetition": rep,
                        "batch_evaluator_type": et,
                    }
                    if experiment_name:
                        meta["experiment_name"] = experiment_name
                    if config_group_tag:
                        meta["config_group_tag"] = config_group_tag

                    try:
                        if et == "heuristic":
                            await _execute_heuristic_cell(
                                session,
                                query_case_id=qc.id,
                                pipeline_config_id=cfg_id,
                                document_id=document_id,
                                run_metadata=meta,
                                realism=realism_profile,
                                rng=rng,
                                commit=commit,
                            )
                            successes += 1
                        else:
                            ok = await _execute_llm_cell(
                                query_case_id=qc.id,
                                pipeline_config_id=cfg_id,
                                document_id=document_id,
                                run_metadata=meta,
                            )
                            if ok:
                                successes += 1
                            else:
                                failures += 1
                    except FullModeNotConfiguredError:
                        raise
                    except Exception:
                        logger.exception(
                            "batch %s: failed cell ds=%s qc=%s cfg=%s rep=%s",
                            batch_id,
                            ds_id,
                            qc.id,
                            cfg_id,
                            rep,
                        )
                        failures += 1
                        if et == "heuristic":
                            try:
                                async with async_session_maker() as s2:
                                    stmt = (
                                        select(Run.id)
                                        .where(Run.query_case_id == qc.id)
                                        .where(Run.pipeline_config_id == cfg_id)
                                        .order_by(Run.id.desc())
                                        .limit(1)
                                    )
                                    last_id = (await s2.execute(stmt)).scalar_one_or_none()
                                    if last_id is not None:
                                        await _mark_run_failed(s2, last_id)
                                        await s2.commit()
                            except Exception:
                                logger.exception("batch %s: failed to mark run failed", batch_id)

    rate = (successes / total) if total else 0.0
    return BatchBenchmarkResult(
        batch_id=batch_id,
        total_runs=total,
        failures=failures,
        successes=successes,
        success_rate=rate,
    )
