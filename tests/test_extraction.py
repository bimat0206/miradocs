"""Tests for table and figure extraction artifacts."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extraction.figure_extractor import extract_figures
from src.extraction.page_image_extractor import extract_page_images
from src.parsing.office_converter import convert_office_to_pdf
from src.extraction.table_extractor import extract_tables


def _mkdir_return(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_extract_tables_writes_empty_index(monkeypatch, tmp_path):
    tables_dir = tmp_path / "tables" / "doc-empty"
    monkeypatch.setattr(
        "src.extraction.table_extractor.get_tables_dir",
        lambda doc_id: _mkdir_return(tables_dir),
    )

    result = extract_tables({"tables": []}, "doc-empty")

    assert result == []
    assert json.loads((tables_dir / "tables_index.json").read_text()) == []


def test_extract_figures_writes_empty_index_without_opening_pdf(monkeypatch, tmp_path):
    figures_dir = tmp_path / "figures" / "doc-empty"
    monkeypatch.setattr(
        "src.extraction.figure_extractor.get_figures_dir",
        lambda doc_id: _mkdir_return(figures_dir),
    )

    result = extract_figures(Path("missing.pdf"), {"figures": []}, "doc-empty")

    assert result == []
    assert json.loads((figures_dir / "figures_index.json").read_text()) == []


def test_extract_page_images_skips_non_pdf_without_render_source(tmp_path):
    result = extract_page_images(tmp_path / "sample.docx", "doc-docx")

    assert result == []


def test_convert_office_to_pdf_uses_soffice(monkeypatch, tmp_path):
    source = tmp_path / "sample.docx"
    source.write_bytes(b"docx")
    output_root = tmp_path / "converted"
    soffice = "/usr/bin/soffice"
    calls = []

    monkeypatch.setattr("src.parsing.office_converter.shutil.which", lambda _name: soffice)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        produced = output_root / "doc-1" / "sample.pdf"
        produced.parent.mkdir(parents=True, exist_ok=True)
        produced.write_bytes(b"%PDF-1.4\n")
        return object()

    monkeypatch.setattr("src.parsing.office_converter.subprocess.run", fake_run)

    result = convert_office_to_pdf(source, "doc-1", output_root)

    assert result == output_root / "doc-1" / "source.pdf"
    assert result.read_bytes() == b"%PDF-1.4\n"
    assert calls[0][0] == [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_root / "doc-1"),
        str(source),
    ]


def test_extract_page_images_renders_office_from_converted_pdf(monkeypatch, tmp_path):
    import fitz

    image_dir = tmp_path / "page_images" / "doc-office"
    monkeypatch.setattr(
        "src.extraction.page_image_extractor.get_page_images_dir",
        lambda doc_id: _mkdir_return(image_dir),
    )
    monkeypatch.setattr(
        "src.extraction.page_image_extractor.get_config",
        lambda: {"parsing": {"page_image_dpi": 72, "page_image_workers": 1}},
    )

    pdf = tmp_path / "converted.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()

    result = extract_page_images(
        tmp_path / "sample.docx",
        "doc-office",
        render_source_path=pdf,
    )

    assert [page["page_number"] for page in result] == [1, 2]
    assert (image_dir / "page_0001.png").exists()
    assert (image_dir / "page_0002.png").exists()


def test_extract_tables_writes_index_for_no_grid_table(monkeypatch, tmp_path):
    tables_dir = tmp_path / "tables" / "doc-with-table"
    monkeypatch.setattr(
        "src.extraction.table_extractor.get_tables_dir",
        lambda doc_id: _mkdir_return(tables_dir),
    )

    result = extract_tables(
        {
            "tables": [
                {"table_id": "table_001_00", "page": 1, "data": {}},
            ]
        },
        "doc-with-table",
    )

    assert result == [
        {
            "table_id": "table_001_00",
            "page": 1,
            "rows": 0,
            "cols": 0,
            "file_csv": None,
            "file_md": None,
            "status": "no_grid",
        }
    ]
    assert json.loads((tables_dir / "tables_index.json").read_text()) == result


def test_extract_tables_supports_docling_offset_cells(monkeypatch, tmp_path):
    tables_dir = tmp_path / "tables" / "doc-offset-table"
    monkeypatch.setattr(
        "src.extraction.table_extractor.get_tables_dir",
        lambda doc_id: _mkdir_return(tables_dir),
    )

    result = extract_tables(
        {
            "tables": [
                {
                    "table_id": "table_003_00",
                    "page": 3,
                    "data": {
                        "table_cells": [
                            {
                                "start_row_offset_idx": 0,
                                "end_row_offset_idx": 1,
                                "start_col_offset_idx": 0,
                                "end_col_offset_idx": 1,
                                "text": "Version",
                            },
                            {
                                "start_row_offset_idx": 1,
                                "end_row_offset_idx": 2,
                                "start_col_offset_idx": 0,
                                "end_col_offset_idx": 1,
                                "text": "1.0",
                            },
                        ],
                    },
                },
            ]
        },
        "doc-offset-table",
    )

    assert result[0]["rows"] == 2
    assert result[0]["cols"] == 1
    assert (tables_dir / "table_003_00.csv").read_text().splitlines() == ["Version", "1.0"]


def test_extract_figures_writes_index_for_detected_figure(monkeypatch, tmp_path):
    import fitz

    figures_dir = tmp_path / "figures" / "doc-with-figure"
    monkeypatch.setattr(
        "src.extraction.figure_extractor.get_figures_dir",
        lambda doc_id: _mkdir_return(figures_dir),
    )
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    result = extract_figures(
        pdf_path,
        {
            "figures": [
                {"figure_id": "figure_001_00", "page": 1, "caption": "Network"},
            ]
        },
        "doc-with-figure",
    )

    assert len(result) == 1
    assert result[0]["figure_id"] == "figure_001_00"
    assert result[0]["page"] == 1
    assert result[0]["caption"] == "Network"
    assert result[0]["image_path"] is not None
    assert Path(result[0]["image_path"]).exists()
    assert json.loads((figures_dir / "figures_index.json").read_text()) == result
