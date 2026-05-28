# MiraDocs

> **Mira** — from the Latin *mīrus*, meaning wonder, astonishment, something that makes you look twice.  
> That's the feeling we're after: the moment a buried insight surfaces from a document you've read a dozen times and still missed.  
> **Docs** keeps it honest — this is a workspace built around your documents, nothing more.

---

## Table of Contents

- [What Problem It Solves](#what-problem-it-solves)
- [Capabilities](#capabilities)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Run](#run)
- [Cleanup](#cleanup)
- [MCP Server — Connect Your AI Client](#mcp-server--connect-your-ai-client)
- [Auto-Update](#auto-update)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

---

## What Problem It Solves

Reading technical documents — architecture designs, policy guides, compliance specs — is slow, and the most important details are buried deep. Standard search tools return keyword matches with no context. AI assistants hallucinate when documents aren't in their training data.

MiraDocs bridges the gap:

- **You have PDFs, DOCX, or PPTX files** that contain knowledge you need to query, review, or cross-reference.
- **You want answers grounded in the actual pages** — not paraphrased from memory.
- **You want to bring your own AI** (Claude, ChatGPT, Gemini, Cursor) and have it read your documents like a colleague who has actually studied them.

MiraDocs parses your documents locally, builds a structured knowledge base, and exposes it to any MCP-compatible AI client — so every answer comes with a source page you can verify.

---

## Capabilities

| Capability | Details |
|---|---|
| **Document ingestion** | PDF, DOCX, PPTX — upload once, process once |
| **Structured parsing** | Docling (primary) + PyMuPDF (fallback) with OCR |
| **Page images** | Every page rendered to PNG for visual verification |
| **Table extraction** | Tables saved as CSV + Markdown |
| **Figure extraction** | Cropped figure images per page |
| **Entity detection** | AWS/Azure services, CIDRs, environments, governance terms |
| **Hybrid search** | Dense (BGE-M3) + sparse (BM25) with optional reranking |
| **Side-by-side compare** | Two documents, keyword overlays, match navigation |
| **Cross search** | Same query run across two documents simultaneously |
| **MCP integration** | 14 tools exposed to Claude, ChatGPT, Gemini, Cursor, Windsurf, Codex |
| **100% local** | No cloud, no API keys required to run the pipeline |
| **Artifact export** | manifest, structure, quality, chunks, entities, markdown, tables, figures |

### Workspace views

- **Library** — Upload, search, tag, select, and delete documents. Paginated with multi-select.
- **Process** — Run the pipeline with live progress bar, ETA, and streaming logs.
- **Tag** — Add up to 5 custom tags per document, available before and after processing.
- **Inspect** — Page images at full size, structure tree, quality signals, tables, and figures.
- **Index & Search** — Index into Qdrant, then run hybrid search with page-level evidence.
- **Compare** — Side-by-side page evidence for two documents with keyword match navigation.

---

## Prerequisites

The setup script installs everything automatically. If you prefer to install manually:

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python3.11`, `python3.12`, or `python3.13` |
| Node.js | 20+ | Required for the Next.js frontend |
| Ollama | latest | Local model runtime |
| `bge-m3` model | — | `ollama pull bge-m3` — used for embeddings |
| `llama3.2` model | — | `ollama pull llama3.2` — used for entity extraction and reranking |

> **No cloud account or API key is needed** to run the pipeline, search, or MCP server.  
> An external LLM API key (Anthropic, OpenAI, Gemini) is only needed if you enable the optional Review Agent feature.

---

## Setup

Clone the repo and run the one-shot setup script. It installs all dependencies, pulls Ollama models, and initialises the data directories.

**macOS / Linux**
```bash
git clone https://github.com/your-username/miradocs.git
cd miradocs
chmod +x setup.sh && ./setup.sh
```

**Windows** (PowerShell, run as Administrator)
```powershell
git clone https://github.com/your-username/miradocs.git
cd miradocs
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

The setup script:
1. Installs Homebrew, Python 3.11+, Node.js 20+, and Ollama (macOS) via Homebrew
2. Creates a Python virtual environment at `.venv/`
3. Installs Python dependencies from `requirements.txt`
4. Installs frontend npm packages in `frontend/`
5. Pulls the `bge-m3` and `llama3.2` Ollama models
6. Creates the `data/` directory structure
7. Initialises the SQLite registry
8. Verifies the MCP server is importable

---

## Run

**macOS / Linux**
```bash
./start.sh
```

**Windows** — requires [Git Bash](https://git-scm.com/download/win) or WSL:
```bash
./start.sh
```

Once running:

| Service | URL |
|---|---|
| Workspace UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

Press `Ctrl+C` to stop all services cleanly.

---

## Cleanup

Remove installed packages and generated files without touching your documents.

**macOS / Linux**
```bash
./cleanup.sh                # interactive menu
./cleanup.sh --packages     # remove .venv + node_modules only
./cleanup.sh --cache        # remove .next, __pycache__, .pytest_cache
./cleanup.sh --all          # packages + cache (safe reset — re-run setup.sh after)
./cleanup.sh --data         # delete all user documents and parsed data (irreversible)
./cleanup.sh --full         # everything
```

**Windows**
```powershell
.\cleanup.ps1               # interactive menu
.\cleanup.ps1 -Packages     # remove .venv + node_modules only
.\cleanup.ps1 -Cache        # remove .next, __pycache__, .pytest_cache
.\cleanup.ps1 -All          # packages + cache
.\cleanup.ps1 -Data         # delete all user documents and parsed data (irreversible)
.\cleanup.ps1 -Full         # everything
```

> `--data` / `-Data` requires typing `delete` at the confirmation prompt — it wipes all uploaded files, parsed output, page images, indexes, and the registry database.

---

## MCP Server — Connect Your AI Client

MiraDocs exposes a local MCP server over stdio. Your AI client spawns it on demand — no port, no background process.

### Step 1 — find your install path

```bash
pwd   # run from the miradocs directory
# e.g. /Users/you/projects/miradocs
```

### Step 2 — add the server to your client

Replace `/path/to/miradocs` with your actual path in the config below.

<details>
<summary><strong>Claude Code</strong> — <code>.claude/settings.json</code></summary>

```json
{
  "mcpServers": {
    "miradocs": {
      "type": "stdio",
      "command": ".venv/bin/python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/miradocs",
      "env": {}
    }
  }
}
```

Or via CLI:
```bash
claude mcp add-json miradocs '{
  "type": "stdio",
  "command": ".venv/bin/python",
  "args": ["-m", "src.mcp.server"],
  "cwd": "/path/to/miradocs",
  "env": {}
}'
```
</details>

<details>
<summary><strong>Claude Desktop</strong> — <code>claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "miradocs": {
      "command": "bash",
      "args": ["-c", "cd /path/to/miradocs && .venv/bin/python -m src.mcp.server"]
    }
  }
}
```

> **Note:** Claude Desktop does not reliably support `cwd`. The `bash -c "cd ... && ..."` wrapper ensures the working directory is correct so Python can find the `src` module.
</details>

<details>
<summary><strong>Cursor</strong> — <code>.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "miradocs": {
      "command": ".venv/bin/python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/miradocs"
    }
  }
}
```
</details>

<details>
<summary><strong>Windsurf</strong> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "miradocs": {
      "command": ".venv/bin/python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/miradocs"
    }
  }
}
```
</details>

<details>
<summary><strong>Gemini CLI</strong> — <code>~/.gemini/settings.json</code></summary>

```json
{
  "mcpServers": {
    "miradocs": {
      "command": ".venv/bin/python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/miradocs",
      "env": {}
    }
  }
}
```
</details>

<details>
<summary><strong>OpenAI Codex CLI</strong> — <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.miradocs]
command = ".venv/bin/python"
args    = ["-m", "src.mcp.server"]
cwd     = "/path/to/miradocs"
```
</details>

> **Windows:** replace `.venv/bin/python` with `.venv\Scripts\python.exe` and use backslashes in `cwd`.

### Step 3 — verify the connection

Ask your AI client: *"List my MiraDocs documents."*  
It should call `list_documents` and return your library.

### Available MCP tools

| Tool | What it does |
|---|---|
| `search_docs` | Semantic / keyword / hybrid search across indexed documents |
| `list_documents` | List all documents with status, type, and page count |
| `get_document_info` | Section structure, quality signals, chunk count, entity summary |
| `get_page_evidence` | Full text, tables, figures, entities, and image path for a page |
| `get_page_matches` | Keyword match boxes for PDF page image highlights |
| `get_section_content` | All chunks and tables within a named section |
| `get_entities` | Extracted entities (AWS services, CIDRs, environments, governance terms) |
| `get_pipeline_status` | Pipeline steps, active run, events, and run history |
| `get_index_status` | Chunk/index status, adapter health, reindex recommendation |
| `detect_compare_mode` | Suggest the best compare mode for two documents |
| `list_compare_runs` | List existing compare runs for a document |
| `get_compare_run` | Read an existing compare run and its findings |
| `put_cross_search` | Side-by-side cross search across two documents |
| `put_compare` | Create a deterministic compare run for two processed documents |

---

## Configuration

Edit `config/settings.yaml` to change runtime behaviour. The app picks up changes on restart.

```yaml
# ── Parsing ─────────────────────────────────────────────────
parsing:
  primary_parser: "docling"     # "docling" | "pymupdf"
  fallback_parser: "pymupdf"
  page_image_dpi: 150           # increase for sharper images (uses more disk)
  ocr_enabled: true             # disable to skip OCR on scanned pages

# ── Embeddings ───────────────────────────────────────────────
embedding:
  provider: "ollama"
  model: "bge-m3"               # 1024-dim dense embeddings
  ollama_url: "http://localhost:11434"

# ── Vector Index ─────────────────────────────────────────────
indexing:
  default_store: "qdrant"
  qdrant_path: "data/indexes/qdrant"
  collection_name: "architecture_docs"

# ── Chunking ─────────────────────────────────────────────────
chunking:
  max_chunk_tokens: 512         # reduce for more granular retrieval
  overlap_tokens: 50

# ── Search ───────────────────────────────────────────────────
search:
  dense_weight: 0.7             # hybrid score = dense*0.7 + sparse*0.3
  sparse_weight: 0.3
  rerank_enabled: true
  rerank_model: "llama3.2"
  default_top_k: 10
  rerank_top_k: 5               # candidates passed to reranker

# ── Entity Extraction ────────────────────────────────────────
entity_extraction:
  use_llm: true                 # false = regex only (faster); true = Ollama enrichment
  ollama_model: "llama3.2"
```

### Common changes

| Goal | Setting |
|---|---|
| Sharper page images | `parsing.page_image_dpi: 300` |
| Faster pipeline (skip LLM enrichment) | `entity_extraction.use_llm: false` |
| More search results | `search.default_top_k: 20` |
| Keyword-only search fallback | `retrieval.fallback_to_keyword: true` |
| Disable reranking | `search.rerank_enabled: false` |
| Different embedding model | `embedding.model: "nomic-embed-text"` (then `ollama pull nomic-embed-text`) |

> After changing embedding model or chunking settings, delete `data/indexes/qdrant/` and re-index your documents.

---

## Architecture

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  Next.js   │────▶│  FastAPI   │────▶│  Pipeline  │
│ workspace  │     │  services  │     │  modules   │
└────────────┘     └────────────┘     └─────┬──────┘
                                            │
                   ┌────────────────────────┼─────────────────────┐
                   ▼                        ▼                     ▼
             ┌──────────┐            ┌────────────┐        ┌──────────┐
             │  Docling │            │  PyMuPDF   │        │  SQLite  │
             │ (parser) │            │  (images)  │        │ registry │
             └──────────┘            └────────────┘        └──────────┘
                                            │
                                            ▼
                                      ┌──────────┐
                                      │  Qdrant  │
                                      │  local   │
                                      └──────────┘
                                            │
                                    ┌───────┴───────┐
                                    ▼               ▼
                              MCP stdio         Browser UI
                         (AI clients)       (localhost:3000)
```

### Pipeline steps

| Step | Output |
|---|---|
| 1. Upload | Raw file registered in SQLite |
| 2. Parse | `document.json`, `full_document.md` |
| 3. Page images | `page_NNNN.png` per page |
| 4. Tables | CSV + Markdown per table |
| 5. Figures | Cropped PNG per figure |
| 6. Entities | `entities.json` |
| 7. Metadata | `doc_manifest.json`, `document_structure.json` |
| 8. Quality | `quality_report.json` |
| 9. Chunks | `chunks.json` |
| 10. Index | Qdrant collection |

---

## Auto-Update

MiraDocs checks for new versions on startup by comparing the local `VERSION` file against the latest on GitHub.

### How it works

1. App loads → frontend calls `/api/version-check`
2. If a newer version exists → a popup appears: *"New version available. Update now?"*
3. User clicks **Yes** → backend spawns a detached update process
4. The update script stops services, pulls changes, installs dependencies (if changed), and restarts the stack
5. Frontend polls `/api/health` until the app comes back → auto-reloads the page

### Manual update

You can also update manually at any time:

```bash
./update.sh
```

### Releasing a new version

Bump the `VERSION` file on your main branch:

```bash
echo "1.1.0" > VERSION
git add VERSION && git commit -m "release: v1.1.0" && git push
```

All running instances will see the update popup on next page load.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `docling` import fails | `pip install docling` (requires PyTorch — takes a few minutes) |
| Ollama not responding | Run `ollama serve` in a separate terminal |
| `bge-m3` not found | `ollama pull bge-m3` |
| Page images missing | `pip install PyMuPDF` |
| Qdrant errors after config change | Delete `data/indexes/qdrant/` and re-index |
| MCP server not found by client | Check `cwd` in your client config points to the project root |
| No search results | Ensure documents are indexed — run Index from the workspace UI first |
| Windows MCP path error | Use `.venv\Scripts\python.exe` and backslashes in `cwd` |
