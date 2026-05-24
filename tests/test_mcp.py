"""Tests for MCP server and retrieval service."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.intake.document_registry import DocumentRegistry
from src.mcp import server, tools
from src.mcp.schemas import (
    DetectCompareModeInput,
    GetCompareRunInput,
    GetIndexStatusInput,
    GetPageMatchesInput,
    GetPipelineStatusInput,
    ListCompareRunsInput,
    PutCompareInput,
    PutCrossSearchInput,
    SearchDocsInput,
)
from src.mcp.tools import search_docs
from src.retrieval.retrieval_service import RetrievalService


@pytest.fixture
def setup_chunks(tmp_path, monkeypatch):
    """Set up test chunks.json in a temp data directory."""
    # Copy fixture to temp parsed dir
    data_dir = tmp_path / "data"
    parsed_dir = data_dir / "parsed" / "doc_lz_001"
    parsed_dir.mkdir(parents=True)
    fixture = Path(__file__).parent / "fixtures" / "chunks.json"
    shutil.copy(fixture, parsed_dir / "chunks.json")

    # Patch get_data_dir to return our temp dir
    monkeypatch.setattr("src.config.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("src.retrieval.retrieval_service.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("src.retrieval.evidence_pack.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("src.mcp.tools.get_data_dir", lambda: data_dir)
    return data_dir


@pytest.fixture
def mcp_state(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    registry = DocumentRegistry(db_path=tmp_path / "registry.db")
    monkeypatch.setattr("src.config.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("src.mcp.tools.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("src.mcp.tools._get_registry", lambda: registry)
    return data_dir, registry


def test_tools_list_includes_read_only_toolset():
    names = {tool["name"] for tool in server.TOOLS}
    assert {
        "search_docs",
        "list_documents",
        "get_document_info",
        "get_page_evidence",
        "get_section_content",
        "get_entities",
        "get_page_matches",
        "get_pipeline_status",
        "get_index_status",
        "detect_compare_mode",
        "list_compare_runs",
        "get_compare_run",
        "put_cross_search",
        "put_compare",
    }.issubset(names)


def test_search_docs_rejects_empty_query(setup_chunks):
    """search_docs rejects empty query."""
    params = SearchDocsInput(query="", top_k=5)
    result = search_docs(params)
    assert result.result_count == 0
    assert "Empty query" in result.warnings[0]


def test_search_docs_caps_top_k(setup_chunks, monkeypatch):
    """search_docs caps top_k at configured max."""
    # SearchDocsInput already validates max 20 via Field(le=20)
    params = SearchDocsInput(query="TGW route table", top_k=20)
    result = search_docs(params)
    assert result.top_k <= 20


def test_search_docs_keyword_fallback(setup_chunks):
    """search_docs returns keyword fallback results from chunks.json."""
    params = SearchDocsInput(query="TGW route table Prod NonProd", search_mode="keyword")
    result = search_docs(params)
    assert result.result_count > 0
    assert result.search_mode_used == "keyword"
    # Networking chunk should rank first
    assert "Transit Gateway" in result.results[0].text or "TGW" in result.results[0].text


def test_search_docs_accepts_multiple_doc_ids(setup_chunks):
    second_dir = setup_chunks / "parsed" / "doc_other_001"
    second_dir.mkdir(parents=True)
    shutil.copy(Path(__file__).parent / "fixtures" / "chunks.json", second_dir / "chunks.json")

    params = SearchDocsInput(query="Transit Gateway", doc_ids=["doc_other_001"], search_mode="keyword")
    result = search_docs(params)

    assert result.result_count > 0
    assert {item.doc_id for item in result.results} == {"doc_other_001"}


def test_search_docs_includes_metadata(setup_chunks):
    """search_docs includes source file, page number, section path, and chunk_id."""
    params = SearchDocsInput(query="CloudTrail organization trail", search_mode="keyword")
    result = search_docs(params)
    assert result.result_count > 0
    top = result.results[0]
    assert top.chunk_id != ""
    assert top.page_start > 0
    assert top.section_path != ""
    assert top.doc_id == "doc_lz_001"


def test_search_docs_no_paths_outside_data_dir(setup_chunks):
    """search_docs does not return paths outside the configured data directory."""
    params = SearchDocsInput(query="Transit Gateway", search_mode="keyword")
    result = search_docs(params)
    for item in result.results:
        for key, val in item.source_refs.items():
            if isinstance(val, str) and val:
                assert not val.startswith("/etc")
                assert not val.startswith("/root")
                assert ".." not in val


def test_retrieval_service_fallback_graceful(setup_chunks):
    """RetrievalService falls back gracefully if vector store unavailable."""
    service = RetrievalService()
    # auto mode should fall back to keyword when Qdrant is not available
    result = service.search_docs("breakglass SCP deletion", top_k=5, search_mode="auto")
    assert result.result_count > 0
    assert result.search_mode_used in ("keyword", "fallback", "hybrid")


def test_search_security_query(setup_chunks):
    """breakglass SCP query returns security chunk first."""
    params = SearchDocsInput(query="breakglass SCP deletion", search_mode="keyword")
    result = search_docs(params)
    assert result.result_count > 0
    assert "SCP" in result.results[0].text or "breakglass" in result.results[0].text


def test_search_logging_query(setup_chunks):
    """CloudTrail query returns logging chunk."""
    params = SearchDocsInput(query="CloudTrail organization trail", search_mode="keyword")
    result = search_docs(params)
    assert result.result_count > 0
    assert "CloudTrail" in result.results[0].text


def test_get_page_matches_returns_pdf_word_boxes(mcp_state):
    data_dir, registry = mcp_state
    doc_id = registry.register_document(
        filename="sample.pdf", file_type="pdf", file_size=5, sha256="mcp-page-matches"
    )
    raw_dir = data_dir / "raw" / "default" / doc_id
    raw_dir.mkdir(parents=True)
    pdf_path = raw_dir / "sample.pdf"

    import fitz
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=200)
    page.insert_text((72, 72), "Architecture evidence network")
    pdf.save(pdf_path)
    pdf.close()

    result = tools.get_page_matches(GetPageMatchesInput(doc_id=doc_id, page_number=1, query="architecture network"))

    assert result.doc_id == doc_id
    assert [match.term for match in result.matches] == ["architecture", "network"]
    assert all(0 <= match.x <= 1 for match in result.matches)


def test_get_pipeline_status_reads_persisted_state(mcp_state):
    _, registry = mcp_state
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="mcp-pipeline"
    )
    run_id = registry.create_pipeline_run(doc_id, "job-1")
    registry.update_pipeline_run(run_id, "running")
    registry.add_pipeline_run_event(run_id, {
        "type": "progress",
        "job_id": "job-1",
        "doc_id": doc_id,
        "timestamp": 1,
        "percent": 10,
    })

    result = tools.get_pipeline_status(GetPipelineStatusInput(doc_id=doc_id))

    assert result["doc_id"] == doc_id
    assert result["active_run"]["run_id"] == run_id
    assert result["events"][0]["percent"] == 10
    assert result["runs"][0]["run_id"] == run_id


def test_get_index_status_is_read_only(mcp_state):
    data_dir, registry = mcp_state
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="mcp-index"
    )
    parsed_dir = data_dir / "parsed" / doc_id
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "chunks.json").write_text(json.dumps([{"chunk_id": "c1"}]), encoding="utf-8")

    result = tools.get_index_status(GetIndexStatusInput(doc_id=doc_id))

    assert result["doc_id"] == doc_id
    assert result["chunks_available"] is True
    assert result["chunks_count"] == 1
    assert "adapter" in result


def test_compare_read_tools(mcp_state):
    _, registry = mcp_state
    source_id = registry.register_document(
        filename="example-hld.pdf", file_type="pdf", file_size=5, sha256="mcp-source", document_type="HLD"
    )
    target_id = registry.register_document(
        filename="example-lld.pdf", file_type="pdf", file_size=5, sha256="mcp-target", document_type="LLD"
    )
    run_id = registry.create_compare_run(
        source_doc_id=source_id,
        target_doc_id=target_id,
        requested_mode="auto",
        detected_mode="hld_lld",
    )
    registry.add_compare_findings(run_id, [{
        "type": "coverage_gap",
        "severity": "medium",
        "title": "Missing networking detail",
        "description": "Target lacks source section detail.",
        "source_evidence": [{"doc_id": source_id, "page": 1, "text": "network"}],
        "target_evidence": [],
        "normalized_key": "coverage_gap:network",
    }])
    registry.complete_compare_run(run_id, status="done", summary={"total": 1})

    detected = tools.detect_compare_mode(DetectCompareModeInput(source_doc_id=source_id, target_doc_id=target_id))
    runs = tools.list_compare_runs(ListCompareRunsInput(doc_id=source_id))
    run = tools.get_compare_run(GetCompareRunInput(run_id=run_id))

    assert detected["detected_mode"] == "hld_lld"
    assert runs["runs"][0]["run_id"] == run_id
    assert run["findings"][0]["title"] == "Missing networking detail"


def test_put_cross_search_groups_two_document_results(setup_chunks):
    second_dir = setup_chunks / "parsed" / "doc_other_001"
    second_dir.mkdir(parents=True)
    shutil.copy(Path(__file__).parent / "fixtures" / "chunks.json", second_dir / "chunks.json")

    class Registry:
        def get_document(self, doc_id):
            return {"doc_id": doc_id, "filename": f"{doc_id}.pdf"} if doc_id in {"doc_lz_001", "doc_other_001"} else None

    original = tools._get_registry
    tools._get_registry = lambda: Registry()
    try:
        result = tools.put_cross_search(PutCrossSearchInput(
            source_doc_id="doc_lz_001",
            target_doc_id="doc_other_001",
            query="Transit Gateway",
            search_mode="keyword",
            top_k=8,
        ))
    finally:
        tools._get_registry = original

    assert result["result_count"] > 0
    assert set(result["results_by_doc"]) == {"doc_lz_001", "doc_other_001"}
    assert all(item["doc_id"] == "doc_lz_001" for item in result["results_by_doc"]["doc_lz_001"])
    assert all(item["doc_id"] == "doc_other_001" for item in result["results_by_doc"]["doc_other_001"])


def test_put_compare_creates_persisted_compare_run(mcp_state):
    data_dir, registry = mcp_state
    source_id = registry.register_document(
        filename="source-hld.pdf", file_type="pdf", file_size=5, sha256="put-compare-source", document_type="HLD"
    )
    target_id = registry.register_document(
        filename="target-lld.pdf", file_type="pdf", file_size=5, sha256="put-compare-target", document_type="LLD"
    )
    for doc_id, title, text in [
        (source_id, "Networking", "Transit Gateway CIDR 10.0.0.0/16"),
        (target_id, "Network Detail", "Transit Gateway CIDR 10.1.0.0/16"),
    ]:
        parsed_dir = data_dir / "parsed" / doc_id
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "document_structure.json").write_text(json.dumps({
            "sections": [{"title": title, "section_path": title, "page_start": 1, "page_end": 1}]
        }), encoding="utf-8")
        (parsed_dir / "chunks.json").write_text(json.dumps([{
            "chunk_id": f"{doc_id}-c1",
            "chunk_type": "text_chunk",
            "page_start": 1,
            "page_end": 1,
            "section_path": title,
            "text": text,
        }]), encoding="utf-8")
        (parsed_dir / "entities.json").write_text(json.dumps({"summary": [], "entities": []}), encoding="utf-8")

    result = tools.put_compare(PutCompareInput(source_doc_id=source_id, target_doc_id=target_id, mode="auto"))

    assert result["run"]["source_doc_id"] == source_id
    assert result["run"]["target_doc_id"] == target_id
    assert result["run"]["status"] == "done"
    assert registry.get_compare_run(result["run"]["run_id"]) is not None


def test_unknown_tool_returns_mcp_error():
    response = server.handle_tools_call(99, {"name": "delete_document", "arguments": {}})
    assert response["error"]["code"] == -32601
