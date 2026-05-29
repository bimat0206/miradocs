"""FastAPI entrypoint for MiraDocs."""
import json
import threading
from pathlib import Path
from typing import Callable, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.config import get_data_dir
from src.intake.document_registry import DocumentRegistry
from src.services.document_service import (
    create_document,
    delete_document,
    list_documents,
    page_image_matches,
    page_image_path,
    read_artifact,
)
from src.services.index_service import get_index_status, index_document, search_document
from src.services.job_service import JobManager
from src.services.compare_service import CompareError, detect_compare_mode, run_compare
from src.services.pipeline_service import (
    process_steps_complete,
    repair_completed_running_steps,
    run_pipeline,
)


def parse_upload_tags(raw_tags: str) -> list[str]:
    try:
        parsed = json.loads(raw_tags)
    except json.JSONDecodeError:
        parsed = [tag.strip() for tag in raw_tags.split(",")]
    if not isinstance(parsed, list):
        return []
    clean_tags = []
    seen = set()
    for value in parsed:
        tag = str(value).strip()
        key = tag.casefold()
        if tag and key not in seen:
            clean_tags.append(tag[:32])
            seen.add(key)
        if len(clean_tags) == 5:
            break
    return clean_tags


class SearchRequest(BaseModel):
    doc_id: str | list[str]
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    hybrid: bool = True
    rerank: bool = False
    dense_weight: float = Field(default=0.7, ge=0, le=1)
    sparse_weight: float = Field(default=0.3, ge=0, le=1)
    search_mode: str = "auto"


class TagsUpdateRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class CompareModeRequest(BaseModel):
    source_doc_id: str
    target_doc_id: str


class CompareRunRequest(BaseModel):
    source_doc_id: str
    target_doc_id: str
    mode: str = "auto"


def _default_index_adapter_factory():
    from src.indexing.qdrant_adapter import QdrantAdapter
    return QdrantAdapter()


def create_app(
    *,
    registry: DocumentRegistry | None = None,
    data_dir: Path | None = None,
    index_adapter_factory: Callable[[], Any] | None = None,
    job_manager: JobManager | None = None,
) -> FastAPI:
    app = FastAPI(title="MiraDocs API", version=_read_local_version())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = registry or DocumentRegistry()
    app.state.data_dir = data_dir or get_data_dir()
    app.state.index_adapter_factory = index_adapter_factory or _default_index_adapter_factory
    app.state.jobs = job_manager or JobManager()

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": _read_local_version(),
            "data_dir": str(app.state.data_dir),
            "registry": str(app.state.registry.db_path),
        }

    @app.get("/api/documents")
    def documents(tag: str | None = None):
        if tag:
            docs = app.state.registry.list_documents_by_tag(tag)
        else:
            docs = list_documents(app.state.registry)
        return {"documents": docs}

    @app.get("/api/tags")
    def get_all_tags():
        docs = list_documents(app.state.registry)
        tags: dict[str, int] = {}
        for d in docs:
            for t in d.get("tags", []):
                tags[t] = tags.get(t, 0) + 1
        return {"tags": [{"name": k, "count": v} for k, v in sorted(tags.items())]}

    @app.post("/api/documents", status_code=201)
    async def upload_document(
        file: UploadFile = File(...),
        project: str = Form("default"),
        document_type: str = Form("Other"),
        domain: str = Form("General"),
        sensitivity: str = Form("Internal"),
        tags: str = Form("[]"),
    ):
        file_bytes = await file.read()
        doc = create_document(
            file_bytes=file_bytes,
            filename=file.filename or "document",
            project=project,
            document_type=document_type,
            domain=domain,
            sensitivity=sensitivity,
            tags=parse_upload_tags(tags),
            registry=app.state.registry,
            data_dir=app.state.data_dir,
        )
        return doc

    @app.get("/api/documents/{doc_id}")
    def get_document(doc_id: str):
        doc = app.state.registry.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        steps = app.state.registry.get_pipeline_status(doc_id)
        return {**doc, "pipeline_steps": steps}

    @app.delete("/api/documents/{doc_id}")
    def remove_document(doc_id: str):
        result = delete_document(
            doc_id,
            app.state.registry,
            app.state.data_dir,
            app.state.index_adapter_factory,
        )
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        return result

    @app.patch("/api/documents/{doc_id}/tags")
    def update_document_tags(doc_id: str, request: TagsUpdateRequest):
        doc = app.state.registry.update_document_tags(doc_id, request.tags)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    @app.get("/api/documents/{doc_id}/pipeline")
    def get_pipeline(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        repair_completed_running_steps(doc_id, app.state.registry, app.state.data_dir)
        return {"steps": app.state.registry.get_pipeline_status(doc_id)}

    @app.get("/api/documents/{doc_id}/pipeline/active")
    def get_active_pipeline(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        repair_completed_running_steps(doc_id, app.state.registry, app.state.data_dir)
        steps = app.state.registry.get_pipeline_status(doc_id)
        active_job = app.state.jobs.active_for_doc(doc_id)
        if active_job:
            run = app.state.registry.get_latest_pipeline_run(doc_id, [active_job.status, "queued", "running"])
            events = [event["payload"] for event in run["events"]] if run else active_job.events
            return {
                "job_id": active_job.job_id,
                "status": active_job.status,
                "run": run,
                "events": events,
                "steps": steps,
            }

        run = app.state.registry.get_latest_pipeline_run(doc_id, ["queued", "running"])
        if not run:
            return {
                "job_id": None,
                "status": None,
                "run": None,
                "events": [],
                "steps": steps,
            }
        return {
            "job_id": None,
            "status": run["status"],
            "run": run,
            "events": [event["payload"] for event in run["events"]],
            "steps": steps,
        }

    @app.post("/api/documents/{doc_id}/pipeline/run")
    def run_document_pipeline(doc_id: str):
        doc = app.state.registry.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        repair_completed_running_steps(doc_id, app.state.registry, app.state.data_dir)
        active_job = app.state.jobs.active_for_doc(doc_id)
        if active_job:
            return {"job_id": active_job.job_id, "status": active_job.status}
        steps = app.state.registry.get_pipeline_status(doc_id)
        if any(step["status"] == "running" for step in steps):
            raise HTTPException(
                status_code=409,
                detail="Pipeline is already marked running. Restart the app or wait for the active run to finish.",
            )

        # Determine if steps 1-9 are complete and indexing is pending/failed
        statuses = {step["step_name"]: step["status"] for step in steps}
        steps_1_9 = [
            "parsed", "page_images", "tables_extracted", "figures_extracted",
            "entities_extracted", "relations_extracted", "metadata_built",
            "quality_checked", "chunks_created",
        ]
        steps_1_8_complete = all(statuses.get(name) == "success" for name in steps_1_9)
        indexing_complete = statuses.get("indexed") == "success"

        if steps_1_8_complete and indexing_complete:
            # Everything is already success, return immediately
            job = app.state.jobs.create(doc_id)
            run_id = app.state.registry.create_pipeline_run(doc_id, job.job_id)
            for event in job.events:
                app.state.registry.add_pipeline_run_event(run_id, event)
            event = app.state.jobs.emit(
                job.job_id,
                "done",
                {"message": "Pipeline already complete", "result": {"status": doc["status"]}},
            )
            app.state.registry.add_pipeline_run_event(run_id, event)
            app.state.registry.update_pipeline_run(run_id, "done", result={"status": doc["status"]})
            return {"job_id": job.job_id, "status": "done"}

        if steps_1_8_complete and not indexing_complete:
            # Automating run index step since all preceding steps are successful
            job = app.state.jobs.create(doc_id)
            run_id = app.state.registry.create_pipeline_run(doc_id, job.job_id)
            for event in job.events:
                app.state.registry.add_pipeline_run_event(run_id, event)

            def emit_job(event_type: str, payload: dict[str, Any]):
                event = app.state.jobs.emit(job.job_id, event_type, payload)
                app.state.registry.add_pipeline_run_event(run_id, event)
                if event_type in {"running", "done", "failed"}:
                    app.state.registry.update_pipeline_run(
                        run_id,
                        event_type,
                        result=payload.get("result"),
                        error_message=payload.get("message") if event_type == "failed" else None,
                    )
                return event

            def worker_indexing_only():
                emit_job("running", {"message": "Indexing started"})
                try:
                    app.state.registry.update_step(doc_id, "indexed", "running")
                    emit_job("progress", {
                        "step": "indexed",
                        "label": "Index Document",
                        "status": "running",
                        "percent": 88,
                        "message": "Index Document running",
                    })
                    
                    from src.services.index_service import index_document
                    res = index_document(doc_id, app.state.data_dir, app.state.index_adapter_factory)
                    if res.get("status") != "success":
                        raise RuntimeError(f"Indexing failed: {res.get('error') or res}")
                    
                    app.state.registry.update_step(doc_id, "indexed", "success")
                    emit_job("progress", {
                        "step": "indexed",
                        "label": "Index Document",
                        "status": "success",
                        "percent": 100,
                    })
                    emit_job("done", {"message": "Pipeline complete (indexing only)", "result": {"status": "success", "indexed": res.get("indexed", 0)}})
                except Exception as e:
                    app.state.registry.update_step(doc_id, "indexed", "failed", str(e))
                    emit_job("failed", {"message": str(e)})

            threading.Thread(target=worker_indexing_only, daemon=True).start()
            return {"job_id": job.job_id, "status": job.status}

        # Otherwise, run full pipeline
        job = app.state.jobs.create(doc_id)
        run_id = app.state.registry.create_pipeline_run(doc_id, job.job_id)
        for event in job.events:
            app.state.registry.add_pipeline_run_event(run_id, event)

        def emit_job(event_type: str, payload: dict[str, Any]):
            event = app.state.jobs.emit(job.job_id, event_type, payload)
            app.state.registry.add_pipeline_run_event(run_id, event)
            if event_type in {"running", "done", "failed"}:
                app.state.registry.update_pipeline_run(
                    run_id,
                    event_type,
                    result=payload.get("result"),
                    error_message=payload.get("message") if event_type == "failed" else None,
                )
            return event

        def worker():
            emit_job("running", {"message": "Pipeline started"})
            try:
                result = run_pipeline(
                    doc_id,
                    doc,
                    app.state.registry,
                    emit=lambda event: emit_job("progress", event),
                    data_dir=app.state.data_dir,
                    index_adapter_factory=app.state.index_adapter_factory,
                )
                emit_job("done", {"message": "Pipeline complete", "result": result})
            except Exception as e:
                emit_job("failed", {"message": str(e)})

        threading.Thread(target=worker, daemon=True).start()
        return {"job_id": job.job_id, "status": job.status}

    @app.get("/api/documents/{doc_id}/pipeline/runs")
    def get_pipeline_runs(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        return {"runs": app.state.registry.get_pipeline_runs(doc_id)}

    @app.post("/api/compare/detect-mode")
    def detect_document_compare_mode(request: CompareModeRequest):
        if request.source_doc_id == request.target_doc_id:
            raise HTTPException(status_code=400, detail="Compare requires two different documents")
        source_doc = app.state.registry.get_document(request.source_doc_id)
        target_doc = app.state.registry.get_document(request.target_doc_id)
        if not source_doc or not target_doc:
            raise HTTPException(status_code=404, detail="Both documents must exist")
        return detect_compare_mode(source_doc, target_doc, app.state.data_dir)

    @app.post("/api/compare/run")
    def run_document_compare(request: CompareRunRequest):
        try:
            return run_compare(
                source_doc_id=request.source_doc_id,
                target_doc_id=request.target_doc_id,
                mode=request.mode,
                registry=app.state.registry,
                data_dir=app.state.data_dir,
            )
        except CompareError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/compare/{run_id}")
    def get_document_compare_run(run_id: str):
        result = app.state.registry.get_compare_run(run_id)
        if not result:
            raise HTTPException(status_code=404, detail="Compare run not found")
        return result

    @app.get("/api/documents/{doc_id}/compare/runs")
    def get_document_compare_runs(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        return {"runs": app.state.registry.get_compare_runs_for_doc(doc_id)}

    @app.get("/api/jobs/{job_id}/events")
    def stream_job_events(job_id: str):
        if not app.state.jobs.get(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return StreamingResponse(
            app.state.jobs.stream(job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/documents/{doc_id}/artifacts/{artifact_type}")
    def get_artifact(doc_id: str, artifact_type: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        artifact = read_artifact(doc_id, artifact_type, app.state.data_dir)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    @app.get("/api/documents/{doc_id}/artifacts/{artifact_type}/{filename}")
    def get_artifact_file(doc_id: str, artifact_type: str, filename: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        safe_name = Path(filename).name
        if artifact_type not in {"tables", "figures"}:
            raise HTTPException(status_code=404, detail="Artifact not found")
        path = app.state.data_dir / artifact_type / doc_id / safe_name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(path)

    @app.get("/api/documents/{doc_id}/pages/{page_num}/image")
    def get_page_image(doc_id: str, page_num: int):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        path = page_image_path(doc_id, page_num, app.state.data_dir)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page image not found")
        return FileResponse(path)

    @app.get("/api/documents/{doc_id}/pages/{page_num}/matches")
    def get_page_matches(doc_id: str, page_num: int, query: str = ""):
        doc = app.state.registry.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return page_image_matches(doc, page_num, query, app.state.data_dir)

    @app.post("/api/documents/{doc_id}/index")
    def index_doc(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        result = index_document(doc_id, app.state.data_dir, app.state.index_adapter_factory)
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result)
        app.state.registry.update_step(doc_id, "indexed", "success")
        return result

    @app.get("/api/documents/{doc_id}/index/status")
    def index_status(doc_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        return get_index_status(
            doc_id,
            app.state.data_dir,
            app.state.registry,
            app.state.index_adapter_factory,
        )

    @app.get("/api/documents/{doc_id}/graph")
    def get_entity_graph(
        doc_id: str,
        entity_type: str | None = None,
        min_edge_weight: int = 1,
    ):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        from src.mcp.schemas import GetEntityGraphInput
        from src.mcp import tools as mcp_tools
        params = GetEntityGraphInput(
            doc_id=doc_id,
            entity_type=entity_type,
            min_edge_weight=min_edge_weight,
        )
        result = mcp_tools.get_entity_graph(params)
        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.get("/api/documents/{doc_id}/graph/relationships")
    def get_entity_relationships(
        doc_id: str,
        entity_type: str,
        entity_value: str,
        max_hops: int = 1,
    ):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        from src.mcp.schemas import GetEntityRelationshipsInput
        from src.mcp import tools as mcp_tools
        params = GetEntityRelationshipsInput(
            doc_id=doc_id,
            entity_type=entity_type,
            entity_value=entity_value,
            max_hops=max_hops,
        )
        result = mcp_tools.get_entity_relationships(params)
        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/api/search")
    def search(request: SearchRequest):
        doc_ids = [request.doc_id] if isinstance(request.doc_id, str) else request.doc_id
        if not doc_ids:
            raise HTTPException(status_code=400, detail="At least one doc_id must be provided")
        for d_id in doc_ids:
            if not app.state.registry.get_document(d_id):
                raise HTTPException(status_code=404, detail=f"Document {d_id} not found")
        results = search_document(
            doc_id=request.doc_id,
            query=request.query,
            top_k=request.top_k,
            index_adapter_factory=app.state.index_adapter_factory,
            registry=app.state.registry,
            hybrid=request.hybrid,
            rerank=request.rerank,
            dense_weight=request.dense_weight,
            sparse_weight=request.sparse_weight,
            search_mode=request.search_mode,
        )
        return {"results": results}

    @app.get("/api/documents/{doc_id}/pages/{page_num}/evidence")
    def get_page_evidence(doc_id: str, page_num: int):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        from src.indexing.page_evidence import PageImageEvidence
        evidence = PageImageEvidence(doc_id)
        return evidence.get_page_evidence(page_num)

    @app.get("/api/documents/{doc_id}/figures/{figure_id}/evidence")
    def get_figure_evidence(doc_id: str, figure_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        from src.indexing.page_evidence import PageImageEvidence
        evidence = PageImageEvidence(doc_id)
        result = evidence.get_figure_evidence(figure_id)
        if not result:
            raise HTTPException(status_code=404, detail="Figure not found")
        return result

    @app.get("/api/documents/{doc_id}/figures/{figure_id}/image")
    def get_figure_image(doc_id: str, figure_id: str):
        if not app.state.registry.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        figures_dir = app.state.data_dir / "figures" / doc_id
        img_path = figures_dir / f"{figure_id}.png"
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="Figure image not found")
        return FileResponse(img_path)

    # ── Auto-Update Endpoints ────────────────────────────────────

    @app.get("/api/version-check")
    def version_check():
        import urllib.request
        local_version = _read_local_version()
        # Check GitHub for latest VERSION file on main branch
        repo = _get_github_repo()
        if not repo:
            return {"update_available": False, "local_version": local_version, "remote_version": local_version}
        url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiraDocs"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                remote_version = resp.read().decode().strip()
        except Exception:
            return {"update_available": False, "local_version": local_version, "remote_version": local_version}
        update_available = remote_version != local_version
        return {"update_available": update_available, "local_version": local_version, "remote_version": remote_version}

    @app.post("/api/update")
    def trigger_update():
        import subprocess
        root = Path(__file__).resolve().parent.parent.parent
        script = root / "update.sh"
        if not script.exists():
            raise HTTPException(status_code=500, detail="update.sh not found")
        # Spawn detached process — update.sh writes its own log to data/update.log
        (root / "data").mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            ["bash", str(script)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(root),
        )
        return {"status": "updating", "message": "Update started. App will restart shortly."}

    @app.get("/api/update-status")
    def update_status():
        root = Path(__file__).resolve().parent.parent.parent
        status_file = root / "data" / "update-status.json"
        if not status_file.exists():
            return {"status": "idle", "version": _read_local_version()}
        try:
            return json.loads(status_file.read_text())
        except Exception:
            return {"status": "idle", "version": _read_local_version()}

    return app


def _read_local_version() -> str:
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    try:
        return version_file.read_text().strip()
    except FileNotFoundError:
        return "0.0.0"


def _get_github_repo() -> str | None:
    """Extract GitHub owner/repo from git remote origin URL."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        url = result.stdout.strip()
        # Handle: https://github.com/owner/repo.git or git@github.com:owner/repo.git
        if "github.com" not in url:
            return None
        if url.startswith("git@"):
            repo = url.split(":")[-1]
        else:
            repo = "/".join(url.split("github.com/")[-1:])
        return repo.removesuffix(".git")
    except Exception:
        return None


app = create_app()
