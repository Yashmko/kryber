"""Pipeline failure handling — jobs must fail with the exact stage + error (§25)."""
from __future__ import annotations

from types import SimpleNamespace

from app.db import init_engine, get_session
from app.errors import TranscriptionFailedError
from app.models.job import JobStatus, VideoJob, new_job_id
from app.services.pipeline import run_job
from tests.helpers import make_test_video

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_transcription_failure_marks_job_failed(monkeypatch, tmp_path):
    init_engine()
    src = make_test_video(tmp_path / "src.mp4", duration=6)

    s = get_session()
    job = VideoJob(
        id=new_job_id(),
        source_url=URL,
        source_platform="youtube",
        status=JobStatus.QUEUED,
        stage=JobStatus.QUEUED,
        source_path=src,
        duration=6.0,
    )
    s.add(job)
    s.commit()
    job_id = job.id
    s.close()

    def boom(audio_path):
        raise TranscriptionFailedError("AssemblyAI said no.")

    monkeypatch.setattr(
        "app.services.transcription.get_transcription_provider",
        lambda: SimpleNamespace(transcribe=boom),
    )

    run_job(job_id)

    s = get_session()
    j = s.get(VideoJob, job_id)
    assert j.status == JobStatus.FAILED
    assert j.stage == "transcribing"
    assert j.error_code == "TRANSCRIPTION_FAILED"
    assert j.error_message == "AssemblyAI said no."
    s.close()
