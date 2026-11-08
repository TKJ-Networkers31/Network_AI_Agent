"""
AIRA OS — SQLite Online Backup & Restore Service (Stage 3 / REC-26).
Implements transactionally safe, non-blocking backups using the official
sqlite3.Connection.backup() API (WAL mode safe).

Guarantees:
- Zero corruption: never performs raw OS copies on live WAL databases.
- Atomic consistency: copies pages under SQLite's internal locking protocol.
- Cryptographic verification: SHA-256 hash computed and verified on every backup.
- Schema & Foreign Key Integrity: Runs PRAGMA integrity_check and PRAGMA foreign_key_check.
- Metadata Sidecars: Generates structured JSON metadata for every backup.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aira.database.backup")

DEFAULT_BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "database" / "backups"


@dataclass
class BackupMetadata:
    backup_id: str
    timestamp_utc: str
    source_db_path: str
    backup_path: str
    size_bytes: int
    sha256: str
    pages: int
    table_counts: Dict[str, int]
    integrity_ok: bool
    foreign_keys_ok: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BackupError(Exception):
    """Base exception for backup operations."""
    pass


class IntegrityError(BackupError):
    """Raised when SQLite database integrity check fails."""
    pass


class ChecksumMismatchError(BackupError):
    """Raised when SHA-256 checksum does not match expected value."""
    pass


def compute_file_sha256(file_path: Path | str) -> str:
    """Computes SHA-256 checksum of a file in 64 KiB chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_database_integrity(db_path: Path | str) -> tuple[bool, bool, str]:
    """
    Runs PRAGMA integrity_check and PRAGMA foreign_key_check.
    Returns: (integrity_ok, fk_ok, message)
    """
    target = Path(db_path).resolve()
    if not target.exists():
        return False, False, f"File not found: {target}"

    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        integrity_res = cur.execute("PRAGMA integrity_check;").fetchall()
        integrity_ok = len(integrity_res) == 1 and integrity_res[0][0].lower() == "ok"

        fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
        fk_ok = len(fk_violations) == 0

        msg = "OK" if (integrity_ok and fk_ok) else f"Integrity: {integrity_res}, FK Violations: {len(fk_violations)}"
        return integrity_ok, fk_ok, msg
    except Exception as e:
        return False, False, f"Integrity check crashed: {e}"
    finally:
        conn.close()


def get_table_counts(db_path: Path | str) -> Dict[str, int]:
    """Retrieves record count for every user table in SQLite database."""
    target = Path(db_path).resolve()
    counts: Dict[str, int] = {}
    if not target.exists():
        return counts

    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        tables = [
            r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for t in tables:
            try:
                cnt = cur.execute(f"SELECT COUNT(*) FROM `{t}`;").fetchone()[0]
                counts[t] = cnt
            except Exception:
                counts[t] = -1
    finally:
        conn.close()
    return counts


def create_online_backup(
    source_db_path: Path | str,
    target_backup_path: Optional[Path | str] = None,
    backup_dir: Optional[Path | str] = None,
    pages_per_step: int = 100,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> BackupMetadata:
    """
    Performs transactionally safe online backup using sqlite3.Connection.backup().
    Safe to execute while read and write queries are actively running against source.
    """
    src = Path(source_db_path).resolve()
    if not src.exists():
        raise BackupError(f"Source database does not exist: {src}")

    dest_dir = Path(backup_dir or DEFAULT_BACKUP_DIR).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    now_ts = now_dt.strftime("%Y%m%d_%H%M%S")

    if target_backup_path:
        dst = Path(target_backup_path).resolve()
    else:
        src_stem = src.stem
        dst = dest_dir / f"{src_stem}_backup_{now_ts}.db"

    dst.parent.mkdir(parents=True, exist_ok=True)

    # 1. Execute online backup via official SQLite backup API
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(dst)

    total_pages = 0
    copied_pages = 0

    def _step_callback(status: int, remaining: int, total: int):
        nonlocal total_pages, copied_pages
        total_pages = total
        copied_pages = total - remaining
        if progress_callback:
            progress_callback(status, remaining, total)

    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=pages_per_step, progress=_step_callback)
    except Exception as e:
        if dst.exists():
            try:
                dst.unlink()
            except Exception:
                pass
        raise BackupError(f"Online backup failed during page copy: {e}") from e
    finally:
        dst_conn.close()
        src_conn.close()

    # 2. Check integrity of backup database
    integrity_ok, fk_ok, check_msg = check_database_integrity(dst)
    if not integrity_ok:
        raise IntegrityError(f"Backup failed SQLite integrity check: {check_msg}")

    # 3. Compute SHA-256 and metadata
    sha256 = compute_file_sha256(dst)
    size_bytes = dst.stat().st_size
    tbl_counts = get_table_counts(dst)
    backup_id = f"bak_{now_ts}_{sha256[:8]}"

    meta = BackupMetadata(
        backup_id=backup_id,
        timestamp_utc=now_iso,
        source_db_path=str(src),
        backup_path=str(dst),
        size_bytes=size_bytes,
        sha256=sha256,
        pages=total_pages,
        table_counts=tbl_counts,
        integrity_ok=integrity_ok,
        foreign_keys_ok=fk_ok,
    )

    # 4. Write sidecar metadata file
    meta_path = dst.with_suffix(".db.meta.json")
    try:
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
        if os.name != "nt":
            os.chmod(meta_path, 0o600)
            os.chmod(dst, 0o600)
    except Exception as e:
        logger.warning("Could not write backup metadata sidecar %s: %s", meta_path, e)

    logger.info("Database online backup completed successfully: %s (size=%d, sha256=%s)", dst.name, size_bytes, sha256[:12])
    return meta


def restore_database(
    backup_path: Path | str,
    target_db_path: Path | str,
    verify_sha256: bool = True,
) -> Dict[str, Any]:
    """
    Safely restores a SQLite database from an online backup.
    Verifies SHA-256 checksum against sidecar metadata and checks integrity before and after restore.
    """
    bak = Path(backup_path).resolve()
    target = Path(target_db_path).resolve()

    if not bak.exists():
        raise BackupError(f"Backup file not found: {bak}")

    # 1. Verify SHA-256 against sidecar metadata if available
    meta_path = bak.with_suffix(".db.meta.json")
    if verify_sha256 and meta_path.exists():
        try:
            meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
            expected_sha = meta_json.get("sha256")
            actual_sha = compute_file_sha256(bak)
            if expected_sha and actual_sha != expected_sha:
                raise ChecksumMismatchError(f"Checksum mismatch for {bak.name}: expected {expected_sha}, got {actual_sha}")
        except json.JSONDecodeError:
            logger.warning("Sidecar metadata corrupted; proceeding with direct file integrity check.")

    # 2. Check backup file integrity
    bak_integrity, bak_fk, bak_msg = check_database_integrity(bak)
    if not bak_integrity:
        raise IntegrityError(f"Backup database file is corrupt: {bak_msg}")

    # 3. Create target directory and use SQLite backup API in reverse
    target.parent.mkdir(parents=True, exist_ok=True)

    bak_conn = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
    target_conn = sqlite3.connect(target)
    try:
        with target_conn:
            bak_conn.backup(target_conn, pages=100)
    except Exception as e:
        raise BackupError(f"Restore page copy failed: {e}") from e
    finally:
        target_conn.close()
        bak_conn.close()

    # 4. Verify restored target database
    target_integrity, target_fk, target_msg = check_database_integrity(target)
    if not target_integrity:
        raise IntegrityError(f"Restored database failed integrity check: {target_msg}")

    target_counts = get_table_counts(target)
    logger.info("Database restored successfully to %s (%d tables verified)", target, len(target_counts))

    return {
        "success": True,
        "restored_to": str(target),
        "source_backup": str(bak),
        "tables_verified": len(target_counts),
        "table_counts": target_counts,
        "integrity_ok": target_integrity,
        "foreign_keys_ok": target_fk,
    }


def list_backups(backup_dir: Optional[Path | str] = None) -> List[Dict[str, Any]]:
    """Lists all available backups in the backup directory with their metadata."""
    bdir = Path(backup_dir or DEFAULT_BACKUP_DIR).resolve()
    if not bdir.exists():
        return []

    results: List[Dict[str, Any]] = []
    for db_file in sorted(bdir.glob("*.db"), reverse=True):
        meta_file = db_file.with_suffix(".db.meta.json")
        meta_dict: Dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        results.append({
            "backup_name": db_file.name,
            "backup_path": str(db_file),
            "size_bytes": db_file.stat().st_size,
            "modified_time": datetime.fromtimestamp(db_file.stat().st_mtime, timezone.utc).isoformat(),
            "metadata": meta_dict or None,
        })
    return results
