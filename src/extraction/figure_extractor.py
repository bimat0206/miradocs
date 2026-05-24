"""Figure extraction - crops figure regions from page images."""
import json
import logging
from pathlib import Path
from typing import Any

import fitz

from src.intake.file_manager import get_figures_dir

logger = logging.getLogger(__name__)


def extract_figures(
    file_path: Path, parse_result: dict[str, Any], doc_id: str
) -> list[dict]:
    """Extract figures from document. Uses Docling metadata + PyMuPDF cropping."""
    figures = parse_result.get("figures", [])
    output_dir = get_figures_dir(doc_id)
    if not figures:
        logger.info(f"No figures found for {doc_id}")
        (output_dir / "figures_index.json").write_text("[]", encoding="utf-8")
        return []

    doc = fitz.open(str(file_path))
    extracted = []

    for i, fig in enumerate(figures):
        figure_id = fig.get("figure_id", f"figure_{i:03d}")
        page_num = fig.get("page", 1)
        caption = fig.get("caption", "")

        # If we have bounding box info, crop it; otherwise save full page
        bbox = fig.get("bbox")
        img_path = output_dir / f"{figure_id}.png"

        if bbox and page_num <= len(doc):
            page = doc[page_num - 1]
            rect = fitz.Rect(bbox)
            pix = page.get_pixmap(clip=rect, dpi=150)
            pix.save(str(img_path))
        elif page_num <= len(doc):
            # No bbox - save full page as figure reference
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=150)
            pix.save(str(img_path))

        extracted.append({
            "figure_id": figure_id,
            "page": page_num,
            "caption": caption,
            "image_path": str(img_path) if img_path.exists() else None,
            "has_bbox": bbox is not None,
        })

    doc.close()

    # Save figure index
    index_path = output_dir / "figures_index.json"
    index_path.write_text(json.dumps(extracted, indent=2), encoding="utf-8")
    logger.info(f"Extracted {len(extracted)} figures for {doc_id}")
    return extracted
