"""Abstract index adapter interface."""
from abc import ABC, abstractmethod
from typing import Any


class IndexAdapter(ABC):
    @abstractmethod
    def index_chunks(self, chunks: list[dict], doc_id: str) -> dict:
        """Index chunks into vector store. Returns status dict."""
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        """Search indexed chunks. Returns list of results with scores."""
        ...

    @abstractmethod
    def get_status(self) -> dict:
        """Get index status (collection info, count, etc.)."""
        ...

    @abstractmethod
    def delete_doc(self, doc_id: str) -> bool:
        """Delete all chunks for a document."""
        ...
