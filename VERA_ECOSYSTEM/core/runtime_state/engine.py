"""
core/runtime_state/engine.py — Runtime State Engine (Sprint 2 / Worker 3).

SATU-SATUNYA pemilik state runtime AIRA (IDLE / LISTENING / THINKING / SPEAKING).
Tidak ada state paralel di modul lain: Brain/Planner/WS/frontend hanya
MEMPUBLISH event; engine ini yang menerjemahkannya jadi state.

    Brain / Planner / lapisan suara
            |  event_bus.publish(...)
            v
        Event Bus  --(subscriber sync, cepat)-->  RuntimeStateEngine.handle_event
                                                        |  state berubah
                                                        v
                                  event_bus.publish("runtime.state_changed")

Tidak membuat event bus baru, tidak melakukan reasoning, tidak memanggil LLM/tool.

Pemetaan event -> aktivitas
---------------------------
    thinking.start        begin THINKING   (owner = correlation_id giliran)
    thinking.finish       end   THINKING   (owner = correlation_id giliran)
    voice.listening.start begin LISTENING  (owner = data.owner | session_id | "default")
    voice.listening.stop  end   LISTENING
    speech.start          begin SPEAKING   (owner = data.owner | session_id | "default")
    speech.finish         end   SPEAKING
    response.ready        begin SPEAKING   HANYA kalau turn ditandai bersuara:
                                           metadata["speak"] / data["speak"] == True
                                           dan data["error"] tidak True

Kenapa response.ready TIDAK otomatis SPEAKING
    1. Urutan nyata di Brain: thinking.finish -> task.finished -> response.ready.
       THINKING sudah berakhir sebelum response.ready datang.
    2. response.ready tidak membawa info apakah jawaban akan diucapkan (jawaban
       chat teks juga menghasilkan response.ready). Menjadikannya SPEAKING tanpa
       info itu akan membuat state menggantung di SPEAKING untuk chat teks.
    Lapisan suara cukup membungkus giliran dengan event_scope(speak=True) atau
    mempublish speech.start / speech.finish - engine sudah siap menerimanya.

Concurrency
-----------
Beberapa giliran/sesi bisa berjalan bersamaan. Tiap aktivitas punya himpunan
owner; state resmi mengikuti prioritas (lihat models.py) sehingga giliran A yang
selesai tidak menjatuhkan state ke IDLE selama giliran B masih THINKING.
Semua mutasi di bawah RLock; event runtime.state_changed dipublish DI DALAM lock
supaya urutannya sama dengan urutan perubahan (subscriber bus WAJIB non-blocking,
sesuai kontrak Event Bus).

Keandalan
---------
- Transisi tidak sah (LISTENING -> SPEAKING) DITOLAK: aktivitas tidak dicatat.
- begin berulang untuk owner yang sama = idempotent (hanya menyegarkan umur).
- end untuk owner yang tidak aktif = diabaikan.
- Aktivitas yang tidak pernah ditutup kedaluwarsa (DEFAULT_STALE_AFTER), dicek
  lazy tiap event / snapshot() - tanpa thread latar.
- handle_event() tidak pernah raise ke publisher.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Mapping, Optional

from core.events import EventBus, Event, EventNames, event_bus
from core.runtime_state.models import (
    ACTIVITY_PRIORITY,
    DEFAULT_STALE_AFTER,
    RuntimeEvents,
    RuntimeSnapshot,
    RuntimeState,
    is_valid_transition,
    resolve_state,
)

logger = logging.getLogger("aira.runtime_state")

BEGIN = "begin"
END = "end"

# event bus -> (aktivitas, aksi, owner_dari_giliran)
#   owner_dari_giliran=True  -> default owner = correlation_id (satu giliran chat)
#   owner_dari_giliran=False -> default owner = session_id / "default"
_ROUTES: Mapping[str, tuple[RuntimeState, str, bool]] = {
    EventNames.THINKING_START: (RuntimeState.THINKING, BEGIN, True),
    EventNames.THINKING_FINISH: (RuntimeState.THINKING, END, True),
    RuntimeEvents.VOICE_LISTENING_START: (RuntimeState.LISTENING, BEGIN, False),
    RuntimeEvents.VOICE_LISTENING_STOP: (RuntimeState.LISTENING, END, False),
    RuntimeEvents.SPEECH_START: (RuntimeState.SPEAKING, BEGIN, False),
    RuntimeEvents.SPEECH_FINISH: (RuntimeState.SPEAKING, END, False),
}

_SPEAK_ROUTE = (RuntimeState.SPEAKING, BEGIN, False)

# Semua event yang di-subscribe engine (subscribe spesifik, BUKAN wildcard).
SUBSCRIBED_EVENTS: tuple[str, ...] = (*_ROUTES.keys(), EventNames.RESPONSE_READY)


def _wants_speech(event: Event) -> bool:
    """response.ready hanya berarti 'akan bicara' kalau ditandai eksplisit."""
    if event.data.get("error"):
        return False
    return event.metadata.get("speak") is True or event.data.get("speak") is True


def _route_for(event: Event) -> Optional[tuple[RuntimeState, str, bool]]:
    route = _ROUTES.get(event.event)

    if route is not None:
        return route

    if event.event == EventNames.RESPONSE_READY and _wants_speech(event):
        return _SPEAK_ROUTE

    return None


def _owner_of(event: Event, from_turn: bool) -> str:
    explicit = event.data.get("owner")

    if explicit:
        return str(explicit)

    if from_turn:
        return str(event.correlation_id)

    return str(event.metadata.get("session_id") or "default")


class RuntimeStateEngine:
    """
    Dependency Injection: bus, clock, dan batas kedaluwarsa bisa disuntik
    (test memakai EventBus baru + clock palsu). Instance produksi lewat
    get_runtime_state().
    """

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
        stale_after: Optional[Mapping[RuntimeState, float]] = None,
        publish_events: bool = True,
    ):
        self._bus = bus if bus is not None else event_bus
        self._clock = clock or time.monotonic
        self._stale_after = {**DEFAULT_STALE_AFTER, **(stale_after or {})}
        self._publish_events = publish_events

        self._lock = threading.RLock()
        self._tokens: list[tuple[str, str]] = []

        self._state = RuntimeState.IDLE
        self._previous: Optional[RuntimeState] = None
        self._since = time.time()
        self._seq = 0
        self._reason: Optional[str] = None

        # aktivitas -> {owner: waktu (clock) terakhir diperbarui}
        self._owners: dict[RuntimeState, dict[str, float]] = {
            activity: {} for activity in ACTIVITY_PRIORITY
        }

        self._stats = {"repeated": 0, "ignored": 0, "rejected": 0, "expired": 0}

    # ============================================================ LIFECYCLE

    def start(self) -> None:
        """Subscribe ke Event Bus. Idempotent."""
        with self._lock:
            if self._tokens:
                return

            for name in SUBSCRIBED_EVENTS:
                self._tokens.append((name, self._bus.subscribe(name, self.handle_event)))

        logger.info("RUNTIME STATE | aktif (%d event di-subscribe).", len(SUBSCRIBED_EVENTS))

    def stop(self) -> None:
        """Lepas semua subscription. State & owner dibiarkan apa adanya."""
        with self._lock:
            tokens, self._tokens = self._tokens, []

        for name, token in tokens:
            self._bus.unsubscribe(name, token)

    @property
    def is_started(self) -> bool:
        with self._lock:
            return bool(self._tokens)

    # =============================================================== READ

    @property
    def state(self) -> RuntimeState:
        return self.snapshot().state

    def snapshot(self) -> RuntimeSnapshot:
        """Potret state saat ini (sekaligus membuang aktivitas yang kedaluwarsa)."""
        with self._lock:
            self._sweep_locked()
            return self._snapshot_locked()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {**self._stats, "transitions": self._seq}

    # ============================================================== WRITE

    def handle_event(self, event: Event) -> None:
        """
        Subscriber Event Bus. Sinkron, cepat, TIDAK PERNAH raise.
        Event yang tidak dikenal diabaikan tanpa efek.
        """
        try:
            route = _route_for(event)

            if route is None:
                return

            activity, action, from_turn = route
            owner = _owner_of(event, from_turn)

            with self._lock:
                self._sweep_locked()
                self._apply_locked(activity, action, owner, event.event)

        except Exception:
            logger.exception("RUNTIME STATE | gagal memproses event (diabaikan).")

    def reset(self, reason: str = "reset") -> None:
        """Buang semua aktivitas dan paksa IDLE (mis. sesudah error tak terduga)."""
        with self._lock:
            for owners in self._owners.values():
                owners.clear()

            self._settle_locked(reason)

    # ============================================================ INTERNAL

    def _counts_locked(self) -> dict[RuntimeState, int]:
        return {activity: len(owners) for activity, owners in self._owners.items()}

    def _snapshot_locked(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            state=self._state,
            previous=self._previous,
            since=self._since,
            seq=self._seq,
            reason=self._reason,
            active={
                activity.value.lower(): count
                for activity, count in self._counts_locked().items()
            },
        )

    def _apply_locked(self, activity: RuntimeState, action: str, owner: str, reason: str) -> None:
        owners = self._owners[activity]
        now = self._clock()

        if action == BEGIN and owner in owners:
            # thinking.start dikirim Planner tiap fase: cukup segarkan umur.
            owners[owner] = now
            self._stats["repeated"] += 1
            return

        if action == END and owner not in owners:
            self._stats["ignored"] += 1
            return

        counts = self._counts_locked()
        counts[activity] += 1 if action == BEGIN else -1
        target = resolve_state(counts)

        if target != self._state and not is_valid_transition(self._state, target):
            self._stats["rejected"] += 1
            logger.warning(
                "RUNTIME STATE | transisi ditolak %s -> %s (event=%s owner=%s).",
                self._state.value, target.value, reason, owner,
            )
            return

        if action == BEGIN:
            owners[owner] = now
        else:
            del owners[owner]

        if target != self._state:
            self._change_locked(target, reason)

    def _sweep_locked(self) -> None:
        """Buang aktivitas yang tidak pernah ditutup. Hanya MENGURANGI aktivitas,
        jadi transisi hasilnya selalu turun prioritas (selalu sah menurut tabel)."""
        now = self._clock()
        removed = 0

        for activity, owners in self._owners.items():
            limit = self._stale_after.get(activity)

            if not limit:
                continue

            for owner in [o for o, seen in owners.items() if now - seen > limit]:
                del owners[owner]
                removed += 1
                logger.warning(
                    "RUNTIME STATE | aktivitas %s (owner=%s) kedaluwarsa setelah %.0fs.",
                    activity.value, owner, limit,
                )

        if removed:
            self._stats["expired"] += removed
            self._settle_locked("stale_expired")

    def _settle_locked(self, reason: str) -> None:
        target = resolve_state(self._counts_locked())

        if target != self._state:
            self._change_locked(target, reason)

    def _change_locked(self, target: RuntimeState, reason: str) -> None:
        self._previous = self._state
        self._state = target
        self._since = time.time()
        self._seq += 1
        self._reason = reason

        snapshot = self._snapshot_locked()

        logger.info(
            "RUNTIME STATE | %s -> %s (seq=%d reason=%s)",
            snapshot.previous.value if snapshot.previous else "-",
            snapshot.state.value, snapshot.seq, reason,
        )

        self._emit(snapshot)

    def _emit(self, snapshot: RuntimeSnapshot) -> None:
        if not self._publish_events:
            return

        try:
            self._bus.publish(
                RuntimeEvents.STATE_CHANGED,
                source="RUNTIME", agent="RUNTIME",
                data=snapshot.to_dict(),
            )
        except Exception:
            logger.exception("RUNTIME STATE | gagal publish runtime.state_changed (diabaikan).")


# ================================================================ SINGLETON

_engine_singleton: Optional[RuntimeStateEngine] = None
_engine_lock = threading.Lock()


def get_runtime_state() -> RuntimeStateEngine:
    """Engine global (terhubung ke event_bus global). Otomatis start(); idempotent."""
    global _engine_singleton

    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                engine = RuntimeStateEngine()
                engine.start()
                _engine_singleton = engine

    return _engine_singleton


def runtime_state_snapshot() -> dict[str, Any]:
    """Snapshot JSON-safe dari engine global (dipakai Context Builder)."""
    return get_runtime_state().snapshot().to_dict()