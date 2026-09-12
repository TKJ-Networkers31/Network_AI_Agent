"""
core/memory.py — satu-satunya lapisan memory AIRA.

Port dari agent/core/memory.py (ConversationMemory) + agent/memory_store/
long_term.py (facts & events lintas sesi). Aturan keras: semua storage
lewat SQLite di folder database/, TIDAK ADA file JSON.

FIX (Phase 0 Stabilization - token tracker hilang):
Versi sebelumnya menghapus TokenTracker per-sesi yang ada di sistem lama
(agent/utils/token_tracker.py + ConversationMemory.token_tracker), diganti
counter global lintas-sesi di api/state.py yang tercampur semua sesi jadi
satu dan tidak bisa diakses dari run_chat.py (mode terminal). TokenTracker
dikembalikan di sini, dipasang balik ke ConversationMemory, supaya
pemakaian token PER SESI bisa dipantau lagi seperti dulu - penting karena
provider gratis (OpenRouter Nemotron) punya rate-limit dan model lokal
(Ollama) performanya dipantau di hardware terbatas.
"""

import sqlite3
import time
import logging
from pathlib import Path
from contextlib import closing
from typing import Any, Optional

logger = logging.getLogger("aira.memory")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "long_term_memory.db"

DATABASE_DIR.mkdir(exist_ok=True)


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
# TOKEN TRACKER (per-sesi, dipasang ke ConversationMemory)
# ============================================================

class TokenTracker:
    """
    Pelacak token untuk SATU sesi percakapan (satu instance
    ConversationMemory). Port dari agent/utils/token_tracker.py yang
    sempat hilang saat migrasi ke AIRA_ECOSYSTEM.

    Catatan:
    - Ollama (lokal) cuma melaporkan token dipakai per request
      (prompt_eval_count, eval_count) - tidak ada konsep kuota
      tersisa.
    - Provider eksternal (OpenRouter) melaporkan usage per request
      lewat field 'usage'. Untuk saldo/kuota tersisa, itu di luar
      cakupan tracker ini - lihat
      agents/rei/provider_client.py::get_openrouter_credits().
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_total_tokens = 0
        self.last_usage: Optional[dict] = None

    def add(self, usage: Optional[dict]) -> None:
        if not usage:
            return

        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        total = usage.get("total_tokens") or (prompt + completion)

        self.session_prompt_tokens += prompt
        self.session_completion_tokens += completion
        self.session_total_tokens += total

        self.last_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    def summary_line(self) -> Optional[str]:
        if self.session_total_tokens == 0:
            return None

        last = ""
        if self.last_usage:
            last = f" (giliran ini: {self.last_usage['total_tokens']} token)"

        return (
            f"Token sesi: {self.session_total_tokens} total "
            f"(prompt: {self.session_prompt_tokens}, "
            f"completion: {self.session_completion_tokens}){last}"
        )

    def as_dict(self) -> dict:
        return {
            "session_prompt_tokens": self.session_prompt_tokens,
            "session_completion_tokens": self.session_completion_tokens,
            "session_total_tokens": self.session_total_tokens,
            "last_usage": self.last_usage,
        }


# ============================================================
# CONVERSATION MEMORY (per-sesi, dikirim ke REI tiap giliran)
# ============================================================

class ConversationMemory:
    """
    Port 1:1 dari agent/core/memory.py, dengan dua perbedaan:
    1. system prompt sekarang datang dari core.persona.build_system_prompt()
       lewat parameter get_messages(system_prompt), bukan disimpan statis
       di sini.
    2. FIX: token_tracker per-sesi dikembalikan (lihat TokenTracker di
       atas) - sempat hilang saat migrasi.
    """

    def __init__(self, max_history_messages: int = 30):
        self.max_history_messages = max_history_messages
        self.history: list[dict[str, Any]] = []
        self.token_tracker = TokenTracker()

    def reset(self) -> None:
        self.history = []
        self.token_tracker.reset()
        logger.info("MEMORY RESET | riwayat percakapan & token tracker dikosongkan.")

    def add_user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})

    def add_message(self, message: dict) -> None:
        self.history.append(message)

    def add_tool_result(self, content: str, tool_call_id: str | None = None) -> None:
        message: dict[str, Any] = {"role": "tool", "content": content}
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        self.history.append(message)

    def get_messages(self, system_prompt: str) -> list[dict]:
        self._trim()
        return [{"role": "system", "content": system_prompt}] + self.history

    def _trim(self) -> None:
        if len(self.history) <= self.max_history_messages:
            return

        overflow = len(self.history) - self.max_history_messages
        cut_index = self._find_safe_cut_index(overflow)

        removed = self.history[:cut_index]
        self.history = self.history[cut_index:]

        if removed:
            logger.info(
                f"MEMORY TRIM | menghapus {len(removed)} pesan lama dari riwayat."
            )

    def _find_safe_cut_index(self, start_index: int) -> int:
        """
        Cari titik potong aman: tepat sebelum pesan role="user", supaya
        tidak memotong tengah pasangan assistant(tool_calls) -> tool result
        yang bisa merusak format pesan yang dikirim ke LLM.
        """
        cut_index = start_index

        while cut_index < len(self.history):
            if self.history[cut_index].get("role") == "user":
                return cut_index
            cut_index += 1

        return len(self.history)


# ============================================================
# FACTS (key-value, persisten, di-overwrite kalau key sama)
# ============================================================

def remember_fact(key: str, value: str) -> dict:
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

    return {"success": True, "key": key, "value": value}


def forget_fact(key: str) -> dict:
    with closing(_connect()) as conn:
        cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        conn.commit()
        deleted = cursor.rowcount > 0

    return {"success": deleted, "key": key}


def get_all_facts() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM facts ORDER BY updated_at DESC"
        ).fetchall()

    return [dict(row) for row in rows]


def recall_facts(query: str, limit: int = 5) -> list[dict]:
    """Pencarian sederhana berbasis keyword (LIKE)."""
    keywords = [w for w in query.lower().split() if len(w) > 2]

    if not keywords:
        return get_all_facts()[:limit]

    conditions = " OR ".join(
        "LOWER(key) LIKE ? OR LOWER(value) LIKE ?" for _ in keywords
    )

    params: list[Any] = []
    for word in keywords:
        params.extend([f"%{word}%", f"%{word}%"])
    params.append(limit)

    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT key, value, updated_at FROM facts "
            f"WHERE {conditions} ORDER BY updated_at DESC LIMIT ?",
            params,
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# EVENTS (log observasi/alert, append-only)
# ============================================================

def log_event(category: str, message: str, device: str | None = None, severity: str = "info") -> dict:
    now = time.time()

    with closing(_connect()) as conn:
        conn.execute("""
            INSERT INTO events (category, device, message, severity, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (category, device, message, severity, now))
        conn.commit()

    return {"success": True, "category": category, "device": device, "message": message}


def get_recent_events(limit: int = 10, device: str | None = None, category: str | None = None) -> list[dict]:
    query = "SELECT * FROM events"
    conditions = []
    params: list[Any] = []

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
# CONTEXT INJECTION (dipakai core/persona.py::build_system_prompt)
# ============================================================

def build_context_snippet(max_facts: int = 10, max_events: int = 5) -> str:
    facts = get_all_facts()[:max_facts]
    events = get_recent_events(limit=max_events)

    if not facts and not events:
        return ""

    lines = ["=== LONG-TERM MEMORY ==="]

    if facts:
        lines.append("Fakta yang sudah diketahui dari sesi sebelumnya:")
        for fact in facts:
            lines.append(f"- {fact['key']}: {fact['value']}")

    if events:
        lines.append("")
        lines.append("Kejadian/observasi terakhir yang tercatat:")
        for event in events:
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(event["created_at"]))
            device_part = f" [{event['device']}]" if event["device"] else ""
            lines.append(f"- ({timestamp}){device_part} {event['message']}")

    return "\n".join(lines)