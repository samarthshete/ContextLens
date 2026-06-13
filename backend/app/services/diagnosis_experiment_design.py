"""Balanced experiment design for diagnosis timing studies.

Pure functions — no database access, fully testable.

Bucket definitions are grounded in ``app.domain.failure_taxonomy``:

* **retrieval_related:** RETRIEVAL_MISS, RETRIEVAL_PARTIAL, CHUNK_FRAGMENTATION
* **generation_incomplete:** ANSWER_UNSUPPORTED, ANSWER_INCOMPLETE, CONTEXT_TRUNCATION
* **mixed_ambiguous:** MIXED_FAILURE, UNKNOWN, CONTEXT_INSUFFICIENT
* **easy_control:** NO_FAILURE
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Bucket definitions (grounded in failure_taxonomy.py FailureType enum)
# ---------------------------------------------------------------------------

Bucket = Literal["retrieval_related", "generation_incomplete", "mixed_ambiguous", "easy_control"]

FAILURE_TO_BUCKET: dict[str, Bucket] = {
    "RETRIEVAL_MISS": "retrieval_related",
    "RETRIEVAL_PARTIAL": "retrieval_related",
    "CHUNK_FRAGMENTATION": "retrieval_related",
    "ANSWER_UNSUPPORTED": "generation_incomplete",
    "ANSWER_INCOMPLETE": "generation_incomplete",
    "CONTEXT_TRUNCATION": "generation_incomplete",
    "MIXED_FAILURE": "mixed_ambiguous",
    "UNKNOWN": "mixed_ambiguous",
    "CONTEXT_INSUFFICIENT": "mixed_ambiguous",
    "NO_FAILURE": "easy_control",
}

# Per-group target allocation: 4 retrieval + 3 generation + 2 mixed + 1 easy = 10
GROUP_TARGETS: dict[Bucket, int] = {
    "retrieval_related": 4,
    "generation_incomplete": 3,
    "mixed_ambiguous": 2,
    "easy_control": 1,
}

ALL_BUCKETS: list[Bucket] = ["retrieval_related", "generation_incomplete", "mixed_ambiguous", "easy_control"]

# Stable column order for CSV/JSON export (documented contract for scripts).
EXPORT_PLAN_ROW_KEYS: tuple[str, ...] = (
    "run_id",
    "assigned_mode",
    "bucket",
    "failure_type",
    "query_text",
    "difficulty_score",
    "rationale",
    "existing_manual_sessions",
    "existing_assisted_sessions",
)


# ---------------------------------------------------------------------------
# Candidate data (input to the planner)
# ---------------------------------------------------------------------------


@dataclass
class CandidateRun:
    """Flat representation of a run suitable for experiment selection."""

    run_id: int
    failure_type: str  # from evaluation_results
    query_text: str
    query_case_id: int
    dataset_id: int | None = None
    # Evaluation scores (0..1 or None)
    retrieval_relevance: float | None = None
    context_coverage: float | None = None
    completeness: float | None = None
    faithfulness: float | None = None
    # Existing session counts
    manual_sessions: int = 0
    assisted_sessions: int = 0


@dataclass
class ScoredCandidate:
    """Candidate with computed bucket and experiment-design score."""

    candidate: CandidateRun
    bucket: Bucket
    score: float  # higher = better candidate
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class ExperimentSlot:
    """One slot in the balanced experiment plan."""

    run_id: int
    mode: Literal["manual", "assisted"]
    bucket: Bucket
    failure_type: str
    query_text: str
    difficulty_score: float
    rationale: str
    manual_sessions: int = 0
    assisted_sessions: int = 0


@dataclass
class ExperimentPlan:
    """A complete balanced 20-run experiment proposal."""

    manual_slots: list[ExperimentSlot]
    assisted_slots: list[ExperimentSlot]
    warnings: list[str]
    bucket_summary: dict[Bucket, dict[str, int]]  # bucket -> {available, needed_total, assigned}


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def classify_bucket(failure_type: str | None) -> Bucket:
    """Map a failure_type string to an experiment bucket."""
    if not failure_type:
        return "easy_control"
    return FAILURE_TO_BUCKET.get(failure_type.strip(), "mixed_ambiguous")


# ---------------------------------------------------------------------------
# Scoring — deterministic, explainable
# ---------------------------------------------------------------------------

def _query_fingerprint(text: str) -> str:
    """Stable short hash of normalised query text for dedup.

    Collapses internal whitespace so near-duplicate strings (extra spaces) share a fingerprint.
    """
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return hashlib.md5(t.encode()).hexdigest()[:12]


def score_candidates(
    candidates: list[CandidateRun],
    *,
    no_failure_penalty: float = -50.0,
    repeat_query_penalty: float = -30.0,
    heavy_session_penalty_per: float = -10.0,
    difficulty_bonus_weight: float = 20.0,
) -> list[ScoredCandidate]:
    """Score and bucket all candidates. Higher score = better for experiment.

    Scoring logic:
    1. Base score from failure type: non-NO_FAILURE gets +40 base, NO_FAILURE gets penalty.
    2. Difficulty bonus from evaluation scores — lower scores = harder = more interesting.
    3. Repeat-query penalty: second+ runs with same normalised query text get penalised.
    4. Heavy-session penalty: runs already with many sessions are less valuable.
    5. Bucket diversity is handled downstream by the planner, not here.
    """
    # Track query text frequencies for repeat penalty
    query_seen: dict[str, int] = {}

    scored: list[ScoredCandidate] = []
    for c in candidates:
        bucket = classify_bucket(c.failure_type)
        base_score = 0.0
        reasons: list[str] = []

        # 1. Failure type signal
        if bucket == "easy_control":
            base_score += no_failure_penalty
            reasons.append(f"NO_FAILURE penalty ({no_failure_penalty:+.0f})")
        else:
            base_score += 40.0
            reasons.append(f"Has failure ({c.failure_type}) (+40)")

        # 2. Difficulty bonus — lower eval scores = harder run = more interesting
        difficulty = _compute_difficulty(c)
        diff_bonus = difficulty * difficulty_bonus_weight
        base_score += diff_bonus
        if diff_bonus > 0:
            reasons.append(f"Difficulty bonus ({diff_bonus:+.1f}, raw={difficulty:.2f})")

        # 3. Repeat-query penalty
        fp = _query_fingerprint(c.query_text)
        seen_count = query_seen.get(fp, 0)
        query_seen[fp] = seen_count + 1
        if seen_count > 0:
            penalty = repeat_query_penalty * seen_count
            base_score += penalty
            reasons.append(f"Repeat query #{seen_count + 1} ({penalty:+.0f})")

        # 4. Heavy-session penalty
        total_sessions = c.manual_sessions + c.assisted_sessions
        if total_sessions > 0:
            sp = heavy_session_penalty_per * total_sessions
            base_score += sp
            reasons.append(f"Existing sessions={total_sessions} ({sp:+.0f})")

        scored.append(ScoredCandidate(
            candidate=c,
            bucket=bucket,
            score=base_score,
            score_reasons=reasons,
        ))

    # Sort: highest score first, then by run_id descending for stability
    scored.sort(key=lambda s: (-s.score, -s.candidate.run_id))
    return scored


def compute_difficulty(c: CandidateRun) -> float:
    """0..1 difficulty estimate from evaluation scores. Higher = harder.

    Uses available scores; missing scores contribute 0.5 (neutral).
    Lower eval scores → higher difficulty.
    """
    components: list[float] = []
    for val in (c.retrieval_relevance, c.context_coverage, c.completeness, c.faithfulness):
        if val is not None:
            # Invert: low score = high difficulty
            components.append(1.0 - max(0.0, min(1.0, val)))
        else:
            components.append(0.5)

    return sum(components) / len(components) if components else 0.5


# Backward-compatible name for internal callers
_compute_difficulty = compute_difficulty


# ---------------------------------------------------------------------------
# Balanced plan generation
# ---------------------------------------------------------------------------


def build_experiment_plan(
    scored: list[ScoredCandidate],
    *,
    targets: dict[Bucket, int] | None = None,
) -> ExperimentPlan:
    """Select 20 runs (10 manual + 10 assisted) with balanced bucket allocation.

    Within each bucket, pairs similar-difficulty candidates across manual/assisted.
    Avoids assigning the same query_case_id to both manual and assisted.
    Warns when insufficient candidates exist for any bucket.
    """
    if targets is None:
        targets = dict(GROUP_TARGETS)

    # Partition scored candidates by bucket
    bucket_pools: dict[Bucket, list[ScoredCandidate]] = {b: [] for b in ALL_BUCKETS}
    for sc in scored:
        bucket_pools[sc.bucket].append(sc)

    warnings: list[str] = []
    manual_slots: list[ExperimentSlot] = []
    assisted_slots: list[ExperimentSlot] = []
    bucket_summary: dict[Bucket, dict[str, int]] = {}

    for bucket in ALL_BUCKETS:
        target_per_group = targets.get(bucket, 0)
        needed_total = target_per_group * 2  # manual + assisted
        pool = bucket_pools[bucket]
        available = len(pool)

        bucket_summary[bucket] = {
            "available": available,
            "needed_total": needed_total,
            "assigned": 0,
        }

        if available < needed_total:
            warnings.append(
                f"Bucket '{bucket}': need {needed_total} candidates (2×{target_per_group}) "
                f"but only {available} available. Experiment will be incomplete for this bucket."
            )

        # Greedy pairing: take top candidates, pair by alternating manual/assisted
        # Avoid same query_case_id in both groups
        used_query_ids_manual: set[int] = set()
        used_query_ids_assisted: set[int] = set()
        assigned_run_ids: set[int] = set()

        manual_picked: list[ScoredCandidate] = []
        assisted_picked: list[ScoredCandidate] = []

        for sc in pool:
            if sc.candidate.run_id in assigned_run_ids:
                continue

            qcid = sc.candidate.query_case_id

            # Try to assign to whichever group needs more and avoids query overlap
            m_needs = target_per_group - len(manual_picked)
            a_needs = target_per_group - len(assisted_picked)

            if m_needs <= 0 and a_needs <= 0:
                break

            # Prefer assigning to the group that needs more candidates
            # Break ties by avoiding query_case_id overlap
            can_manual = m_needs > 0 and qcid not in used_query_ids_manual
            can_assisted = a_needs > 0 and qcid not in used_query_ids_assisted

            if can_manual and can_assisted:
                # Assign to whichever group needs more; break ties: manual first
                if m_needs >= a_needs:
                    manual_picked.append(sc)
                    used_query_ids_manual.add(qcid)
                else:
                    assisted_picked.append(sc)
                    used_query_ids_assisted.add(qcid)
            elif can_manual:
                manual_picked.append(sc)
                used_query_ids_manual.add(qcid)
            elif can_assisted:
                assisted_picked.append(sc)
                used_query_ids_assisted.add(qcid)
            else:
                # Query already used in both groups — still assign if a group needs it
                if m_needs > 0:
                    manual_picked.append(sc)
                    used_query_ids_manual.add(qcid)
                elif a_needs > 0:
                    assisted_picked.append(sc)
                    used_query_ids_assisted.add(qcid)
                else:
                    continue

            assigned_run_ids.add(sc.candidate.run_id)

        # Build slots
        for sc in manual_picked:
            manual_slots.append(_make_slot(sc, "manual"))
        for sc in assisted_picked:
            assisted_slots.append(_make_slot(sc, "assisted"))

        bucket_summary[bucket]["assigned"] = len(manual_picked) + len(assisted_picked)

    # Final check: total assignments
    total = len(manual_slots) + len(assisted_slots)
    if total < 20:
        warnings.append(
            f"Only {total}/20 slots filled. The database lacks enough diverse "
            f"failure candidates for a full balanced experiment."
        )

    return ExperimentPlan(
        manual_slots=manual_slots,
        assisted_slots=assisted_slots,
        warnings=warnings,
        bucket_summary=bucket_summary,
    )


def _make_slot(sc: ScoredCandidate, mode: Literal["manual", "assisted"]) -> ExperimentSlot:
    c = sc.candidate
    difficulty = _compute_difficulty(c)
    return ExperimentSlot(
        run_id=c.run_id,
        mode=mode,
        bucket=sc.bucket,
        failure_type=c.failure_type,
        query_text=c.query_text,
        difficulty_score=round(difficulty, 3),
        rationale="; ".join(sc.score_reasons),
        manual_sessions=c.manual_sessions,
        assisted_sessions=c.assisted_sessions,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bucket_summary(plan: ExperimentPlan) -> str:
    """Human-readable bucket summary."""
    lines = ["\nBucket Summary:"]
    lines.append(f"  {'Bucket':<25} {'Available':>10} {'Needed':>8} {'Assigned':>10}")
    lines.append("  " + "-" * 55)
    for bucket in ALL_BUCKETS:
        info = plan.bucket_summary[bucket]
        status = "✓" if info["assigned"] >= info["needed_total"] else "✗"
        lines.append(
            f"  {bucket:<25} {info['available']:>10} {info['needed_total']:>8} "
            f"{info['assigned']:>10}  {status}"
        )
    return "\n".join(lines)


def format_experiment_plan(plan: ExperimentPlan) -> str:
    """Full human-readable experiment plan output."""
    lines: list[str] = []

    if plan.warnings:
        lines.append("\n⚠ WARNINGS:")
        for w in plan.warnings:
            lines.append(f"  • {w}")

    lines.append(format_bucket_summary(plan))

    for label, slots in [("MANUAL GROUP (10 sessions)", plan.manual_slots),
                         ("ASSISTED GROUP (10 sessions)", plan.assisted_slots)]:
        lines.append(f"\n{label}:")
        lines.append(
            f"  {'#':>3} {'Run ID':>8} {'Bucket':<25} {'Failure Type':<22} "
            f"{'Diff':>5} {'M':>3} {'A':>3} {'Query (truncated)':<40}"
        )
        lines.append("  " + "-" * 115)
        for i, s in enumerate(slots, 1):
            qt = s.query_text[:38] if s.query_text else ""
            lines.append(
                f"  {i:>3} {s.run_id:>8} {s.bucket:<25} {s.failure_type:<22} "
                f"{s.difficulty_score:>5.2f} {s.manual_sessions:>3} {s.assisted_sessions:>3} {qt:<40}"
            )
        if not slots:
            lines.append("  (no candidates available)")

    return "\n".join(lines)


def plan_to_export_rows(plan: ExperimentPlan) -> list[dict[str, object]]:
    """Convert plan to flat dicts suitable for CSV/JSON export (key order = ``EXPORT_PLAN_ROW_KEYS``)."""
    rows: list[dict[str, object]] = []
    for slot in plan.manual_slots + plan.assisted_slots:
        rows.append(
            {
                "run_id": slot.run_id,
                "assigned_mode": slot.mode,
                "bucket": slot.bucket,
                "failure_type": slot.failure_type,
                "query_text": slot.query_text,
                "difficulty_score": slot.difficulty_score,
                "rationale": slot.rationale,
                "existing_manual_sessions": slot.manual_sessions,
                "existing_assisted_sessions": slot.assisted_sessions,
            }
        )
    return rows
