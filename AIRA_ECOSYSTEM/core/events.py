"""
AIRA OS — Internal Event Bus
============================

File:
    AIRA_ECOSYSTEM/core/events.py

Purpose:
    SATU-SATUNYA sistem event internal AIRA OS (publish/subscribe).

Arsitektur:
    Publisher (Brain, Planner, DIO, FSE, AKANE, ...)
        |
        v
    EventBus
        |
        +--> Logger
        +--> WebSocket (api/ws_bridge.py)
        +--> Memory
        +--> Scheduler
        +--> subscriber lain

Prinsip:
    1. Modul berkomunikasi lewat event, bukan callback langsung.
    2. Setiap event punya correlation_id untuk tracing end-to-end.
    3. Setiap event punya event_id unik.
    4. Subscriber terisolasi satu sama lain.
    5. Error subscriber TIDAK PERNAH menjatuhkan publisher.
    6. EventBus thread-safe.
    7. Event immutable setelah dibuat (data/metadata disalin saat publish).
    8. Publisher sync maupun async didukung.
    9. Subscriber wildcard ("*") menerima semua event.
    10. EventBus tidak berisi business logic.

PERUBAHAN (Worker 1 - Event Bus stabilization):

1. DISPATCH TIDAK LAGI asyncio.run() PER EVENT.
   Sebelumnya publish() dari thread tanpa event loop (mis. Planner yang
   dijalankan lewat asyncio.to_thread) memanggil asyncio.run() untuk SETIAP
   event: membuat event loop baru tiap kali, dan subscriber async berjalan
   di loop sementara itu - bukan di loop FastAPI - sehingga tidak bisa
   mengirim ke WebSocket. Sekarang:
     - subscriber SYNC dipanggil langsung (inline) di thread publisher,
       terisolasi try/except -> urutan deterministik, tanpa event loop.
       Subscriber sync WAJIB cepat/non-blocking; kerja berat -> async.
     - subscriber ASYNC dijadwalkan ke loop yang di-bind lewat bind_loop()
       (run_coroutine_threadsafe dari thread lain, create_task dari thread
       loop itu sendiri). asyncio.run() hanya fallback terakhir (terminal /
       test tanpa loop sama sekali).

2. KONTEKS EVENT (contextvars).
   event_scope(correlation_id=..., session_id=..., run_id=...) menempelkan
   konteks ke SEMUA event yang dipublish di dalam blok with - termasuk yang
   dipublish dari thread pekerja (asyncio.to_thread menyalin context).
   correlation_id diambil dari konteks kalau tidak diberikan eksplisit;
   key lain (session_id, run_id, ...) masuk ke Event.metadata. Satu giliran
   chat jadi satu correlation_id tanpa harus mengoper argumen di banyak
   modul.

3. Event.to_json_dict() / json_safe(): payload aman untuk JSON (WebSocket,
   logs.db) walau data berisi objek non-serializable.

4. EventNames dilengkapi (interaction.*, model.selected, model.fallback)
   sesuai string yang SUDAH dipakai modul lain - tidak ada nama yang
   berubah, jadi subscriber/test lama tetap jalan.

5. _log_event hanya menyusun payload kalau level DEBUG aktif (Planner kini
   mem-publish banyak event per giliran).

Do NOT put in this file:
    LLM reasoning, routing, tool execution, network logic, persona logic,
    memory retrieval, security decisions.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import logging
import threading
import uuid

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from typing import (
    Any,
    Awaitable,
    Callable,
    Iterator,
    Optional,
    Union,
)

from core.logger import get_logger, log_event


# ============================================================
# LOGGER
# ============================================================

logger = get_logger("eventbus")


# ============================================================
# CONSTANTS
# ============================================================

WILDCARD = "*"


# ============================================================
# STANDARD EVENT NAMES
# ============================================================

class EventNames:
    """
    Nama event standar AIRA OS.

    Konvensi: <domain>.<action>

    Catatan kompatibilitas: string di bawah SAMA PERSIS dengan yang sudah
    dipakai modul lain (core/model_types.py, core/dio/constants.py, dst).
    """

    # CHAT
    CHAT_RECEIVED = "chat.received"

    # THINKING
    THINKING_START = "thinking.start"
    THINKING_FINISH = "thinking.finish"

    # TOOL
    TOOL_START = "tool.start"
    TOOL_PROGRESS = "tool.progress"
    TOOL_FINISH = "tool.finish"

    # RESPONSE
    RESPONSE_READY = "response.ready"

    # MEMORY
    MEMORY_SAVED = "memory.saved"

    # SYSTEM
    SYSTEM_ERROR = "system.error"

    # MODEL
    MODEL_STARTED = "model.started"
    MODEL_FINISHED = "model.finished"
    MODEL_FAILED = "model.failed"
    MODEL_SWITCHED = "model.switched"
    MODEL_SELECTED = "model.selected"
    MODEL_FALLBACK = "model.fallback"

    # TASK
    TASK_CLASSIFIED = "task.classified"
    TASK_STARTED = "task.started"
    TASK_FINISHED = "task.finished"

    # INTERACTION (DIO)
    INTERACTION_REQUESTED = "interaction.requested"
    INTERACTION_STARTED = "interaction.started"
    INTERACTION_GENERATED = "interaction.generated"
    INTERACTION_COMPLETED = "interaction.completed"
    INTERACTION_CANCELLED = "interaction.cancelled"

    # LOCATION
    LOCATION_UPDATED = "location.updated"
    LOCATION_CLEARED = "location.cleared"


STANDARD_EVENTS: frozenset[str] = frozenset(
    value
    for name, value in vars(EventNames).items()
    if name.isupper() and isinstance(value, str)
)


# ============================================================
# JSON SAFETY
# ============================================================

def json_safe(value: Any) -> Any:
    """
    Kembalikan salinan `value` yang PASTI bisa di-JSON-kan.

    Objek yang tidak dikenali (Path, datetime, dataclass, dst) diubah jadi
    str(); kalau seluruh struktur tetap gagal (mis. key dict non-string atau
    referensi melingkar), dikembalikan str(value). Tidak pernah raise.
    """
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


# ============================================================
# EVENT CONTEXT (correlation / session / run)
# ============================================================

_EVENT_CONTEXT: contextvars.ContextVar[Optional[dict[str, Any]]] = (
    contextvars.ContextVar("aira_event_context", default=None)
)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def current_event_context() -> dict[str, Any]:
    """Salinan konteks event aktif ({} kalau tidak ada)."""
    return dict(_EVENT_CONTEXT.get() or {})


@contextmanager
def event_scope(**values: Any) -> Iterator[dict[str, Any]]:
    """
    Tempelkan konteks ke semua event yang dipublish di dalam blok ini.

        with event_scope(correlation_id=cid, session_id="s1", run_id="r1"):
            await asyncio.to_thread(brain.think, ...)   # event ikut tertandai

    - Scope bersarang digabung (yang dalam menimpa yang luar).
    - Nilai None diabaikan (tidak menimpa konteks luar).
    - Konteks ikut ke thread pekerja lewat asyncio.to_thread.
    """
    merged = {
        **(_EVENT_CONTEXT.get() or {}),
        **{key: value for key, value in values.items() if value is not None},
    }

    token = _EVENT_CONTEXT.set(merged)

    try:
        yield dict(merged)
    finally:
        _EVENT_CONTEXT.reset(token)


# ============================================================
# TYPE DEFINITIONS
# ============================================================

EventCallback = Callable[
    ["Event"],
    Union[
        None,
        Awaitable[None],
    ],
]


# ============================================================
# EVENT
# ============================================================

@dataclass(frozen=True)
class Event:
    """
    Kontrak event (immutable).

    Bentuk serialisasi (to_dict):

        {
            "event_id": "...",
            "correlation_id": "...",
            "event": "tool.start",
            "source": "REI",
            "agent": "REI",
            "tool": "ping",
            "timestamp": "2026-09-19T05:00:00+00:00",   # UTC
            "data": {...},
            "metadata": {...}          # session_id, run_id, ...
        }
    """

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    event: str = ""

    source: Optional[str] = None
    agent: Optional[str] = None
    tool: Optional[str] = None

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Dict biasa (data/metadata direferensikan apa adanya)."""
        return {
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "event": self.event,
            "source": self.source,
            "agent": self.agent,
            "tool": self.tool,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_json_dict(self) -> dict[str, Any]:
        """Salinan yang dijamin JSON-serializable (untuk WebSocket/log DB)."""
        return json_safe(self.to_dict())

    def child(
        self,
        event: str,
        *,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "Event":
        """
        Buat event lain dengan correlation_id yang SAMA (dan metadata induk
        diwariskan, kecuali ditimpa).
        """
        return Event(
            event=event,
            correlation_id=self.correlation_id,
            source=source or self.source,
            agent=agent if agent is not None else self.agent,
            tool=tool if tool is not None else self.tool,
            data=dict(data or {}),
            metadata={**self.metadata, **(metadata or {})},
        )


# ============================================================
# SUBSCRIPTION
# ============================================================

@dataclass(frozen=True)
class _Subscription:
    token: str
    callback: EventCallback


# ============================================================
# EVENT BUS
# ============================================================

class EventBus:
    """
    Publish/subscribe Event Bus yang thread-safe.

    Tanggung jawab: publish, subscribe, unsubscribe, tracing, isolasi
    subscriber, dispatch sync/async.
    Bukan tanggung jawab: reasoning, routing, eksekusi, keamanan, persistensi.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[_Subscription]] = {}
        self._lock = threading.RLock()

        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._published_count = 0
        self._failed_callbacks = 0

    # ========================================================
    # LOOP BINDING
    # ========================================================

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Daftarkan event loop utama (FastAPI). Subscriber async akan
        dijadwalkan ke loop ini walau publish() dipanggil dari thread lain.
        """
        with self._lock:
            self._loop = loop

    def unbind_loop(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Lepas binding (hanya kalau `loop` cocok, atau loop=None)."""
        with self._lock:
            if loop is None or loop is self._loop:
                self._loop = None

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        with self._lock:
            return self._loop

    # ========================================================
    # SUBSCRIBE / UNSUBSCRIBE / CLEAR
    # ========================================================

    def subscribe(self, event_name: str, callback: EventCallback) -> str:
        """
        Daftarkan callback (sync atau async). Return: token untuk unsubscribe.
        `WILDCARD` ("*") menerima semua event.
        """
        if not event_name:
            raise ValueError("event_name tidak boleh kosong.")

        if not callable(callback):
            raise TypeError("callback harus callable.")

        token = uuid.uuid4().hex
        subscription = _Subscription(token=token, callback=callback)

        with self._lock:
            self._subscribers.setdefault(event_name, []).append(subscription)
            total = len(self._subscribers[event_name])

        logger.debug(
            "SUBSCRIBE | event=%s | token=%s | total=%d",
            event_name, token, total,
        )

        return token

    def unsubscribe(self, event_name: str, token: str) -> bool:
        """Hapus subscriber berdasarkan token. True kalau ada yang dihapus."""
        with self._lock:
            subscriptions = self._subscribers.get(event_name)

            if not subscriptions:
                return False

            remaining = [s for s in subscriptions if s.token != token]
            removed = len(remaining) != len(subscriptions)

            if remaining:
                self._subscribers[event_name] = remaining
            else:
                self._subscribers.pop(event_name, None)

        if removed:
            logger.debug("UNSUBSCRIBE | event=%s | token=%s", event_name, token)

        return removed

    def clear(self, event_name: Optional[str] = None) -> None:
        """clear(): hapus semua subscriber; clear("x"): hanya untuk event x."""
        with self._lock:
            if event_name is None:
                self._subscribers.clear()
            else:
                self._subscribers.pop(event_name, None)

    # ========================================================
    # BUILD EVENT
    # ========================================================

    @staticmethod
    def _build_event(
        event_name: str,
        correlation_id: Optional[str],
        source: Optional[str],
        agent: Optional[str],
        tool: Optional[str],
        data: Optional[dict[str, Any]],
        metadata: Optional[dict[str, Any]],
    ) -> Event:
        if not event_name:
            raise ValueError("event_name tidak boleh kosong.")

        context = _EVENT_CONTEXT.get() or {}

        context_metadata = {
            key: value
            for key, value in context.items()
            if key != "correlation_id"
        }

        return Event(
            event=event_name,
            correlation_id=(
                correlation_id
                or context.get("correlation_id")
                or uuid.uuid4().hex
            ),
            source=source,
            agent=agent,
            tool=tool,
            data=dict(data or {}),
            metadata={**context_metadata, **(metadata or {})},
        )

    # ========================================================
    # PUBLISH
    # ========================================================

    def publish(
        self,
        event_name: str,
        *,
        correlation_id: Optional[str] = None,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Publish event (sinkron).

        Aman dipanggil dari kode biasa, thread pekerja, FastAPI, planner,
        tool SSH, dsb.

        - Subscriber sync selesai dipanggil SEBELUM publish() return
          (urutan deterministik). Harus cepat/non-blocking.
        - Subscriber async dijadwalkan (tidak ditunggu) - lihat _schedule().
        - Error subscriber tidak pernah sampai ke pemanggil.
        """
        event = self._build_event(
            event_name, correlation_id, source, agent, tool, data, metadata,
        )

        with self._lock:
            self._published_count += 1

        self._log_event(event)
        self._dispatch(event)

        return event

    async def publish_async(
        self,
        event_name: str,
        *,
        correlation_id: Optional[str] = None,
        source: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Versi async: MENUNGGU semua subscriber async selesai
        (berguna kalau urutan penting).
        """
        event = self._build_event(
            event_name, correlation_id, source, agent, tool, data, metadata,
        )

        with self._lock:
            self._published_count += 1

        self._log_event(event)

        pending = []

        for subscription in self._collect_subscriptions(event.event):
            awaitable = self._invoke(subscription, event)

            if awaitable is not None:
                pending.append(self._guard(awaitable, subscription, event))

        if pending:
            await asyncio.gather(*pending)

        return event

    # ========================================================
    # LOGGING
    # ========================================================

    def _log_event(self, event: Event) -> None:
        """Logging tidak boleh pernah merusak EventBus."""
        try:
            if not logger.isEnabledFor(logging.DEBUG):
                return

            log_event(
                logger,
                "DEBUG",
                f"EVENT | {event.event}",
                category="eventbus",
                context=event.to_dict(),
            )
        except Exception:
            logger.exception("EventBus logging gagal (diabaikan).")

    # ========================================================
    # DISPATCH
    # ========================================================

    def _collect_subscriptions(self, event_name: str) -> list[_Subscription]:
        """Snapshot subscriber (registry aman diubah saat dispatch)."""
        with self._lock:
            specific = list(self._subscribers.get(event_name, []))
            wildcard = list(self._subscribers.get(WILDCARD, []))

        return specific + wildcard

    def _dispatch(self, event: Event) -> None:
        for subscription in self._collect_subscriptions(event.event):
            awaitable = self._invoke(subscription, event)

            if awaitable is not None:
                self._schedule(awaitable, subscription, event)

    def _invoke(
        self,
        subscription: _Subscription,
        event: Event,
    ) -> Optional[Awaitable[None]]:
        """
        Panggil callback SEKARANG, terisolasi.

        Callback sync: selesai di sini. Callback async: pemanggilan hanya
        membuat coroutine (murah) - dikembalikan supaya dijadwalkan/ditunggu.
        """
        try:
            result = subscription.callback(event)
        except Exception:
            self._record_failure(subscription, event)
            return None

        return result if inspect.isawaitable(result) else None

    async def _guard(
        self,
        awaitable: Awaitable[None],
        subscription: _Subscription,
        event: Event,
    ) -> None:
        """Tunggu awaitable subscriber; error dicatat, tidak dilempar."""
        try:
            await awaitable
        except Exception:
            self._record_failure(subscription, event)

    def _schedule(
        self,
        awaitable: Awaitable[None],
        subscription: _Subscription,
        event: Event,
    ) -> None:
        """
        Jadwalkan subscriber async (fire-and-forget).

        Prioritas:
          1. Loop yang di-bind (bind_loop) dan sedang berjalan:
               - dari thread loop itu  -> create_task
               - dari thread lain      -> run_coroutine_threadsafe
          2. Loop yang berjalan di thread ini -> create_task
          3. Tidak ada loop sama sekali (terminal/test) -> asyncio.run,
             selesai sebelum publish() return.
        """
        guarded = self._guard(awaitable, subscription, event)

        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None

        bound = self.loop

        if bound is not None and bound.is_running() and not bound.is_closed():
            if current is bound:
                task = bound.create_task(guarded)
                task.add_done_callback(self._consume_result)
            else:
                future = asyncio.run_coroutine_threadsafe(guarded, bound)
                future.add_done_callback(self._consume_result)
            return

        if current is not None:
            task = current.create_task(guarded)
            task.add_done_callback(self._consume_result)
            return

        asyncio.run(guarded)

    def _record_failure(
        self,
        subscription: _Subscription,
        event: Event,
    ) -> None:
        """Dipanggil dari dalam blok except (supaya traceback ikut tercatat)."""
        with self._lock:
            self._failed_callbacks += 1

        logger.exception(
            "EVENT SUBSCRIBER ERROR | event=%s | event_id=%s | "
            "correlation_id=%s | token=%s",
            event.event,
            event.event_id,
            event.correlation_id,
            subscription.token,
        )

    @staticmethod
    def _consume_result(done: Any) -> None:
        """Konsumsi hasil task/future supaya tidak jadi warning asyncio."""
        try:
            done.result()
        except BaseException:
            # _guard sudah mencatat error subscriber; cancel juga diabaikan.
            pass

    # ========================================================
    # INSPECTION
    # ========================================================

    def subscriber_count(self, event_name: Optional[str] = None) -> int:
        with self._lock:
            if event_name is not None:
                return len(self._subscribers.get(event_name, []))

            return sum(len(subs) for subs in self._subscribers.values())

    def stats(self) -> dict[str, int]:
        with self._lock:
            published = self._published_count
            failed = self._failed_callbacks

        return {
            "published": published,
            "failed_callbacks": failed,
            "subscriber_count": self.subscriber_count(),
        }

    def reset_stats(self) -> None:
        with self._lock:
            self._published_count = 0
            self._failed_callbacks = 0


# ============================================================
# GLOBAL SINGLETON
# ============================================================

event_bus = EventBus()


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def publish_event(
    event_name: str,
    *,
    correlation_id: Optional[str] = None,
    source: Optional[str] = None,
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Event:
    """Shortcut untuk event_bus.publish(...)."""
    return event_bus.publish(
        event_name,
        correlation_id=correlation_id,
        source=source,
        agent=agent,
        tool=tool,
        data=data,
        metadata=metadata,
    )


async def publish_event_async(
    event_name: str,
    *,
    correlation_id: Optional[str] = None,
    source: Optional[str] = None,
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Event:
    """Shortcut async untuk event_bus.publish_async(...)."""
    return await event_bus.publish_async(
        event_name,
        correlation_id=correlation_id,
        source=source,
        agent=agent,
        tool=tool,
        data=data,
        metadata=metadata,
    )