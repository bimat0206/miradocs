# Document Version Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class document version groups so users can upload/import revisions, navigate and switch between versions from a unified history view, delete an unwanted version, compare two versions semantically, and search across one or more versions.

**Architecture:** Keep each uploaded file as a normal processed MiraDocs document with its own `doc_id`; add a thin versioning layer in SQLite that groups document IDs and stores version labels. Reuse the existing compare pipeline with `mode="version_diff"` and add REST, MCP, and frontend affordances around the version metadata. The implementation should use the current `/api/documents` upload route and existing `DocumentRegistry`, `document_service`, `compare_service`, `RetrievalService`, React Query, and workspace tab patterns.

**Tech Stack:** Python 3, FastAPI, SQLite, Pydantic, pytest, Next.js/React/TypeScript, TanStack Query, Tailwind CSS, Vitest.

---

## Resolved Product Decisions

- Version groups are first-class records in `document_groups`.
- Version labels are user-supplied with an automatic default of `v{next_version_number}`.
- Version history is linear for this release. Branching is out of scope.
- Identical re-upload returns duplicate/version metadata instead of creating a new document version.
- Semantic version diffs reuse `compare_runs` and `compare_findings` through `run_compare(..., mode="version_diff")`.
- Auto-grouping is conservative: exact normalized filename match first, fuzzy match only above a threshold.
- Users can delete an already uploaded or imported version. Deleting a version removes the underlying `documents` row and artifacts through the existing document cleanup path, then recalculates the latest version in the group.
- The frontend exposes one unified version-history component that can be used in the Versions workspace tab and in document-focused views. Switching versions updates the selected `doc_id` without making users leave their current workflow.

## File Map

- Modify `src/intake/document_registry.py`: add schema, migration guards, and version-group CRUD/query helpers.
- Create `src/intake/version_matcher.py`: normalize filenames and match uploads to existing groups.
- Modify `src/services/document_service.py`: accept version metadata during document creation and return duplicate version context.
- Create `src/services/version_diff_service.py`: validate version pairs, call `run_compare`, and enrich the response with version labels.
- Modify `src/api/main.py`: extend `/api/documents`, add group/version REST endpoints, add version deletion, and add group suggestion endpoint.
- Modify `src/mcp/schemas.py`: add version schemas and version-aware search fields.
- Modify `src/mcp/tools.py`: add version tools and pass version filters to retrieval.
- Modify `src/mcp/server.py`: register version tools in `TOOLS` and `_DISPATCH`.
- Modify `src/retrieval/retrieval_service.py`: resolve version filters to `doc_id` filters and annotate result items with version metadata.
- Modify `frontend/lib/types.ts`: add version group, version summary, upload option, and enriched search result types.
- Modify `frontend/lib/api.ts`: add version APIs and extend upload/search helpers.
- Modify `frontend/lib/workflow.ts`: add `"Versions"` to the workflow tab union.
- Modify `frontend/components/workspace.tsx`: add the Versions tab and queries/mutations.
- Create `frontend/components/workspace/version-history.tsx`: reusable unified version timeline/switcher/deletion control.
- Create `frontend/components/workspace/versions-view.tsx`: group browser, unified version history, two-version selection, and comparison launcher.
- Modify `frontend/components/workspace/inspect-view.tsx`: show unified version history for the selected document and allow switching versions inline.
- Modify `frontend/components/workspace/process-view.tsx`: add version upload controls once the selected file is known.
- Add tests in `tests/test_version_control.py`, `tests/test_api.py`, `tests/test_mcp.py`, `tests/test_retrieval.py`, and `frontend/lib/workflow.test.ts` as scoped below.

## Task 1: Registry Schema and Version Queries

**Files:**
- Modify: `src/intake/document_registry.py`
- Test: `tests/test_version_control.py`

- [ ] **Step 1: Write registry tests**

Add tests that create a temporary `DocumentRegistry(db_path=tmp_path / "registry.db")`, register two documents with different hashes, and assert:

```python
def test_document_versions_track_latest_and_increment(tmp_path):
    registry = DocumentRegistry(tmp_path / "registry.db")
    first_doc_id = registry.register_document("Architecture_v1.pdf", "pdf", 10, "hash-v1")
    second_doc_id = registry.register_document("Architecture_v2.pdf", "pdf", 12, "hash-v2")

    group = registry.create_or_find_group(
        name="Architecture",
        base_filename="architecture",
        project="default",
    )
    first = registry.add_version(group["group_id"], first_doc_id, label=None, notes="initial")
    second = registry.add_version(group["group_id"], second_doc_id, label="Draft 2", notes="")
    registry.set_latest_version(group["group_id"], second_doc_id)

    versions = registry.get_versions_for_group(group["group_id"])
    assert [v["version_number"] for v in versions] == [1, 2]
    assert [v["version_label"] for v in versions] == ["v1", "Draft 2"]
    assert versions[0]["is_latest"] is False
    assert versions[1]["is_latest"] is True
    assert first["doc_id"] == first_doc_id
    assert second["doc_id"] == second_doc_id
```

Also cover `get_group_for_doc`, `list_groups`, duplicate group idempotency by `(project, base_filename)`, and `find_by_hash` plus version metadata lookup for duplicate uploads.

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
PYTHONPATH=. pytest tests/test_version_control.py -q
```

Expected: FAIL because version tables and registry methods do not exist.

- [ ] **Step 3: Add schema**

Extend `SCHEMA` with:

```sql
CREATE TABLE IF NOT EXISTS document_groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_filename TEXT NOT NULL,
    project TEXT DEFAULT 'default',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project, base_filename)
);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES document_groups(group_id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    version_label TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    is_latest INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(group_id, version_number),
    UNIQUE(group_id, version_label),
    UNIQUE(doc_id)
);

CREATE INDEX IF NOT EXISTS idx_document_groups_project ON document_groups(project);
CREATE INDEX IF NOT EXISTS idx_document_versions_group_id ON document_versions(group_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_doc_id ON document_versions(doc_id);
```

In `_init_db()`, keep the current migration-guard style and add guards for `document_groups.notes` if needed for upgraded databases.

- [ ] **Step 4: Add registry helpers**

Implement these methods with SQLite transactions and row-to-dict conversion:

```python
def create_or_find_group(self, name: str, base_filename: str, project: str = "default", notes: str = "") -> dict: ...
def update_group(self, group_id: str, *, name: str | None = None, notes: str | None = None) -> dict | None: ...
def add_version(self, group_id: str, doc_id: str, label: str | None = None, notes: str = "") -> dict: ...
def set_latest_version(self, group_id: str, doc_id: str) -> None: ...
def get_group(self, group_id: str, include_versions: bool = True) -> dict | None: ...
def get_group_for_doc(self, doc_id: str) -> dict | None: ...
def list_groups(self, project: str | None = None) -> list[dict]: ...
def get_versions_for_group(self, group_id: str) -> list[dict]: ...
def get_version(self, group_id: str, version_number: int) -> dict | None: ...
def get_version_for_doc(self, doc_id: str) -> dict | None: ...
def remove_version(self, group_id: str, version_number: int) -> dict | None: ...
def recompute_latest_version(self, group_id: str) -> dict | None: ...
```

Return `is_latest` as `bool`, include joined document fields (`filename`, `page_count`, `status`, `upload_time`) in version summaries, and update `document_groups.updated_at` whenever a version is added or latest changes.
`remove_version` should delete only the `document_versions` row and return the removed version metadata, including `doc_id`; the service/API layer is responsible for document/artifact cleanup. `recompute_latest_version` should mark the highest remaining `version_number` as latest and return that version, or return `None` when the group has no versions left.

- [ ] **Step 5: Run registry tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_version_control.py -q
```

Expected: PASS for registry tests.

## Task 2: Filename Normalization and Auto-Grouping

**Files:**
- Create: `src/intake/version_matcher.py`
- Test: `tests/test_version_control.py`

- [ ] **Step 1: Write matcher tests**

Cover these inputs:

```python
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("SRS_v2.1_FINAL.docx", "srs"),
        ("Architecture Design - Draft 3.pdf", "architecture design"),
        ("HLD_2024-01-15.docx", "hld"),
        ("network-connectivity-request-workflow.md", "network connectivity request workflow"),
    ],
)
def test_normalise_filename(filename, expected):
    assert normalise_filename(filename) == expected
```

Also assert `auto_match_group("Architecture Design v2.pdf", "default", registry)` returns the group created with base filename `architecture design`, and that below-threshold names return `None`.

- [ ] **Step 2: Implement matcher**

Use `Path(filename).stem`, `re`, and `difflib.SequenceMatcher`. Strip suffix tokens for version labels (`v2`, `v2.1`, `rev3`, `r3`), workflow labels (`final`, `draft`, `draft 3`), and dates (`YYYY-MM-DD`, `YYYYMMDD`, `DDMMYYYY`). Normalize separators to single spaces and lowercase.

- [ ] **Step 3: Run matcher tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_version_control.py -q
```

Expected: PASS.

## Task 3: Document Creation and Upload Version Metadata

**Files:**
- Modify: `src/services/document_service.py`
- Modify: `src/api/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write API tests**

Use FastAPI `TestClient` against `create_app(registry=..., data_dir=tmp_path / "data")` and assert:

- `POST /api/documents` with no version fields creates a new group and returns `group_id`, `version_id`, `version_label == "v1"`, and `duplicate is False`.
- A second upload with similar filename and different bytes auto-matches the first group and returns `version_label == "v2"`.
- Re-uploading the same bytes returns HTTP 409 with JSON containing `duplicate: true`, `existing_doc_id`, and `existing_version`.
- `auto_group=false` forces creation of a new group.

- [ ] **Step 2: Run API tests to confirm failure**

Run:

```bash
PYTHONPATH=. pytest tests/test_api.py -q
```

Expected: FAIL for the new version upload cases.

- [ ] **Step 3: Extend `create_document`**

Add optional parameters:

```python
version_group_id: str | None = None
version_label: str | None = None
version_notes: str = ""
auto_group: bool = True
group_name: str | None = None
```

On duplicate hash, return the existing document plus `duplicate: True` and any `existing_version = registry.get_version_for_doc(existing["doc_id"])`.

On new upload:

1. Register and write raw bytes exactly as today.
2. Resolve group by explicit `version_group_id`, auto-match, or `create_or_find_group`.
3. Call `add_version`.
4. Call `set_latest_version`.
5. Return the document plus `duplicate: False`, `group_id`, `version_id`, `version_label`, and `version_number`.

- [ ] **Step 4: Extend `/api/documents`**

Add form fields to the existing endpoint, not a new `/api/upload` route:

```python
version_group_id: str | None = Form(None)
version_label: str | None = Form(None)
version_notes: str = Form("")
auto_group: bool = Form(True)
group_name: str | None = Form(None)
```

If `create_document` reports `duplicate=True`, raise `HTTPException(status_code=409, detail=result)` so clients can show the existing version.

- [ ] **Step 5: Run API tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_api.py tests/test_version_control.py -q
```

Expected: PASS.

## Task 4: Version REST API and Diff Service

**Files:**
- Create: `src/services/version_diff_service.py`
- Modify: `src/services/document_service.py`
- Modify: `src/api/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write tests**

Add tests for:

- `GET /api/groups` returns version counts and latest version metadata.
- `GET /api/groups/{group_id}` returns ordered `versions`.
- `PATCH /api/groups/{group_id}` renames the group.
- `GET /api/documents/{doc_id}/version` returns the group/version for a document.
- `GET /api/groups/suggest?filename=Architecture_v2.pdf&project=default` returns the matching group.
- `POST /api/groups/{group_id}/compare` rejects same version, missing versions, and calls version diff for valid pairs.
- `DELETE /api/groups/{group_id}/versions/{version_number}` removes the version, deletes the underlying document/artifacts, and makes the highest remaining version latest.
- Deleting the only version removes the version row and underlying document; the empty group remains with `version_count == 0` so the user can decide whether to reuse or rename it.

- [ ] **Step 2: Implement `compare_versions`**

Create:

```python
def compare_versions(
    *,
    group_id: str,
    source_version: int,
    target_version: int,
    registry: DocumentRegistry,
    data_dir: Path,
) -> dict:
    ...
```

Validate both versions belong to the group, require different version numbers, call `run_compare(source_doc_id=..., target_doc_id=..., mode="version_diff", ...)`, and return:

```python
{
    **compare_result,
    "group_id": group_id,
    "source_version": source_version_row,
    "target_version": target_version_row,
    "version_label": f"{source_label} -> {target_label}",
}
```

- [ ] **Step 3: Add REST endpoints**

Add:

```text
GET   /api/groups
GET   /api/groups/{group_id}
PATCH /api/groups/{group_id}
GET   /api/groups/{group_id}/versions
POST  /api/groups/{group_id}/compare
DELETE /api/groups/{group_id}/versions/{version_number}
GET   /api/documents/{doc_id}/version
GET   /api/groups/suggest
```

Use Pydantic request models for PATCH and compare. Return 404 for missing groups/versions and 400 for invalid compare requests.

- [ ] **Step 4: Implement version deletion**

In `document_service.py`, add a service function that combines registry deletion with the existing cleanup behavior:

```python
def delete_document_version(
    *,
    group_id: str,
    version_number: int,
    registry: DocumentRegistry,
    data_dir: Path,
    index_adapter_factory,
) -> dict:
    version = registry.get_version(group_id, version_number)
    if not version:
        return {"status": "not_found"}
    removed = registry.remove_version(group_id, version_number)
    cleanup = delete_document(
        version["doc_id"],
        registry,
        data_dir,
        index_adapter_factory,
    )
    latest = registry.recompute_latest_version(group_id)
    return {
        "status": "deleted",
        "removed_version": removed,
        "cleanup": cleanup,
        "latest_version": latest,
    }
```

Order matters: remove the version row first so document cleanup cannot leave dangling version metadata if it cascades related rows. Return a warning if artifact cleanup reports non-fatal failures.

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_api.py tests/test_version_control.py -q
```

Expected: PASS.

## Task 5: MCP Version Tools

**Files:**
- Modify: `src/mcp/schemas.py`
- Modify: `src/mcp/tools.py`
- Modify: `src/mcp/server.py`
- Test: `tests/test_mcp.py`

- [ ] **Step 1: Write MCP tests**

Assert schema validation and handler results for:

- `list_version_groups`
- `get_version_group`
- `get_version_for_doc`
- `compare_versions`

Use a temporary registry injection or reset the module-level registry singleton after creating test data, following existing `tests/test_mcp.py` patterns.

- [ ] **Step 2: Add schemas**

Add `VersionSummary`, `VersionGroupOutput`, `ListVersionGroupsInput`, `GetVersionGroupInput`, `GetVersionForDocInput`, and `CompareVersionsInput`. Also add `version_group_id: str | None` and `version_number: int | None` to `SearchDocsInput`.

- [ ] **Step 3: Add tools**

Implement tools that call registry/version diff service. For search, when version fields are provided, pass them through `filters` as `version_group_id` and `version_number`.

- [ ] **Step 4: Register tools**

Add tool definitions to `TOOLS` and dispatch entries to `_DISPATCH`.

- [ ] **Step 5: Run MCP tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_mcp.py tests/test_version_control.py -q
```

Expected: PASS.

## Task 6: Version-Aware Retrieval

**Files:**
- Modify: `src/retrieval/retrieval_service.py`
- Modify: `src/retrieval/evidence_pack.py` if `SearchResultItem` needs normalized extra fields.
- Test: `tests/test_retrieval.py`

- [ ] **Step 1: Write retrieval tests**

Create two versioned documents with parsed `chunks.json` fixtures. Assert:

- `filters={"version_group_id": group_id}` searches both docs.
- `filters={"version_group_id": group_id, "version_number": 2}` searches only v2.
- Returned items include `version_group_id`, `version_number`, and `version_label` where available.

- [ ] **Step 2: Implement filter resolution**

At the top of `RetrievalService.search_docs`, before vector/keyword search:

```python
filters, version_map = self._resolve_version_filters(filters)
```

`_resolve_version_filters` should use the registry to convert version filters to `filters["doc_id"] = [...]`. After result enrichment, attach version metadata to chunks by `doc_id`.

- [ ] **Step 3: Run retrieval tests**

Run:

```bash
PYTHONPATH=. pytest tests/test_retrieval.py tests/test_mcp.py -q
```

Expected: PASS.

## Task 7: Frontend API Types and Workflow Tab

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/workflow.ts`
- Test: `frontend/lib/workflow.test.ts`

- [ ] **Step 1: Add TypeScript types**

Add:

```typescript
export type VersionSummary = {
  version_id: string;
  group_id: string;
  doc_id: string;
  version_label: string;
  version_number: number;
  is_latest: boolean;
  notes: string;
  created_at: string;
  filename?: string;
  page_count?: number | null;
  status?: string;
  upload_time?: string;
};

export type DocumentGroup = {
  group_id: string;
  name: string;
  base_filename: string;
  project: string;
  notes: string;
  version_count: number;
  latest_doc_id?: string | null;
  latest_label?: string | null;
  versions?: VersionSummary[];
};

export type VersionUploadOptions = {
  version_group_id?: string;
  version_label?: string;
  version_notes?: string;
  auto_group?: boolean;
  group_name?: string;
};

export type DeleteVersionResult = {
  status: "deleted" | "not_found";
  removed_version?: VersionSummary;
  latest_version?: VersionSummary | null;
  cleanup?: { status: string; warnings?: string[] };
};
```

- [ ] **Step 2: Add API helpers**

Add:

```typescript
export function listVersionGroups(project?: string) { ... }
export function getVersionGroup(groupId: string) { ... }
export function suggestVersionGroup(filename: string, project = "default") { ... }
export function compareVersions(groupId: string, sourceVersion: number, targetVersion: number) { ... }
export function getDocumentVersion(docId: string) { ... }
export function deleteVersion(groupId: string, versionNumber: number) { ... }
```

Extend `uploadDocument` callers by appending version fields to the existing `FormData`; do not create a second upload endpoint.

- [ ] **Step 3: Add workflow tab**

Add `"Versions"` to the `WorkflowTab` union and any tests that enumerate valid tabs.

- [ ] **Step 4: Run frontend unit tests and type check**

Run:

```bash
cd frontend
npm test -- --run
npm run typecheck
```

Expected: PASS. If `typecheck` is not defined, use `npx tsc --noEmit`.

## Task 8: Unified Version History and Versions Workspace UI

**Files:**
- Create: `frontend/components/workspace/version-history.tsx`
- Create: `frontend/components/workspace/versions-view.tsx`
- Modify: `frontend/components/workspace.tsx`
- Modify: `frontend/components/workspace/inspect-view.tsx`

- [ ] **Step 1: Add workspace query wiring**

In `workspace.tsx`, add a `useQuery` for `["version-groups"]` when `activeTab === "Versions"` or when the selected document has version metadata, add the nav item with a `GitBranch` or `History` lucide icon, and pass documents plus callbacks into `VersionsView` and `InspectView`.

- [ ] **Step 2: Build reusable `VersionHistory`**

Create a shared component with this shape:

```typescript
type VersionHistoryProps = {
  group: DocumentGroup | null;
  selectedDocId?: string | null;
  selectedVersions?: number[];
  onSelectDoc: (docId: string) => void;
  onToggleCompareVersion?: (versionNumber: number) => void;
  onCompareSelected?: () => void;
  onDeleteVersion?: (versionNumber: number) => void;
  isDeletingVersion?: boolean;
  compact?: boolean;
};
```

It must render one consistent version timeline everywhere: version label, filename, upload date, status, page count, latest badge, selection checkbox, switch button, and delete button. The selected/current version must be visually distinct. The delete action must show a confirmation state that includes the version label and filename before calling `onDeleteVersion`.

- [ ] **Step 3: Build `VersionsView`**

The view should include:

- Group list with name, project, version count, latest label, and updated time.
- Search input filtering groups by name/project.
- The reusable `VersionHistory` timeline ordered newest first with version labels, filename, status, page count, notes, latest badge, switch action, and delete action.
- Two-version selection with stable checkboxes; once two are selected, enable "Compare selected".
- Compare result panel can reuse the same finding list shape as `CompareView`, but it should be embedded inside the Versions view and labeled with `source_label -> target_label`.

- [ ] **Step 4: Add inline version switching to Inspect**

In `inspect-view.tsx`, render the compact `VersionHistory` for the selected document's group above the existing document inspection content. Selecting another version should call the shared `setSelectedDocId` path and keep the active tab as `Inspect`; the page/artifact queries should naturally refetch for the new document.

- [ ] **Step 5: Hook interactions**

Clicking or pressing "Switch" on a version should select that document. In the Versions tab, this may switch to `Inspect` only when the user explicitly chooses "Open"; quick switching inside the unified history should update the selected document while keeping the Versions tab visible. Comparing selected versions should call `compareVersions`, invalidate compare queries if needed, and render findings inline.
Deleting a version should call `deleteVersion`, invalidate `["documents"]`, `["version-groups"]`, `["version-group", groupId]`, and any selected document/version queries, then select the returned latest version when the currently selected document was deleted.

- [ ] **Step 6: Manual UI check**

Run the frontend and inspect desktop and mobile widths:

```bash
cd frontend
npm run dev
```

Expected: the Versions tab renders without overlap, group list remains scrollable, the same version-history UI appears in Inspect, switching versions updates the selected document, and the compare panel can be used after selecting two versions.

## Task 9: Version Upload Controls

**Files:**
- Modify: `frontend/components/workspace/process-view.tsx`
- Modify: `frontend/components/workspace.tsx`

- [ ] **Step 1: Move file selection metadata into state**

Keep existing upload behavior, but when a file is selected, store the file name so the UI can call `suggestVersionGroup(filename)`.

- [ ] **Step 2: Add upload controls**

Add controls near the upload action:

- Toggle: "Link to version group".
- Select: existing group when toggle is on.
- Input: version label with placeholder `v{next}`.
- Input: version notes.
- Auto-group suggestion badge when the backend returns a confident match.

Use these fields to append `version_group_id`, `version_label`, `version_notes`, `auto_group`, and `group_name` to the upload `FormData`.

- [ ] **Step 3: Handle duplicate response**

When `uploadDocument` receives a 409 response, surface the existing version label/group in the existing error area instead of showing a generic upload failure.

- [ ] **Step 4: Manual upload check**

Upload two small test files with similar names and confirm the second upload lands in the existing group and defaults to the next version label.

- [ ] **Step 5: Manual delete check**

Delete one uploaded/imported version from the unified version history. Confirm the version disappears from the timeline, the document disappears from the library, the latest badge moves to the highest remaining version, and switching still works for remaining versions.

## Task 10: Full Verification

**Files:**
- No new files unless earlier tasks reveal missing tests.

- [ ] **Step 1: Run backend focused tests**

```bash
PYTHONPATH=. pytest tests/test_version_control.py tests/test_api.py tests/test_mcp.py tests/test_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 2: Run backend regression tests**

```bash
PYTHONPATH=. pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend checks**

```bash
cd frontend
npm test -- --run
npx tsc --noEmit
npm run lint
```

Expected: PASS. If `lint` is not defined in `package.json`, record that it is unavailable.

- [ ] **Step 4: Manual end-to-end check**

1. Upload `architecture_v1.pdf`.
2. Confirm `GET /api/groups` shows a new group with one version.
3. Upload `architecture_v2.pdf`.
4. Confirm it auto-groups as version 2.
5. Re-upload the exact same `architecture_v2.pdf`.
6. Confirm 409 duplicate response includes existing version metadata.
7. Run the pipeline for both versions.
8. Open the Versions tab and confirm timeline, latest badge, and document navigation.
9. Open a document in Inspect and confirm the same unified version history is visible.
10. Switch from v2 to v1 in Inspect and confirm the selected document/artifacts update.
11. Select v1 and v2, run compare, and confirm a `version_diff` compare run is created.
12. Delete v1 from the unified history and confirm v2 remains selectable and latest.
13. Use MCP `list_version_groups`, `get_version_group`, and `compare_versions`.
14. Use MCP `search_docs` with `version_group_id` and confirm results are labeled by version.

## Implementation Notes

- Do not change the core compare algorithm unless tests prove it is necessary; `compare_service.py` already supports `version_diff`.
- Do not add a new `/api/upload` endpoint; the app currently uploads through `POST /api/documents`.
- Keep duplicate SHA-256 uniqueness on `documents.sha256`; the change is response behavior, not duplicate storage.
- Keep whole version-group deletion out of this release unless explicitly requested. Individual version deletion is in scope and must remove the underlying document/artifacts, then recompute the latest remaining version.
- Existing uncommitted work outside this plan should be left untouched during implementation.
