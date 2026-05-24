"""Tests for deleting registered documents and their artifacts."""
from pathlib import Path

from src.intake.document_cleanup import remove_document
from src.intake.document_registry import DocumentRegistry


class FakeIndexAdapter:
    def __init__(self):
        self.deleted_doc_ids = []

    def delete_doc(self, doc_id: str) -> bool:
        self.deleted_doc_ids.append(doc_id)
        return True


def test_remove_document_deletes_artifacts_registry_rows_and_index(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setattr("src.intake.document_cleanup.get_data_dir", lambda: data_dir)
    registry = DocumentRegistry(db_path=tmp_path / "registry.db")
    doc_id = registry.register_document(
        filename="sample.pdf",
        file_type="pdf",
        file_size=100,
        sha256="cleanup_doc",
        project="default",
    )
    for artifact_dir in (
        data_dir / "raw" / "default" / doc_id,
        data_dir / "parsed" / doc_id,
        data_dir / "page_images" / doc_id,
        data_dir / "tables" / doc_id,
        data_dir / "figures" / doc_id,
        data_dir / "reports" / doc_id,
    ):
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "artifact.txt").write_text("data")
    adapter = FakeIndexAdapter()

    result = remove_document(
        doc_id,
        registry,
        index_adapter_factory=lambda: adapter,
    )

    assert result["status"] == "deleted"
    assert result["index_deleted"] is True
    assert result["warnings"] == []
    assert adapter.deleted_doc_ids == [doc_id]
    assert registry.get_document(doc_id) is None
    for path in result["removed_paths"]:
        assert not Path(path).exists()


def test_remove_document_returns_not_found_for_missing_document(tmp_path):
    registry = DocumentRegistry(db_path=tmp_path / "registry.db")

    result = remove_document("missing", registry)

    assert result == {
        "status": "not_found",
        "removed_paths": [],
        "index_deleted": False,
        "warnings": [],
    }
