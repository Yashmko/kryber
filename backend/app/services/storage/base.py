"""StorageBackend abstraction: local filesystem and S3-compatible."""
from __future__ import annotations

import abc
from pathlib import Path


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def put(self, source_path: str, key: str) -> str:
        """Store a file and return a resolvable reference (path or object key)."""

    @abc.abstractmethod
    def get_local_path(self, key: str) -> str | None:
        """Return a local path for the object, or None if not present."""

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...
