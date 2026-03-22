"""RAG answer generation: OpenAI (default) or Anthropic (optional ``LLM_PROVIDER=anthropic``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings

RAG_SYSTEM_PROMPT = """You are a precise assistant for a retrieval-augmented system.
Answer the user's question using ONLY the information in the provided context blocks.
If the context is insufficient, say so briefly. Do not invent facts.
Keep answers concise unless the question requires detail."""


def build_rag_user_message(query: str, chunk_bodies: list[str]) -> str:
    lines = ["### Context\n"]
    for i, body in enumerate(chunk_bodies, 1):
        lines.append(f"[{i}] {body.strip()}\n")
    lines.append("### Question\n")
    lines.append(query.strip())
    lines.append("\n### Answer\n")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class GenerationModelResult:
    answer_text: str
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    raw_stop_reason: str | None
    metadata_json: dict[str, Any]


def _provider_name() -> str:
    return (settings.llm_provider or "openai").strip().lower()


async def _generate_rag_answer_openai(
    *,
    query: str,
    chunk_bodies: list[str],
    model: str | None,
) -> GenerationModelResult:
    from app.services.openai_client import get_async_openai

    client = get_async_openai()
    model_id = model or settings.generation_model_name
    user_content = build_rag_user_message(query, chunk_bodies)

    response = await client.responses.create(
        model=model_id,
        input=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        max_output_tokens=2048,
    )

    answer_text = getattr(response, "output_text", "").strip() or "(empty model response)"

    usage = getattr(response, "usage", None)
    inp = getattr(usage, "input_tokens", None) if usage else None
    out = getattr(usage, "output_tokens", None) if usage else None

    return GenerationModelResult(
        answer_text=answer_text,
        model_id=model_id,
        input_tokens=inp,
        output_tokens=out,
        raw_stop_reason=getattr(response, "status", None),
        metadata_json={
            "provider": "openai",
            "prompt_version": "rag_context_blocks_v1",
            "response_status": getattr(response, "status", None),
            "response_id": getattr(response, "id", None),
        },
    )


async def _generate_rag_answer_anthropic(
    *,
    query: str,
    chunk_bodies: list[str],
    model: str | None,
) -> GenerationModelResult:
    from app.services.anthropic_client import get_async_anthropic

    client = get_async_anthropic()
    model_id = model or settings.generation_model_name
    user_content = build_rag_user_message(query, chunk_bodies)

    msg = await client.messages.create(
        model=model_id,
        max_tokens=2048,
        system=RAG_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text_parts: list[str] = []
    for block in msg.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    answer_text = "\n".join(text_parts).strip() or "(empty model response)"
    inp = getattr(msg.usage, "input_tokens", None)
    out = getattr(msg.usage, "output_tokens", None)
    stop = None
    if getattr(msg, "stop_reason", None) is not None:
        stop = str(msg.stop_reason)

    return GenerationModelResult(
        answer_text=answer_text,
        model_id=model_id,
        input_tokens=inp,
        output_tokens=out,
        raw_stop_reason=stop,
        metadata_json={
            "provider": "anthropic",
            "prompt_version": "rag_context_blocks_v1",
            "stop_reason": stop,
        },
    )


async def generate_rag_answer(
    *,
    query: str,
    chunk_bodies: list[str],
    model: str | None = None,
) -> GenerationModelResult:
    """Call the configured provider; return answer text and usage when present."""
    if not chunk_bodies:
        raise ValueError("chunk_bodies must be non-empty for RAG generation")

    if _provider_name() == "anthropic":
        return await _generate_rag_answer_anthropic(
            query=query, chunk_bodies=chunk_bodies, model=model
        )
    return await _generate_rag_answer_openai(query=query, chunk_bodies=chunk_bodies, model=model)
