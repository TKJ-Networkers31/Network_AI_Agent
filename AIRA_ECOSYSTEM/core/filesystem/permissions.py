"""
core/filesystem/permissions.py — Permission Engine untuk File System
Engine (FSE), Sprint 02.

Permission berlaku PER FOLDER, diperiksa terhadap folder ancestor
paling spesifik yang cocok. Belum ada persistensi (in-memory per
proses) dan belum ada GUI - sesuai spesifikasi Sprint 02.
"""

import logging
import threading
from typing import Optional

from core.filesystem.models import PermissionLevel

logger = logging.getLogger("aira.filesystem.permissions")


def _normalize(relative_path: str) -> str:
    return relative_path.replace("\\", "/").strip("/")


class PermissionEngine:
    """
    Resolusi: cari folder terdaftar PALING SPESIFIK yang menjadi
    ancestor (atau sama persis) dari path yang diperiksa. Tanpa aturan
    terdaftar sama sekali -> default READ_WRITE.
    """

    def __init__(self):
        self._rules: dict[str, PermissionLevel] = {}
        self._lock = threading.Lock()

    def grant(self, relative_folder: str, level: PermissionLevel) -> None:
        key = _normalize(relative_folder)

        with self._lock:
            self._rules[key] = level

        logger.info("PERMISSION GRANT | folder=%s level=%s", key or "/", level.value)

    def revoke(self, relative_folder: str) -> None:
        key = _normalize(relative_folder)

        with self._lock:
            self._rules.pop(key, None)

        logger.info("PERMISSION REVOKE | folder=%s", key or "/")

    def _resolve_level(self, relative_path: str) -> PermissionLevel:
        target = _normalize(relative_path)

        with self._lock:
            rules = dict(self._rules)

        if not rules:
            return PermissionLevel.READ_WRITE

        best_match: Optional[str] = None

        for folder_key in rules:
            if target == folder_key or target.startswith(f"{folder_key}/") or folder_key == "":
                if best_match is None or len(folder_key) > len(best_match):
                    best_match = folder_key

        if best_match is None:
            return PermissionLevel.READ_WRITE

        return rules[best_match]

    def can_read(self, relative_path: str) -> bool:
        level = self._resolve_level(relative_path)
        return level in (PermissionLevel.READ_ONLY, PermissionLevel.READ_WRITE)

    def can_write(self, relative_path: str) -> bool:
        return self._resolve_level(relative_path) == PermissionLevel.READ_WRITE

    def list_rules(self) -> dict[str, str]:
        with self._lock:
            return {k or "/": v.value for k, v in self._rules.items()}


_engine_singleton: Optional[PermissionEngine] = None
_engine_lock = threading.Lock()


def get_permission_engine() -> PermissionEngine:
    global _engine_singleton

    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                _engine_singleton = PermissionEngine()

    return _engine_singleton