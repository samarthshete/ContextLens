"""Pure unit tests for config score comparison (best/worst + delta %) — no DB."""

import pytest

pytestmark = pytest.mark.no_database_cleanup

from app.schemas.config_comparison import ConfigComparisonMetrics
from app.services.config_comparison import build_config_score_comparison


def _m(
    pid: int,
    *,
    runs: int = 1,
    faith: float | None = None,
    comp: float | None = None,
) -> ConfigComparisonMetrics:
    return ConfigComparisonMetrics(
        pipeline_config_id=pid,
        traced_runs=runs,
        avg_faithfulness=faith,
        avg_completeness=comp,
    )


def test_two_configs_faithfulness_delta_uses_worst_as_denominator():
    s = build_config_score_comparison(
        [_m(1, faith=0.4, comp=0.5), _m(2, faith=0.9, comp=0.8)],
        include_faithfulness=True,
    )
    assert s.best_config_faithfulness == 2
    assert s.worst_config_faithfulness == 1
    # 100 * (0.9 - 0.4) / 0.4 = 125.0
    assert s.faithfulness_delta_pct == pytest.approx(125.0)
    assert s.best_config_completeness == 2
    assert s.worst_config_completeness == 1
    assert s.completeness_delta_pct == pytest.approx(60.0)


def test_tie_best_prefers_lower_pipeline_config_id():
    s = build_config_score_comparison(
        [_m(5, faith=0.7, comp=0.6), _m(3, faith=0.7, comp=0.6)],
        include_faithfulness=True,
    )
    assert s.best_config_faithfulness == 3
    assert s.worst_config_faithfulness == 3
    assert s.faithfulness_delta_pct == pytest.approx(0.0)


def test_single_config_zero_delta():
    s = build_config_score_comparison([_m(9, faith=0.55, comp=0.66)], include_faithfulness=True)
    assert s.best_config_faithfulness == 9
    assert s.worst_config_faithfulness == 9
    assert s.faithfulness_delta_pct == pytest.approx(0.0)
    assert s.completeness_delta_pct == pytest.approx(0.0)


def test_missing_faithfulness_skips_faithfulness_rank():
    s = build_config_score_comparison(
        [_m(1, faith=None, comp=0.2), _m(2, faith=None, comp=0.4)],
        include_faithfulness=True,
    )
    assert s.best_config_faithfulness is None
    assert s.worst_config_faithfulness is None
    assert s.faithfulness_delta_pct is None
    assert s.best_config_completeness == 2
    assert s.worst_config_completeness == 1


def test_combined_mode_omits_faithfulness_but_keeps_completeness():
    s = build_config_score_comparison(
        [_m(1, faith=0.9, comp=0.1), _m(2, faith=0.2, comp=0.5)],
        include_faithfulness=False,
    )
    assert s.best_config_faithfulness is None
    assert s.worst_config_faithfulness is None
    assert s.faithfulness_delta_pct is None
    assert s.best_config_completeness == 2
    assert s.worst_config_completeness == 1
    assert s.completeness_delta_pct == pytest.approx(400.0)


def test_worst_avg_near_zero_returns_null_delta():
    s = build_config_score_comparison(
        [_m(1, faith=0.0, comp=0.0), _m(2, faith=0.5, comp=0.5)],
        include_faithfulness=True,
    )
    assert s.faithfulness_delta_pct is None
    assert s.completeness_delta_pct is None
