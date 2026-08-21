"""Local filesystem storage backend (dev / single-node)."""
from __future__ import annotations

import os
import shutil

from ...config import get_settings
from ...utils.validation import safe_join
from .base import StorageBackend


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str | None = None):
        self.root = root or get_settings().storage_local_root
        os.makedirs(self.root, exist_ok=True)

    def put(self, source_path: str, key: str) -> str:
        dest = safe_join(self.root, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(source_path, dest)
        return dest

    def get_local_path(self, key: str) -> str | None:
        path = safe_join(self.root, key)
        return path if os.path.isfile(path) else None

    def delete(self, key: str) -> None:
        path = safe_join(self.root, key)
        if os.path.isfile(path):
            os.remove(path)
