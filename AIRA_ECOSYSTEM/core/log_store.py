"""
core/log_store.py — SQLite-backed structured log store untuk AIRA.

Menyimpan setiap log event (bukan cuma teks ke file) ke tabel SQLite supaya
bisa di-query dengan filter (kategori, level, keyword, rentang waktu) dari
endpoint API dan ditampilkan di halaman "Logs" pada PWA.

TERPISAH dari core/memory.py (long_term_memory.db) - skema dan tujuan beda
(audit/observability runtime, bukan fakta yang diingat AI).
"""

import sqlite3
import time
import json
import threading
from pathlib import Path
from contextlib import closing
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "logs.db"

DATABASE_DIR.mkdir(exist_ok=True)

# Kategori resmi yang dikenal sistem - dipakai supaya filter di PWA tetap
# muncul lengkap walau kategori itu belum pernah ada log masuk.
KNOWN_CATEGORIES = [
    "system", "api", "orchestrator", "brain", "planner", "llm", "tool",
    "ssh", "snmp", "mikrotik", "network", "web", "vision", "voice",
    "memory", "session", "auto_extract", "provider_client",
]

_write_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                logger_name TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT,
                duration_ms REAL,
                success INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at)")
        conn.commit()


init_db()


def insert_log(
    category: str,
    level: str,
    logger_name: str,
    message: str,
    context: Optional[dict] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    created_at: Optional[float] = None,
) -> None:
    now = created_at if created_at is not None else time.time()

    context_json = None
    if context is not None:
        try:
            context_json = json.dumps(context, ensure_ascii=False, default=str)
        except Exception:
            context_json = json.dumps({"_unserializable": str(context)})

    success_val = None if success is None else (1 if success else 0)

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute(
                "INSERT INTO logs "
                "(created_at, category, level, logger_name, message, context, duration_ms, success) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, category, level, logger_name, message, context_json, duration_ms, success_val),
            )
            conn.commit()


def query_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if level and level != "all":
        conditions.append("level = ?")
        params.append(level.upper())

    if search:
        conditions.append("(message LIKE ? OR context LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    if until is not None:
        conditions.append("created_at <= ?")
        params.append(until)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM logs {where} ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        if item.get("context"):
            try:
                item["context"] = json.loads(item["context"])
            except (json.JSONDecodeError, TypeError):
                pass
        item["success"] = None if item.get("success") is None else bool(item["success"])
        results.append(item)

    return results


def count_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> int:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if level and level != "all":
        conditions.append("level = ?")
        params.append(level.upper())

    if search:
        conditions.append("(message LIKE ? OR context LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    if until is not None:
        conditions.append("created_at <= ?")
        params.append(until)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT COUNT(*) as total FROM logs {where}", params).fetchone()

    return row["total"] if row else 0


def get_categories_with_counts() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM logs GROUP BY category ORDER BY count DESC"
        ).fetchall()

    found = {row["category"]: row["count"] for row in rows}

    categories = []
    for cat in KNOWN_CATEGORIES:
        categories.append({"category": cat, "count": found.pop(cat, 0)})

    for cat, count in found.items():
        categories.append({"category": cat, "count": count})

    return categories


def get_stats(since: Optional[float] = None) -> dict:
    conditions = []
    params: list[Any] = []

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT level, COUNT(*) as count FROM logs {where} GROUP BY level", params
        ).fetchall()

    return {row["level"]: row["count"] for row in rows}


def clear_logs(category: Optional[str] = None, older_than: Optional[float] = None) -> int:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if older_than is not None:
        conditions.append("created_at < ?")
        params.append(older_than)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with _write_lock:
        with closing(_connect()) as conn:
            cursor = conn.execute(f"DELETE FROM logs {where}", params)
            conn.commit()
            return cursor.rowcount