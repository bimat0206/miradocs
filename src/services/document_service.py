"""Document and artifact operations for the API layer."""
import json
import re
from pathlib import Path
from typing import Any

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
) -> dict:
    sha256 = compute_sha256(file_bytes)
    existing = registry.find_by_hash(sha256)
    if existing:
        return {**existing, "duplicate": True}

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
        return {**existing, "duplicate": True} if existing else {"duplicate": True}

    raw_dir = data_dir / "raw" / project / doc_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / filename).write_bytes(file_bytes)
    doc = registry.get_document(doc_id)
    return {**doc, "duplicate": False}


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
    raw_path = raw_document_path(doc, data_dir)
    response = {
        "doc_id": doc["doc_id"],
        "page": page_num,
        "query": query,
        "page_width": 0,
        "page_height": 0,
        "matches": [],
    }
    if not terms or doc.get("file_type") != "pdf" or not raw_path.exists() or page_num < 1:
        return response

    import fitz

    pdf = None
    try:
        pdf = fitz.open(str(raw_path))
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
    except Exception:
        return response
    finally:
        if pdf is not None:
            pdf.close()
    return response


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in (_normalize_term(match.group(0)) for match in re.finditer(r"[\w./:-]+", query))
        if len(term) >= 2
    }


def _normalize_term(value: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", value.casefold())
