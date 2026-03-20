"""LLM judge JSON extraction and validation."""

import pytest

from app.domain.failure_taxonomy import FailureType
from app.services.llm_judge_parse import extract_judge_json_object, parse_judge_payload


def test_extract_fenced_json():
    raw = 'Here:\n```json\n{"faithfulness": 0.5, "failure_type": "NO_FAILURE"}\n```'
    data, w = extract_judge_json_object(raw)
    assert not w
    assert data["faithfulness"] == 0.5


def test_extract_balanced_braces():
    raw = 'prefix {"faithfulness": 1.2, "failure_type": "NO_FAILURE"} trailer'
    data, w = extract_judge_json_object(raw)
    assert data["faithfulness"] == 1.2
    assert not w


def test_parse_clamps_scores_and_normalizes_failure():
    data = {"faithfulness": 99, "failure_type": "retrieval_miss"}
    pr = parse_judge_payload(data)
    assert pr.scores["faithfulness"] == pytest.approx(1.0)
    assert pr.failure_type == FailureType.RETRIEVAL_MISS.value
    assert pr.score_clamping_occurred is True
    assert pr.raw_failure_type == "retrieval_miss"
    assert pr.scores_raw.get("faithfulness") == 99
    assert not any("failure_type_missing" in w for w in pr.warnings)
    obs = pr.observability_metadata()
    assert obs["judge_score_clamping_occurred"] is True
    assert obs["judge_parse_warning_count"] == len(pr.warnings)


def test_parse_missing_failure_type_defaults_unknown():
    data = {"faithfulness": 0.5}
    pr = parse_judge_payload(data)
    assert pr.failure_type == FailureType.UNKNOWN.value
    assert any("failure_type_missing" in w for w in pr.warnings)


def test_parse_invalid_json_object_empty():
    data, w = extract_judge_json_object("not json at all {{{")
    assert data == {}
    assert w


def test_parse_unknown_failure_emits_warning():
    data = {"faithfulness": 0.5, "failure_type": "GIBBERISH_XYZ"}
    pr = parse_judge_payload(data)
    assert pr.failure_type == FailureType.UNKNOWN.value
    assert pr.raw_failure_type == "GIBBERISH_XYZ"
    assert any("failure_type_unrecognized" in w for w in pr.warnings)
