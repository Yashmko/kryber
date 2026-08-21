"""Request/response schemas for the clips API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    rank: int
    start_time: float
    end_time: float
    score: float | None = None
    hook: str | None = None
    caption_title: str | None = None
    reason: str | None = None
    status: str
    created_at: datetime

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end_time - self.start_time), 2)
