"""Tests for local pipeline job state and SSE replay behavior."""

import json

from src.services.job_service import JobManager


def _event_type(sse_message: str) -> str:
    data_line = next(line for line in sse_message.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))["type"]


def test_active_job_is_tracked_until_terminal_event():
    manager = JobManager()
    job = manager.create("doc-1")

    assert manager.active_for_doc("doc-1") == job

    manager.emit(job.job_id, "running", {"message": "started"})
    assert manager.active_for_doc("doc-1") == job

    manager.emit(job.job_id, "done", {"message": "complete"})
    assert manager.active_for_doc("doc-1") is None


def test_stream_replays_history_once_and_skips_stale_queue_events():
    manager = JobManager()
    job = manager.create("doc-1")
    manager.emit(job.job_id, "running", {"message": "started"})

    stream = manager.stream(job.job_id)
    assert _event_type(next(stream)) == "queued"
    assert _event_type(next(stream)) == "running"

    manager.emit(job.job_id, "progress", {"step": "parsed", "percent": 0})
    manager.emit(job.job_id, "done", {"message": "complete"})

    assert _event_type(next(stream)) == "progress"
    assert _event_type(next(stream)) == "done"
