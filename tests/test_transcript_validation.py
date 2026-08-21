"""Critical transcript validation gates (§13)."""
from __future__ import annotations

import pytest

from app.errors import TranscriptionFailedError
from app.services.transcription.base import Segment, Transcript
from app.services.transcription.normalize import validate_transcript


def test_none_transcript_fails():
    with pytest.raises(TranscriptionFailedError):
        validate_transcript(None)


def test_empty_segments_fails():
    with pytest.raises(TranscriptionFailedError):
        validate_transcript(Transcript(segments=[]))


def test_all_blank_text_fails():
    t = Transcript(segments=[Segment(id=0, start=0, end=2, text="   ")])
    with pytest.raises(TranscriptionFailedError):
        validate_transcript(t)


def test_valid_transcript_passes():
    t = Transcript(
        segments=[
            Segment(id=0, start=0, end=2, text="hello there"),
            Segment(id=1, start=2, end=4, text="second segment"),
        ]
    )
    out = validate_transcript(t)
    assert len(out.segments) == 2
