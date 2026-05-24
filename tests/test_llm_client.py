"""Tests for the LLM client abstraction."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.llm_client import (
    AnthropicLLMClient,
    GeminiLLMClient,
    LLMClient,
    OpenAILLMClient,
    make_llm_client,
)


def test_make_llm_client_anthropic_returns_correct_type():
    with patch("anthropic.AsyncAnthropic"):
        client = make_llm_client("anthropic", api_key="test-key", model="any-model")
    assert isinstance(client, AnthropicLLMClient)


def test_make_llm_client_openai_returns_correct_type():
    with patch("openai.AsyncOpenAI"):
        client = make_llm_client("openai", api_key="test-key", model="any-model")
    assert isinstance(client, OpenAILLMClient)


def test_make_llm_client_gemini_returns_correct_type():
    with patch("google.genai.Client"):
        client = make_llm_client("gemini", api_key="test-key", model="any-model")
    assert isinstance(client, GeminiLLMClient)


def test_make_llm_client_openai_compatible_returns_openai_type():
    with patch("openai.AsyncOpenAI"):
        client = make_llm_client("openai_compatible", api_key="test-key", model="llama3", base_url="http://localhost:11434/v1")
    assert isinstance(client, OpenAILLMClient)


def test_make_llm_client_openai_compatible_requires_base_url():
    with pytest.raises(ValueError, match="base_url"):
        make_llm_client("openai_compatible", api_key="key", model="llama3")


def test_make_llm_client_openai_compatible_requires_model():
    with pytest.raises(ValueError, match="model"):
        make_llm_client("openai_compatible", api_key="key", base_url="http://localhost:11434/v1", model="")


def test_make_llm_client_unknown_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        make_llm_client("unknown_provider", api_key="key", model="any-model")


def test_make_llm_client_requires_model():
    with pytest.raises(ValueError, match="model is required"):
        with patch("anthropic.AsyncAnthropic"):
            make_llm_client("anthropic", api_key="k", model="")
    with pytest.raises(ValueError, match="model is required"):
        with patch("openai.AsyncOpenAI"):
            make_llm_client("openai", api_key="k", model="")
    with pytest.raises(ValueError, match="model is required"):
        with patch("google.genai.Client"):
            make_llm_client("gemini", api_key="k", model="")


def test_make_llm_client_custom_model():
    with patch("anthropic.AsyncAnthropic") as mock_class:
        c = make_llm_client("anthropic", api_key="k", model="claude-opus-4-7")
    assert c._model == "claude-opus-4-7"


def test_make_llm_client_openai_compatible_uses_custom_base_url():
    captured = {}
    def fake_openai(**kwargs):
        captured.update(kwargs)
        return MagicMock()
    with patch("openai.AsyncOpenAI", side_effect=fake_openai):
        make_llm_client("openai_compatible", api_key="key", model="llama3", base_url="http://localhost:11434/v1")
    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["api_key"] == "key"


@pytest.mark.asyncio
async def test_anthropic_chat_returns_text():
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="VPC CIDR is 10.0.0.0/16")]
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        client = AnthropicLLMClient(api_key="test-key", model="claude-3-5-sonnet-20241022")

    result = await client.chat(system="You are an expert.", user="What is the VPC CIDR?")
    assert result == "VPC CIDR is 10.0.0.0/16"


@pytest.mark.asyncio
async def test_openai_chat_returns_text():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "The CIDR is 10.0.0.0/16"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        client = OpenAILLMClient(api_key="test-key", model="gpt-4o")

    result = await client.chat(system="You are an expert.", user="What is the VPC CIDR?")
    assert result == "The CIDR is 10.0.0.0/16"


@pytest.mark.asyncio
async def test_gemini_chat_returns_text():
    mock_genai_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "CIDR is 10.0.0.0/16"
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch("google.genai.Client", return_value=mock_genai_client):
        client = GeminiLLMClient(api_key="test-key", model="gemini-2.0-flash")

    result = await client.chat(system="You are an expert.", user="What is the VPC CIDR?")
    assert result == "CIDR is 10.0.0.0/16"


def test_anthropic_compatible_uses_custom_user_agent_and_headers():
    captured = {}
    def fake_anthropic(**kwargs):
        captured.update(kwargs)
        return MagicMock()
    with patch("anthropic.AsyncAnthropic", side_effect=fake_anthropic):
        make_llm_client("anthropic_compatible", api_key="key-foo", model="claude-3-5-sonnet", base_url="http://localhost:8080/v1")
    assert captured["base_url"] == "http://localhost:8080/v1"
    assert captured["api_key"] == "key-foo"
    assert captured["default_headers"]["Authorization"] == "Bearer key-foo"
    assert captured["default_headers"]["User-Agent"] == "claude-code/0.2.9"
