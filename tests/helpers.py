"""Shared test helpers."""
from __future__ import annotations

import subprocess

from app.utils.ffmpeg import find_ffmpeg


def make_test_video(path, duration: float = 6.0, width: int = 640, height: int = 360) -> str:
    """Generate a synthetic H.264+AAC video with a tone track (no network)."""
    subprocess.run(
        [
            find_ffmpeg(),
            "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return str(path)
