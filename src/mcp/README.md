# MiraDocs — MCP Server

Local MCP server that exposes document search to Claude Code and other MCP-compatible clients.

## What It Does

Exposes read-only tools that query your local parsed architecture documents (LLD/HLD/PDF/DOCX/PPTX) and return evidence-grounded search results, page evidence, image match coordinates, pipeline/index status, and existing compare history.

## Quick Start

```bash
# From project root
python -m src.mcp.server
```

The server uses **stdio transport** — it reads JSON-RPC from stdin and writes responses to stdout.

## Claude Code Integration

Add to Claude Code:

```bash
claude mcp add-json miradocs '{
  "type": "stdio",
  "command": "python",
  "args": ["-m", "src.mcp.server"],
  "cwd": "/path/to/miradocs",
  "env": {}
}'
```

Or in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "miradocs": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/miradocs"
    }
  }
}
```

## Available Tools

Read-only tools currently exposed:

- `search_docs` — semantic/keyword/hybrid search across one or multiple indexed documents.
- `list_documents` — list documents with status, type, domain, and page count.
- `get_document_info` — section structure, quality status, chunk count, and entity summary.
- `get_page_evidence` — page text, tables, figures, entities, and page image path.
- `get_page_matches` — normalized keyword match boxes for PDF page image highlighting.
- `get_section_content` — full content for a named section.
- `get_entities` — extracted architecture entities for a document.
- `get_pipeline_status` — pipeline steps, active persisted run, replayed events, and recent runs.
- `get_index_status` — chunk/index status, adapter health, and reindex recommendation.
- `detect_compare_mode` — suggested compare mode for two documents without creating a run.
- `list_compare_runs` — existing compare runs for a document.
- `get_compare_run` — one existing compare run and its findings.
- `put_cross_search` — run an explicit side-by-side Cross Search across exactly two documents.
- `put_compare` — create a deterministic persisted compare run for two processed documents.

### search_docs

Search the local document knowledge base for evidence.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | required | Search query |
| top_k | integer | 8 | Results to return (max 20) |
| project | string | null | Filter by project |
| doc_id | string | null | Filter by document ID |
| doc_ids | string[] | null | Filter by multiple document IDs |
| domain | string | null | Filter: Networking, Security, Governance, etc. |
| document_type | string | null | Filter: HLD, LLD, Design Review, etc. |
| chunk_types | string[] | null | Filter: child_text_chunk, table_chunk, etc. |
| search_mode | string | "auto" | auto, semantic, keyword, hybrid |

**Example call from Claude Code:**
```
search_docs(query="Transit Gateway route table isolation Prod NonProd")
```

**Example response:**
```json
{
  "query": "Transit Gateway route table isolation",
  "search_mode_used": "keyword",
  "result_count": 2,
  "results": [
    {
      "rank": 1,
      "score": 0.83,
      "doc_id": "doc_lz_001",
      "source_file": "AWS_Landing_Zone_LLD.pdf",
      "chunk_type": "child_text_chunk",
      "page_start": 32,
      "section_path": "4. Networking > 4.2 Transit Gateway",
      "text": "The TGW route table is configured with separate route tables for Prod and NonProd...",
      "entities": {"aws_services": ["Transit Gateway"], "environments": ["Prod", "NonProd"]},
      "source_refs": {"page_image": "data/page_images/doc_lz_001/page_0032.png"}
    }
  ]
}
```

## Search Modes

| Mode | Behavior |
|------|----------|
| `auto` | Try hybrid → semantic → keyword fallback |
| `hybrid` | Dense vectors + BM25 keyword fusion |
| `semantic` | Vector similarity only (requires Qdrant) |
| `keyword` | Term matching over chunks.json (always available) |

## Architecture

```
Claude Code → MCP stdio → server.py → tools.py → RetrievalService
                                                       ↓
                                          Qdrant/Chroma (if available)
                                                  OR
                                          chunks.json keyword fallback
```

The MCP server does **not** require Streamlit, Qdrant, or any external service to be running. It always has keyword fallback over `data/parsed/*/chunks.json`.

## Security Notes

⚠️ **This MCP server gives agents read access to all documents indexed in your local data directory.**

- Mostly read-only: only `put_compare` writes compare run/findings records
- No upload/delete/tag/pipeline-run/index-run tools
- No shell execution
- No arbitrary file read — only returns data within configured `data/` directory
- Path traversal prevented
- Result text capped at 1800 chars per chunk
- Only register this server in trusted local environments

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No results | Ensure documents are parsed: check `data/parsed/*/chunks.json` exists |
| Qdrant unavailable | Server falls back to keyword search automatically |
| Logs polluting stdout | Logs go to stderr only; stdout is reserved for MCP protocol |
| Claude Code can't connect | Verify `cwd` points to project root and Python can import `src.mcp.server` |

## Not Exposed By Design

- Upload, delete, and tag mutation tools
- Pipeline run and index run tools
- Arbitrary file read or shell execution
