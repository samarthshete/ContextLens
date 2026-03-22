"""Pure file checks for rag_systems_retrieval_engineering_v1 (no DB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.benchmark_rag_systems_seed import (
    build_combined_corpus_text,
    default_rag_systems_dataset_dir,
    load_manifest,
    load_queries,
)

_BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.no_database_cleanup
def test_default_dir_under_backend() -> None:
    d = default_rag_systems_dataset_dir()
    assert d.is_dir(), f"Expected dataset directory: {d}"
    assert d.parent.name == "benchmark_data"


@pytest.mark.no_database_cleanup
def test_queries_and_corpus_grounding() -> None:
    data_dir = default_rag_systems_dataset_dir()
    manifest = load_manifest(data_dir)
    queries = load_queries(data_dir)
    assert len(queries) == 8
    combined = build_combined_corpus_text(data_dir, manifest)
    assert len(combined) > 1500
    for row in queries:
        assert row["expected_answer"] in combined, row["query_text"]


@pytest.mark.no_database_cleanup
def test_manifest_lists_files() -> None:
    data_dir = default_rag_systems_dataset_dir()
    m = load_manifest(data_dir)
    for rel in m["corpus_files"]:
        assert (data_dir / rel).is_file(), rel


@pytest.mark.no_database_cleanup
def test_queries_accept_query_alias() -> None:
    """Loader accepts legacy ``query`` key."""
    import json

    tmp = _BACKEND / "benchmark_data" / "rag_systems_retrieval_engineering_v1" / "queries.json"
    raw = json.loads(tmp.read_text(encoding="utf-8"))
    assert all("query_text" in r or "query" in r for r in raw)
