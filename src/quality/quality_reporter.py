"""Quality reporter - determines if document is ready for indexing."""
import json
import logging
from pathlib import Path
from typing import Any

from src.config import get_config
from src.intake.file_manager import get_reports_dir

logger = logging.getLogger(__name__)


def generate_quality_report(
    doc_id: str,
    page_count: int,
    pages_text: list[dict],
    page_images: list[dict],
    tables: list[dict],
    figures: list[dict],
    parse_result: dict[str, Any],
) -> dict:
    """Generate quality report and determine indexing readiness."""
    cfg = get_config()
    low_text_threshold = cfg["quality"]["low_text_threshold"]

    # Compute metrics
    pages_with_text = sum(1 for p in pages_text if len(p.get("text", "").strip()) > low_text_threshold)
    low_text_pages = [p["page"] for p in pages_text if len(p.get("text", "").strip()) <= low_text_threshold]
    empty_pages = [p["page"] for p in pages_text if not p.get("text", "").strip()]
    images_generated = len(page_images)
    tables_detected = len(tables)
    figures_detected = len(figures)

    # Warnings
    warnings = []
    for pg in low_text_pages:
        if pg not in empty_pages:
            warnings.append({"level": "warning", "page": pg, "message": "Low text content - may need OCR or manual review"})
    for pg in empty_pages:
        warnings.append({"level": "warning", "page": pg, "message": "Empty page - no text extracted"})
    if images_generated < page_count:
        warnings.append({"level": "warning", "page": None, "message": f"Missing page images: {page_count - images_generated} pages"})
    for t in tables:
        if t.get("status") == "no_grid":
            warnings.append({"level": "warning", "page": t.get("page"), "message": f"Table {t['table_id']} could not be parsed into grid"})

    # Determine status
    status = _determine_status(page_count, pages_with_text, images_generated, warnings)

    report = {
        "doc_id": doc_id,
        "status": status,
        "summary": {
            "page_count": page_count,
            "pages_with_text": pages_with_text,
            "low_text_pages": low_text_pages,
            "empty_pages": empty_pages,
            "page_images_generated": images_generated,
            "tables_detected": tables_detected,
            "figures_detected": figures_detected,
            "ocr_pages": low_text_pages,
            "unmapped_pages": [],
        },
        "warnings": warnings,
    }

    # Save report
    output_dir = get_reports_dir(doc_id)
    (output_dir / "quality_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    logger.info(f"Quality report for {doc_id}: {status}")
    return report


def _determine_status(page_count: int, pages_with_text: int, images_generated: int, warnings: list) -> str:
    """Determine readiness status."""
    if page_count == 0:
        return "NOT_READY"
    text_ratio = pages_with_text / page_count if page_count else 0
    image_ratio = images_generated / page_count if page_count else 0

    if text_ratio < 0.5:
        return "NOT_READY"
    if text_ratio < 0.8 or image_ratio < 0.9 or len(warnings) > 10:
        return "READY_WITH_WARNINGS"
    return "READY"
