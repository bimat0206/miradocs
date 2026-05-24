"""PyMuPDF-based fallback parser for when Docling fails."""
import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def parse_with_pymupdf(file_path: Path) -> dict[str, Any]:
    """Parse PDF using PyMuPDF as fallback. Returns structured result."""
    logger.info(f"Parsing with PyMuPDF fallback: {file_path}")
    doc = fitz.open(str(file_path))

    pages_text = []
    sections = []
    all_text_parts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pages_text.append({"page": page_num + 1, "text": text})
        all_text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

        # Extract headings via font size heuristics
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("size", 0) >= 14:
                            sections.append({
                                "section_id": f"sec_{len(sections):04d}",
                                "title": span["text"].strip(),
                                "page_start": page_num + 1,
                                "level": _size_to_level(span["size"]),
                            })

    doc.close()
    markdown = "\n\n".join(all_text_parts)

    return {
        "markdown": markdown,
        "doc_dict": {"pages_text": pages_text},
        "sections": _deduplicate_sections(sections),
        "tables": [],
        "figures": [],
        "page_count": len(pages_text),
        "parser": "pymupdf",
    }


def _size_to_level(size: float) -> int:
    if size >= 24:
        return 1
    if size >= 20:
        return 2
    if size >= 16:
        return 3
    return 4


def _deduplicate_sections(sections: list[dict]) -> list[dict]:
    """Remove duplicate headings (same title on same page)."""
    seen = set()
    result = []
    for s in sections:
        key = (s["title"], s["page_start"])
        if key not in seen and s["title"].strip():
            seen.add(key)
            result.append(s)
    return result
