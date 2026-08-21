"""JavaScript runtime detection for yt-dlp's YouTube challenge solver.

Why this exists
---------------
YouTube protects its player with JavaScript challenges (``n`` / signature).
Modern yt-dlp solves them with an "EJS" solver script executed by a real
JavaScript runtime. Crucially, **yt-dlp only enables ``deno`` by default** —
on a machine that has Node.js but not Deno, no challenge provider is available
at all, so yt-dlp silently falls back to JS-less clients and formats go
missing or extraction fails outright.

This module detects the JavaScript runtimes actually installed and turns them
into ``--js-runtimes RUNTIME[:PATH]`` arguments, so an environment with
Node.js 22+ (GitHub Codespaces, the project's Docker image) just works.

Configuration: ``KRYBER_YTDLP_JS_RUNTIMES``
  * unset (default) — auto-detect every supported runtime on PATH.
  * ``node`` / ``node,deno`` — enable exactly these, in this order.
  * ``node:/usr/local/bin/node`` — pin an explicit binary or directory.
  * ``none`` — disable, leaving yt-dlp's own default behavior untouched.

The solver *scripts* come from the ``yt-dlp-ejs`` package (a declared
dependency), so no script download at runtime is required.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ...config import get_settings
from ...utils import logging as logmod

logger = logmod.get_logger("kryber.ingestion.jsruntime")

# yt-dlp's supported runtime names mapped to the executable to look for, in
# yt-dlp's own priority order (highest first).
SUPPORTED_RUNTIMES: dict[str, str] = {
    "deno": "deno",
    "node": "node",
    "quickjs": "qjs",
    "bun": "bun",
}

# yt-dlp's NodeJsRuntime.MIN_SUPPORTED_VERSION. Node 22 is the first release
# with the stable permission model the solver relies on.
NODE_MIN_MAJOR = 22

# Sentinel value that disables Kryber's runtime handling entirely.
DISABLED_VALUES = {"none", "off", "false", "disabled"}

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

EJS_SETUP_HINT = (
    "YouTube requires a JavaScript runtime to solve its player challenge. "
    "Install Node.js 22 or newer (or Deno) so yt-dlp can run the EJS solver, "
    "then retry. yt-dlp only enables 'deno' by default, so Kryber detects "
    "installed runtimes and passes --js-runtimes automatically; set "
    "KRYBER_YTDLP_JS_RUNTIMES (e.g. 'node' or 'node:/usr/local/bin/node') to "
    "choose one explicitly."
)


@dataclass(frozen=True)
class JsRuntimeSpec:
    """A runtime yt-dlp should enable, optionally pinned to a path."""

    name: str
    path: str | None = None

    def to_arg(self) -> str:
        return f"{self.name}:{self.path}" if self.path else self.name


def parse_runtime_setting(raw: str) -> list[JsRuntimeSpec]:
    """Parse ``KRYBER_YTDLP_JS_RUNTIMES`` into specs.

    Format: comma-separated ``name`` or ``name:path`` entries. Unknown names
    are skipped with a warning rather than failing the job — yt-dlp would
    reject them outright, and a typo shouldn't take ingestion down.
    """
    specs: list[JsRuntimeSpec] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, _, path = entry.partition(":")
        name = name.strip().lower()
        path = path.strip() or None
        if name not in SUPPORTED_RUNTIMES:
            logmod.warning(
                logger,
                "ignoring unsupported JavaScript runtime in KRYBER_YTDLP_JS_RUNTIMES",
                runtime=name,
                supported=",".join(SUPPORTED_RUNTIMES),
            )
            continue
        specs.append(JsRuntimeSpec(name=name, path=path))
    return specs


def _node_major(binary: str) -> int | None:
    """Return Node's major version, or None if it cannot be determined."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION_RE.search(f"{proc.stdout} {proc.stderr}")
    return int(match.group(1)) if match else None


@lru_cache(maxsize=1)
def detect_js_runtimes() -> tuple[JsRuntimeSpec, ...]:
    """Detect supported JavaScript runtimes available on PATH.

    Cached: this shells out to ``node --version`` and the answer cannot change
    within a process lifetime.
    """
    found: list[JsRuntimeSpec] = []
    for name, binary in SUPPORTED_RUNTIMES.items():
        path = shutil.which(binary)
        if not path:
            continue
        if name == "node":
            major = _node_major(path)
            if major is not None and major < NODE_MIN_MAJOR:
                logmod.warning(
                    logger,
                    "ignoring Node.js older than the version yt-dlp requires",
                    path=path,
                    major=major,
                    required=NODE_MIN_MAJOR,
                )
                continue
        found.append(JsRuntimeSpec(name=name, path=path))
    return tuple(found)


def resolve_js_runtimes() -> tuple[JsRuntimeSpec, ...]:
    """Runtimes to enable: explicit configuration, else auto-detection."""
    configured = (get_settings().ytdlp_js_runtimes or "").strip()
    if configured.lower() in DISABLED_VALUES:
        return ()
    if configured:
        return tuple(parse_runtime_setting(configured))
    return detect_js_runtimes()


def js_runtime_args() -> list[str]:
    """Build the ``--js-runtimes`` argv fragment for yt-dlp.

    Empty when nothing is available, which leaves yt-dlp's defaults untouched;
    the resulting extraction failure is translated into an actionable error by
    the YouTube adapter.
    """
    args: list[str] = []
    for spec in resolve_js_runtimes():
        args += ["--js-runtimes", spec.to_arg()]
    return args


def runtime_summary() -> str:
    """Human-readable list of enabled runtimes, for logs and error messages."""
    specs = resolve_js_runtimes()
    if not specs:
        return "none"
    return ", ".join(
        f"{s.name} ({Path(s.path).name})" if s.path else s.name for s in specs
    )
