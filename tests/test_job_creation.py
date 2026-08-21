"""Job creation service (§8, §27)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.errors import URLValidationError
from app.models.job import JobStatus, VideoJob
from app.services.jobs import create_job

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_create_job_stores_canonical_url(db_session):
    job = create_job(db_session, "https://youtu.be/dQw4w9WgXcQ", enqueue=lambda _: None)
    assert job.id.startswith("kr_")
    assert job.status == JobStatus.QUEUED
    assert job.source_platform == "youtube"
    assert job.source_url == VALID_URL
    assert job.error_code is None


def test_create_job_enqueues_job_id(db_session):
    seen = []
    job = create_job(db_session, VALID_URL, enqueue=lambda jid: seen.append(jid))
    assert seen == [job.id]


def test_create_job_rejects_invalid_url(db_session):
    with pytest.raises(URLValidationError):
        create_job(db_session, "https://vimeo.com/123", enqueue=lambda _: None)


def test_create_job_rejects_empty_url(db_session):
    with pytest.raises(URLValidationError):
        create_job(db_session, "", enqueue=lambda _: None)


def test_create_job_marks_failed_when_enqueue_fails(db_session):
    def boom(jid):
        raise RuntimeError("redis down")

    with pytest.raises(RuntimeError):
        create_job(db_session, VALID_URL, enqueue=boom)

    jobs = db_session.execute(select(VideoJob)).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.FAILED
    assert jobs[0].error_code == "QUEUE_FAILED"


def test_create_job_stores_clip_length(db_session):
    job = create_job(db_session, VALID_URL, clip_length=45, enqueue=lambda _: None)
    assert job.clip_length == 45


def test_create_job_defaults_clip_length(db_session):
    job = create_job(db_session, VALID_URL, enqueue=lambda _: None)
    assert job.clip_length == 60


def test_create_job_rejects_invalid_clip_length(db_session):
    from app.errors import InvalidClipLengthError

    with pytest.raises(InvalidClipLengthError):
        create_job(db_session, VALID_URL, clip_length=25, enqueue=lambda _: None)


def test_create_job_is_persisted(db_session):
    job = create_job(db_session, VALID_URL, enqueue=lambda _: None)
    loaded = db_session.get(VideoJob, job.id)
    assert loaded is not None
    assert loaded.id == job.id
