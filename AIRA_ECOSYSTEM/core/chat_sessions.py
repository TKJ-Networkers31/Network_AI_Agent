"""
core/chat_sessions.py — penyimpanan SESI CHAT untuk web UI.

FIX (Optimalisasi DIO):
Kolom baru 'interaction_schema_json' di tabel chat_turns, ditambahkan
lewat migrasi ALTER TABLE idempotent (aman untuk database lama yang
sudah ada tanpa kolom ini) - menyimpan Universal Interaction Schema DIO
per giliran assistant, supaya begitu user reload/reopen sesi, form
interaktif yang belum di-submit tetap bisa direkonstruksi frontend.

PERUBAHAN (Chat Session: edit prompt / regenerate):
- add_turn() sekarang MENGEMBALIKAN id baris (INTEGER) - sebelumnya None.
  Caller lama (api/routers/chat.py) yang mengabaikan return value tidak
  terpengaruh.
- get_turns() sekarang ikut mengembalikan key 'id' per turn, dipakai
  frontend sebagai identitas stabil pesan (bukan index array).
- Helper baru: get_turn, count_user_turns_from, truncate_turns_from,
  truncate_history_by_user_turns, find_user_message_from_end. Semuanya
  dipakai api/routers/ws.py untuk edit prompt & regenerate.

Catatan desain truncate: pesan role="user" di raw_history (riwayat LLM)
berpasangan 1:1 dengan turn role="user" di chat_turns (urut waktu). Jadi
"buang N turn user terakhir" di chat_turns == "potong raw_history tepat
sebelum pesan user ke-N dari belakang". Kalau raw_history sudah pernah
di-trim (max 30 pesan) dan target sudah tidak ada di dalamnya, hasilnya
riwayat kosong - benar secara logika, karena semua yang tersisa berada
SETELAH titik potong.
"""

import json
import sqlite3
import time
import uuid
import logging
from pathlib import Path
from contextlib import closing

logger = logging.getLogger("aira.chat_sessions")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "chat_sessions.db"

DATABASE_DIR.mkdir(exist_ok=True)

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
                interaction_schema_json TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()

    _migrate_add_columns()


def _migrate_add_columns() -> None:
    """Migrasi idempotent untuk database lama yang dibuat sebelum kolom
    interaction_schema_json ada. CREATE TABLE IF NOT EXISTS di atas TIDAK
    menambah kolom ke tabel yang sudah ada - migrasi manual ini yang
    melakukannya, aman dijalankan berkali-kali."""
    with closing(_connect()) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(chat_turns)").fetchall()]

        if "interaction_schema_json" not in columns:
            conn.execute("ALTER TABLE chat_turns ADD COLUMN interaction_schema_json TEXT")
            conn.commit()
            logger.info("MIGRATION | kolom interaction_schema_json ditambahkan ke chat_turns.")


init_db()


def create_session(initial_title: str | None = None) -> dict:
    session_id = uuid.uuid4().hex[:12]
    now = time.time()
    title = initial_title or DEFAULT_TITLE

    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, title, raw_history, created_at, updated_at) "
            "VALUES (?, ?, '[]', ?, ?)",
            (session_id, title, now, now),
        )
        conn.commit()

    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}


def list_sessions() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_session_row(session_id: str) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def load_raw_history(session_id: str) -> list | None:
    row = get_session_row(session_id)
    if not row:
        return None
    try:
        return json.loads(row["raw_history"])
    except (json.JSONDecodeError, TypeError):
        return []


def save_raw_history(session_id: str, history: list) -> None:
    now = time.time()
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE chat_sessions SET raw_history = ?, updated_at = ? WHERE id = ?",
            (json.dumps(history, ensure_ascii=False), now, session_id),
        )
        conn.commit()


def maybe_autotitle(session_id: str, first_user_message: str) -> None:
    row = get_session_row(session_id)
    if not row or row["title"] != DEFAULT_TITLE:
        return

    title = first_user_message.strip().replace("\n", " ")
    if len(title) > 48:
        title = title[:48].rstrip() + "..."
    if not title:
        return

    with closing(_connect()) as conn:
        conn.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()


def rename_session(session_id: str, title: str) -> bool:
    if not get_session_row(session_id):
        return False

    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), session_id),
        )
        conn.commit()

    return True


def delete_session(session_id: str) -> bool:
    with closing(_connect()) as conn:
        cursor = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.execute("DELETE FROM chat_turns WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0


def add_turn(
    session_id: str,
    role: str,
    content: str,
    steps: list | None = None,
    interaction_schema: dict | None = None,
) -> int:
    """Simpan satu turn. Return: id baris (chat_turns.id)."""
    now = time.time()
    steps_json = json.dumps(steps, ensure_ascii=False) if steps is not None else None
    schema_json = json.dumps(interaction_schema, ensure_ascii=False) if interaction_schema is not None else None

    with closing(_connect()) as conn:
        cursor = conn.execute(
            "INSERT INTO chat_turns "
            "(session_id, role, content, steps_json, interaction_schema_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, steps_json, schema_json, now),
        )
        conn.commit()
        return cursor.lastrowid


def get_turns(session_id: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, role, content, steps_json, interaction_schema_json, created_at FROM chat_turns "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()

    turns = []
    for row in rows:
        item = dict(row)
        raw_steps = item.pop("steps_json")
        raw_schema = item.pop("interaction_schema_json")
        item["steps"] = json.loads(raw_steps) if raw_steps else []
        item["interaction_schema"] = json.loads(raw_schema) if raw_schema else None
        turns.append(item)

    return turns


# ============================================================
# EDIT PROMPT / REGENERATE
# ============================================================

def get_turn(session_id: str, turn_id: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, role, content FROM chat_turns WHERE session_id = ? AND id = ?",
            (session_id, turn_id),
        ).fetchone()
    return dict(row) if row else None


def count_user_turns_from(session_id: str, from_turn_id: int) -> int:
    """Berapa turn role='user' yang akan terbuang kalau dipotong mulai
    dari from_turn_id (inklusif). READ-ONLY - tidak mengubah data."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM chat_turns "
            "WHERE session_id = ? AND id >= ? AND role = 'user'",
            (session_id, from_turn_id),
        ).fetchone()
    return int(row["c"]) if row else 0


def truncate_turns_from(session_id: str, from_turn_id: int) -> int:
    """Hapus turn dengan id >= from_turn_id di sesi ini. Return jumlah
    baris terhapus. Dipanggil HANYA setelah giliran pengganti sukses,
    supaya stop/error di tengah jalan tidak menghilangkan data lama."""
    with closing(_connect()) as conn:
        cursor = conn.execute(
            "DELETE FROM chat_turns WHERE session_id = ? AND id >= ?",
            (session_id, from_turn_id),
        )
        conn.commit()
        return cursor.rowcount


def truncate_history_by_user_turns(history: list, user_turns_to_drop: int) -> list:
    """Kembalikan SALINAN history yang sudah dipotong tepat sebelum pesan
    user ke-N dari belakang (N = user_turns_to_drop). Fungsi murni."""
    if user_turns_to_drop <= 0:
        return list(history)

    user_indices = [
        i for i, m in enumerate(history)
        if isinstance(m, dict) and m.get("role") == "user"
    ]

    if user_turns_to_drop > len(user_indices):
        return []

    return list(history[: user_indices[-user_turns_to_drop]])


def find_user_message_from_end(history: list, n_from_end: int) -> str | None:
    """Isi pesan user ke-N dari belakang di raw_history (pesan persis yang
    dulu dikirim ke LLM, termasuk hasil rewrite slash-command/DIO). None
    kalau sudah tidak ada (mis. sudah ter-trim)."""
    user_messages = [
        m for m in history
        if isinstance(m, dict) and m.get("role") == "user"
    ]

    if n_from_end < 1 or n_from_end > len(user_messages):
        return None

    return user_messages[-n_from_end].get("content")