"""URL validation + path-safety helpers.

Only user-provided input that survives these checks ever touches the
filesystem, the queue, or external tools (yt-dlp / ffmpeg).
"""
from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

from ..errors import URLValidationError

# ── YouTube URL handling ────────────────────────────────────────────────
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

MAX_URL_LENGTH = 2048


def _clean_host(netloc: str) -> str:
    """Strip userinfo and port from a netloc, lowercase it."""
    host = netloc.split("@")[-1].split(":")[0]
    return host.lower()


def parse_youtube_video_id(url: str) -> str | None:
    """Extract the 11-char video id from a supported YouTube URL, or None."""
    if not url or not isinstance(url, str):
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = _clean_host(parsed.netloc)
    if host not in _YOUTUBE_HOSTS:
        return None

    path = parsed.path or ""

    if host == "youtu.be" or host == "www.youtu.be":
        vid = path.lstrip("/").split("/")[0]
        return vid if _YT_ID_RE.match(vid) else None

    # watch?v=... / watch/VIDEO_ID
    query = parse_qs(parsed.query)
    vid = query.get("v", [None])[0] or query.get("video_id", [None])[0]
    if vid and _YT_ID_RE.match(vid):
        return vid

    # /shorts/VIDEO_ID, /embed/VIDEO_ID, /live/VIDEO_ID
    for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
        if path.startswith(prefix):
            vid = path[len(prefix):].split("/")[0]
            if _YT_ID_RE.match(vid):
                return vid

    return None


def normalize_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ── Direct video URL handling ─────────────────────────────────────────────
_DIRECT_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv"}


def _path_extension(url: str) -> str:
    path = urlparse(url).path or ""
    return os.path.splitext(path)[1].lower()


def is_direct_video_url(url: str) -> bool:
    """True for http(s) links that point directly at a video file."""
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return _path_extension(url) in _DIRECT_VIDEO_EXTENSIONS


def validate_source_url(url: str) -> tuple[str, str]:
    """Validate a user-supplied source URL.

    Returns ``(platform, canonical_url)`` where platform is ``youtube`` or
    ``direct``, or raises :class:`URLValidationError`.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise URLValidationError("Please paste a video URL.")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise URLValidationError("URL is too long.")

    # Reject anything that isn't a plain http(s) URL.
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError("URL must start with http:// or https://.")

    if not parsed.netloc:
        raise URLValidationError("That doesn't look like a valid URL.")

    video_id = parse_youtube_video_id(url)
    if video_id:
        return "youtube", normalize_youtube_url(video_id)

    if is_direct_video_url(url):
        return "direct", url

    raise URLValidationError(
        "Unsupported URL. Kryber accepts YouTube video links "
        "(youtube.com/watch?v=…, youtu.be/…, youtube.com/shorts/…) and direct "
        "video file links ending in .mp4, .webm, .mov, .m4v, .mkv or .ogv."
    )


def is_supported_url(url: str) -> bool:
    try:
        validate_source_url(url)
        return True
    except URLValidationError:
        return False


# ── Filesystem safety ───────────────────────────────────────────────────
def safe_join(root: str, *parts: str) -> str:
    """Join paths under ``root``, refusing any result that escapes it."""
    base = os.path.realpath(root)
    target = os.path.realpath(os.path.join(base, *parts))
    if os.path.commonpath([base, target]) != base:
        raise ValueError("Path traversal detected.")
    return target
