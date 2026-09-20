"""
core/semantic_memory/models.py — bentuk data Semantic Memory (Sprint 2.4).

HANYA data + validasi + serialisasi: tanpa I/O, tanpa database, tanpa embedding.
Semua model bisa di-JSON-kan lewat to_dict()/to_json() dan dipulihkan lewat
from_dict() (round-trip persis, termasuk vektor embedding).
"""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.semantic_memory.defaults import DEFAULT_IMPORTANCE


class MemoryCategory(str, Enum):
    """str-Enum: langsung JSON-serializable dan bisa dibandingkan dengan string."""

    USER_PREFERENCE = "user_preference"
    NETWORK = "network"
    PROJECT = "project"
    PERSONAL = "personal"
    KNOWLEDGE = "knowledge"
    TASK = "task"

    @classmethod
    def coerce(cls, value: Any) -> "MemoryCategory":
        """MemoryCategory | str (tidak peka huruf besar/kecil) -> MemoryCategory."""
        if isinstance(value, cls):
            return value

        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass

        valid = ", ".join(item.value for item in cls)
        raise ValueError(f"Kategori '{value}' tidak valid. Pilihan: {valid}.")


def new_record_id() -> str:
    return uuid.uuid4().hex


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} harus berupa angka, bukan bool.")

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} harus berupa angka.") from None

    if not math.isfinite(number):
        raise ValueError(f"{name} harus berupa angka yang terhingga (bukan NaN/inf).")

    return number


def clamp_unit(value: Any, name: str = "importance") -> float:
    """Angka -> float dalam rentang 0..1 (di luar rentang di-clamp)."""
    return max(0.0, min(1.0, _finite_float(value, name)))


def _clean_embedding(values: Any) -> list[float]:
    if values is None:
        return []

    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError("embedding harus berupa list angka.")

    return [_finite_float(item, "embedding") for item in values]


@dataclass(kw_only=True)
class MemoryRecord:
    """
    Satu fakta yang diingat.

    session_id : pemilik fakta (isolasi sesi). Untuk fakta lintas sesi pakai
                 defaults.GLOBAL_SESSION_ID.
    importance : importance MANUAL 0..1 (di-clamp). Skor importance akhir
                 (recency + kategori + manual) dihitung scorer.py, tidak disimpan.
    embedding  : vektor dari EmbeddingProvider. Boleh kosong (belum di-embed);
                 record kosong tidak pernah muncul di hasil retrieval.
    """

    session_id: str
    text: str
    id: str = field(default_factory=new_record_id)
    category: MemoryCategory = MemoryCategory.KNOWLEDGE
    created_at: float = field(default_factory=time.time)
    updated_at: Optional[float] = None
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = DEFAULT_IMPORTANCE

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("id tidak boleh kosong.")

        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id tidak boleh kosong.")

        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text tidak boleh kosong.")

        self.session_id = self.session_id.strip()
        self.text = self.text.strip()
        self.category = MemoryCategory.coerce(self.category)
        self.importance = clamp_unit(self.importance)

        self.created_at = _finite_float(self.created_at, "created_at")
        self.updated_at = (
            self.created_at
            if self.updated_at is None
            else _finite_float(self.updated_at, "updated_at")
        )

        self.embedding = _clean_embedding(self.embedding)

        if not isinstance(self.metadata, dict):
            raise ValueError("metadata harus berupa dict.")

        self.metadata = dict(self.metadata)

    # ---------------------------------------------------------- serialisasi

    def to_dict(self, include_embedding: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "session_id": self.session_id,
            "text": self.text,
            "category": self.category.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
            "importance": self.importance,
        }

        if include_embedding:
            data["embedding"] = list(self.embedding)

        return data

    def to_json(self, include_embedding: bool = True) -> str:
        return json.dumps(self.to_dict(include_embedding), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Any) -> "MemoryRecord":
        """session_id & text wajib; field lain memakai default kalau hilang."""
        if not isinstance(data, dict):
            raise ValueError("data record harus berupa dict.")

        kwargs: dict[str, Any] = {
            "session_id": data.get("session_id"),
            "text": data.get("text"),
        }

        for key in ("id", "category", "created_at", "updated_at",
                    "embedding", "metadata", "importance"):
            if data.get(key) is not None:
                kwargs[key] = data[key]

        return cls(**kwargs)

    @classmethod
    def from_json(cls, raw: str) -> "MemoryRecord":
        return cls.from_dict(json.loads(raw))


@dataclass
class RetrievalResult:
    """
    Satu hasil retrieval.

    similarity : cosine similarity query vs record (-1..1)
    importance : skor importance 0..1 (scorer.importance_score)
    score      : skor akhir untuk ranking (scorer.combine_score)
    """

    record: MemoryRecord
    similarity: float
    importance: float
    score: float

    def to_dict(self, include_embedding: bool = False) -> dict[str, Any]:
        return {
            "record": self.record.to_dict(include_embedding),
            "similarity": self.similarity,
            "importance": self.importance,
            "score": self.score,
        }

    def to_json(self, include_embedding: bool = False) -> str:
        return json.dumps(self.to_dict(include_embedding), ensure_ascii=False, default=str)
