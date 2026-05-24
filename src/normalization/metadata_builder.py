"""Metadata builder - assembles extraction results into normalized structure."""
import json
import logging
from pathlib import Path
from typing import Any

from src.config import get_data_dir
from src.normalization.document_object import (
    DocManifest, DocumentStructure, SectionInfo, PageInfo
)

logger = logging.getLogger(__name__)


def build_metadata(
    doc_id: str,
    doc_info: dict,
    parse_result: dict[str, Any],
    page_images: list[dict],
    tables: list[dict],
    figures: list[dict],
    entities: list[dict],
) -> tuple[DocManifest, DocumentStructure]:
    """Build normalized metadata from all extraction outputs."""

    # Build manifest
    manifest = DocManifest(
        doc_id=doc_id,
        project_name=doc_info.get("project", "default"),
        source_file_name=doc_info.get("filename", ""),
        source_file_path=doc_info.get("source_path", ""),
        file_type=doc_info.get("file_type", ""),
        sha256=doc_info.get("sha256", ""),
        document_type=doc_info.get("document_type", "Other"),
        domain=doc_info.get("domain", "General"),
        sensitivity=doc_info.get("sensitivity", "Internal"),
        page_count=parse_result.get("page_count", 0),
        parser=parse_result.get("parser", "unknown"),
    )

    # Build section hierarchy
    sections = _build_sections(parse_result.get("sections", []), parse_result.get("page_count", 0))

    # Build page info
    pages = _build_pages(
        page_count=parse_result.get("page_count", 0),
        page_images=page_images,
        tables=tables,
        figures=figures,
        sections=sections,
    )

    structure = DocumentStructure(doc_id=doc_id, sections=sections, pages=pages)

    # Save to disk
    parsed_dir = get_data_dir() / "parsed" / doc_id
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / "doc_manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (parsed_dir / "document_structure.json").write_text(
        structure.model_dump_json(indent=2), encoding="utf-8"
    )

    logger.info(f"Built metadata for {doc_id}: {len(sections)} sections, {len(pages)} pages")
    return manifest, structure


def _build_sections(raw_sections: list[dict], page_count: int) -> list[SectionInfo]:
    """Build section hierarchy with page ranges and paths."""
    sections = []
    parent_stack: list[SectionInfo] = []

    for s in raw_sections:
        level = s.get("level", 1)
        title = s.get("title", "")
        page_start = s.get("page_start", 0)

        # Pop parent stack to find correct parent
        while parent_stack and parent_stack[-1].level >= level:
            parent_stack.pop()

        parent_id = parent_stack[-1].section_id if parent_stack else None
        parent_path = parent_stack[-1].section_path if parent_stack else ""
        section_path = f"{parent_path} > {title}" if parent_path else title

        section = SectionInfo(
            section_id=s.get("section_id", f"sec_{len(sections):04d}"),
            section_path=section_path,
            title=title,
            page_start=page_start,
            page_end=page_start,  # Will be updated
            parent_section_id=parent_id,
            level=level,
        )
        sections.append(section)
        parent_stack.append(section)

    # Fix page_end for each section (extends to next section's start - 1)
    for i, sec in enumerate(sections):
        if i + 1 < len(sections):
            next_start = sections[i + 1].page_start
            sec.page_end = max(sec.page_start, next_start - 1) if next_start > sec.page_start else sec.page_start
        else:
            sec.page_end = page_count

    return sections


def _build_pages(
    page_count: int,
    page_images: list[dict],
    tables: list[dict],
    figures: list[dict],
    sections: list[SectionInfo],
) -> list[PageInfo]:
    """Build page info with linked artifacts."""
    # Index images by page
    img_map = {p["page_number"]: p["image_path"] for p in page_images}
    # Index tables by page
    table_map: dict[int, list[str]] = {}
    for t in tables:
        pg = t.get("page", 0)
        table_map.setdefault(pg, []).append(t.get("table_id", ""))
    # Index figures by page
    fig_map: dict[int, list[str]] = {}
    for f in figures:
        pg = f.get("page", 0)
        fig_map.setdefault(pg, []).append(f.get("figure_id", ""))

    pages = []
    for pg in range(1, page_count + 1):
        # Find section for this page
        section_path = ""
        for sec in reversed(sections):
            if sec.page_start <= pg <= sec.page_end:
                section_path = sec.section_path
                break

        pages.append(PageInfo(
            page_number=pg,
            section_path=section_path,
            image_path=img_map.get(pg),
            tables=table_map.get(pg, []),
            figures=fig_map.get(pg, []),
        ))

    return pages
