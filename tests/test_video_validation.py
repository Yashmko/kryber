"""Post-download video validation (§10)."""
from __future__ import annotations

import pytest

from app.errors import IngestionFailedError
from app.services.ingestion.validation import validate_video_file
from tests.helpers import make_test_video


def test_rejects_missing_file(tmp_path):
    with pytest.raises(IngestionFailedError):
        validate_video_file(str(tmp_path / "nope.mp4"))


def test_rejects_empty_file(tmp_path):
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    with pytest.raises(IngestionFailedError):
        validate_video_file(str(p))


def test_rejects_garbage_file(tmp_path):
    p = tmp_path / "garbage.mp4"
    p.write_bytes(b"not a video at all" * 100)
    with pytest.raises(IngestionFailedError):
        validate_video_file(str(p))


def test_accepts_valid_video(tmp_path):
    src = make_test_video(tmp_path / "ok.mp4", duration=3)
    info = validate_video_file(src)
    assert info.duration > 0
    assert info.has_video
    assert info.has_audio
    assert info.size > 0


def test_rejects_video_without_audio(tmp_path):
    import subprocess
    from app.utils.ffmpeg import find_ffmpeg

    p = tmp_path / "noaudio.mp4"
    subprocess.run(
        [find_ffmpeg(), "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
        capture_output=True, check=True,
    )
    with pytest.raises(IngestionFailedError):
        validate_video_file(str(p))
