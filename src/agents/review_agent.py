# DEPENDENCIES: httpx, pydantic (already in project requirements)
"""Review Agent — wraps hybrid search with query decomposition, gap detection, and iterative refinement."""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

import httpx
from pydantic import BaseModel

from src.agents.llm_client import LLMClient

logger = logging.getLogger("review_agent")

# ─── Prompts ──────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM_PROMPT = """Classify the user query into exactly one category.

Categories:
- FACTUAL: single direct fact from a document (e.g., "What is the VPC CIDR?")
- COMPARATIVE: compares two components, services, or designs (e.g., "How does prod differ from non-prod networking?")
- SUMMARY: broad overview of a section or document (e.g., "Summarize the security controls")
- DIAGRAM: question about a visual, diagram, or topology (e.g., "What does the network topology show?")
- MULTI_PART: question containing 2+ independent sub-questions (e.g., "What is the auth flow and what DB is used?")

Reply with exactly one word from: FACTUAL, COMPARATIVE, SUMMARY, DIAGRAM, MULTI_PART
If uncertain, choose FACTUAL."""

_DECOMPOSE_SYSTEM_PROMPT = """Decompose the user's complex question into 2-4 focused, self-contained sub-questions.

Rules:
- Each sub-question must be independently answerable without context from other sub-questions
- No pronouns or references to other sub-questions
- Maximum 4 sub-questions regardless of complexity
- Return a JSON array of strings only, no other text

Example: ["What VPC CIDR is used in production?", "What routing strategy connects VPCs?"]"""

_DRAFT_SYSTEM_PROMPT = """You are an expert cloud architect answering questions from architecture documentation.

Rules:
- Answer ONLY using the provided context below
- Cite every claim using [doc_name, p.page_num] format
- If the context is insufficient to fully answer, write: INSUFFICIENT CONTEXT: {describe what is missing}
- Do not invent or extrapolate beyond the provided context"""

_GAP_SYSTEM_PROMPT = """Given the original question and a draft answer, identify what aspects are NOT answered or only partially answered.

Return a JSON array of short strings (max 10 words each) describing the missing aspects.
If the answer is fully complete, return an empty array [].
Maximum 4 items."""

_SYNTHESIS_SYSTEM_PROMPT = """You are an expert cloud architect producing a final, authoritative answer from architecture documentation.

Rules:
- Use ONLY the provided context
- Structure the answer clearly with headings if appropriate
- Cite sources inline as [doc_name, p.page_num]
- End with a "## Sources" section listing every source cited: one per line as "- doc_name, Section: section, Page page_num"
- Be precise and technical"""

_SYNTHESIS_COMPARATIVE_ADDENDUM = """
- Use a comparison format: describe each side, then highlight differences."""

_SYNTHESIS_SUMMARY_ADDENDUM = """
- Use a structured outline format with clear sections."""

_SYNTHESIS_DIAGRAM_ADDENDUM = """
- Start with a description of the topology or visual layout before details."""


class QueryType(Enum):
    FACTUAL = "FACTUAL"
    COMPARATIVE = "COMPARATIVE"
    SUMMARY = "SUMMARY"
    DIAGRAM = "DIAGRAM"
    MULTI_PART = "MULTI_PART"


@dataclass
class SubQuery:
    original_query: str
    sub_query_text: str
    index: int


@dataclass
class RetrievedContext:
    chunks: list[dict]
    sub_query: SubQuery
    retrieval_iteration: int


@dataclass
class DraftAnswer:
    text: str
    source_chunks: list[dict]
    is_complete: bool
    missing_aspects: list[str]


@dataclass
class Citation:
    doc_name: str
    section: str
    page_num: int
    excerpt: str


@dataclass
class ReviewAgentResponse:
    final_answer: str
    citations: list[Citation]
    confidence: float
    query_type: QueryType
    sub_queries_used: list[str]
    iterations: int
    warning: Optional[str] = None


@dataclass
class ReviewAgentConfig:
    top_k_retrieval: int = 20
    top_k_context_window: int = 8
    top_k_final_window: int = 10
    max_iterations: int = 2
    max_llm_calls: int = 12
    timeout_seconds: int = 60
    low_confidence_threshold: float = 0.4
    classifier_max_tokens: int = 50
    gap_detector_max_tokens: int = 200


class ReviewAgent:
    """Architecture review agent with iterative retrieval and gap detection."""

    def __init__(
        self,
        retriever: Any,
        llm_client: LLMClient,
        config: Optional[ReviewAgentConfig] = None,
        doc_id: Optional[str] = None,
    ):
        self._retriever = retriever
        self._llm_client = llm_client
        self._config = config or ReviewAgentConfig()
        self._doc_id = doc_id
        self._llm_call_count = 0

    async def run(self, query: str) -> ReviewAgentResponse:
        """Main entry point — orchestrates the full review agent loop."""
        try:
            return await asyncio.wait_for(
                self._run_inner(query),
                timeout=self._config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Review agent timed out for query: %s", query)
            return ReviewAgentResponse(
                final_answer="The review agent timed out before completing analysis.",
                citations=[],
                confidence=0.1,
                query_type=QueryType.FACTUAL,
                sub_queries_used=[query],
                iterations=0,
                warning="Timeout exceeded — answer may be incomplete.",
            )

    async def _run_inner(self, query: str) -> ReviewAgentResponse:
        self._llm_call_count = 0
        logger.info("STEP 1: Classifying query")
        query_type = await self._classify_query(query)
        logger.info("Query type: %s", query_type.value)

        logger.info("STEP 2: Decomposing query")
        sub_queries = await self._decompose_query(query, query_type)
        logger.info("Sub-queries: %d", len(sub_queries))

        logger.info("STEP 3: Retrieving for %d sub-queries", len(sub_queries))
        contexts = await self._retrieve_all(sub_queries, iteration=0)

        logger.info("STEP 4: Generating draft answer")
        draft = await self._generate_draft(query, contexts, query_type)

        logger.info("STEP 5: Detecting gaps")
        gaps = await self._detect_gaps(query, draft)

        iteration = 0
        while gaps and iteration < self._config.max_iterations:
            iteration += 1
            logger.info("STEP 6: Iteration %d — refining with %d gaps", iteration, len(gaps))
            new_contexts = await self._refine_with_gaps(query, gaps, iteration)
            contexts.extend(new_contexts)
            draft = await self._generate_draft(query, contexts, query_type)
            gaps = await self._detect_gaps(query, draft)

        logger.info("STEP 7: Synthesizing final answer")
        response = await self._synthesize(query, contexts, draft, iteration, query_type)

        response.sub_queries_used = [sq.sub_query_text for sq in sub_queries]

        logger.info("STEP 8: Complete — confidence=%.2f, iterations=%d", response.confidence, response.iterations)
        return response

    async def _classify_query(self, query: str) -> QueryType:
        response = await self._llm_call(
            system=_CLASSIFIER_SYSTEM_PROMPT,
            user=query,
            max_tokens=self._config.classifier_max_tokens,
            temperature=0,
        )
        text = response.strip().upper().replace('"', '').replace("'", "")
        try:
            return QueryType(text)
        except ValueError:
            logger.debug("Classification ambiguous (%s), defaulting to FACTUAL", text)
            return QueryType.FACTUAL

    async def _decompose_query(self, query: str, query_type: QueryType) -> list[SubQuery]:
        if query_type in (QueryType.FACTUAL, QueryType.DIAGRAM):
            return [SubQuery(original_query=query, sub_query_text=query, index=0)]

        response = await self._llm_call(
            system=_DECOMPOSE_SYSTEM_PROMPT,
            user=query,
            max_tokens=300,
            temperature=0,
        )
        try:
            items = self._parse_json_array(response)
            if not items:
                raise ValueError("Empty array")
            items = items[:4]
            return [
                SubQuery(original_query=query, sub_query_text=str(text).strip(), index=i)
                for i, text in enumerate(items)
                if isinstance(text, str) and text.strip()
            ]
        except Exception as e:
            logger.warning("Decomposition parse failed: %s", e)
            return [SubQuery(original_query=query, sub_query_text=query, index=0)]

    async def _retrieve_all(self, sub_queries: list[SubQuery], iteration: int) -> list[RetrievedContext]:
        async def _search_one(sq: SubQuery) -> RetrievedContext:
            try:
                results = self._retriever(
                    sq.sub_query_text,
                    top_k=self._config.top_k_retrieval,
                    filters={"doc_id": self._doc_id} if self._doc_id else None,
                )
                if asyncio.iscoroutine(results):
                    results = await results
                if results is None:
                    results = []
                return RetrievedContext(
                    chunks=results,
                    sub_query=sq,
                    retrieval_iteration=iteration,
                )
            except Exception as e:
                logger.error("Retrieval failed for sub-query '%s': %s", sq.sub_query_text, e)
                return RetrievedContext(
                    chunks=[],
                    sub_query=sq,
                    retrieval_iteration=iteration,
                )

        contexts = await asyncio.gather(*(_search_one(sq) for sq in sub_queries))
        return self._deduplicate_contexts(list(contexts))

    def _deduplicate_contexts(self, contexts: list[RetrievedContext]) -> list[RetrievedContext]:
        seen = {}
        for ctx in contexts:
            deduped = []
            for chunk in ctx.chunks:
                key = f"{chunk.get('doc_id', '')}-{chunk.get('page_start', '')}-{chunk.get('text', '')[:50]}"
                existing = seen.get(key)
                if existing is None or chunk.get("score", 0) > existing.get("score", 0):
                    seen[key] = chunk
                    deduped.append(chunk)
            ctx.chunks = deduped
        return contexts

    async def _generate_draft(
        self, query: str, contexts: list[RetrievedContext], query_type: QueryType
    ) -> DraftAnswer:
        all_chunks = []
        for ctx in contexts:
            all_chunks.extend(ctx.chunks)

        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
        top_chunks = all_chunks[: self._config.top_k_context_window]

        context_str = self._format_context(top_chunks)
        user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"

        response = await self._llm_call(
            system=_DRAFT_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=1500,
            temperature=0,
        )

        is_complete = "INSUFFICIENT CONTEXT" not in response
        missing = []
        if not is_complete:
            match = re.search(r"INSUFFICIENT CONTEXT:\s*(.+)", response, re.IGNORECASE)
            if match:
                missing = [m.strip() for m in match.group(1).split(",") if m.strip()]

        return DraftAnswer(
            text=response,
            source_chunks=top_chunks,
            is_complete=is_complete,
            missing_aspects=missing,
        )

    async def _detect_gaps(self, original_query: str, draft: DraftAnswer) -> list[str]:
        if draft.is_complete:
            return []

        user_prompt = f"Original question: {original_query}\n\nDraft answer:\n{draft.text}"
        response = await self._llm_call(
            system=_GAP_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=self._config.gap_detector_max_tokens,
            temperature=0,
        )
        try:
            gaps = self._parse_json_array(response)
            gaps = [g.strip() for g in gaps if isinstance(g, str) and g.strip()][:4]
            logger.warning("Gaps detected: %s", gaps)
            return gaps
        except Exception as e:
            logger.warning("Gap detection parse failed: %s", e)
            return []

    async def _refine_with_gaps(self, original_query: str, gaps: list[str], iteration: int) -> list[RetrievedContext]:
        if iteration >= self._config.max_iterations:
            logger.warning("Max iterations exceeded, skipping gap refinement")
            return []

        gap_sub_queries = []
        for i, gap in enumerate(gaps):
            sub_query_text = f"{original_query} — specifically: {gap}"
            gap_sub_queries.append(
                SubQuery(
                    original_query=original_query,
                    sub_query_text=sub_query_text,
                    index=i,
                )
            )
        return await self._retrieve_all(gap_sub_queries, iteration)

    async def _synthesize(
        self, query: str, all_contexts: list[RetrievedContext], draft: DraftAnswer, iterations: int, query_type: QueryType
    ) -> ReviewAgentResponse:
        all_chunks = []
        for ctx in all_contexts:
            all_chunks.extend(ctx.chunks)

        seen = {}
        for chunk in all_chunks:
            key = f"{chunk.get('doc_id', '')}-{chunk.get('page_start', '')}-{chunk.get('text', '')[:50]}"
            existing = seen.get(key)
            if existing is None or chunk.get("score", 0) > existing.get("score", 0):
                seen[key] = chunk

        sorted_chunks = sorted(seen.values(), key=lambda c: c.get("score", 0), reverse=True)
        top_chunks = sorted_chunks[: self._config.top_k_final_window]

        system = _SYNTHESIS_SYSTEM_PROMPT
        if query_type == QueryType.COMPARATIVE:
            system += _SYNTHESIS_COMPARATIVE_ADDENDUM
        elif query_type == QueryType.SUMMARY:
            system += _SYNTHESIS_SUMMARY_ADDENDUM
        elif query_type == QueryType.DIAGRAM:
            system += _SYNTHESIS_DIAGRAM_ADDENDUM

        context_str = self._format_context(top_chunks)
        user_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"

        response = await self._llm_call(
            system=system,
            user=user_prompt,
            max_tokens=2000,
            temperature=0,
        )

        citations = self._parse_citations(response)

        scores = [c.get("score", 0) for c in top_chunks[:5]]
        base_score = sum(scores) / max(len(scores), 1)
        normalized = min(base_score / 0.8, 1.0)

        confidence = normalized - 0.15 * iterations - (0.0 if draft.is_complete else 0.2)
        confidence = max(0.0, min(1.0, confidence))

        warning = None
        if confidence < self._config.low_confidence_threshold:
            warning = "Low confidence — answer may be incomplete or ambiguous. Verify against source documents."
            logger.warning("Low confidence %.2f for query: %s", confidence, query)

        return ReviewAgentResponse(
            final_answer=response,
            citations=citations,
            confidence=confidence,
            query_type=query_type,
            sub_queries_used=[],
            iterations=iterations,
            warning=warning,
        )

    def _format_context(self, chunks: list[dict]) -> str:
        parts = []
        for chunk in chunks:
            header = f"[Source: {chunk.get('doc_id', 'unknown')}, Section: {chunk.get('section_path', 'N/A')}, Page {chunk.get('page_start', '?')}]"
            parts.append(f"{header}\n{chunk.get('text', '')}\n---")
        return "\n".join(parts)

    def _parse_citations(self, text: str) -> list[Citation]:
        citations = []
        sources_match = re.search(r"##\s*Sources?\s*\n(.*)", text, re.DOTALL | re.IGNORECASE)
        if sources_match:
            lines = sources_match.group(1).strip().split("\n")
            for line in lines:
                line = line.strip().lstrip("- •").strip()
                m = re.match(r"(.+?),\s*Section:\s*(.+?),\s*Page\s*(\d+)", line)
                if m:
                    citations.append(
                        Citation(
                            doc_name=m.group(1).strip(),
                            section=m.group(2).strip(),
                            page_num=int(m.group(3)),
                            excerpt=line[:120],
                        )
                    )
                else:
                    m2 = re.match(r"\[?(.+?),\s*p\.?(\d+)\]?", line)
                    if m2:
                        citations.append(
                            Citation(
                                doc_name=m2.group(1).strip(),
                                section="",
                                page_num=int(m2.group(2)),
                                excerpt=line[:120],
                            )
                        )
        return citations

    def _parse_json_array(self, text: str) -> list:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("No JSON array found")
        return json.loads(text[start : end + 1])

    async def _llm_call(self, *, system: str, user: str, max_tokens: int = 500, temperature: float = 0) -> str:
        """Delegate to the injected LLMClient with call-count guard."""
        if self._llm_call_count >= self._config.max_llm_calls:
            logger.warning("Max LLM calls (%d) reached, returning empty", self._config.max_llm_calls)
            return ""

        self._llm_call_count += 1
        logger.debug("LLM call #%d: system=%s..., user=%s...", self._llm_call_count, system[:40], user[:40])

        result = await self._llm_client.chat(
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        logger.debug("LLM response: %s...", result[:100] if result else "")
        return result
