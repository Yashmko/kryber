"""Direct video URL ingestion (no external network — local HTTP server)."""
from __future__ import annotations

import functools
import http.server
import os
import threading

from app.services.ingestion.direct import DirectVideoSource
from tests.helpers import make_test_video


def test_direct_source_downloads_and_validates(tmp_path):
    # Serve a synthetic mp4 over a local HTTP server.
    video = make_test_video(tmp_path / "clip.mp4", duration=4)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/clip.mp4"
        src = DirectVideoSource()
        assert src.validate_url(url) == url

        dest = str(tmp_path / "dl")
        result = src.download(url, dest)
        assert os.path.isfile(result.path)
        assert os.path.getsize(result.path) == os.path.getsize(video)

        from app.services.ingestion.validation import validate_video_file

        info = validate_video_file(result.path)
        assert info.duration > 0
        assert info.has_video and info.has_audio
    finally:
        server.shutdown()
