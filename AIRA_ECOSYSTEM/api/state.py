"""
api/state.py — cache in-memory ConversationMemory per sesi, di atas
penyimpanan permanen di core/chat_sessions.py (SQLite).
"""

from core.memory import ConversationMemory
from core import chat_sessions as store

_MEMORY_CACHE: dict[str, ConversationMemory] = {}

_GLOBAL_USAGE = {
    "session_prompt_tokens": 0,
    "session_completion_tokens": 0,
    "session_total_tokens": 0,
}


def get_memory(session_id: str) -> ConversationMemory:
    if session_id in _MEMORY_CACHE:
        return _MEMORY_CACHE[session_id]

    memory = ConversationMemory()
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
    if not usage:
        return
    _GLOBAL_USAGE["session_prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
    _GLOBAL_USAGE["session_completion_tokens"] += usage.get("completion_tokens", 0) or 0
    _GLOBAL_USAGE["session_total_tokens"] += usage.get("total_tokens", 0) or 0


def get_global_usage() -> dict:
    return dict(_GLOBAL_USAGE)
