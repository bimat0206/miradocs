"""Pipeline runner shared by API jobs."""
import concurrent.futures
import time
from pathlib import Path
from typing import Callable, Any

from src.config import get_data_dir
from src.intake.document_registry import DocumentRegistry


PIPELINE_STEPS = [
    ("parsed", "Parse Document"),
    ("page_images", "Page Images"),
    ("tables_extracted", "Tables"),
    ("figures_extracted", "Figures"),
    ("entities_extracted", "Entities"),
    ("metadata_built", "Metadata"),
    ("quality_checked", "Quality Check"),
    ("chunks_created", "Chunks"),
    ("indexed", "Index Document"),
]

PROCESS_STEP_NAMES = [step_name for step_name, _ in PIPELINE_STEPS]


def process_steps_complete(steps: list[dict]) -> bool:
    statuses = {step["step_name"]: step["status"] for step in steps}
    return all(statuses.get(step_name) == "success" for step_name in PROCESS_STEP_NAMES)


def repair_completed_running_steps(
    doc_id: str,
    registry: DocumentRegistry,
    data_dir: Path | None = None,
) -> list[dict]:
    """Mark running steps successful when their expected artifact already exists."""
    root = data_dir or get_data_dir()
    artifact_checks = {
        "parsed": lambda: (root / "parsed" / doc_id / "document.json").exists(),
        "page_images": lambda: any((root / "page_images" / doc_id).glob("page_*.png")),
        "tables_extracted": lambda: (root / "tables" / doc_id / "tables_index.json").exists(),
        "figures_extracted": lambda: (root / "figures" / doc_id / "figures_index.json").exists(),
        "entities_extracted": lambda: (root / "parsed" / doc_id / "entities.json").exists(),
        "metadata_built": lambda: (
            (root / "parsed" / doc_id / "doc_manifest.json").exists()
            and (root / "parsed" / doc_id / "document_structure.json").exists()
        ),
        "quality_checked": lambda: (root / "reports" / doc_id / "quality_report.json").exists(),
        "chunks_created": lambda: (root / "parsed" / doc_id / "chunks.json").exists(),
        "indexed": lambda: (root / "parsed" / doc_id / "index_status.json").exists(),
    }
    repaired: list[dict] = []
    for step in registry.get_pipeline_status(doc_id):
        if step["status"] != "running":
            continue
        has_artifact = artifact_checks.get(step["step_name"])
        if has_artifact and has_artifact():
            registry.update_step(doc_id, step["step_name"], "success")
            repaired.append(step)
    return repaired


def run_pipeline(
    doc_id: str,
    doc: dict,
    registry: DocumentRegistry,
    emit: Callable[[dict[str, Any]], None] | None = None,
    data_dir: Path | None = None,
    index_adapter_factory: Callable[[], Any] | None = None,
) -> dict:
    """Run the document pipeline and emit progress events."""
    from src.parsing.parser_router import parse_document
    from src.extraction.page_image_extractor import extract_page_images
    from src.extraction.table_extractor import extract_tables
    from src.extraction.figure_extractor import extract_figures
    from src.extraction.entity_extractor import extract_entities
    from src.normalization.metadata_builder import build_metadata
    from src.quality.quality_reporter import generate_quality_report
    from src.chunking.chunk_candidate_builder import build_chunks

    root = data_dir or get_data_dir()
    raw_path = root / "raw" / doc["project"] / doc_id / doc["filename"]
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file not found: {raw_path}")

    started = time.monotonic()
    total = len(PIPELINE_STEPS)

    def notify(event: dict[str, Any]):
        if emit:
            emit(event)

    def eta_from_percent(current_pct: int) -> float | None:
        if current_pct <= 0 or current_pct >= 100:
            return None
        elapsed = time.monotonic() - started
        return elapsed * (100 - current_pct) / current_pct

    def run_step(step_name: str, label: str, completed_after: int, func):
        pct_start = int(((completed_after - 1) / total) * 100)
        pct_end = int((completed_after / total) * 100)
        step_started = time.monotonic()

        def soft_pct() -> int:
            step_elapsed = time.monotonic() - step_started
            fraction = 1 - 1 / (1 + step_elapsed / 30)
            return int(pct_start + (pct_end - pct_start) * fraction * 0.9)

        notify({
            "step": step_name,
            "label": label,
            "status": "running",
            "percent": pct_start,
            "elapsed_seconds": time.monotonic() - started,
            "eta_seconds": eta_from_percent(pct_start) if pct_start > 0 else None,
        })
        registry.update_step(doc_id, step_name, "running")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            while True:
                try:
                    result = future.result(timeout=5)
                    break
                except concurrent.futures.TimeoutError:
                    sp = soft_pct()
                    notify({
                        "step": step_name,
                        "label": label,
                        "status": "running",
                        "percent": sp,
                        "elapsed_seconds": time.monotonic() - started,
                        "eta_seconds": eta_from_percent(sp),
                        "message": f"{label} still running",
                    })
        registry.update_step(doc_id, step_name, "success")
        notify({
            "step": step_name,
            "label": label,
            "status": "success",
            "percent": pct_end,
            "elapsed_seconds": time.monotonic() - started,
            "eta_seconds": eta_from_percent(pct_end),
        })
        return result

    try:
        parse_result = run_step(
            "parsed",
            "Parse Document",
            1,
            lambda: parse_document(raw_path, doc_id),
        )
        page_images = run_step(
            "page_images",
            "Page Images",
            2,
            lambda: extract_page_images(raw_path, doc_id),
        )
        tables = run_step(
            "tables_extracted",
            "Tables",
            3,
            lambda: extract_tables(parse_result, doc_id),
        )
        figures = run_step(
            "figures_extracted",
            "Figures",
            4,
            lambda: extract_figures(raw_path, parse_result, doc_id),
        )
        pages_text = _get_pages_text(parse_result, raw_path)
        entities = run_step(
            "entities_extracted",
            "Entities",
            5,
            lambda: extract_entities(pages_text, doc_id),
        )
        _, structure = run_step(
            "metadata_built",
            "Metadata",
            6,
            lambda: build_metadata(
                doc_id, doc, parse_result, page_images, tables, figures, entities
            ),
        )
        report = run_step(
            "quality_checked",
            "Quality Check",
            7,
            lambda: generate_quality_report(
                doc_id, parse_result["page_count"], pages_text,
                page_images, tables, figures, parse_result,
            ),
        )
        sections = [s.model_dump() for s in structure.sections]
        chunks = run_step(
            "chunks_created",
            "Chunks",
            8,
            lambda: build_chunks(doc_id, pages_text, sections, tables, figures, entities, page_images),
        )

        def run_indexing():
            from src.services.index_service import index_document
            nonlocal index_adapter_factory
            if index_adapter_factory is None:
                from src.indexing.qdrant_adapter import QdrantAdapter
                index_adapter_factory = lambda: QdrantAdapter()
            res = index_document(doc_id, root, index_adapter_factory)
            if res.get("status") != "success":
                raise RuntimeError(f"Indexing failed: {res.get('error') or res}")
            return res

        index_result = run_step(
            "indexed",
            "Index Document",
            9,
            run_indexing,
        )

        registry.update_document_status(doc_id, report["status"])
        return {"status": report["status"], "chunks": len(chunks), "indexed": index_result.get("indexed", 0)}
    except Exception as e:
        for step in registry.get_pipeline_status(doc_id):
            if step["status"] == "running":
                registry.update_step(doc_id, step["step_name"], "failed", str(e))
        raise


def _get_pages_text(parse_result: dict, raw_path: Path) -> list[dict]:
    doc_dict = parse_result.get("doc_dict", {})
    pages_text = doc_dict.get("pages_text")
    if pages_text:
        return pages_text

    if raw_path.suffix.lower() == ".pdf":
        import fitz
        doc = fitz.open(str(raw_path))
        result = []
        for i in range(len(doc)):
            result.append({"page": i + 1, "text": doc[i].get_text("text")})
        doc.close()
        return result

    return [{"page": 1, "text": parse_result.get("markdown", "")}]
