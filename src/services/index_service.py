"""Indexing and search operations for the API layer."""
import json
from pathlib import Path
from typing import Any, Callable

from src.intake.document_registry import DocumentRegistry


def index_document(doc_id: str, data_dir: Path, index_adapter_factory: Callable[[], Any]) -> dict:
    chunks_path = data_dir / "parsed" / doc_id / "chunks.json"
    if not chunks_path.exists():
        return {"status": "missing_chunks", "indexed": 0}
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    result = index_adapter_factory().index_chunks(chunks, doc_id)
    status_path = data_dir / "parsed" / doc_id / "index_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def get_index_status(
    doc_id: str,
    data_dir: Path,
    registry: DocumentRegistry,
    index_adapter_factory: Callable[[], Any],
) -> dict:
    chunks_path = data_dir / "parsed" / doc_id / "chunks.json"
    chunks_count = 0
    if chunks_path.exists():
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks_count = len(chunks)

    steps = registry.get_pipeline_status(doc_id)
    step = next((s for s in steps if s["step_name"] == "indexed"), None)
    last_result_path = data_dir / "parsed" / doc_id / "index_status.json"
    last_result = json.loads(last_result_path.read_text(encoding="utf-8")) if last_result_path.exists() else None

    try:
        adapter_status = index_adapter_factory().get_status()
    except Exception as e:
        adapter_status = {"status": "error", "error": str(e)}

    indexed = step and step.get("status") == "success"
    reindex_recommended = bool(indexed and last_result and last_result.get("indexed") != chunks_count)
    return {
        "doc_id": doc_id,
        "chunks_available": chunks_path.exists(),
        "chunks_count": chunks_count,
        "index_step": step,
        "indexed": bool(indexed),
        "last_indexed_at": step.get("completed_at") if step else None,
        "last_index_result": last_result,
        "adapter": adapter_status,
        "reindex_recommended": reindex_recommended,
    }


def search_document(
    *,
    doc_id: str | list[str],
    query: str,
    top_k: int,
    index_adapter_factory: Callable[[], Any],
    hybrid: bool = True,
    rerank: bool = False,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
) -> list[dict]:
    """Search with optional hybrid (dense+BM25) and reranking, enriched with page evidence."""
    if hybrid:
        from src.indexing.hybrid_search import HybridSearchEngine
        engine = HybridSearchEngine()
        results = engine.search(
            query=query,
            top_k=top_k,
            filters={"doc_id": doc_id},
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            rerank=rerank,
            rerank_top_k=top_k,
        )
    else:
        results = index_adapter_factory().search(
            query, top_k=top_k, filters={"doc_id": doc_id}
        )

    # Enrich with source file name from registry
    try:
        from src.intake.document_registry import DocumentRegistry
        registry = DocumentRegistry()
        for r in results:
            r_doc_id = r.get("doc_id")
            if r_doc_id:
                doc = registry.get_document(r_doc_id)
                if doc:
                    r["source_file"] = doc.get("filename", "")
                    r["document_type"] = doc.get("document_type", "")
                    r["domain"] = doc.get("domain", "")
    except Exception:
        pass

    # Enrich with page evidence
    from src.indexing.page_evidence import PageImageEvidence
    evidence_layer = PageImageEvidence(doc_id)
    return evidence_layer.enrich_results(results)
