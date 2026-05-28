"""SQLite-backed document registry and pipeline state tracker."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
    status TEXT DEFAULT 'uploaded'
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
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            if "tags_json" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN tags_json TEXT DEFAULT '[]'")

    def _row_to_document(self, row: sqlite3.Row) -> dict:
        doc = dict(row)
        raw_tags = doc.pop("tags_json", None)
        try:
            tags = json.loads(raw_tags or "[]")
        except json.JSONDecodeError:
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

    def list_documents(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY upload_time DESC"
            ).fetchall()
            return [self._row_to_document(r) for r in rows]

    def get_pipeline_status(self, doc_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_steps WHERE doc_id = ? ORDER BY id",
                (doc_id,)
            ).fetchall()
            return [dict(r) for r in rows]

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
            runs = []
            for row in rows:
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
                    {**dict(event_row), "payload": json.loads(event_row["payload_json"])}
                    for event_row in event_rows
                ]
                for event in run["events"]:
                    event.pop("payload_json", None)
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
                {**dict(event_row), "payload": json.loads(event_row["payload_json"])}
                for event_row in event_rows
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
        with self._conn() as conn:
            for finding in findings:
                conn.execute(
                    """INSERT INTO compare_findings
                    (finding_id, run_id, type, severity, title, description,
                     source_evidence_json, target_evidence_json, normalized_key,
                     llm_status, llm_summary, llm_recommendation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    ),
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
