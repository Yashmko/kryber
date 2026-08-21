"""Direct video-file URL ingestion adapter.

Lets Kryber ingest any publicly reachable video file (.mp4/.webm/.mov/.m4v/
.mkv/.ogv) — your own CDN, S3-compatible presigned URL, archive.org, etc. —
without going through a platform extractor.

Downloads via curl (a standard HTTP client, so no Python-TLS fingerprint
issues with CDNs that throttle the urllib/httpx stack), then falls back to
httpx. Streams to disk with a size cap, timeouts and redirect handling.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import httpx

from ...config import get_settings
from ...errors import IngestionFailedError, URLValidationError
from ...utils.validation import validate_source_url
from .base import DownloadResult, VideoMetadata, VideoSource

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Kryber/1.0"
)

_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv"}


def _path_extension(url: str) -> str:
    from urllib.parse import urlparse

    path = urlparse(url).path or ""
    return os.path.splitext(path)[1].lower()


class DirectVideoSource(VideoSource):
    platform = "direct"

    def validate_url(self, url: str) -> str:
        platform, canonical = validate_source_url(url)
        if platform != "direct":
            raise URLValidationError("This source only accepts direct video file URLs.")
        return canonical

    def get_metadata(self, url: str) -> VideoMetadata:
        # Metadata is derived from the downloaded file (ffprobe) after download.
        return VideoMetadata()

    def download(self, url: str, destination_dir: str) -> DownloadResult:
        settings = get_settings()
        url = self.validate_url(url)
        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        ext = _path_extension(url) or ".mp4"
        out = dest / f"source{ext}"

        curl = shutil.which("curl")
        if curl:
            self._download_curl(curl, url, str(out), settings)
        else:
            self._download_httpx(url, out, settings)

        if not out.is_file() or out.stat().st_size <= 0:
            out.unlink(missing_ok=True)
            raise IngestionFailedError("Direct download produced no data.")

        return DownloadResult(path=str(out), metadata=VideoMetadata(ext=ext.lstrip(".")))

    # ── curl path (preferred) ────────────────────────────────────────────
    def _download_curl(self, curl: str, url: str, out: str, settings) -> None:
        argv = [
            curl,
            "-sS",                       # silent, but show errors
            "-L",                        # follow redirects
            "--fail",                    # non-zero exit on HTTP errors
            "--retry", "2",
            "--retry-delay", "2",
            "--connect-timeout", "30",
            "--max-time", str(settings.ingestion_timeout_seconds),
            "--max-filesize", str(settings.direct_max_size_bytes),
            "-A", _USER_AGENT,
            "-o", out,
            url,
        ]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=settings.ingestion_timeout_seconds + 60)
        if proc.returncode != 0:
            if os.path.exists(out):
                os.remove(out)
            detail = (proc.stderr or "").strip().splitlines()
            tail = " | ".join(detail[-3:]) if detail else f"curl exit {proc.returncode}"
            raise IngestionFailedError(f"Direct download failed: {tail}")

    # ── httpx fallback ───────────────────────────────────────────────────
    def _download_httpx(self, url: str, out: Path, settings) -> None:
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=60.0, pool=30.0)
        headers = {"User-Agent": _USER_AGENT}
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout, headers=headers) as resp:
                if resp.status_code != 200:
                    raise IngestionFailedError(f"Direct download failed (HTTP {resp.status_code}).")
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > settings.direct_max_size_bytes:
                    raise IngestionFailedError(
                        f"Video is larger than the {settings.direct_max_size_bytes // (1024**3)} GB limit."
                    )
                written = 0
                with open(out, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        written += len(chunk)
                        if written > settings.direct_max_size_bytes:
                            f.close()
                            out.unlink(missing_ok=True)
                            raise IngestionFailedError(
                                f"Video is larger than the {settings.direct_max_size_bytes // (1024**3)} GB limit."
                            )
                        f.write(chunk)
        except IngestionFailedError:
            raise
        except httpx.HTTPError as exc:
            out.unlink(missing_ok=True)
            raise IngestionFailedError(f"Direct download failed: {exc}") from exc

    def cleanup(self, destination_dir: str) -> None:
        try:
            shutil.rmtree(destination_dir, ignore_errors=True)
        except Exception:
            pass
