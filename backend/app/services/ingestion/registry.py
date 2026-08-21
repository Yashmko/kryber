"""Maps a validated platform → VideoSource implementation."""
from __future__ import annotations

from ...errors import IngestionFailedError
from .base import VideoSource
from .direct import DirectVideoSource
from .youtube import YouTubeVideoSource

_SOURCES: dict[str, type[VideoSource]] = {
    "youtube": YouTubeVideoSource,
    "direct": DirectVideoSource,
}


def get_source(platform: str) -> VideoSource:
    cls = _SOURCES.get(platform)
    if cls is None:
        raise IngestionFailedError(f"No ingestion adapter for platform {platform!r}.")
    return cls()
