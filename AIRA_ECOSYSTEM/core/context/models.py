"""
core/context/models.py — kontrak "Final Context" AIRA (Sprint 2 / Worker 1).

Satu representasi konteks runtime yang stabil. Dibentuk oleh
core/context/builder.py::ContextBuilder, dibawa Brain -> Orchestrator ->
Planner (REI). File ini HANYA bentuk data + serialisasi: tanpa I/O, tanpa
reasoning, dan tanpa import modul AIRA lain (aman diimpor di mana saja).

Dua kelompok section:

  PROMPT_SECTIONS  (runtime_state, memory, location)
      Teksnya disisipkan ke system prompt, TEPAT SEKALI, lewat
      AIRAContext.extra_context() -> PersonaEngine.build(extra_context).

  carried sections (identity, persona, tool_context)
      Hanya data untuk konsumen (log/UI/debug). TIDAK PERNAH disisipkan
      sebagai teks: identity & persona sudah disisipkan PersonaEngine, dan
      skema tool sudah dikirim ke provider lewat argumen `tools=`.

  user_input & task ikut dibawa tetapi juga tidak disisipkan ke system prompt
  (user_input dikirim sebagai pesan user; task = metadata routing).

Aturan "tidak ada injeksi ganda" ditegakkan di sini, secara struktural:
hanya PROMPT_SECTIONS yang bisa masuk ke extra_context().
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

CONTEXT_SCHEMA_VERSION = "1.0"

SECTION_IDENTITY = "identity"
SECTION_PERSONA = "persona"
SECTION_MEMORY = "memory"
SECTION_RUNTIME_STATE = "runtime_state"
SECTION_LOCATION = "location"
SECTION_TOOL_CONTEXT = "tool_context"

# Urutan kanonik (dipakai to_dict / present()).
ALL_SECTIONS = (
    SECTION_IDENTITY,
    SECTION_PERSONA,
    SECTION_MEMORY,
    SECTION_RUNTIME_STATE,
    SECTION_LOCATION,
    SECTION_TOOL_CONTEXT,
)

# Section yang teksnya boleh masuk system prompt, sesuai urutan yang selama ini
# terbentuk di prompt: waktu -> memori jangka panjang -> lokasi.
PROMPT_SECTIONS = (
    SECTION_RUNTIME_STATE,
    SECTION_MEMORY,
    SECTION_LOCATION,
)


def _json_safe(value: Any) -> Any:
    """Salinan yang PASTI JSON-serializable (objek asing -> str). Tidak raise."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _json_dict(value: Any) -> dict:
    safe = _json_safe(value)
    return safe if isinstance(safe, dict) else {"value": safe}


@dataclass
class ContextSection:
    """
    Satu potongan konteks.

    text : teks siap-prompt ("" = tidak disisipkan ke prompt).
    data : info terstruktur untuk konsumen non-prompt.
    source : asal data (mis. "persona", "memory") - hanya untuk observability.
    """

    name: str
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None

    @property
    def is_injectable(self) -> bool:
        return bool(self.text and self.text.strip())

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "text": self.text,
            "data": _json_dict(self.data),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextSection":
        return cls(
            name=str(data.get("name") or ""),
            text=str(data.get("text") or ""),
            data=dict(data.get("data") or {}),
            source=data.get("source"),
        )


@dataclass
class AIRAContext:
    """Final Context untuk satu giliran percakapan."""

    user_input: str = ""
    session_id: Optional[str] = None

    identity: Optional[ContextSection] = None
    persona: Optional[ContextSection] = None
    memory: Optional[ContextSection] = None
    runtime_state: Optional[ContextSection] = None
    location: Optional[ContextSection] = None
    tool_context: Optional[ContextSection] = None

    # Hasil klasifikasi (TaskClassification.to_dict()) kalau sudah ada.
    task: Optional[dict[str, Any]] = None

    # System prompt final: hasil PersonaEngine.build(extra_context()).
    system_prompt: str = ""

    # Section yang gagal dibuat (nama + tipe error, TANPA pesan error).
    warnings: list[str] = field(default_factory=list)

    version: str = CONTEXT_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------ inspeksi

    def sections(self) -> dict[str, ContextSection]:
        """Section yang ADA, urut kanonik."""
        return {
            name: getattr(self, name)
            for name in ALL_SECTIONS
            if getattr(self, name) is not None
        }

    def present(self) -> list[str]:
        return list(self.sections())

    def extra_context(self) -> str:
        """
        Teks tambahan untuk system prompt: HANYA PROMPT_SECTIONS yang punya
        teks, urut kanonik. Section lain tidak akan pernah muncul di sini.
        """
        parts = []

        for name in PROMPT_SECTIONS:
            section = getattr(self, name)

            if section is not None and section.is_injectable:
                parts.append(section.text.strip())

        return "\n\n".join(parts)

    def summary(self) -> dict:
        """Ringkasan aman untuk log (tanpa isi memori/lokasi)."""
        return {
            "sections": self.present(),
            "task": (self.task or {}).get("primary_label"),
            "prompt_chars": len(self.system_prompt or ""),
            "warnings": len(self.warnings),
        }

    # -------------------------------------------------------- serialisasi

    def to_dict(self, include_prompt: bool = True) -> dict:
        data: dict[str, Any] = {
            "version": self.version,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "task": _json_dict(self.task) if self.task is not None else None,
        }

        for name in ALL_SECTIONS:
            section = getattr(self, name)
            data[name] = section.to_dict() if section is not None else None

        data["warnings"] = list(self.warnings)

        if include_prompt:
            data["system_prompt"] = self.system_prompt

        return data

    def to_json(self, include_prompt: bool = True) -> str:
        return json.dumps(self.to_dict(include_prompt), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "AIRAContext":
        """Toleran: field hilang/rusak jadi default, tidak pernah raise."""
        data = data if isinstance(data, dict) else {}

        sections = {
            name: (
                ContextSection.from_dict(data[name])
                if isinstance(data.get(name), dict)
                else None
            )
            for name in ALL_SECTIONS
        }

        task = data.get("task")
        created_at = data.get("created_at")

        return cls(
            user_input=str(data.get("user_input") or ""),
            session_id=data.get("session_id"),
            task=dict(task) if isinstance(task, dict) else None,
            system_prompt=str(data.get("system_prompt") or ""),
            warnings=[str(w) for w in (data.get("warnings") or [])],
            version=str(data.get("version") or CONTEXT_SCHEMA_VERSION),
            created_at=float(created_at) if created_at is not None else time.time(),
            **sections,
        )
