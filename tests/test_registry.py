"""Tests for document registry and file manager."""
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.intake.document_registry import DocumentRegistry
from src.intake.file_manager import compute_sha256, get_file_type


@pytest.fixture
def registry(tmp_path):
    return DocumentRegistry(db_path=tmp_path / "test.db")


def test_register_document(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="abc123"
    )
    assert doc_id is not None
    assert len(doc_id) == 12


def test_duplicate_detection(registry):
    registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="abc123"
    )
    dup = registry.register_document(
        filename="test2.pdf", file_type="pdf",
        file_size=1024, sha256="abc123"
    )
    assert dup is None


def test_pipeline_steps_created(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="xyz789"
    )
    steps = registry.get_pipeline_status(doc_id)
    assert len(steps) == 9
    assert all(s["status"] == "pending" for s in steps)


def test_update_step(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="step_test"
    )
    registry.update_step(doc_id, "parsed", "running")
    steps = registry.get_pipeline_status(doc_id)
    parsed = next(s for s in steps if s["step_name"] == "parsed")
    assert parsed["status"] == "running"
    assert parsed["started_at"] is not None


def test_update_step_running_clears_previous_completion(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="rerun_test"
    )
    registry.update_step(doc_id, "parsed", "success")
    completed = next(
        s for s in registry.get_pipeline_status(doc_id)
        if s["step_name"] == "parsed"
    )
    assert completed["completed_at"] is not None

    registry.update_step(doc_id, "parsed", "running")

    running = next(
        s for s in registry.get_pipeline_status(doc_id)
        if s["step_name"] == "parsed"
    )
    assert running["status"] == "running"
    assert running["completed_at"] is None


def test_delete_document_removes_document_and_pipeline_steps(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="delete_test"
    )
    registry.update_step(doc_id, "parsed", "success")

    assert registry.delete_document(doc_id) is True
    assert registry.get_document(doc_id) is None
    assert registry.get_pipeline_status(doc_id) == []


def test_pipeline_run_history_records_events(registry):
    doc_id = registry.register_document(
        filename="test.pdf", file_type="pdf",
        file_size=1024, sha256="run_history"
    )
    run_id = registry.create_pipeline_run(doc_id, "run-1")
    registry.add_pipeline_run_event(run_id, {"type": "queued", "timestamp": 1.0})
    registry.update_pipeline_run(run_id, "running")
    registry.add_pipeline_run_event(run_id, {"type": "done", "timestamp": 2.0, "result": {"status": "READY"}})
    registry.update_pipeline_run(run_id, "done", result={"status": "READY"})

    runs = registry.get_pipeline_runs(doc_id)

    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-1"
    assert runs[0]["status"] == "done"
    assert runs[0]["result"] == {"status": "READY"}
    assert [event["event_type"] for event in runs[0]["events"]] == ["queued", "done"]

def test_delete_document_returns_false_for_missing_doc(registry):
    assert registry.delete_document("missing") is False


def test_compute_sha256():
    h = compute_sha256(b"hello world")
    assert len(h) == 64


def test_get_file_type():
    assert get_file_type("doc.pdf") == "pdf"
    assert get_file_type("doc.DOCX") == "docx"
    assert get_file_type("doc.xyz") == "unknown"
