"""Job endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.clip import Clip
from ..models.job import JobStatus, VideoJob, new_job_id
from ..schemas.clips import ClipResponse
from ..schemas.jobs import (
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    progress_for_status,
)
from ..services import jobs as jobs_service
from ..services.pipeline import workspace_dir
from ..services.queue import JobQueue
from ..utils import logging as logmod
from ..utils.validation import safe_join
from .deps import get_db, get_job_queue, rate_limit

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logmod.get_logger("kryber.api.jobs")


def _get_job_or_404(db: Session, job_id: str) -> VideoJob:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found."})
    return job


@router.post("", response_model=JobCreateResponse, status_code=201)
def create_job(
    payload: JobCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    queue: JobQueue = Depends(get_job_queue),
):
    rate_limit(request)
    job = jobs_service.create_job(
        db, payload.url, clip_length=payload.clip_length, enqueue=queue.enqueue
    )
    return JobCreateResponse(job_id=job.id, status=job.status)


_UPLOAD_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv"}


@router.post("/upload", response_model=JobCreateResponse, status_code=201)
async def create_job_from_upload(
    request: Request,
    file: UploadFile = File(...),
    clip_length: int = Form(60),
    db: Session = Depends(get_db),
    queue: JobQueue = Depends(get_job_queue),
):
    """Create a job from an uploaded video file (no external host needed)."""
    rate_limit(request)

    if clip_length not in jobs_service.ALLOWED_CLIP_LENGTHS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CLIP_LENGTH",
                "message": f"clip_length must be one of {sorted(jobs_service.ALLOWED_CLIP_LENGTHS)}.",
                "stage": "validation",
            },
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": "Upload a video file (.mp4, .webm, .mov, .m4v, .mkv or .ogv).",
                "stage": "validation",
            },
        )

    job = VideoJob(
        id=new_job_id(),
        source_url=f"upload://{file.filename}",
        source_platform="upload",
        status=JobStatus.QUEUED,
        stage=JobStatus.QUEUED,
        clip_length=clip_length,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    ws = workspace_dir(job.id)
    os.makedirs(ws, exist_ok=True)
    dest = safe_join(ws, f"source{ext}")
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    job.source_path = dest
    db.commit()

    try:
        queue.enqueue(job.id)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.stage = JobStatus.QUEUED
        job.error_code = "QUEUE_FAILED"
        job.error_message = f"Failed to enqueue job: {exc}"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail={"code": "QUEUE_FAILED", "message": str(exc), "stage": "queued"},
        ) from exc

    logmod.info(logger, "upload job created", job_id=job.id, filename=file.filename)
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    resp = JobStatusResponse.model_validate(job)
    resp.progress = progress_for_status(job.status)
    return resp


@router.get("/{job_id}/clips", response_model=list[ClipResponse])
def get_job_clips(job_id: str, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    stmt = select(Clip).where(Clip.job_id == job_id).order_by(Clip.rank)
    return [ClipResponse.model_validate(c) for c in db.execute(stmt).scalars().all()]
