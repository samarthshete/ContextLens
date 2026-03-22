"""Create a run and execute the benchmark pipeline (heuristic inline; full via RQ worker)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import anthropic
from openai import APIError as OpenAIAPIError
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from app.config import settings
from app.database import async_session_maker
from app.models import Document, PipelineConfig, QueryCase, Run
from app.services.llm_provider_keys import require_llm_api_key_for_full_mode
from app.services.benchmark_run import (
    execute_retrieval_benchmark_run,
    execute_retrieval_for_existing_run,
)
from app.services.evaluation_persistence import persist_evaluation_and_complete_run
from app.services.full_rag_evaluation import execute_llm_judge_and_complete_run
from app.services.generation_phase import execute_generation_for_run
from app.services.minimal_retrieval_evaluation import compute_minimal_retrieval_evaluation
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_GENERATION_COMPLETED,
    STATUS_RETRIEVAL_COMPLETED,
    STATUS_RUNNING,
)

logger = logging.getLogger(__name__)


class QueryCaseNotFoundError(LookupError):
    """Raised when ``query_case_id`` does not exist."""


class PipelineConfigNotFoundError(LookupError):
    """Raised when ``pipeline_config_id`` does not exist."""


class FullModeNotConfiguredError(RuntimeError):
    """Raised when ``eval_mode=full`` but the active LLM provider key is missing."""


class DocumentNotFoundError(LookupError):
    """Raised when ``document_id`` is set but no ``documents`` row exists."""


async def validate_run_create_prerequisites(
    session: AsyncSession,
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None,
    eval_mode: Literal["heuristic", "full"],
) -> None:
    """Validate FKs and full-mode API key before creating a run row."""
    qc = await session.get(QueryCase, query_case_id)
    if qc is None:
        raise QueryCaseNotFoundError(query_case_id)
    pc = await session.get(PipelineConfig, pipeline_config_id)
    if pc is None:
        raise PipelineConfigNotFoundError(pipeline_config_id)

    if document_id is not None:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise DocumentNotFoundError(document_id)

    if eval_mode == "full":
        try:
            require_llm_api_key_for_full_mode()
        except ValueError as e:
            raise FullModeNotConfiguredError(str(e)) from e


async def _mark_run_failed_safe(run_id: int) -> None:
    """Best-effort ``failed`` on a fresh session (worker / RQ ``on_failure`` path)."""
    async with async_session_maker() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        if run.status == STATUS_COMPLETED:
            return
        run.status = STATUS_FAILED
        await session.commit()


_sync_mark_failed_engine = None


def _sync_database_url_for_psycopg() -> str:
    """``postgresql+asyncpg://`` → sync driver for RQ callback (no event loop)."""
    u = settings.database_url
    if "+asyncpg" in u:
        return u.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if "+psycopg" in u:
        return u
    if u.startswith("postgresql://"):
        return u
    raise ValueError(f"Unsupported database_url for sync worker callback: {u!r}")


def mark_run_failed_sync(run_id: int) -> None:
    """Persist ``failed`` from RQ ``on_failure`` using a **sync** DB session.

    RQ callbacks may run while an asyncio loop is active elsewhere, and asyncpg pools
    are loop-bound — ``asyncio.run`` here is unsafe. A short-lived psycopg connection
    avoids sharing the app's async engine.
    """
    global _sync_mark_failed_engine
    try:
        if _sync_mark_failed_engine is None:
            _sync_mark_failed_engine = create_engine(
                _sync_database_url_for_psycopg(),
                pool_pre_ping=True,
            )
        SyncSession = sync_sessionmaker(
            _sync_mark_failed_engine,
            expire_on_commit=False,
            autoflush=False,
        )
        with SyncSession() as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            if run.status == STATUS_COMPLETED:
                return
            run.status = STATUS_FAILED
            session.commit()
    except Exception:
        logger.exception("mark_run_failed_sync: failed run_id=%s", run_id)


async def run_full_benchmark_pipeline(run_id: int, document_id: int | None) -> None:
    """Full RAG after HTTP 202: resume-aware, idempotent for terminal states.

    - ``completed`` / ``failed``: no-op (safe if job is duplicated or re-queued).
    - ``running``: run retrieval, then generation, then judge (each phase commits).
    - Mid-pipeline states resume: ``retrieval_completed`` skips retrieval; ``generation_completed`` skips to judge.

    **Retries:** Provider HTTP errors (``anthropic.APIError``, ``openai.APIError``) and most
    ``Exception`` types are re-raised for RQ retry.
    ``ValueError`` / ``TypeError`` (precondition / data) mark the run failed and do not retry.
    """
    async with async_session_maker() as session:
        run = await session.get(Run, run_id)
        if run is None:
            logger.warning("full run pipeline: run id=%s not found", run_id)
            return
        if run.status in (STATUS_COMPLETED, STATUS_FAILED):
            logger.info(
                "full run pipeline: run id=%s already terminal (%s), skipping",
                run_id,
                run.status,
            )
            return

    try:
        async with async_session_maker() as session:
            run = await session.get(Run, run_id)
            if run and run.status == STATUS_RUNNING:
                await execute_retrieval_for_existing_run(
                    session,
                    run_id=run_id,
                    document_id=document_id,
                    commit=True,
                )

        async with async_session_maker() as session:
            run = await session.get(Run, run_id)
            if run and run.status == STATUS_RETRIEVAL_COMPLETED:
                await execute_generation_for_run(session, run_id=run_id, commit=True)

        async with async_session_maker() as session:
            run = await session.get(Run, run_id)
            if run and run.status == STATUS_GENERATION_COMPLETED:
                await execute_llm_judge_and_complete_run(session, run_id=run_id, commit=True)

    except (anthropic.APIError, OpenAIAPIError):
        logger.exception("LLM provider API error (RQ may retry) run_id=%s", run_id)
        raise
    except (ValueError, TypeError):
        logger.exception("Non-retryable error run_id=%s", run_id)
        await _mark_run_failed_safe(run_id)
    except Exception:
        logger.exception("Retryable error run_id=%s", run_id)
        raise


async def create_and_execute_run_from_ids(
    session: AsyncSession,
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None = None,
) -> Run:
    """Heuristic-only inline path: retrieval (with mid-flight commits) + minimal eval + completed.

    For ``eval_mode=full``, use ``validate_run_create_prerequisites`` + ``create_run`` + ``enqueue_full_benchmark_run``.
    """
    await validate_run_create_prerequisites(
        session,
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        document_id=document_id,
        eval_mode="heuristic",
    )

    run = await execute_retrieval_benchmark_run(
        session,
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        document_id=document_id,
        commit=True,
    )
    rid = run.id
    retrieval_ms = run.retrieval_latency_ms or 0

    t0 = time.perf_counter()
    ev = await compute_minimal_retrieval_evaluation(session, run_id=rid)
    eval_ms = max(0, int((time.perf_counter() - t0) * 1000))
    total_ms = retrieval_ms + eval_ms
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
    await session.refresh(run)
    return run
