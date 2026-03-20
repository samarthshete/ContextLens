"""API response for a single benchmark / RAG run (inspection + demos)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class QueryCaseBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    query_text: str
    expected_answer: str | None = None


class PipelineConfigBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    embedding_model: str
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    top_k: int


class RetrievalHitOut(BaseModel):
    rank: int
    score: float
    chunk_id: int
    document_id: int
    content: str
    chunk_index: int


class GenerationOut(BaseModel):
    answer_text: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata_json: dict[str, Any] | None = None


class EvaluationOut(BaseModel):
    faithfulness: float | None = None
    completeness: float | None = None
    retrieval_relevance: float | None = None
    context_coverage: float | None = None
    groundedness: float | None = None
    failure_type: str | None = None
    used_llm_judge: bool
    cost_usd: Decimal | None = None
    metadata_json: dict[str, Any] | None = None

    @field_serializer("cost_usd", when_used="json")
    def _cost_json(self, v: Decimal | None) -> float | None:
        if v is None:
            return None
        return float(v)


class RunDetailResponse(BaseModel):
    run_id: int
    status: str
    created_at: datetime
    retrieval_latency_ms: int | None = None
    generation_latency_ms: int | None = None
    evaluation_latency_ms: int | None = None
    total_latency_ms: int | None = None
    evaluator_type: str
    query_case: QueryCaseBrief
    pipeline_config: PipelineConfigBrief
    retrieval_hits: list[RetrievalHitOut]
    generation: GenerationOut | None = None
    evaluation: EvaluationOut | None = None
