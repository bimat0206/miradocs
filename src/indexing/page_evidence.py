"""Page Image Evidence Layer — assembles full evidence context for search results.

For architecture review, each search result is enriched with:
- Full page screenshot path
- Cropped diagram path (if figure)
- OCR text from diagram
- Caption
- Nearby text (surrounding paragraphs)
- Figure number
- Page number
"""
import json
import logging
from pathlib import Path
from typing import Any

import fitz

from src.config import get_data_dir
from src.intake.file_manager import (
    get_page_images_dir, get_figures_dir, get_tables_dir, get_parsed_dir,
)

logger = logging.getLogger(__name__)

_registry_singleton = None


def _get_registry_singleton():
    global _registry_singleton
    if _registry_singleton is None:
        from src.intake.document_registry import DocumentRegistry
        _registry_singleton = DocumentRegistry()
    return _registry_singleton


class PageImageEvidence:
    """Retrieves and assembles page-level evidence for search results."""

    def __init__(self, doc_id: str | list[str]):
        if isinstance(doc_id, str):
            self.doc_ids = [doc_id]
            self.doc_id = doc_id
        else:
            self.doc_ids = list(doc_id)
            self.doc_id = self.doc_ids[0] if self.doc_ids else ""

        self._doc_data = {}
        # Per-doc cached page text: {doc_id: {page_number: str}}
        self._page_text_cache: dict[str, dict[int, str]] = {}
        for d_id in self.doc_ids:
            self._ensure_doc_loaded(d_id)

    def _ensure_doc_loaded(self, doc_id: str):
        if not doc_id:
            return
        if doc_id not in self._doc_data:
            self._doc_data[doc_id] = {
                "structure": self._load_structure(doc_id),
                "figures_index": self._load_figures_index(doc_id),
                "tables_index": self._load_tables_index(doc_id),
            }

    def enrich_results(self, results: list[dict]) -> list[dict]:
        """Enrich search results with full page evidence."""
        return [self._enrich_one(r) for r in results]

    def get_page_evidence(self, page_number: int, doc_id: str | None = None) -> dict:
        """Get full evidence for a specific page."""
        d_id = doc_id or self.doc_id
        self._ensure_doc_loaded(d_id)
        return {
            "page_number": page_number,
            "page_image": self._get_page_image(d_id, page_number),
            "figures": self._get_figures_on_page(d_id, page_number),
            "tables": self._get_tables_on_page(d_id, page_number),
            "text": self._get_page_text(d_id, page_number),
            "section_path": self._get_section_for_page(d_id, page_number),
        }

    def get_figure_evidence(self, figure_id: str, doc_id: str | None = None) -> dict | None:
        """Get full evidence for a specific figure."""
        d_id = doc_id or self.doc_id
        self._ensure_doc_loaded(d_id)
        figures_index = self._doc_data.get(d_id, {}).get("figures_index", [])
        fig = next((f for f in figures_index if f["figure_id"] == figure_id), None)
        if not fig:
            return None

        page_num = fig.get("page", 0)
        return {
            "figure_id": figure_id,
            "figure_number": self._extract_figure_number(fig),
            "page_number": page_num,
            "page_image": self._get_page_image(d_id, page_num),
            "cropped_diagram": fig.get("image_path"),
            "ocr_text": self._get_figure_ocr(fig),
            "caption": fig.get("caption", ""),
            "nearby_text": self._get_nearby_text(d_id, page_num),
            "section_path": self._get_section_for_page(d_id, page_num),
        }

    def _enrich_one(self, result: dict) -> dict:
        """Enrich a single search result with evidence."""
        d_id = result.get("doc_id") or self.doc_id
        if isinstance(d_id, list):
            d_id = d_id[0] if d_id else self.doc_id
        self._ensure_doc_loaded(d_id)
        page_num = result.get("page_start", 0)
        source_refs = result.get("source_refs", {})
        figure_id = source_refs.get("figure_id")
        table_id = source_refs.get("table_id")

        evidence = {
            "page_number": page_num,
            "page_image": self._get_page_image(d_id, page_num),
            "section_path": result.get("section_path", self._get_section_for_page(d_id, page_num)),
            "nearby_text": self._get_nearby_text(d_id, page_num),
        }

        # Figure evidence
        if figure_id:
            fig_evidence = self.get_figure_evidence(figure_id, d_id)
            if fig_evidence:
                evidence["cropped_diagram"] = fig_evidence["cropped_diagram"]
                evidence["ocr_text"] = fig_evidence["ocr_text"]
                evidence["caption"] = fig_evidence["caption"]
                evidence["figure_number"] = fig_evidence["figure_number"]
        else:
            evidence["cropped_diagram"] = None
            evidence["ocr_text"] = None
            evidence["caption"] = None
            evidence["figure_number"] = None

        # Table evidence
        if table_id:
            tables_index = self._doc_data.get(d_id, {}).get("tables_index", [])
            table = next((t for t in tables_index if t.get("table_id") == table_id), None)
            if table:
                evidence["table_file"] = table.get("file_md") or table.get("file_csv")

        return {**result, "evidence": evidence}

    # ─── Internal helpers ─────────────────────────────────────────────────

    def _get_page_image(self, doc_id: str, page_number: int) -> str | None:
        img_dir = get_page_images_dir(doc_id)
        path = img_dir / f"page_{page_number:04d}.png"
        return str(path) if path.exists() else None

    def _get_figures_on_page(self, doc_id: str, page_number: int) -> list[dict]:
        figures_index = self._doc_data.get(doc_id, {}).get("figures_index", [])
        return [f for f in figures_index if f.get("page") == page_number]

    def _get_tables_on_page(self, doc_id: str, page_number: int) -> list[dict]:
        tables_index = self._doc_data.get(doc_id, {}).get("tables_index", [])
        return [t for t in tables_index if t.get("page") == page_number]

    def _load_page_text_cache(self, doc_id: str):
        """Load all page text for a doc into memory once."""
        if doc_id in self._page_text_cache:
            return
        raw_path = self._find_raw_file(doc_id)
        cache: dict[int, str] = {}
        if raw_path and raw_path.exists() and raw_path.suffix.lower() == ".pdf":
            try:
                pdf = fitz.open(str(raw_path))
                for i, page in enumerate(pdf, start=1):
                    cache[i] = page.get_text("text")
                pdf.close()
            except Exception:
                pass
        self._page_text_cache[doc_id] = cache

    def _get_page_text(self, doc_id: str, page_number: int) -> str:
        self._load_page_text_cache(doc_id)
        return self._page_text_cache.get(doc_id, {}).get(page_number, "")

    def _get_nearby_text(self, doc_id: str, page_number: int, context_pages: int = 1) -> str:
        self._load_page_text_cache(doc_id)
        cache = self._page_text_cache.get(doc_id, {})
        parts = [
            cache[pg]
            for pg in range(max(1, page_number - context_pages), page_number + context_pages + 1)
            if pg in cache
        ]
        return "\n".join(parts)

    def _get_figure_ocr(self, fig: dict) -> str:
        """Get OCR text for a figure (from cropped image if available)."""
        if fig.get("ocr_text"):
            return fig["ocr_text"]
        return ""

    def _get_section_for_page(self, doc_id: str, page_number: int) -> str:
        structure = self._doc_data.get(doc_id, {}).get("structure", {})
        if not structure:
            return ""
        for sec in reversed(structure.get("sections", [])):
            if sec.get("page_start", 0) <= page_number <= sec.get("page_end", 0):
                return sec.get("section_path", sec.get("title", ""))
        return ""

    def _extract_figure_number(self, fig: dict) -> str:
        """Extract figure number from figure_id or caption."""
        fid = fig.get("figure_id", "")
        parts = fid.replace("figure_", "").split("_")
        if len(parts) >= 2:
            return f"Figure {int(parts[0])}.{int(parts[1]) + 1}"
        caption = fig.get("caption", "")
        if caption:
            import re
            match = re.search(r"[Ff]igure\s+(\d+[\.\d]*)", caption)
            if match:
                return f"Figure {match.group(1)}"
        return fid

    def _find_raw_file(self, doc_id: str) -> Path | None:
        try:
            from src.ui.state import get_registry
            registry = get_registry()
        except Exception:
            registry = _get_registry_singleton()
        doc = registry.get_document(doc_id)
        if not doc:
            return None
        return get_data_dir() / "raw" / doc["project"] / doc_id / doc["filename"]

    def _load_structure(self, doc_id: str) -> dict:
        path = get_parsed_dir(doc_id) / "document_structure.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_figures_index(self, doc_id: str) -> list[dict]:
        path = get_figures_dir(doc_id) / "figures_index.json"
        if path.exists():
            return json.loads(path.read_text())
        return []

    def _load_tables_index(self, doc_id: str) -> list[dict]:
        path = get_tables_dir(doc_id) / "tables_index.json"
        if path.exists():
            return json.loads(path.read_text())
        return []
