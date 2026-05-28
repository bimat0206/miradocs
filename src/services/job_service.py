"""In-memory local job state and SSE event queues."""
import json
import queue as queue_module
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Job:
    job_id: str
    doc_id: str
    status: str = "queued"
    events: list[dict] = field(default_factory=list)
    queue: queue_module.Queue = field(default_factory=queue_module.Queue)
    next_seq: int = 0


_MAX_COMPLETED_JOBS = 200


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.active_by_doc: dict[str, str] = {}

    def create(self, doc_id: str) -> Job:
        self._evict_completed()
        job = Job(job_id=uuid.uuid4().hex, doc_id=doc_id)
        self.jobs[job.job_id] = job
        self.active_by_doc[doc_id] = job.job_id
        self.emit(job.job_id, "queued", {"message": "Pipeline queued"})
        return job

    def _evict_completed(self):
        completed = [jid for jid, j in self.jobs.items() if j.status in {"done", "failed"}]
        if len(completed) <= _MAX_COMPLETED_JOBS:
            return
        for jid in completed[: len(completed) - _MAX_COMPLETED_JOBS]:
            self.jobs.pop(jid, None)

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def active_for_doc(self, doc_id: str) -> Job | None:
        job_id = self.active_by_doc.get(doc_id)
        if not job_id:
            return None
        job = self.jobs.get(job_id)
        if not job or job.status in {"done", "failed"}:
            self.active_by_doc.pop(doc_id, None)
            return None
        return job

    def emit(self, job_id: str, event_type: str, payload: dict[str, Any]):
        job = self.jobs[job_id]
        event = {
            "seq": job.next_seq,
            "type": event_type,
            "job_id": job_id,
            "doc_id": job.doc_id,
            "timestamp": time.time(),
            **payload,
        }
        job.next_seq += 1
        if event_type in {"done", "failed"}:
            job.status = event_type
            self.active_by_doc.pop(job.doc_id, None)
        elif event_type == "running":
            job.status = "running"
        job.events.append(event)
        job.queue.put(event)
        return event

    def stream(self, job_id: str) -> Iterator[str]:
        job = self.jobs.get(job_id)
        if not job:
            yield _sse({"type": "failed", "message": "Job not found"})
            return

        sent = 0
        last_sent_seq = -1
        while True:
            while sent < len(job.events):
                event = job.events[sent]
                sent += 1
                last_sent_seq = max(last_sent_seq, event.get("seq", -1))
                yield _sse(event)
                if event["type"] in {"done", "failed"}:
                    return
            try:
                event = job.queue.get(timeout=15)
                if event.get("seq", -1) <= last_sent_seq:
                    continue
                if sent < len(job.events):
                    continue
                last_sent_seq = max(last_sent_seq, event.get("seq", -1))
                yield _sse(event)
                if event["type"] in {"done", "failed"}:
                    return
            except queue_module.Empty:
                yield ": keepalive\n\n"


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
