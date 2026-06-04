"""Shared chunk keyword search — used by both retrieval service and hybrid engine."""

import json
import logging
import re
from pathlib import Path

from src.config import get_data_dir

logger = logging.getLogger(__name__)

# Process-level chunk cache keyed by doc_id
_chunks_cache: dict[str, list[dict]] = {}


def _load_chunks_for_doc(doc_id: str) -> list[dict]:
    """Load chunks.json for a document, cached for process lifetime."""
    if doc_id not in _chunks_cache:
        path = get_data_dir() / "parsed" / doc_id / "chunks.json"
        try:
            _chunks_cache[doc_id] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _chunks_cache[doc_id] = []
    return _chunks_cache[doc_id]


def clear_chunk_cache() -> None:
    """Clear the chunk cache (e.g. after reprocessing)."""
    _chunks_cache.clear()


def keyword_search_chunks(
    query: str,
    top_k: int,
    doc_ids: list[str] | str | None = None,
    chunk_types: list[str] | None = None,
) -> list[dict]:
    """Score chunks by query-term coverage across parsed docs.

    Returns scored chunk dicts (highest first), each with a ``score`` key
    set to the fraction of query terms matched.
    """
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not query_terms:
        return []

    parsed_dir = get_data_dir() / "parsed"
    if not parsed_dir.exists():
        return []

    # Gather chunk files
    if doc_ids:
        ids = [doc_ids] if isinstance(doc_ids, str) else list(doc_ids)
        chunk_files = [parsed_dir / did / "chunks.json" for did in ids]
        chunk_files = [f for f in chunk_files if f.exists()]
    else:
        chunk_files = list(parsed_dir.rglob("chunks.json"))

    if not chunk_files:
        return []

    all_scored: list[tuple[float, dict]] = []

    for chunks_file in chunk_files:
        try:
            doc_id = chunks_file.parent.name
            chunks = _load_chunks_for_doc(doc_id)
        except Exception as e:
            logger.debug("Error reading %s: %s", chunks_file, e)
            continue

        for chunk in chunks:
            if chunk_types and chunk.get("chunk_type") not in chunk_types:
                continue
            text_lower = chunk.get("text", "").lower()
            section_lower = chunk.get("section_path", "").lower()
            combined = text_lower + " " + section_lower
            matches = sum(1 for t in query_terms if t in combined)
            if matches > 0:
                score = matches / len(query_terms)
                chunk_copy = {**chunk, "score": score, "doc_id": doc_id}
                all_scored.append((score, chunk_copy))

    all_scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in all_scored[:top_k]]
