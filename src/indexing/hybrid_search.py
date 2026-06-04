"""Hybrid search engine: dense (BGE-M3) + sparse (BM25) + fusion + reranking."""
import math
import re
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from src.config import get_config
from src.indexing.chunk_keyword_search import keyword_search_chunks
from src.indexing.qdrant_adapter import QdrantAdapter

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    """Combines dense vector search with BM25 sparse scoring and optional reranking."""

    def __init__(self):
        self.qdrant = QdrantAdapter()
        self.reranker: Reranker | None = None
        cfg = get_config()
        self._ollama_url = cfg["embedding"]["ollama_url"]
        search_cfg = cfg.get("search", {})
        self._rerank_model = search_cfg["rerank_model"]
        self._use_reranker = search_cfg.get("rerank_enabled", False)
        self._rrf_k = search_cfg.get("rrf_k", 60)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        rerank: bool | None = None,
        rerank_top_k: int = 5,
    ) -> list[dict]:
        """Hybrid search with RRF fusion and optional reranking.

        1. Dense search via Qdrant (BGE-M3 embeddings)
        2. Sparse search via BM25 scoring on stored text
        3. Reciprocal Rank Fusion to combine
        4. Optional reranking of top results
        """
        # Step 1: Dense retrieval
        dense_results = self.qdrant.search(query, top_k=top_k * 2, filters=filters)

        # Step 2: Sparse candidates from chunks cache, plus BM25 over all candidates
        keyword_results = self._keyword_search_candidates(query, top_k * 2, filters)
        all_candidates = _dedupe_results(dense_results + keyword_results)
        scored = self._bm25_rescore(query, all_candidates)

        # Step 3: RRF fusion
        fused = self._rrf_fusion(
            dense_results,
            scored,
            keyword_results,
            dense_weight,
            sparse_weight,
            keyword_weight=sparse_weight,
            k=self._rrf_k,
        )

        # Take top_k before reranking
        candidates = fused[:top_k * 2]

        # Step 4: Reranking
        should_rerank = rerank if rerank is not None else self._use_reranker
        if should_rerank and candidates:
            candidates = self._rerank(query, candidates, rerank_top_k)

        return candidates[:rerank_top_k if should_rerank else top_k]

    def _bm25_rescore(self, query: str, results: list[dict]) -> list[dict]:
        """Score results using BM25 against query terms."""
        query_terms = _tokenize(query)
        if not query_terms or not results:
            return results

        # Compute IDF across result set
        doc_count = len(results)
        df = Counter()
        doc_term_freqs = []
        doc_lengths = []

        for r in results:
            text = r.get("text", "")
            tokens = _tokenize(text)
            doc_lengths.append(len(tokens))
            tf = Counter(tokens)
            doc_term_freqs.append(tf)
            for term in set(tokens):
                df[term] += 1

        avg_dl = sum(doc_lengths) / max(len(doc_lengths), 1)
        k1, b = 1.5, 0.75

        scored = []
        for i, r in enumerate(results):
            score = 0.0
            dl = doc_lengths[i]
            tf = doc_term_freqs[i]
            for term in query_terms:
                n = df.get(term, 0)
                idf = math.log((doc_count - n + 0.5) / (n + 0.5) + 1)
                term_freq = tf.get(term, 0)
                numerator = term_freq * (k1 + 1)
                denominator = term_freq + k1 * (1 - b + b * dl / avg_dl)
                score += idf * (numerator / denominator)
            scored.append({**r, "bm25_score": score})

        scored.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored

    def _rrf_fusion(
        self,
        dense_results: list[dict],
        sparse_results: list[dict],
        keyword_results: list[dict],
        dense_weight: float,
        sparse_weight: float,
        keyword_weight: float = 0.3,
        k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion combining dense, BM25, and keyword rankings."""
        scores: dict[str, float] = {}
        result_map: dict[str, dict] = {}

        for rank, r in enumerate(dense_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + dense_weight / (k + rank + 1)
            result_map[cid] = r

        for rank, r in enumerate(sparse_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + sparse_weight / (k + rank + 1)
            result_map[cid] = {**result_map.get(cid, {}), **r}

        for rank, r in enumerate(keyword_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + keyword_weight / (k + rank + 1)
            result_map[cid] = {**result_map.get(cid, {}), **r}

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [{**result_map[cid], "hybrid_score": score} for cid, score in ranked]

    def _rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """Rerank candidates using Ollama LLM scoring."""
        try:
            reranked = rerank_with_ollama(
                query, candidates, self._ollama_url, self._rerank_model, top_k
            )
            return reranked
        except Exception as e:
            logger.warning(f"Reranking failed, returning fusion order: {e}")
            return candidates[:top_k]

    def _keyword_search_candidates(self, query: str, top_k: int, filters: dict | None) -> list[dict]:
        """Keyword candidates from chunks cache — fills gaps dense might miss."""
        doc_id = (filters or {}).get("doc_id")
        return keyword_search_chunks(query, top_k, doc_ids=doc_id)


# ─── Reranking ────────────────────────────────────────────────────────────────

def rerank_with_ollama(
    query: str,
    candidates: list[dict],
    ollama_url: str,
    model: str,
    top_k: int,
) -> list[dict]:
    """Rerank using Ollama LLM, scoring all candidates in parallel."""
    import httpx

    pool = candidates[:top_k * 2]

    def score_one(candidate: dict) -> dict:
        text = candidate.get("text", "")[:500]
        prompt = (
            f"Rate the relevance of this passage to the query on a scale of 0-10.\n"
            f"Query: {query}\n"
            f"Passage: {text}\n"
            f"Score (number only):"
        )
        try:
            resp = httpx.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=15.0,
            )
            if resp.status_code == 200:
                answer = resp.json().get("response", "0").strip()
                match = re.search(r"(\d+(?:\.\d+)?)", answer)
                score = float(match.group(1)) if match else 0.0
                return {**candidate, "rerank_score": min(score, 10.0)}
        except Exception:
            pass
        return {**candidate, "rerank_score": 0.0}

    workers = min(len(pool), 5)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        scored = list(executor.map(score_one, pool))

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]


# ─── Utilities ────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _dedupe_results(results: list[dict]) -> list[dict]:
    """Remove duplicate chunks by chunk_id, preserving order."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in results:
        cid = r.get("chunk_id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(r)
        elif not cid:
            out.append(r)  # keep if missing id (should not happen)
    return out
