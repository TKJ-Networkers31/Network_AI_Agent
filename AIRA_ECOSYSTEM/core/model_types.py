"""
core/model_types.py — tipe data & konstanta bersama Model Router (Sprint 1).

Dipisah dari task_classifier / model_router / model_policy supaya modul-modul
itu bisa saling impor tanpa circular import.
"""

from dataclasses import asdict, dataclass
from typing import Any, Optional

VALID_LABELS = (
    "general", "reasoning", "coding", "networking",
    "vision", "voice", "retrieval", "automation",
)
DEFAULT_LABEL = "general"
VALID_PROVIDERS = ("ollama", "openrouter", "gemini")

EVENT_TASK_CLASSIFIED = "task.classified"
EVENT_MODEL_SELECTED = "model.selected"
EVENT_MODEL_FALLBACK = "model.fallback"
EVENT_MODEL_FAILED = "model.failed"


@dataclass
class TaskClassification:
    primary_label: str = DEFAULT_LABEL
    confidence: float = 0.5
    requires_tools: bool = False
    requires_vision: bool = False
    requires_voice: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def fallback(cls) -> "TaskClassification":
        """Hasil aman kalau parsing/panggilan classifier gagal."""
        return cls()


@dataclass
class SelectedModel:
    id: str
    display_name: str
    provider: str
    model_id: str
    label: str
    context_window: int = 0          # 0 = tidak diketahui (cek context dilewati)
    fallback_from: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict, fallback_from: Optional[str] = None) -> "SelectedModel":
        return cls(
            id=row["id"],
            display_name=row["display_name"],
            provider=row["provider"],
            model_id=row["model_id"],
            label=row["label"],
            context_window=int(row.get("context_window") or 0),
            fallback_from=fallback_from,
        )

    @classmethod
    def from_any(cls, value: Any) -> "SelectedModel":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                id=value["id"],
                display_name=value.get("display_name", value["id"]),
                provider=value["provider"],
                model_id=value["model_id"],
                label=value.get("label", DEFAULT_LABEL),
                context_window=int(value.get("context_window") or 0),
                fallback_from=value.get("fallback_from"),
            )
        raise TypeError(f"selected_model harus SelectedModel atau dict, bukan {type(value).__name__}.")