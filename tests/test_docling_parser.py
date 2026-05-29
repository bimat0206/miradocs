"""Tests for adapting Docling document dictionaries."""
import sys
import types

from src.parsing.docling_parser import (
    _extract_figures,
    _extract_tables,
    parse_with_docling,
)


def test_parse_with_docling_forces_pdf_pipeline_to_cpu(monkeypatch, tmp_path):
    captured = {}

    class FakeInputFormat:
        PDF = "pdf"

    class FakeAcceleratorDevice:
        CPU = "cpu"

    class FakeAcceleratorOptions:
        def __init__(self, *, device):
            self.device = device

    class FakePdfPipelineOptions:
        def __init__(self, *, accelerator_options):
            self.accelerator_options = accelerator_options

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options):
            self.pipeline_options = pipeline_options

    class FakeDocument:
        def export_to_markdown(self):
            return "# Parsed"

        def export_to_dict(self):
            return {"pages": {"1": {}}}

    class FakeResult:
        document = FakeDocument()

    class FakeDocumentConverter:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def convert(self, file_path):
            captured["file_path"] = file_path
            return FakeResult()

    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))

    converter_module = types.ModuleType("docling.document_converter")
    converter_module.DocumentConverter = FakeDocumentConverter
    converter_module.PdfFormatOption = FakePdfFormatOption
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    base_models_module = types.ModuleType("docling.datamodel.base_models")
    base_models_module.InputFormat = FakeInputFormat
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_models_module)

    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePdfPipelineOptions
    monkeypatch.setitem(
        sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module
    )

    accelerator_options_module = types.ModuleType("docling.datamodel.accelerator_options")
    accelerator_options_module.AcceleratorDevice = FakeAcceleratorDevice
    accelerator_options_module.AcceleratorOptions = FakeAcceleratorOptions
    monkeypatch.setitem(
        sys.modules, "docling.datamodel.accelerator_options", accelerator_options_module
    )

    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    result = parse_with_docling(file_path)

    pdf_options = captured["kwargs"]["format_options"][FakeInputFormat.PDF]
    assert pdf_options.pipeline_options.accelerator_options.device == "cpu"
    assert captured["file_path"] == str(file_path)
    assert result["parser"] == "docling"


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
