"""Qdrant indexing adapter with Ollama BGE-M3 embeddings."""
import logging
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, PointStruct, VectorParams, Filter, FieldCondition, MatchValue, MatchAny

)

from src.config import get_config, get_data_dir
from src.indexing.index_adapter import IndexAdapter

logger = logging.getLogger(__name__)


class QdrantAdapter(IndexAdapter):
    def __init__(self):
        cfg = get_config()
        self.collection_name = cfg["indexing"]["collection_name"]
        self.dimensions = cfg["embedding"]["dimensions"]
        self.ollama_url = cfg["embedding"]["ollama_url"]
        self.embed_model = cfg["embedding"]["model"]

        qdrant_path = str(get_data_dir() / "indexes" / "qdrant")
        self.client = QdrantClient(path=qdrant_path)
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimensions, distance=Distance.COSINE
                ),
            )
            logger.info(f"Created collection: {self.collection_name}")

    def index_chunks(self, chunks: list[dict], doc_id: str) -> dict:
        """Embed and index chunks into Qdrant."""
        if not chunks:
            return {"status": "empty", "indexed": 0}

        # Batch embed
        texts = [c["text"][:8000] for c in chunks]  # BGE-M3 context limit
        embeddings = self._embed_batch(texts)

        if not embeddings:
            return {"status": "embedding_failed", "indexed": 0}

        # Upsert points
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            points.append(PointStruct(
                id=abs(hash(chunk["chunk_id"])) % (2**63),
                vector=vector,
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["doc_id"],
                    "chunk_type": chunk["chunk_type"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "section_path": chunk["section_path"],
                    "text": chunk["text"][:2000],  # Store truncated for display
                    "entities": chunk.get("entities", {}),
                    "source_refs": chunk.get("source_refs", {}),
                },
            ))

        # Batch upsert (100 at a time)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=self.collection_name,
                points=points[i:i + batch_size],
            )

        logger.info(f"Indexed {len(points)} chunks for {doc_id}")
        return {"status": "success", "indexed": len(points)}

    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        """Search using query embedding."""
        query_vector = self._embed_single(query)
        if not query_vector:
            return []

        # Build filter
        qdrant_filter = None
        if filters:
            conditions = []
            if "doc_id" in filters:
                doc_val = filters["doc_id"]
                if isinstance(doc_val, list):
                    conditions.append(FieldCondition(key="doc_id", match=MatchAny(any=doc_val)))
                else:
                    conditions.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_val)))
            if "chunk_type" in filters:
                conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=filters["chunk_type"])))
            if conditions:
                qdrant_filter = Filter(must=conditions)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )

        return [
            {
                "score": r.score,
                "chunk_id": r.payload.get("chunk_id"),
                "doc_id": r.payload.get("doc_id"),
                "chunk_type": r.payload.get("chunk_type"),
                "page_start": r.payload.get("page_start"),
                "section_path": r.payload.get("section_path"),
                "text": r.payload.get("text"),
                "source_refs": r.payload.get("source_refs", {}),
            }
            for r in results.points
        ]

    def get_status(self) -> dict:
        """Get collection info."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "collection": self.collection_name,
                "vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def delete_doc(self, doc_id: str) -> bool:
        """Delete all points for a document."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False

    def _embed_single(self, text: str) -> list[float] | None:
        result = self._embed_batch([text])
        return result[0] if result else None

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings from Ollama."""
        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/embed",
                json={"model": self.embed_model, "input": texts},
                timeout=120.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("embeddings", [])
            logger.error(f"Ollama embed failed: {resp.status_code}")
            return []
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return []
