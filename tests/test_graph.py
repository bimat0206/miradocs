"""Tests for graph relation extraction and graph_local search."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.extraction.relation_extractor import build_relations, load_graph, get_entity_neighbors
from src.mcp.schemas import GetEntityGraphInput, GetEntityRelationshipsInput
from src.mcp import tools


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_entities():
    """Minimal entity list spanning two pages with shared/distinct services."""
    return [
        {"type": "aws_service", "value": "Transit Gateway", "page": 32},
        {"type": "aws_service", "value": "Direct Connect",  "page": 32},
        {"type": "cidr",        "value": "10.0.0.0/16",     "page": 32},
        {"type": "aws_service", "value": "CloudTrail",      "page": 78},
        {"type": "aws_service", "value": "KMS",             "page": 78},
        # Transit Gateway also appears on page 78 — ties p32 and p78 clusters
        {"type": "aws_service", "value": "Transit Gateway", "page": 78},
    ]


def _graph_cfg(tmp_path, window=1, use_llm=False, min_weight=1):
    return {
        "graph": {
            "use_llm_relations": use_llm,
            "co_occurrence_window_pages": window,
            "min_edge_weight": min_weight,
        },
        "app": {"data_dir": str(tmp_path)},
        "embedding": {"ollama_url": "http://localhost:11434"},
    }


# ─── build_relations ──────────────────────────────────────────────────────────

def test_build_relations_creates_json(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)

    result = build_relations(sample_entities, "doc1", data_dir=tmp_path)

    out = tmp_path / "parsed" / "doc1" / "relations.json"
    assert out.exists(), "relations.json not created"

    data = json.loads(out.read_text())
    assert data["doc_id"] == "doc1"
    assert data["node_count"] > 0
    assert data["edge_count"] > 0

    # Transit Gateway and Direct Connect co-occur on page 32
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    edge_pairs |= {(e["target"], e["source"]) for e in data["edges"]}
    tgw_id = "aws_service::Transit Gateway"
    dc_id  = "aws_service::Direct Connect"
    assert (tgw_id, dc_id) in edge_pairs, (
        f"Expected edge between Transit Gateway and Direct Connect. Got: {edge_pairs}"
    )


def test_build_relations_never_raises_on_empty_entities(tmp_path, monkeypatch):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc_empty").mkdir(parents=True)

    # Should not raise even with empty input
    result = build_relations([], "doc_empty", data_dir=tmp_path)
    assert result["node_count"] == 0
    assert result["edge_count"] == 0


# ─── load_graph ───────────────────────────────────────────────────────────────

def test_load_graph_returns_networkx(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    g = load_graph("doc1", data_dir=tmp_path)
    assert g is not None
    assert g.number_of_nodes() > 0
    assert g.number_of_edges() > 0


def test_load_graph_returns_none_for_missing(tmp_path):
    g = load_graph("nonexistent_doc", data_dir=tmp_path)
    assert g is None


# ─── get_entity_neighbors ─────────────────────────────────────────────────────

def test_get_entity_neighbors_direct(tmp_path, monkeypatch, sample_entities):
    # Use a wide window so all entities can reach each other
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path, window=100))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    g = load_graph("doc1", data_dir=tmp_path)
    assert g is not None

    nbrs = get_entity_neighbors(g, "aws_service", "Transit Gateway", max_hops=1)
    neighbor_values = [n["value"] for n in nbrs]

    assert "Direct Connect" in neighbor_values, (
        f"Expected Direct Connect as neighbor of Transit Gateway. Got: {neighbor_values}"
    )
    assert "10.0.0.0/16" in neighbor_values, (
        f"Expected 10.0.0.0/16 as neighbor of Transit Gateway. Got: {neighbor_values}"
    )


def test_get_entity_neighbors_unknown_entity_returns_empty(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    g = load_graph("doc1", data_dir=tmp_path)
    nbrs = get_entity_neighbors(g, "aws_service", "NonExistentService", max_hops=1)
    assert nbrs == []


# ─── MCP tool: get_entity_graph ───────────────────────────────────────────────

def test_get_entity_graph_mcp_tool(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("src.mcp.tools.get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    result = tools.get_entity_graph(GetEntityGraphInput(doc_id="doc1"))
    assert hasattr(result, "node_count"), f"Expected GetEntityGraphOutput, got: {result}"
    assert result.node_count > 0
    assert result.edge_count > 0
    assert len(result.nodes) == result.node_count
    assert len(result.edges) == result.edge_count


def test_get_entity_graph_returns_error_if_no_graph(tmp_path, monkeypatch):
    monkeypatch.setattr("src.mcp.tools.get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc_missing").mkdir(parents=True)

    result = tools.get_entity_graph(GetEntityGraphInput(doc_id="doc_missing"))
    assert isinstance(result, dict), "Expected error dict when no graph file"
    assert "error" in result


def test_get_entity_graph_filter_by_type(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("src.mcp.tools.get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    result = tools.get_entity_graph(GetEntityGraphInput(doc_id="doc1", entity_type="aws_service"))
    assert hasattr(result, "nodes")
    # All nodes should be aws_service type
    for node in result.nodes:
        assert node.type == "aws_service", f"Expected only aws_service nodes, got: {node.type}"


# ─── MCP tool: get_entity_relationships ───────────────────────────────────────

def test_get_entity_relationships_mcp_tool(tmp_path, monkeypatch, sample_entities):
    monkeypatch.setattr("src.extraction.relation_extractor._get_config", lambda: _graph_cfg(tmp_path, window=100))
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc1").mkdir(parents=True)
    build_relations(sample_entities, "doc1", data_dir=tmp_path)

    result = tools.get_entity_relationships(GetEntityRelationshipsInput(
        doc_id="doc1",
        entity_type="aws_service",
        entity_value="Transit Gateway",
        max_hops=1,
    ))
    assert hasattr(result, "neighbor_count"), f"Expected GetEntityRelationshipsOutput, got: {result}"
    assert result.neighbor_count > 0
    neighbor_values = [r.neighbor_value for r in result.relationships]
    assert "Direct Connect" in neighbor_values, (
        f"Expected Direct Connect in neighbors. Got: {neighbor_values}"
    )


def test_get_entity_relationships_returns_error_for_missing_graph(tmp_path, monkeypatch):
    monkeypatch.setattr("src.extraction.relation_extractor._get_data_dir", lambda: tmp_path)
    (tmp_path / "parsed" / "doc_x").mkdir(parents=True)

    result = tools.get_entity_relationships(GetEntityRelationshipsInput(
        doc_id="doc_x",
        entity_type="aws_service",
        entity_value="EC2",
        max_hops=1,
    ))
    assert isinstance(result, dict)
    assert "error" in result
