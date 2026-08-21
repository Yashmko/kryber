"""Clip candidate validation + de-duplication (§17, §7).

Never trust the LLM: every returned clip is re-checked against real bounds,
malformed candidates are dropped, and overlapping duplicates are removed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClipCandidate:
    rank: int
    start: float
    end: float
    score: float
    reason: str
    hook: str
    caption_title: str


def parse_candidates(raw: dict | None) -> list[ClipCandidate]:
    """Coerce LLM JSON into candidate objects; drop unparseable entries."""
    if not isinstance(raw, dict):
        return []
    items = raw.get("clips")
    if not isinstance(items, list):
        return []
    out: list[ClipCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start"])
            end = float(item["end"])
            score = float(item.get("score", 0))
        except (KeyError, TypeError, ValueError):
            continue
        out.append(
            ClipCandidate(
                rank=int(item.get("rank", len(out) + 1) or len(out) + 1),
                start=start,
                end=end,
                score=score,
                reason=str(item.get("reason", "")).strip(),
                hook=str(item.get("hook", "")).strip(),
                caption_title=str(item.get("caption_title", "")).strip(),
            )
        )
    return out


def validate_candidate(c: ClipCandidate, video_duration: float, min_dur: float, max_dur: float) -> bool:
    """Enforce start>=0, end>start, end<=duration, min<=dur<=max."""
    if c.start < 0:
        return False
    if c.end <= c.start:
        return False
    if video_duration > 0 and c.end > video_duration + 1e-6:
        return False
    dur = c.end - c.start
    if dur < min_dur - 1e-6:
        return False
    if dur > max_dur + 1e-6:
        return False
    return True


def overlaps(a: ClipCandidate, b: ClipCandidate) -> bool:
    return a.start < b.end and b.start < a.end


def dedupe_overlaps(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    """Keep the highest-scoring clip from any mutually-overlapping set."""
    kept: list[ClipCandidate] = []
    for c in sorted(candidates, key=lambda x: -x.score):
        if not any(overlaps(c, k) for k in kept):
            kept.append(c)
    return kept


def select_top(candidates: list[ClipCandidate], target: int) -> list[ClipCandidate]:
    """Return at most ``target`` clips, ranked by score descending."""
    ranked = sorted(candidates, key=lambda x: -x.score)
    for i, c in enumerate(ranked):
        c.rank = i + 1
    return ranked[:target]
