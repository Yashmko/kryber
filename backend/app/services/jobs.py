"""Job creation, duplicate detection, and the state machine."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import InvalidClipLengthError, InvalidStateTransitionError
from ..models.job import JobStatus, VideoJob, new_job_id
from ..utils import logging as logmod
from ..utils.validation import validate_source_url

logger = logmod.get_logger("kryber.jobs")

ALLOWED_CLIP_LENGTHS = {30, 45, 60}
DEFAULT_CLIP_LENGTH = 60

# Allowed transitions. ``FAILED -> QUEUED`` enables explicit retries.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    JobStatus.QUEUED: {JobStatus.INGESTING, JobStatus.FAILED},
    JobStatus.INGESTING: {JobStatus.TRANSCRIBING, JobStatus.FAILED},
    JobStatus.TRANSCRIBING: {JobStatus.ANALYZING, JobStatus.FAILED},
    JobStatus.ANALYZING: {JobStatus.RENDERING, JobStatus.FAILED},
    JobStatus.RENDERING: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: {JobStatus.QUEUED},
}


def transition(job: VideoJob, new_status: str, *, stage: str | None = None) -> None:
    """Move a job to ``new_status``, enforcing the state machine."""
    if new_status not in JobStatus.ALL:
        raise InvalidStateTransitionError(f"Unknown status: {new_status!r}.")
    if job.status == new_status:
        return
    if new_status not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise InvalidStateTransitionError(
            f"Cannot move job {job.id} from {job.status!r} to {new_status!r}."
        )
    job.status = new_status
    if stage is not None:
        job.stage = stage
    elif new_status in JobStatus.ALL:
        job.stage = new_status


def mark_failed(job: VideoJob, *, stage: str, code: str, message: str) -> None:
    """Record a stage failure on the job and move it to ``failed``."""
    job.error_code = code
    job.error_message = message
    job.stage = stage
    job.status = JobStatus.FAILED


def _find_existing_job(db: Session, source_url: str) -> VideoJob | None:
    stmt = select(VideoJob).where(VideoJob.source_url == source_url)
    return db.execute(stmt).scalars().first()


def create_job(
    db: Session,
    url: str,
    *,
    clip_length: int | None = None,
    enqueue=None,
) -> VideoJob:
    """Validate a URL and create a job, deduping identical work.

    The job is committed BEFORE it is enqueued so a concurrent worker always
    finds it (fixes a claim race). If enqueueing fails, the job is marked
    failed with a real error instead of being silently lost.
    """
    platform, canonical_url = validate_source_url(url)

    length = int(clip_length) if clip_length is not None else DEFAULT_CLIP_LENGTH
    if length not in ALLOWED_CLIP_LENGTHS:
        raise InvalidClipLengthError(
            f"clip_length must be one of {sorted(ALLOWED_CLIP_LENGTHS)} seconds (got {length})."
        )

    existing = _find_existing_job(db, canonical_url)
    if existing is not None and existing.status != JobStatus.FAILED:
        logmod.info(
            logger,
            "duplicate work detected; reusing job",
            job_id=existing.id,
            status=existing.status,
        )
        return existing

    job = VideoJob(
        id=new_job_id(),
        source_url=canonical_url,
        source_platform=platform,
        status=JobStatus.QUEUED,
        stage=JobStatus.QUEUED,
        clip_length=length,
    )
    db.add(job)
    db.commit()  # visible to the worker BEFORE it is enqueued
    db.refresh(job)

    if enqueue is not None:
        try:
            enqueue(job.id)
        except Exception as exc:  # surface a real queue failure
            job.status = JobStatus.FAILED
            job.stage = JobStatus.QUEUED
            job.error_code = "QUEUE_FAILED"
            job.error_message = f"Failed to enqueue job: {exc}"
            db.commit()
            raise RuntimeError(f"Failed to enqueue job: {exc}") from exc

    logmod.info(logger, "job created", job_id=job.id, platform=platform, clip_length=length)
    return job
