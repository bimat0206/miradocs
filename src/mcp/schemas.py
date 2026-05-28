"""MCP tool input/output schemas."""
from pydantic import BaseModel, Field


class SearchDocsInput(BaseModel):
    query: str = Field(..., description="Search query for architecture documents")
    top_k: int = Field(default=8, ge=1, le=20, description="Number of results to return (max 20)")
    project: str | None = Field(default=None, description="Filter by project name")
    doc_id: str | None = Field(default=None, description="Filter by specific document ID")
    doc_ids: list[str] | None = Field(default=None, description="Filter by multiple document IDs")
    domain: str | None = Field(default=None, description="Filter by domain: Networking, Security, Governance, etc.")
    document_type: str | None = Field(default=None, description="Filter by type: HLD, LLD, Design Review, etc.")
    chunk_types: list[str] | None = Field(default=None, description="Filter by chunk types: child_text_chunk, table_chunk, figure_chunk, etc.")
    include_page_images: bool = Field(default=True, description="Include page image paths in results")
    include_tables: bool = Field(default=True, description="Include table references in results")
    search_mode: str = Field(default="auto", description="Search mode: auto, semantic, keyword, hybrid, graph_local")


class SearchResultItem(BaseModel):
    rank: int
    score: float
    doc_id: str
    source_file: str = ""
    document_type: str = ""
    domain: str = ""
    chunk_id: str
    chunk_type: str
    page_start: int
    page_end: int
    section_path: str
    text: str
    text_preview: str
    entities: dict = Field(default_factory=dict)
    source_refs: dict = Field(default_factory=dict)
    why_relevant: str = ""


class SearchDocsOutput(BaseModel):
    query: str
    search_mode_used: str
    top_k: int
    result_count: int
    results: list[SearchResultItem]
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


# ─── list_documents ───────────────────────────────────────────────────────────

class ListDocsInput(BaseModel):
    project: str | None = Field(default=None, description="Filter by project name")
    domain: str | None = Field(default=None, description="Filter by domain")
    document_type: str | None = Field(default=None, description="Filter by document type")


class DocSummary(BaseModel):
    doc_id: str
    filename: str
    project: str
    document_type: str
    domain: str
    sensitivity: str
    page_count: int = 0
    status: str
    upload_time: str


class ListDocsOutput(BaseModel):
    count: int
    documents: list[DocSummary]


# ─── get_document_info ────────────────────────────────────────────────────────

class GetDocInfoInput(BaseModel):
    doc_id: str = Field(..., description="Document ID to retrieve info for")


class DocInfoOutput(BaseModel):
    doc_id: str
    filename: str
    project: str
    file_type: str
    document_type: str
    domain: str
    sensitivity: str
    status: str
    page_count: int = 0
    sections: list[dict] = Field(default_factory=list)
    quality_status: str = ""
    chunk_count: int = 0
    entities_summary: dict = Field(default_factory=dict)


# ─── get_page_evidence ────────────────────────────────────────────────────────

class GetPageEvidenceInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    page_number: int = Field(..., ge=1, description="Page number to inspect")


class PageEvidenceOutput(BaseModel):
    doc_id: str
    page_number: int
    section_path: str = ""
    text: str = ""
    tables: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    page_image: str | None = None
    entities: dict = Field(default_factory=dict)


# ─── get_section_content ──────────────────────────────────────────────────────

class GetSectionInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    section_path: str = Field(..., description="Section path like '4. Networking > 4.2 Transit Gateway'")


class SectionContentOutput(BaseModel):
    doc_id: str
    section_path: str
    page_start: int = 0
    page_end: int = 0
    text: str = ""
    chunks: list[dict] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)


# ─── get_entities ─────────────────────────────────────────────────────────────

class GetEntitiesInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    entity_type: str | None = Field(default=None, description="Filter: aws_service, cidr, environment, governance, etc.")


class GetEntitiesOutput(BaseModel):
    doc_id: str
    entity_count: int
    entities: list[dict] = Field(default_factory=list)


# ─── get_page_matches ─────────────────────────────────────────────────────────

class GetPageMatchesInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    page_number: int = Field(..., ge=1, description="Page number to inspect")
    query: str = Field(..., description="Terms to locate on the page image")


class PageImageMatch(BaseModel):
    text: str
    term: str
    x: float
    y: float
    width: float
    height: float


class GetPageMatchesOutput(BaseModel):
    doc_id: str
    page: int
    query: str
    page_width: float = 0
    page_height: float = 0
    matches: list[PageImageMatch] = Field(default_factory=list)


# ─── pipeline/index status ───────────────────────────────────────────────────

class GetPipelineStatusInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    include_runs: bool = Field(default=True, description="Include recent persisted pipeline runs")


class GetIndexStatusInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")


# ─── compare read tools ───────────────────────────────────────────────────────

class DetectCompareModeInput(BaseModel):
    source_doc_id: str = Field(..., description="Source document ID")
    target_doc_id: str = Field(..., description="Target document ID")


class ListCompareRunsInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    limit: int = Field(default=20, ge=1, le=50, description="Maximum compare runs to return")


class GetCompareRunInput(BaseModel):
    run_id: str = Field(..., description="Compare run ID")


# ─── action tools ─────────────────────────────────────────────────────────────

class PutCrossSearchInput(BaseModel):
    source_doc_id: str = Field(..., description="First document ID")
    target_doc_id: str = Field(..., description="Second document ID")
    query: str = Field(..., description="Search query to run across both documents")
    top_k: int = Field(default=8, ge=1, le=20, description="Total results to return across both documents")
    search_mode: str = Field(default="auto", description="Search mode: auto, semantic, keyword, hybrid, graph_local")
    include_page_images: bool = Field(default=True, description="Include page image paths in results")
    include_tables: bool = Field(default=True, description="Include table references in results")


class PutCompareInput(BaseModel):
    source_doc_id: str = Field(..., description="Source document ID")
    target_doc_id: str = Field(..., description="Target document ID")
    mode: str = Field(default="auto", description="Compare mode or auto")


# ─── get_entity_graph ─────────────────────────────────────────────────────────

class GetEntityGraphInput(BaseModel):
    doc_id: str = Field(..., description="Document ID to retrieve entity graph for")
    entity_type: str | None = Field(
        default=None,
        description="Filter nodes by type: aws_service, cidr, environment, governance, azure_service",
    )
    min_edge_weight: int = Field(
        default=1,
        ge=1,
        description="Only include edges with weight >= this value",
    )


class GraphNode(BaseModel):
    id: str
    type: str
    value: str
    page_first_seen: int = 0
    occurrence_count: int = 0


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int = 1
    relation: str = "co_occurs"
    pages: list[int] = Field(default_factory=list)


class GetEntityGraphOutput(BaseModel):
    doc_id: str
    node_count: int
    edge_count: int
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ─── get_entity_relationships ─────────────────────────────────────────────────

class GetEntityRelationshipsInput(BaseModel):
    doc_id: str = Field(..., description="Document ID")
    entity_type: str = Field(
        ...,
        description="Entity type: aws_service, cidr, environment, governance, azure_service",
    )
    entity_value: str = Field(
        ...,
        description="Entity value to look up, e.g. 'Transit Gateway'",
    )
    max_hops: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Traversal depth (1 = direct neighbors only)",
    )


class EntityRelationship(BaseModel):
    neighbor_id: str
    neighbor_type: str
    neighbor_value: str
    edge_weight: int = 1
    relation: str = "co_occurs"
    pages: list[int] = Field(default_factory=list)


class GetEntityRelationshipsOutput(BaseModel):
    doc_id: str
    entity_id: str
    entity_type: str
    entity_value: str
    neighbor_count: int
    relationships: list[EntityRelationship] = Field(default_factory=list)
