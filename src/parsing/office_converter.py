"""Office document conversion helpers for page rendering."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.config import get_data_dir

logger = logging.getLogger(__name__)

OFFICE_SUFFIXES = {".docx", ".pptx"}


def convert_office_to_pdf(
    file_path: Path,
    doc_id: str,
    output_root: Path | None = None,
) -> Path | None:
    """Convert DOCX/PPTX to a derived PDF for page evidence.

    Returns the normalized ``source.pdf`` path when conversion succeeds. If
    LibreOffice is not installed or conversion fails, returns ``None`` so the
    parser can still process textual content where possible.
    """
    suffix = file_path.suffix.lower()
    if suffix not in OFFICE_SUFFIXES:
        return None

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        logger.warning("LibreOffice/soffice not found; skipping Office PDF conversion for %s", file_path)
        return None

    root = output_root or (get_data_dir() / "converted")
    output_dir = root / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    produced_pdf = output_dir / f"{file_path.stem}.pdf"
    normalized_pdf = output_dir / "source.pdf"
    for path in (produced_pdf, normalized_pdf):
        if path.exists():
            path.unlink()

    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(file_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        logger.warning("Office PDF conversion failed for %s: %s", file_path, exc)
        return None

    if not produced_pdf.exists():
        logger.warning("Office PDF conversion did not produce expected output: %s", produced_pdf)
        return None

    produced_pdf.replace(normalized_pdf)
    return normalized_pdf
