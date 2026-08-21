"""VideoSource abstraction.

Implemented by the YouTube adapter in Phase 3. Design constraints (spec §9):
retries with exponential backoff, rate limiting, timeouts, download
validation, duplicate detection, caching, cleanup — and clear errors instead
of hammering a platform. No CAPTCHA / anti-bot circumvention.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class VideoMetadata:
    title: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    ext: str = "mp4"


@dataclass
class DownloadResult:
    path: str
    metadata: VideoMetadata = field(default_factory=VideoMetadata)


class VideoSource(abc.ABC):
    """One pluggable way to fetch a source video."""

    platform: str = "unknown"

    @abc.abstractmethod
    def validate_url(self, url: str) -> str:
        """Normalize/validate; return a canonical URL or raise URLValidationError."""

    @abc.abstractmethod
    def get_metadata(self, url: str) -> VideoMetadata: ...

    @abc.abstractmethod
    def download(self, url: str, destination_dir: str) -> DownloadResult: ...

    @abc.abstractmethod
    def cleanup(self, destination_dir: str) -> None: ...
