"""End-to-end pipeline test (mock ASR/LLM + REAL FFmpeg rendering).

This exercises the full workflow — audio extraction, transcript validation,
clip discovery, hook grounding, caption burn-in, 9:16 crop, loudness
normalization — and produces real 1080×1920 MP4 files on disk.
"""
from __future__ import annotations

import os

from app.db import init_engine, get_session
from app.models.clip import Clip, ClipStatus
from app.models.job import JobStatus, VideoJob, new_job_id
from app.services.pipeline import run_job
from app.utils.ffmpeg import probe
from tests.helpers import make_test_video

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_full_pipeline_end_to_end(tmp_path):
    init_engine()
    src = make_test_video(tmp_path / "src.mp4", duration=90)

    s = get_session()
    job = VideoJob(
        id=new_job_id(),
        source_url=URL,
        source_platform="youtube",
        status=JobStatus.QUEUED,
        stage=JobStatus.QUEUED,
        source_path=src,
        duration=90.0,
    )
    s.add(job)
    s.commit()
    job_id = job.id
    s.close()

    run_job(job_id)

    s = get_session()
    j = s.get(VideoJob, job_id)
    assert j.status == JobStatus.COMPLETED, f"{j.error_code}: {j.error_message}"

    clips = s.query(Clip).filter(Clip.job_id == job_id).order_by(Clip.rank).all()
    assert 1 <= len(clips) <= 10

    for c in clips:
        assert c.status == ClipStatus.COMPLETED, f"clip {c.rank} status={c.status}"
        assert c.output_path and os.path.isfile(c.output_path), f"clip {c.rank} missing output"
        info = probe(c.output_path)
        assert info.width == 1080 and info.height == 1920, f"clip {c.rank} is {info.width}x{info.height}"
        assert info.has_video and info.has_audio
        assert 20 <= (c.end_time - c.start_time) <= 60

    s.close()
