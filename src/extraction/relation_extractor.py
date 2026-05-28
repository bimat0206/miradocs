"""Entity co-occurrence graph builder for local GraphRAG.

Produces a per-document relations.json artifact containing nodes
(architecture entities) and edges (co-occurrence within a page window,
or optionally LLM-extracted predicates).

Public API
----------
build_relations(entities, doc_id, pages_text=None, data_dir=None) -> dict
    Build graph, save relations.json, return graph dict. Never raises.

load_graph(doc_id, data_dir=None) -> nx.Graph | None
    Load relations.json into a networkx.Graph. Returns None if missing.

get_entity_neighbors(graph, entity_type, entity_value, max_hops=1) -> list[dict]
    Return neighbors sorted by edge_weight descending.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("relation_extractor")

# Lazy import — avoids hard dependency at module import time
def _nx():
    try:
        import networkx as nx
        return nx
    except ImportError as e:
        raise ImportError(
            "networkx is required for GraphRAG. Install it with: pip install networkx>=3.3"
        ) from e


def _get_config():
    from src.config import get_config
    return get_config()


def _get_data_dir():
    from src.config import get_data_dir
    return get_data_dir()


# ─── Public API ───────────────────────────────────────────────────────────────

def build_relations(
    entities: list[dict],
    doc_id: str,
    pages_text: list[dict] | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Build entity graph from extracted entities, save to relations.json.

    Args:
        entities:   Output of extract_entities() —
                    [{"type": str, "value": str, "page": int, ...}, ...]
        doc_id:     Document identifier (used for output path).
        pages_text: Optional page text list. Required only when
                    cfg["graph"]["use_llm_relations"] is True.
        data_dir:   Override for the data root directory (useful in tests).

    Returns:
        The graph dict written to relations.json.

    Never raises — all errors are logged and a minimal empty graph is returned
    so the pipeline is never blocked by graph construction failures.
    """
    try:
        nx = _nx()
        cfg = _get_config()
        graph_cfg = cfg.get("graph", {})

        window = int(graph_cfg.get("co_occurrence_window_pages", 1))
        min_weight = int(graph_cfg.get("min_edge_weight", 1))
        use_llm = bool(graph_cfg.get("use_llm_relations", False))

        G = _build_cooccurrence_graph(entities, window, min_weight)

        if use_llm and pages_text:
            try:
                G_llm = _build_llm_relation_graph(entities, pages_text, cfg)
                # Merge: for shared edges, keep maximum weight
                for u, v, data in G_llm.edges(data=True):
                    if G.has_edge(u, v):
                        G[u][v]["weight"] = max(G[u][v].get("weight", 1), data.get("weight", 1))
                        # Keep co_occurs relation label if already set
                    else:
                        G.add_edge(u, v, **data)
                # Merge node attributes
                for node_id, node_data in G_llm.nodes(data=True):
                    if node_id not in G:
                        G.add_node(node_id, **node_data)
                    else:
                        # Merge occurrence counts
                        existing = G.nodes[node_id]
                        existing["occurrence_count"] = max(
                            existing.get("occurrence_count", 1),
                            node_data.get("occurrence_count", 1),
                        )
            except Exception as e:
                logger.warning("LLM relation graph build failed, using co-occurrence only: %s", e)

        result = _graph_to_dict(G, doc_id)

        root = data_dir or _get_data_dir()
        out_path = root / "parsed" / doc_id / "relations.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        logger.info(
            "Built entity graph for %s: %d nodes, %d edges",
            doc_id, result["node_count"], result["edge_count"],
        )
        return result

    except Exception as e:
        logger.error("build_relations failed for %s: %s", doc_id, e, exc_info=True)
        empty = {
            "doc_id": doc_id,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }
        try:
            root = data_dir or _get_data_dir()
            out_path = root / "parsed" / doc_id / "relations.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
        except Exception:
            pass
        return empty


def load_graph(doc_id: str, data_dir: Path | None = None):
    """Load persisted relations.json into a networkx.Graph.

    Returns:
        nx.Graph with node/edge attributes, or None if file does not exist.
    """
    try:
        nx = _nx()
        root = data_dir or _get_data_dir()
        path = root / "parsed" / doc_id / "relations.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        G = nx.Graph()

        for node in data.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                G.add_node(node_id, **{k: v for k, v in node.items() if k != "id"})

        for edge in data.get("edges", []):
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src and tgt:
                G.add_edge(src, tgt, **{k: v for k, v in edge.items() if k not in ("source", "target")})

        return G

    except Exception as e:
        logger.warning("load_graph failed for %s: %s", doc_id, e)
        return None


def get_entity_neighbors(
    graph,
    entity_type: str,
    entity_value: str,
    max_hops: int = 1,
) -> list[dict]:
    """Return neighbors of the named entity within max_hops, sorted by edge_weight desc.

    Each result dict has keys:
        id, type, value, edge_weight, relation, pages
    """
    try:
        nx = _nx()
        node_id = _make_node_id(entity_type, entity_value)
        if node_id not in graph:
            return []

        if max_hops == 1:
            neighbor_ids = list(graph.neighbors(node_id))
        else:
            # BFS up to max_hops
            visited = {node_id}
            frontier = {node_id}
            for _ in range(max_hops):
                next_frontier = set()
                for n in frontier:
                    for nb in graph.neighbors(n):
                        if nb not in visited:
                            next_frontier.add(nb)
                            visited.add(nb)
                frontier = next_frontier
            neighbor_ids = list(visited - {node_id})

        results = []
        for nb_id in neighbor_ids:
            nb_data = graph.nodes.get(nb_id, {})
            # Edge data: take direct edge if present, else 0
            if graph.has_edge(node_id, nb_id):
                edge_data = graph[node_id][nb_id]
            else:
                edge_data = {}
            results.append({
                "id": nb_id,
                "type": nb_data.get("type", ""),
                "value": nb_data.get("value", ""),
                "edge_weight": edge_data.get("weight", 1),
                "relation": edge_data.get("relation", "co_occurs"),
                "pages": edge_data.get("pages", []),
            })

        results.sort(key=lambda x: -x["edge_weight"])
        return results

    except Exception as e:
        logger.warning("get_entity_neighbors failed: %s", e)
        return []


# ─── Internal Helpers ──────────────────────────────────────────────────────────

def _make_node_id(entity_type: str, entity_value: str) -> str:
    """Return deterministic node ID: '{type}::{value}'."""
    return f"{entity_type}::{entity_value}"


def _build_cooccurrence_graph(
    entities: list[dict],
    window_pages: int,
    min_edge_weight: int,
):
    """Build weighted entity co-occurrence graph.

    Two entities co-occur when they appear within window_pages of each other.
    Edge weight = number of times the pair co-occurs.
    """
    nx = _nx()
    G = nx.Graph()

    # Group entity occurrences by page
    page_buckets: dict[int, list[dict]] = {}
    for ent in entities:
        page = int(ent.get("page", 0))
        page_buckets.setdefault(page, []).append(ent)

    # Performance guard: cap entities per page at 50 (drop lower-frequency)
    # to avoid O(n²) blowup on dense documents
    for page in page_buckets:
        if len(page_buckets[page]) > 50:
            page_buckets[page] = page_buckets[page][:50]

    # Add all entity nodes (deduplicated by id)
    node_first_seen: dict[str, int] = {}
    node_count: dict[str, int] = {}
    for ent in entities:
        nid = _make_node_id(ent["type"], ent["value"])
        page = int(ent.get("page", 0))
        if nid not in node_first_seen or page < node_first_seen[nid]:
            node_first_seen[nid] = page
        node_count[nid] = node_count.get(nid, 0) + 1
        if nid not in G:
            G.add_node(nid, type=ent["type"], value=ent["value"],
                       page_first_seen=page, occurrence_count=1)
        else:
            G.nodes[nid]["occurrence_count"] = node_count[nid]

    # Build co-occurrence edges
    pages = sorted(page_buckets.keys())
    for i, page in enumerate(pages):
        # Collect all entities in window [page, page+window_pages]
        window_entities: list[dict] = []
        for p in pages[i:]:
            if p > page + window_pages:
                break
            window_entities.extend(page_buckets[p])

        # Pair all distinct entities in window
        for j in range(len(window_entities)):
            for k in range(j + 1, len(window_entities)):
                a = window_entities[j]
                b = window_entities[k]
                a_id = _make_node_id(a["type"], a["value"])
                b_id = _make_node_id(b["type"], b["value"])
                if a_id == b_id:
                    continue
                if G.has_edge(a_id, b_id):
                    G[a_id][b_id]["weight"] = G[a_id][b_id].get("weight", 1) + 1
                    pages_list = G[a_id][b_id].get("pages", [])
                    if page not in pages_list:
                        pages_list.append(page)
                    G[a_id][b_id]["pages"] = pages_list
                else:
                    G.add_edge(a_id, b_id, weight=1, relation="co_occurs", pages=[page])

    # Prune edges below min_edge_weight
    low_weight_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("weight", 1) < min_edge_weight
    ]
    G.remove_edges_from(low_weight_edges)

    return G


def _build_llm_relation_graph(
    entities: list[dict],
    pages_text: list[dict],
    cfg: dict,
):
    """Build relation graph via LLM relation extraction (optional enrichment).

    Sends batches of pages to Ollama and asks for (subject, predicate, object) triples.
    Valid predicates: uses, connects_to, contains, depends_on, governs, routes_to.
    Falls back silently to an empty graph on any error.
    """
    nx = _nx()
    G = nx.Graph()

    try:
        import httpx
        ollama_url = cfg.get("embedding", {}).get("ollama_url", "http://localhost:11434")
        model = cfg["graph"]["ollama_model"]

        # Build entity value set for filtering LLM output
        known_entities: dict[str, dict] = {}
        for ent in entities:
            nid = _make_node_id(ent["type"], ent["value"])
            known_entities[ent["value"].lower()] = ent
            if nid not in G:
                G.add_node(nid, type=ent["type"], value=ent["value"],
                           page_first_seen=int(ent.get("page", 0)), occurrence_count=1)

        VALID_PREDICATES = {"uses", "connects_to", "contains", "depends_on", "governs", "routes_to"}
        BATCH_SIZE = 5

        for batch_start in range(0, len(pages_text), BATCH_SIZE):
            batch = pages_text[batch_start: batch_start + BATCH_SIZE]
            combined_text = "\n".join(
                f"[Page {p['page']}] {p['text'][:500]}" for p in batch
            )

            prompt = (
                "Extract architecture component relationships from the following text.\n"
                "Return a JSON array of objects with keys: "
                "source_type, source_value, target_type, target_value, relation.\n"
                f"Valid relations: {', '.join(sorted(VALID_PREDICATES))}.\n"
                "Only include relationships between named architecture entities "
                "(AWS/Azure services, CIDRs, VPCs, accounts, environments).\n"
                "Return ONLY the JSON array, no other text.\n\n"
                f"Text:\n{combined_text}"
            )

            try:
                resp = httpx.post(
                    f"{ollama_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=60,
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "")
                # Extract JSON array from response
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                if not match:
                    continue
                relations = json.loads(match.group(0))
                if not isinstance(relations, list):
                    continue

                for rel in relations:
                    src_type = str(rel.get("source_type", "")).strip()
                    src_val = str(rel.get("source_value", "")).strip()
                    tgt_type = str(rel.get("target_type", "")).strip()
                    tgt_val = str(rel.get("target_value", "")).strip()
                    predicate = str(rel.get("relation", "")).strip().lower()

                    if not all([src_type, src_val, tgt_type, tgt_val]):
                        continue
                    if predicate not in VALID_PREDICATES:
                        predicate = "uses"

                    src_id = _make_node_id(src_type, src_val)
                    tgt_id = _make_node_id(tgt_type, tgt_val)
                    if src_id == tgt_id:
                        continue

                    for nid, ntype, nval in [(src_id, src_type, src_val), (tgt_id, tgt_type, tgt_val)]:
                        if nid not in G:
                            G.add_node(nid, type=ntype, value=nval, page_first_seen=0, occurrence_count=1)

                    if G.has_edge(src_id, tgt_id):
                        G[src_id][tgt_id]["weight"] = G[src_id][tgt_id].get("weight", 1) + 1
                    else:
                        G.add_edge(src_id, tgt_id, weight=1, relation=predicate, pages=[])

            except Exception as e:
                logger.debug("LLM batch relation extraction failed: %s", e)
                continue

    except Exception as e:
        logger.warning("_build_llm_relation_graph failed: %s", e)

    return G


def _graph_to_dict(G, doc_id: str) -> dict:
    """Serialize nx.Graph to the relations.json dict format."""
    nx = _nx()
    nodes = []
    for node_id, data in G.nodes(data=True):
        nodes.append({
            "id": node_id,
            "type": data.get("type", ""),
            "value": data.get("value", ""),
            "page_first_seen": data.get("page_first_seen", 0),
            "occurrence_count": data.get("occurrence_count", 1),
        })

    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "weight": data.get("weight", 1),
            "relation": data.get("relation", "co_occurs"),
            "pages": data.get("pages", []),
        })

    return {
        "doc_id": doc_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
