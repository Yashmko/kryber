"""Deterministic mock LLM provider (tests + no-key local dev).

Returns valid, non-overlapping 20–60s clips derived from the transcript's real
duration, so the full pipeline can run end-to-end without calling Gemini.
"""
from __future__ import annotations

import re

from .base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock"

    def complete_json(self, system_prompt: str, user_prompt: str, response_schema: dict | None = None) -> dict:
        # Total duration of the video, as encoded in the prompt.
        m = re.search(r'"video_duration_seconds"\s*:\s*([0-9.]+)', user_prompt)
        total = float(m.group(1)) if m else 0.0
        if total < 20:
            return {"clips": []}

        clips = []
        window = 30.0
        i = 0
        while i * window < total and len(clips) < 5:
            start = i * window
            end = min(total, start + window)
            if end - start >= 20:
                clips.append(
                    {
                        "rank": len(clips) + 1,
                        "start": round(start, 2),
                        "end": round(end, 2),
                        "score": 95 - len(clips) * 4,
                        "reason": "Deterministic mock candidate (30s window).",
                        "hook": "I made one massive mistake.",
                        "caption_title": f"Kryber moment {len(clips) + 1}",
                    }
                )
            i += 1
        return {"clips": clips}
