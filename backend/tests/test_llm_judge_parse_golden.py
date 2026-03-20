"""Golden-style cases for judge JSON extract + parse (fixtures + payloads)."""

from pathlib import Path

import pytest

from app.domain.failure_taxonomy import FailureType
from app.services.llm_judge_parse import extract_judge_json_object, parse_judge_payload

_FIX = Path(__file__).resolve().parent / "fixtures" / "judge_outputs"


def test_golden_valid_plain_file():
    raw = (_FIX / "valid_plain.json").read_text(encoding="utf-8").strip()
    data, w = extract_judge_json_object(raw)
    assert not w
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] == pytest.approx(0.7)
    assert pr.failure_type == FailureType.NO_FAILURE.value
    assert pr.observability_metadata()["judge_parse_warning_count"] == len(pr.warnings)


def test_golden_prose_wrapped_fenced():
    raw = (_FIX / "prose_wrapped.txt").read_text(encoding="utf-8")
    data, w = extract_judge_json_object(raw)
    assert not w
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] == pytest.approx(0.6)
    assert pr.failure_type == FailureType.NO_FAILURE.value


def test_golden_malformed_extract_fails():
    raw = (_FIX / "malformed.txt").read_text(encoding="utf-8")
    data, w = extract_judge_json_object(raw)
    assert data == {}
    assert w


def test_golden_balanced_invalid_json_warnings():
    raw = (_FIX / "balanced_but_invalid.txt").read_text(encoding="utf-8")
    data, w = extract_judge_json_object(raw)
    assert data == {}
    assert "balanced_brace_json_invalid" in w


def test_parse_wrong_type_score_field():
    data = {
        "faithfulness": "totally_not_a_number",
        "failure_type": "NO_FAILURE",
    }
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] is None
    assert any("invalid_numeric:faithfulness" in x for x in pr.warnings)


def test_parse_missing_all_scores_failure_only():
    data = {"failure_type": "RETRIEVAL_MISS"}
    pr = parse_judge_payload(data)
    assert pr.failure_type == FailureType.RETRIEVAL_MISS.value
    assert all(pr.scores[k] is None for k in pr.scores)


def test_parse_extra_nested_object_does_not_crash():
    data = {
        "faithfulness": 0.5,
        "failure_type": "NO_FAILURE",
        "extra": {"nested": 1},
    }
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] == pytest.approx(0.5)


def test_parse_out_of_range_negative_clamped():
    data = {"faithfulness": -0.5, "failure_type": "NO_FAILURE"}
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] == pytest.approx(0.0)
    assert pr.score_clamping_occurred is True
