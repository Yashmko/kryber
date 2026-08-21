"""Clip endpoints."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..models.clip import Clip, ClipStatus
from ..schemas.clips import ClipResponse
from .deps import get_db

router = APIRouter(prefix="/api/clips", tags=["clips"])


def _get_clip_or_404(db: Session, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail={"code": "CLIP_NOT_FOUND", "message": f"Clip {clip_id} not found."})
    return clip


@router.get("/{clip_id}", response_model=ClipResponse)
def get_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip_or_404(db, clip_id)
    return ClipResponse.model_validate(clip)


@router.get("/{clip_id}/download")
def download_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip_or_404(db, clip_id)
    if clip.status != ClipStatus.COMPLETED or not clip.output_path:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CLIP_NOT_READY",
                "message": "This clip has not been rendered yet.",
                "stage": "rendering",
            },
        )
    if not os.path.isfile(clip.output_path):
        raise HTTPException(
            status_code=404,
            detail={"code": "CLIP_FILE_MISSING", "message": "Rendered file is missing from storage."},
        )
    return FileResponse(
        clip.output_path,
        media_type="video/mp4",
        filename=f"kryber_short_{clip.rank:02d}.mp4",
    )
