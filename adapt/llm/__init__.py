"""Factory for the active LLM backend.

Defaults to the offline mock backend so the CLI works with zero setup. Set
OPENROUTER_API_KEY (and optionally ADAPT_MODEL) to route through OpenRouter, or
ANTHROPIC_API_KEY to call Claude directly — without touching any agent code.
OpenRouter is checked first since it's the backend currently configured for this
project.
"""

from __future__ import annotations

import os

from adapt.llm.base import LLMClient
from adapt.llm.mock_client import MockLLMClient

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is not None:
        return _client

    if os.environ.get("OPENROUTER_API_KEY"):
        from adapt.llm.openrouter_client import OpenRouterClient

        _client = OpenRouterClient()
        return _client

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from adapt.llm.anthropic_client import AnthropicClient

            _client = AnthropicClient()
            return _client
        except RuntimeError:
            pass  # anthropic package missing; fall back to mock

    _client = MockLLMClient()
    return _client


__all__ = ["LLMClient", "get_llm_client"]
