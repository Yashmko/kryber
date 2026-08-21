"""Transcript normalization (§13–14)."""
from __future__ import annotations

from app.services.transcription.base import Segment, Transcript, Word
from app.services.transcription.normalize import clean_transcript, normalize_assemblyai


def _utt(start_ms, end_ms, text):
    return {"start": start_ms, "end": end_ms, "text": text}


def test_normalize_assemblyai_with_utterances():
    result = {
        "words": [
            {"text": "hello", "start": 100, "end": 500},
            {"text": "world", "start": 500, "end": 900},
            {"text": "again", "start": 2000, "end": 2500},
        ],
        "utterances": [
            _utt(100, 900, "hello world"),
            _utt(2000, 2500, "again"),
        ],
    }
    t = normalize_assemblyai(result)
    assert len(t.segments) == 2
    assert t.segments[0].start == 0.1
    assert t.segments[0].end == 0.9
    assert t.segments[0].text == "hello world"
    assert len(t.segments[0].words) == 2


def test_normalize_assemblyai_falls_back_to_words():
    result = {
        "words": [
            {"text": "one", "start": 0, "end": 400},
            {"text": "two", "start": 500, "end": 900},
            {"text": "three", "start": 5000, "end": 5400},
        ],
        "utterances": [],
    }
    t = normalize_assemblyai(result)
    assert len(t.segments) == 2  # split on the 4.1s gap
    assert t.segments[0].text == "one two"


def test_normalize_assemblyai_skips_empty_words():
    result = {
        "words": [
            {"text": "ok", "start": 0, "end": 300},
            {"text": "", "start": 400, "end": 500},
        ],
        "utterances": [_utt(0, 500, "ok")],
    }
    t = normalize_assemblyai(result)
    assert len(t.segments[0].words) == 1


def test_clean_transcript_removes_bad_segments():
    t = Transcript(
        segments=[
            Segment(id=0, start=0, end=2, text="good"),
            Segment(id=1, start=5, end=5, text="zero length"),
            Segment(id=2, start=-1, end=3, text="negative start"),
            Segment(id=3, start=2, end=4, text="   "),
            Segment(id=4, start=4, end=6, text="dupe"),
            Segment(id=5, start=4, end=6, text="dupe"),
        ]
    )
    cleaned = clean_transcript(t)
    assert [s.text for s in cleaned.segments] == ["good", "dupe"]
    assert cleaned.segments[1].id == 1  # renumbered
