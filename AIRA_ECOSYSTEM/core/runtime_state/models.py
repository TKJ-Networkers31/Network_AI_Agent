"""
core/runtime_state/models.py — kontrak Runtime State AIRA (Sprint 2 / Worker 3).

HANYA bentuk data + aturan murni (enum, tabel transisi, prioritas, snapshot).
Tanpa I/O, tanpa Event Bus, tanpa threading - semua itu tugas engine.py.

Model
-----
Ada SATU state resmi:

    IDLE       tidak ada aktivitas
    LISTENING  input suara pengguna sedang ditangkap
    THINKING   AIRA sedang memproses satu/lebih giliran (classifier/planner/tool)
    SPEAKING   AIRA sedang berbicara

Tiga state non-IDLE berasal dari "aktivitas" yang punya pemilik (owner). Boleh ada
beberapa aktivitas sekaligus (mis. dua sesi chat berjalan bersamaan), jadi state
resmi = aktivitas berprioritas tertinggi yang masih aktif:

    SPEAKING > THINKING > LISTENING > IDLE

Invarian yang selalu dijaga engine:  state == resolve_state(jumlah owner per aktivitas)

Nama event baru
---------------
RuntimeEvents berisi event yang BELUM ada di core.events.EventNames. Nilainya
konvensi "<domain>.<action>" yang sama dengan EventNames, sehingga bisa dipindah
ke EventNames tanpa mengubah string apa pun (lihat docs/roadmap - remaining issues).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional
from core.events import EventNames


class RuntimeState(str, Enum):
    """str-Enum: langsung JSON-serializable dan bisa dibandingkan dengan string."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


class RuntimeEvents:
    """Compatibility surface for Runtime State's event names.

    These are no longer independently defined strings — they are aliases
    onto core.events.EventNames, which is the single authoritative source
    for event-name strings across AIRA. This class exists only so existing
    callers (engine.py, tests, any other consumer importing RuntimeEvents
    from core.runtime_state) do not need to change their import path or
    attribute names.
    """

    STATE_CHANGED = EventNames.RUNTIME_STATE_CHANGED
    VOICE_LISTENING_START = EventNames.VOICE_LISTENING_START
    VOICE_LISTENING_STOP = EventNames.VOICE_LISTENING_STOP
    SPEECH_START = EventNames.SPEECH_START
    SPEECH_FINISH = EventNames.SPEECH_FINISH


# Urutan prioritas (tertinggi dulu) untuk state yang berasal dari aktivitas.
ACTIVITY_PRIORITY: tuple[RuntimeState, ...] = (
    RuntimeState.SPEAKING,
    RuntimeState.THINKING,
    RuntimeState.LISTENING,
)

# Transisi yang DIIZINKAN (src -> {dst}). Self-transition bukan transisi.
#
# Satu-satunya pasangan yang sengaja dilarang: LISTENING -> SPEAKING.
# AIRA tidak boleh mulai bicara saat mikrofon pengguna sedang menangkap input;
# lapisan suara harus menutup LISTENING lebih dulu. Event speech.start yang
# melanggar ini DITOLAK oleh engine (state tidak berubah, dihitung di stats).
ALLOWED_TRANSITIONS: Mapping[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.IDLE: frozenset({
        RuntimeState.LISTENING, RuntimeState.THINKING, RuntimeState.SPEAKING,
    }),
    RuntimeState.LISTENING: frozenset({
        RuntimeState.IDLE, RuntimeState.THINKING,
    }),
    RuntimeState.THINKING: frozenset({
        RuntimeState.IDLE, RuntimeState.SPEAKING, RuntimeState.LISTENING,
    }),
    RuntimeState.SPEAKING: frozenset({
        RuntimeState.IDLE, RuntimeState.LISTENING, RuntimeState.THINKING,
    }),
}

# Batas umur satu aktivitas tanpa event pembaruan (detik). Jaring pengaman kalau
# event penutup (thinking.finish / speech.finish / ...) tidak pernah datang,
# mis. thread pekerja mati. thinking.start berulang menyegarkan umurnya.
DEFAULT_STALE_AFTER: Mapping[RuntimeState, float] = {
    RuntimeState.THINKING: 1800.0,
    RuntimeState.LISTENING: 300.0,
    RuntimeState.SPEAKING: 600.0,
}


def is_valid_transition(source: RuntimeState, target: RuntimeState) -> bool:
    """True kalau source -> target transisi yang sah (self-transition = False)."""
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())


def resolve_state(counts: Mapping[RuntimeState, int]) -> RuntimeState:
    """State resmi dari jumlah owner tiap aktivitas (prioritas SPEAKING > THINKING > LISTENING)."""
    for state in ACTIVITY_PRIORITY:
        if counts.get(state, 0) > 0:
            return state
    return RuntimeState.IDLE


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Potret state pada satu saat (immutable, JSON-safe lewat to_dict)."""

    state: RuntimeState = RuntimeState.IDLE
    previous: Optional[RuntimeState] = None
    since: float = 0.0                      # epoch detik saat state ini mulai
    seq: int = 0                            # naik 1 tiap state BERUBAH (0 = belum pernah)
    reason: Optional[str] = None            # event/alasan penyebab perubahan terakhir
    active: dict[str, int] = field(default_factory=dict)   # {"listening": n, ...}

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "previous": self.previous.value if self.previous else None,
            "since": self.since,
            "seq": self.seq,
            "reason": self.reason,
            "active": dict(self.active),
        }