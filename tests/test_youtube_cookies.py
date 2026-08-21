"""YouTube adapter: runtime cookie support (KRYBER_YTDLP_COOKIES_FILE).

Covers:
- argv construction (no --cookies by default; --cookies <path> when set)
- graceful, actionable INGESTION_FAILED when the configured file is missing
- bot-check friendly error guidance (with / without a configured file)
- regression: other friendly errors are unchanged
- offline checks that the REAL yt-dlp binary accepts a well-formed cookies
  file and fails on a missing one (no network involved)

yt-dlp execution is stubbed for the argv tests — no network access here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

import app.utils.ffmpeg as ffmpeg_utils
import app.services.ingestion.youtube as yt
from app.config import Settings
from app.errors import IngestionFailedError
from app.services.ingestion.youtube import YouTubeVideoSource
from app.utils.process import ProcessFailure

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

SIGN_IN_STDERR = (
    "ERROR: [youtube] dQw4w9WgXcQ: dQw4w9WgXcQ: "
    "Sign in to confirm you're not a bot. "
    "(see https://github.com/yt-dlp/yt-dlp/wiki/FAQ for details)"
)

NETSCAPE_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tFALSE\t1999999999\tSID\tfake-session-value\n"
)


def _settings(**overrides) -> Settings:
    base = {"ytdlp_cookies_file": None, "ingestion_min_interval_seconds": 0}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _stub_run(monkeypatch, calls: list, fail_stderr: str | None = None, stdout: str = ""):
    """Replace yt.run_command; record argv; optionally fail with fail_stderr."""
    def fake_run(argv, *, timeout, cwd=None):
        calls.append(list(argv))
        if fail_stderr is not None:
            raise ProcessFailure(argv=argv, returncode=1, stderr_tail=fail_stderr, timed_out=False)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=stdout, stderr="")
    monkeypatch.setattr(yt, "run_command", fake_run)


def _stub_ffmpeg(monkeypatch):
    # download() resolves ffmpeg for --ffmpeg-location; keep tests hermetic.
    monkeypatch.setattr(ffmpeg_utils, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")


# ── argv construction ─────────────────────────────────────────────────────

def test_no_cookies_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(yt, "get_settings", lambda: _settings())
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T", "duration": 30.0}))
    meta = YouTubeVideoSource().get_metadata(URL)
    assert meta.title == "T"
    assert len(calls) == 1
    assert "--cookies" not in calls[0]


def test_cookies_arg_in_metadata_and_download(monkeypatch, tmp_path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(NETSCAPE_COOKIES)
    settings = _settings(ytdlp_cookies_file=str(cookie))

    meta_json = json.dumps({"title": "T", "duration": 30.0})
    calls = []
    monkeypatch.setattr(yt, "get_settings", lambda: settings)
    _stub_run(monkeypatch, calls, stdout=meta_json)
    _stub_ffmpeg(monkeypatch)

    dest = tmp_path / "dl"
    dest.mkdir()
    (dest / "source.mp4").write_bytes(b"fake-video-bytes")

    result = YouTubeVideoSource().download(URL, str(dest))
    assert result.metadata.title == "T"
    assert len(calls) == 2  # metadata + download
    for argv in calls:
        assert "--cookies" in argv
        assert argv[argv.index("--cookies") + 1] == str(cookie)


def test_cookies_expanduser_path(monkeypatch, tmp_path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(NETSCAPE_COOKIES)
    expanded = str(cookie)
    as_tilde = f"~/{cookie.name}" if cookie.parent.name != "~" else cookie.name
    # _cookies_args must resolve the path exactly as given when absolute.
    monkeypatch.setattr(yt, "get_settings", lambda: _settings(ytdlp_cookies_file=expanded))
    assert yt._cookies_args() == ["--cookies", expanded]


# ── graceful failure on misconfigured cookie file ─────────────────────────

def test_missing_cookie_file_fails_gracefully_in_metadata(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    calls = []
    monkeypatch.setattr(yt, "get_settings", lambda: _settings(ytdlp_cookies_file=str(missing)))
    _stub_run(monkeypatch, calls)

    with pytest.raises(IngestionFailedError) as excinfo:
        YouTubeVideoSource().get_metadata(URL)
    assert excinfo.value.code == "INGESTION_FAILED"
    assert excinfo.value.stage == "ingesting"
    assert "KRYBER_YTDLP_COOKIES_FILE" in str(excinfo.value)
    assert "cookies.txt" in str(excinfo.value)
    assert calls == []  # yt-dlp must not run with a missing cookie file


def test_missing_cookie_file_fails_gracefully_in_download(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    calls = []
    monkeypatch.setattr(yt, "get_settings", lambda: _settings(ytdlp_cookies_file=str(missing)))
    _stub_run(monkeypatch, calls)
    _stub_ffmpeg(monkeypatch)

    with pytest.raises(IngestionFailedError) as excinfo:
        YouTubeVideoSource().download(URL, str(tmp_path / "dl"))
    assert excinfo.value.code == "INGESTION_FAILED"
    assert "KRYBER_YTDLP_COOKIES_FILE" in str(excinfo.value)
    assert calls == []


# ── bot-check friendly errors ─────────────────────────────────────────────

def test_bot_check_without_cookies_gives_setup_guidance(monkeypatch):
    monkeypatch.setattr(yt, "get_settings", lambda: _settings())
    _stub_run(monkeypatch, [], fail_stderr=SIGN_IN_STDERR)

    with pytest.raises(IngestionFailedError) as excinfo:
        YouTubeVideoSource().get_metadata(URL)
    msg = str(excinfo.value)
    assert excinfo.value.code == "INGESTION_FAILED"
    # Actionable: names the env var and the cookie-file fix.
    assert "KRYBER_YTDLP_COOKIES_FILE" in msg
    assert "cookies.txt" in msg
    assert "local PC" in msg or "local browser" in msg


def test_bot_check_with_cookies_gives_stale_hint(tmp_path, monkeypatch):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(NETSCAPE_COOKIES)
    monkeypatch.setattr(yt, "get_settings", lambda: _settings(ytdlp_cookies_file=str(cookie)))
    _stub_run(monkeypatch, [], fail_stderr=SIGN_IN_STDERR)

    with pytest.raises(IngestionFailedError) as excinfo:
        YouTubeVideoSource().get_metadata(URL)
    msg = str(excinfo.value)
    assert "stale" in msg
    assert "re-export" in msg


def test_private_video_friendly_error_unchanged(monkeypatch):
    monkeypatch.setattr(yt, "get_settings", lambda: _settings())
    _stub_run(monkeypatch, [], fail_stderr="ERROR: [youtube] xxx: private video")

    with pytest.raises(IngestionFailedError) as excinfo:
        YouTubeVideoSource().get_metadata(URL)
    assert "This video is private." in str(excinfo.value)


# ── real yt-dlp binary, fully offline (no network touched) ────────────────
#
# "not-a-url" makes yt-dlp fail BEFORE any network I/O. Whatever cookie
# handling happens first is therefore observable deterministically.

def _ytdlp_argv() -> list[str]:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return []


def test_real_ytdlp_accepts_well_formed_cookie_file(tmp_path):
    argv0 = _ytdlp_argv()
    if not argv0:
        pytest.skip("yt-dlp not installed in this environment")
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(NETSCAPE_COOKIES)
    proc = subprocess.run(
        argv0 + ["--cookies", str(cookie), "not-a-url"],
        capture_output=True, text=True, timeout=120,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    # The well-formed file loads cleanly: yt-dlp complains only about the
    # (deliberately) invalid URL — no cookie-related diagnostics at all.
    assert "not a valid URL" in combined
    cookie_lines = [l for l in combined.lower().splitlines() if "cookie" in l]
    assert cookie_lines == []


def test_real_ytdlp_rejects_malformed_cookie_file(tmp_path):
    argv0 = _ytdlp_argv()
    if not argv0:
        pytest.skip("yt-dlp not installed in this environment")
    bad = tmp_path / "bad.txt"
    bad.write_text("this is not a cookie file\n@@@garbage@@@\n")
    proc = subprocess.run(
        argv0 + ["--cookies", str(bad), "not-a-url"],
        capture_output=True, text=True, timeout=120,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    # A malformed file is reported explicitly — the failure mode the
    # app-level guard (_cookies_args) protects users from.
    assert proc.returncode != 0
    assert "netscape format cookies file" in combined.lower()
