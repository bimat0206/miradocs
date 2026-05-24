"""File manager for raw document storage and hash computation."""
import hashlib
from pathlib import Path
from typing import BinaryIO

from src.config import get_data_dir


def compute_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def get_raw_dir(project: str, doc_id: str) -> Path:
    path = get_data_dir() / "raw" / project / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_raw_file(file_bytes: bytes, filename: str, project: str, doc_id: str) -> Path:
    dest_dir = get_raw_dir(project, doc_id)
    dest = dest_dir / filename
    dest.write_bytes(file_bytes)
    return dest


def get_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    type_map = {
        ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx",
        ".xlsx": "xlsx", ".md": "markdown", ".txt": "text",
    }
    return type_map.get(suffix, "unknown")


def get_parsed_dir(doc_id: str) -> Path:
    path = get_data_dir() / "parsed" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_page_images_dir(doc_id: str) -> Path:
    path = get_data_dir() / "page_images" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_tables_dir(doc_id: str) -> Path:
    path = get_data_dir() / "tables" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_figures_dir(doc_id: str) -> Path:
    path = get_data_dir() / "figures" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_reports_dir(doc_id: str) -> Path:
    path = get_data_dir() / "reports" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path
