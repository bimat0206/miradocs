"""Retrieval service — stable search interface hiding backend details."""
import json
import logging
from typing import Any

from src.config import get_config, get_data_dir
from src.indexing.chunk_keyword_search import keyword_search_chunks
from src.retrieval.evidence_pack import normalize_chunk_to_result
from src.mcp.schemas import SearchDocsOutput, SearchResultItem

logger = logging.getLogger("retrieval_service")

# Module-level singletons — created once per process
_hybrid_engine = None
_registry = None
# Process-level chunk cache keyed by doc_id; invalidated on server restart
_chunks_cache: dict[str, list[dict]] = {}


def _get_hybrid_engine():
    global _hybrid_engine
    if _hybrid_engine is None:
        from src.indexing.hybrid_search import HybridSearchEngine
        _hybrid_engine = HybridSearchEngine()
    return _hybrid_engine


def _get_registry():
    global _registry
    if _registry is None:
        from src.intake.document_registry import DocumentRegistry
        _registry = DocumentRegistry()
    return _registry


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

        # Resolve version group filters to document IDs
        filters = self._resolve_version_filters(filters)

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

        # Enrich results with doc metadata and version info
        results = self._enrich_results(results, filters)

        # Add parent section context before normalizing
        results = self._expand_parent_context(results)

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
            engine = _get_hybrid_engine()
            qdrant_filters = {}
            if filters:
                if filters.get("doc_id"):
                    qdrant_filters["doc_id"] = filters["doc_id"]
            results = engine.search(query, top_k=top_k, filters=qdrant_filters or None)
            if results:
                return results, "hybrid"
        except Exception as e:
            logger.warning("Vector search unavailable: %s", e)
        return [], ""

    def _keyword_search(self, query: str, top_k: int, filters: dict | None) -> list[dict]:
        """Keyword search over chunks.json files as fallback."""
        doc_id_filter = (filters or {}).get("doc_id")
        chunk_types = (filters or {}).get("chunk_types")
        results = keyword_search_chunks(query, top_k, doc_ids=doc_id_filter, chunk_types=chunk_types)
        if doc_id_filter:
            ids = [doc_id_filter] if isinstance(doc_id_filter, str) else list(doc_id_filter)
            results = [r for r in results if r.get("doc_id") in ids]
        return results

    def _expand_parent_context(self, results: list[dict]) -> list[dict]:
        """For each result with a parent_chunk_id, resolve parent text and inject."""
        expand = self._retrieval_cfg.get("expand_parent_context", True)
        if not expand:
            return results
        max_chars = self._retrieval_cfg.get("parent_context_max_chars", 1800)
        for result in results:
            parent_id = result.get("parent_chunk_id")
            doc_id = result.get("doc_id", "")
            if not parent_id or not doc_id:
                continue
            doc_chunks = self._load_chunks_for_doc(doc_id)
            parent = next((c for c in doc_chunks if c.get("chunk_id") == parent_id), None)
            if parent:
                result["parent_text"] = parent.get("text", "")[:max_chars]
                result["parent_chunk_id"] = parent_id
                result["parent_section_path"] = parent.get("section_path", "")
        return results

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
        """Enrich results with doc metadata and version info if available."""
        try:
            registry = _get_registry()
            doc_ids = list({r.get("doc_id", "") for r in results if r.get("doc_id")})
            docs = {d["doc_id"]: d for d in registry.get_documents_batch(doc_ids)}
            for r in results:
                did = r.get("doc_id", "")
                doc = docs.get(did)
                if doc:
                    r["source_file"] = doc.get("filename", "")
                    r["document_type"] = doc.get("document_type", "")
                    r["domain"] = doc.get("domain", "")

                if did:
                    v = registry.get_version_for_doc(did)
                    if v:
                        r["version_label"] = v.get("version_label")
                        r["version_number"] = v.get("version_number")
        except Exception as e:
            logger.error("Failed to enrich results: %s", e)
        return results

    def _resolve_version_filters(self, filters: dict | None) -> dict | None:
        """Resolve version_group_id and version_number into concrete doc_ids."""
        if not filters:
            return None

        version_group_id = filters.get("version_group_id")
        version_number = filters.get("version_number")

        if not version_group_id:
            return filters

        # Clone filters to avoid side-effects
        resolved = dict(filters)

        registry = _get_registry()
        versions = registry.get_versions_for_group(version_group_id)
        if version_number is not None:
            versions = [v for v in versions if v["version_number"] == version_number]

        doc_ids = [v["doc_id"] for v in versions]

        # Override doc_id filter
        if doc_ids:
            existing_doc_id = filters.get("doc_id")
            if existing_doc_id:
                existing_ids = [existing_doc_id] if isinstance(existing_doc_id, str) else list(existing_doc_id)
                resolved["doc_id"] = [did for did in doc_ids if did in existing_ids]
            else:
                resolved["doc_id"] = doc_ids
        else:
            resolved["doc_id"] = ["__nonexistent_doc_id__"]

        return resolved

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
        """Load chunks.json for a document, cached for the process lifetime."""
        if doc_id not in _chunks_cache:
            path = get_data_dir() / "parsed" / doc_id / "chunks.json"
            try:
                _chunks_cache[doc_id] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                _chunks_cache[doc_id] = []
        return _chunks_cache[doc_id]
