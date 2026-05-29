"""Page image extraction using PyMuPDF.

Performance: pages render in parallel. Each worker thread opens its own
``fitz.Document`` because PyMuPDF's Document objects are not safe to share
across threads. Opening an already-on-disk PDF is cheap (just trailer parse),
so the duplication cost is negligible compared to rendering at 150 DPI.

Cross-platform notes:
- Works identically on macOS (Apple Silicon / Intel), Linux (x86_64 / ARM64),
  and Windows.
- ``os.cpu_count()`` is wrapped so containerized environments and unusual
  hosts that return ``None`` always get a safe default.
- Default worker count is conservative (``min(cores // 2, 4)``) so the
  pipeline's outer ``run_steps_parallel`` (which itself runs 4 steps
  concurrently) doesn't oversubscribe small machines.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz

from src.config import get_config
from src.intake.file_manager import get_page_images_dir

logger = logging.getLogger(__name__)


def extract_page_images(file_path: Path, doc_id: str) -> list[dict]:
    """Render each page as PNG. Returns list of page image metadata in page order."""
    cfg = get_config()
    dpi = int(cfg["parsing"]["page_image_dpi"])
    workers_cfg = int(cfg["parsing"].get("page_image_workers", 0) or 0)
    output_dir = get_page_images_dir(doc_id)

    # Probe page count once with a short-lived handle.
    with _open_pdf(file_path) as doc:
        page_count = len(doc)

    if page_count == 0:
        logger.info("No pages to render for %s", doc_id)
        return []

    workers = _resolve_worker_count(workers_cfg, page_count)
    file_str = str(file_path)

    # Single-page or single-worker fast path: avoid the executor overhead.
    if workers <= 1 or page_count == 1:
        with _open_pdf(file_path) as doc:
            pages = [_render_page(doc, page_index, dpi, output_dir) for page_index in range(page_count)]
        logger.info("Generated %d page images for %s (sequential)", len(pages), doc_id)
        return pages

    # Each worker keeps its own thread-local fitz.Document.
    import threading
    thread_local = threading.local()

    def render_one(page_index: int) -> dict:
        doc = getattr(thread_local, "doc", None)
        if doc is None:
            doc = fitz.open(file_str)
            thread_local.doc = doc
        return _render_page(doc, page_index, dpi, output_dir)

    pages: list[dict] = [None] * page_count  # type: ignore[list-item]
    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pageimg") as ex:
            for idx, page_meta in zip(range(page_count), ex.map(render_one, range(page_count))):
                pages[idx] = page_meta
    finally:
        # Close any per-thread handles. ThreadPoolExecutor doesn't expose its threads,
        # so we clear our own thread-local on the calling thread for completeness.
        local_doc = getattr(thread_local, "doc", None)
        if local_doc is not None:
            try:
                local_doc.close()
            except Exception:
                pass

    logger.info("Generated %d page images for %s (workers=%d)", len(pages), doc_id, workers)
    return pages


def _render_page(doc, page_index: int, dpi: int, output_dir: Path) -> dict:
    """Render a single page to PNG. Caller owns the fitz.Document."""
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    img_name = f"page_{page_index + 1:04d}.png"
    img_path = output_dir / img_name
    pix.save(str(img_path))
    return {
        "page_number": page_index + 1,
        "image_path": str(img_path),
        "width": pix.width,
        "height": pix.height,
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

class _open_pdf:
    """Context manager that opens a fitz.Document and guarantees close()."""

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._doc = None

    def __enter__(self):
        self._doc = fitz.open(str(self._file_path))
        return self._doc

    def __exit__(self, exc_type, exc, tb):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass


def _resolve_worker_count(configured: int, page_count: int) -> int:
    """Pick worker count: explicit config > auto from CPU count.

    Auto formula: ``min(cores // 2, 4)`` so the pipeline's outer concurrency
    (``run_steps_parallel``) and Docling's intra-op threads still have CPU
    headroom on small machines.
    """
    if configured > 0:
        return min(configured, page_count)

    cores = _detect_usable_cpu_count()
    auto = max(1, min(cores // 2, 4))
    return min(auto, page_count)


def _detect_usable_cpu_count() -> int:
    """Return CPU count that respects container/cpuset/affinity limits."""
    # Python 3.13+: respects container CPU quota when available.
    fn = getattr(os, "process_cpu_count", None)
    if fn is not None:
        try:
            count = fn()
            if count:
                return count
        except Exception:
            pass

    # Linux: respects sched_setaffinity / cpuset.
    fn = getattr(os, "sched_getaffinity", None)
    if fn is not None:
        try:
            return len(fn(0))
        except Exception:
            pass

    return os.cpu_count() or 4
