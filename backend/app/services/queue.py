"""Job queue abstraction.

``JobQueue`` is the interface the worker and API depend on. Two backends:
  * :class:`RedisJobQueue` — production, backed by a Redis list.
  * :class:`InMemoryJobQueue` — dev/tests, in-process.

Worker visibility
-----------------
The in-memory queue lives inside a single process, so jobs are only ever
consumed when a worker loop runs in *that* process (``KRYBER_INPROC_WORKER=1``).
Without one, ``POST /api/jobs`` still succeeds and the job simply stays QUEUED
forever — which looks like a frozen UI. :func:`queue_status` makes that state
observable (startup logs, ``/healthz``) instead of silently hanging.
"""
from __future__ import annotations

import abc
import queue as _stdlib_queue
import threading

from ..config import get_settings


class JobQueue(abc.ABC):
    @abc.abstractmethod
    def enqueue(self, job_id: str) -> None: ...

    @abc.abstractmethod
    def dequeue(self, timeout: float | None = None) -> str | None: ...

    @abc.abstractmethod
    def size(self) -> int: ...


class InMemoryJobQueue(JobQueue):
    def __init__(self) -> None:
        self._q: _stdlib_queue.Queue[str] = _stdlib_queue.Queue()

    def enqueue(self, job_id: str) -> None:
        self._q.put(job_id)

    def dequeue(self, timeout: float | None = None) -> str | None:
        try:
            if timeout is None:
                return self._q.get_nowait()
            return self._q.get(timeout=timeout)
        except _stdlib_queue.Empty:
            return None

    def size(self) -> int:
        return self._q.qsize()


class RedisJobQueue(JobQueue):
    def __init__(self, client, key: str = "kryber:jobs"):
        self._client = client
        self._key = key

    def enqueue(self, job_id: str) -> None:
        self._client.lpush(self._key, job_id)

    def dequeue(self, timeout: float | None = None) -> str | None:
        if timeout:
            item = self._client.brpop(self._key, timeout=int(timeout))
            return item[1].decode() if item else None
        item = self._client.rpop(self._key)
        return item.decode() if item else None

    def size(self) -> int:
        return int(self._client.llen(self._key))


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        settings = get_settings()
        if settings.queue_backend == "redis":
            import redis

            _queue = RedisJobQueue(redis.Redis.from_url(settings.redis_url))
        else:
            _queue = InMemoryJobQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    """Override the process-wide queue (used by tests)."""
    global _queue
    _queue = queue


# ── Worker visibility ───────────────────────────────────────────────────
# A worker loop registers itself here while it is consuming this process's
# queue. Only meaningful for the in-memory backend, where producer and
# consumer must share a process; a Redis worker runs elsewhere and cannot be
# observed from the API.

_worker_present = threading.Event()

WORKER_MISSING_HINT = (
    "No worker is consuming the in-memory queue in this process, so jobs will "
    "be accepted but stay QUEUED forever. Start the API with "
    "KRYBER_INPROC_WORKER=1 (dev/Codespaces), or set KRYBER_QUEUE_BACKEND=redis "
    "and run a separate worker (python -m app.workers.video_worker)."
)

WORKER_EXTERNAL_HINT = (
    "Jobs are consumed by a separate worker process; this API cannot observe "
    "its liveness. Check the worker's own logs if jobs stay queued."
)


def mark_worker_active() -> None:
    """Record that a worker loop is running in this process."""
    _worker_present.set()


def mark_worker_inactive() -> None:
    """Record that this process's worker loop has stopped."""
    _worker_present.clear()


def worker_active() -> bool:
    """True when a worker loop is running in this process."""
    return _worker_present.is_set()


def queue_status() -> dict:
    """Observable queue/worker state for startup diagnostics and /healthz.

    ``worker`` is one of:
      * ``running``     — a worker loop is consuming this process's queue.
      * ``unavailable`` — in-memory queue with no worker: jobs cannot progress.
      * ``external``    — Redis backend; the worker is a separate process whose
        liveness this API cannot observe.
    """
    settings = get_settings()
    backend = settings.queue_backend

    depth: int | None
    try:
        depth = get_queue().size()
    except Exception:  # unreachable Redis must not break health reporting
        depth = None

    if backend == "memory":
        if worker_active():
            worker, detail = "running", None
        else:
            worker, detail = "unavailable", WORKER_MISSING_HINT
    else:
        worker, detail = "external", WORKER_EXTERNAL_HINT

    return {
        "backend": backend,
        "depth": depth,
        "worker": worker,
        # False only when we can prove nothing will ever pick the job up.
        "processing_available": worker != "unavailable",
        "detail": detail,
    }
