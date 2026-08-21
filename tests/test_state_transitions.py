"""Job state machine (§7, §25)."""
from __future__ import annotations

import pytest

from app.errors import InvalidStateTransitionError
from app.models.job import JobStatus, VideoJob, new_job_id
from app.services.jobs import mark_failed, transition


def make_job(status: str = JobStatus.QUEUED) -> VideoJob:
    return VideoJob(
        id=new_job_id(),
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        source_platform="youtube",
        status=status,
        stage=status,
    )


def test_happy_path_transitions():
    job = make_job()
    for nxt in [
        JobStatus.INGESTING,
        JobStatus.TRANSCRIBING,
        JobStatus.ANALYZING,
        JobStatus.RENDERING,
        JobStatus.COMPLETED,
    ]:
        transition(job, nxt)
        assert job.status == nxt
    assert job.status == JobStatus.COMPLETED


def test_terminal_completed_is_final():
    job = make_job(JobStatus.COMPLETED)
    with pytest.raises(InvalidStateTransitionError):
        transition(job, JobStatus.INGESTING)


def test_cannot_skip_stages():
    job = make_job(JobStatus.QUEUED)
    with pytest.raises(InvalidStateTransitionError):
        transition(job, JobStatus.ANALYZING)


def test_unknown_status_rejected():
    job = make_job()
    with pytest.raises(InvalidStateTransitionError):
        transition(job, "wat")


def test_any_active_stage_can_fail():
    for stage in [JobStatus.QUEUED, JobStatus.INGESTING, JobStatus.TRANSCRIBING, JobStatus.ANALYZING, JobStatus.RENDERING]:
        job = make_job(stage)
        transition(job, JobStatus.FAILED)
        assert job.status == JobStatus.FAILED


def test_failed_can_be_retried():
    job = make_job(JobStatus.FAILED)
    transition(job, JobStatus.QUEUED)
    assert job.status == JobStatus.QUEUED


def test_mark_failed_records_error_details():
    job = make_job(JobStatus.INGESTING)
    mark_failed(job, stage="ingesting", code="INGESTION_FAILED", message="Download timed out.")
    assert job.status == JobStatus.FAILED
    assert job.stage == "ingesting"
    assert job.error_code == "INGESTION_FAILED"
    assert job.error_message == "Download timed out."
