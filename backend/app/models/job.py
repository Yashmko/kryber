"""VideoJob model + status definitions."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class JobStatus:
    QUEUED = "queued"
    INGESTING = "ingesting"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"

    ALL = {QUEUED, INGESTING, TRANSCRIBING, ANALYZING, RENDERING, COMPLETED, FAILED}
    ACTIVE = {QUEUED, INGESTING, TRANSCRIBING, ANALYZING, RENDERING}
    TERMINAL = {COMPLETED, FAILED}


def new_job_id() -> str:
    """Short, human-friendly id, e.g. ``kr_9f3ab21c4d5e6f70``."""
    return "kr_" + secrets.token_hex(8)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(2048), index=True)
    source_platform: Mapped[str] = mapped_column(String(32), default="youtube")
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED, index=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    transcript_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    clip_length: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
