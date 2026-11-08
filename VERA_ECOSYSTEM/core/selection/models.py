"""
core/selection/models.py — bentuk data Selection Intelligence (Sprint 2.7 / W4).

HANYA data + serialisasi (dataclass murni), mengikuti pola core/dio/models.py
dan core/filesystem/models.py: tanpa I/O, tanpa database, tanpa reasoning.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from core.selection.constants import SOURCE_MESSAGE


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class SelectionContext:
    """Satu 'seleksi' user atas sebagian teks pesan/percakapan."""

    selected_text: str
    surrounding_text: str = ""
    selection_id: str = field(default_factory=lambda: _new_id("sel"))
    source_type: str = SOURCE_MESSAGE
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SelectionContext":
        data = data if isinstance(data, dict) else {}
        known = {
            "selected_text", "surrounding_text", "selection_id", "source_type",
            "message_id", "conversation_id", "session_id", "start_offset",
            "end_offset", "created_at", "metadata",
        }
        kwargs = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**kwargs)


@dataclass
class SelectionContextPacket:
    """
    Packet siap-kirim ke Capability Layer / Planner. Tidak menyentuh
    ContextBuilder - to_llm_instruction() menghasilkan teks instruksi yang
    bisa dibungkus ke `llm_message` yang SUDAH ada (pola sama dengan
    core/slash_commands.py::apply_slash_command), bukan lewat extra_context().
    """

    source: str = "selection"
    message_id: Optional[str] = None
    selected_text: str = ""
    surrounding_text: str = ""
    user_question: str = ""
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    action: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_llm_instruction(self) -> str:
        from core.selection.constants import ACTION_LABELS

        action_line = (
            f"[Aksi diminta: {ACTION_LABELS.get(self.action, self.action)}]\n"
            if self.action else ""
        )
        question = self.user_question.strip() or "Jelaskan/tindak-lanjuti bagian yang dipilih."
        surrounding_block = (
            f'Konteks sekitar (untuk memahami maksud, JANGAN dianggap sebagai bagian yang dipilih):\n"""\n{self.surrounding_text}\n"""\n'
            if self.surrounding_text else ""
        )

        return (
            "[Konteks: user memilih sebagian teks dari percakapan sebelumnya. "
            "Fokuskan jawaban pada teks yang dipilih ini.]\n"
            f"{action_line}"
            f'Teks yang dipilih:\n"""\n{self.selected_text}\n"""\n'
            f"{surrounding_block}"
            f"Permintaan user: {question}"
        )


@dataclass
class ContextActionRequest:
    """Kontrak permintaan aksi atas sebuah selection (input ke Capability Layer)."""

    action: str
    packet: SelectionContextPacket
    selection_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "selection_id": self.selection_id,
            "packet": self.packet.to_dict(),
        }


@dataclass
class SelectionResult:
    """Hasil pembangunan SelectionContext - tidak pernah raise (pola core/dio)."""

    success: bool
    selection: Optional[SelectionContext] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "selection": self.selection.to_dict() if self.selection else None,
            "errors": list(self.errors),
        }