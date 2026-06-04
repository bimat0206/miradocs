"""Tests for retrieval service parent context and keyword fallback."""
import copy
import json
import tempfile
from pathlib import Path

import pytest

from src.retrieval.retrieval_service import RetrievalService, _chunks_cache
from src.indexing.chunk_keyword_search import keyword_search_chunks, clear_chunk_cache
import src.config as config_module


@pytest.fixture(autouse=True)
def _temp_data_dir(monkeypatch):
    """Setup temp data dir and write mock chunks."""
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr("src.retrieval.retrieval_service.get_data_dir", lambda: tmp)
    monkeypatch.setattr("src.indexing.chunk_keyword_search.get_data_dir", lambda: tmp)
    monkeypatch.setattr("src.config.get_data_dir", lambda: tmp)

    # Write mock chunks
    parsed = tmp / "parsed" / "test_doc"
    parsed.mkdir(parents=True)

    parent_id = "parent123"
    chunks = [
        {
            "chunk_id": parent_id,
            "chunk_type": "parent_section_chunk",
            "section_path": "1. Intro",
            "text": "This is the full parent section text about the architecture.",
        },
        {
            "chunk_id": "child1",
            "chunk_type": "child_text_chunk",
            "section_path": "1. Intro",
            "text": "architecture.",
            "parent_chunk_id": parent_id,
        },
        {
            "chunk_id": "child2",
            "chunk_type": "child_text_chunk",
            "section_path": "2. Other",
            "text": "No parent linked here.",
            "parent_chunk_id": None,
        }
    ]
    (parsed / "chunks.json").write_text(json.dumps(chunks))

    # clear module cache
    clear_chunk_cache()
    if "test_doc" in _chunks_cache:
        del _chunks_cache["test_doc"]

    yield tmp

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def _patch_config(overrides: dict):
    import contextlib
    @contextlib.contextmanager
    def _patch():
        if config_module._CONFIG is None:
            config_module.get_config()
        old = copy.deepcopy(config_module._CONFIG)
        for k, v in overrides.items():
            if k in config_module._CONFIG and isinstance(config_module._CONFIG[k], dict) and isinstance(v, dict):
                config_module._CONFIG[k].update(v)
            else:
                config_module._CONFIG[k] = v
        try:
            yield
        finally:
            config_module._CONFIG.clear()
            config_module._CONFIG.update(old)
    return _patch()


class TestRetrievalParentExpansion:
    def test_parent_expansion_with_valid_parent(self):
        service = RetrievalService()
        raw_results = [{"chunk_id": "child1", "doc_id": "test_doc", "parent_chunk_id": "parent123", "text": "architecture."}]

        with _patch_config({"retrieval": {"expand_parent_context": True, "parent_context_max_chars": 1800}}):
            expanded = service._expand_parent_context(raw_results)

        assert expanded[0]["parent_text"] == "This is the full parent section text about the architecture."
        assert expanded[0]["parent_chunk_id"] == "parent123"
        assert expanded[0]["parent_section_path"] == "1. Intro"

    def test_parent_expansion_skips_missing_parent(self):
        service = RetrievalService()
        raw_results = [{"chunk_id": "child2", "doc_id": "test_doc", "parent_chunk_id": None, "text": "No parent linked here."}]

        with _patch_config({"retrieval": {"expand_parent_context": True}}):
            expanded = service._expand_parent_context(raw_results)

        assert "parent_text" not in expanded[0]

    def test_parent_expansion_disabled(self):
        service = RetrievalService()
        raw_results = [{"chunk_id": "child1", "doc_id": "test_doc", "parent_chunk_id": "parent123", "text": "architecture."}]

        with _patch_config({"retrieval": {"expand_parent_context": False}}):
            expanded = service._expand_parent_context(raw_results)

        assert "parent_text" not in expanded[0]


class TestKeywordSearchChunks:
    def test_keyword_search_matches(self):
        # We query for 'architecture'
        results = keyword_search_chunks("architecture", 10)
        assert len(results) > 0
        assert any(r["chunk_id"] == "parent123" for r in results)
        assert any(r["chunk_id"] == "child1" for r in results)
        assert all(r["chunk_id"] != "child2" for r in results)
        assert "score" in results[0]
