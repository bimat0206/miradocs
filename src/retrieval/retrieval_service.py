"""Retrieval service — stable search interface hiding backend details."""
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.config import get_config, get_data_dir
from src.retrieval.evidence_pack import normalize_chunk_to_result
from src.mcp.schemas import SearchDocsOutput, SearchResultItem

logger = logging.getLogger("retrieval_service")


class RetrievalService:
    """Unified search interface over vector stores and keyword fallback."""

    def __init__(self):
        self._cfg = get_config()
        self._retrieval_cfg = self._cfg.get("retrieval", {})
        self._max_text = self._retrieval_cfg.get("max_result_text_chars", 1800)

    def search_docs(
        self,
        query: str,
        top_k: int = 8,
        filters: dict | None = None,
        search_mode: str = "auto",
        include_page_images: bool = True,
        include_tables: bool = True,
    ) -> SearchDocsOutput:
        """Search documents and return normalized evidence results."""
        if not query.strip():
            return SearchDocsOutput(
                query=query, search_mode_used="none", top_k=top_k,
                result_count=0, results=[], warnings=["Empty query provided"],
            )

        max_top_k = self._cfg.get("mcp", {}).get("max_top_k", 20)
        top_k = min(top_k, max_top_k)

        results: list[dict] = []
        mode_used = "fallback"
        warnings: list[str] = []

        if search_mode in ("auto", "hybrid", "semantic"):
            results, mode_used = self._try_vector_search(query, top_k, filters)

        if not results and search_mode in ("auto", "keyword"):
            results = self._keyword_search(query, top_k, filters)
            mode_used = "keyword" if results else "fallback"
            if not results and search_mode == "keyword":
                warnings.append("Keyword search returned no results")

        if not results and search_mode in ("auto", "hybrid", "semantic"):
            # Final fallback
            results = self._keyword_search(query, top_k, filters)
            mode_used = "fallback"
            if not results:
                warnings.append("No results found in any search mode")

        # Normalize results
        items = [
            normalize_chunk_to_result(chunk, rank=i + 1, max_text_chars=self._max_text)
            for i, chunk in enumerate(results[:top_k])
        ]

        # Strip page images/tables if not requested
        if not include_page_images:
            for item in items:
                item.source_refs.pop("page_image", None)
        if not include_tables:
            for item in items:
                item.source_refs.pop("table_id", None)

        return SearchDocsOutput(
            query=query,
            search_mode_used=mode_used,
            top_k=top_k,
            result_count=len(items),
            results=items,
            warnings=warnings,
            next_actions=[
                "Use get_page_evidence(doc_id, page_number) to inspect the full page image.",
                "Use review agent to transform evidence chunks into findings.",
            ] if items else [],
        )

    def _try_vector_search(self, query: str, top_k: int, filters: dict | None) -> tuple[list[dict], str]:
        """Try vector search via existing adapters."""
        try:
            from src.indexing.hybrid_search import HybridSearchEngine
            engine = HybridSearchEngine()
            qdrant_filters = {}
            if filters:
                if filters.get("doc_id"):
                    qdrant_filters["doc_id"] = filters["doc_id"]
            results = engine.search(query, top_k=top_k, filters=qdrant_filters or None)
            if results:
                # Enrich with doc metadata
                return self._enrich_results(results, filters), "hybrid"
        except Exception as e:
            logger.warning("Vector search unavailable: %s", e)
        return [], ""

    def _keyword_search(self, query: str, top_k: int, filters: dict | None) -> list[dict]:
        """Keyword search over chunks.json files as fallback."""
        data_dir = get_data_dir()
        parsed_dir = data_dir / "parsed"
        if not parsed_dir.exists():
            return []

        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        if not query_terms:
            return []

        all_scored: list[tuple[float, dict]] = []

        for chunks_file in parsed_dir.rglob("chunks.json"):
            try:
                chunks = json.loads(chunks_file.read_text(encoding="utf-8"))
                doc_id = chunks_file.parent.name
                for chunk in chunks:
                    if not self._matches_filters(chunk, doc_id, filters):
                        continue
                    text_lower = chunk.get("text", "").lower()
                    section_lower = chunk.get("section_path", "").lower()
                    combined = text_lower + " " + section_lower
                    # Score: fraction of query terms found
                    matches = sum(1 for t in query_terms if t in combined)
                    if matches > 0:
                        score = matches / len(query_terms)
                        chunk_copy = {**chunk, "score": score, "doc_id": doc_id}
                        all_scored.append((score, chunk_copy))
            except Exception as e:
                logger.debug("Error reading %s: %s", chunks_file, e)

        all_scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in all_scored[:top_k]]

    def _matches_filters(self, chunk: dict, doc_id: str, filters: dict | None) -> bool:
        """Check if chunk matches provided filters."""
        if not filters:
            return True
        if filters.get("doc_id"):
            doc_id_filter = filters["doc_id"]
            if isinstance(doc_id_filter, list):
                if doc_id not in doc_id_filter:
                    return False
            elif doc_id != doc_id_filter:
                return False
        if filters.get("chunk_types") and chunk.get("chunk_type") not in filters["chunk_types"]:
            return False
        return True

    def _enrich_results(self, results: list[dict], filters: dict | None) -> list[dict]:
        """Enrich vector search results with doc metadata if available."""
        # Results from hybrid search already have most fields
        # Add source_file from registry if possible
        try:
            from src.intake.document_registry import DocumentRegistry
            registry = DocumentRegistry()
            for r in results:
                doc_id = r.get("doc_id", "")
                if doc_id:
                    doc = registry.get_document(doc_id)
                    if doc:
                        r["source_file"] = doc.get("filename", "")
                        r["document_type"] = doc.get("document_type", "")
                        r["domain"] = doc.get("domain", "")
        except Exception:
            pass
        return results
