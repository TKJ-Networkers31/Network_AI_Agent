"""
core/selection/builder.py — SelectionBuilder: input mentah -> SelectionContext,
dan pembangun SelectionContextPacket / ContextActionRequest.

Tidak membuat Context Builder baru dan tidak mengimpor core.context. Lookup
pesan (untuk validasi message_id/session_id) memakai core.chat_sessions yang
SUDAH ADA lewat dependency injection (default lazy import) - sama seperti
pola core/context/builder.py menyuntik provider secara opsional.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.selection.constants import (
    VALID_SOURCE_TYPES, VALID_ACTIONS,
    DEFAULT_SURROUNDING_WINDOW, MAX_SELECTED_TEXT_CHARS, MAX_SURROUNDING_TEXT_CHARS,
)
from core.selection.models import (
    SelectionContext, SelectionContextPacket, ContextActionRequest, SelectionResult,
)

MessageLookup = Callable[[str, Optional[str]], Optional[dict]]


def _default_message_lookup(message_id: str, session_id: Optional[str]) -> Optional[dict]:
    """message_id di sini adalah id baris chat_turns (lihat core/chat_sessions.py::get_turn).
    Tanpa session_id, tidak bisa divalidasi (chat_turns tidak diindeks per id
    global) - dianggap 'tidak diketahui', BUKAN 'tidak valid'."""
    if not session_id:
        return None

    try:
        turn_id = int(message_id)
    except (TypeError, ValueError):
        return None

    from core import chat_sessions as store
    return store.get_turn(session_id, turn_id)


def _extract_surrounding(
    full_text: str,
    selected_text: str,
    start_offset: Optional[int],
    end_offset: Optional[int],
    window: int = DEFAULT_SURROUNDING_WINDOW,
) -> str:
    """Ambil teks di sekitar selection, TANPA menyertakan selected_text itu
    sendiri (supaya tidak dobel saat digabung ke prompt). Deterministik."""
    if not full_text:
        return ""

    if start_offset is None or end_offset is None:
        idx = full_text.find(selected_text)
        if idx == -1:
            return full_text[:MAX_SURROUNDING_TEXT_CHARS]
        start_offset, end_offset = idx, idx + len(selected_text)

    start_offset = max(0, min(start_offset, len(full_text)))
    end_offset = max(start_offset, min(end_offset, len(full_text)))

    win_start = max(0, start_offset - window)
    win_end = min(len(full_text), end_offset + window)

    prefix = ("…" if win_start > 0 else "") + full_text[win_start:start_offset]
    suffix = full_text[end_offset:win_end] + ("…" if win_end < len(full_text) else "")

    combined = (prefix + "\n[...]\n" + suffix) if prefix and suffix else (prefix or suffix)

    return combined[:MAX_SURROUNDING_TEXT_CHARS]


class SelectionBuilder:

    def __init__(self, message_lookup: Optional[MessageLookup] = None):
        self._message_lookup = message_lookup or _default_message_lookup

    def build(
        self,
        *,
        selected_text: str,
        source_type: str = "message",
        message_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        full_text: Optional[str] = None,
        start_offset: Optional[int] = None,
        end_offset: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        require_message: bool = False,
    ) -> SelectionResult:
        errors: list[str] = []

        cleaned = (selected_text or "").strip()
        if not cleaned:
            errors.append("selected_text tidak boleh kosong.")

        if source_type not in VALID_SOURCE_TYPES:
            errors.append(f"source_type '{source_type}' tidak dikenal.")

        message = None
        if message_id is not None:
            message = self._message_lookup(message_id, session_id)
            if message is None and (require_message or session_id):
                errors.append(f"message_id '{message_id}' tidak ditemukan untuk session '{session_id}'.")

        if errors:
            return SelectionResult(success=False, errors=errors, selection=None)

        text_for_context = full_text
        if text_for_context is None and message is not None:
            text_for_context = message.get("content")
        if text_for_context is None:
            text_for_context = cleaned

        surrounding = _extract_surrounding(text_for_context, cleaned, start_offset, end_offset)

        selection = SelectionContext(
            selected_text=cleaned[:MAX_SELECTED_TEXT_CHARS],
            surrounding_text=surrounding,
            source_type=source_type,
            message_id=message_id,
            conversation_id=conversation_id or session_id,
            session_id=session_id,
            start_offset=start_offset,
            end_offset=end_offset,
            metadata=dict(metadata or {}),
        )

        return SelectionResult(success=True, errors=[], selection=selection)


def build_context_packet(
    selection: SelectionContext,
    user_question: str = "",
    action: Optional[str] = None,
) -> SelectionContextPacket:
    return SelectionContextPacket(
        message_id=selection.message_id,
        selected_text=selection.selected_text,
        surrounding_text=selection.surrounding_text,
        user_question=(user_question or "").strip(),
        conversation_id=selection.conversation_id,
        session_id=selection.session_id,
        start_offset=selection.start_offset,
        end_offset=selection.end_offset,
        action=action,
    )


def validate_action(action: str) -> Optional[str]:
    """Return pesan error, atau None kalau valid."""
    if action not in VALID_ACTIONS:
        return f"Aksi '{action}' tidak dikenal. Pilihan: {sorted(VALID_ACTIONS)}."
    return None


def build_action_request(
    selection: SelectionContext,
    action: str,
    user_question: str = "",
) -> tuple[Optional[ContextActionRequest], Optional[str]]:
    """(request, None) kalau sukses, (None, error) kalau aksi tidak dikenal."""
    error = validate_action(action)
    if error:
        return None, error

    packet = build_context_packet(selection, user_question=user_question, action=action)
    request = ContextActionRequest(action=action, packet=packet, selection_id=selection.selection_id)

    return request, None