"""Hook source-grounding (§18)."""
from __future__ import annotations

from app.services.hooks.generator import ensure_grounded, fallback_hook, is_grounded


def test_grounded_hook_passes():
    window = "I spent three years building the wrong product"
    assert is_grounded("I wasted three years building the wrong product", window)


def test_fabricated_number_fails():
    window = "I spent three years building the wrong product"
    assert not is_grounded("This mistake cost me $10 million", window)


def test_empty_hook_fails():
    assert not is_grounded("", "some transcript text")


def test_ensure_grounded_returns_original_when_valid():
    window = "I made one massive mistake when I started my company"
    assert ensure_grounded("I made one massive mistake", window) == "I made one massive mistake"


def test_ensure_grounded_substitutes_fallback():
    window = "the moment I talked to real customers everything changed"
    hook = "This mistake cost me $10 million"
    out = ensure_grounded(hook, window)
    assert out != hook
    assert out == "the moment I talked to real"


def test_fallback_hook_word_limit():
    assert fallback_hook("a b c d e f g h i j", max_words=4) == "a b c d"
