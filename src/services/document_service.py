"""Document and artifact operations for the API layer."""
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from src.intake.document_cleanup import remove_document
from src.intake.document_registry import DocumentRegistry
from src.intake.file_manager import compute_sha256, get_file_type


ARTIFACTS = {
    "manifest": ("parsed", "doc_manifest.json"),
    "structure": ("parsed", "document_structure.json"),
    "document": ("parsed", "document.json"),
    "markdown": ("parsed", "full_document.md"),
    "entities": ("parsed", "entities.json"),
    "relations": ("parsed", "relations.json"),
    "chunks": ("parsed", "chunks.json"),
    "quality": ("reports", "quality_report.json"),
    "tables": ("tables", "tables_index.json"),
    "figures": ("figures", "figures_index.json"),
}


def pipeline_summary(steps: list[dict]) -> dict:
    total = len(steps)
    completed = sum(1 for step in steps if step.get("status") == "success")
    failed = sum(1 for step in steps if step.get("status") == "failed")
    running = sum(1 for step in steps if step.get("status") == "running")
    percent = int((completed / total) * 100) if total else 0
    return {
        "completed": completed,
        "total": total,
        "failed": failed,
        "running": running,
        "percent": percent,
    }


def list_documents(registry: DocumentRegistry) -> list[dict]:
    raw_docs = registry.list_documents()
    if not raw_docs:
        return []
    doc_ids = [d["doc_id"] for d in raw_docs]
    steps_by_doc = registry.get_pipeline_status_batch(doc_ids)
    return [{**doc, "pipeline": pipeline_summary(steps_by_doc.get(doc["doc_id"], []))} for doc in raw_docs]


def create_document(
    *,
    file_bytes: bytes,
    filename: str,
    project: str,
    document_type: str,
    domain: str,
    sensitivity: str,
    tags: list[str] | None = None,
    registry: DocumentRegistry,
    data_dir: Path,
    # Version control options
    version_group_id: str | None = None,
    version_label: str | None = None,
    version_notes: str = "",
    auto_group: bool = True,
    group_name: str | None = None,
) -> dict:
    sha256 = compute_sha256(file_bytes)
    existing = registry.find_by_hash(sha256)
    if existing:
        existing_ver = registry.get_version_for_doc(existing["doc_id"])
        return {**existing, "duplicate": True, "existing_version": existing_ver}

    doc_id = registry.register_document(
        filename=filename,
        file_type=get_file_type(filename),
        file_size=len(file_bytes),
        sha256=sha256,
        project=project,
        document_type=document_type,
        domain=domain,
        sensitivity=sensitivity,
        tags=tags,
    )
    if not doc_id:
        existing = registry.find_by_hash(sha256)
        if existing:
            existing_ver = registry.get_version_for_doc(existing["doc_id"])
            return {**existing, "duplicate": True, "existing_version": existing_ver}
        return {"duplicate": True}

    raw_dir = data_dir / "raw" / project / doc_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / filename).write_bytes(file_bytes)

    # ── Version group assignment ──────────────────────────────────────────────────
    group = None
    if version_group_id:
        group = registry.get_group(version_group_id, include_versions=False)
    if group is None and auto_group:
        from src.intake.version_matcher import auto_match_group, normalise_filename
        matched_id = auto_match_group(filename, project, registry)
        if matched_id:
            group = registry.get_group(matched_id, include_versions=False)
    if group is None:
        from src.intake.version_matcher import normalise_filename
        base = normalise_filename(filename)
        name = group_name or (base.title() if base else filename)
        group = registry.create_or_find_group(name=name, base_filename=base or filename.lower(), project=project)

    ver = registry.add_version(group["group_id"], doc_id, label=version_label, notes=version_notes)
    registry.set_latest_version(group["group_id"], doc_id)
    # ───────────────────────────────────────────────────────────────────

    doc = registry.get_document(doc_id)
    return {
        **doc,
        "duplicate": False,
        "group_id": group["group_id"],
        "version_id": ver["version_id"] if ver else None,
        "version_label": ver["version_label"] if ver else None,
        "version_number": ver["version_number"] if ver else None,
    }


def delete_document(
    doc_id: str,
    registry: DocumentRegistry,
    data_dir: Path,
    index_adapter_factory,
) -> dict:
    return remove_document(
        doc_id,
        registry,
        index_adapter_factory=index_adapter_factory,
        data_dir=data_dir,
    )


def delete_document_version(
    *,
    group_id: str,
    version_number: int,
    registry: DocumentRegistry,
    data_dir: Path,
    index_adapter_factory,
) -> dict:
    """Remove a version from its group and delete the underlying document + artifacts.

    Order: remove version row first, then delete document (so cleanup cannot leave
    dangling version metadata if it cascades), then recompute the group's latest.
    """
    ver = registry.get_version(group_id, version_number)
    if not ver:
        return {"status": "not_found"}
    doc_id = ver["doc_id"]
    # Remove version row first
    removed = registry.remove_version(group_id, version_number)
    # Delete the underlying document and its artifacts
    cleanup = remove_document(
        doc_id,
        registry,
        index_adapter_factory=index_adapter_factory,
        data_dir=data_dir,
    )
    # Recompute latest among remaining versions
    latest = registry.recompute_latest_version(group_id)
    return {
        "status": "deleted",
        "removed_version": removed,
        "cleanup": cleanup,
        "latest_version": latest,
    }


def artifact_path(doc_id: str, artifact_type: str, data_dir: Path) -> Path | None:
    spec = ARTIFACTS.get(artifact_type)
    if not spec:
        return None
    folder, filename = spec
    return data_dir / folder / doc_id / filename


def read_artifact(doc_id: str, artifact_type: str, data_dir: Path) -> Any:
    path = artifact_path(doc_id, artifact_type, data_dir)
    if not path or not path.exists():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def page_image_path(doc_id: str, page_num: int, data_dir: Path) -> Path:
    return data_dir / "page_images" / doc_id / f"page_{page_num:04d}.png"


def raw_document_path(doc: dict, data_dir: Path) -> Path:
    return data_dir / "raw" / doc["project"] / doc["doc_id"] / doc["filename"]


def page_image_matches(doc: dict, page_num: int, query: str, data_dir: Path) -> dict:
    terms = _query_terms(query)
    response = {
        "doc_id": doc["doc_id"],
        "page": page_num,
        "query": query,
        "page_width": 0,
        "page_height": 0,
        "matches": [],
    }
    if not terms or page_num < 1:
        return response

    pdf_path = _resolve_pdf_path(doc, data_dir)
    if pdf_path is None:
        return response

    import fitz

    pdf = None
    try:
        pdf = fitz.open(str(pdf_path))
        if page_num > len(pdf):
            return response
        page = pdf[page_num - 1]
        rect = page.rect
        response["page_width"] = rect.width
        response["page_height"] = rect.height
        matches = []
        for word in page.get_text("words"):
            x0, y0, x1, y1, text = word[:5]
            normalized = _normalize_term(str(text))
            if normalized in terms and rect.width and rect.height:
                matches.append({
                    "text": str(text),
                    "term": normalized,
                    "x": x0 / rect.width,
                    "y": y0 / rect.height,
                    "width": (x1 - x0) / rect.width,
                    "height": (y1 - y0) / rect.height,
                })
        response["matches"] = matches
    except Exception as exc:
        logger.warning("Failed to extract page matches for %s page %d: %s", doc["doc_id"], page_num, exc)
        return response
    finally:
        if pdf is not None:
            pdf.close()
    return response


def _resolve_pdf_path(doc: dict, data_dir: Path) -> Path | None:
    """Return the PDF file to use for word-bbox extraction.

    PDFs → the original uploaded file.
    DOCX/PPTX → the converted source.pdf produced by office_converter.
    Returns None if no usable PDF exists (LibreOffice unavailable or pre-v1.5.13 doc).
    """
    if doc.get("file_type") == "pdf":
        path = raw_document_path(doc, data_dir)
        return path if path.exists() else None
    converted = data_dir / "converted" / doc["doc_id"] / "source.pdf"
    return converted if converted.exists() else None


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in (_normalize_term(match.group(0)) for match in re.finditer(r"[\w./:-]+", query))
        if len(term) >= 2
    }


def _normalize_term(value: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", value.casefold())
