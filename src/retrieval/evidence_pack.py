"""Evidence result normalization for MCP responses."""
from src.config import get_data_dir
from src.mcp.schemas import SearchResultItem


def normalize_chunk_to_result(chunk: dict, rank: int, max_text_chars: int = 1800) -> SearchResultItem:
    """Convert a raw chunk dict into a normalized SearchResultItem."""
    text = chunk.get("text", "")
    return SearchResultItem(
        rank=rank,
        score=round(chunk.get("score", 0.0), 4),
        doc_id=chunk.get("doc_id", ""),
        source_file=chunk.get("source_file", ""),
        document_type=chunk.get("document_type", ""),
        domain=chunk.get("domain", ""),
        chunk_id=chunk.get("chunk_id", ""),
        chunk_type=chunk.get("chunk_type", ""),
        page_start=chunk.get("page_start", 0),
        page_end=chunk.get("page_end", chunk.get("page_start", 0)),
        section_path=chunk.get("section_path", ""),
        text=text[:max_text_chars],
        text_preview=text[:200],
        entities=chunk.get("entities", {}),
        source_refs=_sanitize_refs(chunk.get("source_refs", {})),
        why_relevant=chunk.get("why_relevant", ""),
    )


def _sanitize_refs(refs: dict) -> dict:
    """Ensure source_refs paths are within data directory."""
    data_dir = str(get_data_dir())
    sanitized = {}
    for key, val in refs.items():
        if isinstance(val, str) and val:
            # Only include paths that are relative or within data_dir
            if val.startswith(data_dir) or not val.startswith("/"):
                sanitized[key] = val
            else:
                sanitized[key] = None
        else:
            sanitized[key] = val
    return sanitized
