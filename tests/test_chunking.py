"""Tests for chunking: stable IDs, parent links, section-first splitting."""
import copy
import tempfile
from pathlib import Path

import pytest

from src.chunking.chunk_candidate_builder import (
    _stable_chunk_id,
    _page_text_window,
    _section_ranges,
    _split_semantic_blocks,
    _merge_blocks_to_chunks,
    _make_chunk,
    build_chunks,
)
import src.config as config_module


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_pages():
    return [
        {"page": 1, "text": "Introduction text.\n\nSome more intro content."},
        {"page": 2, "text": "Architecture overview.\n\nAWS Transit Gateway design."},
        {"page": 3, "text": "Networking details.\n\nVPC peering setup."},
        {"page": 4, "text": "Security groups.\n\nInbound and outbound rules."},
    ]


@pytest.fixture
def sample_sections():
    return [
        {
            "section_path": "1. Introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "section_path": "2. Architecture",
            "title": "Architecture",
            "page_start": 2,
            "page_end": 3,
        },
        {
            "section_path": "3. Security",
            "title": "Security",
            "page_start": 4,
            "page_end": 4,
        },
    ]


# ─── Test _stable_chunk_id ────────────────────────────────────────────

class TestStableChunkId:
    def test_deterministic(self):
        a = _stable_chunk_id("doc1", "child_text_chunk", 1, 1, "Intro", 0, "some text here")
        b = _stable_chunk_id("doc1", "child_text_chunk", 1, 1, "Intro", 0, "some text here")
        assert a == b

    def test_changes_on_field_diff(self):
        a = _stable_chunk_id("doc1", "child_text_chunk", 1, 1, "Intro", 0, "text")
        b = _stable_chunk_id("doc1", "child_text_chunk", 2, 2, "Intro", 0, "text")
        assert a != b

    def test_returns_hex_16_chars(self):
        cid = _stable_chunk_id("doc1", "parent_section_chunk", 1, 1, "Intro", 0, "text")
        assert len(cid) == 16
        int(cid, 16)  # should not raise ValueError


# ─── Test _make_chunk relationship fields ─────────────────────────────

class TestMakeChunk:
    def test_default_parent_none(self):
        chunk = _make_chunk(
            doc_id="doc1", chunk_type="parent_section_chunk",
            text="Section text", page_start=1, page_end=2,
            section_path="Intro", entities={}, source_refs={},
        )
        assert chunk["parent_chunk_id"] is None
        assert chunk["chunk_index"] == 0
        assert chunk["chunk_count"] == 1

    def test_child_with_parent_id(self):
        parent = _make_chunk(
            doc_id="doc1", chunk_type="parent_section_chunk",
            text="Parent", page_start=1, page_end=2,
            section_path="Intro", entities={}, source_refs={},
        )
        child = _make_chunk(
            doc_id="doc1", chunk_type="child_text_chunk",
            text="Child text", page_start=1, page_end=2,
            section_path="Intro", entities={}, source_refs={},
            chunk_index=0, chunk_count=3,
            parent_chunk_id=parent["chunk_id"],
        )
        assert child["parent_chunk_id"] == parent["chunk_id"]
        assert child["chunk_index"] == 0
        assert child["chunk_count"] == 3


# ─── Test build_chunks stable IDs across reruns ────────────────────────

class TestBuildChunksStable:
    def test_stable_ids_across_runs(self, sample_pages, sample_sections):
        tables, figures, entities, page_images = [], [], [], []
        # Patch config to use stable_chunk_ids
        old_config = copy.deepcopy(config_module._CONFIG) if config_module._CONFIG else None
        with _patch_config({"chunking": {"max_chunk_tokens": 512, "overlap_tokens": 0, "stable_chunk_ids": True, "section_first_chunking": False, "artifact_context_chars": 0}}):
            a = build_chunks("test_stable", sample_pages, sample_sections, tables, figures, entities, page_images)
            b = build_chunks("test_stable", sample_pages, sample_sections, tables, figures, entities, page_images)

        assert len(a) == len(b)
        for ca, cb in zip(a, b):
            assert ca["chunk_id"] == cb["chunk_id"], f"Chunk ID mismatch for {ca['chunk_type']}"

    def test_child_has_parent_link(self, sample_pages, sample_sections):
        with _patch_config({"chunking": {"max_chunk_tokens": 512, "overlap_tokens": 0, "stable_chunk_ids": True, "section_first_chunking": False, "artifact_context_chars": 0}}):
            chunks = build_chunks("test_parent", sample_pages, sample_sections, [], [], [], [])

        # Find parent chunk
        parent = next(c for c in chunks if c["chunk_type"] == "parent_section_chunk")
        # Find child in same section
        child = next(c for c in chunks if c["chunk_type"] == "child_text_chunk"
                     and c["section_path"] == parent["section_path"])
        assert child["parent_chunk_id"] == parent["chunk_id"]

    def test_table_figure_parent_link(self, sample_pages, sample_sections):
        tables = [{"page": 2, "table_id": "t1", "file_md": None}]
        figures = [{"page": 3, "figure_id": "f1", "caption": "Fig 1", "image_path": None}]
        with _patch_config({"chunking": {"max_chunk_tokens": 512, "overlap_tokens": 0, "stable_chunk_ids": True, "section_first_chunking": False, "artifact_context_chars": 0}}):
            chunks = build_chunks("test_tf", sample_pages, sample_sections, tables, figures, [], [])

        table_chunk = next(c for c in chunks if c["chunk_type"] == "table_chunk")
        fig_chunk = next(c for c in chunks if c["chunk_type"] == "figure_chunk")
        # Section "2. Architecture" spans pages 2-3
        parent = next(c for c in chunks if c["chunk_type"] == "parent_section_chunk"
                      and c["section_path"] == "2. Architecture")
        assert table_chunk["parent_chunk_id"] == parent["chunk_id"]
        assert fig_chunk["parent_chunk_id"] == parent["chunk_id"]


# ─── Test section-first chunking ──────────────────────────────────────

class TestSectionFirstChunking:
    def test_section_ranges_fills_gaps(self):
        sections = [
            {"page_start": 1, "page_end": 1, "section_path": "A"},
            {"page_start": 3, "page_end": 4, "section_path": "B"},
        ]
        ranges = _section_ranges(sections, 5)
        assert len(ranges) == 3  # A, gap, B extended
        assert ranges[0]["section_path"] == "A"
        assert ranges[1]["section_path"] == "A (continued)"
        assert ranges[1]["page_start"] == 2
        assert ranges[1]["page_end"] == 2
        assert ranges[2]["section_path"] == "B"
        assert ranges[2]["page_end"] == 5

    def test_split_semantic_blocks_headings_bullets(self):
        text = "# Heading 1\n\nSome para.\n\n- bullet 1\n- bullet 2\n\n1. numbered 1\n2. numbered 2"
        blocks = _split_semantic_blocks(text)
        # heading, paragraph, bullet block, numbered block
        assert len(blocks) >= 3
        assert "# Heading 1" in blocks[0]

    def test_merge_blocks_to_chunks_under_limit(self):
        blocks = ["small block", "another block"]
        chunks = _merge_blocks_to_chunks(blocks, 200, 0)
        assert len(chunks) == 1  # merged
        assert "small block" in chunks[0]
        assert "another block" in chunks[0]

    def test_empty_sections_fallback_to_page_chunks(self, sample_pages):
        with _patch_config({"chunking": {"max_chunk_tokens": 512, "overlap_tokens": 0, "stable_chunk_ids": True, "section_first_chunking": True, "artifact_context_chars": 0}}):
            chunks = build_chunks("test_fallback", sample_pages, [], [], [], [], [])
        child_types = [c for c in chunks if c["chunk_type"] == "child_text_chunk"]
        assert len(child_types) > 0


# ─── Test context window ──────────────────────────────────────────────

class TestContextWindow:
    def test_page_text_window_center(self):
        pages = [
            {"page": 1, "text": "AAA"},
            {"page": 2, "text": "BBB"},
            {"page": 3, "text": "CCC"},
            {"page": 4, "text": "DDD"},
        ]
        result = _page_text_window(pages, 2, 100)
        assert "BBB" in result
        assert "AAA" in result  # expands backward

    def test_page_text_window_first_page(self):
        pages = [{"page": 1, "text": "First"}, {"page": 2, "text": "Second"}]
        result = _page_text_window(pages, 1, 50)
        assert "First" in result
        assert "Second" in result


# ─── Helper ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _temp_data_dir(monkeypatch):
    """Point data_dir to a temp dir so tests don't pollute real data."""
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr("src.chunking.chunk_candidate_builder.get_data_dir", lambda: tmp)
    monkeypatch.setattr("src.config.get_data_dir", lambda: tmp)
    yield tmp
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def _patch_config(overrides: dict):
    """Context manager that merges overrides into the global config."""
    import contextlib
    import copy

    @contextlib.contextmanager
    def _patch():
        if config_module._CONFIG is None:
            config_module.get_config()
        old = copy.deepcopy(config_module._CONFIG)
        # merge shallow
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
