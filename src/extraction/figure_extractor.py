"""Figure extraction - crops figure regions from page images.

Performance: figures crop in parallel using thread-local fitz.Document
handles (PyMuPDF Document objects are not thread-safe). Cross-platform safe
on macOS, Linux, and Windows; works on x86_64 and ARM64.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import fitz

from src.config import get_config
from src.intake.file_manager import get_figures_dir

logger = logging.getLogger(__name__)


def extract_figures(
    file_path: Path, parse_result: dict[str, Any], doc_id: str
) -> list[dict]:
    """Extract figures from document. Uses Docling metadata + PyMuPDF cropping."""
    figures = parse_result.get("figures", []) or []
    output_dir = get_figures_dir(doc_id)

    if not figures:
        logger.info("No figures found for %s", doc_id)
        (output_dir / "figures_index.json").write_text("[]", encoding="utf-8")
        return []

    cfg = get_config()
    workers_cfg = int(cfg.get("parsing", {}).get("figure_workers", 0) or 0)

    # Probe document length once with a short-lived handle so each worker
    # doesn't have to do bounds-check IO independently.
    try:
        with _open_pdf(file_path) as doc:
            page_count = len(doc)
    except Exception as e:
        logger.warning("Could not open %s for figure extraction: %s", file_path, e)
        page_count = 0

    workers = _resolve_worker_count(workers_cfg, len(figures))
    file_str = str(file_path)

    # Build the task list with stable indices so output order matches the input.
    tasks = list(enumerate(figures))

    if workers <= 1 or len(tasks) == 1 or page_count == 0:
        # Sequential fast path.
        with _open_pdf(file_path) if page_count > 0 else _NullDoc() as doc:
            extracted = [_crop_figure(doc, fig, i, page_count, output_dir) for i, fig in tasks]
    else:
        thread_local = threading.local()

        def crop_one(item):
            i, fig = item
            doc = getattr(thread_local, "doc", None)
            if doc is None:
                doc = fitz.open(file_str)
                thread_local.doc = doc
            return _crop_figure(doc, fig, i, page_count, output_dir)

        extracted_unsorted: list[tuple[int, dict]] = []
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="figcrop") as ex:
                # Use map to preserve task ordering by re-zipping with indices.
                results = list(ex.map(crop_one, tasks))
            extracted_unsorted = list(zip([i for i, _ in tasks], results))
        finally:
            local_doc = getattr(thread_local, "doc", None)
            if local_doc is not None:
                try:
                    local_doc.close()
                except Exception:
                    pass

        extracted_unsorted.sort(key=lambda x: x[0])
        extracted = [meta for _, meta in extracted_unsorted]

    # Save figure index
    index_path = output_dir / "figures_index.json"
    index_path.write_text(json.dumps(extracted, indent=2), encoding="utf-8")
    logger.info("Extracted %d figures for %s (workers=%d)", len(extracted), doc_id, workers)
    return extracted


# ─── Internals ───────────────────────────────────────────────────────────────

def _crop_figure(doc, fig: dict, i: int, page_count: int, output_dir: Path) -> dict:
    """Crop one figure into a PNG. Caller owns the fitz.Document."""
    figure_id = fig.get("figure_id", f"figure_{i:03d}")
    page_num = fig.get("page", 1)
    caption = fig.get("caption", "")
    bbox = fig.get("bbox")
    img_path = output_dir / f"{figure_id}.png"

    rendered = False
    if doc is not None and page_count > 0 and 1 <= page_num <= page_count:
        page = doc[page_num - 1]
        if bbox:
            try:
                rect = fitz.Rect(bbox)
                pix = page.get_pixmap(clip=rect, dpi=150)
            except Exception as e:
                logger.debug("bbox crop failed for %s, falling back to full page: %s", figure_id, e)
                pix = page.get_pixmap(dpi=150)
        else:
            pix = page.get_pixmap(dpi=150)
        pix.save(str(img_path))
        rendered = True

    return {
        "figure_id": figure_id,
        "page": page_num,
        "caption": caption,
        "image_path": str(img_path) if rendered and img_path.exists() else None,
        "has_bbox": bbox is not None,
    }


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


class _NullDoc:
    """Standin context manager when no PDF is available — keeps `with` syntax usable."""

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _resolve_worker_count(configured: int, task_count: int) -> int:
    if task_count <= 1:
        return 1
    if configured > 0:
        return min(configured, task_count)
    cores = _detect_usable_cpu_count()
    auto = max(1, min(cores // 2, 4))
    return min(auto, task_count)


def _detect_usable_cpu_count() -> int:
    fn = getattr(os, "process_cpu_count", None)
    if fn is not None:
        try:
            count = fn()
            if count:
                return count
        except Exception:
            pass
    fn = getattr(os, "sched_getaffinity", None)
    if fn is not None:
        try:
            return len(fn(0))
        except Exception:
            pass
    return os.cpu_count() or 4
