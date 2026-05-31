"""MCP tool definitions for architecture RAG."""
import json
import logging
from pathlib import Path

from src.config import get_data_dir
from src.mcp.schemas import (
    SearchDocsInput, SearchDocsOutput,
    ListDocsInput, ListDocsOutput, DocSummary,
    GetDocInfoInput, DocInfoOutput,
    GetPageEvidenceInput, PageEvidenceOutput,
    GetSectionInput, SectionContentOutput,
    GetEntitiesInput, GetEntitiesOutput,
    GetPageMatchesInput, GetPageMatchesOutput,
    GetPipelineStatusInput, GetIndexStatusInput,
    DetectCompareModeInput, ListCompareRunsInput, GetCompareRunInput,
    PutCrossSearchInput, PutCompareInput,
    GetEntityGraphInput, GetEntityGraphOutput, GraphNode, GraphEdge,
    GetEntityRelationshipsInput, GetEntityRelationshipsOutput, EntityRelationship,
)
from src.retrieval.retrieval_service import RetrievalService

logger = logging.getLogger("mcp.tools")

_retrieval: RetrievalService | None = None
_registry = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval
    if _retrieval is None:
        _retrieval = RetrievalService()
    return _retrieval


def _get_registry():
    global _registry
    if _registry is None:
        from src.intake.document_registry import DocumentRegistry
        _registry = DocumentRegistry()
    return _registry


def _load_json(path: Path) -> dict | list | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ─── search_docs ──────────────────────────────────────────────────────────────

def search_docs(params: SearchDocsInput) -> SearchDocsOutput:
    """Search local architecture document knowledge base for evidence."""
    logger.info("search_docs: query=%s, top_k=%d", params.query[:60], params.top_k)
    filters = {}
    if params.project:
        filters["project"] = params.project
    if params.doc_id:
        filters["doc_id"] = params.doc_id
    if params.doc_ids:
        filters["doc_id"] = params.doc_ids
    if params.domain:
        filters["domain"] = params.domain
    if params.document_type:
        filters["document_type"] = params.document_type
    if params.chunk_types:
        filters["chunk_types"] = params.chunk_types

    return get_retrieval_service().search_docs(
        query=params.query, top_k=params.top_k,
        filters=filters or None, search_mode=params.search_mode,
        include_page_images=params.include_page_images,
        include_tables=params.include_tables,
    )


# ─── list_documents ──────────────────────────────────────────────────────────

def list_documents(params: ListDocsInput) -> ListDocsOutput:
    """List all indexed documents with optional filters."""
    logger.info("list_documents: project=%s, domain=%s", params.project, params.domain)
    registry = _get_registry()
    docs = registry.list_documents()

    if params.project:
        docs = [d for d in docs if d["project"] == params.project]
    if params.domain:
        docs = [d for d in docs if d["domain"] == params.domain]
    if params.document_type:
        docs = [d for d in docs if d["document_type"] == params.document_type]
    if params.tag:
        docs = [d for d in docs if params.tag.casefold() in [t.casefold() for t in d.get("tags", [])]]

    data_dir = get_data_dir()

    def _page_count(doc_id: str) -> int:
        path = data_dir / "parsed" / doc_id / "doc_manifest.json"
        if not path.exists():
            return 0
        try:
            text = path.read_text(encoding="utf-8")
            import re
            m = re.search(r'"page_count"\s*:\s*(\d+)', text)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    summaries = [
        DocSummary(
            doc_id=d["doc_id"], filename=d["filename"], project=d["project"],
            document_type=d["document_type"], domain=d["domain"],
            sensitivity=d["sensitivity"], page_count=_page_count(d["doc_id"]),
            status=d["status"], upload_time=d["upload_time"],
        )
        for d in docs
    ]

    return ListDocsOutput(count=len(summaries), documents=summaries)


# ─── get_document_info ────────────────────────────────────────────────────────

def get_document_info(params: GetDocInfoInput) -> DocInfoOutput | dict:
    """Get detailed info about a specific document including structure and quality."""
    logger.info("get_document_info: doc_id=%s", params.doc_id)
    registry = _get_registry()
    doc = registry.get_document(params.doc_id)
    if not doc:
        return {"error": f"Document {params.doc_id} not found"}

    parsed_dir = get_data_dir() / "parsed" / params.doc_id

    # Load structure
    structure = _load_json(parsed_dir / "document_structure.json") or {}
    sections = structure.get("sections", [])

    # Load quality
    quality = _load_json(get_data_dir() / "reports" / params.doc_id / "quality_report.json") or {}

    # Load chunks count
    chunks = _load_json(parsed_dir / "chunks.json")
    chunk_count = len(chunks) if isinstance(chunks, list) else 0

    # Load entities summary
    entities_data = _load_json(parsed_dir / "entities.json") or {}
    entities_summary = {}
    for e in entities_data.get("summary", [])[:20]:
        t = e.get("type", "other")
        entities_summary.setdefault(t, []).append(e.get("value", ""))

    return DocInfoOutput(
        doc_id=doc["doc_id"], filename=doc["filename"], project=doc["project"],
        file_type=doc["file_type"], document_type=doc["document_type"],
        domain=doc["domain"], sensitivity=doc["sensitivity"], status=doc["status"],
        page_count=structure.get("pages", []).__len__() if structure else 0,
        sections=[{"title": s.get("title", ""), "page_start": s.get("page_start", 0), "level": s.get("level", 1)} for s in sections[:30]],
        quality_status=quality.get("status", "unknown"),
        chunk_count=chunk_count,
        entities_summary=entities_summary,
    )


# ─── get_page_evidence ────────────────────────────────────────────────────────

def get_page_evidence(params: GetPageEvidenceInput) -> PageEvidenceOutput | dict:
    """Get full evidence for a specific page: text, tables, figures, image path."""
    logger.info("get_page_evidence: doc_id=%s, page=%d", params.doc_id, params.page_number)
    parsed_dir = get_data_dir() / "parsed" / params.doc_id

    structure = _load_json(parsed_dir / "document_structure.json")
    if not structure:
        return {"error": f"No parsed structure for document {params.doc_id}"}

    pages = structure.get("pages", [])
    if params.page_number > len(pages) or params.page_number < 1:
        return {"error": f"Page {params.page_number} out of range (1-{len(pages)})"}

    page_info = pages[params.page_number - 1]

    # Get page text from PDF
    text = ""
    try:
        raw_path = _find_raw_file(params.doc_id)
        if raw_path and raw_path.suffix.lower() == ".pdf":
            import fitz
            doc = fitz.open(str(raw_path))
            if params.page_number <= len(doc):
                text = doc[params.page_number - 1].get_text("text")[:3000]
            doc.close()
    except Exception as e:
        logger.debug("Could not read page text: %s", e)

    # Get entities for this page
    entities_data = _load_json(parsed_dir / "entities.json") or {}
    page_entities = {}
    for ent in entities_data.get("entities", []):
        if ent.get("page") == params.page_number:
            t = ent.get("type", "other")
            page_entities.setdefault(t, []).append(ent.get("value", ""))

    img_dir = get_data_dir() / "page_images" / params.doc_id
    img_path = img_dir / f"page_{params.page_number:04d}.png"

    return PageEvidenceOutput(
        doc_id=params.doc_id,
        page_number=params.page_number,
        section_path=page_info.get("section_path", ""),
        text=text,
        tables=page_info.get("tables", []),
        figures=page_info.get("figures", []),
        page_image=str(img_path) if img_path.exists() else None,
        entities=page_entities,
    )


# ─── get_section_content ──────────────────────────────────────────────────────

def get_section_content(params: GetSectionInput) -> SectionContentOutput | dict:
    """Get all content for a specific section path."""
    logger.info("get_section_content: doc_id=%s, section=%s", params.doc_id, params.section_path[:50])
    parsed_dir = get_data_dir() / "parsed" / params.doc_id

    structure = _load_json(parsed_dir / "document_structure.json")
    if not structure:
        return {"error": f"No parsed structure for document {params.doc_id}"}

    # Find matching section
    sections = structure.get("sections", [])
    match = None
    for sec in sections:
        if params.section_path.lower() in sec.get("section_path", "").lower() or \
           params.section_path.lower() in sec.get("title", "").lower():
            match = sec
            break

    if not match:
        return {"error": f"Section '{params.section_path}' not found", "available_sections": [s.get("title", "") for s in sections[:20]]}

    page_start = match.get("page_start", 0)
    page_end = match.get("page_end", page_start)

    # Get chunks in this section
    chunks_data = _load_json(parsed_dir / "chunks.json") or []
    section_chunks = [
        {"chunk_id": c["chunk_id"], "chunk_type": c["chunk_type"], "page_start": c["page_start"], "text_preview": c.get("text", "")[:200]}
        for c in chunks_data
        if params.section_path.lower() in c.get("section_path", "").lower()
    ]

    # Get tables/figures in page range
    pages = structure.get("pages", [])
    tables, figures = [], []
    for pg in pages:
        pn = pg.get("page_number", 0)
        if page_start <= pn <= page_end:
            tables.extend(pg.get("tables", []))
            figures.extend(pg.get("figures", []))

    # Get section text
    text = ""
    try:
        raw_path = _find_raw_file(params.doc_id)
        if raw_path and raw_path.suffix.lower() == ".pdf":
            import fitz
            doc = fitz.open(str(raw_path))
            parts = []
            for pg in range(max(0, page_start - 1), min(len(doc), page_end)):
                parts.append(doc[pg].get_text("text"))
            doc.close()
            text = "\n".join(parts)[:5000]
    except Exception:
        pass

    return SectionContentOutput(
        doc_id=params.doc_id, section_path=match.get("section_path", params.section_path),
        page_start=page_start, page_end=page_end,
        text=text, chunks=section_chunks[:20],
        tables=tables, figures=figures,
    )


# ─── get_entities ─────────────────────────────────────────────────────────────

def get_entities(params: GetEntitiesInput) -> GetEntitiesOutput | dict:
    """Get extracted entities from a document, optionally filtered by type."""
    logger.info("get_entities: doc_id=%s, type=%s", params.doc_id, params.entity_type)
    parsed_dir = get_data_dir() / "parsed" / params.doc_id
    entities_data = _load_json(parsed_dir / "entities.json")
    if not entities_data:
        return {"error": f"No entities found for document {params.doc_id}"}

    summary = entities_data.get("summary", [])
    if params.entity_type:
        summary = [e for e in summary if e.get("type") == params.entity_type]

    return GetEntitiesOutput(
        doc_id=params.doc_id,
        entity_count=len(summary),
        entities=summary[:50],
    )


# ─── get_page_matches ────────────────────────────────────────────────────────

def get_page_matches(params: GetPageMatchesInput) -> GetPageMatchesOutput | dict:
    """Get normalized keyword match boxes for a PDF page image."""
    logger.info("get_page_matches: doc_id=%s, page=%d", params.doc_id, params.page_number)
    registry = _get_registry()
    doc = registry.get_document(params.doc_id)
    if not doc:
        return {"error": f"Document {params.doc_id} not found"}

    from src.services.document_service import page_image_matches
    return GetPageMatchesOutput(**page_image_matches(doc, params.page_number, params.query, get_data_dir()))


# ─── get_pipeline_status ─────────────────────────────────────────────────────

def get_pipeline_status(params: GetPipelineStatusInput) -> dict:
    """Get read-only pipeline steps plus persisted active/recent run metadata."""
    logger.info("get_pipeline_status: doc_id=%s", params.doc_id)
    registry = _get_registry()
    doc = registry.get_document(params.doc_id)
    if not doc:
        return {"error": f"Document {params.doc_id} not found"}

    steps = registry.get_pipeline_status(params.doc_id)
    active_run = registry.get_latest_pipeline_run(params.doc_id, ["queued", "running"])
    return {
        "doc_id": params.doc_id,
        "steps": steps,
        "active_run": active_run,
        "events": [event["payload"] for event in active_run["events"]] if active_run else [],
        "runs": registry.get_pipeline_runs(params.doc_id, limit=10) if params.include_runs else [],
    }


# ─── get_index_status ────────────────────────────────────────────────────────

def get_index_status(params: GetIndexStatusInput) -> dict:
    """Get read-only index state and adapter health."""
    logger.info("get_index_status: doc_id=%s", params.doc_id)
    registry = _get_registry()
    if not registry.get_document(params.doc_id):
        return {"error": f"Document {params.doc_id} not found"}

    from src.indexing.qdrant_adapter import QdrantAdapter
    from src.services.index_service import get_index_status as read_index_status
    return read_index_status(params.doc_id, get_data_dir(), registry, lambda: QdrantAdapter())


# ─── compare read tools ──────────────────────────────────────────────────────

def detect_compare_mode(params: DetectCompareModeInput) -> dict:
    """Detect the best compare mode for two documents without creating a run."""
    logger.info("detect_compare_mode: source=%s target=%s", params.source_doc_id, params.target_doc_id)
    registry = _get_registry()
    if params.source_doc_id == params.target_doc_id:
        return {"error": "Compare requires two different documents"}
    source_doc = registry.get_document(params.source_doc_id)
    target_doc = registry.get_document(params.target_doc_id)
    if not source_doc or not target_doc:
        return {"error": "Both documents must exist"}

    from src.services.compare_service import detect_compare_mode as detect
    return detect(source_doc, target_doc, get_data_dir())


def list_compare_runs(params: ListCompareRunsInput) -> dict:
    """List persisted compare runs for a document."""
    logger.info("list_compare_runs: doc_id=%s", params.doc_id)
    registry = _get_registry()
    if not registry.get_document(params.doc_id):
        return {"error": f"Document {params.doc_id} not found"}
    return {"doc_id": params.doc_id, "runs": registry.get_compare_runs_for_doc(params.doc_id, limit=params.limit)}


def get_compare_run(params: GetCompareRunInput) -> dict:
    """Get one persisted compare run and its findings."""
    logger.info("get_compare_run: run_id=%s", params.run_id)
    registry = _get_registry()
    result = registry.get_compare_run(params.run_id)
    if not result:
        return {"error": f"Compare run {params.run_id} not found"}
    return result


# ─── action tools ────────────────────────────────────────────────────────────

def put_cross_search(params: PutCrossSearchInput) -> dict:
    """Run an explicit two-document cross search and return grouped results."""
    logger.info("put_cross_search: source=%s target=%s", params.source_doc_id, params.target_doc_id)
    registry = _get_registry()
    source_doc = registry.get_document(params.source_doc_id)
    target_doc = registry.get_document(params.target_doc_id)
    if params.source_doc_id == params.target_doc_id:
        return {"error": "Cross search requires two different documents"}
    if not source_doc or not target_doc:
        return {"error": "Both documents must exist"}
    if not params.query.strip():
        return {"error": "Query cannot be empty"}

    result = get_retrieval_service().search_docs(
        query=params.query,
        top_k=params.top_k,
        filters={"doc_id": [params.source_doc_id, params.target_doc_id]},
        search_mode=params.search_mode,
        include_page_images=params.include_page_images,
        include_tables=params.include_tables,
    )
    items = [item.model_dump() for item in result.results]
    return {
        "query": result.query,
        "source_doc_id": params.source_doc_id,
        "target_doc_id": params.target_doc_id,
        "search_mode_used": result.search_mode_used,
        "result_count": result.result_count,
        "results": items,
        "results_by_doc": {
            params.source_doc_id: [item for item in items if item["doc_id"] == params.source_doc_id],
            params.target_doc_id: [item for item in items if item["doc_id"] == params.target_doc_id],
        },
        "warnings": result.warnings,
        "next_actions": result.next_actions,
    }


def put_compare(params: PutCompareInput) -> dict:
    """Create and persist a deterministic compare run."""
    logger.info("put_compare: source=%s target=%s mode=%s", params.source_doc_id, params.target_doc_id, params.mode)
    registry = _get_registry()
    try:
        from src.services.compare_service import CompareError, run_compare
        return run_compare(
            source_doc_id=params.source_doc_id,
            target_doc_id=params.target_doc_id,
            mode=params.mode,
            registry=registry,
            data_dir=get_data_dir(),
        )
    except CompareError as exc:
        return {"error": str(exc)}


# ─── get_entity_graph ─────────────────────────────────────────────────────────

def get_entity_graph(params: GetEntityGraphInput) -> GetEntityGraphOutput | dict:
    """Return the persisted entity co-occurrence graph for a document."""
    logger.info("get_entity_graph: doc_id=%s, entity_type=%s", params.doc_id, params.entity_type)
    parsed_dir = get_data_dir() / "parsed" / params.doc_id
    relations_path = parsed_dir / "relations.json"
    if not relations_path.exists():
        return {
            "error": (
                f"No entity graph found for document {params.doc_id}. "
                "Re-index the document to build the graph."
            )
        }

    data = _load_json(relations_path)
    if not isinstance(data, dict):
        return {"error": "relations.json is malformed"}

    nodes_raw = data.get("nodes", [])
    edges_raw = data.get("edges", [])

    # Filter nodes by entity_type if requested
    if params.entity_type:
        valid_ids = {n["id"] for n in nodes_raw if n.get("type") == params.entity_type}
        nodes_raw = [n for n in nodes_raw if n["id"] in valid_ids]
        edges_raw = [
            e for e in edges_raw
            if e.get("source") in valid_ids or e.get("target") in valid_ids
        ]

    # Filter edges by min_edge_weight
    edges_raw = [e for e in edges_raw if e.get("weight", 1) >= params.min_edge_weight]

    nodes = [GraphNode(**{k: v for k, v in n.items() if k in GraphNode.model_fields}) for n in nodes_raw]
    edges = [GraphEdge(**{k: v for k, v in e.items() if k in GraphEdge.model_fields}) for e in edges_raw]

    return GetEntityGraphOutput(
        doc_id=params.doc_id,
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=nodes,
        edges=edges,
    )


# ─── get_entity_relationships ─────────────────────────────────────────────────

def get_entity_relationships(params: GetEntityRelationshipsInput) -> GetEntityRelationshipsOutput | dict:
    """Return all entities connected to a named entity in the document graph."""
    logger.info(
        "get_entity_relationships: doc_id=%s, %s::%s",
        params.doc_id, params.entity_type, params.entity_value,
    )
    try:
        from src.extraction.relation_extractor import load_graph, get_entity_neighbors
    except ImportError:
        return {"error": "relation_extractor module unavailable (networkx may not be installed)"}

    graph = load_graph(params.doc_id)
    if graph is None:
        return {
            "error": (
                f"No entity graph found for document {params.doc_id}. "
                "Re-index the document to build the graph."
            )
        }

    neighbors = get_entity_neighbors(
        graph, params.entity_type, params.entity_value, params.max_hops
    )

    entity_id = f"{params.entity_type}::{params.entity_value}"
    relationships = [
        EntityRelationship(
            neighbor_id=n["id"],
            neighbor_type=n["type"],
            neighbor_value=n["value"],
            edge_weight=int(n.get("edge_weight", 1)),
            relation=n.get("relation", "co_occurs"),
            pages=n.get("pages", []),
        )
        for n in neighbors
    ]

    return GetEntityRelationshipsOutput(
        doc_id=params.doc_id,
        entity_id=entity_id,
        entity_type=params.entity_type,
        entity_value=params.entity_value,
        neighbor_count=len(relationships),
        relationships=relationships,
    )


# ─── Helper ──────────────────────────────────────────────────────────────────

def _find_raw_file(doc_id: str) -> Path | None:
    registry = _get_registry()
    doc = registry.get_document(doc_id)
    if not doc:
        return None
    raw_dir = get_data_dir() / "raw" / doc["project"] / doc_id
    if raw_dir.exists():
        files = list(raw_dir.iterdir())
        return files[0] if files else None
    return None
