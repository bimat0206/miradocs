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


class TestVersionAwareRetrieval:
    def test_search_docs_with_version_filters(self, monkeypatch, _temp_data_dir):
        # We need a real/temp registry and mock its connection
        from src.intake.document_registry import DocumentRegistry
        registry = DocumentRegistry(db_path=_temp_data_dir / "registry.db")

        # Patch the _get_registry singleton in retrieval_service to return our registry
        monkeypatch.setattr("src.retrieval.retrieval_service._get_registry", lambda: registry)

        # Register a version group and documents
        doc1_id = registry.register_document("Architecture_v1.pdf", "pdf", 10, "hash-v1")
        doc2_id = registry.register_document("Architecture_v2.pdf", "pdf", 12, "hash-v2")

        # Write chunks for doc1
        parsed1 = _temp_data_dir / "parsed" / doc1_id
        parsed1.mkdir(parents=True)
        import json
        (parsed1 / "chunks.json").write_text(json.dumps([
            {
                "chunk_id": "doc1_child1",
                "chunk_type": "child_text_chunk",
                "section_path": "1. Intro",
                "text": "architecture version one is here.",
                "parent_chunk_id": None,
            }
        ]))

        # Write chunks for doc2 so search doesn't fail to load them
        parsed2 = _temp_data_dir / "parsed" / doc2_id
        parsed2.mkdir(parents=True)
        import json
        (parsed2 / "chunks.json").write_text(json.dumps([
            {
                "chunk_id": "doc2_child1",
                "chunk_type": "child_text_chunk",
                "section_path": "1. Intro",
                "text": "architecture version two is here.",
                "parent_chunk_id": None,
            }
        ]))

        g = registry.create_or_find_group("Architecture", "architecture", "default")
        registry.add_version(g["group_id"], doc1_id)
        registry.add_version(g["group_id"], doc2_id)
        registry.set_latest_version(g["group_id"], doc2_id)

        service = RetrievalService()

        # 1. Search without version filters (matches both)
        res_all = service.search_docs("architecture", filters=None)
        assert res_all.result_count > 0

        # 2. Search filtering by version group
        res_group = service.search_docs("architecture", filters={"version_group_id": g["group_id"]})
        # Result chunks should have version labels set!
        assert res_group.result_count > 0
        for item in res_group.results:
            assert item.version_label in ("v1", "v2")
            assert item.version_number in (1, 2)

        # 3. Search filtering by version group AND version number = 1
        res_v1 = service.search_docs("architecture", filters={"version_group_id": g["group_id"], "version_number": 1})
        assert res_v1.result_count > 0
        for item in res_v1.results:
            assert item.doc_id == doc1_id
            assert item.version_label == "v1"
            assert item.version_number == 1

        # 4. Search filtering by version group AND version number = 2
        res_v2 = service.search_docs("architecture", filters={"version_group_id": g["group_id"], "version_number": 2})
        assert res_v2.result_count > 0
        for item in res_v2.results:
            assert item.doc_id == doc2_id
            assert item.version_label == "v2"
            assert item.version_number == 2
