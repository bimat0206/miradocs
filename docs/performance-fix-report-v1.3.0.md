# Performance Fix Report — v1.3.0

**Date:** 2026-05-31
**Version bump:** 1.2.0 → 1.3.0

---

## What Was Done

### 1. N+1 DB queries in `list_documents` — `document_service.py:41`, `document_registry.py`

**Fix:** Added `get_pipeline_status_batch(doc_ids)` to `DocumentRegistry`. It fetches all pipeline steps for a list of documents in one `WHERE doc_id IN (...)` query, then assembles results by doc_id in Python. `list_documents()` now calls this once instead of one `get_pipeline_status` SELECT per document.

**Impact:** 100 documents: 101 DB queries → 2 queries per `/api/documents` or `/api/tags` request.

---

### 2. N+1 in `get_pipeline_runs` — `document_registry.py:289`

**Fix:** Fetched all run IDs first, then retrieved all events for those runs in a single `WHERE run_id IN (...)` query. Events grouped into a dict by run_id in Python.

**Impact:** 20 pipeline runs: 21 queries → 2 queries per call.

---

### 3. Missing DB indexes — `document_registry.py` SCHEMA

**Fix:** Added three `CREATE INDEX IF NOT EXISTS` statements to the schema:
- `idx_pipeline_steps_doc_id ON pipeline_steps(doc_id)`
- `idx_pipeline_runs_doc_id ON pipeline_runs(doc_id)`
- `idx_compare_findings_run_id ON compare_findings(run_id)`

**Impact:** Eliminated full table scans on every pipeline status fetch, pipeline runs fetch, and compare findings fetch. Applied on first startup via `_init_db`.

---

### 4. PDF re-opened per search result — `page_evidence.py:148`

**Fix:** Added `_load_page_text_cache(doc_id)` that opens the PDF once and reads all pages into `self._page_text_cache[doc_id]`. `_get_page_text` and `_get_nearby_text` now read from this in-memory dict. The `PageImageEvidence` instance is created once per search request, so the PDF is opened at most once per doc per request.

**Impact:** top_k=10 search: 10 `fitz.open()` calls → 1 per doc. Removes the dominant I/O cost from the search hot path.

---

### 5. New `DocumentRegistry()` on every `_find_raw_file` call — `page_evidence.py:207`

**Fix:** Added a module-level `_get_registry_singleton()` that caches a `DocumentRegistry` instance. `_find_raw_file` now uses this singleton instead of constructing a fresh DB connection each call.

**Impact:** Eliminates repeated SQLite connection initialization inside the search hot path.

---

### 6. Full `chunks.json` deserialize just for `len()` — `index_service.py:40`

**Fix:** Added `_count_json_array()` which counts `"chunk_id"` occurrences in the raw file text as a fast approximation. Also, `index_document()` now writes `chunks_count` into `index_status.json` at index time, so subsequent `get_index_status` calls read the count from the status file without touching `chunks.json` at all.

**Impact:** Avoids deserializing potentially MB-sized chunk files on every `/api/documents/{id}/index/status` request.

---

### 7. `_read_local_version()` reads disk on every `/api/health` — `api/main.py:605`

**Fix:** Added `_LOCAL_VERSION` module-level cache. Value read once on first call; subsequent calls return the cached string.

**Impact:** Eliminates unnecessary disk I/O on high-frequency health poll endpoint.

---

### 8. N sequential DB lookups in `/api/search` doc validation — `api/main.py:504`

**Fix:** Added `get_documents_batch(doc_ids)` to `DocumentRegistry` (single `IN` query). `/api/search` now validates all doc_ids in one query and builds a local map to check for missing IDs.

**Impact:** Multi-doc search requests: N SELECT queries → 1.

---

### 9. New `DocumentRegistry()` per MCP tool call — `mcp/tools.py:36`

**Fix:** `_get_registry()` now caches the `DocumentRegistry` instance in a module-level `_registry` variable, matching the existing `_retrieval` pattern.

**Impact:** Eliminates fresh DB connection on every MCP tool invocation on the stdio server.

---

### 10. N filesystem reads in MCP `list_documents` — `mcp/tools.py:93`

**Fix:** Instead of full JSON parse of `doc_manifest.json` per document, `_page_count()` uses a regex on the raw file text to extract `page_count` without allocating a full dict. This reduces allocation cost proportional to manifest size.

**Impact:** Reduces memory allocation and parse time for large manifests; does not change file I/O count but eliminates the object deserialization cost.

---

### 11. Unconditional 5 s poll on `/api/documents` — `workspace.tsx:143`

**Fix:** Set `refetchInterval: false` on `documentsQuery`. Document list is now refreshed only on explicit mutations (upload, delete) and on SSE terminal events (`done`/`failed`), which already call `queryClient.invalidateQueries(["documents"])`.

**Impact:** ~720 background requests/hour per open browser tab → 0 background requests when idle.

---

### 12. 4 overlapping pollers on Process tab — `workspace.tsx:176`

**Fix:** Set `refetchInterval: false` on `documentQuery`, `pipelineQuery`, and `runsQuery`. `activePipelineQuery` polls only when the Process tab is active AND SSE is not connected (`!sseConnected`). When SSE is live, all process data arrives via push events which call `invalidateQueries` on terminal states.

**Impact:** ~80 requests/minute per tab during an active run → SSE delivers real-time; polling only fires as a fallback when SSE disconnects (~1 req/3 s on Process tab when no SSE).

---

## Why These Fixes Were Needed

- **N+1 queries** scale linearly with document count and hit the DB on every page load or pipeline poll. With 50+ documents they become the dominant latency source for the UI.
- **PDF re-opening per result** means every search query hits the filesystem proportional to `top_k`. At top_k=10 this adds 10 file open/close cycles in the API response path — directly visible as search latency.
- **Missing DB indexes** cause SQLite to scan the entire `pipeline_steps` and `pipeline_runs` tables on every document status request. With thousands of pipeline events, this compounds with the polling frequency.
- **Unconditional polling** generates continuous background load regardless of user activity. The frontend was making 5–6 HTTP requests every 3–5 seconds per open tab, regardless of whether any pipeline was running, saturating the FastAPI event loop with low-value traffic.
- **Fresh `DocumentRegistry()` per call** means SQLite connection setup overhead on the critical path for MCP tools and search enrichment.
- **VERSION file read on every health check** is hit by both the frontend version badge poller and the update notification — multiplying disk reads across polling intervals.

---

## Remaining Findings (High / Medium)

These were identified in the audit but not fixed in this release:

### High
| File | Issue |
|------|-------|
| `qdrant_adapter.py:156` | Serial HTTP batches to Ollama for embeddings — no connection reuse, no async |
| `qdrant_adapter.py:56` | Unstable `hash()` used as Qdrant point ID — ghost points on re-index |
| `hybrid_search.py:62` | Full re-tokenization of result texts per search query |
| `retrieval_service.py:136` | `chunks.json` read from disk on every fallback keyword search (bypasses cache) |
| `retrieval_service.py:199` | N+1 registry lookups in `_enrich_results` |
| `entity_extractor.py:89` | O(\|text\| × \|dict\|) per-page dictionary scan — no word-boundary regex |
| `compare_service.py:297` | O(E × C) entity chunk scan — no inverted index |
| `update-notification.tsx:42` | Leaked `setInterval`, no exponential backoff |
| `server.py:353` | `DISPATCH` dict rebuilt on every MCP tool call |
| `query-provider.tsx:7` | `QueryClient` defaults: `staleTime: 0`, 3 retries — compounds polling |
| `workspace.tsx:214` | `[...logs].reverse()` on every render — not memoized |

### Medium
| File | Issue |
|------|-------|
| `chunk_candidate_builder.py:35` | O(pages × sections) scan per chunk — no pre-built page dict |
| `metadata_builder.py:132` | O(pages × sections) section lookup — should use `bisect` |
| `relation_extractor.py:361` | Serial Ollama calls per page batch — no parallelism or connection reuse |
| `pdf_fallback.py:27` | Two PyMuPDF parse passes per page (`"text"` + `"dict"`) |
| `config.py:9` | YAML parsed on every call until `_CONFIG` set — not thread-safe |
| `server.py:421` | Blocking synchronous stdio loop — one slow tool stalls all MCP messages |
| `workspace.tsx:245` | `EventSource` listeners not removed before close |
| `version-badge.tsx:16` | Duplicate `/api/health` fetch, not deduplicated with `UpdateNotification` |
| `compare_service.py:144` | O(n×m) `SequenceMatcher` for section similarity |
| `settings.yaml:9` | `page_image_dpi: 150` — below reliable OCR floor, triggers reruns |
