"""Chunk candidate builder - generates typed chunks for indexing."""
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from src.config import get_config, get_data_dir

logger = logging.getLogger(__name__)


def build_chunks(
    doc_id: str,
    pages_text: list[dict],
    sections: list[dict],
    tables: list[dict],
    figures: list[dict],
    entities: list[dict],
    page_images: list[dict],
) -> list[dict]:
    """Generate chunk candidates from all extraction outputs."""
    cfg = get_config()
    max_tokens = cfg["chunking"]["max_chunk_tokens"]
    max_chars = max_tokens * 4  # rough char estimate
    overlap_chars = cfg["chunking"].get("overlap_tokens", 0) * 4

    chunks = []
    img_map = {p["page_number"]: p["image_path"] for p in page_images}

    # 1. Section-level parent chunks
    for sec in sections:
        page_start = sec.get("page_start", 0)
        page_end = sec.get("page_end", page_start)
        section_text = _get_text_for_pages(pages_text, page_start, page_end)
        if section_text.strip():
            chunks.append(_make_chunk(
                doc_id=doc_id,
                chunk_type="parent_section_chunk",
                text=section_text[:max_chars],
                page_start=page_start,
                page_end=page_end,
                section_path=sec.get("section_path", sec.get("title", "")),
                entities=_entities_for_pages(entities, page_start, page_end),
                source_refs={"page_image": img_map.get(page_start)},
            ))

    # 2. Page-level text chunks (child chunks)
    for page_info in pages_text:
        pg = page_info.get("page", 0)
        text = page_info.get("text", "")
        if not text.strip():
            continue
        # Split long pages into sub-chunks with overlap
        for i, chunk_text in enumerate(_split_text(text, max_chars, overlap_chars)):
            section_path = _find_section_for_page(sections, pg)
            chunks.append(_make_chunk(
                doc_id=doc_id,
                chunk_type="child_text_chunk",
                text=chunk_text,
                page_start=pg,
                page_end=pg,
                section_path=section_path,
                entities=_entities_for_pages(entities, pg, pg),
                source_refs={"page_image": img_map.get(pg)},
            ))

    # 3. Table chunks
    for table in tables:
        pg = table.get("page", 0)
        md_path = table.get("file_md")
        text = ""
        if md_path and Path(md_path).exists():
            text = Path(md_path).read_text(encoding="utf-8")
        if not text:
            text = f"[Table {table.get('table_id', '')} on page {pg}]"
        chunks.append(_make_chunk(
            doc_id=doc_id,
            chunk_type="table_chunk",
            text=text[:max_chars],
            page_start=pg,
            page_end=pg,
            section_path=_find_section_for_page(sections, pg),
            entities=_entities_for_pages(entities, pg, pg),
            source_refs={"page_image": img_map.get(pg), "table_id": table.get("table_id")},
        ))

    # 4. Figure chunks
    for fig in figures:
        pg = fig.get("page", 0)
        caption = fig.get("caption", "")
        text = caption if caption else f"[Figure {fig.get('figure_id', '')} on page {pg}]"
        chunks.append(_make_chunk(
            doc_id=doc_id,
            chunk_type="figure_chunk",
            text=text,
            page_start=pg,
            page_end=pg,
            section_path=_find_section_for_page(sections, pg),
            entities=_entities_for_pages(entities, pg, pg),
            source_refs={
                "page_image": img_map.get(pg),
                "figure_id": fig.get("figure_id"),
                "figure_image": fig.get("image_path"),
            },
        ))

    # Save chunks
    output_dir = get_data_dir() / "parsed" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks.json").write_text(
        json.dumps(chunks, indent=2), encoding="utf-8"
    )
    logger.info(f"Generated {len(chunks)} chunks for {doc_id}")
    return chunks


def _make_chunk(doc_id: str, chunk_type: str, text: str, page_start: int,
                page_end: int, section_path: str, entities: dict,
                source_refs: dict) -> dict:
    return {
        "chunk_id": uuid.uuid4().hex[:16],
        "doc_id": doc_id,
        "chunk_type": chunk_type,
        "page_start": page_start,
        "page_end": page_end,
        "section_path": section_path,
        "text": text,
        "entities": entities,
        "source_refs": source_refs,
        "quality_flags": [],
    }


def _get_text_for_pages(pages_text: list[dict], start: int, end: int) -> str:
    parts = []
    for p in pages_text:
        pg = p.get("page", 0)
        if start <= pg <= end:
            parts.append(p.get("text", ""))
    return "\n".join(parts)


def _split_text(text: str, max_chars: int, overlap_chars: int = 0) -> list[str]:
    """Split text into chunks at paragraph boundaries, with optional tail overlap."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current:
                chunks.append(current)
            current = para[:max_chars]
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current)
    result = chunks if chunks else [text[:max_chars]]
    if overlap_chars <= 0 or len(result) <= 1:
        return result
    # Prepend tail of previous chunk to each subsequent chunk so context
    # at split boundaries is present in both neighbours.
    overlapped = [result[0]]
    for i in range(1, len(result)):
        tail = result[i - 1][-overlap_chars:]
        overlapped.append(tail + "\n\n" + result[i])
    return overlapped


def _entities_for_pages(entities: list[dict], start: int, end: int) -> dict:
    """Group entities by type for given page range."""
    result: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for e in entities:
        pg = e.get("page", 0)
        if start <= pg <= end:
            key = (e["type"], e["value"])
            if key not in seen:
                seen.add(key)
                result.setdefault(e["type"], []).append(e["value"])
    return result


def _find_section_for_page(sections: list[dict], page: int) -> str:
    """Find the section path for a given page."""
    for sec in reversed(sections):
        if sec.get("page_start", 0) <= page <= sec.get("page_end", sec.get("page_start", 0)):
            return sec.get("section_path", sec.get("title", ""))
    return ""
