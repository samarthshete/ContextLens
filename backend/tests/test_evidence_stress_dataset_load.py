"""Pure file checks for evidence-stress-v1 (no DB)."""

from __future__ import annotations

import pytest

from app.services.benchmark_evidence_seed import (
    build_combined_corpus_text,
    load_manifest,
    load_queries,
)
from app.services.benchmark_stress_seed import default_stress_dataset_dir


@pytest.mark.no_database_cleanup
def test_default_stress_dataset_dir_exists() -> None:
    d = default_stress_dataset_dir()
    assert d.is_dir(), f"Expected stress dataset directory: {d}"


@pytest.mark.no_database_cleanup
def test_stress_queries_and_narrow_corpus() -> None:
    """On-topic Redis material is in corpus; off-topic expected answers are absent (stress design)."""
    stress_dir = default_stress_dataset_dir()
    manifest = load_manifest(stress_dir)
    queries = load_queries(stress_dir)
    assert len(queries) == 6
    combined = build_combined_corpus_text(stress_dir, manifest)
    assert len(combined) > 200
    assert "allkeys-lru" in combined
    assert "noeviction" in combined
    assert "volatile-lru" in combined
    # Off-topic query expected answers should not appear in the narrow Redis corpus
    for row in queries:
        qt = row["query_text"].lower()
        exp = row["expected_answer"]
        if "istio" in qt or "postgresql" in qt or "grpc" in qt:
            assert exp not in combined, row["query_text"]


@pytest.mark.no_database_cleanup
def test_stress_manifest_lists_existing_files() -> None:
    stress_dir = default_stress_dataset_dir()
    m = load_manifest(stress_dir)
    for rel in m["corpus_files"]:
        assert (stress_dir / rel).is_file(), rel
