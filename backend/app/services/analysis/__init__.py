"""LLM provider factory."""
from __future__ import annotations

from ...config import get_settings
from .base import LLMProvider  # noqa: F401
from .gemini import GeminiLLMProvider
from .mock import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        return GeminiLLMProvider()
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")
