"""MCP Server for MiraDocs — exposes search_docs tool via stdio transport.

Run: python -m src.mcp.server
"""
import json
import logging
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Configure logging to stderr only — stdout is reserved for MCP protocol
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp.server")


def _read_message() -> dict | None:
    """Read a JSON-RPC message from stdin."""
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON on stdin: %s", e)
        return None


def _write_message(msg: dict):
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _error_response(id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _success_response(id, result) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


# ─── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_docs",
        "description": (
            "Search the local architecture document knowledge base for evidence relevant to a query. "
            "Returns ranked chunks with file name, page number, section path, chunk type, entities, "
            "and page image/table references. Retrieval-only — does not generate findings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for architecture documents"},
                "top_k": {"type": "integer", "description": "Number of results (1-20, default 8)", "default": 8},
                "project": {"type": "string", "description": "Filter by project name"},
                "doc_id": {"type": "string", "description": "Filter by document ID"},
                "doc_ids": {"type": "array", "items": {"type": "string"}, "description": "Filter by multiple document IDs"},
                "domain": {"type": "string", "description": "Filter by domain: Networking, Security, Governance, etc."},
                "document_type": {"type": "string", "description": "Filter by type: HLD, LLD, Design Review, etc."},
                "chunk_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by chunk types"},
                "include_page_images": {"type": "boolean", "description": "Include page image paths", "default": True},
                "include_tables": {"type": "boolean", "description": "Include table references", "default": True},
                "search_mode": {"type": "string", "enum": ["auto", "semantic", "keyword", "hybrid", "graph_local"], "default": "auto"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_documents",
        "description": (
            "List all indexed architecture documents in the local knowledge base. "
            "Returns document IDs, filenames, types, domains, page counts, and pipeline status. "
            "Use this to discover what documents are available before searching."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project name"},
                "domain": {"type": "string", "description": "Filter by domain"},
                "document_type": {"type": "string", "description": "Filter by document type"},
                "tag": {"type": "string", "description": "Filter by tag (returns docs containing this tag)"},
            },
        },
    },
    {
        "name": "get_document_info",
        "description": (
            "Get detailed information about a specific document: section structure, quality status, "
            "chunk count, and extracted entities summary. Use after list_documents to inspect a document."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID to retrieve info for"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "get_page_evidence",
        "description": (
            "Get full evidence for a specific page: extracted text, tables, figures, entities, "
            "and page image path. Use this to inspect a specific page referenced in search results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "page_number": {"type": "integer", "description": "Page number (1-based)", "minimum": 1},
            },
            "required": ["doc_id", "page_number"],
        },
    },
    {
        "name": "get_section_content",
        "description": (
            "Get all content for a specific document section: full text, chunks, tables, and figures. "
            "Use section paths from search results or document structure (e.g., '4. Networking > 4.2 Transit Gateway')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "section_path": {"type": "string", "description": "Section path or title to look up"},
            },
            "required": ["doc_id", "section_path"],
        },
    },
    {
        "name": "get_entities",
        "description": (
            "Get extracted architecture entities from a document: AWS services, CIDRs, environments, "
            "governance terms, VPC names, etc. Useful for understanding what a document covers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "entity_type": {"type": "string", "description": "Filter by type: aws_service, cidr, environment, governance, azure_service"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "get_page_matches",
        "description": (
            "Get normalized keyword match boxes for a PDF page image. "
            "Use this with page image evidence to highlight search terms on the evidence image."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "page_number": {"type": "integer", "description": "Page number (1-based)", "minimum": 1},
                "query": {"type": "string", "description": "Terms to locate on the page image"},
            },
            "required": ["doc_id", "page_number", "query"],
        },
    },
    {
        "name": "get_pipeline_status",
        "description": (
            "Read pipeline steps, active persisted run metadata, replayed events, and recent run history. "
            "Read-only: does not start or modify pipeline jobs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "include_runs": {"type": "boolean", "description": "Include recent persisted runs", "default": True},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "get_index_status",
        "description": (
            "Read index state for a document: chunks availability, indexed step, adapter health, "
            "last index result, and whether reindexing is recommended."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "detect_compare_mode",
        "description": "Suggest the best compare mode for two documents without creating a compare run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_doc_id": {"type": "string", "description": "Source document ID"},
                "target_doc_id": {"type": "string", "description": "Target document ID"},
            },
            "required": ["source_doc_id", "target_doc_id"],
        },
    },
    {
        "name": "list_compare_runs",
        "description": "List existing persisted compare runs for a document. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "limit": {"type": "integer", "description": "Maximum runs to return (1-50)", "default": 20, "minimum": 1, "maximum": 50},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "get_compare_run",
        "description": "Get one existing compare run and its findings by run ID. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Compare run ID"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "put_cross_search",
        "description": (
            "Run an explicit side-by-side cross search across exactly two documents. "
            "Returns combined results plus grouped source/target results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_doc_id": {"type": "string", "description": "First document ID"},
                "target_doc_id": {"type": "string", "description": "Second document ID"},
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Total results (1-20, default 8)", "default": 8, "minimum": 1, "maximum": 20},
                "search_mode": {"type": "string", "enum": ["auto", "semantic", "keyword", "hybrid", "graph_local"], "default": "auto"},
                "include_page_images": {"type": "boolean", "description": "Include page image paths", "default": True},
                "include_tables": {"type": "boolean", "description": "Include table references", "default": True},
            },
            "required": ["source_doc_id", "target_doc_id", "query"],
        },
    },
    {
        "name": "put_compare",
        "description": (
            "Create and persist a deterministic compare run for two processed documents. "
            "This is an action tool and writes compare run/findings records."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_doc_id": {"type": "string", "description": "Source document ID"},
                "target_doc_id": {"type": "string", "description": "Target document ID"},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "hld_lld", "requirements_design", "requirements_test", "policy_architecture", "sow_design", "version_diff", "generic_diff"],
                    "default": "auto",
                },
            },
            "required": ["source_doc_id", "target_doc_id"],
        },
    },
    {
        "name": "get_entity_graph",
        "description": (
            "Return the persisted entity co-occurrence graph for a document. "
            "Nodes are architecture entities (AWS services, CIDRs, environments, governance terms, etc.). "
            "Edges represent entities that appear together within the same page range. "
            "Use to understand structural relationships before running graph_local search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "entity_type": {
                    "type": "string",
                    "description": "Filter nodes by type: aws_service, cidr, environment, governance, azure_service",
                },
                "min_edge_weight": {
                    "type": "integer",
                    "description": "Minimum edge co-occurrence weight to include (default 1)",
                    "default": 1,
                    "minimum": 1,
                },
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "get_entity_relationships",
        "description": (
            "Return all entities directly connected to a named entity in the document graph. "
            "Use to explore what co-occurs with a specific service, CIDR, or governance term."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
                "entity_type": {
                    "type": "string",
                    "description": "Entity type: aws_service, cidr, environment, governance, azure_service",
                },
                "entity_value": {
                    "type": "string",
                    "description": "Entity value, e.g. 'Transit Gateway' or '10.0.0.0/16'",
                },
                "max_hops": {
                    "type": "integer",
                    "description": "Traversal depth (1=direct neighbors, 2=two hops)",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 2,
                },
            },
            "required": ["doc_id", "entity_type", "entity_value"],
        },
    },
]

SERVER_INFO = {
    "name": "miradocs",
    "version": "1.1.2",
    "protocolVersion": "2024-11-05",
}


# ─── Request Handlers ─────────────────────────────────────────────────────────

def handle_initialize(id, params: dict) -> dict:
    return _success_response(id, {
        "protocolVersion": SERVER_INFO["protocolVersion"],
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_INFO["name"], "version": SERVER_INFO["version"]},
    })


def handle_tools_list(id, params: dict) -> dict:
    return _success_response(id, {"tools": TOOLS})


def handle_tools_call(id, params: dict) -> dict:
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        from src.mcp import schemas, tools

        DISPATCH = {
            "search_docs": (schemas.SearchDocsInput, tools.search_docs),
            "list_documents": (schemas.ListDocsInput, tools.list_documents),
            "get_document_info": (schemas.GetDocInfoInput, tools.get_document_info),
            "get_page_evidence": (schemas.GetPageEvidenceInput, tools.get_page_evidence),
            "get_section_content": (schemas.GetSectionInput, tools.get_section_content),
            "get_entities": (schemas.GetEntitiesInput, tools.get_entities),
            "get_page_matches": (schemas.GetPageMatchesInput, tools.get_page_matches),
            "get_pipeline_status": (schemas.GetPipelineStatusInput, tools.get_pipeline_status),
            "get_index_status": (schemas.GetIndexStatusInput, tools.get_index_status),
            "detect_compare_mode": (schemas.DetectCompareModeInput, tools.detect_compare_mode),
            "list_compare_runs": (schemas.ListCompareRunsInput, tools.list_compare_runs),
            "get_compare_run": (schemas.GetCompareRunInput, tools.get_compare_run),
            "put_cross_search": (schemas.PutCrossSearchInput, tools.put_cross_search),
            "put_compare": (schemas.PutCompareInput, tools.put_compare),
            "get_entity_graph": (schemas.GetEntityGraphInput, tools.get_entity_graph),
            "get_entity_relationships": (schemas.GetEntityRelationshipsInput, tools.get_entity_relationships),
        }

        if tool_name not in DISPATCH:
            return _error_response(id, -32601, f"Unknown tool: {tool_name}")

        input_cls, handler = DISPATCH[tool_name]
        input_data = input_cls(**arguments)

        # Validate search_docs query non-empty
        if tool_name == "search_docs" and not input_data.query.strip():
            return _success_response(id, {
                "content": [{"type": "text", "text": json.dumps({"error": "Query cannot be empty"})}]
            })

        result = handler(input_data)

        # Serialize result
        if hasattr(result, "model_dump_json"):
            text = result.model_dump_json()
        else:
            text = json.dumps(result, default=str)

        return _success_response(id, {"content": [{"type": "text", "text": text}]})

    except Exception as e:
        logger.error("Tool call %s failed: %s", tool_name, e, exc_info=True)
        return _success_response(id, {
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
            "isError": True,
        })


HANDLERS = {
    "initialize": handle_initialize,
    "notifications/initialized": lambda id, p: None,
    "notifications/cancelled": lambda id, p: None,
    "ping": lambda id, p: _success_response(id, {}),
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    logger.info("MiraDocs MCP server starting (stdio transport)")

    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        handler = HANDLERS.get(method)
        if handler is None:
            if msg_id is not None:
                _write_message(_error_response(msg_id, -32601, f"Method not found: {method}"))
            continue

        response = handler(msg_id, params)
        if response is not None and msg_id is not None:
            _write_message(response)

    logger.info("MCP server shutting down")


if __name__ == "__main__":
    main()
