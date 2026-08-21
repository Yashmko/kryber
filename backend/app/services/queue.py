"""Job queue abstraction.

``JobQueue`` is the interface the worker and API depend on. Two backends:
  * :class:`RedisJobQueue` — production, backed by a Redis list.
  * :class:`InMemoryJobQueue` — dev/tests, in-process.
"""
from __future__ import annotations

import abc
import queue as _stdlib_queue

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
