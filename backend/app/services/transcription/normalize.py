"""Transcript normalization + critical validation (§13–14).

The pipeline is NOT allowed to hand the LLM an empty/broken transcript —
every gate here fails the job loudly before any analysis call.
"""
from __future__ import annotations

from ...errors import TranscriptionFailedError
from ...utils import logging as logmod
from .base import Segment, Transcript, Word

logger = logmod.get_logger("kryber.transcription.normalize")


def _clean_text(text: str) -> str:
    return " ".join((text or "").split())


def normalize_assemblyai(result: dict) -> Transcript:
    """Convert an AssemblyAI v2 transcript result into a clean Transcript.

    Prefers ``utterances`` (timestamped speech segments); falls back to
    grouping word timestamps into segments by time gaps.
    """
    words_raw = result.get("words") or []
    words: list[Word] = []
    for w in words_raw:
        text = _clean_text(w.get("text") or "")
        if not text:
            continue
        try:
            words.append(Word(word=text, start=float(w["start"]) / 1000.0, end=float(w["end"]) / 1000.0))
        except (KeyError, TypeError, ValueError):
            continue

    utterances = result.get("utterances") or []
    segments: list[Segment] = []
    if utterances:
        for i, u in enumerate(utterances):
            text = _clean_text(u.get("text") or "")
            if not text:
                continue
            seg_words = [
                w for w in words
                if w.start >= float(u.get("start", 0)) / 1000.0 - 0.1
                and w.end <= float(u.get("end", 0)) / 1000.0 + 0.1
            ]
            segments.append(
                Segment(
                    id=len(segments),
                    start=float(u.get("start", 0)) / 1000.0,
                    end=float(u.get("end", 0)) / 1000.0,
                    text=text,
                    words=seg_words or [],
                )
            )
    else:
        segments = _segments_from_words(words)

    return Transcript(segments=segments)


def _segments_from_words(words: list[Word], max_gap: float = 1.5, max_words: int = 14) -> list[Segment]:
    """Fallback: group words into segments, splitting on pauses."""
    if not words:
        return []
    segments: list[Segment] = []
    current: list[Word] = [words[0]]
    for w in words[1:]:
        gap = w.start - current[-1].end
        if gap > max_gap or len(current) >= max_words:
            segments.append(_segment_from_words(len(segments), current))
            current = [w]
        else:
            current.append(w)
    if current:
        segments.append(_segment_from_words(len(segments), current))
    return segments


def _segment_from_words(idx: int, words: list[Word]) -> Segment:
    return Segment(
        id=idx,
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(w.word for w in words),
        words=words,
    )


def clean_transcript(transcript: Transcript) -> Transcript:
    """Remove empty segments, invalid timestamps and duplicates (§14)."""
    kept: list[Segment] = []
    seen_times: set[tuple[float, float]] = set()
    for seg in transcript.segments:
        text = _clean_text(seg.text)
        if not text:
            continue
        if seg.start < 0 or seg.end <= seg.start:
            continue
        key = (round(seg.start, 2), round(seg.end, 2))
        if key in seen_times:
            continue
        seen_times.add(key)
        seg.text = text
        seg.id = len(kept)
        kept.append(seg)
    return Transcript(segments=kept)


def validate_transcript(
    transcript: Transcript | None,
    *,
    job_id: str | None = None,
    video_duration: float | None = None,
    audio_duration: float | None = None,
) -> Transcript:
    """Hard gate before the LLM. Raises TRANSCRIPTION_FAILED on any defect."""
    tag = f" (job {job_id})" if job_id else ""

    if transcript is None:
        raise TranscriptionFailedError(f"No transcript was produced{tag}.")

    transcript = clean_transcript(transcript)

    if not transcript.segments:
        raise TranscriptionFailedError(f"Transcript has no segments{tag}.")

    if not transcript.is_usable():
        raise TranscriptionFailedError(f"Transcript segments contain no usable text{tag}.")

    logmod.info(
        logger,
        "TRANSCRIPTION COMPLETE",
        job_id=job_id,
        stage="transcribing",
        video_duration=f"{video_duration:.1f}" if video_duration is not None else None,
        audio_duration=f"{audio_duration:.1f}" if audio_duration is not None else None,
        segments=len(transcript.segments),
        characters=transcript.character_count,
    )
    for seg in transcript.segments[:3]:
        logmod.info(logger, "segment", job_id=job_id, stage="transcribing", id=seg.id, start=f"{seg.start:.2f}", end=f"{seg.end:.2f}", text=seg.text[:80])

    return transcript
