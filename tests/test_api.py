"""Tests for the FastAPI document workspace API."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.intake.document_registry import DocumentRegistry


class FakeIndexAdapter:
    def __init__(self):
        self.deleted = []
        self.search_filters = []

    def delete_doc(self, doc_id: str) -> bool:
        self.deleted.append(doc_id)
        return True

    def index_chunks(self, chunks: list[dict], doc_id: str) -> dict:
        return {"status": "success", "indexed": len(chunks)}

    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        self.search_filters.append(filters)
        f_doc_id = filters["doc_id"] if filters else "default_doc"
        if isinstance(f_doc_id, list):
            f_doc_id = f_doc_id[0] if f_doc_id else "default_doc"
        return [
            {
                "score": 0.91,
                "chunk_id": "chunk_001",
                "doc_id": f_doc_id,
                "chunk_type": "text_chunk",
                "page_start": 1,
                "section_path": "Overview",
                "text": f"result for {query}",
                "source_refs": {},
            }
        ]

    def get_status(self) -> dict:
        return {"status": "green", "collection": "test", "points_count": 3}


def _client(tmp_path):
    data_dir = tmp_path / "data"
    registry = DocumentRegistry(db_path=tmp_path / "registry.db")
    index_adapter = FakeIndexAdapter()
    app = create_app(
        registry=registry,
        data_dir=data_dir,
        index_adapter_factory=lambda: index_adapter,
    )
    return TestClient(app), registry, data_dir, index_adapter


def test_health_reports_local_dependencies(tmp_path):
    client, _, data_dir, _ = _client(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_dir"] == str(data_dir)


def test_document_upload_creates_raw_file_and_registry_row(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)

    response = client.post(
        "/api/documents",
        data={
            "project": "default",
            "document_type": "HLD",
            "domain": "Networking",
            "sensitivity": "Internal",
            "tags": json.dumps(["landing-zone", "aws", "networking"]),
        },
        files={"file": ("sample.txt", b"hello architecture", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    doc_id = body["doc_id"]
    assert registry.get_document(doc_id)["filename"] == "sample.txt"
    assert body["tags"] == ["landing-zone", "aws", "networking"]
    assert registry.get_document(doc_id)["tags"] == ["landing-zone", "aws", "networking"]
    assert (data_dir / "raw" / "default" / doc_id / "sample.txt").read_bytes() == b"hello architecture"


def test_update_document_tags_cleans_and_persists_tags(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="tags"
    )

    response = client.patch(
        f"/api/documents/{doc_id}/tags",
        json={"tags": [" aws ", "AWS", "", "networking", "landing-zone", "security", "extra"]},
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["aws", "networking", "landing-zone", "security", "extra"]
    assert registry.get_document(doc_id)["tags"] == ["aws", "networking", "landing-zone", "security", "extra"]


def test_delete_document_removes_registry_artifacts_and_index(tmp_path):
    client, registry, data_dir, index_adapter = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="delete-me"
    )
    artifact_dir = data_dir / "parsed" / doc_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "document.json").write_text("{}")

    response = client.delete(f"/api/documents/{doc_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert registry.get_document(doc_id) is None
    assert not artifact_dir.exists()
    assert index_adapter.deleted == [doc_id]


def test_artifact_endpoint_returns_json_artifacts(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="artifact"
    )
    parsed_dir = data_dir / "parsed" / doc_id
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "chunks.json").write_text(json.dumps([{"chunk_id": "c1"}]))

    response = client.get(f"/api/documents/{doc_id}/artifacts/chunks")

    assert response.status_code == 200
    assert response.json() == [{"chunk_id": "c1"}]


def test_artifact_file_endpoint_returns_table_preview(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="artifact-file"
    )
    tables_dir = data_dir / "tables" / doc_id
    tables_dir.mkdir(parents=True)
    (tables_dir / "table_001.md").write_text("| A |\n|---|")

    response = client.get(f"/api/documents/{doc_id}/artifacts/tables/table_001.md")

    assert response.status_code == 200
    assert "| A |" in response.text


def test_page_matches_returns_pdf_word_boxes(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.pdf", file_type="pdf", file_size=5, sha256="page-matches"
    )
    raw_dir = data_dir / "raw" / "default" / doc_id
    raw_dir.mkdir(parents=True)
    pdf_path = raw_dir / "sample.pdf"

    import fitz
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=200)
    page.insert_text((72, 72), "Architecture evidence and network design")
    pdf.save(pdf_path)
    pdf.close()

    response = client.get(f"/api/documents/{doc_id}/pages/1/matches", params={"query": "architecture network"})

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == doc_id
    assert body["page"] == 1
    assert body["page_width"] == 300
    assert body["page_height"] == 200
    assert [match["term"] for match in body["matches"]] == ["architecture", "network"]
    for match in body["matches"]:
        assert 0 <= match["x"] <= 1
        assert 0 <= match["y"] <= 1
        assert match["width"] > 0
        assert match["height"] > 0


def test_page_matches_empty_query_returns_no_matches(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.pdf", file_type="pdf", file_size=5, sha256="empty-page-matches"
    )

    response = client.get(f"/api/documents/{doc_id}/pages/1/matches", params={"query": ""})

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_page_matches_non_pdf_returns_no_matches(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="non-pdf-page-matches"
    )
    raw_dir = data_dir / "raw" / "default" / doc_id
    raw_dir.mkdir(parents=True)
    (raw_dir / "sample.txt").write_text("Architecture evidence", encoding="utf-8")

    response = client.get(f"/api/documents/{doc_id}/pages/1/matches", params={"query": "architecture"})

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_page_matches_missing_document_returns_404(tmp_path):
    client, _, _, _ = _client(tmp_path)

    response = client.get("/api/documents/missing/pages/1/matches", params={"query": "architecture"})

    assert response.status_code == 404


def test_page_matches_missing_page_returns_no_matches(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.pdf", file_type="pdf", file_size=5, sha256="missing-page-matches"
    )
    raw_dir = data_dir / "raw" / "default" / doc_id
    raw_dir.mkdir(parents=True)
    pdf_path = raw_dir / "sample.pdf"

    import fitz
    pdf = fitz.open()
    pdf.new_page(width=300, height=200)
    pdf.save(pdf_path)
    pdf.close()

    response = client.get(f"/api/documents/{doc_id}/pages/2/matches", params={"query": "architecture"})

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_search_filters_by_document_id(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="search"
    )
    (data_dir / "parsed" / doc_id).mkdir(parents=True)

    response = client.post("/api/search", json={"doc_id": doc_id, "query": "vpc", "hybrid": False})

    assert response.status_code == 200
    assert response.json()["results"][0]["doc_id"] == doc_id


def test_search_filters_by_multiple_document_ids(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id1 = registry.register_document(
        filename="sample1.txt", file_type="text", file_size=5, sha256="search1"
    )
    doc_id2 = registry.register_document(
        filename="sample2.txt", file_type="text", file_size=5, sha256="search2"
    )
    (data_dir / "parsed" / doc_id1).mkdir(parents=True)
    (data_dir / "parsed" / doc_id2).mkdir(parents=True)

    response = client.post("/api/search", json={"doc_id": [doc_id1, doc_id2], "query": "vpc", "hybrid": False})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["doc_id"] == doc_id1


def test_search_accepts_all_uploaded_document_ids_in_one_request(tmp_path):
    client, registry, data_dir, index_adapter = _client(tmp_path)
    doc_ids = [
        registry.register_document(filename="a.txt", file_type="text", file_size=5, sha256="all-a"),
        registry.register_document(filename="b.txt", file_type="text", file_size=5, sha256="all-b"),
        registry.register_document(filename="c.txt", file_type="text", file_size=5, sha256="all-c"),
    ]
    for doc_id in doc_ids:
        (data_dir / "parsed" / doc_id).mkdir(parents=True)

    response = client.post("/api/search", json={"doc_id": doc_ids, "query": "firewall", "hybrid": False})

    assert response.status_code == 200
    assert index_adapter.search_filters[-1] == {"doc_id": doc_ids}


def _write_compare_artifacts(data_dir: Path, doc_id: str, *, sections: list[dict], chunks: list[dict], entities: list[dict], table_text: str | None = None):
    parsed_dir = data_dir / "parsed" / doc_id
    parsed_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.joinpath("document_structure.json").write_text(json.dumps({"sections": sections, "pages": []}))
    parsed_dir.joinpath("chunks.json").write_text(json.dumps(chunks))
    parsed_dir.joinpath("entities.json").write_text(json.dumps({"summary": entities, "entities": entities}))
    if table_text is not None:
        tables_dir = data_dir / "tables" / doc_id
        tables_dir.mkdir(parents=True, exist_ok=True)
        tables_dir.joinpath("table_001.md").write_text(table_text)
        tables_dir.joinpath("tables_index.json").write_text(json.dumps([
            {"table_id": "table_001", "page": 2, "file_md": "table_001.md", "rows": 2, "cols": 2}
        ]))


def test_compare_detect_mode_for_hld_lld_pair(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    hld_id = registry.register_document(
        filename="landing-zone-hld.pdf", file_type="pdf", file_size=5, sha256="compare-hld", document_type="HLD"
    )
    lld_id = registry.register_document(
        filename="landing-zone-lld.pdf", file_type="pdf", file_size=5, sha256="compare-lld", document_type="LLD"
    )

    response = client.post("/api/compare/detect-mode", json={"source_doc_id": hld_id, "target_doc_id": lld_id})

    assert response.status_code == 200
    body = response.json()
    assert body["detected_mode"] == "hld_lld"
    assert body["confidence"] >= 0.8


def test_compare_run_finds_deterministic_gaps_and_persists(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    hld_id = registry.register_document(
        filename="landing-zone-hld.pdf", file_type="pdf", file_size=5, sha256="run-hld", document_type="HLD"
    )
    lld_id = registry.register_document(
        filename="landing-zone-lld.pdf", file_type="pdf", file_size=5, sha256="run-lld", document_type="LLD"
    )
    _write_compare_artifacts(
        data_dir,
        hld_id,
        sections=[
            {"title": "Networking", "page_start": 1, "page_end": 2},
            {"title": "Backup and Recovery", "page_start": 3, "page_end": 4},
        ],
        chunks=[
            {"chunk_id": "h1", "page_start": 1, "section_path": "Networking", "text": "Production VPC CIDR 10.20.0.0/16 uses AWS Network Firewall in ap-southeast-1."},
            {"chunk_id": "h2", "page_start": 3, "section_path": "Backup and Recovery", "text": "Daily backups are required."},
        ],
        entities=[
            {"type": "aws_service", "value": "AWS Network Firewall", "page": 1},
            {"type": "cidr", "value": "10.20.0.0/16", "page": 1},
        ],
        table_text="| Component | Requirement |\n|---|---|\n| Logs | Retain 365 days |",
    )
    _write_compare_artifacts(
        data_dir,
        lld_id,
        sections=[
            {"title": "Networking", "page_start": 1, "page_end": 2},
        ],
        chunks=[
            {"chunk_id": "l1", "page_start": 1, "section_path": "Networking", "text": "Production VPC CIDR 10.21.0.0/16 is deployed in ap-southeast-1."},
        ],
        entities=[
            {"type": "cidr", "value": "10.21.0.0/16", "page": 1},
        ],
        table_text="| Component | Requirement |\n|---|---|\n| Logs | Retain 90 days |",
    )

    response = client.post("/api/compare/run", json={"source_doc_id": hld_id, "target_doc_id": lld_id, "mode": "auto"})

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["detected_mode"] == "hld_lld"
    finding_types = {finding["type"] for finding in body["findings"]}
    assert {"missing_section", "missing_entity", "value_mismatch", "table_mismatch"}.issubset(finding_types)
    assert body["summary"]["total"] == len(body["findings"])
    assert body["findings"][0]["llm_status"] == "not_requested"

    run_id = body["run"]["run_id"]
    fetched = client.get(f"/api/compare/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run"]["run_id"] == run_id

    history = client.get(f"/api/documents/{hld_id}/compare/runs")
    assert history.status_code == 200
    assert history.json()["runs"][0]["run_id"] == run_id


def test_compare_evidence_uses_occurrence_page_not_summary_default(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    source_id = registry.register_document(
        filename="source-hld.pdf", file_type="pdf", file_size=5, sha256="evidence-source", document_type="HLD"
    )
    target_id = registry.register_document(
        filename="target-lld.pdf", file_type="pdf", file_size=5, sha256="evidence-target", document_type="LLD"
    )
    _write_compare_artifacts(
        data_dir,
        source_id,
        sections=[{"title": "Security"}],
        chunks=[
            {"chunk_id": "s1", "page_start": 7, "section_path": "Security", "text": "Security uses AWS WAF on the application edge."},
        ],
        entities=[
            {"type": "aws_service", "value": "AWS WAF", "page": 7},
        ],
    )
    (data_dir / "parsed" / source_id / "entities.json").write_text(json.dumps({
        "summary": [{"type": "aws_service", "value": "AWS WAF", "count": 1}],
        "entities": [{"type": "aws_service", "value": "AWS WAF", "page": 7}],
    }))
    _write_compare_artifacts(
        data_dir,
        target_id,
        sections=[{"title": "Security"}],
        chunks=[
            {"chunk_id": "t1", "page_start": 2, "section_path": "Security", "text": "Security controls are defined."},
        ],
        entities=[],
    )

    response = client.post("/api/compare/run", json={"source_doc_id": source_id, "target_doc_id": target_id, "mode": "auto"})

    assert response.status_code == 200
    finding = next(item for item in response.json()["findings"] if item["type"] == "missing_entity")
    assert finding["source_evidence"][0]["page"] == 7
    assert "AWS WAF" in finding["source_evidence"][0]["text"]


def test_compare_missing_section_evidence_infers_page_from_chunk(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    source_id = registry.register_document(
        filename="source-hld.pdf", file_type="pdf", file_size=5, sha256="section-source", document_type="HLD"
    )
    target_id = registry.register_document(
        filename="target-lld.pdf", file_type="pdf", file_size=5, sha256="section-target", document_type="LLD"
    )
    _write_compare_artifacts(
        data_dir,
        source_id,
        sections=[{"title": "Backup and Recovery"}],
        chunks=[
            {"chunk_id": "s1", "page_start": 9, "section_path": "Backup and Recovery", "text": "Backup and Recovery requires immutable vault retention."},
        ],
        entities=[],
    )
    _write_compare_artifacts(
        data_dir,
        target_id,
        sections=[{"title": "Networking"}],
        chunks=[
            {"chunk_id": "t1", "page_start": 3, "section_path": "Networking", "text": "Networking details."},
        ],
        entities=[],
    )

    response = client.post("/api/compare/run", json={"source_doc_id": source_id, "target_doc_id": target_id, "mode": "auto"})

    assert response.status_code == 200
    finding = next(item for item in response.json()["findings"] if item["type"] == "missing_section")
    assert finding["source_evidence"][0]["page"] == 9
    assert "immutable vault" in finding["source_evidence"][0]["text"]


def test_compare_run_rejects_same_document(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.pdf", file_type="pdf", file_size=5, sha256="same-compare"
    )

    response = client.post("/api/compare/run", json={"source_doc_id": doc_id, "target_doc_id": doc_id, "mode": "auto"})

    assert response.status_code == 400


def test_pipeline_status_repairs_running_step_when_artifact_exists(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="repair-running"
    )
    parsed_dir = data_dir / "parsed" / doc_id
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "document.json").write_text("{}")
    registry.update_step(doc_id, "parsed", "running")

    response = client.get(f"/api/documents/{doc_id}/pipeline")

    assert response.status_code == 200
    parsed = next(step for step in response.json()["steps"] if step["step_name"] == "parsed")
    assert parsed["status"] == "success"


def test_active_pipeline_returns_active_job_steps_and_events(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="active-run"
    )
    jobs = client.app.state.jobs
    job = jobs.create(doc_id)
    run_id = registry.create_pipeline_run(doc_id, job.job_id)
    for event in job.events:
        registry.add_pipeline_run_event(run_id, event)
    running = jobs.emit(job.job_id, "running", {"message": "started"})
    progress = jobs.emit(job.job_id, "progress", {"step": "parsed", "percent": 7})
    registry.add_pipeline_run_event(run_id, running)
    registry.add_pipeline_run_event(run_id, progress)
    registry.update_pipeline_run(run_id, "running")
    registry.update_step(doc_id, "parsed", "running")

    response = client.get(f"/api/documents/{doc_id}/pipeline/active")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job.job_id
    assert body["status"] == "running"
    assert body["run"]["run_id"] == run_id
    assert [event["type"] for event in body["events"]] == ["queued", "running", "progress"]
    assert body["events"][-1]["percent"] == 7
    parsed = next(step for step in body["steps"] if step["step_name"] == "parsed")
    assert parsed["status"] == "running"


def test_active_pipeline_omits_terminal_job(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="terminal-run"
    )
    jobs = client.app.state.jobs
    job = jobs.create(doc_id)
    run_id = registry.create_pipeline_run(doc_id, job.job_id)
    for event in job.events:
        registry.add_pipeline_run_event(run_id, event)
    done = jobs.emit(job.job_id, "done", {"message": "complete"})
    registry.add_pipeline_run_event(run_id, done)
    registry.update_pipeline_run(run_id, "done")

    response = client.get(f"/api/documents/{doc_id}/pipeline/active")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] is None
    assert body["status"] is None
    assert body["events"] == []
    assert body["run"] is None


def test_active_pipeline_falls_back_to_latest_persisted_running_run(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="persisted-run"
    )
    run_id = registry.create_pipeline_run(doc_id, "persisted-job")
    registry.update_pipeline_run(run_id, "running")
    registry.add_pipeline_run_event(run_id, {
        "type": "queued",
        "job_id": "persisted-job",
        "doc_id": doc_id,
        "timestamp": 1,
        "message": "queued",
    })
    registry.add_pipeline_run_event(run_id, {
        "type": "progress",
        "job_id": "persisted-job",
        "doc_id": doc_id,
        "timestamp": 2,
        "step": "parsed",
        "percent": 13,
    })

    response = client.get(f"/api/documents/{doc_id}/pipeline/active")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] is None
    assert body["status"] == "running"
    assert body["run"]["run_id"] == run_id
    assert [event["type"] for event in body["events"]] == ["queued", "progress"]
    assert body["events"][-1]["percent"] == 13


def test_completed_pipeline_run_returns_noop_job(tmp_path):
    client, registry, _, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="complete-run"
    )
    for step_name in [
        "parsed",
        "page_images",
        "tables_extracted",
        "figures_extracted",
        "entities_extracted",
        "metadata_built",
        "quality_checked",
        "chunks_created",
        "indexed",
    ]:
        registry.update_step(doc_id, step_name, "success")

    response = client.post(f"/api/documents/{doc_id}/pipeline/run")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"

    history = client.get(f"/api/documents/{doc_id}/pipeline/runs")
    assert history.status_code == 200
    runs = history.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "done"
    assert [event["event_type"] for event in runs[0]["events"]] == ["queued", "done"]


def test_index_status_reports_chunks_and_adapter_status(tmp_path):
    client, registry, data_dir, _ = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="index-status"
    )
    parsed_dir = data_dir / "parsed" / doc_id
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "chunks.json").write_text(json.dumps([
        {"chunk_id": "c1", "text": "one"},
        {"chunk_id": "c2", "text": "two"},
    ]))
    registry.update_step(doc_id, "indexed", "success")

    response = client.get(f"/api/documents/{doc_id}/index/status")

    assert response.status_code == 200
    body = response.json()
    assert body["chunks_available"] is True
    assert body["chunks_count"] == 2
    assert body["indexed"] is True
    assert body["adapter"]["collection"] == "test"


def test_update_endpoint_spawns_python_launcher(tmp_path, monkeypatch):
    client, _, _, _ = _client(tmp_path)
    popen_calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            popen_calls.append((args, kwargs))

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    response = client.post("/api/update")

    assert response.status_code == 200
    assert response.json()["status"] == "updating"
    assert len(popen_calls) == 1
    args, kwargs = popen_calls[0]
    assert args[1].endswith("start.py")
    assert args[2] == "update"
    assert kwargs["start_new_session"] is True


def test_pipeline_run_only_indexes_when_steps_1_8_successful(tmp_path):
    client, registry, data_dir, index_adapter = _client(tmp_path)
    doc_id = registry.register_document(
        filename="sample.txt", file_type="text", file_size=5, sha256="index-only"
    )
    for step_name in [
        "parsed",
        "page_images",
        "tables_extracted",
        "figures_extracted",
        "entities_extracted",
        "metadata_built",
        "quality_checked",
        "chunks_created",
    ]:
        registry.update_step(doc_id, step_name, "success")

    chunks_path = data_dir / "parsed" / doc_id / "chunks.json"
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text("[]", encoding="utf-8")

    response = client.post(f"/api/documents/{doc_id}/pipeline/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"queued", "running"}

    import time
    for _ in range(20):
        time.sleep(0.1)
        steps = registry.get_pipeline_status(doc_id)
        idx_step = next(s for s in steps if s["step_name"] == "indexed")
        if idx_step["status"] == "success":
            break

    steps = registry.get_pipeline_status(doc_id)
    idx_step = next(s for s in steps if s["step_name"] == "indexed")
    assert idx_step["status"] == "success"
