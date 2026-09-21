"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

Flow: prompt -> TaskClassifier -> ModelRouter (+ModelPolicy) -> SelectedModel
-> ContextBuilder -> Orchestrator/REI. Kegagalan classifier/router tidak
pernah menjatuhkan giliran: classifier jatuh ke general/0.50, router gagal ->
selected=None dan provider_client memakai default label general.

Konteks runtime (persona/identity, waktu, memory, lokasi, ringkasan tool, task)
disusun SATU kali per giliran oleh core/context (ContextBuilder) lalu dibawa
ke Planner sebagai AIRAContext. Kalau builder gagal, context=None dan Planner
memakai builder default - giliran tetap jalan.

Siklus hidup satu giliran dipublish ke Event Bus (core/events.py), semuanya
dengan correlation_id yang SAMA:

    chat.received -> thinking.start -> (task.classified oleh classifier)
      -> task.started -> [tool.* dari Planner] -> thinking.finish
      -> task.finished -> response.ready

correlation_id diambil dari event_scope yang sudah aktif (ws.py mengaturnya
per giliran); kalau tidak ada (REST/terminal) dibuat baru di sini.

Runtime State (Sprint 2 / Worker 3): Brain memastikan Runtime State Engine aktif
(get_runtime_state() otomatis subscribe ke Event Bus) sebelum event apa pun
dipublish, dan menyuntikkan snapshot-nya ke ContextBuilder. Brain TIDAK menyimpan
atau mengubah state sendiri - state hanya diturunkan dari event di atas.
Aturan yang dijaga Brain untuk state: setiap thinking.start HARUS punya
thinking.finish, termasuk saat Stop ditekan sesudah klasifikasi tapi sebelum
task.started.

think() menerima cancel_event (threading.Event) untuk tombol Stop.
Tidak ada lagi parameter on_event: WebSocket menerima event lewat
api/ws_bridge.py (subscriber Event Bus).

Streaming (Sprint 2.5): think(..., stream=True) meminta provider streaming.
Brain hanya meneruskan flag ke Orchestrator; chunk mengalir Planner -> Event
Bus (stream.start / stream.delta) -> WS bridge. Siklus event Brain di atas
(thinking.*, task.*, response.ready) dan Runtime State TIDAK berubah. Hasil
akhir tetap BrainResponse utuh (answer lengkap); field 'streamed' hanya
info apakah ada panggilan yang benar-benar di-stream.
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
from core.context import AIRAContext, ContextBuilder, summarize_tool_schemas
from core.orchestrator import AGENT_TOOL_CATEGORY, AGENT_TOOL_SCHEMAS, Orchestrator
from core.memory import ConversationMemory
from core.model_router import get_model_router
from core.model_types import SelectedModel, TaskClassification
from core.runtime_state import get_runtime_state
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
    streamed: bool = False           # Sprint 2.5: ada panggilan LLM yang benar-benar di-stream


def _tool_summary() -> dict:
    """Ringkasan tool (nama + kategori) untuk tool_context - bukan skema penuh."""
    return summarize_tool_schemas(AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY)


def _runtime_snapshot() -> dict:
    """Snapshot Runtime State (JSON-safe) untuk section runtime_state di konteks."""
    return get_runtime_state().snapshot().to_dict()


class Brain:

    def __init__(self, memory: ConversationMemory, context_builder: Optional[ContextBuilder] = None):
        self.memory = memory
        self._ensure_runtime_state()
        self.orchestrator = Orchestrator()
        self.classifier = get_task_classifier()
        self.router = get_model_router()
        self.context_builder = context_builder or ContextBuilder(
            tool_summary=_tool_summary, runtime_state=_runtime_snapshot,
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _ensure_runtime_state() -> None:
        """Engine harus sudah subscribe SEBELUM Brain mempublish event pertama."""
        try:
            get_runtime_state()
        except Exception:
            logger.exception("BRAIN | Runtime State Engine gagal aktif (diabaikan).")

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

    def _build_context(self, user_input: str, classification: TaskClassification) -> Optional[AIRAContext]:
        """Builder hanya menggabungkan konteks; gagal -> None, Planner memakai builder default."""
        try:
            return self.context_builder.build(
                user_input,
                session_id=getattr(self.memory, "session_id", None),
                task=classification,
            )
        except Exception:
            logger.exception("BRAIN | context builder gagal - Planner memakai builder default.")
            return None

    # -------------------------------------------------------------- think

    def think(self, user_input: str, cancel_event=None, stream: bool = False) -> BrainResponse:
        # Satu giliran = satu correlation_id (pakai yang sudah ada dari
        # ws.py kalau ada, supaya event WS dan event Brain nyambung).
        correlation_id = current_event_context().get("correlation_id") or new_correlation_id()

        with event_scope(correlation_id=correlation_id):
            return self._think(user_input, cancel_event, stream)

    def _think(self, user_input: str, cancel_event, stream: bool = False) -> BrainResponse:
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
            # thinking.start sudah dipublish di atas, tetapi blok try/finally di
            # bawah belum tercapai: tutup dulu supaya Runtime State tidak
            # menggantung di THINKING.
            self._publish(EventNames.THINKING_FINISH)
            return BrainResponse(answer="", cancelled=True)

        self._publish(
            EventNames.TASK_STARTED,
            label=classification.primary_label,
            confidence=classification.confidence,
            model=selected.display_name if selected else None,
        )

        context = self._build_context(user_input, classification)

        started = time.perf_counter()
        outcome = {"error": True, "cancelled": False}   # kalau route() raise

        # 'stream' hanya diteruskan kalau True: orchestrator/test double lama
        # tanpa parameter stream tetap kompatibel.
        route_kwargs = {"stream": True} if stream else {}

        try:
            result = self.orchestrator.route(
                user_input, self.memory,
                cancel_event=cancel_event, selected_model=selected,
                context=context, **route_kwargs,
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
            streamed=bool(result.get("streamed", False)),
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