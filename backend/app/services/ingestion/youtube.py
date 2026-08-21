"""YouTube ingestion adapter using yt-dlp as a subprocess.

Design (§9 / §1): timeout, stderr capture, exit-code validation, output-file
validation, cleanup on failure, retries with exponential backoff, a polite
inter-download interval, and clear errors. No CAPTCHA / anti-bot / auth
circumvention of any kind — if YouTube refuses the request, the job fails with
a useful INGESTION_FAILED error instead of being hammered.

Optional operator session: when ``KRYBER_YTDLP_COOKIES_FILE`` points at a
Netscape-format cookies.txt the operator exported from their OWN browser, it
is passed to yt-dlp via ``--cookies``. That is the standard remedy for
YouTube's "Sign in to confirm you're not a bot" check against datacenter IPs
(e.g. GitHub Codespaces). The file is a secret: it is never committed, never
logged, and the setting is a runtime environment variable only. Unset
(default) keeps fully anonymous behavior.

JavaScript challenge: YouTube's player requires a JS runtime to solve its
``n``/signature challenges. yt-dlp enables only ``deno`` by default, so
installed runtimes are detected and passed via ``--js-runtimes`` (see
:mod:`.jsruntime`); when none is available the job fails with an actionable
error instead of a bare extraction failure.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ...config import get_settings
from ...errors import IngestionFailedError, URLValidationError
from ...utils import logging as logmod
from ...utils.process import ProcessFailure, run_command
from ...utils.validation import validate_source_url
from .base import DownloadResult, VideoMetadata, VideoSource
from .jsruntime import EJS_SETUP_HINT, js_runtime_args, resolve_js_runtimes, runtime_summary

logger = logmod.get_logger("kryber.ingestion.youtube")

# Polite global interval between downloads (across all jobs in a process).
_lock = threading.Lock()
_last_download_ts = 0.0

# YouTube bot-check / sign-in challenges (typical for datacenter IPs, e.g.
# GitHub Codespaces). Handled with a DYNAMIC hint (see _bot_check_hint) so the
# error tells the operator exactly how to fix it.
_BOT_CHECK_RE = re.compile(
    r"sign in to confirm|confirm you'?re not a bot|please sign in|requires sign-in",
    re.I,
)

# YouTube JavaScript challenge failures (EJS solver). yt-dlp reports these as
# warnings on stderr and then produces no usable formats, so the underlying
# cause is invisible without this translation.
_JS_CHALLENGE_RE = re.compile(
    r"no supported javascript runtime|"
    r"only deno is enabled by default|"
    r"n challenge solving failed|"
    r"signature solving failed|"
    r"no usable challenge solver|"
    r"challenge solver .* script|"
    r"--js-runtimes",
    re.I,
)

_FRIENDLY_ERRORS = [
    (re.compile(r"private video", re.I), "This video is private."),
    (re.compile(r"video unavailable|not available", re.I), "This video is unavailable."),
    (re.compile(r"age-restricted|age restricted", re.I), "This video is age-restricted."),
    (re.compile(r"copyright", re.I), "This video is blocked for copyright reasons."),
    (re.compile(r"region|country", re.I), "This video is not available in this region."),
    (re.compile(r"members-only|members only", re.I), "This video requires a channel membership."),
]


def _resolve_ytdlp() -> list[str]:
    settings = get_settings()
    if settings.ytdlp_binary:
        return [settings.ytdlp_binary]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _cookies_args() -> list[str]:
    """Build the ``--cookies`` argv fragment from runtime settings (or none).

    Raises a graceful, actionable :class:`IngestionFailedError`
    (code=INGESTION_FAILED, stage=ingesting) when the operator configured a
    cookie file that is not readable. This guard matters because yt-dlp
    *silently ignores a missing cookie file* — without it, a mistyped path
    would degrade to an anonymous download and fail later with a confusing
    bot-check error. The cookie CONTENTS are never read, logged, or returned.
    """
    path = (get_settings().ytdlp_cookies_file or "").strip()
    if not path:
        return []
    cookie_path = Path(path).expanduser()
    if not cookie_path.is_file():
        raise IngestionFailedError(
            f"KRYBER_YTDLP_COOKIES_FILE is set to {path}, but that file does not "
            "exist or is not readable. Export cookies.txt from your browser "
            "(e.g. the 'Get cookies.txt LOCALLY' extension, while signed into "
            "YouTube), place it on this machine outside the repository, and "
            "point KRYBER_YTDLP_COOKIES_FILE at its path, then retry."
        )
    return ["--cookies", str(cookie_path)]


def _bot_check_hint() -> str:
    if (get_settings().ytdlp_cookies_file or "").strip():
        return (
            "YouTube still requires sign-in for this video. The configured cookie "
            "file (KRYBER_YTDLP_COOKIES_FILE) may be stale or missing the YouTube "
            "session cookies — re-export cookies.txt from your local browser, "
            "update the file, and retry."
        )
    return (
        "YouTube is blocking this request with a sign-in / bot check (common for "
        "datacenter IPs such as GitHub Codespaces). Fix without committing "
        "secrets: while signed into YouTube on your local PC, export a "
        "cookies.txt file (e.g. the 'Get cookies.txt LOCALLY' extension), "
        "upload it to this machine outside the repository, and set "
        "KRYBER_YTDLP_COOKIES_FILE to its path, then retry."
    )


def _js_challenge_hint() -> str:
    """Actionable guidance for a failed YouTube JavaScript challenge."""
    enabled = resolve_js_runtimes()
    if not enabled:
        return EJS_SETUP_HINT
    return (
        "YouTube's JavaScript player challenge could not be solved even though "
        f"a runtime is enabled ({runtime_summary()}). Make sure yt-dlp and the "
        "yt-dlp-ejs solver package are up to date (pip install -U yt-dlp "
        "yt-dlp-ejs), and that the runtime is Node.js 22+ or Deno, then retry."
    )


def _friendly(message: str, stderr: str) -> str:
    if _BOT_CHECK_RE.search(stderr):
        return f"{_bot_check_hint()} ({message})"
    if _JS_CHALLENGE_RE.search(stderr):
        return f"{_js_challenge_hint()} ({message})"
    for pattern, text in _FRIENDLY_ERRORS:
        if pattern.search(stderr):
            return f"{text} ({message})"
    return message


def _is_transient(failure: ProcessFailure) -> bool:
    if failure.timed_out:
        return True
    stderr = failure.stderr_tail or ""
    # Network-level / rate-limit style failures are worth retrying politely.
    return bool(
        re.search(r"timed out|connection reset|network is unreachable|temporary failure|http error 5\d\d|rate.?limit", stderr, re.I)
    )


class YouTubeVideoSource(VideoSource):
    platform = "youtube"

    def validate_url(self, url: str) -> str:
        platform, canonical = validate_source_url(url)
        if platform != "youtube":
            raise URLValidationError("This source only accepts YouTube URLs.")
        return canonical

    def get_metadata(self, url: str) -> VideoMetadata:
        cookies = _cookies_args()  # may raise a clear INGESTION_FAILED
        js_runtimes = js_runtime_args()
        argv = _resolve_ytdlp() + [
            "--skip-download", "--dump-single-json", "--no-playlist",
            "--no-warnings", "--socket-timeout", "30",
        ] + js_runtimes + cookies + [url]
        if cookies:
            logmod.info(logger, "using runtime cookie file for yt-dlp", path=cookies[1])
        if js_runtimes:
            logmod.info(logger, "enabling yt-dlp JavaScript runtimes", runtimes=runtime_summary())
        try:
            proc = run_command(argv, timeout=get_settings().ingestion_timeout_seconds)
        except ProcessFailure as exc:
            raise IngestionFailedError(_friendly(f"Could not read video metadata: {exc}", exc.stderr_tail)) from exc
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise IngestionFailedError("Could not parse video metadata.") from exc
        return VideoMetadata(
            title=data.get("title"),
            duration=float(data.get("duration") or 0.0) or None,
            width=data.get("width"),
            height=data.get("height"),
            ext=data.get("ext", "mp4"),
        )

    def download(self, url: str, destination_dir: str) -> DownloadResult:
        settings = get_settings()
        url = self.validate_url(url)
        dest = Path(destination_dir)
        dest.mkdir(parents=True, exist_ok=True)

        metadata = VideoMetadata()
        try:
            metadata = self.get_metadata(url)
        except IngestionFailedError:
            # Metadata can fail on edge cases; proceed with the download attempt anyway.
            logmod.warning(logger, "metadata lookup failed; continuing to download")

        # Build argv first so a misconfigured cookie file fails fast,
        # before any polite pacing sleep.
        template = str(dest / "source.%(ext)s")
        # Point yt-dlp at our ffmpeg so video+audio streams can be merged to mp4.
        from ...utils.ffmpeg import find_ffmpeg

        cookies = _cookies_args()  # may raise a clear INGESTION_FAILED
        js_runtimes = js_runtime_args()
        argv = _resolve_ytdlp() + [
            "-f", settings.ytdlp_format,
            "--merge-output-format", "mp4",
            "--ffmpeg-location", os.path.dirname(find_ffmpeg()),
            "--no-playlist",
            "--no-warnings",
            "--socket-timeout", "30",
            "--retries", "1",
            "--fragment-retries", "1",
            "-o", template,
        ] + js_runtimes + cookies
        if settings.ytdlp_player_clients:
            argv += ["--extractor-args", f"youtube:player_client={settings.ytdlp_player_clients}"]
        if cookies:
            logmod.info(logger, "using runtime cookie file for yt-dlp", path=cookies[1])
        if js_runtimes:
            logmod.info(logger, "enabling yt-dlp JavaScript runtimes", runtimes=runtime_summary())
        argv.append(url)

        # Polite pacing: never fire back-to-back downloads.
        with _lock:
            global _last_download_ts
            wait = settings.ingestion_min_interval_seconds - (time.monotonic() - _last_download_ts)
            if wait > 0:
                time.sleep(wait)
            _last_download_ts = time.monotonic()

        last_error: ProcessFailure | None = None
        for attempt in range(1, settings.ingestion_retries + 1):
            try:
                run_command(argv, timeout=settings.ingestion_timeout_seconds)
                last_error = None
                break
            except ProcessFailure as exc:
                last_error = exc
                if not _is_transient(exc) or attempt == settings.ingestion_retries:
                    break
                backoff = 2 ** attempt
                logmod.warning(logger, "download attempt failed; retrying", attempt=attempt, backoff_s=backoff)
                time.sleep(backoff)

        if last_error is not None:
            self.cleanup(destination_dir)
            raise IngestionFailedError(
                _friendly(f"Download failed: {last_error}", last_error.stderr_tail)
            ) from last_error

        path = self._locate_output(dest)
        if path is None:
            self.cleanup(destination_dir)
            raise IngestionFailedError("Download finished but no output file was produced.")

        return DownloadResult(path=path, metadata=metadata)

    def _locate_output(self, dest: Path) -> str | None:
        # Prefer the merged mp4; otherwise the largest non-empty source file.
        merged = dest / "source.mp4"
        if merged.is_file() and merged.stat().st_size > 0:
            return str(merged)
        candidates = [c for c in dest.glob("source.*") if c.is_file() and c.stat().st_size > 0]
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        return str(candidates[0])

    def cleanup(self, destination_dir: str) -> None:
        try:
            shutil.rmtree(destination_dir, ignore_errors=True)
        except Exception:  # best-effort
            pass
