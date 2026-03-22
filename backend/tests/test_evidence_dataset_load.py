"""Pure file checks for evidence-rag-v1 (no DB)."""

from __future__ import annotations

import pytest

from app.services.benchmark_evidence_seed import (
    build_combined_corpus_text,
    default_evidence_dataset_dir,
    load_manifest,
    load_queries,
)


@pytest.mark.no_database_cleanup
def test_default_evidence_dir_exists() -> None:
    d = default_evidence_dataset_dir()
    assert d.is_dir(), f"Expected evidence dataset directory: {d}"


@pytest.mark.no_database_cleanup
def test_queries_and_corpus_grounding() -> None:
    evidence_dir = default_evidence_dataset_dir()
    manifest = load_manifest(evidence_dir)
    queries = load_queries(evidence_dir)
    assert len(queries) == 8
    combined = build_combined_corpus_text(evidence_dir, manifest)
    assert len(combined) > 2000
    for row in queries:
        assert row["expected_answer"] in combined, row["query_text"]


@pytest.mark.no_database_cleanup
def test_manifest_lists_existing_files() -> None:
    evidence_dir = default_evidence_dataset_dir()
    m = load_manifest(evidence_dir)
    for rel in m["corpus_files"]:
        assert (evidence_dir / rel).is_file(), rel
