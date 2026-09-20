"""
tests/test_runtime_state.py — unit test Runtime State Engine (Sprint 2 / Worker 3).

Cakupan:
  - state awal, snapshot, serialisasi
  - tabel transisi + prioritas state
  - integrasi Event Bus (subscribe/unsubscribe, event lifecycle nyata Brain/Planner,
    event suara, runtime.state_changed)
  - transisi tidak sah, event duplikat/tidak dikenal, event rusak
  - concurrency (giliran tumpang-tindih, thread paralel, urutan event)
  - kedaluwarsa aktivitas yang tidak pernah ditutup
  - Context Builder (data-only, tidak masuk prompt)
  - Brain asli (lifecycle THINKING -> IDLE, cancel dini, error, hint speak)

Setiap test memakai EventBus + RuntimeStateEngine BARU (bukan singleton global),
jadi tidak saling mengganggu dan tidak menyentuh database/provider asli.
Test Brain di-skip (bukan gagal) kalau dependency runtime-nya tidak terpasang.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_runtime_state -v
"""

import json
import logging
import threading
import types
import unittest
from unittest import mock

from core.context import ContextBuilder
from core.context import builder as builder_module
from core.events import EventBus, EventNames, event_scope
from core.runtime_state import (
    ALLOWED_TRANSITIONS,
    SUBSCRIBED_EVENTS,
    RuntimeEvents,
    RuntimeState,
    RuntimeStateEngine,
    get_runtime_state,
    is_valid_transition,
    resolve_state,
    runtime_state_snapshot,
)
from core.runtime_state import engine as engine_module

IDLE = RuntimeState.IDLE
LISTENING = RuntimeState.LISTENING
THINKING = RuntimeState.THINKING
SPEAKING = RuntimeState.SPEAKING

ENGINE_LOGGER = "aira.runtime_state"


def setUpModule():
    # Beberapa test sengaja memicu penolakan/kedaluwarsa (warning) dan event rusak.
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


# ============================================================
# HELPER
# ============================================================

class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make(**kwargs):
    """(bus, engine, clock, events) - engine sudah start; events = runtime.state_changed."""
    bus = EventBus()
    clock = FakeClock()
    engine = RuntimeStateEngine(bus, clock=clock, **kwargs)
    engine.start()

    events = []
    bus.subscribe(RuntimeEvents.STATE_CHANGED, events.append)

    return bus, engine, clock, events


def states(events) -> list[str]:
    return [event.data["state"] for event in events]


def think_start(bus, turn="t1"):
    bus.publish(EventNames.THINKING_START, correlation_id=turn, data={"message": "..."})


def think_finish(bus, turn="t1"):
    bus.publish(EventNames.THINKING_FINISH, correlation_id=turn)


def listen_start(bus, owner="s1"):
    bus.publish(RuntimeEvents.VOICE_LISTENING_START, data={"owner": owner})


def listen_stop(bus, owner="s1"):
    bus.publish(RuntimeEvents.VOICE_LISTENING_STOP, data={"owner": owner})


def speech_start(bus, owner="s1"):
    bus.publish(RuntimeEvents.SPEECH_START, data={"owner": owner})


def speech_finish(bus, owner="s1"):
    bus.publish(RuntimeEvents.SPEECH_FINISH, data={"owner": owner})


def assert_invariant(test: unittest.TestCase, engine: RuntimeStateEngine) -> None:
    """state resmi HARUS sama dengan hasil prioritas dari jumlah aktivitas."""
    snapshot = engine.snapshot()
    counts = {RuntimeState[name.upper()]: count for name, count in snapshot.active.items()}
    test.assertEqual(snapshot.state, resolve_state(counts))


# ============================================================
# STATE AWAL
# ============================================================

class TestInitialState(unittest.TestCase):

    def test_engine_starts_idle_with_empty_snapshot(self):
        engine = RuntimeStateEngine(EventBus())
        snapshot = engine.snapshot()

        self.assertEqual(snapshot.state, IDLE)
        self.assertIsNone(snapshot.previous)
        self.assertEqual(snapshot.seq, 0)
        self.assertIsNone(snapshot.reason)
        self.assertEqual(snapshot.active, {"speaking": 0, "thinking": 0, "listening": 0})
        self.assertEqual(engine.state, IDLE)

    def test_not_started_until_start_is_called(self):
        engine = RuntimeStateEngine(EventBus())
        self.assertFalse(engine.is_started)

        engine.start()
        self.assertTrue(engine.is_started)

    def test_state_is_a_json_friendly_string_enum(self):
        self.assertEqual(IDLE, "IDLE")
        self.assertEqual(json.dumps({"s": THINKING}), '{"s": "THINKING"}')
        self.assertEqual([s.value for s in RuntimeState], ["IDLE", "LISTENING", "THINKING", "SPEAKING"])

    def test_snapshot_to_dict_is_json_serializable(self):
        payload = RuntimeStateEngine(EventBus()).snapshot().to_dict()

        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertEqual(payload["state"], "IDLE")
        self.assertIsNone(payload["previous"])

    def test_initial_stats_are_zero(self):
        self.assertEqual(
            RuntimeStateEngine(EventBus()).stats(),
            {"repeated": 0, "ignored": 0, "rejected": 0, "expired": 0, "transitions": 0},
        )


# ============================================================
# TABEL TRANSISI
# ============================================================

class TestTransitionTable(unittest.TestCase):

    def test_valid_transitions(self):
        valid = [
            (IDLE, LISTENING), (IDLE, THINKING), (IDLE, SPEAKING),
            (LISTENING, IDLE), (LISTENING, THINKING),
            (THINKING, IDLE), (THINKING, SPEAKING), (THINKING, LISTENING),
            (SPEAKING, IDLE), (SPEAKING, LISTENING), (SPEAKING, THINKING),
        ]
        for source, target in valid:
            self.assertTrue(is_valid_transition(source, target), f"{source} -> {target}")

    def test_listening_to_speaking_is_the_only_forbidden_pair(self):
        invalid = [
            (source, target)
            for source in RuntimeState
            for target in RuntimeState
            if source != target and not is_valid_transition(source, target)
        ]
        self.assertEqual(invalid, [(LISTENING, SPEAKING)])

    def test_self_transition_is_not_a_transition(self):
        for state in RuntimeState:
            self.assertFalse(is_valid_transition(state, state))

    def test_every_state_can_return_to_idle(self):
        for state in RuntimeState:
            if state != IDLE:
                self.assertIn(IDLE, ALLOWED_TRANSITIONS[state])

    def test_priority_speaking_over_thinking_over_listening(self):
        self.assertEqual(resolve_state({}), IDLE)
        self.assertEqual(resolve_state({LISTENING: 1}), LISTENING)
        self.assertEqual(resolve_state({LISTENING: 2, THINKING: 1}), THINKING)
        self.assertEqual(resolve_state({LISTENING: 1, THINKING: 1, SPEAKING: 1}), SPEAKING)
        self.assertEqual(resolve_state({THINKING: 0, SPEAKING: 0}), IDLE)


# ============================================================
# INTEGRASI EVENT BUS
# ============================================================

class TestEventBusIntegration(unittest.TestCase):

    def test_subscribes_each_event_once_and_never_wildcard(self):
        bus = EventBus()
        engine = RuntimeStateEngine(bus)

        engine.start()
        engine.start()   # idempotent

        for name in SUBSCRIBED_EVENTS:
            self.assertEqual(bus.subscriber_count(name), 1, name)

        self.assertEqual(bus.subscriber_count("*"), 0)

    def test_stop_unsubscribes_and_stops_reacting(self):
        bus, engine, _, events = make()

        engine.stop()

        self.assertFalse(engine.is_started)
        for name in SUBSCRIBED_EVENTS:
            self.assertEqual(bus.subscriber_count(name), 0, name)

        think_start(bus)
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(events, [])

    def test_thinking_start_then_finish(self):
        bus, engine, _, events = make()

        think_start(bus)
        self.assertEqual(engine.state, THINKING)

        think_finish(bus)
        self.assertEqual(engine.state, IDLE)

        self.assertEqual(states(events), ["THINKING", "IDLE"])
        assert_invariant(self, engine)

    def test_real_brain_and_planner_sequence(self):
        """Urutan event NYATA satu giliran (Brain + Planner), satu correlation_id."""
        bus, engine, _, events = make()
        turn = "turn-1"

        def pub(event_name, **data):
            bus.publish(event_name, correlation_id=turn, data=data)

        pub(EventNames.CHAT_RECEIVED, chars=12)
        pub(EventNames.THINKING_START, message="Mengklasifikasi permintaan...")
        pub(EventNames.TASK_CLASSIFIED, label="networking")
        pub(EventNames.TASK_STARTED, label="networking")
        pub(EventNames.THINKING_START, message="Menganalisis permintaan...")     # Planner
        pub(EventNames.THINKING_START, message="Menggunakan 1 tool...")
        pub(EventNames.TOOL_START, name="ping")
        pub(EventNames.TOOL_PROGRESS, name="ping")
        pub(EventNames.TOOL_FINISH, name="ping", success=True)
        pub(EventNames.THINKING_START, message="Menyusun jawaban...")
        self.assertEqual(engine.state, THINKING)

        pub(EventNames.THINKING_FINISH)                                          # Brain finally
        pub(EventNames.TASK_FINISHED, label="networking", error=False, cancelled=False)
        pub(EventNames.RESPONSE_READY, answer_chars=40, error=False)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["THINKING", "IDLE"])      # tepat dua perubahan
        self.assertEqual(engine.stats()["repeated"], 3)             # 3 thinking.start berulang
        assert_invariant(self, engine)

    def test_unrelated_events_do_not_change_state(self):
        bus, engine, _, events = make()

        for name in (
            EventNames.CHAT_RECEIVED, EventNames.TASK_STARTED, EventNames.TASK_FINISHED,
            EventNames.TOOL_START, EventNames.TOOL_FINISH, EventNames.SYSTEM_ERROR,
            EventNames.RESPONSE_READY, EventNames.MEMORY_SAVED, "sesuatu.yang.asing",
        ):
            bus.publish(name)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(events, [])
        self.assertEqual(engine.stats()["transitions"], 0)

    def test_state_changed_event_contract(self):
        bus, engine, _, events = make()

        think_start(bus)
        think_finish(bus)

        first, second = events

        self.assertEqual(first.event, RuntimeEvents.STATE_CHANGED)
        self.assertEqual(first.event, "runtime.state_changed")
        self.assertEqual(first.source, "RUNTIME")
        self.assertEqual(first.agent, "RUNTIME")

        self.assertEqual(first.data["state"], "THINKING")
        self.assertEqual(first.data["previous"], "IDLE")
        self.assertEqual(first.data["seq"], 1)
        self.assertEqual(first.data["reason"], EventNames.THINKING_START)
        self.assertEqual(first.data["active"]["thinking"], 1)

        self.assertEqual(second.data["state"], "IDLE")
        self.assertEqual(second.data["previous"], "THINKING")
        self.assertEqual(second.data["seq"], 2)
        self.assertEqual(second.data["reason"], EventNames.THINKING_FINISH)

        json.dumps(first.to_json_dict())   # aman untuk WebSocket/log DB

    def test_state_changed_inherits_event_scope_metadata(self):
        bus, _, _, events = make()

        with event_scope(session_id="s1", run_id="r1", correlation_id="c1"):
            bus.publish(EventNames.THINKING_START)

        self.assertEqual(events[0].metadata["session_id"], "s1")
        self.assertEqual(events[0].metadata["run_id"], "r1")
        self.assertEqual(events[0].correlation_id, "c1")

    def test_publish_events_can_be_disabled(self):
        bus, engine, _, events = make(publish_events=False)

        think_start(bus)

        self.assertEqual(engine.state, THINKING)
        self.assertEqual(events, [])

    def test_subscriber_error_on_state_changed_does_not_break_engine(self):
        bus, engine, _, _ = make()

        def rusak(event):
            raise RuntimeError("subscriber rusak")

        bus.subscribe(RuntimeEvents.STATE_CHANGED, rusak)

        think_start(bus)
        think_finish(bus)

        self.assertEqual(engine.state, IDLE)
        assert_invariant(self, engine)


# ============================================================
# SUARA: LISTENING / SPEAKING
# ============================================================

class TestVoiceLifecycle(unittest.TestCase):

    def test_listening_start_and_stop(self):
        bus, engine, _, events = make()

        listen_start(bus)
        self.assertEqual(engine.state, LISTENING)

        listen_stop(bus)
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["LISTENING", "IDLE"])

    def test_full_voice_turn_listening_thinking_idle(self):
        bus, engine, _, events = make()

        listen_start(bus)
        think_start(bus)       # transkrip terkirim saat mic masih dianggap aktif
        listen_stop(bus)       # tidak mengubah state (THINKING lebih tinggi)
        self.assertEqual(engine.state, THINKING)

        think_finish(bus)
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["LISTENING", "THINKING", "IDLE"])
        assert_invariant(self, engine)

    def test_speech_start_and_finish_from_idle(self):
        bus, engine, _, events = make()

        speech_start(bus)
        self.assertEqual(engine.state, SPEAKING)

        speech_finish(bus)
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["SPEAKING", "IDLE"])

    def test_response_ready_with_speak_hint_in_scope_becomes_speaking(self):
        bus, engine, _, events = make()

        think_start(bus, "t1")
        think_finish(bus, "t1")                 # urutan nyata: finish SEBELUM response.ready
        with event_scope(speak=True):
            bus.publish(EventNames.RESPONSE_READY, correlation_id="t1", data={"error": False})

        self.assertEqual(engine.state, SPEAKING)

        speech_finish(bus, owner="default")
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["THINKING", "IDLE", "SPEAKING", "IDLE"])

    def test_response_ready_with_speak_hint_in_data(self):
        bus, engine, _, _ = make()

        bus.publish(EventNames.RESPONSE_READY, data={"speak": True})

        self.assertEqual(engine.state, SPEAKING)

    def test_speak_hint_uses_session_as_owner(self):
        bus, engine, _, _ = make()

        with event_scope(session_id="sess-9", speak=True):
            bus.publish(EventNames.RESPONSE_READY)

        self.assertEqual(engine.state, SPEAKING)

        speech_finish(bus, owner="sess-9")
        self.assertEqual(engine.state, IDLE)

    def test_response_ready_without_hint_never_speaks(self):
        bus, engine, _, events = make()

        bus.publish(EventNames.RESPONSE_READY, data={"answer_chars": 10})
        bus.publish(EventNames.RESPONSE_READY, data={"speak": False})

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(events, [])

    def test_speak_hint_is_ignored_for_error_response(self):
        bus, engine, _, _ = make()

        with event_scope(speak=True):
            bus.publish(EventNames.RESPONSE_READY, data={"error": True})

        self.assertEqual(engine.state, IDLE)

    def test_barge_in_speaking_to_listening(self):
        bus, engine, _, events = make()

        speech_start(bus, "s1")
        listen_start(bus, "s1")            # pengguna mulai bicara di atas AIRA
        self.assertEqual(engine.state, SPEAKING)   # SPEAKING masih prioritas

        speech_finish(bus, "s1")           # lapisan suara memotong ucapan AIRA
        self.assertEqual(engine.state, LISTENING)
        self.assertEqual(states(events), ["SPEAKING", "LISTENING"])

    def test_thinking_during_speech_resumes_thinking_after_speech(self):
        bus, engine, _, events = make()

        speech_start(bus)
        think_start(bus, "t2")
        self.assertEqual(engine.state, SPEAKING)

        speech_finish(bus)
        self.assertEqual(engine.state, THINKING)

        think_finish(bus, "t2")
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["SPEAKING", "THINKING", "IDLE"])

    def test_owner_falls_back_to_session_id_then_default(self):
        bus, engine, _, _ = make()

        bus.publish(RuntimeEvents.VOICE_LISTENING_START, metadata={"session_id": "sA"})
        bus.publish(RuntimeEvents.VOICE_LISTENING_STOP, metadata={"session_id": "sA"})
        self.assertEqual(engine.state, IDLE)

        bus.publish(RuntimeEvents.VOICE_LISTENING_START)
        bus.publish(RuntimeEvents.VOICE_LISTENING_STOP)
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(engine.stats()["ignored"], 0)   # start & stop berpasangan


# ============================================================
# TRANSISI TIDAK SAH / EVENT TIDAK NORMAL
# ============================================================

class TestInvalidTransitions(unittest.TestCase):

    def test_speech_start_while_listening_is_rejected(self):
        bus, engine, _, events = make()

        listen_start(bus)
        speech_start(bus, "x")

        self.assertEqual(engine.state, LISTENING)
        self.assertEqual(engine.snapshot().active["speaking"], 0)   # tidak dicatat
        self.assertEqual(engine.stats()["rejected"], 1)
        self.assertEqual(states(events), ["LISTENING"])

        speech_finish(bus, "x")            # penutup untuk speech yang ditolak: diabaikan
        self.assertEqual(engine.state, LISTENING)
        self.assertEqual(engine.stats()["ignored"], 1)

        listen_stop(bus)
        self.assertEqual(engine.state, IDLE)
        assert_invariant(self, engine)

    def test_speech_is_accepted_after_listening_closed(self):
        bus, engine, _, _ = make()

        listen_start(bus)
        speech_start(bus, "x")             # ditolak
        listen_stop(bus)
        speech_start(bus, "x")             # sekarang sah (IDLE -> SPEAKING)

        self.assertEqual(engine.state, SPEAKING)

    def test_finish_without_start_is_ignored(self):
        bus, engine, _, events = make()

        think_finish(bus, "tidak-pernah-mulai")
        speech_finish(bus)
        listen_stop(bus)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(events, [])
        self.assertEqual(engine.stats()["ignored"], 3)

    def test_duplicate_finish_is_ignored(self):
        bus, engine, _, events = make()

        think_start(bus)
        think_finish(bus)
        think_finish(bus)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["THINKING", "IDLE"])
        self.assertEqual(engine.stats()["ignored"], 1)

    def test_handle_event_never_raises_on_garbage(self):
        _, engine, _, _ = make()

        for garbage in (None, object(), "thinking.start", 42):
            engine.handle_event(garbage)   # tidak boleh raise

        self.assertEqual(engine.state, IDLE)

    def test_owner_from_data_overrides_correlation(self):
        bus, engine, _, _ = make()

        bus.publish(EventNames.THINKING_START, correlation_id="a", data={"owner": "job-1"})
        bus.publish(EventNames.THINKING_FINISH, correlation_id="b", data={"owner": "job-1"})

        self.assertEqual(engine.state, IDLE)


# ============================================================
# CONCURRENCY / UPDATE BERULANG
# ============================================================

class TestConcurrencyAndRepetition(unittest.TestCase):

    def test_overlapping_turns_keep_thinking_until_last_finishes(self):
        bus, engine, _, events = make()

        think_start(bus, "A")
        think_start(bus, "B")
        self.assertEqual(engine.snapshot().active["thinking"], 2)

        think_finish(bus, "A")
        self.assertEqual(engine.state, THINKING)     # B masih jalan

        think_finish(bus, "B")
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(states(events), ["THINKING", "IDLE"])   # tidak ada IDLE palsu

    def test_two_sessions_listening_independently(self):
        bus, engine, _, _ = make()

        listen_start(bus, "s1")
        listen_start(bus, "s2")
        listen_stop(bus, "s1")
        self.assertEqual(engine.state, LISTENING)

        listen_stop(bus, "s2")
        self.assertEqual(engine.state, IDLE)

    def test_repeated_identical_begin_is_idempotent(self):
        bus, engine, _, events = make()

        for _ in range(500):
            think_start(bus)

        self.assertEqual(engine.state, THINKING)
        self.assertEqual(engine.snapshot().active["thinking"], 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(engine.stats()["repeated"], 499)

        think_finish(bus)
        self.assertEqual(engine.state, IDLE)

    def test_repeated_unknown_finish_never_changes_state(self):
        bus, engine, _, events = make()

        for _ in range(200):
            speech_finish(bus)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(events, [])
        self.assertEqual(engine.stats()["ignored"], 200)

    def test_parallel_threads_stay_consistent_and_ordered(self):
        bus, engine, _, events = make()
        errors = []

        def worker(index):
            try:
                for n in range(60):
                    turn = f"t{index}-{n}"
                    think_start(bus, turn)
                    think_start(bus, turn)     # fase Planner berulang
                    think_finish(bus, turn)
            except Exception as exc:           # pragma: no cover - hanya kalau ada bug
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(engine.snapshot().active["thinking"], 0)
        assert_invariant(self, engine)

        # Event dipublish di dalam lock -> urutannya identik dengan urutan perubahan.
        previous = "IDLE"

        for index, event in enumerate(events, start=1):
            self.assertEqual(event.data["seq"], index)
            self.assertEqual(event.data["previous"], previous)
            self.assertNotEqual(event.data["state"], previous)
            previous = event.data["state"]

        self.assertEqual(previous, "IDLE")
        self.assertEqual(engine.stats()["transitions"], len(events))

    def test_parallel_mixed_activities_end_idle(self):
        bus, engine, _, _ = make()
        errors = []

        def thinker(index):
            try:
                for n in range(40):
                    think_start(bus, f"t{index}-{n}")
                    think_finish(bus, f"t{index}-{n}")
            except Exception as exc:           # pragma: no cover
                errors.append(exc)

        def speaker(index):
            try:
                for _ in range(40):
                    listen_start(bus, f"l{index}")
                    listen_stop(bus, f"l{index}")
                    speech_start(bus, f"p{index}")
                    speech_finish(bus, f"p{index}")
            except Exception as exc:           # pragma: no cover
                errors.append(exc)

        threads = (
            [threading.Thread(target=thinker, args=(i,)) for i in range(4)]
            + [threading.Thread(target=speaker, args=(i,)) for i in range(4)]
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(engine.state, IDLE)
        self.assertEqual(engine.snapshot().active, {"speaking": 0, "thinking": 0, "listening": 0})
        assert_invariant(self, engine)


# ============================================================
# KEDALUWARSA
# ============================================================

class TestStaleExpiry(unittest.TestCase):

    def test_unclosed_thinking_expires_back_to_idle(self):
        bus, engine, clock, events = make(stale_after={THINKING: 100})

        think_start(bus)
        clock.advance(101)

        snapshot = engine.snapshot()

        self.assertEqual(snapshot.state, IDLE)
        self.assertEqual(snapshot.reason, "stale_expired")
        self.assertEqual(engine.stats()["expired"], 1)
        self.assertEqual(states(events), ["THINKING", "IDLE"])

    def test_not_expired_before_limit(self):
        bus, engine, clock, _ = make(stale_after={THINKING: 100})

        think_start(bus)
        clock.advance(99)

        self.assertEqual(engine.state, THINKING)

    def test_repeated_begin_refreshes_the_lease(self):
        bus, engine, clock, _ = make(stale_after={THINKING: 100})

        think_start(bus)
        clock.advance(60)
        think_start(bus)            # fase Planner berikutnya
        clock.advance(60)
        self.assertEqual(engine.state, THINKING)    # 120s sejak awal, tapi 60s sejak refresh

        clock.advance(50)
        self.assertEqual(engine.state, IDLE)

    def test_expiry_only_drops_the_stale_activity(self):
        bus, engine, clock, events = make(stale_after={SPEAKING: 10, THINKING: 1000})

        think_start(bus)
        speech_start(bus)
        self.assertEqual(engine.state, SPEAKING)

        clock.advance(20)

        self.assertEqual(engine.state, THINKING)
        self.assertEqual(states(events), ["THINKING", "SPEAKING", "THINKING"])
        assert_invariant(self, engine)

    def test_expiry_is_also_applied_when_a_new_event_arrives(self):
        bus, engine, clock, _ = make(stale_after={LISTENING: 10})

        listen_start(bus, "lama")
        clock.advance(30)
        think_start(bus, "baru")             # handle_event menyapu dulu

        self.assertEqual(engine.state, THINKING)
        self.assertEqual(engine.snapshot().active["listening"], 0)
        self.assertEqual(engine.stats()["expired"], 1)

    def test_late_finish_after_expiry_is_ignored(self):
        bus, engine, clock, _ = make(stale_after={THINKING: 10})

        think_start(bus)
        clock.advance(20)
        engine.snapshot()
        think_finish(bus)

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(engine.stats()["ignored"], 1)


# ============================================================
# RESET
# ============================================================

class TestReset(unittest.TestCase):

    def test_reset_clears_everything_and_publishes_once(self):
        bus, engine, _, events = make()

        think_start(bus, "A")
        listen_start(bus, "s1")
        events.clear()

        engine.reset()

        self.assertEqual(engine.state, IDLE)
        self.assertEqual(engine.snapshot().active, {"speaking": 0, "thinking": 0, "listening": 0})
        self.assertEqual(states(events), ["IDLE"])
        self.assertEqual(events[0].data["reason"], "reset")

    def test_reset_when_idle_is_silent(self):
        _, engine, _, events = make()

        engine.reset()

        self.assertEqual(events, [])


# ============================================================
# SINGLETON
# ============================================================

class TestSingleton(unittest.TestCase):

    def tearDown(self):
        current = engine_module._engine_singleton

        if current is not None:
            current.stop()

        engine_module._engine_singleton = None

    def test_get_runtime_state_is_a_started_singleton(self):
        first = get_runtime_state()
        second = get_runtime_state()

        self.assertIs(first, second)
        self.assertTrue(first.is_started)

    def test_snapshot_helper_is_json_safe(self):
        payload = runtime_state_snapshot()

        json.dumps(payload)
        self.assertIn(payload["state"], {s.value for s in RuntimeState})


# ============================================================
# CONTEXT BUILDER
# ============================================================

def make_builder(engine=None, runtime_text="TIME_MARKER", state_provider=None):
    provider = state_provider

    if provider is None and engine is not None:
        provider = lambda: engine.snapshot().to_dict()   # noqa: E731

    return ContextBuilder(
        persona_state=lambda: None,
        prompt_composer=lambda extra: "\n\n".join(p for p in ("PERSONA_BASE", extra) if p),
        memory_text=lambda: None,
        runtime_text=lambda: runtime_text,
        location_text=lambda session_id: None,
        runtime_state=provider,
    )


class TestContextBuilderIntegration(unittest.TestCase):

    def test_state_is_exposed_as_data_on_runtime_state_section(self):
        bus, engine, _, _ = make()
        think_start(bus)

        context = make_builder(engine).build("halo", session_id="s1")

        data = context.runtime_state.data["engine"]
        self.assertEqual(data["state"], "THINKING")
        self.assertEqual(data["active"]["thinking"], 1)
        self.assertEqual(data["seq"], 1)

    def test_state_never_reaches_the_system_prompt(self):
        bus, engine, _, _ = make()
        think_start(bus)

        with_state = make_builder(engine).build("halo")
        without_state = make_builder(None).build("halo")

        self.assertEqual(with_state.system_prompt, without_state.system_prompt)
        for leaked in ("THINKING", "engine", "runtime.state", "seq"):
            self.assertNotIn(leaked, with_state.system_prompt)

    def test_time_text_is_preserved_and_data_is_merged(self):
        bus, engine, _, _ = make()

        context = make_builder(engine).build("halo")

        self.assertEqual(context.runtime_state.text, "TIME_MARKER")
        self.assertTrue(context.runtime_state.is_injectable)
        self.assertEqual(context.runtime_state.data["engine"]["state"], "IDLE")
        self.assertIn("TIME_MARKER", context.system_prompt)

    def test_data_only_section_is_created_when_time_text_is_blank(self):
        _, engine, _, _ = make()

        context = make_builder(engine, runtime_text="").build("halo")

        self.assertIsNotNone(context.runtime_state)
        self.assertEqual(context.runtime_state.text, "")
        self.assertFalse(context.runtime_state.is_injectable)
        self.assertEqual(context.extra_context(), "")
        self.assertIn("runtime_state", context.present())

    def test_without_provider_behavior_is_unchanged(self):
        blank = make_builder(None, runtime_text="").build("halo")
        text = make_builder(None).build("halo")

        self.assertIsNone(blank.runtime_state)
        self.assertEqual(text.runtime_state.data, {})

    def test_failing_provider_is_isolated_and_reported(self):
        def rusak():
            raise RuntimeError("engine mati")

        context = make_builder(state_provider=rusak).build("halo")

        self.assertEqual(context.warnings, ["runtime_state: unavailable (RuntimeError)"])
        self.assertEqual(context.runtime_state.text, "TIME_MARKER")   # sumber lain aman
        self.assertNotIn("engine mati", json.dumps(context.to_dict()["warnings"]))

    def test_empty_or_malformed_snapshot_is_ignored(self):
        for value in (None, {}, "bukan-dict", []):
            context = make_builder(state_provider=lambda v=value: v).build("halo")
            self.assertEqual(context.runtime_state.data, {}, value)

    def test_context_stays_json_serializable(self):
        _, engine, _, _ = make()

        context = make_builder(engine).build("halo", session_id="s1")

        restored = json.loads(json.dumps(context.to_dict()))
        self.assertEqual(restored["runtime_state"]["data"]["engine"]["state"], "IDLE")

    def test_default_singleton_builder_wires_the_runtime_provider(self):
        with mock.patch.object(builder_module, "_builder_singleton", None):
            singleton = builder_module.get_context_builder()

            self.assertIs(singleton._runtime_state, builder_module._default_runtime_state)


# ============================================================
# BRAIN ASLI (classifier, router, orchestrator dipalsukan)
# ============================================================

class FakeClassifier:

    def __init__(self, on_classify=None):
        self.on_classify = on_classify

    def classify(self, prompt):
        from core.model_types import TaskClassification

        if self.on_classify:
            self.on_classify()

        return TaskClassification(primary_label="networking", confidence=0.9)


class FakeRouter:

    def select(self, classification):
        return None


def make_orchestrator(result=None, error=None, sink=None):
    """Kelas Orchestrator palsu; sink (list) merekam panggilan route()."""

    class FakeOrchestrator:

        def route(self, user_input, memory, cancel_event=None, selected_model=None, context=None):
            if sink is not None:
                sink.append({"user_input": user_input, "context": context})

            if error is not None:
                raise error

            return result or {
                "answer": "ok", "steps": [], "token_usage": None,
                "session_token_usage": None, "error": False, "duration": 0.0,
                "interaction_schema": None,
            }

    return FakeOrchestrator


class TestBrainIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            import core.brain as brain_module
        except ImportError as exc:   # dependency runtime belum terpasang
            raise unittest.SkipTest(f"core.brain tidak bisa diimpor: {exc}")
        cls.brain_module = brain_module

    def setUp(self):
        self.bus, self.engine, _, self.events = make()

    def patched(self, orchestrator, classifier=None):
        return mock.patch.multiple(
            "core.brain",
            Orchestrator=orchestrator,
            get_task_classifier=lambda: classifier or FakeClassifier(),
            get_model_router=lambda: FakeRouter(),
            event_bus=self.bus,
            get_runtime_state=lambda: self.engine,
        )

    def brain(self):
        memory = types.SimpleNamespace(session_id="sess-1", history=[])
        builder = ContextBuilder(
            persona_state=lambda: None,
            prompt_composer=lambda extra: extra,
            memory_text=lambda: None,
            runtime_text=lambda: None,
            location_text=lambda session_id: None,
            runtime_state=lambda: self.engine.snapshot().to_dict(),
        )
        return self.brain_module.Brain(memory, context_builder=builder)

    def test_normal_turn_goes_thinking_then_idle(self):
        calls = []

        with self.patched(make_orchestrator(sink=calls)):
            response = self.brain().think("cek R1")

        self.assertEqual(response.answer, "ok")
        self.assertEqual(states(self.events), ["THINKING", "IDLE"])
        self.assertEqual(self.engine.state, IDLE)
        assert_invariant(self, self.engine)

        # konteks yang dibawa ke Planner dibangun SAAT state = THINKING
        self.assertEqual(calls[0]["context"].runtime_state.data["engine"]["state"], "THINKING")

    def test_error_result_still_returns_to_idle(self):
        result = {"answer": "gagal", "error": True, "steps": []}

        with self.patched(make_orchestrator(result=result)):
            response = self.brain().think("halo")

        self.assertTrue(response.error)
        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(states(self.events), ["THINKING", "IDLE"])

    def test_orchestrator_exception_still_returns_to_idle(self):
        with self.patched(make_orchestrator(error=RuntimeError("planner meledak"))):
            with self.assertRaises(RuntimeError):
                self.brain().think("halo")

        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(states(self.events), ["THINKING", "IDLE"])

    def test_planner_reported_cancel_returns_to_idle(self):
        result = {"answer": "", "cancelled": True, "steps": []}

        with self.patched(make_orchestrator(result=result)):
            response = self.brain().think("halo", cancel_event=threading.Event())

        self.assertTrue(response.cancelled)
        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(states(self.events), ["THINKING", "IDLE"])

    def test_cancel_after_classification_does_not_leave_thinking(self):
        """Regresi: thinking.start sudah terbit tapi try/finally Brain belum tercapai."""
        cancel = threading.Event()
        calls = []

        with self.patched(make_orchestrator(sink=calls), FakeClassifier(on_classify=cancel.set)):
            response = self.brain().think("halo", cancel_event=cancel)

        self.assertTrue(response.cancelled)
        self.assertEqual(calls, [])                       # orchestrator tidak pernah dipanggil
        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(states(self.events), ["THINKING", "IDLE"])
        assert_invariant(self, self.engine)

    def test_cancel_before_anything_never_touches_state(self):
        cancel = threading.Event()
        cancel.set()

        with self.patched(make_orchestrator()):
            response = self.brain().think("halo", cancel_event=cancel)

        self.assertTrue(response.cancelled)
        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(self.engine.stats()["transitions"], 0)

    def test_speak_hint_gives_thinking_idle_speaking_then_idle(self):
        with self.patched(make_orchestrator()):
            with event_scope(speak=True):
                self.brain().think("halo")

        self.assertEqual(self.engine.state, SPEAKING)

        speech_finish(self.bus, owner="default")

        self.assertEqual(self.engine.state, IDLE)
        self.assertEqual(states(self.events), ["THINKING", "IDLE", "SPEAKING", "IDLE"])

    def test_text_turn_without_hint_never_speaks(self):
        with self.patched(make_orchestrator()):
            self.brain().think("halo")

        self.assertNotIn("SPEAKING", states(self.events))

    def test_brain_ensures_engine_and_default_builder_gets_provider(self):
        ensure = mock.Mock(return_value=self.engine)
        memory = types.SimpleNamespace(session_id=None, history=[])

        with mock.patch.multiple(
            "core.brain",
            Orchestrator=make_orchestrator(),
            get_task_classifier=lambda: FakeClassifier(),
            get_model_router=lambda: FakeRouter(),
            get_runtime_state=ensure,
        ):
            brain = self.brain_module.Brain(memory)

        ensure.assert_called()
        self.assertIs(brain.context_builder._runtime_state, self.brain_module._runtime_snapshot)

    def test_broken_engine_does_not_break_brain_construction(self):
        memory = types.SimpleNamespace(session_id=None, history=[])

        with mock.patch.multiple(
            "core.brain",
            Orchestrator=make_orchestrator(),
            get_task_classifier=lambda: FakeClassifier(),
            get_model_router=lambda: FakeRouter(),
            get_runtime_state=mock.Mock(side_effect=RuntimeError("engine rusak")),
        ):
            brain = self.brain_module.Brain(memory)   # tidak boleh raise

        self.assertIsNotNone(brain)


if __name__ == "__main__":
    unittest.main()
