"""Tests for evidence tier gating logic (dashboard_evidence.py helpers)."""

import pytest

from app.services.dashboard_evidence import _diagnosis_tier, _llm_reduction_tier

pytestmark = pytest.mark.no_database_cleanup


# --- Diagnosis timing tiers ---

def test_diagnosis_tier_insufficient_when_manual_low():
    tier, note = _diagnosis_tier(manual_n=2, assisted_n=10)
    assert tier == "insufficient"
    assert "insufficient" in note.lower()


def test_diagnosis_tier_insufficient_when_assisted_low():
    tier, note = _diagnosis_tier(manual_n=10, assisted_n=3)
    assert tier == "insufficient"


def test_diagnosis_tier_limited_when_both_5_to_9():
    tier, note = _diagnosis_tier(manual_n=7, assisted_n=8)
    assert tier == "limited"
    assert "directional" in note.lower()


def test_diagnosis_tier_limited_when_one_below_10():
    tier, note = _diagnosis_tier(manual_n=5, assisted_n=15)
    assert tier == "limited"


def test_diagnosis_tier_normal_when_both_10_plus():
    tier, note = _diagnosis_tier(manual_n=10, assisted_n=10)
    assert tier == "normal"
    assert note == ""


def test_diagnosis_tier_normal_when_high():
    tier, _ = _diagnosis_tier(manual_n=50, assisted_n=50)
    assert tier == "normal"


# --- LLM reduction tiers ---

def test_llm_reduction_sparse_zero():
    tier, note = _llm_reduction_tier(0)
    assert tier == "sparse"
    assert "not meaningful" in note.lower()


def test_llm_reduction_sparse_low():
    tier, _ = _llm_reduction_tier(2)
    assert tier == "sparse"


def test_llm_reduction_directional_3():
    tier, note = _llm_reduction_tier(3)
    assert tier == "directional"
    assert "directional" in note.lower()


def test_llm_reduction_directional_9():
    tier, _ = _llm_reduction_tier(9)
    assert tier == "directional"


def test_llm_reduction_normal_10():
    tier, note = _llm_reduction_tier(10)
    assert tier == "normal"
    assert note == ""


def test_llm_reduction_normal_high():
    tier, _ = _llm_reduction_tier(100)
    assert tier == "normal"


# --- Boundary tests ---

def test_diagnosis_tier_boundary_5_5():
    tier, _ = _diagnosis_tier(manual_n=5, assisted_n=5)
    assert tier == "limited"


def test_diagnosis_tier_boundary_4_4():
    tier, _ = _diagnosis_tier(manual_n=4, assisted_n=4)
    assert tier == "insufficient"


def test_llm_reduction_boundary_exact_3():
    tier, _ = _llm_reduction_tier(3)
    assert tier == "directional"


def test_llm_reduction_boundary_exact_10():
    tier, _ = _llm_reduction_tier(10)
    assert tier == "normal"
