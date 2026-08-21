"""Shared FastAPI dependencies."""
from __future__ import annotations

import time
from collections import deque

from fastapi import Request

from ..config import get_settings
from ..db import get_session
from ..errors import RateLimitedError
from ..services.queue import JobQueue, get_queue


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_job_queue() -> JobQueue:
    return get_queue()


# ── Minimal per-IP rate limiting (job creation) ─────────────────────────
# Production note: swap for a Redis-backed limiter for multi-process safety.
_WINDOW = 60.0
_recent: dict[str, deque[float]] = {}


def rate_limit(request: Request) -> None:
    settings = get_settings()
    limit = settings.rate_limit_jobs_per_minute
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _recent.setdefault(client, deque())
    while hits and now - hits[0] > _WINDOW:
        hits.popleft()
    if len(hits) >= limit:
        raise RateLimitedError(
            "Too many requests. Please wait a moment and try again."
        )
    hits.append(now)
