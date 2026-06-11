# Changelog

All notable changes to MiraDocs are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## v1.8.2 - 2026-06-11

### Fixed
- **Auto-update version detection**: update checks now prefer a fresh `git fetch origin main` and read `VERSION` from `FETCH_HEAD`, avoiding stale GitHub raw responses after a release push.
- **Auto-update frontend consistency**: update success now waits for both backend and frontend readiness, then navigates through a versioned cache-busting URL so the browser does not keep old UI assets.

---

## v1.8.1 - 2026-06-11

### Fixed
- **Inspect panel readability**: the Inspect layout now keeps the section tree, tables, and figures readable with bounded panels and independent scrolling.
- **Collapsed quality summary**: the Quality panel is collapsed by default and shows the current status in the title to preserve vertical space.

---

## v1.8.0 - 2026-06-11

### Added
- **Document version history**: uploaded and imported documents can now be grouped into version histories with labels, notes, latest-version tracking, and duplicate upload detection.
- **Unified version workflow**: the workspace adds a Versions tab for browsing groups, switching between versions, selecting two versions, and launching semantic version diffs.
- **Version-aware APIs and MCP tools**: REST and MCP surfaces now expose version groups, per-document version lookup, semantic version comparison, and version-scoped retrieval filters.
- **Inline Inspect version switching**: the Inspect view can switch between document versions without leaving the current evidence workflow.
- **Visible section tree**: Inspect now shows parsed document sections with filtering, current-section highlighting, and click-to-jump page navigation.

### Changed
- **Version upload controls**: the library upload flow can attach new files to an existing version group and surface duplicate-version context.
- **Search result enrichment**: retrieval results can include version labels and version numbers when documents belong to a version group.

### Fixed
- **Uploaded version cleanup**: deleting a version removes the version row, deletes the underlying document artifacts, and recomputes the latest remaining version.

---

## v1.7.2 - 2026-06-10

### Fixed
- **Auto-update false positives**: startup and API version checks now compare semantic version ordering, so a newer local release branch is not prompted to "update" to an older `main` version.
- **Unsafe update fallback target**: failed `git pull --ff-only` recovery now resets to the current branch's configured upstream instead of hardcoded `origin/main`.
- **Stash failure handling**: updater now aborts with a failed status if local tracked changes cannot be stashed, instead of continuing into pull/reset.
- **Stale update status**: `/api/update-status` now marks old `updating` records as failed so the UI does not stay stuck after an abandoned update.
- **Office page text extraction**: `_get_pages_text` now reads the converted PDF for DOCX/PPTX inputs when available, matching visual page evidence.

---

## v1.7.1 - 2026-06-10

### Fixed
- **Docling DOCX section indexing**: section extraction now supports Docling's current `body` reference tree plus top-level `texts` nodes, including `section_header` labels and numbered heading text.
- **Table-backed DOCX headings**: one-row Docling table headings are now promoted into section metadata so styled template headings no longer produce empty `document_structure.json` sections.
- **DOCX page evidence text**: page evidence can now rebuild page text from persisted `document.json` Docling output instead of returning empty text for non-PDF documents.
- **Docling table markdown**: table extraction now avoids writing bbox/cell dictionaries into markdown when Docling's `grid` contains structured cell objects.

---

## v1.7.0 - 2026-06-04

### Added
- **Chunking and Search Quality improvements**:
  - Deterministic chunk IDs using SHA-256 hashes (stable across reruns).
  - Parent/child chunk relationships — child, table, and figure chunks now link to their parent section chunk via `parent_chunk_id`.
  - Section-first chunking with semantic boundaries (headings, numbered/bullet lists, paragraphs) instead of page-first splitting.
  - Table and figure context windows — 400 characters of surrounding text added to each artifact chunk.
  - Parent context expansion during retrieval — search results now include full parent section text when available.
  - Hybrid search with 3-list RRF fusion: Dense, BM25 (sparse over dense), and Keyword (global sparse index fallback).
  - Frontend collapsible "Section context" panel in cross-document search view.

---

## v1.6.0 - 2026-06-04

### Added
- **Performance fixes plan v1.6.0 implemented**:
  - `qdrant_adapter.py`: deterministic Qdrant point IDs using SHA-256 derived hashes (H1).
  - `qdrant_adapter.py`: shared `httpx.Client` to reuse TCP/HTTP connections for Ollama embeddings (H2).
  - `retrieval_service.py`: batch SQLite document lookups in `_enrich_results` (H3).
  - `retrieval_service.py`: uses `_load_chunks_for_doc` cache helper in `_keyword_search` to avoid repetitive disk parses (H4).
  - `mcp/server.py`: module-level `_DISPATCH` dict built once on import to avoid reconstruction per tool call (H5).
  - `workspace.tsx`: memoized `latestProgressLog` via `useMemo` to avoid reverse/find on every render (H6).
  - `entity_extractor.py`: pre-compiled entity dictionary patterns (AWS, Azure, env, governance) avoiding substring scans (H7).
  - `metadata_builder.py`: binary search (bisect) section lookup for pages (M1).
  - `chunk_candidate_builder.py`: binary search (bisect) section lookup for child chunks (M2).
  - `config.py`: thread-safe lazy configuration loading with `threading.Lock` (M3).
  - `pdf_fallback.py`: single-pass PyMuPDF dictionary parsing to extract text and headings together (M4).
  - `compare_service.py`: token overlap fast-path check in `_best_similarity` to bypass expensive SequenceMatcher calls (M5).
  - `relation_extractor.py`: shared `httpx.Client` connection block for Ollama generates (M6).

---

## v1.5.15 - 2026-06-04

### Fixed
- **page_count never stored in registry**: added `page_count` column to `documents` table with `ALTER TABLE` migration; pipeline now writes the final value after `build_metadata`; frontend `doc.page_count` fallback is now populated.
- **KeyError crash on malformed page_images entries**: `metadata_builder._build_pages` and `chunk_candidate_builder` now use `.get()` with a warning log when `page_number` or `image_path` is missing.
- **Silent tags_json parse failure in registry**: `JSONDecodeError` now logs a warning with `doc_id` before falling back to `[]`.
- **`doc["status"]` KeyError on pipeline-complete path**: both accesses in `main.py` replaced with `doc.get("status", "unknown")`.
- **Swallowed torch exceptions in accelerator detection**: CUDA and MPS probe `pass` blocks now log `logger.debug(..., exc_info=True)` so broken driver/torch installs are diagnosable.
- **original_format lost after DOCX/PPTX → PDF conversion**: `pipeline_service` now sets `parse_result["original_format"]` before the parse step and persists it via `_persist_parse_result`.
- **Overly loose TypeScript types**: `source_refs` and `last_index_result` now enumerate known keys intersected with `Record<string, unknown>` for adapter-specific escape hatch.

---

## v1.5.14 - 2026-06-04

### Fixed
- **Keyword highlight overlays missing for DOCX/PPTX in cross-document search**: `page_image_matches` was hard-gated on `file_type == "pdf"`, returning empty matches for all office docs. Added `_resolve_pdf_path` helper that returns the original PDF for native PDFs, or the LibreOffice-converted `source.pdf` for DOCX/PPTX. Pre-v1.5.13 docs without a converted PDF gracefully return empty matches (no overlay, no error). Warning logged when fitz extraction fails.

---

## v1.5.13 - 2026-06-04

### Changed
- **Unified PDF pipeline for DOCX/PPTX**: office files are now converted to PDF via LibreOffice *before* the parse step, so page images, figure cropping, and text extraction all run through the single PDF path. Falls back to native Docling parsing if LibreOffice is unavailable. Removes `render_source` branching from `run_pipeline` and simplifies `_get_pages_text` and `_reconcile_parse_page_count`.

---

## v1.5.12 - 2026-06-04

### Fixed
- **Inspect view page clamp fires before data loads**: the `useEffect` that clamps `page > totalPages` now guards on query loading state and `doc.page_count` presence, preventing the user's current page from being reset to 1 before queries resolve.
- **Redundant manifest HTTP fetch in Inspect view**: dropped the `manifestQuery` network call — `page_count` is already present on the `DocumentRecord` prop; `totalPages` now reads `doc.page_count` directly as its fallback.
- **LibreOffice output filename prediction brittle**: `convert_office_to_pdf` now globs `output_dir/*.pdf` instead of predicting `{stem}.pdf`, handling filenames with spaces, parentheses, and Unicode correctly.
- **Zero-byte PDF silently accepted**: `convert_office_to_pdf` now checks `stat().st_size == 0` after confirming the file exists, logging and discarding empty outputs that LibreOffice writes on partial failure.
- **LibreOffice stderr swallowed on failure**: `CalledProcessError` is now caught separately with `stdout`/`stderr` included in the warning log, making conversion failures diagnosable.
- **fitz document not closed on exception in `_get_pages_text`**: wrapped `fitz.open()` in `try/finally` to guarantee `doc.close()` even when a corrupt page raises mid-loop.
- **Dual page-count resolvers could disagree**: `_reconcile_parse_page_count` (pipeline) now delegates to `resolve_page_count` (metadata_builder) for the common cases, eliminating the duplicate logic; `resolve_page_count` is exported as the canonical resolver.
- **Double SQLite read in `repair_completed_running_steps`**: `get_pipeline_status()` was called twice per repair invocation; result is now fetched once and reused for both the running-step loop and the migration guard.

---

## v1.5.11 - 2026-06-02

### Fixed
- **DOCX/PPTX visual page support**: Office files are now converted to derived PDFs for page image rendering and page-scoped text extraction while preserving the original uploaded file.
- **Non-PDF page counts collapse to `0`/`1`**: pipeline metadata now reconciles missing Docling page counts from rendered page images or the converted PDF page count.
- **Broken inspector previews**: the Inspect view now falls back to manifest page counts and shows an unavailable preview state when a page image is missing.

---

## v1.5.10 - 2026-06-02

### Fixed
- **DOCX fallback parser missing tables and `source_format`**: `parse_with_docx` returned empty tables and no `source_format` key; added `_extract_tables` / `_grid_to_markdown` helpers and `source_format: .docx` to the result dict.
- **Quality reporter penalises DOCX/PPTX for missing page images**: `_determine_status` treated a zero `image_ratio` as a hard failure even for formats that never produce page screenshots. Added `_page_images_required` guard (only `.pdf` requires images); DOCX/PPTX now score `image_ratio = 1` so they can reach `READY`.
- **`source_format` not set by parser router**: `parse_document` now calls `result.setdefault("source_format", file_type)` after routing, ensuring all parsers expose the field even if their internal result omits it.

---

## v1.5.9 - 2026-06-02

### Fixed
- **Pipeline step cards frozen during DOCX/PPTX run**: SSE `progress` events carrying `step` + `status` were only used to update the percent bar. The `steps[]` array driving step card icons (pending → running → success) was only refreshed from the DB on job completion, so cards never transitioned mid-run. Added a `liveStepsByDoc` overlay in `workspace.tsx` that merges step statuses from incoming SSE events, making each step card flip immediately as the backend reports it.

---

## v1.5.8 - 2026-06-02

### Fixed
- **DOCX and PPTX parsing produces empty output**: `DocumentConverter` was built with only `PdfFormatOption`, so Docling had no pipeline configured for Office formats. Added `WordFormatOption` (DOCX) and `PowerpointFormatOption` (PPTX) to the converter's `format_options`, enabling native Docling parsing with full structure extraction (headings, tables, figures) for both formats.

---

## v1.5.7 - 2026-05-31

### Fixed
- **DOCX parsing fails when Docling is unavailable or conversion fails**: `.docx` files now try Docling first and fall back to the existing `python-docx` parser instead of hard-failing.
- **DOCX pipeline tries to render page images as PDF**: page-image extraction now skips non-PDF inputs instead of opening DOCX files with PyMuPDF.
- **Docling DOCX parses can report zero pages**: text-bearing Docling output with no page metadata now reports at least one logical page so metadata and quality steps can proceed.

---

## v1.5.6 - 2026-05-31

### Fixed
- **Auto-update gaps**: improved startup update prompting, interval cleanup, and service shutdown handling.

---

## v1.5.5 - 2026-05-31

### Fixed
- **App crash on startup: `sqlite3.OperationalError: no such table: main.compare_findings`**: `CREATE INDEX idx_compare_findings_run_id` was placed before the `compare_findings` table definition in `SCHEMA`. SQLite `executescript` runs statements in order — the index creation failed because the table didn't exist yet. Moved the index to after `compare_findings`.

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
