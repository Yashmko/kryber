"""FFmpeg rendering: trim → 9:16 crop → loudness → captions → validate (§21–22).

One encode per clip (trim is input seeking; crop/scale/loudnorm/drawtext are
filter stages of the same encode). Captions are burned in with drawtext using
the bundled font, so output is deterministic and glyph-correct.
"""
from __future__ import annotations

import os
from pathlib import Path

from ...config import get_settings
from ...errors import RenderFailedError
from ...utils import logging as logmod
from ...utils.ffmpeg import MediaInfo, find_ffmpeg, probe
from ...utils.process import ProcessFailure, run_command
from ..captions.grouper import CaptionGroup, build_drawtext_filters, bundled_font_path
from .cropper import build_crop_filter

logger = logmod.get_logger("kryber.rendering")


def render_clip(
    source_path: str,
    out_path: str,
    *,
    start: float,
    end: float,
    caption_groups: list[CaptionGroup],
    x_frac: float = 0.5,
) -> MediaInfo:
    settings = get_settings()

    if not os.path.isfile(source_path):
        raise RenderFailedError(f"Source video missing for rendering: {source_path}")

    duration = max(0.5, end - start)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    crop = build_crop_filter(x_frac)

    caption_filters = ""
    if caption_groups:
        try:
            caption_filters = build_drawtext_filters(
                caption_groups,
                font_path=bundled_font_path(),
                font_size=settings.caption_font_size,
            )
        except Exception as exc:
            raise RenderFailedError(f"Caption generation failed: {exc}") from exc

    if caption_filters:
        video_filter = f"[0:v]{crop},{caption_filters}[v]"
    else:
        video_filter = f"[0:v]{crop}[v]"

    filter_complex = f"{video_filter};[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"

    argv = [
        find_ffmpeg(),
        "-y",
        "-ss", f"{start:.3f}",
        "-i", source_path,
        "-t", f"{duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", settings.render_preset,
        "-crf", str(settings.render_crf),
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-c:a", "aac",
        "-b:a", settings.render_audio_bitrate,
        "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ]

    try:
        run_command(argv, timeout=settings.render_timeout_seconds)
    except ProcessFailure as exc:
        if out.exists():
            out.unlink(missing_ok=True)
        raise RenderFailedError(f"FFmpeg render failed: {exc}") from exc

    return validate_rendered_clip(str(out))


def validate_rendered_clip(path: str) -> MediaInfo:
    """Verify a rendered clip before it is exposed to the user."""
    if not os.path.isfile(path):
        raise RenderFailedError(f"Rendered clip missing: {path}")
    if os.path.getsize(path) <= 0:
        raise RenderFailedError(f"Rendered clip is empty: {path}")
    try:
        info = probe(path)
    except ProcessFailure as exc:
        raise RenderFailedError(f"Rendered clip unreadable by ffprobe: {exc}") from exc
    if info.duration <= 0:
        raise RenderFailedError(f"Rendered clip has no duration: {path}")
    if not info.has_video:
        raise RenderFailedError(f"Rendered clip has no video stream: {path}")
    if not info.has_audio:
        raise RenderFailedError(f"Rendered clip has no audio stream: {path}")
    if info.width != 1080 or info.height != 1920:
        raise RenderFailedError(f"Rendered clip is {info.width}x{info.height}, expected 1080x1920: {path}")
    return info
