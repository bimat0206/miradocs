"""Docling-based document parser."""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_with_docling(file_path: Path) -> dict[str, Any]:
    """Parse document using Docling. Returns structured result."""
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    logger.info(f"Parsing with Docling: {file_path}")
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    accelerator_options=AcceleratorOptions(
                        device=AcceleratorDevice.CPU
                    )
                )
            )
        }
    )
    result = converter.convert(str(file_path))
    doc = result.document

    markdown = doc.export_to_markdown()
    doc_dict = doc.export_to_dict()

    # Extract sections from document structure
    sections = _extract_sections(doc_dict)
    tables = _extract_tables(doc_dict)
    figures = _extract_figures(doc_dict)
    page_count = _get_page_count(doc_dict)

    return {
        "markdown": markdown,
        "doc_dict": doc_dict,
        "sections": sections,
        "tables": tables,
        "figures": figures,
        "page_count": page_count,
        "parser": "docling",
    }


def _extract_sections(doc_dict: dict) -> list[dict]:
    """Extract section hierarchy from Docling output."""
    sections = []
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "heading" in label.lower() or "title" in label.lower():
                    text = item.get("text", "")
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    sections.append({
                        "section_id": f"sec_{i:04d}",
                        "title": text,
                        "page_start": page,
                        "level": _guess_heading_level(label, text),
                    })
    return sections


def _extract_tables(doc_dict: dict) -> list[dict]:
    """Extract table metadata from Docling output."""
    tables = []
    top_level_tables = doc_dict.get("tables", [])
    if isinstance(top_level_tables, list):
        for i, item in enumerate(top_level_tables):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", [{}])
            page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
            data = item.get("data", item.get("table_data", {}))
            tables.append({
                "table_id": f"table_{page:03d}_{i:02d}",
                "page": page,
                "data": data,
                "num_rows": data.get("num_rows", 0) if isinstance(data, dict) else 0,
                "num_cols": data.get("num_cols", 0) if isinstance(data, dict) else 0,
            })
        if tables:
            return tables

    # Docling stores tables in the document structure
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "table" in label.lower():
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    data = item.get("data", item.get("table_data", {}))
                    tables.append({
                        "table_id": f"table_{page:03d}_{len(tables):02d}",
                        "page": page,
                        "data": data,
                        "num_rows": data.get("num_rows", 0) if isinstance(data, dict) else 0,
                        "num_cols": data.get("num_cols", 0) if isinstance(data, dict) else 0,
                    })
    return tables


def _extract_figures(doc_dict: dict) -> list[dict]:
    """Extract figure metadata from Docling output."""
    figures = []
    top_level_pictures = doc_dict.get("pictures", [])
    if isinstance(top_level_pictures, list):
        for i, item in enumerate(top_level_pictures):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", [{}])
            page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
            bbox = prov[0].get("bbox") if prov else None
            figures.append({
                "figure_id": f"figure_{page:03d}_{i:02d}",
                "page": page,
                "caption": item.get("text", ""),
                "bbox": _bbox_to_rect(bbox),
            })
        if figures:
            return figures

    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "figure" in label.lower() or "picture" in label.lower():
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    figures.append({
                        "figure_id": f"figure_{page:03d}_{len(figures):02d}",
                        "page": page,
                        "caption": item.get("text", ""),
                        "bbox": _bbox_to_rect(prov[0].get("bbox")) if prov else None,
                    })
    return figures


def _get_page_count(doc_dict: dict) -> int:
    """Get page count from Docling output."""
    pages = doc_dict.get("pages", {})
    if pages:
        return len(pages)
    # Fallback: find max page number from provenance
    max_page = 0
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                prov = item.get("prov", [{}])
                if prov:
                    p = prov[0].get("page_no", prov[0].get("page", 0))
                    max_page = max(max_page, p)
    return max_page


def _bbox_to_rect(bbox: dict | None) -> list[float] | None:
    if not isinstance(bbox, dict):
        return None
    try:
        return [float(bbox["l"]), float(bbox["b"]), float(bbox["r"]), float(bbox["t"])]
    except (KeyError, TypeError, ValueError):
        return None


def _guess_heading_level(label: str, text: str) -> int:
    """Guess heading level from label or numbering."""
    label_lower = label.lower()
    if "section" in label_lower or "heading" in label_lower:
        # Try to extract level from label like "section_header_level_1"
        for i in range(1, 7):
            if str(i) in label_lower:
                return i
    # Guess from numbering pattern
    if text and text[0].isdigit():
        dots = text.split(" ")[0].count(".")
        return min(dots + 1, 6)
    return 1
