"""Pydantic models for normalized document artifacts."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocManifest(BaseModel):
    doc_id: str
    project_name: str = "default"
    source_file_name: str
    source_file_path: str
    file_type: str
    sha256: str
    document_type: str = "Other"
    domain: str = "General"
    sensitivity: str = "Internal"
    page_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    parser: str = "docling"
    pipeline_status: str = "pending"


class SectionInfo(BaseModel):
    section_id: str
    section_path: str = ""
    title: str
    page_start: int = 0
    page_end: int = 0
    parent_section_id: Optional[str] = None
    level: int = 1


class PageInfo(BaseModel):
    page_number: int
    section_path: str = ""
    text_length: int = 0
    image_path: Optional[str] = None
    ocr_text_path: Optional[str] = None
    tables: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DocumentStructure(BaseModel):
    doc_id: str
    sections: list[SectionInfo] = Field(default_factory=list)
    pages: list[PageInfo] = Field(default_factory=list)
