"""Clip model + status definitions."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClipStatus:
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"

    ALL = {PENDING, RENDERING, COMPLETED, FAILED}


def new_clip_id() -> str:
    return "cl_" + secrets.token_hex(8)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("video_jobs.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ClipStatus.PENDING, index=True)
    output_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
