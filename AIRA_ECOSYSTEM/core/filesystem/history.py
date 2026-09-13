"""
core/filesystem/history.py — History Engine untuk File System Engine
(FSE), Sprint 02.

Sebelum setiap overwrite (write_text pada file yang sudah ada), engine
ini membuat snapshot (SHA256 + salinan isi + timestamp) di
.aira_history/ di dalam workspace, supaya perubahan bisa di-restore.
"""

import hashlib
import json
import logging
import threading
import time
import uuid
from pathlib import Path

from core.filesystem.models import HistorySnapshot

logger = logging.getLogger("aira.filesystem.history")

HISTORY_DIRNAME = ".aira_history"
INDEX_FILENAME = "index.jsonl"


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_folder_name(relative_path: str) -> str:
    cleaned = relative_path.replace("\\", "/").strip("/")
    return cleaned.replace("/", "__") or "root"


class HistoryEngine:
    """
    Snapshot disimpan sebagai file biner di:
        <workspace_root>/.aira_history/<safe_name>/<snapshot_id>.snap
    dicatat sebagai satu baris JSON di:
        <workspace_root>/.aira_history/index.jsonl
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.history_dir = self.workspace_root / HISTORY_DIRNAME
        self.index_path = self.history_dir / INDEX_FILENAME
        self._lock = threading.Lock()

        self.history_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_path.exists():
            self.index_path.touch()

    def create_snapshot(self, relative_path: str, absolute_path: Path) -> HistorySnapshot:
        """Dipanggil SEBELUM overwrite file yang sudah ada."""

        content = absolute_path.read_bytes()
        checksum = _checksum(content)

        snapshot_id = uuid.uuid4().hex[:16]
        folder = self.history_dir / _safe_folder_name(relative_path)
        folder.mkdir(parents=True, exist_ok=True)

        snapshot_file = folder / f"{snapshot_id}.snap"
        snapshot_file.write_bytes(content)

        snapshot = HistorySnapshot(
            snapshot_id=snapshot_id,
            path=relative_path,
            checksum=checksum,
            created_at=time.time(),
            size=len(content),
        )

        self._append_index(snapshot, snapshot_file)

        logger.info(
            "SNAPSHOT CREATED | path=%s snapshot_id=%s checksum=%s",
            relative_path, snapshot_id, checksum[:12],
        )

        return snapshot

    def _append_index(self, snapshot: HistorySnapshot, snapshot_file: Path) -> None:
        record = {
            "snapshot_id": snapshot.snapshot_id,
            "path": snapshot.path,
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at,
            "size": snapshot.size,
            "snapshot_file": str(snapshot_file.relative_to(self.workspace_root)),
        }

        with self._lock:
            with open(self.index_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_index(self) -> list[dict]:
        if not self.index_path.exists():
            return []

        records = []

        with self._lock:
            with open(self.index_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return records

    def list_history(self, relative_path: Optional[str] = None) -> list[HistorySnapshot]:
        records = self._read_index()
        results = []

        for record in records:
            if relative_path is not None and record["path"] != relative_path:
                continue

            results.append(HistorySnapshot(
                snapshot_id=record["snapshot_id"],
                path=record["path"],
                checksum=record["checksum"],
                created_at=record["created_at"],
                size=record["size"],
            ))

        results.sort(key=lambda s: s.created_at, reverse=True)

        return results

    def restore(self, snapshot_id: str) -> bool:
        """Tulis ulang isi snapshot ke path aslinya. False kalau
        snapshot_id tidak ditemukan."""

        records = self._read_index()

        for record in records:
            if record["snapshot_id"] != snapshot_id:
                continue

            snapshot_file = self.workspace_root / record["snapshot_file"]

            if not snapshot_file.exists():
                logger.error("RESTORE GAGAL | snapshot_id=%s file hilang: %s", snapshot_id, snapshot_file)
                return False

            target = self.workspace_root / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot_file.read_bytes())

            logger.info("RESTORE SUKSES | snapshot_id=%s -> %s", snapshot_id, record["path"])

            return True

        logger.warning("RESTORE GAGAL | snapshot_id=%s tidak ditemukan.", snapshot_id)

        return False


from typing import Optional  # noqa: E402  (dipakai di list_history di atas)