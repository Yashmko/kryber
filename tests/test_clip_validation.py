"""Clip candidate validation + selection (§17)."""
from __future__ import annotations

from app.services.analysis.validation import (
    ClipCandidate,
    dedupe_overlaps,
    parse_candidates,
    select_top,
    validate_candidate,
)

MIN, MAX = 20.0, 60.0


def _c(start, end, score=90, **kw):
    return ClipCandidate(rank=1, start=start, end=end, score=score, reason="", hook="", caption_title="")


def test_parse_candidates_skips_malformed():
    raw = {"clips": [{"start": 1, "end": 30, "score": 90}, {"start": "x", "end": 40}, "junk", None]}
    out = parse_candidates(raw)
    assert len(out) == 1
    assert out[0].start == 1


def test_parse_candidates_empty_when_missing_clips():
    assert parse_candidates({}) == []
    assert parse_candidates({"clips": "nope"}) == []


def test_validate_candidate_bounds():
    assert validate_candidate(_c(0, 30), 100, MIN, MAX)
    assert not validate_candidate(_c(-1, 30), 100, MIN, MAX)          # start < 0
    assert not validate_candidate(_c(30, 30), 100, MIN, MAX)          # end == start
    assert not validate_candidate(_c(10, 90), 100, MIN, MAX)          # too long
    assert not validate_candidate(_c(0, 15), 100, MIN, MAX)           # too short
    assert not validate_candidate(_c(0, 30), 25, MIN, MAX)            # end > video duration
    assert validate_candidate(_c(0, 25), 25, MIN, MAX)                # end == duration ok


def test_dedupe_overlaps_keeps_highest_score():
    a = _c(0, 30, score=80)
    b = _c(25, 55, score=95)
    c = _c(60, 90, score=70)
    kept = dedupe_overlaps([a, b, c])
    assert len(kept) == 2
    assert b in kept and c in kept


def test_select_top_reranks_and_truncates():
    items = [_c(i * 10, i * 10 + 30, score=i) for i in range(8)]
    top = select_top(items, 3)
    assert [c.score for c in top] == [7, 6, 5]
    assert [c.rank for c in top] == [1, 2, 3]
