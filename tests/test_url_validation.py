"""URL validation (§9, §27)."""
from __future__ import annotations

import pytest

from app.errors import URLValidationError
from app.utils.validation import (
    is_supported_url,
    normalize_youtube_url,
    parse_youtube_video_id,
    validate_source_url,
)


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=30", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("http://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "dQw4w9WgXcQ"),
    ],
)
def test_parse_youtube_video_id(url, expected_id):
    assert parse_youtube_video_id(url) == expected_id


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "not a url",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://vimeo.com/123456",
        "https://www.youtube.com/",
        "https://www.youtube.com/watch?v=short",  # invalid id length
        "https://www.youtube.com/watch?v=dQw4w9WgXc!",  # invalid char
    ],
)
def test_parse_youtube_video_id_invalid(url):
    assert parse_youtube_video_id(url) is None


def test_validate_source_url_returns_platform_and_canonical():
    platform, canonical = validate_source_url("https://youtu.be/dQw4w9WgXcQ")
    assert platform == "youtube"
    assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_youtube_url():
    assert normalize_youtube_url("dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_validate_rejects_missing_scheme():
    with pytest.raises(URLValidationError):
        validate_source_url("youtube.com/watch?v=dQw4w9WgXcQ")


def test_validate_rejects_unsupported_platform():
    with pytest.raises(URLValidationError) as excinfo:
        validate_source_url("https://vimeo.com/123456")
    assert "Unsupported URL" in str(excinfo.value)


def test_validate_rejects_empty():
    with pytest.raises(URLValidationError):
        validate_source_url("")


def test_is_supported_url():
    assert is_supported_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_supported_url("https://vimeo.com/123") is False


# ── Direct video URLs ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/video.mp4",
        "https://example.com/path/to/clip.webm",
        "https://example.com/v.mov?X-Amz-Signature=abc123",
        "http://example.com/x.MKV",
        "https://example.com/video.ogv",
    ],
)
def test_direct_video_urls_validate(url):
    platform, canonical = validate_source_url(url)
    assert platform == "direct"
    assert canonical == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video.mp3",
        "https://example.com/video.txt",
        "https://example.com/page",  # no extension
        "https://example.com/video.mp4.exe",
    ],
)
def test_non_video_direct_urls_rejected(url):
    with pytest.raises(URLValidationError):
        validate_source_url(url)
