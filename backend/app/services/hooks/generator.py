"""Hook grounding (§18).

Hooks must be supported by the transcript. A deterministic source-grounding
check verifies the hook's content words appear in the clip's transcript
window (and any numbers appear verbatim). Hooks that fail are replaced with a
guaranteed-grounded fallback.
"""
from __future__ import annotations

import re

from ...utils import logging as logmod

logger = logmod.get_logger("kryber.hooks")

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "to", "in", "on",
    "for", "with", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "i", "you", "he", "she",
    "we", "they", "my", "your", "his", "her", "our", "their", "me", "him", "us", "them",
    "do", "does", "did", "have", "has", "had", "just", "very", "really", "about", "into",
    "out", "up", "down", "not", "no", "yes", "what", "when", "where", "why", "how",
}

_WORD_RE = re.compile(r"[a-z0-9$€£%']+")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?|[$€£]\d+(?:\.\d+)?")


def _content_tokens(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS]


def _numbers(text: str) -> list[str]:
    return [t.lower() for t in _NUMBER_RE.findall(text)]


def is_grounded(hook: str, window_text: str, *, min_ratio: float = 0.6) -> bool:
    """True if the hook is plausibly supported by ``window_text``."""
    hook = (hook or "").strip()
    window = (window_text or "").lower()
    if not hook:
        return False

    tokens = _content_tokens(hook)
    if not tokens:
        return False

    # Every number in the hook must appear verbatim in the transcript.
    for num in _numbers(hook):
        if num not in window:
            return False

    present = sum(1 for t in tokens if t in window)
    return (present / len(tokens)) >= min_ratio


def fallback_hook(window_text: str, max_words: int = 6) -> str:
    words = (window_text or "").split()
    return " ".join(words[:max_words]).strip()


def ensure_grounded(hook: str, window_text: str) -> str:
    """Return a hook that passes the grounding check, logging any substitution."""
    if is_grounded(hook, window_text):
        return hook
    fb = fallback_hook(window_text)
    logmod.warning(
        logger,
        "hook failed grounding check; using transcript-derived fallback",
        stage="analyzing",
        hook=hook[:80],
        fallback=fb[:80],
    )
    return fb
