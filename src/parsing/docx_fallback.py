"""DOCX fallback parser using python-docx (placeholder for future use)."""
from pathlib import Path
from typing import Any


def parse_with_docx(file_path: Path) -> dict[str, Any]:
    """Parse DOCX using python-docx. Used only if Docling unavailable."""
    from docx import Document

    doc = Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    markdown = "\n\n".join(paragraphs)

    return {
        "markdown": markdown,
        "doc_dict": {"paragraphs": paragraphs},
        "sections": [],
        "tables": [],
        "figures": [],
        "page_count": 1,
        "parser": "python-docx",
    }
