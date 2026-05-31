"""Parser router - tries Docling first, falls back to format-specific parsers."""
import json
import logging
from pathlib import Path
from typing import Any

from src.intake.file_manager import get_parsed_dir

logger = logging.getLogger(__name__)


def parse_document(file_path: Path, doc_id: str) -> dict[str, Any]:
    """Parse document using best available parser. Saves outputs to parsed dir."""
    file_type = file_path.suffix.lower()

    if file_type == ".pdf":
        result = _parse_pdf(file_path)
    elif file_type == ".docx":
        result = _parse_docx(file_path)
    elif file_type in (".pptx", ".xlsx"):
        result = _parse_with_docling_or_fail(file_path)
    elif file_type in (".md", ".txt"):
        result = _parse_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    # Save outputs
    parsed_dir = get_parsed_dir(doc_id)
    (parsed_dir / "full_document.md").write_text(result["markdown"], encoding="utf-8")

    # Save doc_dict as JSON (exclude markdown to avoid duplication)
    export = {k: v for k, v in result.items() if k != "markdown"}
    (parsed_dir / "document.json").write_text(
        json.dumps(export, default=str, indent=2), encoding="utf-8"
    )

    return result


def _parse_pdf(file_path: Path) -> dict[str, Any]:
    """Try Docling first, fall back to PyMuPDF."""
    try:
        from src.parsing.docling_parser import parse_with_docling
        return parse_with_docling(file_path)
    except Exception as e:
        logger.warning(f"Docling failed ({e}), falling back to PyMuPDF")
        from src.parsing.pdf_fallback import parse_with_pymupdf
        return parse_with_pymupdf(file_path)


def _parse_docx(file_path: Path) -> dict[str, Any]:
    """Try Docling first, fall back to python-docx."""
    try:
        from src.parsing.docling_parser import parse_with_docling
        return parse_with_docling(file_path)
    except Exception as e:
        logger.warning(f"Docling failed ({e}), falling back to python-docx")
        from src.parsing.docx_fallback import parse_with_docx
        return parse_with_docx(file_path)


def _parse_with_docling_or_fail(file_path: Path) -> dict[str, Any]:
    """Use Docling for formats without a local fallback."""
    try:
        from src.parsing.docling_parser import parse_with_docling
        return parse_with_docling(file_path)
    except Exception as e:
        raise RuntimeError(f"Docling required for {file_path.suffix} but failed: {e}")


def _parse_text(file_path: Path) -> dict[str, Any]:
    """Simple text/markdown file parsing."""
    text = file_path.read_text(encoding="utf-8")
    return {
        "markdown": text,
        "doc_dict": {"raw_text": text},
        "sections": [],
        "tables": [],
        "figures": [],
        "page_count": 1,
        "parser": "text",
    }
