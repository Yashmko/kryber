"""FFmpeg / FFprobe helpers: binary discovery, probing, audio extraction."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from functools import lru_cache

from ..config import get_settings
from .process import ProcessFailure, run_command


def _static_ffmpeg_paths() -> tuple[str, str] | None:
    try:
        from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise

        return get_or_fetch_platform_executables_else_raise()
    except Exception:
        return None


@lru_cache
def find_ffmpeg() -> str:
    """Locate an ffmpeg binary (env override → PATH → static binaries)."""
    settings = get_settings()
    if settings.ffmpeg_binary:
        return settings.ffmpeg_binary
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    static = _static_ffmpeg_paths()
    if static:
        return static[0]
    raise RuntimeError("ffmpeg not found. Install ffmpeg or set KRYBER_FFMPEG_BINARY.")


@lru_cache
def find_ffprobe() -> str:
    settings = get_settings()
    if settings.ffprobe_binary:
        return settings.ffprobe_binary
    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path
    static = _static_ffmpeg_paths()
    if static:
        return static[1]
    raise RuntimeError("ffprobe not found. Install ffmpeg or set KRYBER_FFPROBE_BINARY.")


@dataclass
class MediaInfo:
    path: str
    size: int = 0
    duration: float = 0.0
    width: int | None = None
    height: int | None = None
    has_video: bool = False
    has_audio: bool = False
    video_codec: str | None = None
    audio_codec: str | None = None


def probe(path: str) -> MediaInfo:
    """Read media metadata with ffprobe. Raises ProcessFailure if unreadable."""
    argv = [
        find_ffprobe(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    proc = run_command(argv, timeout=120)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProcessFailure(argv=argv, returncode=0, stderr_tail="ffprobe returned invalid JSON", timed_out=False) from exc

    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []

    duration = 0.0
    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width = None
    height = None
    if video:
        try:
            width = int(video.get("width") or 0) or None
            height = int(video.get("height") or 0) or None
        except (TypeError, ValueError):
            width = height = None
        # Some files report duration only on the stream.
        if duration <= 0:
            try:
                duration = float(video.get("duration") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0

    return MediaInfo(
        path=path,
        size=os.path.getsize(path) if os.path.isfile(path) else 0,
        duration=duration,
        width=width,
        height=height,
        has_video=video is not None,
        has_audio=audio is not None,
        video_codec=(video or {}).get("codec_name"),
        audio_codec=(audio or {}).get("codec_name"),
    )


def probe_duration(path: str) -> float:
    return probe(path).duration


def extract_audio(source_path: str, audio_path: str, *, timeout: float = 600) -> str:
    """Extract mono 16 kHz PCM WAV (transcription-friendly) from a video."""
    argv = [
        find_ffmpeg(),
        "-y",
        "-i", source_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        audio_path,
    ]
    run_command(argv, timeout=timeout)
    return audio_path
