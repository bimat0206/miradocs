"""Tests for adapting Docling document dictionaries."""

from src.parsing.docling_parser import _extract_figures, _extract_tables


def test_extract_tables_reads_top_level_docling_tables():
    doc_dict = {
        "body": {"children": [{"$ref": "#/tables/0"}]},
        "tables": [
            {
                "prov": [{"page_no": 3}],
                "data": {
                    "table_cells": [
                        {
                            "start_row_offset_idx": 0,
                            "end_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                            "end_col_offset_idx": 1,
                            "text": "Version",
                        }
                    ]
                },
            }
        ],
    }

    tables = _extract_tables(doc_dict)

    assert len(tables) == 1
    assert tables[0]["table_id"] == "table_003_00"
    assert tables[0]["page"] == 3
    assert tables[0]["data"]["table_cells"][0]["text"] == "Version"


def test_extract_figures_reads_top_level_docling_pictures():
    doc_dict = {
        "body": {"children": [{"$ref": "#/pictures/0"}]},
        "pictures": [
            {
                "prov": [{"page_no": 7, "bbox": {"l": 1, "b": 2, "r": 3, "t": 4}}],
                "text": "Network diagram",
            }
        ],
    }

    figures = _extract_figures(doc_dict)

    assert figures == [
        {
            "figure_id": "figure_007_00",
            "page": 7,
            "caption": "Network diagram",
            "bbox": [1.0, 2.0, 3.0, 4.0],
        }
    ]
