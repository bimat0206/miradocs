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
        graph_annotations: dict[str, str] = {}

        if search_mode == "graph_local":
            results, mode_used, graph_annotations = self._graph_local_search(query, top_k, filters)
        else:
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

        # Inject graph context annotations into why_relevant
        if graph_annotations:
            for item in items:
                if item.chunk_id in graph_annotations:
                    item.why_relevant = graph_annotations[item.chunk_id]

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

    # ─── Graph-local search ───────────────────────────────────────────────────

    def _graph_local_search(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> tuple[list[dict], str, dict[str, str]]:
        """Graph-local search: seed from hybrid, expand 1-hop via entity graph.

        Returns:
            (results, mode_used, graph_annotations)
            graph_annotations maps chunk_id -> why_relevant string for graph-expanded chunks.
        """
        cfg = self._cfg.get("graph", {})
        max_expanded = int(cfg.get("max_expanded_chunks", 5))

        # Step 1: Seed phase — use hybrid search as base
        seed_results, mode_used = self._try_vector_search(query, top_k * 2, filters)
        if not seed_results:
            seed_results = self._keyword_search(query, top_k, filters)
        if not seed_results:
            return [], "graph_local", {}

        # Step 2: Collect seed entities
        seed_entity_set: set[tuple[str, str]] = set()
        for chunk in seed_results:
            for etype, values in chunk.get("entities", {}).items():
                if isinstance(values, list):
                    for val in values:
                        seed_entity_set.add((etype, str(val)))

        if not seed_entity_set:
            return seed_results[:top_k], "graph_local", {}

        # Step 3: Load one graph per unique doc_id in seed results
        try:
            from src.extraction.relation_extractor import load_graph, get_entity_neighbors
        except ImportError:
            logger.warning("graph_local search: relation_extractor unavailable, falling back to seed results")
            return seed_results[:top_k], "graph_local", {}

        doc_ids = {c.get("doc_id", "") for c in seed_results if c.get("doc_id")}
        graphs: dict[str, Any] = {}
        for did in doc_ids:
            g = load_graph(did)
            if g is not None:
                graphs[did] = g

        if not graphs:
            # No graphs built yet — return seed results, degrade gracefully
            return seed_results[:top_k], "graph_local", {}

        # Step 4: Expand 1-hop from seed entities
        # neighbor_candidates: (doc_id, type, value, edge_weight)
        seen_nbr: dict[tuple[str, str], float] = {}
        for chunk in seed_results:
            did = chunk.get("doc_id", "")
            g = graphs.get(did)
            if not g:
                continue
            for etype, values in chunk.get("entities", {}).items():
                if not isinstance(values, list):
                    continue
                for val in values:
                    nbrs = get_entity_neighbors(g, etype, str(val), max_hops=1)
                    for nbr in nbrs:
                        nbr_key = (nbr["type"], nbr["value"])
                        if nbr_key not in seed_entity_set:
                            weight = float(nbr.get("edge_weight", 1))
                            if seen_nbr.get(nbr_key, -1.0) < weight:
                                seen_nbr[nbr_key] = weight

        # Step 5: Find chunks for top-N neighbor entities
        top_nbrs = sorted(seen_nbr.items(), key=lambda x: -x[1])[:max_expanded]

        seed_ids = {c.get("chunk_id", "") for c in seed_results}
        doc_chunks_cache: dict[str, list[dict]] = {}
        expanded_chunks: list[dict] = []

        for (ntype, nval), edge_weight in top_nbrs:
            for did in doc_ids:
                if did not in doc_chunks_cache:
                    doc_chunks_cache[did] = self._load_chunks_for_doc(did)
                for chunk in doc_chunks_cache[did]:
                    chunk_id = chunk.get("chunk_id", "")
                    if chunk_id in seed_ids:
                        continue
                    chunk_ents = chunk.get("entities", {})
                    if ntype in chunk_ents and nval in chunk_ents.get(ntype, []):
                        expanded_chunks.append({
                            **chunk,
                            "score": edge_weight * 0.5,
                            "doc_id": did,
                            "_from_graph": True,
                            "_graph_entity": f"{ntype}::{nval}",
                        })
                        seed_ids.add(chunk_id)  # prevent duplicates
                        break  # one chunk per expanded entity is enough

        # Step 6: Merge seed + expanded, deduplicated
        merged = list(seed_results) + expanded_chunks

        # Step 7: Build graph_annotations for expanded chunks
        graph_annotations: dict[str, str] = {
            chunk.get("chunk_id", ""): (
                f"Added via graph expansion: entity '{chunk['_graph_entity']}' "
                "co-occurs with a seed result entity."
            )
            for chunk in expanded_chunks
            if chunk.get("chunk_id")
        }

        return merged, "graph_local", graph_annotations

    def _load_chunks_for_doc(self, doc_id: str) -> list[dict]:
        """Load chunks.json for a document. Returns [] on any error."""
        path = get_data_dir() / "parsed" / doc_id / "chunks.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
