"""Pipeline orchestrator — the real KRYBER workflow.

queued → ingesting → transcribing → analyzing → rendering → completed
        └→ failed (error_code + stage + error_message) on any stage error.

Every stage is independently recoverable: failures are recorded with the exact
stage and error, never swallowed or replaced with a generic message.
"""
from __future__ import annotations

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import get_settings
from ..db import get_session
from ..errors import RenderFailedError, StageError
from ..models.clip import Clip, ClipStatus, new_clip_id
from ..models.job import JobStatus, VideoJob
from ..services import jobs as jobs_service
from ..utils import logging as logmod
from ..utils.ffmpeg import extract_audio, probe
from ..utils.process import ProcessFailure
from ..utils.validation import safe_join

logger = logmod.get_logger("kryber.pipeline")


def workspace_dir(job_id: str) -> str:
    settings = get_settings()
    return safe_join(settings.tmp_root, job_id)


def run_job(job_id: str) -> None:
    """Run every pipeline stage for a job, recording failures per stage."""
    session = get_session()
    try:
        job = session.get(VideoJob, job_id)
        if job is None:
            logmod.error(logger, "job not found", job_id=job_id)
            return
        with logmod.JobContext(job_id):
            _run_stages(session, job)
    finally:
        session.close()


def _run_stages(session, job: VideoJob) -> None:
    stages = [
        (JobStatus.INGESTING, _stage_ingest),
        (JobStatus.TRANSCRIBING, _stage_transcribe),
        (JobStatus.ANALYZING, _stage_analyze),
        (JobStatus.RENDERING, _stage_render),
    ]
    for status, fn in stages:
        if job.status in JobStatus.TERMINAL:
            return
        jobs_service.transition(job, status, stage=status)
        session.commit()
        stage_started = time.monotonic()
        with logmod.StageContext(status):
            try:
                fn(session, job)
            except StageError as exc:
                jobs_service.mark_failed(
                    job, stage=exc.stage or status, code=exc.code, message=exc.message
                )
                session.commit()
                logmod.error(logger, "stage failed", job_id=job.id, stage=status, code=exc.code)
                return
            except Exception as exc:  # unexpected — surfaced, never swallowed
                jobs_service.mark_failed(
                    job,
                    stage=status,
                    code=f"{status.upper()}_FAILED",
                    message=f"Unexpected error: {type(exc).__name__}: {exc}",
                )
                session.commit()
                logmod.error(logger, "stage crashed", job_id=job.id, stage=status, exc_info=True)
                return
        # Persist stage results (paths, durations, transcript) before proceeding.
        session.commit()
        logmod.info(
            logger,
            "stage done",
            job_id=job.id,
            stage=status,
            elapsed_s=round(time.monotonic() - stage_started, 1),
        )
        # A concurrent sweeper may have failed this job; respect it.
        session.refresh(job)

    if job.status not in JobStatus.TERMINAL:
        jobs_service.transition(job, JobStatus.COMPLETED, stage=JobStatus.COMPLETED)
        session.commit()
        logmod.info(logger, "job completed", job_id=job.id)


# ── Stage 1: ingestion ───────────────────────────────────────────────────
def _stage_ingest(session, job: VideoJob) -> None:
    from .ingestion.registry import get_source
    from .ingestion.validation import validate_video_file

    ws = workspace_dir(job.id)
    os.makedirs(ws, exist_ok=True)

    # Cache hit: reuse an already-downloaded, valid source.
    if job.source_path and os.path.isfile(job.source_path):
        try:
            info = validate_video_file(job.source_path, job_id=job.id)
            job.duration = info.duration
            logmod.info(logger, "using cached source video", job_id=job.id, path=job.source_path)
            return
        except StageError:
            logmod.warning(logger, "cached source invalid; re-downloading", job_id=job.id)

    # Uploaded files are not re-downloadable — surface a clear error instead.
    if job.source_platform == "upload":
        raise StageError(
            "ingesting",
            "INGESTION_FAILED",
            "The uploaded video file is missing or invalid. Please upload it again.",
        )

    source = get_source(job.source_platform)
    meta = None
    try:
        meta = source.get_metadata(job.source_url)
        job.title = meta.title or job.title
    except StageError:
        logmod.warning(logger, "metadata lookup failed; continuing", job_id=job.id)

    result = source.download(job.source_url, ws)
    info = validate_video_file(result.path, job_id=job.id)

    job.source_path = result.path
    job.duration = info.duration
    if result.metadata.title:
        job.title = result.metadata.title
    elif meta and meta.title:
        job.title = meta.title

    logmod.info(
        logger,
        "video ingested and validated",
        job_id=job.id,
        stage="ingesting",
        video_path=job.source_path,
        file_size=info.size,
        duration=f"{info.duration:.2f}",
        width=info.width,
        height=info.height,
    )


# ── Stage 2: transcription ───────────────────────────────────────────────
def _stage_transcribe(session, job: VideoJob) -> None:
    from .transcription import get_transcription_provider
    from .transcription.base import Transcript
    from .transcription.normalize import validate_transcript

    ws = workspace_dir(job.id)
    audio_path = safe_join(ws, "audio.wav")
    transcript_path = safe_join(ws, "transcript.json")

    # Cache hit: reuse a valid transcript from a previous attempt.
    if os.path.isfile(transcript_path):
        try:
            cached = Transcript.load(transcript_path)
            validate_transcript(cached, job_id=job.id, video_duration=job.duration)
            job.transcript_path = transcript_path
            logmod.info(logger, "using cached transcript", job_id=job.id)
            return
        except StageError:
            logmod.warning(logger, "cached transcript invalid; re-transcribing", job_id=job.id)

    if not job.source_path or not os.path.isfile(job.source_path):
        raise StageError("transcribing", "TRANSCRIPTION_FAILED", "Source video is missing.")

    # Audio extraction.
    if not (os.path.isfile(audio_path) and os.path.getsize(audio_path) > 0):
        try:
            extract_audio(job.source_path, audio_path)
        except ProcessFailure as exc:
            raise StageError("transcribing", "TRANSCRIPTION_FAILED", f"Audio extraction failed: {exc}") from exc

    if not os.path.isfile(audio_path) or os.path.getsize(audio_path) <= 0:
        raise StageError("transcribing", "TRANSCRIPTION_FAILED", "Extracted audio is missing or empty.")
    try:
        audio_info = probe(audio_path)
    except ProcessFailure:
        audio_info = None
    if audio_info is None or audio_info.duration <= 0:
        raise StageError("transcribing", "TRANSCRIPTION_FAILED", "Extracted audio has no valid duration.")

    job.audio_path = audio_path

    provider = get_transcription_provider()
    transcript = provider.transcribe(audio_path)
    transcript = validate_transcript(
        transcript,
        job_id=job.id,
        video_duration=job.duration,
        audio_duration=audio_info.duration,
    )
    transcript.save(transcript_path)
    job.transcript_path = transcript_path


# ── Stage 3: analysis ────────────────────────────────────────────────────
def _stage_analyze(session, job: VideoJob) -> None:
    from .analysis import get_llm_provider
    from .analysis.clip_engine import discover_clips
    from .transcription.base import Transcript
    from .hooks.generator import ensure_grounded

    if not job.transcript_path or not os.path.isfile(job.transcript_path):
        raise StageError("analyzing", "ANALYSIS_FAILED", "Transcript is missing; cannot analyze.")
    transcript = Transcript.load(job.transcript_path)

    provider = get_llm_provider()
    video_duration = job.duration or transcript.duration
    target_duration = float(job.clip_length or get_settings().clip_max_duration)
    candidates = discover_clips(provider, transcript, video_duration, max_duration=target_duration)

    for cand in candidates:
        window_text = _window_text(transcript, cand.start, cand.end)
        hook = ensure_grounded(cand.hook, window_text)
        session.add(
            Clip(
                id=new_clip_id(),
                job_id=job.id,
                rank=cand.rank,
                start_time=cand.start,
                end_time=cand.end,
                score=cand.score,
                hook=hook,
                caption_title=cand.caption_title,
                reason=cand.reason,
                status=ClipStatus.PENDING,
            )
        )
    session.commit()
    logmod.info(logger, "clips persisted", job_id=job.id, count=len(candidates))


def _window_text(transcript: Transcript, start: float, end: float) -> str:
    parts = [s.text for s in transcript.segments if s.end >= start - 0.5 and s.start <= end + 0.5]
    return " ".join(parts)


# ── Stage 4: rendering ───────────────────────────────────────────────────
def _stage_render(session, job: VideoJob) -> None:
    from .captions.grouper import clip_local_words, group_words, synthesize_words
    from .rendering.ffmpeg_renderer import render_clip
    from .storage import get_storage

    settings = get_settings()
    ws = workspace_dir(job.id)

    if not job.source_path or not os.path.isfile(job.source_path):
        raise RenderFailedError("Source video is missing; cannot render.")

    transcript = None
    if job.transcript_path and os.path.isfile(job.transcript_path):
        from .transcription.base import Transcript

        transcript = Transcript.load(job.transcript_path)

    clips = (
        session.query(Clip)
        .filter(Clip.job_id == job.id)
        .order_by(Clip.rank)
        .all()
    )
    if not clips:
        raise RenderFailedError("No clips to render.")

    storage = get_storage()
    render_dir = safe_join(ws, "clips")
    os.makedirs(render_dir, exist_ok=True)

    # Build caption groups in the main thread (cheap, deterministic).
    tasks = []
    for clip in clips:
        groups = []
        if transcript is not None:
            words = [w for s in transcript.segments for w in s.words]
            clip_dur = clip.end_time - clip.start_time
            local_words = clip_local_words(words, clip.start_time, clip_dur)
            if local_words:
                groups = group_words(local_words)
            if not groups:
                synth = synthesize_words(transcript.segments, clip.start_time, clip_dur)
                groups = group_words(synth)
        out_path = safe_join(render_dir, f"clip_{clip.rank:02d}.mp4")
        tasks.append((clip, groups, out_path))

    def _render_one(task):
        clip, groups, out_path = task
        try:
            info = render_clip(
                job.source_path,
                out_path,
                start=clip.start_time,
                end=clip.end_time,
                caption_groups=groups,
            )
            return clip.id, out_path, info, None
        except Exception as exc:  # per-clip isolation: one failure doesn't kill the job
            return clip.id, None, None, str(exc)

    successes = 0
    with ThreadPoolExecutor(max_workers=max(1, settings.render_parallelism)) as pool:
        futures = {pool.submit(_render_one, t): t for t in tasks}
        for fut in as_completed(futures):
            clip_id, out_path, info, err = fut.result()
            clip = session.get(Clip, clip_id)
            if err is not None:
                clip.status = ClipStatus.FAILED
                logmod.error(logger, "clip render failed", job_id=job.id, clip_id=clip_id, error=err)
                continue
            try:
                stored = storage.put(out_path, f"{job.id}/clip_{clip.rank:02d}.mp4")
            except Exception as exc:
                clip.status = ClipStatus.FAILED
                logmod.error(logger, "clip upload failed", job_id=job.id, clip_id=clip.id, error=str(exc))
                continue
            clip.output_path = stored
            clip.status = ClipStatus.COMPLETED
            successes += 1
            logmod.info(
                logger,
                "clip rendered",
                job_id=job.id,
                clip_id=clip.id,
                rank=clip.rank,
                duration=f"{clip.end_time - clip.start_time:.1f}s",
                path=stored,
            )
    session.commit()

    if successes == 0:
        raise RenderFailedError("All clip renders failed.")

    # Retention: drop the per-job temp workspace after a successful upload.
    shutil.rmtree(ws, ignore_errors=True)
    logmod.info(logger, "rendering complete", job_id=job.id, rendered=successes, total=len(tasks))
