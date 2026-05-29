"""Docling-based document parser.

Performance optimizations:
- DocumentConverter is cached as a thread-safe module-level singleton so that
  Docling's expensive ML model loading (layout / table-structure / OCR) only
  happens once per process, not per document.
- Hardware acceleration is auto-detected and configurable.

Cross-platform / cross-architecture support:
- macOS arm64 (Apple Silicon): MPS via PyTorch when available
- macOS x86_64 (Intel)        : CPU
- Linux + NVIDIA              : CUDA
- Linux ARM64 / other         : CPU
- Windows + NVIDIA            : CUDA
- Windows other               : CPU

The accelerator can be overridden in ``config/settings.yaml`` under
``parsing.accelerator_device`` (``auto`` | ``cpu`` | ``cuda`` | ``mps``).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from src.config import get_config

logger = logging.getLogger(__name__)


# ─── Cached singleton ────────────────────────────────────────────────────────

# The cache key includes the resolved device + thread count so a config change
# transparently rebuilds the converter on next call. We also key on the
# DocumentConverter class identity so monkeypatched test doubles never see a
# stale real converter.
_CONVERTER_CACHE: dict[tuple, Any] = {}
_CONVERTER_LOCK = threading.Lock()

# Process-level blacklist of accelerator device *names* (e.g. {"MPS"}) that
# raised a hard incompatibility during convert(). Once a device is blacklisted
# for the current process, neither auto-detection nor explicit config will
# select it again, so subsequent documents skip the doomed retry. This is
# specifically how we handle the transformers + Apple Silicon MPS float64
# issue in models like RT-DETR v2 used by Docling for layout detection.
_FAILED_DEVICES: set[str] = set()
_FAILED_DEVICES_LOCK = threading.Lock()


def reset_converter_cache() -> None:
    """Clear the cached DocumentConverter. Intended for tests and config reloads."""
    with _CONVERTER_LOCK:
        _CONVERTER_CACHE.clear()


def reset_failed_devices() -> None:
    """Clear the failed-device blacklist. Intended for tests."""
    with _FAILED_DEVICES_LOCK:
        _FAILED_DEVICES.clear()


def _is_device_blacklisted(device) -> bool:
    """Return True if this device name has been recorded as failing this process."""
    name = getattr(device, "name", str(device)).upper()
    with _FAILED_DEVICES_LOCK:
        return name in _FAILED_DEVICES


def _blacklist_device(device) -> None:
    """Record a device as failing for the rest of this process."""
    name = getattr(device, "name", str(device)).upper()
    with _FAILED_DEVICES_LOCK:
        _FAILED_DEVICES.add(name)


# ─── Public API ──────────────────────────────────────────────────────────────

# Substrings used to detect a hard accelerator incompatibility coming from
# upstream code (transformers, torch, Docling models). When we see one of
# these *and* the active device is non-CPU, we blacklist the device, reset
# the converter cache, and retry once on CPU. The list errs on the side of
# being slightly broad: if a real bug ever matches one of these strings on
# CPU we'll still raise it — we only re-route when the active device != CPU.
_ACCELERATOR_FAILURE_PATTERNS = (
    "mps framework doesn't support float64",
    "cannot convert a mps tensor to float64",
    "the mps framework doesn",            # broad MPS limitation cover
    "cuda out of memory",                  # OOM can sometimes be cleared by CPU fallback
    "cuda error",                          # broad CUDA driver/runtime errors
)


def parse_with_docling(file_path: Path) -> dict[str, Any]:
    """Parse document using Docling. Returns structured result.

    On hard accelerator incompatibilities (e.g. transformers requiring
    ``float64`` on Apple Silicon MPS) the failing device is blacklisted for
    the rest of the process, the converter cache is rebuilt on CPU, and the
    parse is retried once. The retry is silent to the caller — they get a
    successful result or the original exception.
    """
    last_exc: Exception | None = None

    for attempt in range(2):
        converter, active_device = _get_or_create_converter_with_device()

        logger.info(
            "Parsing with Docling: %s (device=%s, attempt=%d)",
            file_path,
            getattr(active_device, "name", active_device),
            attempt + 1,
        )

        try:
            result = converter.convert(str(file_path))
        except Exception as exc:
            if not _should_retry_on_cpu(exc, active_device):
                raise
            last_exc = exc
            logger.warning(
                "Docling convert failed on device=%s with %s: %s — "
                "blacklisting device and retrying on CPU.",
                getattr(active_device, "name", active_device),
                type(exc).__name__,
                exc,
            )
            _blacklist_device(active_device)
            reset_converter_cache()
            continue

        doc = result.document
        markdown = doc.export_to_markdown()
        doc_dict = doc.export_to_dict()

        sections = _extract_sections(doc_dict)
        tables = _extract_tables(doc_dict)
        figures = _extract_figures(doc_dict)
        page_count = _get_page_count(doc_dict)

        return {
            "markdown": markdown,
            "doc_dict": doc_dict,
            "sections": sections,
            "tables": tables,
            "figures": figures,
            "page_count": page_count,
            "parser": "docling",
        }

    # Reached only if the second (CPU) attempt also tripped the retry path,
    # which shouldn't happen since CPU is excluded from _should_retry_on_cpu.
    assert last_exc is not None
    raise last_exc


def _should_retry_on_cpu(exc: Exception, active_device) -> bool:
    """Return True if exc looks like an accelerator incompatibility worth retrying on CPU."""
    name = getattr(active_device, "name", str(active_device)).upper()
    if name == "CPU":
        # Already on CPU — no fallback target left, surface the real error.
        return False

    msg = (str(exc) or "").lower()
    if not msg:
        return False
    return any(pat in msg for pat in _ACCELERATOR_FAILURE_PATTERNS)


# ─── Converter construction ──────────────────────────────────────────────────

def _get_or_create_converter():
    """Return a cached DocumentConverter, creating it on first use.

    Backward-compatible wrapper: returns only the converter, dropping the
    active device. Internal callers that need the device should use
    :func:`_get_or_create_converter_with_device`.
    """
    converter, _device = _get_or_create_converter_with_device()
    return converter


def _get_or_create_converter_with_device():
    """Return ``(converter, active_device)`` pair, building if not cached."""
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    cfg = get_config().get("parsing", {})
    device_name = str(cfg.get("accelerator_device", "auto")).lower()
    num_threads = int(cfg.get("accelerator_num_threads", 0) or 0)

    device = _resolve_accelerator_device(AcceleratorDevice, device_name)

    # Cache key includes the class identity so monkeypatched test doubles
    # don't share a cached real instance from a previous test.
    cache_key = (id(DocumentConverter), id(device), num_threads)

    with _CONVERTER_LOCK:
        cached = _CONVERTER_CACHE.get(cache_key)
        if cached is not None:
            return cached, device

        accelerator_options = _build_accelerator_options(
            AcceleratorOptions, device=device, num_threads=num_threads
        )
        pipeline_options = PdfPipelineOptions(accelerator_options=accelerator_options)

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        _CONVERTER_CACHE[cache_key] = converter
        logger.info(
            "Initialized Docling DocumentConverter (device=%s, num_threads=%s)",
            getattr(device, "name", device), num_threads or "library-default",
        )
        return converter, device


def _build_accelerator_options(AcceleratorOptions, *, device, num_threads: int):
    """Construct AcceleratorOptions, tolerating older Docling signatures."""
    # Newer versions accept num_threads; older ones don't. Try the rich form first.
    if num_threads > 0:
        try:
            return AcceleratorOptions(device=device, num_threads=num_threads)
        except TypeError:
            logger.debug("AcceleratorOptions does not accept num_threads; using device-only.")
    return AcceleratorOptions(device=device)


def _resolve_accelerator_device(AcceleratorDevice, device_name: str):
    """Return the AcceleratorDevice enum value for the requested device.

    Falls back gracefully when:
    - the requested device or auto-detection target isn't available in the
      installed Docling version (older builds may lack AUTO/MPS/CUDA constants);
    - the chosen device has already failed once in this process (recorded in
      ``_FAILED_DEVICES``) — this is the recovery path for runtime
      incompatibilities such as transformers' RT-DETR v2 needing float64 on
      MPS, which Apple Silicon doesn't support.

    For ``auto`` we always probe the runtime ourselves (CUDA → MPS → CPU)
    instead of returning Docling's opaque ``AcceleratorDevice.AUTO``. Using
    a concrete device makes the blacklist precise: when MPS fails we can
    blacklist exactly that device, and the next call will pick CPU instead
    of re-selecting MPS through AUTO.
    """
    name = (device_name or "auto").lower().strip()

    if name == "auto":
        return _auto_detect_device(AcceleratorDevice)

    enum_name = name.upper()
    if hasattr(AcceleratorDevice, enum_name):
        explicit = getattr(AcceleratorDevice, enum_name)
        if _is_device_blacklisted(explicit):
            logger.warning(
                "Configured accelerator_device=%r previously failed in this process; "
                "falling back to CPU.",
                device_name,
            )
            return AcceleratorDevice.CPU
        return explicit

    logger.warning(
        "Configured accelerator_device=%r is not available in this Docling version; "
        "falling back to CPU.",
        device_name,
    )
    return AcceleratorDevice.CPU


def _any_known_device_blacklisted(AcceleratorDevice) -> bool:
    """Return True if MPS or CUDA is blacklisted. Kept for legacy callers."""
    for attr in ("MPS", "CUDA"):
        if hasattr(AcceleratorDevice, attr) and _is_device_blacklisted(getattr(AcceleratorDevice, attr)):
            return True
    return False


def _auto_detect_device(AcceleratorDevice):
    """Pick the best available device based on the runtime hardware.

    Order of preference: CUDA → MPS → CPU. Each step is fully guarded so a
    missing torch / missing enum constant / driver error always degrades
    quietly to CPU. Devices already blacklisted in this process are skipped.
    """
    try:
        import torch  # type: ignore

        # NVIDIA GPU (Linux/Windows; rarely macOS).
        try:
            if (
                torch.cuda.is_available()
                and hasattr(AcceleratorDevice, "CUDA")
                and not _is_device_blacklisted(AcceleratorDevice.CUDA)
            ):
                return AcceleratorDevice.CUDA
        except Exception:
            pass

        # Apple Silicon GPU.
        try:
            mps = getattr(torch.backends, "mps", None)
            if (
                mps is not None
                and mps.is_available()
                and hasattr(AcceleratorDevice, "MPS")
                and not _is_device_blacklisted(AcceleratorDevice.MPS)
            ):
                return AcceleratorDevice.MPS
        except Exception:
            pass
    except ImportError:
        # PyTorch isn't installed — Docling's CPU pipeline still works.
        logger.debug("torch not importable; using CPU for Docling.")

    return AcceleratorDevice.CPU


# ─── Document-dict adapters (unchanged) ──────────────────────────────────────

def _extract_sections(doc_dict: dict) -> list[dict]:
    """Extract section hierarchy from Docling output."""
    sections = []
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "heading" in label.lower() or "title" in label.lower():
                    text = item.get("text", "")
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    sections.append({
                        "section_id": f"sec_{i:04d}",
                        "title": text,
                        "page_start": page,
                        "level": _guess_heading_level(label, text),
                    })
    return sections


def _extract_tables(doc_dict: dict) -> list[dict]:
    """Extract table metadata from Docling output."""
    tables = []
    top_level_tables = doc_dict.get("tables", [])
    if isinstance(top_level_tables, list):
        for i, item in enumerate(top_level_tables):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", [{}])
            page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
            data = item.get("data", item.get("table_data", {}))
            tables.append({
                "table_id": f"table_{page:03d}_{i:02d}",
                "page": page,
                "data": data,
                "num_rows": data.get("num_rows", 0) if isinstance(data, dict) else 0,
                "num_cols": data.get("num_cols", 0) if isinstance(data, dict) else 0,
            })
        if tables:
            return tables

    # Fallback: tables nested in body
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "table" in label.lower():
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    data = item.get("data", item.get("table_data", {}))
                    tables.append({
                        "table_id": f"table_{page:03d}_{len(tables):02d}",
                        "page": page,
                        "data": data,
                        "num_rows": data.get("num_rows", 0) if isinstance(data, dict) else 0,
                        "num_cols": data.get("num_cols", 0) if isinstance(data, dict) else 0,
                    })
    return tables


def _extract_figures(doc_dict: dict) -> list[dict]:
    """Extract figure metadata from Docling output."""
    figures = []
    top_level_pictures = doc_dict.get("pictures", [])
    if isinstance(top_level_pictures, list):
        for i, item in enumerate(top_level_pictures):
            if not isinstance(item, dict):
                continue
            prov = item.get("prov", [{}])
            page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
            bbox = prov[0].get("bbox") if prov else None
            figures.append({
                "figure_id": f"figure_{page:03d}_{i:02d}",
                "page": page,
                "caption": item.get("text", ""),
                "bbox": _bbox_to_rect(bbox),
            })
        if figures:
            return figures

    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for i, item in enumerate(body):
            if isinstance(item, dict):
                label = item.get("label", item.get("type", ""))
                if "figure" in label.lower() or "picture" in label.lower():
                    prov = item.get("prov", [{}])
                    page = prov[0].get("page_no", prov[0].get("page", 0)) if prov else 0
                    figures.append({
                        "figure_id": f"figure_{page:03d}_{len(figures):02d}",
                        "page": page,
                        "caption": item.get("text", ""),
                        "bbox": _bbox_to_rect(prov[0].get("bbox")) if prov else None,
                    })
    return figures


def _get_page_count(doc_dict: dict) -> int:
    """Get page count from Docling output."""
    pages = doc_dict.get("pages", {})
    if pages:
        return len(pages)
    max_page = 0
    body = doc_dict.get("body", doc_dict.get("main_text", []))
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                prov = item.get("prov", [{}])
                if prov:
                    p = prov[0].get("page_no", prov[0].get("page", 0))
                    max_page = max(max_page, p)
    return max_page


def _bbox_to_rect(bbox: dict | None) -> list[float] | None:
    if not isinstance(bbox, dict):
        return None
    try:
        return [float(bbox["l"]), float(bbox["b"]), float(bbox["r"]), float(bbox["t"])]
    except (KeyError, TypeError, ValueError):
        return None


def _guess_heading_level(label: str, text: str) -> int:
    """Guess heading level from label or numbering."""
    label_lower = label.lower()
    if "section" in label_lower or "heading" in label_lower:
        for i in range(1, 7):
            if str(i) in label_lower:
                return i
    if text and text[0].isdigit():
        dots = text.split(" ")[0].count(".")
        return min(dots + 1, 6)
    return 1
