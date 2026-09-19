"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

FIX (Optimalisasi DIO):
BrainResponse sekarang membawa 'interaction_schema' (dict atau None),
diteruskan apa adanya dari hasil Planner.run() lewat Orchestrator.route()
- ini yang membuat form/pilihan interaktif DIO bisa sampai ke
api/routers/chat.py & ws.py, lalu ke frontend.

PERUBAHAN (Chat Session: tombol Stop):
- think() menerima 'cancel_event' opsional (threading.Event).
- BrainResponse punya field 'cancelled' (default False) - True kalau
  giliran ini dihentikan user sebelum selesai.

PERUBAHAN (Sprint 1 - Model Router):
Flow: prompt -> TaskClassifier -> ModelRouter (+ModelPolicy) -> SelectedModel
-> Orchestrator/REI. Kegagalan classifier/router tidak pernah menjatuhkan
giliran: classifier jatuh ke general/0.50, router gagal -> selected=None dan
provider_client memakai default label general.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.orchestrator import Orchestrator
from core.memory import ConversationMemory
from core.model_router import get_model_router
from core.model_types import SelectedModel, TaskClassification
from core.task_classifier import get_task_classifier

logger = logging.getLogger("aira.brain")


@dataclass
class BrainResponse:
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    token_usage: Optional[dict] = None
    session_token_usage: Optional[dict] = None
    error: bool = False
    duration: float = 0.0
    interaction_schema: Optional[dict] = None
    cancelled: bool = False
    routing: Optional[dict] = None   # {"task": {...}, "model": {...}|None}


class Brain:

    def __init__(self, memory: ConversationMemory):
        self.memory = memory
        self.orchestrator = Orchestrator()
        self.classifier = get_task_classifier()
        self.router = get_model_router()

    def _classify(self, user_input: str) -> TaskClassification:
        try:
            return self.classifier.classify(user_input)
        except Exception:
            logger.exception("BRAIN | classifier gagal - pakai fallback general.")
            return TaskClassification.fallback()

    def _select(self, classification: TaskClassification) -> Optional[SelectedModel]:
        try:
            return self.router.select(classification)
        except Exception:
            logger.exception("BRAIN | router gagal - provider_client akan pakai default general.")
            return None

    def think(self, user_input: str, on_event=None, cancel_event=None) -> BrainResponse:
        logger.info("BRAIN | menerima input user (%d char)", len(user_input))

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        if cancelled():
            return BrainResponse(answer="", cancelled=True)

        if on_event:
            try:
                on_event("thinking", {"message": "Mengklasifikasi permintaan..."})
            except Exception:
                logger.exception("on_event callback error (diabaikan)")

        classification = self._classify(user_input)
        selected = self._select(classification)

        if cancelled():
            return BrainResponse(answer="", cancelled=True)

        result = self.orchestrator.route(
            user_input, self.memory,
            on_event=on_event, cancel_event=cancel_event, selected_model=selected,
        )

        return BrainResponse(
            answer=result.get("answer", ""),
            steps=result.get("steps", []),
            token_usage=result.get("token_usage"),
            session_token_usage=result.get("session_token_usage"),
            error=result.get("error", False),
            duration=result.get("duration", 0.0),
            interaction_schema=result.get("interaction_schema"),
            cancelled=bool(result.get("cancelled", False)),
            routing={
                "task": classification.to_dict(),
                "model": selected.to_dict() if selected else None,
            },
        )