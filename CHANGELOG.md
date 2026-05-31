# Changelog

All notable changes to MiraDocs are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## v1.5.4 - 2026-05-31

### Changed
- **Centralized version**: `VERSION` file is now the single source of truth. `src/mcp/server.py` `SERVER_INFO["version"]` now reads from `VERSION` at startup instead of being hardcoded. `src/api/main.py` already did this via `_read_local_version()`.

---

## v1.5.3 - 2026-05-31

### Fixed
- **Qdrant "already accessed by another instance" error**: Qdrant local file mode uses an exclusive OS-level lock per process. Multiple `QdrantAdapter()` instantiations within the same process each tried to open the path independently, and any second OS process (e.g. MCP server alongside API server) would also conflict.
  - **Within one process**: `QdrantAdapter` now uses a module-level `_client` singleton (double-checked lock). All adapter instances share one `QdrantClient` — one lock, no conflict.
  - **Across processes** (API server + MCP server running simultaneously): set `qdrant_url: "http://localhost:6333"` in `config/settings.yaml` to switch to Qdrant HTTP server mode. Both processes connect as HTTP clients — no file lock. See the added comment in `settings.yaml`.

---

## v1.5.2 - 2026-05-31

### Fixed
- **DOCX/PPTX always get `NOT_READY` quality status**: Docling's `export_to_dict()` returns an empty `pages` dict for non-PDF formats, causing `page_count = 0` → immediate `NOT_READY`. Two fixes:
  1. `quality_reporter.py`: when `page_count == 0`, fall back to `max(len(page_images), len(pages_text))` before evaluating thresholds. Page images are rendered independently and are the ground truth for DOCX/PPTX page count.
  2. `docling_parser.py` `_get_page_count`: when `pages` dict is empty, scan `texts`, `tables`, and `pictures` items (not just `body`) for `prov[0]["page_no"]` — the correct key in the current Docling schema. Previously only scanned `body`/`main_text` which are absent in the new schema.

---

## v1.5.1 - 2026-05-31

### Fixed
- **Raw status strings shown in UI**: `NOT_READY`, `READY_WITH_WARNINGS`, `done`, `queued`, etc. were displayed verbatim throughout the app. Added `statusLabel()` mapper in `workflow.ts` and applied it in `StatusPill`, the Inspect quality panel, and the Process view run history. Display values: `NOT_READY` → "Low quality", `READY_WITH_WARNINGS` → "Ready (warnings)", `READY` → "Ready", `done` → "Done", etc.
- **"result NOT_READY" in run history**: process view run history row now shows "quality: Low quality" instead of the raw backend key.

### Note
`NOT_READY` on a fully-pipelined document is **expected behavior** — it means the quality checker found fewer than 50% of pages had extractable text (common for image-heavy DOCX files). The document is still indexed and searchable; the status is a signal that search quality may be lower.

---

## v1.5.0 - 2026-05-31

### Added
- **MCP `export_workspace` tool**: exports the full workspace (SQLite DB + all artifacts + Qdrant vector index) to a ZIP file on disk. Accepts optional `output_path` and `doc_ids` for selective export. Returns the file path, size in MB, document count, and export timestamp. Auto-saves to `data/exports/` if no path is given.
- **MCP `import_workspace` tool**: imports a workspace ZIP produced by `export_workspace`. Merge mode (default) skips documents already present by SHA-256; replace mode wipes and restores. Returns counts of imported/skipped documents. Invalidates the registry singleton so new documents are immediately visible in subsequent MCP tool calls.
- MCP server version bumped to `1.5.0`.

---

## v1.4.2 - 2026-05-31

### Fixed
- **`indexStatusQuery` fires on every doc select**: gated `enabled` on `activeTab === "Index"` — was hitting the Qdrant endpoint regardless of active tab, causing `TypeError: Failed to fetch` in the UI whenever the Index tab was not open.
- **3× retry storm on network errors**: set `QueryClient` defaults `retry: false, staleTime: 10_000` — stops automatic triple-retry on failed requests and reduces redundant background refetches.

---

## v1.4.1 - 2026-05-31

### Fixed
- **Status pill wrong colour for imported docs**: `statusTone` only mapped `"READY"` to green. Added `"READY_WITH_WARNINGS"` → amber and `"NOT_READY"` → red to match the three values emitted by the quality reporter.

---

## v1.4.0 - 2026-05-31

### Added
- **Workspace export/import**: export the full workspace (SQLite DB + all artifacts + Qdrant vector index) as a ZIP via `GET /api/export`. Optional `?doc_ids=` param for selective export. Import via `POST /api/import` with merge (skip sha256 duplicates) or replace mode. UI: **Export all** / **Export (N)** and **Import** buttons in the library sidebar with success/error feedback and auto-refresh.

---

## v1.3.0 - 2026-05-31

### Performance
- **Fix N+1 DB queries in `list_documents`**: replaced per-document `get_pipeline_status` loop with a single batched `get_pipeline_status_batch` query. 100 docs: 101 queries → 2 queries per page load.
- **Fix N+1 DB queries in `get_pipeline_runs`**: replaced per-run events sub-query loop with a single `IN` query; assembled events in Python. 20 runs: 21 queries → 2 queries.
- **Add missing DB indexes**: `CREATE INDEX` for `pipeline_steps(doc_id)`, `pipeline_runs(doc_id)`, `compare_findings(run_id)` — eliminates full table scans on every pipeline status/runs fetch.
- **Fix PDF re-opened per search result in `PageImageEvidence`**: replaced `fitz.open()` per result call with a single `_load_page_text_cache` that reads all page text once per doc per instance. top_k=10: 10 file opens → 1.
- **Fix new `DocumentRegistry()` per `_find_raw_file` call**: `page_evidence.py` now uses a module-level singleton instead of constructing a fresh DB connection on every search result enrichment.
- **Add `get_documents_batch` to `DocumentRegistry`**: bulk-fetches documents by a list of IDs in a single `IN` query; used by `/api/search` doc validation (N SELECTs → 1).
- **Fix `_read_local_version()` reads disk on every `/api/health` call**: result cached in `_LOCAL_VERSION` module-level variable after first read.
- **Fix full `chunks.json` parse just for `len()` in `get_index_status`**: reads `chunks_count` from cached `index_status.json` first; falls back to a regex count on the raw file. Avoids deserializing the entire file.
- **Fix `DocumentRegistry()` per MCP tool call in `tools.py`**: `_get_registry()` now caches the instance as a module-level singleton, matching the existing `_retrieval` pattern.
- **Fix N filesystem reads in MCP `list_documents`**: `page_count` read from manifests now uses a fast regex on raw file text instead of full JSON parse; avoids constructing a dict per document.
- **Fix unconditional 5 s poll on `/api/documents`**: `refetchInterval` set to `false` — cache invalidated on mutation success and SSE terminal events only.
- **Fix 4 overlapping pollers on Process tab**: `documentQuery`, `pipelineQuery`, `runsQuery` set to `refetchInterval: false`; `activePipelineQuery` polls only when SSE is not connected and Process tab is active — SSE delivers real-time events, polling is a fallback.

---

## v1.2.0 - 2026-05-29

### Removed
- **All shell scripts deleted**: `start.sh`, `update.sh`, `cleanup.sh`, `setup.sh`, `cleanup.ps1`.

### Added
- `cleanup.py` — cross-platform replacement for `cleanup.sh` + `cleanup.ps1`.
- `setup.py` — cross-platform replacement for `setup.sh`.
- All entry points are now pure Python (macOS/Linux/Windows, Intel/ARM64).

### Changed
- README updated: all references now point to `python3 setup.py`, `python3 start.py`, `python3 cleanup.py`.
- `.gitignore` hardened: added `frontend/.next/`, `frontend/node_modules/`, `.claude/`, `.DS_Store`.
- FastAPI app version is now dynamic (reads from `VERSION` file).

---

## v1.1.5 - 2026-05-29

### Fixed
- MPS/CUDA accelerator fallback now retries on **any** exception when the active device is not CPU — no longer relies on fragile substring matching. Fixes the persistent `TypeError: Cannot convert a MPS Tensor to float64` crash when Docling wraps the inner error in a `ConversionError`.
- Errors on CPU are still surfaced normally (never silently retried).

### Added
- Test: `test_any_exception_on_mps_triggers_cpu_fallback`.

---

## v1.1.4 - 2026-05-29

### Changed
- Migrated startup, service supervision, and update logic into the Python launcher `start.py`.
- Reduced `start.sh` and `update.sh` to compatibility wrappers around the Python launcher.
- Updated `/api/update` to invoke `start.py update` directly.

---

## v1.1.3 - 2026-05-29

### Fixed
- Startup-triggered updates now update in place and re-exec the refreshed launcher in the same terminal.

---

## v1.1.2 - 2026-05-29

### Fixed
- Update-triggered restarts: `start.sh` hands service control to `update.sh` instead of treating the intentional shutdown as a crash.
- Added update handoff marker and ignored its runtime file.

---

## v1.1.1 - 2026-05-29

### Added
- Startup auto-update checks in `start.sh` before API/UI launch.
- Update recursion guard with `MIRADOCS_SKIP_START_UPDATE`.
- Shell-level regression tests for startup update paths.

---

## v1.1.0 - 2026-05-29

### Added
- Configurable hardware acceleration for Docling: `parsing.accelerator_device` (`auto`|`cpu`|`cuda`|`mps`), `parsing.accelerator_num_threads`.
- Parallel page-image rendering: `parsing.page_image_workers`.
- Parallel figure cropping: `parsing.figure_workers`.
- Auto-fallback: if MPS/CUDA fails at parse time, the device is blacklisted and parsing retries on CPU automatically.
- Three new pytest tests for the accelerator-fallback path.

### Changed
- `DocumentConverter` cached as a thread-safe singleton (model loading runs once per process).
- Auto-detect probes runtime directly (CUDA → MPS → CPU) instead of using Docling's opaque `AUTO`.

### Fixed
- Apple Silicon MPS crash on RT-DETR v2 layout model (`TypeError: Cannot convert a MPS Tensor to float64`). Pipeline now self-recovers.
- Figure cropping falls back to full-page render on malformed bounding box.

### Performance
- Subsequent Docling parses: ~5–15 s saved per document.
- Apple Silicon (MPS-compatible models): 1.5–3× faster.
- NVIDIA GPU: 2–4× faster.
- Page image rendering (50-page doc): ~3× faster on 4-core box.

---

## v1.0.0 - 2026-05-28

Initial public release.
