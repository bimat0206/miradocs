"""Tests for the Review Agent."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.review_agent import (
    Citation,
    DraftAnswer,
    QueryType,
    ReviewAgent,
    ReviewAgentConfig,
    ReviewAgentResponse,
    SubQuery,
)


def _mock_retriever(query, top_k, filters=None):
    """Mock retriever returning fake chunks."""
    return [
        {
            "chunk_id": f"chunk_{i}",
            "doc_id": "test_doc",
            "chunk_type": "child_text_chunk",
            "page_start": 1,
            "section_path": "4. Networking > 4.1 VPC Design",
            "text": f"The production VPC uses CIDR 10.0.0.0/16 with Transit Gateway. Chunk {i}.",
            "score": 0.85 - i * 0.05,
            "source_refs": [],
        }
        for i in range(min(top_k, 5))
    ]


def _make_agent(**kwargs):
    mock_client = MagicMock()
    retriever = kwargs.pop("retriever", _mock_retriever)
    llm_client = kwargs.pop("llm_client", mock_client)
    config = kwargs.pop("config", ReviewAgentConfig(timeout_seconds=10))
    return ReviewAgent(retriever=retriever, llm_client=llm_client, config=config, **kwargs)


@pytest.mark.asyncio
async def test_classify_factual_query():
    """Test that a factual query is classified correctly."""
    agent = _make_agent()
    with patch.object(agent, "_llm_call", return_value="FACTUAL"):
        result = await agent._classify_query("What is the VPC CIDR block for the prod environment?")
    assert result == QueryType.FACTUAL


@pytest.mark.asyncio
async def test_classify_fallback_on_ambiguous():
    """Test fallback to FACTUAL on ambiguous LLM response."""
    agent = _make_agent()
    with patch.object(agent, "_llm_call", return_value="I'm not sure, maybe something"):
        result = await agent._classify_query("Tell me about stuff")
    assert result == QueryType.FACTUAL


@pytest.mark.asyncio
async def test_decompose_multipart_query():
    """Test that a multi-part query produces 2+ sub-queries."""
    agent = _make_agent()
    with patch.object(
        agent,
        "_llm_call",
        return_value='["How does auth connect to the DB?", "What is the failover strategy?"]',
    ):
        result = await agent._decompose_query(
            "How does auth connect to the DB and what is the failover?", QueryType.MULTI_PART
        )
    assert len(result) >= 2
    assert all(isinstance(sq, SubQuery) for sq in result)
    assert all(sq.sub_query_text.strip() for sq in result)


@pytest.mark.asyncio
async def test_decompose_factual_no_split():
    """Test that FACTUAL queries are not decomposed."""
    agent = _make_agent()
    result = await agent._decompose_query("What is the VPC CIDR?", QueryType.FACTUAL)
    assert len(result) == 1
    assert result[0].sub_query_text == "What is the VPC CIDR?"


@pytest.mark.asyncio
async def test_gap_detector_complete_draft():
    """Test that gap detector returns [] for complete drafts without calling LLM."""
    agent = _make_agent()
    draft = DraftAnswer(text="The VPC CIDR is 10.0.0.0/16.", source_chunks=[], is_complete=True, missing_aspects=[])
    with patch.object(agent, "_llm_call") as mock_llm:
        result = await agent._detect_gaps("What is the VPC CIDR?", draft)
    assert result == []
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_max_iterations_enforced():
    """Test that the agent stops after max_iterations even with persistent gaps."""
    agent = _make_agent(config=ReviewAgentConfig(max_iterations=2, timeout_seconds=30))

    async def mock_llm(*args, **kwargs):
        system = kwargs.get("system", "")
        if "Classify" in system or "category" in system.lower():
            return "FACTUAL"
        if "Decompose" in system or "sub-question" in system.lower():
            return '["test query"]'
        if "gap" in system or "missing" in system.lower():
            return '["missing aspect 1"]'
        return "INSUFFICIENT CONTEXT: missing network details"

    with patch.object(agent, "_llm_call", side_effect=mock_llm):
        response = await agent.run("What is the network design?")
    assert response.iterations <= 2


@pytest.mark.asyncio
async def test_timeout_returns_partial_response():
    """Test that timeout produces a partial response with warning."""

    async def slow_retriever(*args, **kwargs):
        await asyncio.sleep(70)

    agent = _make_agent(retriever=slow_retriever, config=ReviewAgentConfig(timeout_seconds=0.1))
    with patch.object(agent, "_llm_call", return_value="FACTUAL"):
        response = await agent.run("test query")
    assert response.warning is not None
    assert "Timeout" in response.warning or "timeout" in response.warning.lower()
    assert response.confidence <= 0.1


@pytest.mark.asyncio
async def test_citation_parsing():
    """Test that citations are parsed from ## Sources section."""
    agent = _make_agent()
    synthesis_response = (
        "The VPC uses 10.0.0.0/16 [landing-zone-hld, p.32].\n\n"
        "## Sources\n"
        "- landing-zone-hld, Section: 4. Networking > 4.1 VPC, Page 32\n"
        "- security-design, Section: 3. Controls, Page 15"
    )

    async def mock_llm(*args, **kwargs):
        system = kwargs.get("system", "")
        if "Classify" in system or "category" in system.lower():
            return "FACTUAL"
        if "expert cloud architect" in system.lower() or "synthesis" in system.lower():
            return synthesis_response
        return "The VPC uses 10.0.0.0/16."

    with patch.object(agent, "_llm_call", side_effect=mock_llm):
        response = await agent.run("What is the VPC CIDR?")
    assert len(response.citations) >= 1
    assert response.citations[0].doc_name == "landing-zone-hld"
    assert response.citations[0].page_num == 32


@pytest.mark.asyncio
async def test_full_run_returns_valid_response():
    """Test that a full run returns a valid ReviewAgentResponse."""
    agent = _make_agent()

    async def mock_llm(*args, **kwargs):
        system = kwargs.get("system", "")
        if "Classify" in system or "category" in system.lower():
            return "FACTUAL"
        if "expert cloud architect" in system.lower() or "synthesis" in system.lower():
            return "The VPC uses 10.0.0.0/16.\n\n## Sources\n- test_doc, Section: Networking, Page 1"
        if "gap" in system or "missing" in system.lower():
            return "[]"
        return "The VPC CIDR is 10.0.0.0/16 [test_doc, p.1]."

    with patch.object(agent, "_llm_call", side_effect=mock_llm):
        response = await agent.run("What is the VPC CIDR for production?")
    assert isinstance(response, ReviewAgentResponse)
    assert response.final_answer
    assert response.confidence > 0.0
    assert response.query_type == QueryType.FACTUAL
    assert response.iterations >= 0
