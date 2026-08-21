"""Subprocess helpers with timeout, stderr capture and clear errors.

Every external tool (yt-dlp, ffmpeg, ffprobe) runs through here so timeouts
and non-zero exits are surfaced as typed errors with the offending output —
never swallowed.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ProcessFailure(Exception):
    """A subprocess failed or timed out."""

    argv: list[str]
    returncode: int | None
    stderr_tail: str
    timed_out: bool

    def __str__(self) -> str:
        if self.timed_out:
            return f"Command timed out: {' '.join(self.argv[:3])}..."
        return (
            f"Command failed (exit {self.returncode}): {' '.join(self.argv[:3])}... "
            f"→ {self.stderr_tail}"
        )


def tail(stderr: str, lines: int = 12) -> str:
    parts = [l for l in (stderr or "").splitlines() if l.strip()]
    return " | ".join(parts[-lines:])


def run_command(
    argv: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, raising :class:`ProcessFailure` on timeout / non-zero exit."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcessFailure(
            argv=argv,
            returncode=None,
            stderr_tail=(exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            timed_out=True,
        ) from exc
    except FileNotFoundError as exc:
        raise ProcessFailure(
            argv=argv, returncode=None, stderr_tail=f"binary not found: {argv[0]}", timed_out=False
        ) from exc

    if proc.returncode != 0:
        raise ProcessFailure(
            argv=argv,
            returncode=proc.returncode,
            stderr_tail=tail(proc.stderr),
            timed_out=False,
        )
    return proc
