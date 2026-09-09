"""
Cache in-memory dari ConversationMemory per sesi chat, DI ATAS
penyimpanan permanen di agent/memory_store/chat_sessions.py
(SQLite).

Kenapa dua lapis (cache + DB):
- ConversationMemory (format pesan untuk dikirim ke LLM) dipakai
  berkali-kali dalam satu sesi berjalan - cache di RAM supaya
  tidak perlu deserialize JSON dari DB tiap giliran chat.
- Tapi begitu backend restart, cache RAM hilang. Makanya tiap
  sesi yang belum ada di cache akan di-"rehydrate" dari
  raw_history yang tersimpan di SQLite (lihat get_memory()) -
  jadi "lanjut sesi lama" tetap jalan walau server sempat mati.

Token tracker SENGAJA tidak ikut dipersist (cukup di RAM) - itu
cuma metadata pemakaian, bukan konteks percakapan, jadi reset ke
0 tiap restart backend itu wajar dan tidak masalah.
"""

from agent.core.memory import ConversationMemory
from agent.core.engine import SYSTEM_PROMPT
from agent.memory_store import chat_sessions as store


_MEMORY_CACHE: dict[str, ConversationMemory] = {}

_GLOBAL_USAGE = {
    "session_prompt_tokens": 0,
    "session_completion_tokens": 0,
    "session_total_tokens": 0,
}


def get_memory(session_id: str) -> ConversationMemory:

    if session_id in _MEMORY_CACHE:
        return _MEMORY_CACHE[session_id]

    memory = ConversationMemory(system_prompt=SYSTEM_PROMPT)

    raw_history = store.load_raw_history(session_id)

    if raw_history:
        memory.history = raw_history

    _MEMORY_CACHE[session_id] = memory

    return memory


def persist_memory(session_id: str, memory: ConversationMemory) -> None:
    store.save_raw_history(session_id, memory.history)


def drop_cache(session_id: str) -> None:
    _MEMORY_CACHE.pop(session_id, None)


def add_global_usage(usage) -> None:
    """
    Akumulasi pemakaian token lintas SEMUA sesi selama proses
    backend hidup - dipakai di halaman Settings sebagai gambaran
    kasar pemakaian, bukan per-sesi (karena user bisa punya banyak
    sesi chat sekarang).
    """

    if not usage:
        return

    _GLOBAL_USAGE["session_prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
    _GLOBAL_USAGE["session_completion_tokens"] += usage.get("completion_tokens", 0) or 0
    _GLOBAL_USAGE["session_total_tokens"] += usage.get("total_tokens", 0) or 0


def get_global_usage() -> dict:
    return dict(_GLOBAL_USAGE)
