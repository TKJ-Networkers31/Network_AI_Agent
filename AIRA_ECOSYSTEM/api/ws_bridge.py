"""
api/ws_bridge.py — jembatan Event Bus -> WebSocket (Worker 1 - Event Bus).

Alur:

    Planner / Brain / ...  (thread pekerja via asyncio.to_thread)
            |  event_bus.publish(...)
            v
        Event Bus
            |  subscriber wildcard (sync, cepat, thread-safe)
            v
    WebSocketEventBridge._on_event
            |  loop.call_soon_threadsafe(queue.put_nowait, ...)
            v
    asyncio.Queue (urutan FIFO terjaga)
            |  satu consumer
            v
    manager.send(session_id, payload)  ->  client

Menggantikan mekanisme lama di ws.py (callback on_event -> queue.Queue ->
_drain_queue_to_socket). Bentuk pesan WebSocket TIDAK berubah - frontend
(ChatRuntimeContext.handleEvent) tetap menerima:

    {"type": "tool_start", "data": {..., "session_id", "run_id"}, "ts": ...}

Aturan penerusan:
  - Event harus punya metadata session_id DAN run_id (diisi ws.py lewat
    core.events.event_scope). Giliran REST (/api/chat) tidak punya run_id,
    jadi tidak pernah "bocor" ke WebSocket sesi yang kebetulan terbuka.
  - Hanya event yang ada di peta DEFAULT_WS_EVENT_MAP yang diteruskan.
    Event lain (response.ready, task.*, model.*, dst) tetap milik
    subscriber lain (Logger, dst) dan TIDAK dikirim ke client.
  - Data dijadikan JSON-safe sebelum dikirim.

Urutan terhadap event "response": ws.py memanggil `await bridge.flush()`
sebelum mengirim response/error/cancelled, jadi semua tool_start/tool_finish
tiba lebih dulu (perilaku yang sama dengan drain lama).
"""

import asyncio
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Optional

from core.events import EventNames, WILDCARD, Event, EventBus, event_bus, json_safe

logger = logging.getLogger("aira.ws.bridge")

# nama event bus -> nama "type" di protokol WebSocket (frontend bergantung
# pada nama underscore ini - jangan diubah sepihak).
DEFAULT_WS_EVENT_MAP: dict[str, str] = {
    EventNames.THINKING_START: "thinking",
    EventNames.TOOL_START: "tool_start",
    EventNames.TOOL_PROGRESS: "tool_progress",
    EventNames.TOOL_FINISH: "tool_finish",
    EventNames.SYSTEM_ERROR: "error",
}

Sender = Callable[[str, dict], Awaitable[None]]


async def _default_sender(session_id: str, payload: dict) -> None:
    # Import malas: modul ini bisa dites tanpa FastAPI.
    from api.ws_manager import manager

    await manager.send(session_id, payload)


class WebSocketEventBridge:

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        sender: Optional[Sender] = None,
        event_map: Optional[dict[str, str]] = None,
    ):
        self._bus = bus if bus is not None else event_bus
        self._sender: Sender = sender or _default_sender
        self._map = dict(event_map if event_map is not None else DEFAULT_WS_EVENT_MAP)

        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self._consumer: Optional[asyncio.Task] = None
        self._token: Optional[str] = None

    # ------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Idempotent. Panggil dari thread event loop (startup FastAPI atau
        awal koneksi WebSocket). Kalau sudah jalan di loop yang sama: no-op.
        """
        loop = loop or asyncio.get_running_loop()

        with self._lock:
            if (
                self._token is not None
                and self._loop is loop
                and not loop.is_closed()
            ):
                return

            self._detach_locked()

            self._loop = loop
            self._queue = asyncio.Queue()
            self._consumer = loop.create_task(self._consume(self._queue))
            self._token = self._bus.subscribe(WILDCARD, self._on_event)

        self._bus.bind_loop(loop)

        logger.info("WS BRIDGE | aktif (subscriber wildcard terdaftar).")

    ensure_started = start

    async def stop(self) -> None:
        with self._lock:
            consumer = self._consumer
            loop = self._loop
            self._detach_locked()

        if consumer is not None:
            await asyncio.gather(consumer, return_exceptions=True)

        self._bus.unbind_loop(loop)

        logger.info("WS BRIDGE | dihentikan.")

    def _detach_locked(self) -> None:
        if self._token is not None:
            self._bus.unsubscribe(WILDCARD, self._token)
            self._token = None

        if self._consumer is not None:
            try:
                self._consumer.cancel()
            except Exception:
                pass
            self._consumer = None

        self._queue = None
        self._loop = None

    @property
    def is_started(self) -> bool:
        with self._lock:
            return self._token is not None

    # ------------------------------------------------------------
    # EVENT BUS -> QUEUE  (dipanggil di thread publisher mana pun)
    # ------------------------------------------------------------

    def translate(self, event: Event) -> Optional[tuple[str, dict]]:
        """
        Event bus -> (session_id, payload WebSocket), atau None kalau event
        ini tidak boleh/perlu dikirim ke client.
        """
        session_id = event.metadata.get("session_id")
        run_id = event.metadata.get("run_id")

        if not session_id or not run_id:
            return None

        ws_type = self._map.get(event.event)

        if ws_type is None:
            return None

        data = json_safe(dict(event.data))

        if not isinstance(data, dict):
            data = {"value": data}

        data["session_id"] = session_id
        data["run_id"] = run_id

        return session_id, {
            "type": ws_type,
            "data": data,
            "ts": time.time(),
            "event_id": event.event_id,
            "correlation_id": event.correlation_id,
        }

    def _on_event(self, event: Event) -> None:
        """Subscriber sync: cepat, tidak pernah blocking."""
        translated = self.translate(event)

        if translated is None:
            return

        with self._lock:
            loop, queue = self._loop, self._queue

        if loop is None or queue is None or loop.is_closed():
            return

        loop.call_soon_threadsafe(queue.put_nowait, translated)

    # ------------------------------------------------------------
    # QUEUE -> WEBSOCKET
    # ------------------------------------------------------------

    async def _consume(self, queue: "asyncio.Queue") -> None:
        while True:
            session_id, payload = await queue.get()

            try:
                await self._sender(session_id, payload)
            except Exception:
                logger.exception(
                    "WS BRIDGE | gagal mengirim event (session=%s type=%s).",
                    session_id, payload.get("type"),
                )
            finally:
                queue.task_done()

    async def flush(self, timeout: float = 5.0) -> bool:
        """
        Tunggu sampai semua event yang sudah masuk antrean terkirim.
        True kalau tuntas (atau bridge belum aktif), False kalau timeout.
        """
        with self._lock:
            queue = self._queue

        if queue is None:
            return True

        # call_soon_threadsafe(queue.put_nowait, ...) baru berjalan di
        # iterasi loop berikutnya. Tanpa yield ini, join() bisa melihat
        # antrean "kosong" padahal event sudah dijadwalkan tapi belum masuk.
        await asyncio.sleep(0)

        try:
            await asyncio.wait_for(queue.join(), timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning("WS BRIDGE | flush timeout (%.1fs).", timeout)
            return False


_bridge_singleton: Optional[WebSocketEventBridge] = None
_bridge_lock = threading.Lock()


def get_ws_bridge() -> WebSocketEventBridge:
    global _bridge_singleton

    if _bridge_singleton is None:
        with _bridge_lock:
            if _bridge_singleton is None:
                _bridge_singleton = WebSocketEventBridge()

    return _bridge_singleton
