"""TranscriptionProvider abstraction + transcript dataclasses.

Contract: every provider returns a :class:`Transcript` with timestamped
segments (and word timestamps when available). Normalization and validation
live in :mod:`app.services.transcription.normalize`.
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field


@dataclass
class Word:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(word=str(d.get("word", "")).strip(), start=float(d.get("start", 0)), end=float(d.get("end", 0)))


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    def to_dict(self, *, include_words: bool = True) -> dict:
        d = {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }
        if include_words and self.words:
            d["words"] = [w.to_dict() for w in self.words]
        return d

    @classmethod
    def from_dict(cls, d: dict, idx: int = 0) -> "Segment":
        words = [Word.from_dict(w) for w in (d.get("words") or [])]
        return cls(
            id=int(d.get("id", idx)),
            start=float(d.get("start", 0)),
            end=float(d.get("end", 0)),
            text=str(d.get("text", "")).strip(),
            words=words,
        )


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((s.end for s in self.segments), default=0.0)

    @property
    def character_count(self) -> int:
        return sum(len(s.text) for s in self.segments)

    def is_usable(self) -> bool:
        return any(s.text.strip() for s in self.segments)

    def to_payload(self) -> dict:
        return {"segments": [s.to_dict() for s in self.segments]}

    @classmethod
    def from_payload(cls, payload: dict) -> "Transcript":
        segs = payload.get("segments") or []
        return cls(segments=[Segment.from_dict(s, idx=i) for i, s in enumerate(segs)])

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_payload(), f, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Transcript":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_payload(json.load(f))


class TranscriptionProvider(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def transcribe(self, audio_path: str) -> Transcript:
        """Transcribe ``audio_path`` into a timestamped Transcript."""
