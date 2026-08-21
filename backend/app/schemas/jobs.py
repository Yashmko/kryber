"""Request/response schemas for the jobs API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.job import JobStatus

# Progress is derived from the actual pipeline stage (never fabricated).
_STAGE_PROGRESS = {
    JobStatus.QUEUED: 0,
    JobStatus.INGESTING: 10,
    JobStatus.TRANSCRIBING: 30,
    JobStatus.ANALYZING: 55,
    JobStatus.RENDERING: 75,
    JobStatus.COMPLETED: 100,
    JobStatus.FAILED: 100,
}


def progress_for_status(status: str) -> int:
    return _STAGE_PROGRESS.get(status, 0)


class JobCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    clip_length: int | None = Field(
        default=None,
        description="Target short length in seconds: 30, 45, or 60 (default 60).",
    )


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    stage: str | None = None
    progress: int = 0
    error_code: str | None = None
    error_message: str | None = None
    source_url: str
    source_platform: str
    title: str | None = None
    duration: float | None = None
    clip_length: int = 60
    created_at: datetime
    updated_at: datetime
