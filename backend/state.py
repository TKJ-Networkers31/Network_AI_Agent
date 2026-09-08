"""
Penyimpanan sesi percakapan di memory proses backend.

Desain sengaja SEDERHANA (single-process, in-memory dict) karena
project ini dipakai personal/lokal, bukan multi-tenant production.
Kalau nanti mau deploy multi-user beneran, ganti dict ini dengan
Redis atau simpan per-user di DB - tapi untuk kebutuhan sekarang
ini paling ringan dan cukup.

session_id default "default" dipakai kalau frontend tidak kirim
session_id sama sekali (mirip perilaku agent/main.py yang cuma
punya satu ConversationMemory per proses).
"""

from agent.core.memory import ConversationMemory
from agent.core.engine import SYSTEM_PROMPT


_SESSIONS: dict[str, ConversationMemory] = {}


def get_session(session_id: str = "default") -> ConversationMemory:

    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = ConversationMemory(
            system_prompt=SYSTEM_PROMPT
        )

    return _SESSIONS[session_id]


def reset_session(session_id: str = "default") -> None:

    session = get_session(session_id)
    session.reset()


def list_session_ids():
    return list(_SESSIONS.keys())
