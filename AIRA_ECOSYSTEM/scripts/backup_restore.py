#!/usr/bin/env python3
"""
AIRA OS — Production Database Backup & Restore Tooling (Stage 3 / REC-26).
CLI command line interface for operators to execute online backups, verify integrity,
and rehearse restores.

Usage:
    # 1. Create online backup of topology.db:
    python scripts/backup_restore.py backup

    # 2. List all backups:
    python scripts/backup_restore.py list

    # 3. Verify backup integrity:
    python scripts/backup_restore.py verify --file database/backups/topology_backup_20261108_120000.db

    # 4. Restore database from backup:
    python scripts/backup_restore.py restore --file database/backups/topology_backup_20261108_120000.db --target /tmp/restored.db
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

# Ensure repository root in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
ECOSYSTEM_ROOT = REPO_ROOT / "AIRA_ECOSYSTEM"
if str(ECOSYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(ECOSYSTEM_ROOT))

from core.database.backup_service import (
    check_database_integrity,
    compute_file_sha256,
    create_online_backup,
    list_backups,
    restore_database,
)
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aira.backup_restore")


def cmd_backup(args: argparse.Namespace) -> int:
    source_db = Path(args.source or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    logger.info("Starting online backup for source: %s", source_db)
    try:
        meta = create_online_backup(
            source_db_path=source_db,
            target_backup_path=args.dest,
            backup_dir=args.dir,
        )
        print("\n=== BACKUP SUCCESSFUL ===")
        print(f"Backup ID:    {meta.backup_id}")
        print(f"Timestamp:    {meta.timestamp_utc}")
        print(f"Backup File:  {meta.backup_path}")
        print(f"Size:         {meta.size_bytes} bytes ({meta.size_bytes / 1024:.2f} KiB)")
        print(f"SHA-256:      {meta.sha256}")
        print(f"Integrity:    {'PASSED' if meta.integrity_ok else 'FAILED'}")
        print(f"Tables:       {len(meta.table_counts)} tables backed up")
        return 0
    except Exception as e:
        logger.error("Backup failed: %s", e)
        return 1


def cmd_restore(args: argparse.Namespace) -> int:
    if not args.file:
        logger.error("--file argument is required for restore.")
        return 1
    if not args.target:
        logger.error("--target argument is required for restore.")
        return 1

    backup_file = Path(args.file).resolve()
    target_file = Path(args.target).resolve()

    logger.info("Restoring from backup %s to target %s", backup_file, target_file)
    try:
        res = restore_database(
            backup_path=backup_file,
            target_db_path=target_file,
            verify_sha256=not args.skip_checksum,
        )
        print("\n=== RESTORE SUCCESSFUL ===")
        print(f"Source:       {res['source_backup']}")
        print(f"Restored To:  {res['restored_to']}")
        print(f"Tables:       {res['tables_verified']}")
        print(f"Integrity:    {'PASSED' if res['integrity_ok'] else 'FAILED'}")
        return 0
    except Exception as e:
        logger.error("Restore failed: %s", e)
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    if not args.file:
        logger.error("--file argument is required for verify.")
        return 1

    target = Path(args.file).resolve()
    if not target.exists():
        logger.error("File not found: %s", target)
        return 1

    sha256 = compute_file_sha256(target)
    integrity_ok, fk_ok, msg = check_database_integrity(target)

    # Check sidecar if present
    meta_path = target.with_suffix(".db.meta.json")
    sidecar_match = None
    if meta_path.exists():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            sidecar_match = (m.get("sha256") == sha256)
        except Exception:
            pass

    print("\n=== DATABASE VERIFICATION ===")
    print(f"File:         {target}")
    print(f"SHA-256:      {sha256}")
    print(f"Integrity:    {'PASSED' if integrity_ok else 'FAILED'}")
    print(f"Foreign Keys: {'PASSED' if fk_ok else 'FAILED'}")
    if sidecar_match is not None:
        print(f"Sidecar Hash: {'MATCHES' if sidecar_match else 'MISMATCH'}")
    print(f"Message:      {msg}")

    return 0 if (integrity_ok and fk_ok and (sidecar_match is not False)) else 1


def cmd_list(args: argparse.Namespace) -> int:
    backups = list_backups(backup_dir=args.dir)
    if not backups:
        print("No backups found in directory.")
        return 0

    print(f"\nFound {len(backups)} backups:")
    print("-" * 80)
    for b in backups:
        meta = b.get("metadata") or {}
        sha_short = meta.get("sha256", "no-meta")[:12]
        size_kb = b["size_bytes"] / 1024
        print(f"{b['backup_name']:<35} | {size_kb:>8.1f} KiB | {sha_short:<12} | {b['modified_time']}")
    print("-" * 80)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AIRA OS Database Backup & Restore Tooling")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # backup
    p_backup = subparsers.add_parser("backup", help="Create an online SQLite backup")
    p_backup.add_argument("--source", "-s", help="Path to source SQLite database")
    p_backup.add_argument("--dest", "-d", help="Explicit destination backup file path")
    p_backup.add_argument("--dir", help="Backup directory (default: database/backups)")

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore database from an online backup")
    p_restore.add_argument("--file", "-f", required=True, help="Backup file to restore from")
    p_restore.add_argument("--target", "-t", required=True, help="Target path to restore into")
    p_restore.add_argument("--skip-checksum", action="store_true", help="Skip SHA-256 sidecar validation")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify integrity and checksum of a database/backup")
    p_verify.add_argument("--file", "-f", required=True, help="Database or backup file to verify")

    # list
    p_list = subparsers.add_parser("list", help="List all backups in backup directory")
    p_list.add_argument("--dir", help="Backup directory (default: database/backups)")

    args = parser.parse_args()
    if args.command == "backup":
        return cmd_backup(args)
    elif args.command == "restore":
        return cmd_restore(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "list":
        return cmd_list(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
