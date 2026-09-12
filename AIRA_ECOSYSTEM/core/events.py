"""
core/events.py — Event Bus internal AIRA OS (Phase 1.1).

Taruh file ini di: AIRA_ECOSYSTEM/core/events.py

Pusat publish/subscribe yang menghubungkan AIRA, AKANE, REI, HIKARI, YUKI,
Logger, WebSocket, Memory, dan Scheduler TANPA mereka saling import/panggil
langsung satu sama lain. Tujuannya: modular, realtime, dan longgar (loosely
coupled) — modul cukup publish event, siapa pun yang butuh cukup subscribe.

DESAIN SINGKAT
--------------
- EventBus menyimpan subscriber per nama event di dict `_subscribers`.
- subscribe("*", cb) mendaftarkan listener wildcard yang menerima SEMUA
  event apa pun namanya (dipakai Logger/WebSocket agar tidak perlu daftar
  satu-satu untuk setiap event baru).
- publish() membentuk payload standar lalu men-dispatch ke:
    1) subscriber event spesifik (mis. "tool.start")
    2) subscriber wildcard ("*")
  Setiap event yang dipublish OTOMATIS dicatat ke core/logger.py (kategori
  "eventbus") — jadi Logger dianggap sudah "subscribe" ke semua event
  secara bawaan, tanpa perlu registrasi manual.
- Dispatch aman dipanggil dari context sync (thread biasa, mis. dari
  agents/rei/planner.py yang berjalan di asyncio.to_thread) MAUPUN dari
  context async (event loop FastAPI/WebSocket):
    - Kalau ada event loop berjalan di thread saat ini -> tiap callback
      (sync maupun async) dijadwalkan sebagai task terpisah, non-blocking,
      fire-and-forget.
    - Kalau TIDAK ada event loop berjalan (dipanggil dari thread murni
      sync) -> semua callback dieksekusi lewat asyncio.run() sekali per
      publish, supaya publish() tetap bisa dipanggil dari mana saja tanpa
      syarat khusus.
    - Setiap callback dibungkus try/except sendiri-sendiri -> satu
      subscriber error TIDAK menjatuhkan subscriber lain maupun publisher.
- Thread-safe: akses ke `_subscribers` dilindungi `threading.Lock`, karena
  publisher (mis. worker thread tool SSH) bisa berjalan bersamaan dengan
  subscriber yang didaftarkan/dihapus dari event loop utama (WebSocket).

TIDAK ADA PERUBAHAN pada persona, scheduler, workspace, tool SSH, skema
database, atau REST API di file ini — murni modul baru, mandiri.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Union

from core.logger import get_logger, log_event

logger = get_logger("eventbus")

# ============================================================
# STANDARD EVENT NAMES
# ============================================================
# Konstanta disediakan supaya pemanggil tidak perlu mengetik ulang string
# literal dan typo-safe (mis. EventNames.TOOL_START, bukan "tool.strat").


class EventNames:
    CHAT_RECEIVED = "chat.received"
    THINKING_START = "thinking.start"
    THINKING_FINISH = "thinking.finish"
    TOOL_START = "tool.start"
    TOOL_PROGRESS = "tool.progress"
    TOOL_FINISH = "tool.finish"
    RESPONSE_READY = "response.ready"
    MEMORY_SAVED = "memory.saved"
    SYSTEM_ERROR = "system.error"


# Semua nama event standar Phase 1.1, dipakai untuk validasi ringan/opsional.
STANDARD_EVENTS: frozenset[str] = frozenset(
    {
        EventNames.CHAT_RECEIVED,
        EventNames.THINKING_START,
        EventNames.THINKING_FINISH,
        EventNames.TOOL_START,
        EventNames.TOOL_PROGRESS,
        EventNames.TOOL_FINISH,
        EventNames.RESPONSE_READY,
        EventNames.MEMORY_SAVED,
        EventNames.SYSTEM_ERROR,
    }
)

# Nama wildcard: subscriber yang didaftarkan di sini menerima SEMUA event,
# apa pun namanya (termasuk event custom di luar STANDARD_EVENTS).
WILDCARD = "*"

# Tipe callback: boleh fungsi sync biasa atau coroutine function (async def).
EventCallback = Callable[["Event"], Union[None, Awaitable[None]]]


@dataclass(frozen=True)
class Event:
    """
    Payload event yang konsisten untuk seluruh sistem AIRA OS.

    Contoh bentuk saat di-serialize (lihat Event.to_dict()):
        {
            "event": "tool.start",
            "agent": "AKANE",
            "tool": "ssh",
            "timestamp": "2026-09-12T10:00:00.000000+00:00",
            "data": {}
        }
    """

    event: str
    agent: Optional[str] = None
    tool: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "agent": self.agent,
            "tool": self.tool,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class _Subscription:
    token: str
    callback: EventCallback


class EventBus:
    """
    Pusat publish/subscribe internal AIRA OS.

    Penggunaan dasar:
        from core.events import event_bus, EventNames

        # subscribe ke event spesifik
        token = event_bus.subscribe(EventNames.TOOL_START, my_handler)

        # subscribe ke SEMUA event (mis. untuk WebSocket relay)
        token_all = event_bus.subscribe("*", relay_to_websocket)

        # publish event
        event_bus.publish(
            EventNames.TOOL_START,
            agent="AKANE",
            tool="ssh",
            data={"device": "R1", "command": "/system resource print"},
        )

        # unsubscribe
        event_bus.unsubscribe(EventNames.TOOL_START, token)
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[_Subscription]] = {}
        self._lock = threading.Lock()

    # --------------------------------------------------------
    # SUBSCRIBE / UNSUBSCRIBE
    # --------------------------------------------------------

    def subscribe(self, event_name: str, callback: EventCallback) -> str:
        """
        Daftarkan callback untuk event_name tertentu, atau EventBus.WILDCARD
        ("*") untuk menerima SEMUA event. callback boleh fungsi sync biasa
        `def cb(event: Event) -> None` atau coroutine `async def cb(event)`.

        Return: token (str) yang dipakai untuk unsubscribe() nanti.
        """

        if not event_name:
            raise ValueError("event_name tidak boleh kosong.")

        token = uuid.uuid4().hex

        with self._lock:
            self._subscribers.setdefault(event_name, []).append(
                _Subscription(token=token, callback=callback)
            )

        logger.debug(
            "SUBSCRIBE | event=%s | token=%s | total_subscriber=%d",
            event_name,
            token,
            len(self._subscribers.get(event_name, [])),
        )

        return token

    def unsubscribe(self, event_name: str, token: str) -> bool:
        """
        Hapus subscriber berdasarkan token yang dikembalikan subscribe().
        Return True kalau ditemukan & dihapus, False kalau tidak ada.
        """

        with self._lock:
            subs = self._subscribers.get(event_name)

            if not subs:
                return False

            new_subs = [s for s in subs if s.token != token]
            removed = len(new_subs) != len(subs)

            if new_subs:
                self._subscribers[event_name] = new_subs
            else:
                self._subscribers.pop(event_name, None)

        if removed:
            logger.debug("UNSUBSCRIBE | event=%s | token=%s", event_name, token)

        return removed

    def clear(self, event_name: Optional[str] = None) -> None:
        """
        Hapus semua subscriber. Kalau event_name diberikan, hanya event
        tersebut yang dibersihkan; kalau None, SEMUA subscriber (termasuk
        wildcard) dihapus. Terutama berguna untuk unit test agar bus tidak
        "bocor" state antar test case.
        """

        with self._lock:
            if event_name is None:
                self._subscribers.clear()
            else:
                self._subscribers.pop(event_name, None)

    # --------------------------------------------------------
    # PUBLISH
    # --------------------------------------------------------

    def publish(
        self,
        event_name: str,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Bentuk payload standar dan dispatch ke seluruh subscriber yang
        relevan (event spesifik + wildcard). Setiap publish otomatis
        dicatat ke core/logger.py (kategori "eventbus") sehingga Logger
        "menerima semua event" tanpa perlu subscribe manual.

        Aman dipanggil dari thread sync biasa maupun dari dalam event loop
        asyncio (mis. handler WebSocket).

        Return: instance Event yang baru dipublish (berguna kalau
        pemanggil ingin memakai timestamp/isi payload yang sama).
        """

        event = Event(
            event=event_name,
            agent=agent,
            tool=tool,
            data=data or {},
        )

        self._log_event(event)
        self._dispatch(event)

        return event

    # --------------------------------------------------------
    # INTERNAL: LOGGING
    # --------------------------------------------------------

    def _log_event(self, event: Event) -> None:
        try:
            log_event(
                logger,
                "DEBUG",
                f"EVENT | {event.event}",
                category="eventbus",
                context=event.to_dict(),
            )
        except Exception:
            # Logging tidak boleh pernah menggagalkan publish().
            logger.exception("Gagal mencatat event ke log_store (diabaikan).")

    # --------------------------------------------------------
    # INTERNAL: DISPATCH
    # --------------------------------------------------------

    def _collect_subscriptions(self, event_name: str) -> list[_Subscription]:
        with self._lock:
            specific = list(self._subscribers.get(event_name, []))
            wildcard = list(self._subscribers.get(WILDCARD, []))

        return specific + wildcard

    def _dispatch(self, event: Event) -> None:
        subscriptions = self._collect_subscriptions(event.event)

        if not subscriptions:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Kita sedang berada di dalam event loop asyncio yang aktif
            # (mis. dipanggil dari coroutine handler WebSocket). Jadwalkan
            # tiap callback sebagai task terpisah -> non-blocking, dan
            # error di satu subscriber tidak menghentikan yang lain.
            for sub in subscriptions:
                loop.create_task(self._run_callback_async(sub, event))
        else:
            # Tidak ada event loop di thread ini (dipanggil dari kode sync
            # biasa, mis. agents/rei/planner.py atau tools/*). Jalankan
            # semua callback secara blocking-singkat lewat event loop
            # sementara, supaya publish() tetap bisa dipanggil dari mana
            # saja tanpa syarat khusus.
            asyncio.run(self._run_all_async(subscriptions, event))

    async def _run_all_async(
        self, subscriptions: list[_Subscription], event: Event
    ) -> None:
        await asyncio.gather(
            *(self._run_callback_async(sub, event) for sub in subscriptions),
            return_exceptions=True,
        )

    async def _run_callback_async(self, sub: _Subscription, event: Event) -> None:
        try:
            result = sub.callback(event)

            if asyncio.iscoroutine(result):
                await result

        except Exception:
            logger.exception(
                "Subscriber error (diabaikan, tidak mengganggu subscriber lain) "
                "| event=%s | token=%s",
                event.event,
                sub.token,
            )


# ============================================================
# GLOBAL SINGLETON
# ============================================================
# Modul lain (AIRA/AKANE/REI/HIKARI/YUKI/WebSocket/Memory/Scheduler) cukup
# `from core.events import event_bus` untuk publish/subscribe tanpa perlu
# membuat instance sendiri atau melewatkan referensi lewat parameter.

event_bus = EventBus()