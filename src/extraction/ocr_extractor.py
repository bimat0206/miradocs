"""OCR extractor - flags pages needing OCR. Actual OCR handled by Docling."""
import logging
from typing import Any

from src.config import get_config

logger = logging.getLogger(__name__)


def identify_ocr_pages(pages_text: list[dict]) -> list[int]:
    """Identify pages with very low text that likely need OCR."""
    cfg = get_config()
    threshold = cfg["quality"]["low_text_threshold"]
    ocr_pages = []
    for page_info in pages_text:
        text = page_info.get("text", "")
        if len(text.strip()) < threshold:
            ocr_pages.append(page_info.get("page", 0))
    return ocr_pages
