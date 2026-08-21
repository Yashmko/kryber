"""AI clip discovery engine (§15–17).

Transcript → prompt → LLM (JSON only) → validate → dedupe → select 3–10.
"""
from __future__ import annotations

import json

from ...config import get_settings
from ...errors import AnalysisFailedError
from ...utils import logging as logmod
from ..transcription.base import Transcript
from .base import LLMProvider
from .validation import ClipCandidate, dedupe_overlaps, parse_candidates, select_top, validate_candidate

logger = logmod.get_logger("kryber.analysis.clip_engine")

CLIP_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "rank": {"type": "integer"},
        "start": {"type": "number", "description": "Clip start time in seconds."},
        "end": {"type": "number", "description": "Clip end time in seconds."},
        "score": {"type": "integer", "description": "0-100 overall strength."},
        "reason": {"type": "string"},
        "hook": {"type": "string", "description": "Short hook grounded in the transcript."},
        "caption_title": {"type": "string"},
    },
    "required": ["rank", "start", "end", "score", "reason", "hook", "caption_title"],
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"clips": {"type": "array", "items": CLIP_ITEM_SCHEMA}},
    "required": ["clips"],
}

SYSTEM_PROMPT = """You are an expert short-form video editor. You select the strongest, \
self-contained moments from a long video transcript and turn them into vertical Shorts.

For each candidate moment, evaluate:
- hook strength (does it grab attention in the first seconds?)
- curiosity (does it make the viewer want to keep watching?)
- emotional intensity
- surprise
- information density
- payoff (does it deliver by the end?)
- context (is it understandable on its own?)
- retention (will people watch to the end?)
- editability (clean start/end points, no mid-sentence cuts)

Prioritize: surprising claims, strong opinions, useful insights, stories, emotional \
moments, controversial ideas, mistakes, lessons, unexpected facts, predictions, \
punchlines, transformations, arguments, actionable advice.

Avoid: greetings, introductions, sponsor reads, repetitive explanations, filler, weak \
conclusions, and moments that need extensive missing context.

Each clip MUST be 20–60 seconds and use timestamps that exist in the transcript.
The hook MUST be grounded in what the speaker actually said — never invent facts,
numbers, or claims that are not in the transcript.

Return JSON only, following the exact schema, with approximately 10 candidates.
IMPORTANT: the candidates MUST NOT overlap each other — pick distinct, non-overlapping
moments spread across the video so the final set covers different ideas."""


def build_user_prompt(transcript: Transcript, video_duration: float, target_duration: float = 60.0) -> str:
    segments = [s.to_dict(include_words=False) for s in transcript.segments]
    payload = {
        "video_duration_seconds": round(video_duration, 2),
        "transcript_segments": segments,
    }
    return (
        "Here is a timestamped transcript. Identify the strongest self-contained "
        "short-form moments.\n\n"
        "Requirements:\n"
        f"- target clip length: about {target_duration:.0f} seconds each "
        f"(allowed range: 20 to {target_duration:.0f} seconds)\n"
        "- start and end must match real segment timestamps\n"
        "- approximately 10 candidates, ranked best-first\n"
        "- candidates MUST NOT overlap each other (distinct, non-overlapping moments)\n"
        "- each clip needs: rank, start, end, score (0-100), reason, hook, caption_title\n"
        "- the hook must be a short, punchy sentence grounded ONLY in the transcript\n\n"
        "Transcript JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def discover_clips(
    provider: LLMProvider,
    transcript: Transcript,
    video_duration: float,
    max_duration: float | None = None,
) -> list[ClipCandidate]:
    """Run the LLM and return validated, de-duplicated, selected candidates."""
    settings = get_settings()

    target_duration = float(max_duration or settings.clip_max_duration)

    raw = provider.complete_json(
        SYSTEM_PROMPT,
        build_user_prompt(transcript, video_duration, target_duration=target_duration),
        RESPONSE_SCHEMA,
    )
    candidates = parse_candidates(raw)

    if not candidates:
        raise AnalysisFailedError("The LLM returned no valid clip candidates.")

    valid = [
        c for c in candidates
        if validate_candidate(c, video_duration, settings.clip_min_duration, target_duration)
    ]

    rejected = len(candidates) - len(valid)
    if rejected:
        logmod.warning(
            logger,
            "rejected malformed LLM clips",
            stage="analyzing",
            rejected=rejected,
            kept=len(valid),
        )

    if not valid:
        raise AnalysisFailedError(
            f"All {len(candidates)} LLM candidates failed validation (clips must be "
            f"{settings.clip_min_duration:.0f}–{target_duration:.0f}s within a "
            f"{video_duration:.1f}s video)."
        )

    deduped = dedupe_overlaps(valid)
    target = min(max(3, settings.clip_target_count), 10)
    selected = select_top(deduped, target)

    logmod.info(
        logger,
        "clips selected",
        stage="analyzing",
        candidates=len(candidates),
        valid=len(valid),
        deduped=len(deduped),
        selected=len(selected),
        target_duration=target_duration,
    )
    return selected
