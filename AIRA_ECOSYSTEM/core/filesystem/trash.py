"""
core/filesystem/trash.py — Trash System untuk File System Engine (FSE),
Sprint 02.

Delete TIDAK PERNAH menghapus file secara permanen - selalu dipindahkan
ke <workspace_root>/Trash/ beserta metadata, dicatat di index.jsonl
seperti History Engine. Penghapusan permanen HANYA lewat empty_trash().
"""

import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from core.filesystem.models import TrashEntry

logger = logging.getLogger("aira.filesystem.trash")

TRASH_DIRNAME = "Trash"
INDEX_FILENAME = ".trash_index.jsonl"


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class TrashEngine:

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.trash_dir = self.workspace_root / TRASH_DIRNAME
        self.index_path = self.trash_dir / INDEX_FILENAME
        self._lock = threading.Lock()

        self.trash_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_path.exists():
            self.index_path.touch()

    def move_to_trash(self, relative_path: str, absolute_path: Path) -> TrashEntry:
        is_dir = absolute_path.is_dir()

        if is_dir:
            content_for_checksum = relative_path.encode("utf-8")
            size = sum(f.stat().st_size for f in absolute_path.rglob("*") if f.is_file())
        else:
            content_for_checksum = absolute_path.read_bytes()
            size = len(content_for_checksum)

        checksum = _checksum(content_for_checksum)
        trash_id = uuid.uuid4().hex[:16]

        suffix = absolute_path.suffix if not is_dir else ""
        trashed_path = self.trash_dir / f"{trash_id}{suffix}"

        absolute_path.rename(trashed_path)

        entry = TrashEntry(
            trash_id=trash_id,
            original_path=relative_path,
            trashed_path=str(trashed_path.relative_to(self.workspace_root)),
            deleted_at=time.time(),
            checksum=checksum,
            size=size,
        )

        self._append_index(entry)

        logger.info("TRASH MOVE | original=%s trash_id=%s", relative_path, trash_id)

        return entry

    def _append_index(self, entry: TrashEntry) -> None:
        record = {
            "trash_id": entry.trash_id,
            "original_path": entry.original_path,
            "trashed_path": entry.trashed_path,
            "deleted_at": entry.deleted_at,
            "checksum": entry.checksum,
            "size": entry.size,
            "restored": False,
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

    def _rewrite_index(self, records: list[dict]) -> None:
        with self._lock:
            with open(self.index_path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_trash(self) -> list[TrashEntry]:
        records = self._read_index()

        results = [
            TrashEntry(
                trash_id=r["trash_id"], original_path=r["original_path"],
                trashed_path=r["trashed_path"], deleted_at=r["deleted_at"],
                checksum=r["checksum"], size=r["size"],
            )
            for r in records if not r.get("restored")
        ]

        results.sort(key=lambda e: e.deleted_at, reverse=True)

        return results

    def restore(self, trash_id: str) -> bool:
        records = self._read_index()

        for record in records:
            if record["trash_id"] != trash_id or record.get("restored"):
                continue

            trashed_path = self.workspace_root / record["trashed_path"]

            if not trashed_path.exists():
                logger.error("TRASH RESTORE GAGAL | trash_id=%s file hilang.", trash_id)
                return False

            target = self.workspace_root / record["original_path"]
            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists():
                # Hindari menimpa file yang sudah ada di lokasi asal.
                target = target.with_name(f"{target.stem}_restored_{trash_id[:6]}{target.suffix}")

            trashed_path.rename(target)
            record["restored"] = True

            self._rewrite_index(records)

            logger.info("TRASH RESTORE SUKSES | trash_id=%s -> %s", trash_id, target)

            return True

        logger.warning("TRASH RESTORE GAGAL | trash_id=%s tidak ditemukan.", trash_id)

        return False

    def empty_trash(self) -> int:
        """SATU-SATUNYA jalur penghapusan permanen di seluruh FSE."""

        records = self._read_index()
        remaining = []
        deleted_count = 0

        for record in records:
            if record.get("restored"):
                remaining.append(record)
                continue

            trashed_path = self.workspace_root / record["trashed_path"]

            try:
                if trashed_path.is_dir():
                    shutil.rmtree(trashed_path, ignore_errors=True)
                elif trashed_path.exists():
                    trashed_path.unlink()

                deleted_count += 1

            except Exception:
                logger.exception("Gagal menghapus permanen trash_id=%s", record["trash_id"])
                remaining.append(record)

        self._rewrite_index(remaining)

        logger.info("TRASH EMPTIED | deleted_count=%d", deleted_count)

        return deleted_count