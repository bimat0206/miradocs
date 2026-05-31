"""Full workspace export/import — bundles DB + all artifacts + vector index snapshot."""
import io
import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from src.config import get_data_dir, get_db_path

logger = logging.getLogger(__name__)

EXPORT_VERSION = "1"
MANIFEST_FILENAME = "miradocs_export.json"

# Artifact sub-dirs relative to data_dir that are included in a full export
_ARTIFACT_DIRS = [
    "raw",
    "parsed",
    "page_images",
    "tables",
    "figures",
    "reports",
]

# Vector index dir relative to data_dir
_INDEX_DIR = "indexes"


# ─── Export ──────────────────────────────────────────────────────────────────

def export_workspace(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    doc_ids: list[str] | None = None,
) -> Iterator[bytes]:
    """Stream a ZIP archive of the full workspace.

    If doc_ids is provided only those documents (and their artifacts) are
    exported. Otherwise all documents are included.

    Yields bytes chunks suitable for a StreamingResponse.
    """
    data_dir = data_dir or get_data_dir()
    db_path = db_path or get_db_path()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        # Manifest first
        manifest = _build_manifest(db_path, doc_ids)
        zf.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2))

        # SQLite DB — copy to temp to avoid locking issues
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _backup_sqlite(db_path, tmp_path)
            if doc_ids:
                _filter_db(tmp_path, doc_ids)
            zf.write(tmp_path, "registry.db")
        finally:
            tmp_path.unlink(missing_ok=True)

        # Artifact directories
        for subdir in _ARTIFACT_DIRS:
            src = data_dir / subdir
            if not src.exists():
                continue
            if doc_ids:
                for doc_id in doc_ids:
                    _add_dir(zf, src / doc_id, f"data/{subdir}/{doc_id}")
            else:
                _add_dir(zf, src, f"data/{subdir}")

        # Vector index (Qdrant local — just copy the directory)
        index_src = data_dir / _INDEX_DIR
        if index_src.exists():
            _add_dir(zf, index_src, f"data/{_INDEX_DIR}")

    size = buf.tell()
    buf.seek(0)
    logger.info("Export complete: %.1f MB", size / 1_048_576)

    chunk_size = 1024 * 256  # 256 KB
    while True:
        chunk = buf.read(chunk_size)
        if not chunk:
            break
        yield chunk


def export_workspace_to_file(
    dest: Path,
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    doc_ids: list[str] | None = None,
) -> Path:
    """Write export ZIP to dest and return the path."""
    with open(dest, "wb") as fh:
        for chunk in export_workspace(data_dir=data_dir, db_path=db_path, doc_ids=doc_ids):
            fh.write(chunk)
    return dest


# ─── Import ──────────────────────────────────────────────────────────────────

def import_workspace(
    zip_bytes: bytes,
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    merge: bool = True,
) -> dict:
    """Import a workspace ZIP.

    merge=True  — keep existing documents, skip duplicates by sha256.
    merge=False — wipe and replace (destructive).

    Returns a summary dict.
    """
    data_dir = data_dir or get_data_dir()
    db_path = db_path or get_db_path()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

        if MANIFEST_FILENAME not in names:
            raise ValueError("Not a valid MiraDocs export (missing manifest)")

        manifest = json.loads(zf.read(MANIFEST_FILENAME))
        _validate_manifest(manifest)

        # ── DB merge / replace ────────────────────────────────────────────
        if "registry.db" not in names:
            raise ValueError("Export archive is missing registry.db")

        imported_docs: list[str] = []
        skipped_docs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_db = Path(tmp_dir) / "import.db"
            tmp_db.write_bytes(zf.read("registry.db"))

            if merge:
                imported_docs, skipped_docs = _merge_db(src=tmp_db, dst=db_path)
            else:
                shutil.copy2(tmp_db, db_path)
                imported_docs = manifest.get("doc_ids", [])

        # ── Artifact files ────────────────────────────────────────────────
        files_written = 0
        for name in names:
            if not name.startswith("data/"):
                continue
            rel = name[len("data/"):]
            dest = data_dir / rel
            if name.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
                continue
            # Skip artifacts for docs that were skipped (already exist)
            doc_id = _doc_id_from_path(rel)
            if doc_id and doc_id in skipped_docs:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            files_written += 1

    return {
        "status": "ok",
        "export_version": manifest.get("version"),
        "exported_at": manifest.get("exported_at"),
        "imported_docs": len(imported_docs),
        "skipped_docs": len(skipped_docs),
        "files_written": files_written,
        "doc_ids_imported": imported_docs,
        "doc_ids_skipped": skipped_docs,
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_manifest(db_path: Path, doc_ids: list[str] | None) -> dict:
    from src.api.main import _read_local_version
    doc_list: list[str] = []
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            if doc_ids:
                placeholders = ",".join("?" for _ in doc_ids)
                rows = conn.execute(
                    f"SELECT doc_id FROM documents WHERE doc_id IN ({placeholders})", doc_ids
                ).fetchall()
            else:
                rows = conn.execute("SELECT doc_id FROM documents").fetchall()
            doc_list = [r["doc_id"] for r in rows]
        finally:
            conn.close()

    return {
        "version": EXPORT_VERSION,
        "app_version": _read_local_version(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "doc_count": len(doc_list),
        "doc_ids": doc_list,
        "type": "full",
    }


def _backup_sqlite(src: Path, dst: Path):
    """Online backup of SQLite — safe under concurrent reads/writes."""
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()


def _filter_db(db_path: Path, doc_ids: list[str]):
    """Remove all documents not in doc_ids from a copy of the DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" for _ in doc_ids)
        keep_set = tuple(doc_ids)
        conn.execute(f"DELETE FROM documents WHERE doc_id NOT IN ({placeholders})", keep_set)
        conn.execute(f"DELETE FROM pipeline_steps WHERE doc_id NOT IN ({placeholders})", keep_set)
        # keep pipeline_runs and events for the kept docs
        run_ids = [r[0] for r in conn.execute(
            f"SELECT run_id FROM pipeline_runs WHERE doc_id NOT IN ({placeholders})", keep_set
        ).fetchall()]
        if run_ids:
            rp = ",".join("?" for _ in run_ids)
            conn.execute(f"DELETE FROM pipeline_run_events WHERE run_id IN ({rp})", run_ids)
            conn.execute(f"DELETE FROM pipeline_runs WHERE run_id IN ({rp})", run_ids)
        conn.commit()
    finally:
        conn.close()


def _merge_db(src: Path, dst: Path) -> tuple[list[str], list[str]]:
    """Merge src DB into dst. Skip documents that already exist (by sha256).

    Returns (imported_doc_ids, skipped_doc_ids).
    """
    if not dst.exists():
        shutil.copy2(src, dst)
        src_conn = sqlite3.connect(str(src))
        src_conn.row_factory = sqlite3.Row
        try:
            all_ids = [r["doc_id"] for r in src_conn.execute("SELECT doc_id FROM documents").fetchall()]
        finally:
            src_conn.close()
        return all_ids, []

    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    src_conn.row_factory = sqlite3.Row
    dst_conn.row_factory = sqlite3.Row
    imported: list[str] = []
    skipped: list[str] = []

    try:
        existing_hashes = {r["sha256"] for r in dst_conn.execute("SELECT sha256 FROM documents").fetchall()}
        src_docs = src_conn.execute("SELECT * FROM documents").fetchall()

        for doc in src_docs:
            if doc["sha256"] in existing_hashes:
                skipped.append(doc["doc_id"])
                continue
            doc_id = doc["doc_id"]
            # Insert document row
            cols = list(doc.keys())
            placeholders = ",".join("?" for _ in cols)
            dst_conn.execute(
                f"INSERT OR IGNORE INTO documents ({','.join(cols)}) VALUES ({placeholders})",
                tuple(doc[c] for c in cols),
            )
            # Insert pipeline steps
            for step in src_conn.execute(
                "SELECT * FROM pipeline_steps WHERE doc_id = ?", (doc_id,)
            ).fetchall():
                step_cols = list(step.keys())
                step_ph = ",".join("?" for _ in step_cols)
                dst_conn.execute(
                    f"INSERT OR IGNORE INTO pipeline_steps ({','.join(step_cols)}) VALUES ({step_ph})",
                    tuple(step[c] for c in step_cols),
                )
            # Insert pipeline runs + events
            for run in src_conn.execute(
                "SELECT * FROM pipeline_runs WHERE doc_id = ?", (doc_id,)
            ).fetchall():
                run_cols = list(run.keys())
                run_ph = ",".join("?" for _ in run_cols)
                dst_conn.execute(
                    f"INSERT OR IGNORE INTO pipeline_runs ({','.join(run_cols)}) VALUES ({run_ph})",
                    tuple(run[c] for c in run_cols),
                )
                for ev in src_conn.execute(
                    "SELECT * FROM pipeline_run_events WHERE run_id = ?", (run["run_id"],)
                ).fetchall():
                    ev_cols = list(ev.keys())
                    ev_ph = ",".join("?" for _ in ev_cols)
                    dst_conn.execute(
                        f"INSERT OR IGNORE INTO pipeline_run_events ({','.join(ev_cols)}) VALUES ({ev_ph})",
                        tuple(ev[c] for c in ev_cols),
                    )
            imported.append(doc_id)

        dst_conn.commit()
    finally:
        src_conn.close()
        dst_conn.close()

    return imported, skipped


def _add_dir(zf: zipfile.ZipFile, src: Path, arc_prefix: str):
    """Recursively add src directory into the zip under arc_prefix."""
    if not src.exists():
        return
    for path in src.rglob("*"):
        if path.is_file():
            arc_name = arc_prefix + "/" + path.relative_to(src).as_posix()
            zf.write(path, arc_name)


def _validate_manifest(manifest: dict):
    if manifest.get("version") != EXPORT_VERSION:
        raise ValueError(
            f"Unsupported export version: {manifest.get('version')} (expected {EXPORT_VERSION})"
        )


def _doc_id_from_path(rel: str) -> str | None:
    """Extract doc_id from paths like 'raw/<doc_id>/...' or 'parsed/<doc_id>/...'"""
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0] in _ARTIFACT_DIRS:
        return parts[1] if parts[1] else None
    return None
