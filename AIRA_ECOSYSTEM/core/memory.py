"""
core/memory.py — satu-satunya lapisan memory AIRA.

Menggabungkan dua konsep yang di repo lama terpisah:
  - agent/core/memory.py       -> ConversationMemory (riwayat per-sesi, trimming)
  - agent/memory_store/long_term.py -> facts & events lintas sesi (SQLite)
  - agent/memory_store/chat_sessions.py -> sesi chat untuk web UI (SQLite)

Aturan keras dari master prompt: "Jangan menyimpan memory di file JSON" -
semua tabel di bawah WAJIB SQLite, disimpan di folder `database/`
(bukan lagi `data/` seperti repo lama).

TODO migrasi konkret:
  1. Copy isi agent/memory_store/long_term.py ke sini, ganti
     DB_FILE = BASE_DIR / "database" / "long_term_memory.db"
  2. Copy isi agent/memory_store/chat_sessions.py ke sini (atau file
     terpisah core/chat_sessions.py, sama-sama diimpor dari sini) dengan
     DB_FILE serupa di folder `database/`.
  3. Class ConversationMemory di bawah adalah port 1:1 dari
     agent/core/memory.py, tidak ada perubahan logic - cuma pindah folder.
"""

import logging
from typing import Any

logger = logging.getLogger("aira.memory")


class ConversationMemory:
    """
    Riwayat percakapan satu sesi AIRA (dikirim ke REI setiap giliran).

    TODO: port persis dari agent/core/memory.py (system_prompt sekarang
    datang dari core.persona.build_system_prompt(), bukan string statis).
    """

    def __init__(self, max_history_messages: int = 30):
        self.max_history_messages = max_history_messages
        self.history: list[dict[str, Any]] = []

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

    def reset(self) -> None:
        self.history = []
        logger.info("MEMORY RESET | riwayat percakapan dikosongkan.")

    def _trim(self) -> None:
        if len(self.history) <= self.max_history_messages:
            return
        # TODO: port _find_safe_cut_index dari agent/core/memory.py (jangan
        # potong tepat di tengah pasangan assistant(tool_calls) -> tool result).
        overflow = len(self.history) - self.max_history_messages
        self.history = self.history[overflow:]


# ---------------------------------------------------------------------------
# Long-term facts & events (lintas sesi) - TODO: port dari
# agent/memory_store/long_term.py, ganti path DB ke database/long_term_memory.db
# ---------------------------------------------------------------------------

def remember_fact(key: str, value: str) -> dict:
    raise NotImplementedError("TODO: port dari agent/memory_store/long_term.py")


def recall_facts(query: str, limit: int = 5) -> list[dict]:
    raise NotImplementedError("TODO: port dari agent/memory_store/long_term.py")


def forget_fact(key: str) -> dict:
    raise NotImplementedError("TODO: port dari agent/memory_store/long_term.py")


def build_context_snippet(max_facts: int = 10, max_events: int = 5) -> str:
    raise NotImplementedError("TODO: port dari agent/memory_store/long_term.py")
