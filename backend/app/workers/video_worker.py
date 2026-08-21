"""Background worker: claim jobs from the queue and run the pipeline.

Also sweeps for jobs stuck in an active state beyond the job timeout so no job
is ever left permanently stuck (§11, §25).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from ..config import get_settings
from ..db import get_session
from ..models.job import JobStatus, VideoJob
from ..services.pipeline import run_job
from ..services.queue import get_queue
from ..utils import logging as logmod

logger = logmod.get_logger("kryber.worker")

SWEEP_INTERVAL_SECONDS = 60.0


def recover_stuck_jobs() -> int:
    """Mark jobs that have been active beyond the timeout as failed."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.job_timeout_seconds)
    session = get_session()
    try:
        stuck = (
            session.query(VideoJob)
            .filter(
                VideoJob.status.in_(JobStatus.ACTIVE),
                VideoJob.updated_at < cutoff,
            )
            .all()
        )
        for job in stuck:
            job.status = JobStatus.FAILED
            job.stage = job.stage or "unknown"
            job.error_code = "JOB_TIMEOUT"
            job.error_message = (
                f"Job exceeded the {settings.job_timeout_seconds}s timeout and was marked failed."
            )
            logmod.error(logger, "job timed out", job_id=job.id, stage=job.stage)
        session.commit()
        return len(stuck)
    finally:
        session.close()


def run_worker() -> None:
    settings = get_settings()
    logmod.setup_logging(settings.log_level)
    queue = get_queue()
    logmod.info(logger, "worker started", queue_backend=settings.queue_backend)

    recovered = recover_stuck_jobs()
    if recovered:
        logmod.warning(logger, "recovered stuck jobs on startup", count=recovered)

    last_sweep = time.monotonic()

    while True:
        if time.monotonic() - last_sweep >= SWEEP_INTERVAL_SECONDS:
            recover_stuck_jobs()
            last_sweep = time.monotonic()

        job_id = queue.dequeue(timeout=5.0)
        if job_id is None:
            continue

        logmod.info(logger, "claimed job", job_id=job_id)
        try:
            run_job(job_id)
        except Exception:
            # run_job records stage failures on the job; this is a last-resort guard.
            logmod.error(logger, "worker crashed while running job", job_id=job_id, exc_info=True)
            time.sleep(1)


if __name__ == "__main__":
    run_worker()
