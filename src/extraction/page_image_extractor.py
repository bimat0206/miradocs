"""Page image extraction using PyMuPDF."""
import logging
from pathlib import Path

import fitz

from src.config import get_config
from src.intake.file_manager import get_page_images_dir

logger = logging.getLogger(__name__)


def extract_page_images(file_path: Path, doc_id: str) -> list[dict]:
    """Render each page as PNG. Returns list of page image metadata."""
    cfg = get_config()
    dpi = cfg["parsing"]["page_image_dpi"]
    output_dir = get_page_images_dir(doc_id)

    doc = fitz.open(str(file_path))
    pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img_name = f"page_{page_num + 1:04d}.png"
        img_path = output_dir / img_name
        pix.save(str(img_path))
        pages.append({
            "page_number": page_num + 1,
            "image_path": str(img_path),
            "width": pix.width,
            "height": pix.height,
        })

    doc.close()
    logger.info(f"Generated {len(pages)} page images for {doc_id}")
    return pages
