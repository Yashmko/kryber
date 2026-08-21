"""Storage backend factory."""
from __future__ import annotations

from ...config import get_settings
from ...errors import KryberError
from .base import StorageBackend  # noqa: F401
from .local import LocalStorageBackend


def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorageBackend(settings.storage_local_root)
    if settings.storage_backend == "s3":
        raise KryberError(
            "S3 storage is not configured in this build; use KRYBER_STORAGE_BACKEND=local.",
            code="STORAGE_UNSUPPORTED",
            stage="rendering",
        )
    raise KryberError(
        f"Unknown storage backend: {settings.storage_backend!r}",
        code="STORAGE_UNSUPPORTED",
        stage="rendering",
    )
