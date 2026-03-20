"""RAG answer generation with Claude (context + query → answer)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.services.anthropic_client import get_async_anthropic


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


async def generate_rag_answer(
    *,
    query: str,
    chunk_bodies: list[str],
    model: str | None = None,
) -> GenerationModelResult:
    """Call Claude Messages API; return answer text and usage when present."""
    if not chunk_bodies:
        raise ValueError("chunk_bodies must be non-empty for RAG generation")

    client = get_async_anthropic()
    model_id = model or settings.generation_model_name
    user_content = build_rag_user_message(query, chunk_bodies)

    msg = await client.messages.create(
        model=model_id,
        max_tokens=2048,
        system=RAG_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    parts: list[str] = []
    for block in msg.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    answer_text = "\n".join(parts).strip() or "(empty model response)"

    inp = getattr(msg.usage, "input_tokens", None)
    out = getattr(msg.usage, "output_tokens", None)

    return GenerationModelResult(
        answer_text=answer_text,
        model_id=model_id,
        input_tokens=inp,
        output_tokens=out,
        raw_stop_reason=getattr(msg, "stop_reason", None),
        metadata_json={
            "prompt_version": "rag_context_blocks_v1",
            "stop_reason": getattr(msg, "stop_reason", None),
        },
    )
