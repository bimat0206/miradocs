"""Chunk candidate builder - generates typed chunks for indexing."""
import bisect
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.config import get_config, get_data_dir

logger = logging.getLogger(__name__)


def _stable_chunk_id(doc_id: str, chunk_type: str, page_start: int,
                     page_end: int, section_path: str, chunk_index: int,
                     text_prefix: str) -> str:
    """Deterministic chunk ID derived from content — stable across reruns."""
    raw = f"{doc_id}:{chunk_type}:{page_start}:{page_end}:{section_path}:{chunk_index}:{text_prefix[:128]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


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
    use_stable_ids = cfg["chunking"].get("stable_chunk_ids", True)
    use_section_first = cfg["chunking"].get("section_first_chunking", True)
    artifact_context_chars = cfg["chunking"].get("artifact_context_chars", 400)

    chunks = []
    img_map: dict[int, str] = {}
    for p in page_images:
        if not isinstance(p, dict):
            logger.warning("Skipping non-dict page_images entry in chunk builder: %r", p)
            continue
        pg = p.get("page_number")
        path = p.get("image_path")
        if pg is None or path is None:
            logger.warning("Skipping malformed page_images entry in chunk builder: %s", p)
            continue
        img_map[pg] = path

    # Precompute section starts for binary search (sections sorted by page_start).
    section_starts: list[int] = [s.get("page_start", 0) for s in sections]

    # Build lookup: section_path -> parent chunk ID for linking child/table/figure chunks.
    parent_by_section: dict[str, str] = {}

    # 1. Section-level parent chunks
    for sec in sections:
        page_start = sec.get("page_start", 0)
        page_end = sec.get("page_end", page_start)
        section_text = _get_text_for_pages(pages_text, page_start, page_end)
        section_path = sec.get("section_path", sec.get("title", ""))
        if section_text.strip():
            chunk = _make_chunk(
                doc_id=doc_id,
                chunk_type="parent_section_chunk",
                text=section_text[:max_chars],
                page_start=page_start,
                page_end=page_end,
                section_path=section_path,
                entities=_entities_for_pages(entities, page_start, page_end),
                source_refs={"page_image": img_map.get(page_start)},
                chunk_index=0,
                chunk_count=1,
                parent_chunk_id=None,
                stable_ids=use_stable_ids,
            )
            chunks.append(chunk)
            parent_by_section[section_path] = chunk["chunk_id"]

    # 2. Text chunks (child chunks) — section-first or page-fallback
    if use_section_first and sections:
        _build_section_child_chunks(chunks, doc_id, pages_text, sections,
                                    section_starts, parent_by_section, entities,
                                    img_map, max_chars, overlap_chars, use_stable_ids)
    else:
        _build_page_child_chunks(chunks, doc_id, pages_text, sections,
                                 section_starts, parent_by_section, entities,
                                 img_map, max_chars, overlap_chars, use_stable_ids)

    # 3. Table chunks
    for table in tables:
        pg = table.get("page", 0)
        md_path = table.get("file_md")
        text = ""
        if md_path and Path(md_path).exists():
            text = Path(md_path).read_text(encoding="utf-8")
        if not text:
            text = f"[Table {table.get('table_id', '')} on page {pg}]"
        text = text[:max_chars]
        section_path = _find_section_for_page(sections, section_starts, pg)
        context_text = _page_text_window(pages_text, pg, artifact_context_chars)
        refs: dict[str, Any] = {
            "page_image": img_map.get(pg),
            "table_id": table.get("table_id"),
            "context_text": context_text,
        }
        chunks.append(_make_chunk(
            doc_id=doc_id,
            chunk_type="table_chunk",
            text=text,
            page_start=pg,
            page_end=pg,
            section_path=section_path,
            entities=_entities_for_pages(entities, pg, pg),
            source_refs=refs,
            chunk_index=0,
            chunk_count=1,
            parent_chunk_id=parent_by_section.get(section_path),
            stable_ids=use_stable_ids,
        ))

    # 4. Figure chunks
    for fig in figures:
        pg = fig.get("page", 0)
        caption = fig.get("caption", "")
        text = caption if caption else f"[Figure {fig.get('figure_id', '')} on page {pg}]"
        section_path = _find_section_for_page(sections, section_starts, pg)
        context_text = _page_text_window(pages_text, pg, artifact_context_chars)
        refs = {
            "page_image": img_map.get(pg),
            "figure_id": fig.get("figure_id"),
            "figure_image": fig.get("image_path"),
            "context_text": context_text,
        }
        chunks.append(_make_chunk(
            doc_id=doc_id,
            chunk_type="figure_chunk",
            text=text,
            page_start=pg,
            page_end=pg,
            section_path=section_path,
            entities=_entities_for_pages(entities, pg, pg),
            source_refs=refs,
            chunk_index=0,
            chunk_count=1,
            parent_chunk_id=parent_by_section.get(section_path),
            stable_ids=use_stable_ids,
        ))

    # Save chunks
    output_dir = get_data_dir() / "parsed" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks.json").write_text(
        json.dumps(chunks, indent=2), encoding="utf-8"
    )
    logger.info(f"Generated {len(chunks)} chunks for {doc_id}")
    return chunks


# ─── Child chunk builders ──────────────────────────────────────────────


def _build_page_child_chunks(
    chunks: list[dict], doc_id: str, pages_text: list[dict],
    sections: list[dict], section_starts: list[int],
    parent_by_section: dict[str, str],
    entities: list[dict], img_map: dict[int, str],
    max_chars: int, overlap_chars: int, use_stable_ids: bool,
) -> None:
    """Page-level child chunks (original behaviour, fallback when no sections)."""
    for page_info in pages_text:
        pg = page_info.get("page", 0)
        text = page_info.get("text", "")
        if not text.strip():
            continue
        section_path = _find_section_for_page(sections, section_starts, pg)
        text_chunks = _split_text(text, max_chars, overlap_chars)
        count = len(text_chunks)
        for i, chunk_text in enumerate(text_chunks):
            chunks.append(_make_chunk(
                doc_id=doc_id,
                chunk_type="child_text_chunk",
                text=chunk_text,
                page_start=pg,
                page_end=pg,
                section_path=section_path,
                entities=_entities_for_pages(entities, pg, pg),
                source_refs={"page_image": img_map.get(pg)},
                chunk_index=i,
                chunk_count=count,
                parent_chunk_id=parent_by_section.get(section_path),
                stable_ids=use_stable_ids,
            ))


def _build_section_child_chunks(
    chunks: list[dict], doc_id: str, pages_text: list[dict],
    sections: list[dict], section_starts: list[int],
    parent_by_section: dict[str, str],
    entities: list[dict], img_map: dict[int, str],
    max_chars: int, overlap_chars: int, use_stable_ids: bool,
) -> None:
    """Section-first child chunking: group text by section, split semantically."""
    pages_by_number: dict[int, str] = {p.get("page", 0): p.get("text", "")
                                       for p in pages_text}
    page_count = max(pages_by_number.keys()) if pages_by_number else 0
    ranges = _section_ranges(sections, page_count)

    for sr in ranges:
        ps, pe, path = sr["page_start"], sr["page_end"], sr["section_path"]
        # Collect text across pages for this section
        parts: list[str] = []
        for pnum in range(ps, pe + 1):
            t = pages_by_number.get(pnum, "")
            if t.strip():
                parts.append(t)
        full_text = "\n".join(parts)
        if not full_text.strip():
            continue

        # Split at semantic boundaries then merge into token-sized chunks
        blocks = _split_semantic_blocks(full_text)
        text_chunks = _merge_blocks_to_chunks(blocks, max_chars, overlap_chars)

        parent_id = parent_by_section.get(path)
        count = len(text_chunks)
        for i, chunk_text in enumerate(text_chunks):
            chunks.append(_make_chunk(
                doc_id=doc_id,
                chunk_type="child_text_chunk",
                text=chunk_text,
                page_start=ps,
                page_end=pe,
                section_path=path,
                entities=_entities_for_pages(entities, ps, pe),
                source_refs={"page_image": img_map.get(ps)},
                chunk_index=i,
                chunk_count=count,
                parent_chunk_id=parent_id,
                stable_ids=use_stable_ids,
            ))


# ─── Section range helpers ─────────────────────────────────────────────


def _section_ranges(sections: list[dict], page_count: int) -> list[dict]:
    """Convert sections to (page_start, page_end, section_path) dicts.

    Fills gaps between sections so no page is left uncovered.
    Extends the last section's page_end to *page_count*.
    """
    if not sections:
        return []
    ranges: list[dict] = []
    for i, sec in enumerate(sections):
        ps = sec.get("page_start", 0)
        pe = sec.get("page_end", ps)
        path = sec.get("section_path", sec.get("title", ""))
        # Fill gap between previous section and this one
        if i > 0 and ps > ranges[-1]["page_end"] + 1:
            ranges.append({
                "page_start": ranges[-1]["page_end"] + 1,
                "page_end": ps - 1,
                "section_path": f"{ranges[-1]['section_path']} (continued)",
            })
        ranges.append({"page_start": ps, "page_end": pe, "section_path": path})
    # Extend last range to cover remaining pages
    if ranges and page_count > ranges[-1]["page_end"]:
        ranges[-1]["page_end"] = page_count
    return ranges


def _split_semantic_blocks(text: str) -> list[str]:
    """Split text at semantic boundaries while keeping blocks intact.

    Priority:
        1. headings (lines ending with === === or lines starting with #)
        2. numbered list blocks (consecutive numbered lines)
        3. bullet list blocks (consecutive bullet lines)
        4. paragraphs (double-newline separated)
    """
    blocks: list[str] = []
    lines = text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Heading detection: line of === or --- above, or # prefix
        if line.lstrip().startswith("#"):
            j = i + 1
            heading_lines = [line]
            while j < len(lines):
                if lines[j].strip() and not lines[j].lstrip().startswith("#"):
                    break
                heading_lines.append(lines[j])
                j += 1
            blocks.append("\n".join(heading_lines))
            i = j
            continue

        # Underline-style heading: previous line was empty, this line is === or ---
        if re.match(r"^[=\-]{3,}$", line.strip()):
            if blocks:
                blocks[-1] = blocks[-1] + "\n" + line
            else:
                blocks.append(line)
            i += 1
            continue

        # Numbered list
        if re.match(r"\s*\d+[.)]\s", line):
            j = i + 1
            lst = [line]
            while j < len(lines) and re.match(r"\s*\d+[.)]\s", lines[j]):
                lst.append(lines[j])
                j += 1
            blocks.append("\n".join(lst))
            i = j
            continue

        # Bullet list
        if re.match(r"\s*[-*•]\s", line):
            j = i + 1
            lst = [line]
            while j < len(lines) and re.match(r"\s*[-*•]\s", lines[j]):
                lst.append(lines[j])
                j += 1
            blocks.append("\n".join(lst))
            i = j
            continue

        # Paragraph: collect until next empty line
        j = i + 1
        para_lines = [line]
        while j < len(lines) and lines[j].strip():
            # Stop if next line is heading, list, or underline
            next_s = lines[j].strip()
            if (re.match(r"^\d+[.)]\s", next_s) or
                re.match(r"\s*[-*•]\s", next_s) or
                lines[j].lstrip().startswith("#") or
                re.match(r"^[=\-]{3,}$", next_s)):
                break
            para_lines.append(lines[j])
            j += 1
        blocks.append("\n".join(para_lines))
        i = j

    return blocks


def _merge_blocks_to_chunks(blocks: list[str], max_chars: int,
                            overlap_chars: int) -> list[str]:
    """Merge adjacent small blocks, split oversized ones.

    Returns a list of chunks each roughly ≤ max_chars.
    """
    if not blocks:
        return []

    merged: list[str] = []
    current = ""

    for block in blocks:
        # If single block already exceeds max, add it directly
        if len(block) > max_chars:
            if current:
                merged.append(current)
                current = ""
            # Split oversized block further via paragraph splitting
            if overlap_chars > 0:
                sub = _split_text(block, max_chars, overlap_chars)
            else:
                sub = _split_plain(block, max_chars)
            merged.extend(sub)
            continue

        # Merge as long as total stays within limit
        if not current:
            current = block
        elif len(current) + 1 + len(block) <= max_chars:
            current = current + "\n\n" + block
        else:
            merged.append(current)
            current = block

    if current:
        merged.append(current)

    return merged


def _split_plain(text: str, max_chars: int) -> list[str]:
    """Split text purely by character limit (no semantic)."""
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


# ─── Context window ────────────────────────────────────────────────────


def _page_text_window(pages_text: list[dict], page: int,
                      context_chars: int) -> str:
    """Get text from page N expanded to adjacent pages up to context_chars."""
    if not pages_text or context_chars <= 0:
        return ""

    text_map = {p.get("page", 0): p.get("text", "") for p in pages_text}
    page_nums = sorted(text_map.keys())
    target_idx = page_nums.index(page) if page in page_nums else -1
    if target_idx < 0:
        return text_map.get(page, "")

    parts: list[str] = []
    remaining = context_chars

    # Current page first
    current_text = text_map.get(page, "")
    if current_text:
        parts.append(current_text)
        remaining -= len(current_text)

    # Expand forward as needed
    for idx in range(target_idx + 1, len(page_nums)):
        if remaining <= 0:
            break
        t = text_map[page_nums[idx]]
        if t:
            take = t[:remaining]
            parts.append(take)
            remaining -= len(take)

    # Expand backward as needed
    for idx in range(target_idx - 1, -1, -1):
        if remaining <= 0:
            break
        t = text_map[page_nums[idx]]
        if t:
            take = t[-remaining:]
            parts.insert(0, take)
            remaining -= len(take)

    return "\n".join(parts)


# ─── Chunk factory ─────────────────────────────────────────────────────


def _make_chunk(doc_id: str, chunk_type: str, text: str, page_start: int,
                page_end: int, section_path: str, entities: dict,
                source_refs: dict, *,
                chunk_index: int = 0, chunk_count: int = 1,
                parent_chunk_id: str | None = None,
                stable_ids: bool = True) -> dict:
    chunk_id = (
        _stable_chunk_id(doc_id, chunk_type, page_start, page_end,
                         section_path, chunk_index, text)
        if stable_ids
        else hashlib.sha256(text.encode()).hexdigest()[:16]
    )
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "chunk_type": chunk_type,
        "page_start": page_start,
        "page_end": page_end,
        "section_path": section_path,
        "text": text,
        "entities": entities,
        "source_refs": source_refs,
        "quality_flags": [],
        "parent_chunk_id": parent_chunk_id,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
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


def _find_section_for_page(sections: list[dict], section_starts: list[int], page: int) -> str:
    """Find the section path for a given page using binary search."""
    idx = bisect.bisect_right(section_starts, page) - 1
    if idx < 0:
        return ""
    sec = sections[idx]
    start = sec.get("page_start", 0)
    end = sec.get("page_end", start)
    if start <= page <= end:
        return sec.get("section_path", sec.get("title", ""))
    return ""
