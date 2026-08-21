"""yt-dlp JavaScript runtime configuration (KRYBER_YTDLP_JS_RUNTIMES).

YouTube's player challenge is solved by yt-dlp's EJS solver, which needs a
JavaScript runtime. yt-dlp enables only "deno" by default, so a host with
Node.js and no Deno silently loses formats. These tests pin:

- parsing of the KRYBER_YTDLP_JS_RUNTIMES setting (names, paths, "none")
- auto-detection of installed runtimes, including the Node 22 minimum
- --js-runtimes being passed to BOTH the metadata and download calls
- graceful, actionable errors when the challenge cannot be solved
- coexistence with the already-shipped --cookies mechanism

yt-dlp execution is stubbed for the argv tests — no network access here.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

import app.services.ingestion.jsruntime as jsrt
import app.services.ingestion.youtube as yt
import app.utils.ffmpeg as ffmpeg_utils
from app.config import Settings
from app.errors import IngestionFailedError
from app.services.ingestion.jsruntime import (
    NODE_MIN_MAJOR,
    JsRuntimeSpec,
    detect_js_runtimes,
    js_runtime_args,
    parse_runtime_setting,
    resolve_js_runtimes,
    runtime_summary,
)
from app.services.ingestion.youtube import YouTubeVideoSource
from app.utils.process import ProcessFailure

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Real yt-dlp stderr for a host where no JS runtime is enabled.
NO_RUNTIME_STDERR = (
    "WARNING: [youtube] No supported JavaScript runtime could be found. "
    "Only deno is enabled by default; to use another runtime add "
    "--js-runtimes RUNTIME[:PATH] to your command/config. "
    "YouTube extraction without a JS runtime has been deprecated, and some "
    "formats may be missing."
)

SOLVER_FAILED_STDERR = (
    "WARNING: [youtube] dQw4w9WgXcQ: n challenge solving failed: Some formats "
    "may be missing. Ensure you have a supported JavaScript runtime and "
    "challenge solver script distribution installed."
)


def _settings(**overrides) -> Settings:
    base = {
        "ytdlp_cookies_file": None,
        "ytdlp_js_runtimes": "",
        "ingestion_min_interval_seconds": 0,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _use_settings(monkeypatch, **overrides):
    settings = _settings(**overrides)
    monkeypatch.setattr(yt, "get_settings", lambda: settings)
    monkeypatch.setattr(jsrt, "get_settings", lambda: settings)
    return settings


def _stub_run(monkeypatch, calls: list, fail_stderr: str | None = None, stdout: str = ""):
    def fake_run(argv, *, timeout, cwd=None):
        calls.append(list(argv))
        if fail_stderr is not None:
            raise ProcessFailure(argv=argv, returncode=1, stderr_tail=fail_stderr, timed_out=False)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(yt, "run_command", fake_run)


def _stub_ffmpeg(monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")


def _no_detection(monkeypatch):
    """Pin auto-detection to nothing so tests don't depend on the host."""
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: ())


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    detect_js_runtimes.cache_clear()
    yield
    detect_js_runtimes.cache_clear()


# ── setting parsing ───────────────────────────────────────────────────────

def test_parses_single_runtime_name():
    assert parse_runtime_setting("node") == [JsRuntimeSpec(name="node", path=None)]


def test_parses_multiple_runtimes_preserving_order():
    assert parse_runtime_setting("node,deno") == [
        JsRuntimeSpec(name="node"),
        JsRuntimeSpec(name="deno"),
    ]


def test_parses_runtime_with_explicit_path():
    assert parse_runtime_setting("node:/usr/local/bin/node") == [
        JsRuntimeSpec(name="node", path="/usr/local/bin/node")
    ]


def test_parsing_is_whitespace_and_case_tolerant():
    assert parse_runtime_setting(" Node , DENO ") == [
        JsRuntimeSpec(name="node"),
        JsRuntimeSpec(name="deno"),
    ]


def test_unsupported_runtime_is_skipped_not_fatal():
    # A typo must not take ingestion down; yt-dlp would reject the argument.
    assert parse_runtime_setting("nodejs,node") == [JsRuntimeSpec(name="node")]


def test_spec_renders_yt_dlp_argument():
    assert JsRuntimeSpec("node").to_arg() == "node"
    assert JsRuntimeSpec("node", "/opt/node").to_arg() == "node:/opt/node"


# ── resolution ────────────────────────────────────────────────────────────

def test_explicit_setting_overrides_detection(monkeypatch):
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("deno", "/usr/bin/deno"),))
    _use_settings(monkeypatch, ytdlp_js_runtimes="node")

    assert resolve_js_runtimes() == (JsRuntimeSpec("node"),)


def test_unset_setting_falls_back_to_detection(monkeypatch):
    detected = (JsRuntimeSpec("node", "/usr/local/bin/node"),)
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: detected)
    _use_settings(monkeypatch, ytdlp_js_runtimes="")

    assert resolve_js_runtimes() == detected


@pytest.mark.parametrize("value", ["none", "None", "off", "disabled"])
def test_none_disables_runtime_handling(monkeypatch, value):
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node"),))
    _use_settings(monkeypatch, ytdlp_js_runtimes=value)

    assert resolve_js_runtimes() == ()
    assert js_runtime_args() == []


def test_runtime_summary_is_readable(monkeypatch):
    monkeypatch.setattr(
        jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node", "/usr/local/bin/node"),)
    )
    _use_settings(monkeypatch)

    assert runtime_summary() == "node (node)"


def test_runtime_summary_when_nothing_available(monkeypatch):
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)

    assert runtime_summary() == "none"


# ── detection ─────────────────────────────────────────────────────────────

def test_detects_node_on_path(monkeypatch):
    monkeypatch.setattr(
        jsrt.shutil, "which", lambda b: "/usr/local/bin/node" if b == "node" else None
    )
    monkeypatch.setattr(jsrt, "_node_major", lambda path: NODE_MIN_MAJOR)

    assert detect_js_runtimes() == (JsRuntimeSpec("node", "/usr/local/bin/node"),)


def test_ignores_node_older_than_yt_dlp_minimum(monkeypatch):
    monkeypatch.setattr(
        jsrt.shutil, "which", lambda b: "/usr/local/bin/node" if b == "node" else None
    )
    monkeypatch.setattr(jsrt, "_node_major", lambda path: NODE_MIN_MAJOR - 2)

    assert detect_js_runtimes() == ()


def test_detection_follows_yt_dlp_priority_order(monkeypatch):
    paths = {"deno": "/usr/bin/deno", "node": "/usr/bin/node"}
    monkeypatch.setattr(jsrt.shutil, "which", lambda b: paths.get(b))
    monkeypatch.setattr(jsrt, "_node_major", lambda path: NODE_MIN_MAJOR)

    # deno outranks node in yt-dlp's own ordering.
    assert [s.name for s in detect_js_runtimes()] == ["deno", "node"]


def test_detects_nothing_when_no_runtime_installed(monkeypatch):
    monkeypatch.setattr(jsrt.shutil, "which", lambda b: None)

    assert detect_js_runtimes() == ()


def test_node_version_probe_handles_missing_binary():
    assert jsrt._node_major("/nonexistent/node-binary") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_real_node_version_is_detected():
    """Sanity check against the actual runtime on this machine."""
    major = jsrt._node_major(shutil.which("node"))
    assert isinstance(major, int) and major > 0


# ── argv wiring ───────────────────────────────────────────────────────────

def test_js_runtimes_passed_to_metadata(monkeypatch):
    calls = []
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node", "/usr/local/bin/node"),))
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T", "duration": 30.0}))

    YouTubeVideoSource().get_metadata(URL)

    argv = calls[0]
    assert "--js-runtimes" in argv
    assert argv[argv.index("--js-runtimes") + 1] == "node:/usr/local/bin/node"


def test_js_runtimes_passed_to_download(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node"),))
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T", "duration": 30.0}))
    _stub_ffmpeg(monkeypatch)
    (tmp_path / "source.mp4").write_bytes(b"data")

    YouTubeVideoSource().download(URL, str(tmp_path))

    # Both the metadata call and the download call must carry the runtime.
    assert len(calls) == 2
    for argv in calls:
        assert "--js-runtimes" in argv
        assert argv[argv.index("--js-runtimes") + 1] == "node"


def test_multiple_runtimes_each_get_their_own_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(
        jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("deno"), JsRuntimeSpec("node"))
    )
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T"}))

    YouTubeVideoSource().get_metadata(URL)

    argv = calls[0]
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--js-runtimes"] == ["deno", "node"]


def test_no_js_runtimes_flag_when_none_available(monkeypatch):
    calls = []
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T"}))

    YouTubeVideoSource().get_metadata(URL)

    assert "--js-runtimes" not in calls[0]


def test_js_runtimes_coexist_with_cookies(monkeypatch, tmp_path):
    """The already-merged cookie mechanism must be unaffected."""
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n")
    calls = []
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node"),))
    _use_settings(monkeypatch, ytdlp_cookies_file=str(cookie))
    _stub_run(monkeypatch, calls, stdout=json.dumps({"title": "T"}))

    YouTubeVideoSource().get_metadata(URL)

    argv = calls[0]
    assert argv[argv.index("--cookies") + 1] == str(cookie)
    assert argv[argv.index("--js-runtimes") + 1] == "node"
    assert argv[-1] == URL  # the URL stays last


# ── actionable errors ─────────────────────────────────────────────────────

def test_missing_runtime_error_is_actionable(monkeypatch):
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, [], fail_stderr=NO_RUNTIME_STDERR)

    with pytest.raises(IngestionFailedError) as exc:
        YouTubeVideoSource().get_metadata(URL)

    message = str(exc.value)
    assert "JavaScript runtime" in message
    assert "Node.js 22" in message
    assert "KRYBER_YTDLP_JS_RUNTIMES" in message


def test_solver_failure_with_runtime_present_gives_update_hint(monkeypatch):
    monkeypatch.setattr(jsrt, "detect_js_runtimes", lambda: (JsRuntimeSpec("node", "/usr/local/bin/node"),))
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, [], fail_stderr=SOLVER_FAILED_STDERR)

    with pytest.raises(IngestionFailedError) as exc:
        YouTubeVideoSource().get_metadata(URL)

    message = str(exc.value)
    assert "yt-dlp-ejs" in message
    assert "node" in message


def test_js_challenge_error_surfaces_on_download(monkeypatch, tmp_path):
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, [], fail_stderr=NO_RUNTIME_STDERR)
    _stub_ffmpeg(monkeypatch)

    with pytest.raises(IngestionFailedError) as exc:
        YouTubeVideoSource().download(URL, str(tmp_path / "work"))

    assert "JavaScript runtime" in str(exc.value)


def test_bot_check_still_takes_priority_over_js_hint(monkeypatch):
    """A sign-in challenge is the more specific diagnosis; keep PR #1 behavior."""
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)
    _stub_run(
        monkeypatch,
        [],
        fail_stderr="ERROR: Sign in to confirm you're not a bot. --js-runtimes",
    )

    with pytest.raises(IngestionFailedError) as exc:
        YouTubeVideoSource().get_metadata(URL)

    assert "cookies.txt" in str(exc.value)


def test_unrelated_errors_are_not_misreported_as_js_failures(monkeypatch):
    _no_detection(monkeypatch)
    _use_settings(monkeypatch)
    _stub_run(monkeypatch, [], fail_stderr="ERROR: Private video. Sign in if you've been granted access")

    with pytest.raises(IngestionFailedError) as exc:
        YouTubeVideoSource().get_metadata(URL)

    assert "JavaScript runtime" not in str(exc.value)


# ── dependency ────────────────────────────────────────────────────────────

def test_ejs_solver_package_is_installed_and_loadable():
    """yt-dlp-ejs supplies the solver scripts; without it yt-dlp must fetch them."""
    yt_dlp_ejs = pytest.importorskip("yt_dlp_ejs")
    from yt_dlp_ejs.yt import solver

    assert tuple(int(p) for p in yt_dlp_ejs.version.split(".")[:2]) >= (0, 8)
    assert solver.core().strip()
    assert solver.lib().strip()
