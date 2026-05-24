"""Tests for table and figure extraction artifacts."""
import json
from pathlib import Path

from src.extraction.figure_extractor import extract_figures
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
