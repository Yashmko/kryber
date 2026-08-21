"""LLMProvider abstraction.

The clip engine asks for *JSON only* and re-validates everything it gets back
(§16–17: never trust the LLM).
"""
from __future__ import annotations

import abc


class LLMProvider(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Return a parsed JSON object, raising AnalysisFailedError on failure."""
