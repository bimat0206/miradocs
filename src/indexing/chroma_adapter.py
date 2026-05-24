"""Chroma adapter placeholder - implements IndexAdapter interface."""
import logging
from src.indexing.index_adapter import IndexAdapter

logger = logging.getLogger(__name__)


class ChromaAdapter(IndexAdapter):
    """Placeholder for Chroma vector store. Not implemented in MVP."""

    def index_chunks(self, chunks: list[dict], doc_id: str) -> dict:
        logger.warning("Chroma adapter not implemented yet. Use Qdrant.")
        return {"status": "not_implemented", "indexed": 0}

    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        return []

    def get_status(self) -> dict:
        return {"status": "not_implemented"}

    def delete_doc(self, doc_id: str) -> bool:
        return False
