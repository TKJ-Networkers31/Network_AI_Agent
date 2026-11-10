"""
core/model_types.py — tipe data & konstanta bersama Model Router (Sprint 1).

Dipisah dari task_classifier / model_router / model_policy supaya modul-modul
itu bisa saling impor tanpa circular import.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional

from core.events import EventNames

VALID_LABELS = (
    "general", "reasoning", "coding", "networking",
    "vision", "voice", "retrieval", "automation",
)
DEFAULT_LABEL = "general"
VALID_PROVIDERS = ("openrouter", "gemini", "nvidia", "kumo")

# 15 Canonical Model Classifications (A through O)
MODEL_CLASSIFICATION_CLASSES = {
    "A": "General Chat",
    "B": "Reasoning",
    "C": "Coding",
    "D": "Network Engineering",
    "E": "Agentic / Tool Calling",
    "F": "Long-Context / RAG",
    "G": "Vision / Multimodal",
    "H": "Image and Document Understanding",
    "I": "Embedding",
    "J": "Reranking",
    "K": "Speech / Audio",
    "L": "Translation",
    "M": "Content Safety",
    "N": "Video Understanding",
    "O": "Specialized Domain Models",
}

# All 28 classification categories mandated by Section 5 of the Master Directive
TASK_CLASSIFICATION_CATEGORIES = (
    "general_chat",
    "general_reasoning",
    "network_engineering",
    "network_troubleshooting",
    "network_configuration",
    "network_topology",
    "routing_protocols",
    "subnetting",
    "cybersecurity",
    "linux_administration",
    "devops",
    "programming",
    "coding",
    "terminal_operations",
    "documentation",
    "mathematics",
    "research",
    "long_context_analysis",
    "vision_analysis",
    "image_understanding",
    "document_processing",
    "audio_processing",
    "translation",
    "embedding",
    "retrieval",
    "reranking",
    "voice_generation",
    "content_safety",
)

# Deterministic mapping from fine-grained categories to primary routing labels
CATEGORY_TO_LABEL_MAP: dict[str, str] = {
    "general_chat": "general",
    "documentation": "general",
    "general_reasoning": "reasoning",
    "mathematics": "reasoning",
    "research": "reasoning",
    "long_context_analysis": "reasoning",
    "network_engineering": "networking",
    "network_troubleshooting": "networking",
    "network_configuration": "networking",
    "network_topology": "networking",
    "routing_protocols": "networking",
    "subnetting": "networking",
    "cybersecurity": "networking",
    "coding": "coding",
    "programming": "coding",
    "terminal_operations": "coding",
    "devops": "coding",
    "linux_administration": "coding",
    "vision_analysis": "vision",
    "image_understanding": "vision",
    "document_processing": "automation",
    "automation": "automation",
    "retrieval": "retrieval",
    "embedding": "retrieval",
    "reranking": "retrieval",
    "translation": "general",
    "voice_generation": "voice",
    "audio_processing": "voice",
    "content_safety": "general",
}

# Nilai berasal dari EventNames (satu sumber kebenaran).
EVENT_TASK_CLASSIFIED = EventNames.TASK_CLASSIFIED
EVENT_MODEL_SELECTED = EventNames.MODEL_SELECTED
EVENT_MODEL_FALLBACK = EventNames.MODEL_FALLBACK
EVENT_MODEL_FAILED = EventNames.MODEL_FAILED


@dataclass
class TaskClassification:
    primary_label: str = DEFAULT_LABEL
    confidence: float = 0.5
    requires_tools: bool = False
    requires_vision: bool = False
    requires_voice: bool = False
    task_category: str = "general_chat"
    required_capabilities: List[str] = field(default_factory=list)
    required_modalities: List[str] = field(default_factory=lambda: ["text"])
    rationale: str = ""

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
    publisher: str = ""
    endpoint: str = ""
    capabilities: List[str] = field(default_factory=list)
    supports_streaming: bool = True
    supports_tool_calling: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict, fallback_from: Optional[str] = None) -> "SelectedModel":
        caps = row.get("capabilities") or []
        if isinstance(caps, str):
            import json
            try:
                caps = json.loads(caps)
            except Exception:
                caps = []
        return cls(
            id=row["id"],
            display_name=row["display_name"],
            provider=row["provider"],
            model_id=row["model_id"],
            label=row["label"],
            context_window=int(row.get("context_window") or 0),
            fallback_from=fallback_from,
            publisher=str(row.get("publisher") or ""),
            endpoint=str(row.get("api_endpoint") or row.get("endpoint") or ""),
            capabilities=caps,
            supports_streaming=bool(row.get("supports_streaming", 1)),
            supports_tool_calling=bool(row.get("supports_tool_calling", 0)),
        )

    @classmethod
    def from_any(cls, value: Any) -> "SelectedModel":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            caps = value.get("capabilities") or []
            if isinstance(caps, str):
                import json
                try:
                    caps = json.loads(caps)
                except Exception:
                    caps = []
            return cls(
                id=value["id"],
                display_name=value.get("display_name", value["id"]),
                provider=value["provider"],
                model_id=value["model_id"],
                label=value.get("label", DEFAULT_LABEL),
                context_window=int(value.get("context_window") or 0),
                fallback_from=value.get("fallback_from"),
                publisher=str(value.get("publisher") or ""),
                endpoint=str(value.get("api_endpoint") or value.get("endpoint") or ""),
                capabilities=caps,
                supports_streaming=bool(value.get("supports_streaming", 1)),
                supports_tool_calling=bool(value.get("supports_tool_calling", 0)),
            )
        raise TypeError(f"selected_model harus SelectedModel atau dict, bukan {type(value).__name__}.")