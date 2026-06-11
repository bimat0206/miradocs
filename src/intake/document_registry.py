"""SQLite-backed document registry and pipeline state tracker."""
import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from src.config import get_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    project TEXT DEFAULT 'default',
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    upload_time TEXT NOT NULL,
    document_type TEXT DEFAULT 'Other',
    domain TEXT DEFAULT 'General',
    sensitivity TEXT DEFAULT 'Internal',
    tags_json TEXT DEFAULT '[]',
    status TEXT DEFAULT 'uploaded',
    page_count INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
    UNIQUE(doc_id, step_name)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds REAL,
    result_json TEXT,
    error_message TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE IF NOT EXISTS pipeline_run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_events_run_id ON pipeline_run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_steps_doc_id ON pipeline_steps(doc_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_doc_id ON pipeline_runs(doc_id);

CREATE TABLE IF NOT EXISTS compare_runs (
    run_id TEXT PRIMARY KEY,
    source_doc_id TEXT NOT NULL,
    target_doc_id TEXT NOT NULL,
    requested_mode TEXT NOT NULL,
    detected_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_json TEXT DEFAULT '{}',
    error_message TEXT,
    FOREIGN KEY (source_doc_id) REFERENCES documents(doc_id),
    FOREIGN KEY (target_doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE IF NOT EXISTS compare_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    source_evidence_json TEXT DEFAULT '[]',
    target_evidence_json TEXT DEFAULT '[]',
    normalized_key TEXT NOT NULL,
    llm_status TEXT DEFAULT 'not_requested',
    llm_summary TEXT,
    llm_recommendation TEXT,
    FOREIGN KEY (run_id) REFERENCES compare_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_compare_findings_run_id ON compare_findings(run_id);

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

"""

PIPELINE_STEPS = [
    "parsed", "page_images", "tables_extracted",
    "figures_extracted", "entities_extracted",
    "relations_extracted",
    "metadata_built", "quality_checked",
    "chunks_created", "indexed"
]


class DocumentRegistry:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            if "tags_json" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN tags_json TEXT DEFAULT '[]'")
            if "page_count" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN page_count INTEGER DEFAULT NULL")
            # Migration guard for document_groups.notes (added in v1.8)
            group_cols = {row["name"] for row in conn.execute("PRAGMA table_info(document_groups)").fetchall()}
            if group_cols and "notes" not in group_cols:
                conn.execute("ALTER TABLE document_groups ADD COLUMN notes TEXT DEFAULT ''")

    def _row_to_document(self, row: sqlite3.Row) -> dict:
        doc = dict(row)
        raw_tags = doc.pop("tags_json", None)
        try:
            tags = json.loads(raw_tags or "[]")
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse tags_json for doc %s: %s", doc.get("doc_id"), exc)
            tags = []
        doc["tags"] = [str(tag) for tag in tags if str(tag).strip()]
        return doc

    def register_document(
        self, filename: str, file_type: str, file_size: int, sha256: str,
        project: str = "default", document_type: str = "Other",
        domain: str = "General", sensitivity: str = "Internal",
        tags: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Register a new document. Returns doc_id or None if duplicate."""
        doc_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        clean_tags = [tag.strip() for tag in (tags or []) if tag.strip()][:5]
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
            if existing:
                return None
            conn.execute(
                """INSERT INTO documents
                (doc_id, project, filename, file_type, file_size, sha256,
                 upload_time, document_type, domain, sensitivity, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, project, filename, file_type, file_size, sha256,
                 now, document_type, domain, sensitivity, json.dumps(clean_tags))
            )
            for step in PIPELINE_STEPS:
                conn.execute(
                    "INSERT INTO pipeline_steps (doc_id, step_name) VALUES (?, ?)",
                    (doc_id, step)
                )
        return doc_id

    def get_document(self, doc_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            return self._row_to_document(row) if row else None

    def get_documents_batch(self, doc_ids: list[str]) -> list[dict]:
        """Return docs for all given doc_ids in a single query."""
        if not doc_ids:
            return []
        placeholders = ",".join("?" for _ in doc_ids)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM documents WHERE doc_id IN ({placeholders})",
                doc_ids,
            ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def list_documents(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY upload_time DESC"
            ).fetchall()
            return [self._row_to_document(r) for r in rows]

    def list_documents_by_tag(self, tag: str) -> list[dict]:
        """Return documents whose tags_json contains tag (case-insensitive)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT d.* FROM documents d, json_each(d.tags_json) t
                   WHERE LOWER(t.value) = LOWER(?)
                   ORDER BY d.upload_time DESC""",
                (tag,),
            ).fetchall()
            return [self._row_to_document(r) for r in rows]

    def get_pipeline_status(self, doc_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_steps WHERE doc_id = ? ORDER BY id",
                (doc_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_pipeline_status_batch(self, doc_ids: list[str]) -> dict[str, list[dict]]:
        """Return {doc_id: [steps]} for all given doc_ids in a single query."""
        if not doc_ids:
            return {}
        placeholders = ",".join("?" for _ in doc_ids)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM pipeline_steps WHERE doc_id IN ({placeholders}) ORDER BY doc_id, id",
                doc_ids,
            ).fetchall()
        result: dict[str, list[dict]] = {d: [] for d in doc_ids}
        for r in rows:
            result[r["doc_id"]].append(dict(r))
        return result

    def update_step(
        self, doc_id: str, step_name: str, status: str,
        error_message: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            if status == "running":
                conn.execute(
                    """UPDATE pipeline_steps
                    SET status = ?, started_at = ?, completed_at = NULL, error_message = NULL
                    WHERE doc_id = ? AND step_name = ?""",
                    (status, now, doc_id, step_name)
                )
            else:
                conn.execute(
                    """UPDATE pipeline_steps
                    SET status = ?, completed_at = ?, error_message = ?
                    WHERE doc_id = ? AND step_name = ?""",
                    (status, now, error_message, doc_id, step_name)
                )

    def create_pipeline_run(self, doc_id: str, run_id: Optional[str] = None) -> str:
        run_id = run_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pipeline_runs
                (run_id, doc_id, status, started_at)
                VALUES (?, ?, ?, ?)""",
                (run_id, doc_id, "queued", now),
            )
        return run_id

    def update_pipeline_run(
        self,
        run_id: str,
        status: str,
        result: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT started_at FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return
            duration = None
            completed_at = None
            if status in {"done", "failed"}:
                completed_at = now
                started = datetime.fromisoformat(row["started_at"])
                duration = (datetime.fromisoformat(now) - started).total_seconds()
            conn.execute(
                """UPDATE pipeline_runs
                SET status = ?, completed_at = COALESCE(?, completed_at),
                    duration_seconds = COALESCE(?, duration_seconds),
                    result_json = COALESCE(?, result_json),
                    error_message = ?
                WHERE run_id = ?""",
                (
                    status,
                    completed_at,
                    duration,
                    json.dumps(result) if result is not None else None,
                    error_message,
                    run_id,
                ),
            )

    def add_pipeline_run_event(self, run_id: str, event: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pipeline_run_events
                (run_id, event_type, timestamp, payload_json)
                VALUES (?, ?, ?, ?)""",
                (
                    run_id,
                    event.get("type", "event"),
                    float(event.get("timestamp", 0)),
                    json.dumps(event),
                ),
            )

    def get_pipeline_runs(self, doc_id: str, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM pipeline_runs
                WHERE doc_id = ?
                ORDER BY started_at DESC
                LIMIT ?""",
                (doc_id, limit),
            ).fetchall()
            if not rows:
                return []
            run_ids = [r["run_id"] for r in rows]
            placeholders = ",".join("?" for _ in run_ids)
            event_rows = conn.execute(
                f"""SELECT run_id, event_type, timestamp, payload_json
                FROM pipeline_run_events
                WHERE run_id IN ({placeholders})
                ORDER BY id""",
                run_ids,
            ).fetchall()
        events_by_run: dict[str, list[dict]] = {rid: [] for rid in run_ids}
        for ev in event_rows:
            entry = dict(ev)
            entry["payload"] = json.loads(entry.pop("payload_json"))
            events_by_run[ev["run_id"]].append(entry)
        runs = []
        for row in rows:
            run = dict(row)
            run["result"] = json.loads(run.pop("result_json")) if run.get("result_json") else None
            run["events"] = events_by_run.get(run["run_id"], [])
            runs.append(run)
        return runs

    def get_latest_pipeline_run(
        self,
        doc_id: str,
        statuses: Optional[list[str]] = None,
    ) -> Optional[dict]:
        params: list[Any] = [doc_id]
        status_filter = ""
        if statuses:
            status_filter = f" AND status IN ({','.join('?' for _ in statuses)})"
            params.extend(statuses)
        with self._conn() as conn:
            row = conn.execute(
                f"""SELECT * FROM pipeline_runs
                WHERE doc_id = ?{status_filter}
                ORDER BY started_at DESC
                LIMIT 1""",
                params,
            ).fetchone()
            if not row:
                return None
            run = dict(row)
            run["result"] = json.loads(run.pop("result_json")) if run.get("result_json") else None
            event_rows = conn.execute(
                """SELECT event_type, timestamp, payload_json
                FROM pipeline_run_events
                WHERE run_id = ?
                ORDER BY id""",
                (run["run_id"],),
            ).fetchall()
            run["events"] = [
                {**dict(ev), "payload": json.loads(ev["payload_json"])}
                for ev in event_rows
            ]
            for event in run["events"]:
                event.pop("payload_json", None)
            return run

    def update_document_status(self, doc_id: str, status: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET status = ? WHERE doc_id = ?",
                (status, doc_id)
            )

    def update_document_page_count(self, doc_id: str, page_count: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET page_count = ? WHERE doc_id = ?",
                (page_count, doc_id),
            )

    def update_document_tags(self, doc_id: str, tags: list[str]) -> Optional[dict]:
        clean_tags = []
        seen = set()
        for value in tags:
            tag = str(value).strip()
            key = tag.casefold()
            if tag and key not in seen:
                clean_tags.append(tag[:32])
                seen.add(key)
            if len(clean_tags) == 5:
                break
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if not existing:
                return None
            conn.execute(
                "UPDATE documents SET tags_json = ? WHERE doc_id = ?",
                (json.dumps(clean_tags), doc_id),
            )
        return self.get_document(doc_id)

    def create_compare_run(
        self,
        *,
        source_doc_id: str,
        target_doc_id: str,
        requested_mode: str,
        detected_mode: str,
    ) -> str:
        run_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO compare_runs
                (run_id, source_doc_id, target_doc_id, requested_mode, detected_mode, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, source_doc_id, target_doc_id, requested_mode, detected_mode, "running", now),
            )
        return run_id

    def complete_compare_run(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """UPDATE compare_runs
                SET status = ?, completed_at = ?, summary_json = COALESCE(?, summary_json), error_message = ?
                WHERE run_id = ?""",
                (
                    status,
                    now,
                    json.dumps(summary) if summary is not None else None,
                    error_message,
                    run_id,
                ),
            )

    def add_compare_findings(self, run_id: str, findings: list[dict[str, Any]]):
        rows = [
            (
                finding.get("finding_id") or uuid.uuid4().hex,
                run_id,
                finding["type"],
                finding["severity"],
                finding["title"],
                finding["description"],
                json.dumps(finding.get("source_evidence", [])),
                json.dumps(finding.get("target_evidence", [])),
                finding.get("normalized_key", finding["title"]),
                finding.get("llm_status", "not_requested"),
                finding.get("llm_summary"),
                finding.get("llm_recommendation"),
            )
            for finding in findings
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO compare_findings
                (finding_id, run_id, type, severity, title, description,
                 source_evidence_json, target_evidence_json, normalized_key,
                 llm_status, llm_summary, llm_recommendation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def get_compare_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            run_row = conn.execute(
                "SELECT * FROM compare_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not run_row:
                return None
            finding_rows = conn.execute(
                "SELECT * FROM compare_findings WHERE run_id = ? ORDER BY severity, type, title",
                (run_id,),
            ).fetchall()
        run = self._row_to_compare_run(run_row)
        return {
            "run": run,
            "summary": run.get("summary", {}),
            "findings": [self._row_to_compare_finding(row) for row in finding_rows],
        }

    def get_compare_runs_for_doc(self, doc_id: str, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM compare_runs
                WHERE source_doc_id = ? OR target_doc_id = ?
                ORDER BY started_at DESC
                LIMIT ?""",
                (doc_id, doc_id, limit),
            ).fetchall()
        return [self._row_to_compare_run(row) for row in rows]

    def _row_to_compare_run(self, row: sqlite3.Row) -> dict:
        run = dict(row)
        try:
            run["summary"] = json.loads(run.pop("summary_json") or "{}")
        except json.JSONDecodeError:
            run["summary"] = {}
        return run

    def _row_to_compare_finding(self, row: sqlite3.Row) -> dict:
        finding = dict(row)
        try:
            finding["source_evidence"] = json.loads(finding.pop("source_evidence_json") or "[]")
        except json.JSONDecodeError:
            finding["source_evidence"] = []
        try:
            finding["target_evidence"] = json.loads(finding.pop("target_evidence_json") or "[]")
        except json.JSONDecodeError:
            finding["target_evidence"] = []
        return finding

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its pipeline state from the registry."""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if not existing:
                return False
            run_ids = conn.execute(
                "SELECT run_id FROM pipeline_runs WHERE doc_id = ?", (doc_id,)
            ).fetchall()
            for run in run_ids:
                conn.execute("DELETE FROM pipeline_run_events WHERE run_id = ?", (run["run_id"],))
            compare_run_ids = conn.execute(
                "SELECT run_id FROM compare_runs WHERE source_doc_id = ? OR target_doc_id = ?",
                (doc_id, doc_id),
            ).fetchall()
            for run in compare_run_ids:
                conn.execute("DELETE FROM compare_findings WHERE run_id = ?", (run["run_id"],))
            conn.execute("DELETE FROM compare_runs WHERE source_doc_id = ? OR target_doc_id = ?", (doc_id, doc_id))
            conn.execute("DELETE FROM pipeline_runs WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM pipeline_steps WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        return True

    def find_by_hash(self, sha256: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
            return self._row_to_document(row) if row else None

    # ─── Version Group helpers ────────────────────────────────────────────────

    def _row_to_version(self, row: sqlite3.Row) -> dict:
        """Convert a document_versions row (optionally joined with documents) to dict."""
        v = dict(row)
        v["is_latest"] = bool(v.get("is_latest", 0))
        return v

    def create_or_find_group(
        self,
        name: str,
        base_filename: str,
        project: str = "default",
        notes: str = "",
    ) -> dict:
        """Return existing group for (project, base_filename) or create a new one."""
        now = datetime.now(timezone.utc).isoformat()
        group_id = uuid.uuid4().hex
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM document_groups WHERE project = ? AND base_filename = ?",
                (project, base_filename),
            ).fetchone()
            if existing:
                return dict(existing)
            conn.execute(
                """INSERT INTO document_groups
                (group_id, name, base_filename, project, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (group_id, name, base_filename, project, notes, now, now),
            )
        return self.get_group(group_id, include_versions=False)

    def update_group(
        self,
        group_id: str,
        *,
        name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        """Update group name and/or notes. Returns updated group or None if not found."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM document_groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not existing:
                return None
            new_name = name if name is not None else existing["name"]
            new_notes = notes if notes is not None else existing["notes"]
            conn.execute(
                "UPDATE document_groups SET name = ?, notes = ?, updated_at = ? WHERE group_id = ?",
                (new_name, new_notes, now, group_id),
            )
        return self.get_group(group_id, include_versions=False)

    def add_version(
        self,
        group_id: str,
        doc_id: str,
        label: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """Add a document as a new version to a group. Auto-assigns version_number and label."""
        now = datetime.now(timezone.utc).isoformat()
        version_id = uuid.uuid4().hex
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS mx FROM document_versions WHERE group_id = ?",
                (group_id,),
            ).fetchone()
            next_num = (row["mx"] if row else 0) + 1
            version_label = label if label else f"v{next_num}"
            conn.execute(
                """INSERT INTO document_versions
                (version_id, group_id, doc_id, version_label, version_number, is_latest, notes, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
                (version_id, group_id, doc_id, version_label, next_num, notes, now),
            )
            # Update group updated_at
            conn.execute(
                "UPDATE document_groups SET updated_at = ? WHERE group_id = ?",
                (now, group_id),
            )
        return self.get_version_for_doc(doc_id)

    def set_latest_version(self, group_id: str, doc_id: str) -> None:
        """Mark doc_id as the latest version in the group; clear is_latest on all others."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE document_versions SET is_latest = 0 WHERE group_id = ?",
                (group_id,),
            )
            conn.execute(
                "UPDATE document_versions SET is_latest = 1 WHERE group_id = ? AND doc_id = ?",
                (group_id, doc_id),
            )
            conn.execute(
                "UPDATE document_groups SET updated_at = ? WHERE group_id = ?",
                (now, group_id),
            )

    def get_group(self, group_id: str, include_versions: bool = True) -> Optional[dict]:
        """Return group dict (optionally with nested versions list)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM document_groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if not row:
                return None
            group = dict(row)
        if include_versions:
            group["versions"] = self.get_versions_for_group(group_id)
        return group

    def get_group_for_doc(self, doc_id: str) -> Optional[dict]:
        """Return the group that contains doc_id, or None."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT g.* FROM document_groups g
                   JOIN document_versions v ON v.group_id = g.group_id
                   WHERE v.doc_id = ?""",
                (doc_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_groups(self, project: Optional[str] = None) -> list[dict]:
        """List all groups, optionally filtered by project, with version count and latest info."""
        with self._conn() as conn:
            if project:
                rows = conn.execute(
                    "SELECT * FROM document_groups WHERE project = ? ORDER BY updated_at DESC",
                    (project,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM document_groups ORDER BY updated_at DESC"
                ).fetchall()
        result = []
        for row in rows:
            group = dict(row)
            versions = self.get_versions_for_group(group["group_id"])
            group["version_count"] = len(versions)
            latest = next((v for v in versions if v["is_latest"]), None)
            group["latest_doc_id"] = latest["doc_id"] if latest else None
            group["latest_label"] = latest["version_label"] if latest else None
            result.append(group)
        return result

    def get_versions_for_group(self, group_id: str) -> list[dict]:
        """Return all versions for a group ordered by version_number ASC, joined with doc info."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT v.*, d.filename, d.status, d.upload_time, d.page_count
                   FROM document_versions v
                   LEFT JOIN documents d ON d.doc_id = v.doc_id
                   WHERE v.group_id = ?
                   ORDER BY v.version_number ASC""",
                (group_id,),
            ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def get_version(self, group_id: str, version_number: int) -> Optional[dict]:
        """Return a single version row joined with doc info, or None."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT v.*, d.filename, d.status, d.upload_time, d.page_count
                   FROM document_versions v
                   LEFT JOIN documents d ON d.doc_id = v.doc_id
                   WHERE v.group_id = ? AND v.version_number = ?""",
                (group_id, version_number),
            ).fetchone()
        return self._row_to_version(row) if row else None

    def get_version_for_doc(self, doc_id: str) -> Optional[dict]:
        """Return the version row for a given doc_id (joined with doc info), or None."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT v.*, d.filename, d.status, d.upload_time, d.page_count
                   FROM document_versions v
                   LEFT JOIN documents d ON d.doc_id = v.doc_id
                   WHERE v.doc_id = ?""",
                (doc_id,),
            ).fetchone()
        return self._row_to_version(row) if row else None

    def remove_version(self, group_id: str, version_number: int) -> Optional[dict]:
        """Delete a document_versions row and return its metadata. Does NOT delete the document."""
        ver = self.get_version(group_id, version_number)
        if not ver:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM document_versions WHERE group_id = ? AND version_number = ?",
                (group_id, version_number),
            )
            conn.execute(
                "UPDATE document_groups SET updated_at = ? WHERE group_id = ?",
                (now, group_id),
            )
        return ver

    def recompute_latest_version(self, group_id: str) -> Optional[dict]:
        """Mark the highest remaining version_number as latest and return it (or None if empty)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE document_versions SET is_latest = 0 WHERE group_id = ?",
                (group_id,),
            )
            top = conn.execute(
                """SELECT version_number FROM document_versions
                   WHERE group_id = ? ORDER BY version_number DESC LIMIT 1""",
                (group_id,),
            ).fetchone()
            if not top:
                return None
            conn.execute(
                """UPDATE document_versions SET is_latest = 1
                   WHERE group_id = ? AND version_number = ?""",
                (group_id, top["version_number"]),
            )
            conn.execute(
                "UPDATE document_groups SET updated_at = ? WHERE group_id = ?",
                (now, group_id),
            )
        return self.get_version(group_id, top["version_number"])
