"""Post-download video validation (§10)."""
from __future__ import annotations

import os

from ...config import get_settings
from ...errors import IngestionFailedError
from ...utils.ffmpeg import MediaInfo, probe
from ...utils.process import ProcessFailure


def validate_video_file(
    path: str,
    *,
    job_id: str | None = None,
) -> MediaInfo:
    """Verify a downloaded video meets every requirement, or fail loudly."""
    tag = f" (job {job_id})" if job_id else ""

    if not path or not os.path.isfile(path):
        raise IngestionFailedError(f"Downloaded file does not exist{tag}.")

    size = os.path.getsize(path)
    if size <= 0:
        raise IngestionFailedError(f"Downloaded file is empty (0 bytes){tag}.")

    try:
        info = probe(path)
    except ProcessFailure as exc:
        raise IngestionFailedError(f"FFprobe could not read the downloaded file{tag}: {exc}") from exc

    if info.duration <= 0:
        raise IngestionFailedError(f"Video has no valid duration{tag}.")
    if not info.has_video:
        raise IngestionFailedError(f"Downloaded file has no video stream{tag}.")
    if not info.has_audio:
        raise IngestionFailedError(f"Downloaded file has no audio stream{tag}.")

    settings = get_settings()
    if info.duration > settings.max_video_duration_seconds:
        raise IngestionFailedError(
            f"Video is {info.duration:.0f}s, exceeding the "
            f"{settings.max_video_duration_seconds}s limit{tag}."
        )

    return info
