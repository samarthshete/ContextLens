"""Tests for diagnosis experiment design: bucketing, scoring, plan generation, export."""

import random

import pytest

from app.services.diagnosis_experiment_design import (
    ALL_BUCKETS,
    EXPORT_PLAN_ROW_KEYS,
    CandidateRun,
    build_experiment_plan,
    classify_bucket,
    compute_difficulty,
    format_bucket_summary,
    format_experiment_plan,
    plan_to_export_rows,
    score_candidates,
)

pytestmark = pytest.mark.no_database_cleanup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    run_id: int = 1,
    failure_type: str = "NO_FAILURE",
    query_text: str = "test query",
    query_case_id: int = 1,
    retrieval_relevance: float | None = 0.5,
    context_coverage: float | None = 0.5,
    completeness: float | None = 0.5,
    faithfulness: float | None = None,
    manual_sessions: int = 0,
    assisted_sessions: int = 0,
) -> CandidateRun:
    return CandidateRun(
        run_id=run_id,
        failure_type=failure_type,
        query_text=query_text,
        query_case_id=query_case_id,
        retrieval_relevance=retrieval_relevance,
        context_coverage=context_coverage,
        completeness=completeness,
        faithfulness=faithfulness,
        manual_sessions=manual_sessions,
        assisted_sessions=assisted_sessions,
    )


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


class TestClassifyBucket:
    def test_retrieval_miss(self):
        assert classify_bucket("RETRIEVAL_MISS") == "retrieval_related"

    def test_retrieval_partial(self):
        assert classify_bucket("RETRIEVAL_PARTIAL") == "retrieval_related"

    def test_chunk_fragmentation(self):
        assert classify_bucket("CHUNK_FRAGMENTATION") == "retrieval_related"

    def test_answer_unsupported(self):
        assert classify_bucket("ANSWER_UNSUPPORTED") == "generation_incomplete"

    def test_answer_incomplete(self):
        assert classify_bucket("ANSWER_INCOMPLETE") == "generation_incomplete"

    def test_context_truncation(self):
        assert classify_bucket("CONTEXT_TRUNCATION") == "generation_incomplete"

    def test_mixed_failure(self):
        assert classify_bucket("MIXED_FAILURE") == "mixed_ambiguous"

    def test_unknown(self):
        assert classify_bucket("UNKNOWN") == "mixed_ambiguous"

    def test_context_insufficient(self):
        assert classify_bucket("CONTEXT_INSUFFICIENT") == "mixed_ambiguous"

    def test_no_failure(self):
        assert classify_bucket("NO_FAILURE") == "easy_control"

    def test_none_maps_to_easy(self):
        assert classify_bucket(None) == "easy_control"

    def test_empty_string_maps_to_easy(self):
        assert classify_bucket("") == "easy_control"

    def test_unknown_string_maps_to_mixed(self):
        assert classify_bucket("SOMETHING_WEIRD") == "mixed_ambiguous"


# ---------------------------------------------------------------------------
# Difficulty computation
# ---------------------------------------------------------------------------


class TestComputeDifficulty:
    def test_perfect_scores_low_difficulty(self):
        c = _make_candidate(retrieval_relevance=1.0, context_coverage=1.0,
                            completeness=1.0, faithfulness=1.0)
        assert compute_difficulty(c) == pytest.approx(0.0)

    def test_zero_scores_max_difficulty(self):
        c = _make_candidate(retrieval_relevance=0.0, context_coverage=0.0,
                            completeness=0.0, faithfulness=0.0)
        assert compute_difficulty(c) == pytest.approx(1.0)

    def test_missing_scores_neutral(self):
        c = _make_candidate(retrieval_relevance=None, context_coverage=None,
                            completeness=None, faithfulness=None)
        assert compute_difficulty(c) == pytest.approx(0.5)

    def test_mixed_scores(self):
        c = _make_candidate(retrieval_relevance=0.2, context_coverage=0.8,
                            completeness=0.5, faithfulness=None)
        # (0.8 + 0.2 + 0.5 + 0.5) / 4 = 0.5
        assert compute_difficulty(c) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Scoring: NO_FAILURE penalty
# ---------------------------------------------------------------------------


class TestScoring:
    def test_no_failure_penalised(self):
        candidates = [
            _make_candidate(run_id=1, failure_type="NO_FAILURE"),
            _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS"),
        ]
        scored = score_candidates(candidates)
        # RETRIEVAL_MISS should rank higher
        assert scored[0].candidate.run_id == 2
        assert scored[1].candidate.run_id == 1
        assert scored[0].score > scored[1].score

    def test_no_failure_gets_negative_score(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="NO_FAILURE"),
        ])
        assert scored[0].score < 0, "NO_FAILURE should have negative score"

    def test_failure_gets_positive_base(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS"),
        ])
        assert scored[0].score > 0, "Real failures should have positive score"


# ---------------------------------------------------------------------------
# Scoring: repeated-query penalty
# ---------------------------------------------------------------------------


class TestRepeatQueryPenalty:
    def test_first_occurrence_no_penalty(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS", query_text="unique query"),
        ])
        assert all("Repeat" not in r for r in scored[0].score_reasons)

    def test_second_occurrence_penalised(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS", query_text="same query"),
            _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS", query_text="same query"),
        ])
        # First should rank higher
        assert scored[0].candidate.run_id == 1
        assert scored[0].score > scored[1].score

    def test_case_insensitive_dedup(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS", query_text="Same Query"),
            _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS", query_text="same query"),
        ])
        # Second should be penalised (same normalised text)
        repeat_reasons = [r for r in scored[1].score_reasons if "Repeat" in r]
        assert len(repeat_reasons) > 0

    def test_third_occurrence_double_penalty(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS", query_text="dup"),
            _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS", query_text="dup"),
            _make_candidate(run_id=3, failure_type="RETRIEVAL_MISS", query_text="dup"),
        ])
        scores = [s.score for s in scored]
        # Each successive duplicate should have lower score
        assert scores[0] > scores[1] > scores[2]


class TestNearDuplicateQueryPenalty:
    """Whitespace-normalised fingerprints treat near-duplicates as repeats."""

    def test_whitespace_variants_penalised_like_repeat(self):
        scored = score_candidates(
            [
                _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS", query_text="what  is"),
                _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS", query_text="what is"),
            ]
        )
        assert scored[0].candidate.run_id == 1
        assert any("Repeat" in r for r in scored[1].score_reasons)


# ---------------------------------------------------------------------------
# Scoring: session count penalty
# ---------------------------------------------------------------------------


class TestSessionCountPenalty:
    def test_no_sessions_no_penalty(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS",
                            manual_sessions=0, assisted_sessions=0),
        ])
        assert all("sessions" not in r.lower() for r in scored[0].score_reasons)

    def test_many_sessions_penalised(self):
        scored = score_candidates([
            _make_candidate(run_id=1, failure_type="RETRIEVAL_MISS",
                            manual_sessions=5, assisted_sessions=3),
            _make_candidate(run_id=2, failure_type="RETRIEVAL_MISS",
                            manual_sessions=0, assisted_sessions=0,
                            query_text="different query"),
        ])
        # Run with no sessions should rank higher
        assert scored[0].candidate.run_id == 2

    def test_separate_manual_and_assisted_counts_sum(self):
        scored = score_candidates(
            [
                _make_candidate(
                    run_id=1,
                    failure_type="RETRIEVAL_MISS",
                    manual_sessions=2,
                    assisted_sessions=1,
                    query_text="solo",
                ),
            ]
        )
        assert any("Existing sessions=3" in r for r in scored[0].score_reasons)


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_scored_order_independent_of_input_order(self):
        pool = [
            _make_candidate(run_id=i, failure_type="RETRIEVAL_MISS", query_text=f"q{i}", query_case_id=i)
            for i in range(1, 9)
        ]
        ordered = score_candidates(pool)
        shuffled = pool[:]
        random.Random(123).shuffle(shuffled)
        reshuffled = score_candidates(shuffled)
        assert [s.candidate.run_id for s in ordered] == [s.candidate.run_id for s in reshuffled]

    def test_tie_break_higher_run_id_first(self):
        """Equal base+difficulty → sort key (-score, -run_id) prefers larger run_id."""
        scored = score_candidates(
            [
                _make_candidate(run_id=5, failure_type="RETRIEVAL_MISS", query_text="a"),
                _make_candidate(run_id=12, failure_type="RETRIEVAL_MISS", query_text="b"),
            ]
        )
        assert scored[0].candidate.run_id == 12
        assert scored[1].candidate.run_id == 5
        assert scored[0].score == pytest.approx(scored[1].score)


# ---------------------------------------------------------------------------
# Balanced plan generation
# ---------------------------------------------------------------------------


class TestBuildExperimentPlan:
    def _make_diverse_pool(self) -> list[CandidateRun]:
        """Create a pool with enough candidates for a full 20-run plan."""
        pool: list[CandidateRun] = []
        run_id = 1

        # 10 retrieval failures (need 8 = 4+4)
        for i in range(10):
            pool.append(_make_candidate(
                run_id=run_id, failure_type="RETRIEVAL_MISS",
                query_text=f"retrieval query {i}", query_case_id=100 + i,
                retrieval_relevance=0.2 + i * 0.05,
            ))
            run_id += 1

        # 8 generation failures (need 6 = 3+3)
        for i in range(8):
            pool.append(_make_candidate(
                run_id=run_id, failure_type="ANSWER_INCOMPLETE",
                query_text=f"generation query {i}", query_case_id=200 + i,
                completeness=0.3 + i * 0.05,
            ))
            run_id += 1

        # 6 mixed failures (need 4 = 2+2)
        for i in range(6):
            pool.append(_make_candidate(
                run_id=run_id, failure_type="MIXED_FAILURE",
                query_text=f"mixed query {i}", query_case_id=300 + i,
            ))
            run_id += 1

        # 4 easy controls (need 2 = 1+1)
        for i in range(4):
            pool.append(_make_candidate(
                run_id=run_id, failure_type="NO_FAILURE",
                query_text=f"easy query {i}", query_case_id=400 + i,
                retrieval_relevance=0.9, context_coverage=0.9, completeness=0.95,
            ))
            run_id += 1

        return pool

    def test_full_plan_has_20_slots(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        total = len(plan.manual_slots) + len(plan.assisted_slots)
        assert total == 20

    def test_manual_group_has_10(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        assert len(plan.manual_slots) == 10

    def test_assisted_group_has_10(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        assert len(plan.assisted_slots) == 10

    def test_manual_bucket_distribution(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        buckets = [s.bucket for s in plan.manual_slots]
        assert buckets.count("retrieval_related") == 4
        assert buckets.count("generation_incomplete") == 3
        assert buckets.count("mixed_ambiguous") == 2
        assert buckets.count("easy_control") == 1

    def test_assisted_bucket_distribution(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        buckets = [s.bucket for s in plan.assisted_slots]
        assert buckets.count("retrieval_related") == 4
        assert buckets.count("generation_incomplete") == 3
        assert buckets.count("mixed_ambiguous") == 2
        assert buckets.count("easy_control") == 1

    def test_no_duplicate_run_ids(self):
        pool = self._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        all_ids = [s.run_id for s in plan.manual_slots + plan.assisted_slots]
        assert len(all_ids) == len(set(all_ids)), "No run should be assigned twice"


# ---------------------------------------------------------------------------
# Warnings when pool is insufficient
# ---------------------------------------------------------------------------


class TestPlanWarnings:
    def test_warns_when_empty_pool(self):
        plan = build_experiment_plan([])
        assert len(plan.warnings) > 0
        assert any("0/20" in w or "slots filled" in w for w in plan.warnings)

    def test_graceful_partial_fill_counts(self):
        """Only two retrieval candidates → 2 slots total, bucket + total warnings."""
        candidates = [
            _make_candidate(run_id=10, failure_type="RETRIEVAL_MISS", query_text="r1", query_case_id=1),
            _make_candidate(run_id=11, failure_type="RETRIEVAL_MISS", query_text="r2", query_case_id=2),
        ]
        scored = score_candidates(candidates)
        plan = build_experiment_plan(scored)
        assert len(plan.manual_slots) + len(plan.assisted_slots) == 2
        assert plan.bucket_summary["retrieval_related"]["assigned"] == 2
        assert plan.bucket_summary["generation_incomplete"]["assigned"] == 0
        assert any("retrieval_related" in w and "only 2 available" in w for w in plan.warnings)
        assert any("Only 2/20" in w for w in plan.warnings)

    def test_warns_when_bucket_short(self):
        # Only retrieval candidates, nothing else
        candidates = [
            _make_candidate(run_id=i, failure_type="RETRIEVAL_MISS",
                            query_text=f"q{i}", query_case_id=i)
            for i in range(10)
        ]
        scored = score_candidates(candidates)
        plan = build_experiment_plan(scored)
        # Should warn about missing generation, mixed, easy buckets
        assert any("generation_incomplete" in w for w in plan.warnings)
        assert any("mixed_ambiguous" in w for w in plan.warnings)
        assert any("easy_control" in w for w in plan.warnings)

    def test_no_warnings_when_pool_sufficient(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        # Should have no bucket shortage warnings (may have other informational messages)
        bucket_warnings = [w for w in plan.warnings if "need" in w and "available" in w]
        assert len(bucket_warnings) == 0


# ---------------------------------------------------------------------------
# Export shape
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_rows_shape(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        rows = plan_to_export_rows(plan)

        assert len(rows) == 20

        # Check all required fields present
        required_keys = {
            "run_id", "assigned_mode", "bucket", "failure_type",
            "query_text", "difficulty_score", "rationale",
            "existing_manual_sessions", "existing_assisted_sessions",
        }
        for row in rows:
            assert set(row.keys()) == required_keys
            assert list(row.keys()) == list(EXPORT_PLAN_ROW_KEYS)

    def test_export_modes_correct(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        rows = plan_to_export_rows(plan)

        manual_rows = [r for r in rows if r["assigned_mode"] == "manual"]
        assisted_rows = [r for r in rows if r["assigned_mode"] == "assisted"]
        assert len(manual_rows) == 10
        assert len(assisted_rows) == 10

    def test_export_has_valid_buckets(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        rows = plan_to_export_rows(plan)
        valid_buckets = set(ALL_BUCKETS)
        for row in rows:
            assert row["bucket"] in valid_buckets

    def test_slots_carry_explainable_rationale(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        for slot in plan.manual_slots[:3]:
            assert "Has failure" in slot.rationale or "NO_FAILURE" in slot.rationale
            assert slot.query_text


# ---------------------------------------------------------------------------
# Format helpers (smoke tests)
# ---------------------------------------------------------------------------


class TestFormatting:
    def test_format_bucket_summary_runs(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        output = format_bucket_summary(plan)
        assert "retrieval_related" in output
        assert "generation_incomplete" in output

    def test_format_experiment_plan_runs(self):
        pool = TestBuildExperimentPlan()._make_diverse_pool()
        scored = score_candidates(pool)
        plan = build_experiment_plan(scored)
        output = format_experiment_plan(plan)
        assert "MANUAL GROUP" in output
        assert "ASSISTED GROUP" in output

    def test_format_with_warnings(self):
        plan = build_experiment_plan([])
        output = format_experiment_plan(plan)
        assert "WARNING" in output.upper()
