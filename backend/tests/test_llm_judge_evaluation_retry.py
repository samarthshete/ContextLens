"""Judge API wrapper: one retry when first structural parse fails."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_judge_evaluation import JUDGE_PROMPT_VERSION, evaluate_with_llm_judge

_VALID = (
    '{"faithfulness":0.5,"completeness":0.5,"groundedness":0.5,'
    '"retrieval_relevance":0.5,"context_coverage":0.5,"failure_type":"NO_FAILURE"}'
)


def _fake_message(text: str, inp: int = 5, out: int = 10) -> MagicMock:
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    msg.usage = MagicMock(input_tokens=inp, output_tokens=out)
    return msg


@pytest.mark.asyncio
async def test_judge_first_ok_no_retry(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_fake_message(_VALID, 10, 20))
    monkeypatch.setattr("app.services.llm_judge_evaluation.get_async_anthropic", lambda: client)

    r = await evaluate_with_llm_judge(
        query="q",
        context_chunks=["ctx"],
        generated_answer="ans",
        reference_answer=None,
    )

    assert client.messages.create.call_count == 1
    assert r.metadata_json["judge_parse_ok"] is True
    assert r.metadata_json["judge_prompt_version"] == JUDGE_PROMPT_VERSION
    assert r.metadata_json["judge_initial_parse_ok"] is True
    assert r.metadata_json["judge_retry_attempted"] is False
    assert r.metadata_json["judge_retry_succeeded"] is False
    assert r.judge_input_tokens == 10
    assert r.judge_output_tokens == 20


@pytest.mark.asyncio
async def test_judge_first_bad_second_ok_retry_succeeds(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=[
            _fake_message("not json {{{", 10, 20),
            _fake_message(_VALID, 8, 12),
        ]
    )
    monkeypatch.setattr("app.services.llm_judge_evaluation.get_async_anthropic", lambda: client)

    r = await evaluate_with_llm_judge(
        query="q",
        context_chunks=["ctx"],
        generated_answer="ans",
    )

    assert client.messages.create.call_count == 2
    assert r.metadata_json["judge_initial_parse_ok"] is False
    assert r.metadata_json["judge_retry_attempted"] is True
    assert r.metadata_json["judge_retry_succeeded"] is True
    assert r.metadata_json["judge_parse_ok"] is True
    assert r.faithfulness == pytest.approx(0.5)
    assert r.judge_input_tokens == 18
    assert r.judge_output_tokens == 32


@pytest.mark.asyncio
async def test_judge_both_attempts_bad_retry_fails(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=[
            _fake_message("{{{", 1, 2),
            _fake_message("also bad", 3, 4),
        ]
    )
    monkeypatch.setattr("app.services.llm_judge_evaluation.get_async_anthropic", lambda: client)

    r = await evaluate_with_llm_judge(query="q", context_chunks=["c"], generated_answer="a")

    assert client.messages.create.call_count == 2
    assert r.metadata_json["judge_retry_attempted"] is True
    assert r.metadata_json["judge_retry_succeeded"] is False
    assert r.metadata_json["judge_parse_ok"] is False
    assert r.judge_input_tokens == 4
    assert r.judge_output_tokens == 6


@pytest.mark.asyncio
async def test_judge_transport_error_no_second_call(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()

    async def boom(**kwargs):
        raise RuntimeError("simulated transport failure")

    client.messages.create = AsyncMock(side_effect=boom)
    monkeypatch.setattr("app.services.llm_judge_evaluation.get_async_anthropic", lambda: client)

    with pytest.raises(RuntimeError, match="simulated transport"):
        await evaluate_with_llm_judge(query="q", context_chunks=["c"], generated_answer="a")

    assert client.messages.create.call_count == 1
