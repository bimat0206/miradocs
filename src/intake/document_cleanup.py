"""Document deletion helpers for registry and generated artifacts."""
import shutil
from pathlib import Path
from typing import Callable, Any

from src.config import get_data_dir
from src.intake.document_registry import DocumentRegistry


def _artifact_paths(data_dir: Path, doc: dict) -> list[Path]:
    doc_id = doc["doc_id"]
    return [
        data_dir / "raw" / doc["project"] / doc_id,
        data_dir / "parsed" / doc_id,
        data_dir / "page_images" / doc_id,
        data_dir / "tables" / doc_id,
        data_dir / "figures" / doc_id,
        data_dir / "reports" / doc_id,
    ]


def remove_document(
    doc_id: str,
    registry: DocumentRegistry,
    index_adapter_factory: Callable[[], Any] | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Remove a document from the vector index, artifacts, and registry."""
    doc = registry.get_document(doc_id)
    if not doc:
        return {
            "status": "not_found",
            "removed_paths": [],
            "index_deleted": False,
            "warnings": [],
        }

    warnings = []
    index_deleted = False
    if index_adapter_factory is None:
        from src.indexing.qdrant_adapter import QdrantAdapter
        index_adapter_factory = QdrantAdapter

    try:
        index_deleted = bool(index_adapter_factory().delete_doc(doc_id))
        if not index_deleted:
            warnings.append("No indexed chunks were deleted or the index delete failed.")
    except Exception as e:
        warnings.append(f"Index delete failed: {e}")

    removed_paths = []
    root = data_dir or get_data_dir()
    for path in _artifact_paths(root, doc):
        if path.exists():
            shutil.rmtree(path)
            removed_paths.append(str(path))

    registry.delete_document(doc_id)
    return {
        "status": "deleted",
        "removed_paths": removed_paths,
        "index_deleted": index_deleted,
        "warnings": warnings,
    }
