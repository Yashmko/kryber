"""Transcription provider factory."""
from __future__ import annotations

from ...config import get_settings
from .base import Transcript, TranscriptionProvider, Segment, Word  # noqa: F401
from .assemblyai import AssemblyAITranscriptionProvider
from .mock import MockTranscriptionProvider


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    if settings.transcription_provider == "assemblyai":
        return AssemblyAITranscriptionProvider()
    if settings.transcription_provider == "mock":
        return MockTranscriptionProvider()
    raise ValueError(f"Unknown transcription provider: {settings.transcription_provider!r}")
