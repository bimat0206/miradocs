"""Provider-agnostic LLM client for the Review Agent."""
from abc import ABC, abstractmethod

_ANTHROPIC_KNOWN_MODELS = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, *, system: str, user: str, max_tokens: int = 500, temperature: float = 0) -> str:
        """Send a chat message and return the response text."""
        pass


class AnthropicLLMClient(LLMClient):
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None):
        import anthropic
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
            # Claude Code-compatible proxies use Bearer auth; standard API uses x-api-key.
            # Sending both and setting User-Agent lets this client work with either.
            kwargs["default_headers"] = {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "claude-code/0.2.9",
            }
        self._client = anthropic.AsyncAnthropic(**kwargs)
        self._model = model
        self._base_url = base_url

    async def chat(self, *, system: str, user: str, max_tokens: int = 500, temperature: float = 0) -> str:
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text


class OpenAILLMClient(LLMClient):
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None):
        import openai
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model

    async def chat(self, *, system: str, user: str, max_tokens: int = 500, temperature: float = 0) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


class GeminiLLMClient(LLMClient):
    def __init__(self, *, api_key: str, model: str):
        import google.genai as genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def chat(self, *, system: str, user: str, max_tokens: int = 500, temperature: float = 0) -> str:
        import google.genai.types as genai_types
        prompt = f"{system}\n\n{user}"
        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return resp.text or ""


_PROVIDER_CLASSES = {
    "anthropic": AnthropicLLMClient,
    "anthropic_compatible": AnthropicLLMClient,
    "openai": OpenAILLMClient,
    "openai_compatible": OpenAILLMClient,
    "gemini": GeminiLLMClient,
}


def make_llm_client(provider: str, *, api_key: str, model: str, base_url: str | None = None) -> LLMClient:
    """Factory: create a LLMClient for the given provider.

    provider values:
      anthropic            — Anthropic native SDK (Claude Code, Cline, Anthropic SDK apps)
      anthropic_compatible — Anthropic SDK with custom base_url (Claude proxies, LiteLLM, etc.)
      openai               — OpenAI native SDK (GPT-4o, etc.)
      openai_compatible    — OpenAI SDK with custom base_url (Ollama, local LLMs, LiteLLM, etc.)
      gemini               — Gemini SDK (Gemini 2.0, etc.)
    """
    if provider not in _PROVIDER_CLASSES:
        raise ValueError(f"Unknown provider: {provider}. Supported: {list(_PROVIDER_CLASSES.keys())}")
    if not model:
        raise ValueError("model is required. Select a model or click 'Load models' in the settings panel.")
    if provider in ("openai_compatible", "anthropic_compatible") and not base_url:
        raise ValueError(f"base_url is required for {provider} provider.")

    cls = _PROVIDER_CLASSES[provider]
    if provider in ("openai_compatible", "anthropic_compatible", "openai", "anthropic") and base_url:
        return cls(api_key=api_key, model=model, base_url=base_url)
    return cls(api_key=api_key, model=model)


async def list_models(provider: str, *, api_key: str, base_url: str | None = None) -> list[str]:
    """Fetch available model IDs from the provider's API.

    Falls back to a known list if the API fails or is not listable.
    """
    if provider in ("openai", "openai_compatible"):
        return await _list_openai_models(api_key=api_key, base_url=base_url)
    if provider == "anthropic":
        return list(_ANTHROPIC_KNOWN_MODELS)
    if provider == "anthropic_compatible":
        return await _list_anthropic_compatible_models(api_key=api_key, base_url=base_url)
    if provider == "gemini":
        return await _list_gemini_models(api_key=api_key)
    raise ValueError(f"Unknown provider: {provider}")


async def _list_openai_models(*, api_key: str, base_url: str | None) -> list[str]:
    from openai import AsyncOpenAI
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    models = await client.models.list()
    return sorted(m.id for m in models.data)


async def _list_anthropic_compatible_models(*, api_key: str, base_url: str | None) -> list[str]:
    """Try OpenAI-style /v1/models on the proxy; fall back to known Claude list."""
    import httpx
    if not base_url:
        return list(_ANTHROPIC_KNOWN_MODELS)
    try:
        base = base_url.rstrip("/")
        models_url = f"{base}/v1/models" if not base.endswith("/v1") else f"{base}/models"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                models_url,
                headers={
                    "x-api-key": api_key,
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "claude-code/0.2.9",
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            ids = [m.get("id", "") for m in data.get("data", data if isinstance(data, list) else [])]
            ids = [i for i in ids if i]
            if ids:
                return sorted(ids)
    except Exception:
        pass
    return list(_ANTHROPIC_KNOWN_MODELS)


async def _list_gemini_models(*, api_key: str) -> list[str]:
    import google.genai as genai
    client = genai.Client(api_key=api_key)
    names = []
    async for m in await client.aio.models.list():
        name = m.name.removeprefix("models/") if hasattr(m, "name") else str(m)
        if "gemini" in name.lower():
            names.append(name)
    return sorted(names)
