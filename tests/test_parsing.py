"""Tests for parsing modules."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsing.pdf_fallback import parse_with_pymupdf, _size_to_level


def test_size_to_level():
    assert _size_to_level(24) == 1
    assert _size_to_level(20) == 2
    assert _size_to_level(16) == 3
    assert _size_to_level(12) == 4


def test_parse_text_file(tmp_path):
    """Test text file parsing via router."""
    from src.parsing.parser_router import _parse_text
    txt = tmp_path / "test.txt"
    txt.write_text("Hello world\n\nSection 1\nContent here")
    result = _parse_text(txt)
    assert result["parser"] == "text"
    assert "Hello world" in result["markdown"]
    assert result["page_count"] == 1


def test_pymupdf_fallback_with_sample(tmp_path):
    """Test PyMuPDF parser with a minimal PDF created by fitz."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Test Document Title", fontsize=20)
    page.insert_text((72, 120), "This is body text content.", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Page 2 heading", fontsize=16)
    page2.insert_text((72, 120), "More content here.", fontsize=11)
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()

    result = parse_with_pymupdf(pdf_path)
    assert result["parser"] == "pymupdf"
    assert result["page_count"] == 2
    assert "Test Document Title" in result["markdown"]
    assert len(result["sections"]) >= 1
