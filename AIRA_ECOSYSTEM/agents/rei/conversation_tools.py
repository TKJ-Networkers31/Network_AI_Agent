"""
agents/rei/conversation_tools.py — adapter tool "conversation_history" untuk REI
(Sprint 2.6 / Worker 2).

Wrapper tipis (pola sama dengan agents/rei/fs_tools.py) di atas
core/conversation_context.py. Semua logika baca ada di layanan itu; file ini
hanya: (1) mengikat tool ke SESI AKTIF, (2) mengubah hasil/error jadi dict
tool ({"success", "tool", ...}), (3) menyediakan kontrak + skema function-calling.

STATUS: BELUM DIDAFTARKAN. Tidak ada perubahan pada agents/rei/registry.py,
agents/rei/planner.py, maupun core/orchestrator.py. Cara mendaftarkannya ada
di bagian "INTEGRASI" di bawah.

KONTRAK
-------
Nama logis (konseptual) -> nama tool di wire:

    conversation_history.recent   -> conversation_history_recent
    conversation_history.search   -> conversation_history_search
    conversation_history.summary  -> conversation_history_summary

Nama di wire memakai underscore karena nama function OpenAI-style hanya boleh
[a-zA-Z0-9_-] - titik ditolak provider.

KEAMANAN: SESI DIIKAT DARI SISI SERVER, BUKAN DARI LLM
-------------------------------------------------------
Skema tool SENGAJA tidak punya parameter session_id. Kalau LLM menyebutkannya
juga, nilainya DIABAIKAN (kelebihan argumen ditampung **ignored) dan hasilnya
diberi peringatan. Sesi yang dibaca hanya sesi dari event_scope(session_id=...)
milik giliran yang sedang berjalan (api/routers/ws.py membukanya untuk setiap
giliran, dan konteksnya ikut ke thread pekerja lewat asyncio.to_thread).
Dengan begitu LLM tidak bisa membaca sesi lain, tanpa perlu mengubah planner.

Konsekuensinya: tanpa event_scope berisi session_id (mis. REST /api/chat, yang
belum membuka event_scope - lihat docs/roadmap.md, dan mode terminal) tool
mengembalikan success=False "tidak ada sesi aktif". Gagal aman, bukan bocor.

INTEGRASI (dilakukan oleh integrator, bukan file ini)
------------------------------------------------------
Di agents/rei/registry.py (tambahan murni, tidak mengubah tool yang ada):

    from agents.rei import conversation_tools as ct
    REI_TOOLS.update(ct.CONVERSATION_TOOLS)
    REI_TOOL_CATEGORY.update(ct.CONVERSATION_TOOL_CATEGORY)
    REI_TOOL_SCHEMAS.extend(ct.CONVERSATION_TOOL_SCHEMAS)

core/orchestrator.py tidak perlu disentuh (otomatis menggabungkan registry REI).
Alternatif: kalau kelak planner memang mau menyisipkan session_id sendiri (pola
SESSION_AWARE_TOOLS untuk request_location_permission), tambahkan nama tool ke
himpunan itu DAN ubah _active_session_id() di sini; jangan pernah menerima
session_id dari argumen yang datang dari LLM tanpa penimpaan oleh planner.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from core.conversation_context import (
    DEFAULT_RECENT_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SUMMARY_LIMIT,
    MAX_LIMIT,
    ConversationContextError,
    InvalidRequestError,
    get_conversation_context,
)
from core.events import current_event_context

logger = logging.getLogger("aira.rei.conversation_tools")

TOOL_RECENT = "conversation_history_recent"
TOOL_SEARCH = "conversation_history_search"
TOOL_SUMMARY = "conversation_history_summary"

# nama logis (kontrak konseptual) -> nama tool di wire
TOOL_CONTRACT: dict[str, str] = {
    "conversation_history.recent": TOOL_RECENT,
    "conversation_history.search": TOOL_SEARCH,
    "conversation_history.summary": TOOL_SUMMARY,
}

NO_SESSION_ERROR = (
    "Tidak ada sesi chat aktif untuk dibaca riwayatnya "
    "(tool ini hanya bisa dipakai dari dalam sesi chat)."
)


# ------------------------------------------------------------------ helper

def _active_session_id() -> Optional[str]:
    """Sesi milik giliran yang sedang berjalan, dari event_scope (BUKAN dari LLM)."""
    value = current_event_context().get("session_id")

    return value if isinstance(value, str) and value.strip() else None


def _coerce_int(value: Any, name: str) -> Optional[int]:
    """LLM sering mengirim angka sebagai string ("5") atau float (5.0)."""
    if value is None or isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())

    raise InvalidRequestError(f"{name} harus berupa bilangan bulat.")


def _run(tool: str, ignored: dict, call: Callable[[Any, str], Any]) -> dict:
    session_id = _active_session_id()

    if session_id is None:
        return {"success": False, "tool": tool, "error": NO_SESSION_ERROR}

    try:
        payload = call(get_conversation_context(), session_id).to_dict()
    except ConversationContextError as exc:
        return {"success": False, "tool": tool, "error": str(exc)}
    except Exception:
        logger.exception("Tool %s gagal membaca riwayat percakapan.", tool)
        return {"success": False, "tool": tool, "error": "Gagal membaca riwayat percakapan."}

    result = {"success": True, "tool": tool, **payload}

    if "session_id" in ignored:
        result["warning"] = (
            "Argumen session_id diabaikan: tool ini hanya membaca sesi chat yang sedang aktif."
        )

    return result


# ------------------------------------------------------------------ tool

def conversation_history_recent(limit: Any = DEFAULT_RECENT_LIMIT, **ignored: Any) -> dict:
    """Giliran terbaru di sesi aktif, urut kronologis."""
    try:
        count = _coerce_int(limit, "limit")
    except InvalidRequestError as exc:
        return {"success": False, "tool": TOOL_RECENT, "error": str(exc)}

    return _run(TOOL_RECENT, ignored, lambda svc, sid: svc.recent(sid, count))


def conversation_history_search(query: Any = "", limit: Any = DEFAULT_SEARCH_LIMIT, **ignored: Any) -> dict:
    """Cari kata kunci di riwayat sesi aktif."""
    try:
        count = _coerce_int(limit, "limit")
    except InvalidRequestError as exc:
        return {"success": False, "tool": TOOL_SEARCH, "error": str(exc)}

    return _run(TOOL_SEARCH, ignored, lambda svc, sid: svc.search(sid, query, count))


def conversation_history_summary(limit: Any = DEFAULT_SUMMARY_LIMIT, **ignored: Any) -> dict:
    """Ringkasan ekstraktif deterministik riwayat sesi aktif."""
    try:
        count = _coerce_int(limit, "limit")
    except InvalidRequestError as exc:
        return {"success": False, "tool": TOOL_SUMMARY, "error": str(exc)}

    return _run(TOOL_SUMMARY, ignored, lambda svc, sid: svc.summary(sid, count))


# ------------------------------------------------------------------ registry-ready

CONVERSATION_TOOLS: dict = {
    TOOL_RECENT: conversation_history_recent,
    TOOL_SEARCH: conversation_history_search,
    TOOL_SUMMARY: conversation_history_summary,
}

# Kategori UI: "memory" dipilih karena sudah punya warna/ikon di frontend
# (ToolStep.jsx / LiveSteps.jsx). Kategori baru akan jatuh ke gaya "tool" default.
CONVERSATION_TOOL_CATEGORY: dict[str, str] = {name: "memory" for name in CONVERSATION_TOOLS}

# Semua tool ini murni baca -> tidak dangerous.
CONVERSATION_DANGEROUS_TOOLS: set[str] = set()

_LIMIT_DESC = f"Jumlah giliran (1-{MAX_LIMIT}; lebih dari itu dipotong ke {MAX_LIMIT})."

CONVERSATION_TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": TOOL_RECENT,
        "description": (
            "Membaca giliran percakapan TERBARU di chat yang sedang berlangsung ini "
            "(bukan chat lain), urut dari lama ke baru. Pakai kalau user bertanya soal "
            "yang dibicarakan sebelumnya ('tadi kita bahas apa', 'apa yang tadi kubilang') "
            "dan itu tidak ada lagi di konteks yang kamu lihat. BUKAN untuk fakta jangka "
            "panjang lintas sesi - untuk itu pakai 'recall'."
        ),
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": _LIMIT_DESC, "default": DEFAULT_RECENT_LIMIT},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": TOOL_SEARCH,
        "description": (
            "Mencari kata kunci di riwayat chat yang sedang berlangsung ini (bukan chat "
            "lain). Pencarian berbasis kata, tidak peka huruf besar/kecil; hasil diurutkan "
            "dari yang paling cocok. Pakai kalau user menyebut sesuatu yang pernah dibahas "
            "di chat ini tapi tidak terlihat lagi ('kemarin aku sebut IP router itu apa?'). "
            "Untuk fakta jangka panjang lintas sesi pakai 'recall'."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Kata kunci yang dicari (satu atau beberapa kata)."},
            "limit": {"type": "integer", "description": _LIMIT_DESC, "default": DEFAULT_SEARCH_LIMIT},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": TOOL_SUMMARY,
        "description": (
            "Mengambil gambaran ringkas terstruktur dari chat yang sedang berlangsung ini: "
            "jumlah giliran, permintaan pertama, permintaan/jawaban terakhir, kata yang "
            "sering muncul, dan kutipan giliran terbaru. Ini ekstraksi otomatis (bukan "
            "ringkasan yang ditulis model) - susun ringkasan naturalmu sendiri dari datanya."
        ),
        "parameters": {"type": "object", "properties": {
            "limit": {
                "type": "integer",
                "description": f"Jumlah giliran terakhir yang dikutip (1-{MAX_LIMIT}).",
                "default": DEFAULT_SUMMARY_LIMIT,
            },
        }, "required": []},
    }},
]