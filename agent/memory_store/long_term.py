import sqlite3
import time
from pathlib import Path
from contextlib import closing


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "long_term_memory.db"

DATA_DIR.mkdir(
    exist_ok=True
)


def _connect():

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    with closing(_connect()) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                device TEXT,
                message TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                created_at REAL NOT NULL
            )
        """)

        conn.commit()


init_db()


# ============================================================
# FACTS (key-value, persisten, di-overwrite kalau key sama)
# ============================================================

def remember_fact(key, value):

    now = time.time()

    with closing(_connect()) as conn:

        conn.execute("""
            INSERT INTO facts (key, value, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, value, now, now))

        conn.commit()

    return {
        "success": True,
        "key": key,
        "value": value
    }


def forget_fact(key):

    with closing(_connect()) as conn:

        cursor = conn.execute(
            "DELETE FROM facts WHERE key = ?",
            (key,)
        )

        conn.commit()

        deleted = cursor.rowcount > 0

    return {
        "success": deleted,
        "key": key
    }


def get_all_facts():

    with closing(_connect()) as conn:

        rows = conn.execute(
            "SELECT key, value, updated_at FROM facts "
            "ORDER BY updated_at DESC"
        ).fetchall()

    return [dict(row) for row in rows]


def recall_facts(query, limit=5):
    """
    Pencarian sederhana berbasis keyword (LIKE), cukup untuk
    skala data kecil tanpa perlu embedding/vector DB.
    """

    keywords = [
        word for word in query.lower().split()
        if len(word) > 2
    ]

    if not keywords:
        return get_all_facts()[:limit]

    conditions = " OR ".join(
        "LOWER(key) LIKE ? OR LOWER(value) LIKE ?"
        for _ in keywords
    )

    params = []

    for word in keywords:
        params.extend([
            f"%{word}%",
            f"%{word}%"
        ])

    params.append(limit)

    with closing(_connect()) as conn:

        rows = conn.execute(
            f"SELECT key, value, updated_at FROM facts "
            f"WHERE {conditions} "
            f"ORDER BY updated_at DESC LIMIT ?",
            params
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# EVENTS (log observasi/alert, append-only)
# ============================================================

def log_event(category, message, device=None, severity="info"):

    now = time.time()

    with closing(_connect()) as conn:

        conn.execute("""
            INSERT INTO events
                (category, device, message, severity, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (category, device, message, severity, now))

        conn.commit()

    return {
        "success": True,
        "category": category,
        "device": device,
        "message": message
    }


def get_recent_events(limit=10, device=None, category=None):

    query = "SELECT * FROM events"
    conditions = []
    params = []

    if device:
        conditions.append("device = ?")
        params.append(device)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# CONTEXT INJECTION
# ============================================================

def build_context_snippet(max_facts=10, max_events=5):
    """
    Membuat ringkasan singkat dari long-term memory untuk
    disisipkan ke system prompt tiap request, supaya agent
    tetap "ingat" fakta & kejadian penting lintas sesi tanpa
    harus dipanggil manual sebagai tool.
    """

    facts = get_all_facts()[:max_facts]
    events = get_recent_events(limit=max_events)

    if not facts and not events:
        return ""

    lines = [
        "=== LONG-TERM MEMORY ==="
    ]

    if facts:

        lines.append(
            "Fakta yang sudah diketahui dari sesi sebelumnya:"
        )

        for fact in facts:
            lines.append(
                f"- {fact['key']}: {fact['value']}"
            )

    if events:

        lines.append("")
        lines.append(
            "Kejadian/observasi terakhir yang tercatat "
            "(termasuk dari scheduler jika aktif):"
        )

        for event in events:

            timestamp = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(event["created_at"])
            )

            device_part = (
                f" [{event['device']}]"
                if event["device"] else ""
            )

            lines.append(
                f"- ({timestamp}){device_part} {event['message']}"
            )

    return "\n".join(lines)