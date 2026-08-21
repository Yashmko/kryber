"""Deterministic mock transcription provider (tests + no-key local dev).

Produces a realistic timestamped transcript spanning the *actual audio
duration* (probed from the WAV), so the full pipeline can be exercised
end-to-end against any real video without calling AssemblyAI.
"""
from __future__ import annotations

from .base import Segment, Transcript, TranscriptionProvider, Word

_SCRIPT = [
    "when I started my company I made one massive mistake",
    "I spent three years building the wrong product",
    "before realizing that nobody wanted it",
    "the moment I talked to real customers everything changed",
    "most founders fall in love with their idea and ignore the market",
    "here is the part nobody tells you about pricing",
    "I almost gave up twice but the third pivot saved the business",
    "so if you are building something stop polishing and go talk to users today",
]


class MockTranscriptionProvider(TranscriptionProvider):
    name = "mock"

    def __init__(self, duration: float | None = None):
        self.duration = duration

    def transcribe(self, audio_path: str) -> Transcript:
        duration = self.duration
        if not duration:
            try:
                from ...utils.ffmpeg import probe

                duration = probe(audio_path).duration
            except Exception:
                duration = 90.0
        if not duration or duration <= 0:
            duration = 90.0

        n = len(_SCRIPT)
        seg_dur = duration / n
        segments: list[Segment] = []
        for i, text in enumerate(_SCRIPT):
            start = round(i * seg_dur, 2)
            end = round((i + 1) * seg_dur - 0.05, 2)
            words_raw = text.split()
            w_dur = (end - start) / len(words_raw)
            words = [
                Word(word=w, start=round(start + j * w_dur, 2), end=round(start + (j + 1) * w_dur, 2))
                for j, w in enumerate(words_raw)
            ]
            segments.append(Segment(id=i, start=start, end=end, text=text, words=words))
        return Transcript(segments=segments)
