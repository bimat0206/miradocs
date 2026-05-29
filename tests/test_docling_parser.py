"""Tests for adapting Docling document dictionaries."""
import sys
import types

import pytest

import src.parsing.docling_parser as docling_parser_mod
from src.parsing.docling_parser import (
    _extract_figures,
    _extract_tables,
    parse_with_docling,
    reset_converter_cache,
    reset_failed_devices,
)


@pytest.fixture(autouse=True)
def _reset_converter_cache_between_tests():
    """Make sure no test leaks a cached converter or device blacklist into the next test."""
    reset_converter_cache()
    reset_failed_devices()
    yield
    reset_converter_cache()
    reset_failed_devices()


def _install_fake_docling(monkeypatch, captured: dict):
    """Wire up fake docling modules into sys.modules and return the AcceleratorDevice fake."""

    class FakeInputFormat:
        PDF = "pdf"

    class FakeAcceleratorDevice:
        # Mirrors the real enum's CPU constant (the only one we can rely on
        # being present across all Docling versions).
        CPU = "cpu"

    class FakeAcceleratorOptions:
        def __init__(self, *, device, **kwargs):
            self.device = device
            self.kwargs = kwargs

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

    return FakeAcceleratorDevice


def test_parse_with_docling_uses_configured_device(monkeypatch, tmp_path):
    """When accelerator_device='cpu' is configured, the CPU enum value is forwarded."""
    captured: dict = {}
    fake_device = _install_fake_docling(monkeypatch, captured)

    # Force CPU regardless of host hardware so the assertion is deterministic
    # across macOS Apple Silicon, Linux x86_64, Linux ARM64, and Windows.
    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "cpu", "accelerator_num_threads": 0}},
    )

    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    result = parse_with_docling(file_path)

    pdf_options = captured["kwargs"]["format_options"][type(fake_device).PDF if hasattr(type(fake_device), "PDF") else "pdf"]
    assert pdf_options.pipeline_options.accelerator_options.device == fake_device.CPU
    assert captured["file_path"] == str(file_path)
    assert result["parser"] == "docling"


def test_auto_device_falls_back_to_cpu_when_only_cpu_available(monkeypatch, tmp_path):
    """auto-detection must degrade to CPU on builds where MPS/CUDA enum values are missing."""
    captured: dict = {}
    fake_device = _install_fake_docling(monkeypatch, captured)

    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "auto", "accelerator_num_threads": 0}},
    )

    # Even on a host with MPS/CUDA available, the fake AcceleratorDevice exposes only
    # CPU — _resolve_accelerator_device must hasattr-guard and fall back gracefully.
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    parse_with_docling(file_path)

    pdf_options = captured["kwargs"]["format_options"]["pdf"]
    assert pdf_options.pipeline_options.accelerator_options.device == fake_device.CPU


def test_converter_is_cached_between_calls(monkeypatch, tmp_path):
    """Second call must reuse the same DocumentConverter instance (avoids re-loading models)."""
    instances: list = []

    fake_acc_module = types.ModuleType("docling.datamodel.accelerator_options")

    class FakeAcceleratorDevice:
        CPU = "cpu"

    class FakeAcceleratorOptions:
        def __init__(self, *, device, **kwargs):
            self.device = device

    fake_acc_module.AcceleratorDevice = FakeAcceleratorDevice
    fake_acc_module.AcceleratorOptions = FakeAcceleratorOptions
    monkeypatch.setitem(sys.modules, "docling.datamodel.accelerator_options", fake_acc_module)

    base_module = types.ModuleType("docling.datamodel.base_models")
    base_module.InputFormat = types.SimpleNamespace(PDF="pdf")
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_module)

    pipeline_module = types.ModuleType("docling.datamodel.pipeline_options")

    class FakePdfPipelineOptions:
        def __init__(self, *, accelerator_options):
            self.accelerator_options = accelerator_options

    pipeline_module.PdfPipelineOptions = FakePdfPipelineOptions
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_module)

    converter_module = types.ModuleType("docling.document_converter")

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options):
            self.pipeline_options = pipeline_options

    class FakeDocument:
        def export_to_markdown(self):
            return ""

        def export_to_dict(self):
            return {}

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def __init__(self, **kwargs):
            instances.append(self)

        def convert(self, file_path):
            return FakeResult()

    converter_module.DocumentConverter = FakeConverter
    converter_module.PdfFormatOption = FakePdfFormatOption
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))

    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "cpu", "accelerator_num_threads": 0}},
    )

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    parse_with_docling(pdf)
    parse_with_docling(pdf)

    assert len(instances) == 1, "DocumentConverter should be cached and reused across calls"


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


# ─── Accelerator fallback ────────────────────────────────────────────────────

def _install_fake_docling_with_devices(monkeypatch, captured: dict, *, allow_mps: bool):
    """Like _install_fake_docling but exposes MPS so the fallback path can be exercised."""

    class FakeAcceleratorDevice:
        CPU = types.SimpleNamespace(name="CPU")
        if True:
            MPS = types.SimpleNamespace(name="MPS")

    class FakeAcceleratorOptions:
        def __init__(self, *, device, **kwargs):
            self.device = device
            self.kwargs = kwargs

    class FakePdfPipelineOptions:
        def __init__(self, *, accelerator_options):
            self.accelerator_options = accelerator_options

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options):
            self.pipeline_options = pipeline_options

    class FakeDocument:
        def export_to_markdown(self):
            return "# CPU"

        def export_to_dict(self):
            return {"pages": {"1": {}}}

    class FakeResult:
        document = FakeDocument()

    class FakeDocumentConverter:
        def __init__(self, **kwargs):
            captured.setdefault("init_devices", []).append(
                kwargs["format_options"]["pdf"].pipeline_options.accelerator_options.device
            )
            self._device = captured["init_devices"][-1]

        def convert(self, file_path):
            captured.setdefault("convert_devices", []).append(self._device)
            if self._device.name == "MPS":
                raise TypeError(
                    "Cannot convert a MPS Tensor to float64 dtype as the MPS framework "
                    "doesn't support float64. Please use float32 instead."
                )
            return FakeResult()

    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))

    converter_module = types.ModuleType("docling.document_converter")
    converter_module.DocumentConverter = FakeDocumentConverter
    converter_module.PdfFormatOption = FakePdfFormatOption
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    base_models_module = types.ModuleType("docling.datamodel.base_models")
    base_models_module.InputFormat = types.SimpleNamespace(PDF="pdf")
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_models_module)

    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePdfPipelineOptions
    monkeypatch.setitem(
        sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module
    )

    accelerator_options_module = types.ModuleType("docling.datamodel.accelerator_options")
    accelerator_options_module.AcceleratorDevice = FakeAcceleratorDevice
    accelerator_options_module.AcceleratorOptions = FakeAcceleratorOptions
    if not allow_mps:
        # Hide MPS so auto-detection cannot select it.
        del accelerator_options_module.AcceleratorDevice.MPS
    monkeypatch.setitem(
        sys.modules, "docling.datamodel.accelerator_options", accelerator_options_module
    )

    return FakeAcceleratorDevice


def test_mps_float64_failure_triggers_cpu_fallback(monkeypatch, tmp_path):
    """When MPS raises the transformers float64 TypeError, parse retries on CPU."""
    captured: dict = {}
    fake_device = _install_fake_docling_with_devices(monkeypatch, captured, allow_mps=True)

    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "mps", "accelerator_num_threads": 0}},
    )

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    result = parse_with_docling(pdf)

    assert result["parser"] == "docling"
    assert [d.name for d in captured["convert_devices"]] == ["MPS", "CPU"]
    assert "MPS" in docling_parser_mod._FAILED_DEVICES


def test_blacklisted_device_skipped_on_subsequent_calls(monkeypatch, tmp_path):
    """Once MPS is blacklisted, future parses pick CPU directly without retrying."""
    captured: dict = {}
    _install_fake_docling_with_devices(monkeypatch, captured, allow_mps=True)

    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "mps", "accelerator_num_threads": 0}},
    )

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    parse_with_docling(pdf)
    parse_with_docling(pdf)
    parse_with_docling(pdf)

    # First call: tried MPS once (failed) then CPU; subsequent calls go straight to CPU.
    convert_device_names = [d.name for d in captured["convert_devices"]]
    assert convert_device_names == ["MPS", "CPU", "CPU", "CPU"]


def test_cpu_failures_are_not_retried(monkeypatch, tmp_path):
    """When the active device is already CPU, an unrelated TypeError is raised, not silently retried."""
    captured: dict = {}

    class FakeAcceleratorDevice:
        CPU = types.SimpleNamespace(name="CPU")

    class FakeAcceleratorOptions:
        def __init__(self, *, device, **kwargs):
            self.device = device

    class FakePdfPipelineOptions:
        def __init__(self, *, accelerator_options):
            self.accelerator_options = accelerator_options

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options):
            self.pipeline_options = pipeline_options

    class FakeConverter:
        def __init__(self, **kwargs):
            captured["device"] = kwargs["format_options"]["pdf"].pipeline_options.accelerator_options.device

        def convert(self, file_path):
            # Even with an MPS-shaped error message, retry must NOT happen on CPU.
            raise TypeError("Cannot convert a MPS Tensor to float64 (simulated bug on CPU path)")

    converter_module = types.ModuleType("docling.document_converter")
    converter_module.DocumentConverter = FakeConverter
    converter_module.PdfFormatOption = FakePdfFormatOption
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    base_models_module = types.ModuleType("docling.datamodel.base_models")
    base_models_module.InputFormat = types.SimpleNamespace(PDF="pdf")
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

    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))

    monkeypatch.setattr(
        docling_parser_mod,
        "get_config",
        lambda: {"parsing": {"accelerator_device": "cpu", "accelerator_num_threads": 0}},
    )

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(TypeError, match="MPS Tensor"):
        parse_with_docling(pdf)

    assert "CPU" not in docling_parser_mod._FAILED_DEVICES
