"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

Flow: prompt -> TaskClassifier -> ModelRouter (+ModelPolicy) -> SelectedModel
-> Orchestrator/REI. Kegagalan classifier/router tidak pernah menjatuhkan
giliran: classifier jatuh ke general/0.50, router gagal -> selected=None dan
provider_client memakai default label general.

Siklus hidup satu giliran dipublish ke Event Bus (core/events.py), semuanya
dengan correlation_id yang SAMA:

    chat.received -> thinking.start -> (task.classified oleh classifier)
      -> task.started -> [tool.* dari Planner] -> thinking.finish
      -> task.finished -> response.ready

correlation_id diambil dari event_scope yang sudah aktif (ws.py mengaturnya
per giliran); kalau tidak ada (REST/terminal) dibuat baru di sini.

think() menerima cancel_event (threading.Event) untuk tombol Stop.
Tidak ada lagi parameter on_event: WebSocket menerima event lewat
api/ws_bridge.py (subscriber Event Bus).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.events import (
    EventNames,
    current_event_context,
    event_bus,
    event_scope,
    new_correlation_id,
)
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

    # ------------------------------------------------------------ helpers

    def _publish(self, event_name: str, **data) -> None:
        """Publish ke Event Bus; kegagalan apa pun tidak boleh menjatuhkan giliran."""
        try:
            event_bus.publish(event_name, source="BRAIN", agent="BRAIN", data=data)
        except Exception:
            logger.exception("BRAIN | gagal publish %s (diabaikan).", event_name)

    def _thinking(self, message: str) -> None:
        self._publish(EventNames.THINKING_START, message=message)

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

    # -------------------------------------------------------------- think

    def think(self, user_input: str, cancel_event=None) -> BrainResponse:
        # Satu giliran = satu correlation_id (pakai yang sudah ada dari
        # ws.py kalau ada, supaya event WS dan event Brain nyambung).
        correlation_id = current_event_context().get("correlation_id") or new_correlation_id()

        with event_scope(correlation_id=correlation_id):
            return self._think(user_input, cancel_event)

    def _think(self, user_input: str, cancel_event) -> BrainResponse:
        logger.info("BRAIN | menerima input user (%d char)", len(user_input))

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        self._publish(EventNames.CHAT_RECEIVED, chars=len(user_input))

        if cancelled():
            return BrainResponse(answer="", cancelled=True)

        self._thinking("Mengklasifikasi permintaan...")

        classification = self._classify(user_input)
        selected = self._select(classification)

        if cancelled():
            return BrainResponse(answer="", cancelled=True)

        self._publish(
            EventNames.TASK_STARTED,
            label=classification.primary_label,
            confidence=classification.confidence,
            model=selected.display_name if selected else None,
        )

        started = time.perf_counter()
        outcome = {"error": True, "cancelled": False}   # kalau route() raise

        try:
            result = self.orchestrator.route(
                user_input, self.memory,
                cancel_event=cancel_event, selected_model=selected,
            )
            outcome = {
                "error": bool(result.get("error", False)),
                "cancelled": bool(result.get("cancelled", False)),
            }
        finally:
            self._publish(EventNames.THINKING_FINISH)
            self._publish(
                EventNames.TASK_FINISHED,
                label=classification.primary_label,
                duration=round(time.perf_counter() - started, 3),
                **outcome,
            )

        response = BrainResponse(
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

        if not response.cancelled:
            # Ringkasan saja (bukan isi jawaban) - payload ini juga lewat Logger.
            self._publish(
                EventNames.RESPONSE_READY,
                answer_chars=len(response.answer or ""),
                steps=len(response.steps),
                duration=response.duration,
                error=response.error,
            )

        return response