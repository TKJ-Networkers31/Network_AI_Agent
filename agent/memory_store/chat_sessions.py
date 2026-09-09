"""
Penyimpanan SESI CHAT untuk web UI (bukan long-term memory/facts —
itu tetap di agent/memory_store/long_term.py dan tidak disentuh
sama sekali).

Kenapa file terpisah dari long_term.py:
long_term.py isinya "facts" (preferensi/threshold yang diingat
lintas sesi) dan "events" (log observasi). Sesi chat itu konsep
berbeda: riwayat percakapan MENTAH (untuk dikirim ulang ke LLM
supaya konteks nyambung) + transkrip yang sudah "dibersihkan"
untuk ditampilkan di UI (bubble chat + timeline tool). Dipisah
biar tidak mencampur skema tabel yang beda tanggung jawab.

Dua tabel:
- chat_sessions   : satu baris per sesi/percakapan (id, judul,
                    riwayat mentah dalam bentuk JSON, timestamp)
- chat_turns      : satu baris per giliran user/assistant, khusus
                    untuk direkonstruksi di UI saat sesi dibuka
                    ulang (termasuk 'steps' timeline tool)

raw_history disimpan sebagai JSON blob dan di-OVERWRITE utuh tiap
kali ada giliran baru (bukan di-append per baris) - ini pilihan
sengaja untuk kesederhanaan: skala data personal/lokal seperti ini
kecil, jadi overhead rewrite penuh tidak masalah, dan implementasi
jauh lebih simpel dibanding sinkronisasi incremental.

Taruh file ini di: agent/memory_store/chat_sessions.py
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import closing


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "chat_sessions.db"

DATA_DIR.mkdir(exist_ok=True)

DEFAULT_TITLE = "Chat baru"


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    with closing(_connect()) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                raw_history TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                steps_json TEXT,
                created_at REAL NOT NULL
            )
        """)

        conn.commit()


init_db()


# ============================================================
# SESSIONS
# ============================================================

def create_session(initial_title=None):

    session_id = uuid.uuid4().hex[:12]
    now = time.time()
    title = initial_title or DEFAULT_TITLE

    with closing(_connect()) as conn:

        conn.execute(
            "INSERT INTO chat_sessions "
            "(id, title, raw_history, created_at, updated_at) "
            "VALUES (?, ?, '[]', ?, ?)",
            (session_id, title, now, now),
        )

        conn.commit()

    return {
        "id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }


def list_sessions():

    with closing(_connect()) as conn:

        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions "
            "ORDER BY updated_at DESC"
        ).fetchall()

    return [dict(row) for row in rows]


def get_session_row(session_id):

    with closing(_connect()) as conn:

        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    return dict(row) if row else None


def load_raw_history(session_id):

    row = get_session_row(session_id)

    if not row:
        return None

    try:
        return json.loads(row["raw_history"])
    except (json.JSONDecodeError, TypeError):
        return []


def save_raw_history(session_id, history):

    now = time.time()

    with closing(_connect()) as conn:

        conn.execute(
            "UPDATE chat_sessions SET raw_history = ?, updated_at = ? "
            "WHERE id = ?",
            (json.dumps(history, ensure_ascii=False), now, session_id),
        )

        conn.commit()


def maybe_autotitle(session_id, first_user_message):
    """
    Judul sesi otomatis diisi dari pesan pertama user, TAPI hanya
    kalau judulnya masih default ("Chat baru") - supaya tidak
    menimpa judul yang sudah di-rename manual oleh user.
    """

    row = get_session_row(session_id)

    if not row or row["title"] != DEFAULT_TITLE:
        return

    title = first_user_message.strip().replace("\n", " ")

    if len(title) > 48:
        title = title[:48].rstrip() + "..."

    if not title:
        return

    with closing(_connect()) as conn:

        conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )

        conn.commit()


def rename_session(session_id, title):

    if not get_session_row(session_id):
        return False

    with closing(_connect()) as conn:

        conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), session_id),
        )

        conn.commit()

    return True


def delete_session(session_id):

    with closing(_connect()) as conn:

        cursor = conn.execute(
            "DELETE FROM chat_sessions WHERE id = ?",
            (session_id,),
        )

        conn.execute(
            "DELETE FROM chat_turns WHERE session_id = ?",
            (session_id,),
        )

        conn.commit()

        return cursor.rowcount > 0


# ============================================================
# TURNS (transkrip untuk ditampilkan ulang di UI)
# ============================================================

def add_turn(session_id, role, content, steps=None):

    now = time.time()

    steps_json = (
        json.dumps(steps, ensure_ascii=False)
        if steps is not None else None
    )

    with closing(_connect()) as conn:

        conn.execute(
            "INSERT INTO chat_turns "
            "(session_id, role, content, steps_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, steps_json, now),
        )

        conn.commit()


def get_turns(session_id):

    with closing(_connect()) as conn:

        rows = conn.execute(
            "SELECT role, content, steps_json, created_at FROM chat_turns "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()

    turns = []

    for row in rows:

        item = dict(row)
        raw_steps = item.pop("steps_json")
        item["steps"] = json.loads(raw_steps) if raw_steps else []
        turns.append(item)

    return turns
