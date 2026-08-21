"""Duplicate-work detection (§33)."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.job import JobStatus, VideoJob
from app.services.jobs import create_job, mark_failed

WATCH = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SHORT = "https://youtu.be/dQw4w9WgXcQ"


def _count(db) -> int:
    return db.execute(select(func.count()).select_from(VideoJob)).scalar_one()


def test_same_url_reuses_active_job(db_session):
    first = create_job(db_session, WATCH, enqueue=lambda _: None)
    second = create_job(db_session, WATCH, enqueue=lambda _: None)
    assert second.id == first.id
    assert _count(db_session) == 1


def test_different_url_forms_normalize_to_same_job(db_session):
    first = create_job(db_session, WATCH, enqueue=lambda _: None)
    second = create_job(db_session, SHORT, enqueue=lambda _: None)
    assert second.id == first.id
    assert _count(db_session) == 1


def test_completed_job_is_reused(db_session):
    job = create_job(db_session, WATCH, enqueue=lambda _: None)
    job.status = JobStatus.COMPLETED
    db_session.commit()
    again = create_job(db_session, WATCH, enqueue=lambda _: None)
    assert again.id == job.id


def test_failed_job_allows_new_attempt(db_session):
    job = create_job(db_session, WATCH, enqueue=lambda _: None)
    mark_failed(job, stage="ingesting", code="INGESTION_FAILED", message="nope")
    db_session.commit()

    retry = create_job(db_session, WATCH, enqueue=lambda _: None)
    assert retry.id != job.id
    assert _count(db_session) == 2


def test_distinct_urls_create_distinct_jobs(db_session):
    a = create_job(db_session, WATCH, enqueue=lambda _: None)
    b = create_job(db_session, "https://www.youtube.com/watch?v=9bZkp7q19f0", enqueue=lambda _: None)
    assert a.id != b.id
    assert _count(db_session) == 2
