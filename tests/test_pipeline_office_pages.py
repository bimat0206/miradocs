"""Tests for Office document page normalization in the pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.normalization.metadata_builder import build_metadata
from src.services.pipeline_service import _get_pages_text


def test_get_pages_text_uses_converted_pdf_pages_for_office(tmp_path):
    import fitz

    pdf = tmp_path / "converted.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Slide one")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Slide two")
    doc.save(str(pdf))
    doc.close()

    pages = _get_pages_text(
        {"markdown": "combined text", "converted_pdf_path": str(pdf)},
        tmp_path / "deck.pptx",
    )

    assert pages == [
        {"page": 1, "text": "Slide one\n"},
        {"page": 2, "text": "Slide two\n"},
    ]


def test_metadata_uses_page_images_when_parse_page_count_is_zero(monkeypatch, tmp_path):
    parsed_dir = tmp_path / "parsed" / "doc-office"
    monkeypatch.setattr("src.normalization.metadata_builder.get_data_dir", lambda: tmp_path)

    manifest, structure = build_metadata(
        "doc-office",
        {
            "project": "default",
            "filename": "sample.docx",
            "file_type": "docx",
            "sha256": "abc",
        },
        {"page_count": 0, "parser": "docling", "sections": []},
        [
            {"page_number": 1, "image_path": "/tmp/page_0001.png"},
            {"page_number": 2, "image_path": "/tmp/page_0002.png"},
        ],
        [],
        [],
        [],
    )

    assert manifest.page_count == 2
    assert [page.page_number for page in structure.pages] == [1, 2]
    assert (parsed_dir / "doc_manifest.json").exists()
    assert (parsed_dir / "document_structure.json").exists()
