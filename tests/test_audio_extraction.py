"""FFmpeg audio extraction (§11)."""
from __future__ import annotations

import os

from app.utils.ffmpeg import extract_audio, probe
from tests.helpers import make_test_video


def test_extract_audio(tmp_path):
    src = make_test_video(tmp_path / "src.mp4", duration=4)
    wav = tmp_path / "audio.wav"
    extract_audio(src, str(wav))
    assert os.path.isfile(wav)
    assert os.path.getsize(wav) > 0
    info = probe(str(wav))
    assert info.duration > 0
