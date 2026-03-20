"""Strict, safe parsing of LLM judge JSON (no uncaught parse errors)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.failure_taxonomy import FailureType, normalize_failure_type

SCORE_KEYS = (
    "faithfulness",
    "completeness",
    "groundedness",
    "retrieval_relevance",
    "context_coverage",
)


def _clamp01_val(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return max(0.0, min(1.0, x))


def _coerce_raw_number(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x


def extract_judge_json_object(raw: str) -> tuple[dict[str, Any], list[str]]:
    """Best-effort extract a JSON object from model text. Never raises.

    Returns ``({}, warnings)`` on total failure.
    """
    warnings: list[str] = []
    text = (raw or "").strip()
    if not text:
        return {}, ["empty_judge_response"]

    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1)), warnings
        except json.JSONDecodeError:
            warnings.append("fenced_json_invalid")

    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            return obj, warnings
                        warnings.append("json_root_not_object")
                        return {}, warnings
                    except json.JSONDecodeError:
                        warnings.append("balanced_brace_json_invalid")
                        break

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, warnings
        warnings.append("json_root_not_object")
    except json.JSONDecodeError:
        warnings.append("json_decode_failed")

    return {}, warnings


@dataclass
class JudgeParseResult:
    """Parsed judge scores + observability for ``metadata_json``."""

    scores: dict[str, float | None]
    failure_type: str | None
    warnings: list[str] = field(default_factory=list)
    score_clamping_occurred: bool = False
    scores_raw: dict[str, Any] = field(default_factory=dict)
    raw_failure_type: str | None = None

    def observability_metadata(self) -> dict[str, Any]:
        return {
            "judge_score_clamping_occurred": self.score_clamping_occurred,
            "judge_scores_raw": self.scores_raw if self.scores_raw else None,
            "judge_raw_failure_type": self.raw_failure_type,
            "judge_parse_warning_count": len(self.warnings),
        }


def parse_judge_payload(
    data: dict[str, Any],
    *,
    existing_warnings: list[str] | None = None,
) -> JudgeParseResult:
    """Parse judge JSON object into clamped scores, normalized ``failure_type``, warnings.

    Stores **raw** score and failure_type values before clamp/normalize for observability.
    """
    warnings = list(existing_warnings or [])
    scores: dict[str, float | None] = {k: None for k in SCORE_KEYS}
    scores_raw: dict[str, Any] = {}
    clamping_any = False

    for k in SCORE_KEYS:
        if k not in data:
            continue
        raw_v = data[k]
        scores_raw[k] = raw_v
        raw_num = _coerce_raw_number(raw_v)
        if raw_num is None and raw_v is not None:
            warnings.append(f"invalid_numeric:{k}")
        clamped = _clamp01_val(raw_v)
        scores[k] = clamped
        if raw_num is not None and clamped is not None:
            if raw_num < 0.0 or raw_num > 1.0 or abs(raw_num - clamped) > 1e-12:
                clamping_any = True

    raw_ft: str | None = None
    if "failure_type" in data and data["failure_type"] is not None:
        raw_ft = str(data["failure_type"]).strip() or None
        if raw_ft:
            scores_raw["failure_type"] = data["failure_type"]

    if raw_ft is None or not raw_ft:
        warnings.append("failure_type_missing_default_unknown")
        ft = FailureType.UNKNOWN.value
    else:
        ft = normalize_failure_type(raw_ft)
        if ft == FailureType.UNKNOWN.value and raw_ft.upper() not in ("UNKNOWN", ""):
            warnings.append("failure_type_unrecognized_normalized_to_unknown")

    return JudgeParseResult(
        scores=scores,
        failure_type=ft,
        warnings=warnings,
        score_clamping_occurred=clamping_any,
        scores_raw={k: v for k, v in scores_raw.items()},
        raw_failure_type=raw_ft,
    )
