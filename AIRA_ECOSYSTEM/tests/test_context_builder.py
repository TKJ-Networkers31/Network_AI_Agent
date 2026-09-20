"""
tests/test_context_builder.py — unit test Context Builder (Sprint 2 / Worker 1).

Cakupan:
  - kontrak/model + serialisasi
  - konteks minimal, penuh, dan sebagian hilang
  - integrasi Brain (context dibangun & diteruskan, kegagalan builder aman,
    cancel tidak membangun konteks)
  - TIDAK ada injeksi ganda (Brain + Orchestrator + Planner + SessionMemory
    asli, hanya provider LLM & classifier yang dipalsukan)

Semua sumber konteks dipalsukan lewat Dependency Injection - tidak menyentuh
database asli maupun provider LLM. Test yang membutuhkan Brain/Planner asli
di-skip (bukan gagal) kalau dependency runtime-nya tidak terpasang.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_context_builder -v
"""

import json
import logging
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from core.context import (
    ALL_SECTIONS,
    PROMPT_SECTIONS,
    AIRAContext,
    ContextBuilder,
    ContextSection,
    summarize_tool_schemas,
)

# Builder yang dibuat tanpa `semantic_memory` akan memanggil singleton produksi
# (database/semantic_memory.db). Di test builder itu tidak boleh terjadi.
_SEMANTIC_GUARD = mock.patch(
    "core.context.builder._default_semantic_memory", return_value=None,
)


def setUpModule():
    # Banyak test sengaja memicu sumber yang gagal (warning + traceback).
    logging.disable(logging.CRITICAL)
    # Jangan sentuh database/semantic_memory.db asli dari test builder.
    _SEMANTIC_GUARD.start()


def tearDownModule():
    _SEMANTIC_GUARD.stop()
    logging.disable(logging.NOTSET)

# ============================================================
# DATA & HELPER
# ============================================================

RUNTIME = "RUNTIME_MARKER waktu saat ini"
MEMORY = "=== LONG-TERM MEMORY ===\nMEMORY_MARKER"
LOCATION = "=== KONTEKS LOKASI ===\nLOCATION_MARKER"
MARKERS = ("RUNTIME_MARKER", "MEMORY_MARKER", "LOCATION_MARKER")

PERSONA_STATE = {
    "profile": {
        "assistant_name": "AIRA",
        "user_name": "Tester",
        "language": "id",
        "timezone": "Asia/Jakarta",
        "active_preset": "akane",
        "greeting": "tidak relevan",
        "created_at": 1.0,
    },
    "behavior": {"professionalism": 86, "friendliness": 84},
}

TOOL_SUMMARY = {
    "count": 2,
    "names": ["ping", "get_routes"],
    "categories": {"network": ["ping"], "mikrotik": ["get_routes"]},
}

DEFAULTS = {
    "persona_state": PERSONA_STATE,
    "memory_text": MEMORY,
    "runtime_text": RUNTIME,
    "location_text": LOCATION,
    "tool_summary": TOOL_SUMMARY,
    "prompt_composer": None,  # nilai diabaikan; hanya Exception yang berpengaruh
}


def make_builder(calls=None, **overrides):
    """
    Builder dengan semua sumber dipalsukan. overrides: nama sumber -> nilai
    (None = tidak tersedia, Exception = sumber raise). `calls` menghitung
    berapa kali tiap sumber dipanggil.
    """
    calls = calls if calls is not None else {}
    values = {**DEFAULTS, **overrides}

    def wrap(name):
        value = values[name]

        def provider(*args):
            calls[name] = calls.get(name, 0) + 1

            if isinstance(value, Exception):
                raise value

            return value

        return provider

    def composer(extra_context):
        calls["prompt_composer"] = calls.get("prompt_composer", 0) + 1

        if isinstance(values["prompt_composer"], Exception):
            raise values["prompt_composer"]

        return "\n\n".join(p for p in ("PERSONA_BASE", extra_context) if p)

    return ContextBuilder(
        persona_state=wrap("persona_state"),
        prompt_composer=composer,
        memory_text=wrap("memory_text"),
        runtime_text=wrap("runtime_text"),
        location_text=wrap("location_text"),
        tool_summary=wrap("tool_summary"),
    )


class FakeTask:
    """Mirip TaskClassification: cukup punya to_dict()."""

    def to_dict(self):
        return {
            "primary_label": "networking", "confidence": 0.9,
            "requires_tools": True, "requires_vision": False, "requires_voice": False,
        }


# ============================================================
# KONTRAK / MODEL / SERIALISASI
# ============================================================

class TestContextModels(unittest.TestCase):

    def test_empty_context_defaults(self):
        context = AIRAContext()

        self.assertEqual(context.present(), [])
        self.assertEqual(context.extra_context(), "")
        self.assertEqual(context.warnings, [])
        self.assertIsNone(context.task)

    def test_extra_context_only_uses_prompt_sections_in_canonical_order(self):
        context = AIRAContext(
            # sengaja diisi terbalik & dengan section non-prompt yang punya text
            location=ContextSection("location", text="LOC"),
            memory=ContextSection("memory", text="MEM"),
            runtime_state=ContextSection("runtime_state", text="RUN"),
            tool_context=ContextSection("tool_context", text="TOOL_TEXT_JANGAN_MASUK"),
            identity=ContextSection("identity", text="IDENTITY_TEXT_JANGAN_MASUK"),
            persona=ContextSection("persona", text="PERSONA_TEXT_JANGAN_MASUK"),
        )

        self.assertEqual(PROMPT_SECTIONS, ("runtime_state", "memory", "location"))
        self.assertEqual(context.extra_context(), "RUN\n\nMEM\n\nLOC")
        self.assertNotIn("JANGAN_MASUK", context.extra_context())

    def test_blank_prompt_section_is_not_injected(self):
        context = AIRAContext(memory=ContextSection("memory", text="   \n"))
        self.assertEqual(context.extra_context(), "")

    def test_roundtrip_serialization(self):
        context = make_builder().build("cek R1", session_id="s1", task=FakeTask())

        payload = json.loads(json.dumps(context.to_dict()))  # harus JSON-serializable
        restored = AIRAContext.from_dict(payload)

        self.assertEqual(restored, context)
        self.assertEqual(restored.to_dict(), context.to_dict())
        self.assertEqual(json.loads(context.to_json())["user_input"], "cek R1")

    def test_to_dict_can_exclude_prompt(self):
        context = make_builder().build("halo", session_id="s1")

        self.assertIn("system_prompt", context.to_dict())
        self.assertNotIn("system_prompt", context.to_dict(include_prompt=False))

    def test_non_json_values_are_coerced(self):
        section = ContextSection("x", data={"path": Path("a/b"), "obj": object()})
        context = AIRAContext(identity=section, task={"when": Path("t")})

        json.dumps(context.to_dict())  # tidak boleh raise
        self.assertEqual(context.to_dict()["identity"]["data"]["path"], str(Path("a/b")))

    def test_from_dict_tolerates_garbage(self):
        self.assertEqual(AIRAContext.from_dict({}).present(), [])
        self.assertEqual(AIRAContext.from_dict(None).user_input, "")
        self.assertIsNone(AIRAContext.from_dict({"identity": "bukan-dict"}).identity)

    def test_summary_has_no_section_content(self):
        context = make_builder().build("halo", session_id="s1", task=FakeTask())
        summary = context.summary()

        self.assertEqual(summary["task"], "networking")
        self.assertEqual(summary["sections"], list(ALL_SECTIONS))
        self.assertNotIn("MEMORY_MARKER", json.dumps(summary))


# ============================================================
# BUILDER: MINIMAL / PENUH / SEBAGIAN HILANG
# ============================================================

class TestBuilderMinimal(unittest.TestCase):

    def test_no_sources_available_gives_minimal_context(self):
        builder = make_builder(
            persona_state=None, memory_text=None, runtime_text=None,
            location_text=None, tool_summary=None,
        )

        context = builder.build("halo", session_id="s1")

        self.assertEqual(context.user_input, "halo")
        self.assertEqual(context.session_id, "s1")
        self.assertEqual(context.present(), [])
        self.assertEqual(context.warnings, [])   # "tidak ada" bukan error
        self.assertIsNone(context.task)
        self.assertEqual(context.system_prompt, "PERSONA_BASE")

    def test_empty_user_input_is_safe(self):
        context = make_builder().build(None)
        self.assertEqual(context.user_input, "")


class TestBuilderFull(unittest.TestCase):

    def setUp(self):
        self.context = make_builder().build("cek R1", session_id="s1", task=FakeTask())

    def test_all_sections_present(self):
        self.assertEqual(self.context.present(), list(ALL_SECTIONS))
        self.assertEqual(self.context.warnings, [])

    def test_identity_and_persona_are_data_only(self):
        identity = self.context.identity
        persona = self.context.persona

        self.assertEqual(identity.data, {
            "assistant_name": "AIRA", "user_name": "Tester",
            "language": "id", "timezone": "Asia/Jakarta",
        })
        self.assertEqual(identity.text, "")
        self.assertEqual(persona.data["active_preset"], "akane")
        self.assertEqual(persona.data["behavior"]["professionalism"], 86)
        self.assertEqual(persona.text, "")

    def test_tool_context_is_summary_only(self):
        tool = self.context.tool_context

        self.assertEqual(tool.data["names"], ["ping", "get_routes"])
        self.assertEqual(tool.text, "")
        self.assertNotIn("function", json.dumps(tool.data))   # bukan skema penuh

    def test_task_normalized_from_object_and_dict(self):
        self.assertEqual(self.context.task["primary_label"], "networking")

        from_dict = make_builder().build("x", task={"primary_label": "coding"})
        self.assertEqual(from_dict.task, {"primary_label": "coding"})

    def test_system_prompt_order_and_scope(self):
        prompt = self.context.system_prompt

        self.assertTrue(prompt.startswith("PERSONA_BASE"))
        self.assertLess(prompt.index("RUNTIME_MARKER"), prompt.index("MEMORY_MARKER"))
        self.assertLess(prompt.index("MEMORY_MARKER"), prompt.index("LOCATION_MARKER"))

        # section non-prompt & user_input tidak ikut disisipkan
        for leaked in ("ping", "get_routes", "Tester", "cek R1"):
            self.assertNotIn(leaked, prompt)

    def test_each_source_called_once(self):
        calls = {}
        make_builder(calls).build("halo", session_id="s1")

        self.assertEqual(
            calls,
            {
                "persona_state": 1, "runtime_text": 1, "memory_text": 1,
                "location_text": 1, "tool_summary": 1, "prompt_composer": 1,
            },
        )

    def test_summarize_tool_schemas(self):
        schemas = [
            {"type": "function", "function": {"name": "ping"}},
            {"type": "function", "function": {"name": "get_routes"}},
            {"type": "function", "function": {}},   # tanpa nama -> diabaikan
            "bukan-dict",
        ]
        summary = summarize_tool_schemas(schemas, {"ping": "network"})

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["categories"], {"network": ["ping"], "tool": ["get_routes"]})
        self.assertEqual(summarize_tool_schemas([], {}), {})


class TestMissingOptionalContext(unittest.TestCase):

    def test_failing_source_is_skipped_and_reported(self):
        context = make_builder(memory_text=RuntimeError("database is locked")).build(
            "halo", session_id="s1",
        )

        self.assertIsNone(context.memory)
        self.assertIsNotNone(context.runtime_state)
        self.assertIsNotNone(context.location)
        self.assertEqual(context.warnings, ["memory: unavailable (RuntimeError)"])
        self.assertNotIn("MEMORY_MARKER", context.system_prompt)
        self.assertIn("RUNTIME_MARKER", context.system_prompt)

    def test_error_message_is_not_leaked_into_warnings(self):
        context = make_builder(runtime_text=RuntimeError("secret-token-123")).build("halo")

        self.assertNotIn("secret-token-123", json.dumps(context.to_dict()["warnings"]))

    def test_blank_source_text_is_not_injected(self):
        context = make_builder(runtime_text="  \n ", memory_text="").build("halo", session_id="s1")

        self.assertIsNone(context.runtime_state)
        self.assertIsNone(context.memory)
        self.assertEqual(context.warnings, [])

    def test_location_skipped_without_session(self):
        calls = {}
        context = make_builder(calls).build("halo", session_id=None)

        self.assertIsNone(context.location)
        self.assertNotIn("location_text", calls)   # sumber tidak dipanggil sama sekali
        self.assertNotIn("LOCATION_MARKER", context.system_prompt)

    def test_malformed_persona_state_is_safe(self):
        context = make_builder(persona_state="bukan dict").build("halo")

        self.assertIsNone(context.identity)
        self.assertIsNone(context.persona)

        context = make_builder(persona_state={"profile": None, "behavior": "x"}).build("halo")
        self.assertIsNone(context.identity)
        self.assertIsNone(context.persona)

    def test_persona_source_failure_keeps_runtime_context(self):
        context = make_builder(persona_state=OSError("db")).build("halo", session_id="s1")

        self.assertIsNone(context.identity)
        self.assertEqual(context.warnings, ["persona: unavailable (OSError)"])
        self.assertIn("MEMORY_MARKER", context.system_prompt)

    def test_prompt_composer_failure_degrades_to_runtime_context(self):
        context = make_builder(prompt_composer=ValueError("x")).build("halo", session_id="s1")

        self.assertEqual(context.system_prompt, context.extra_context())
        self.assertIn("RUNTIME_MARKER", context.system_prompt)
        self.assertEqual(context.warnings, ["persona: prompt composer failed (ValueError)"])

    def test_unsupported_task_type_is_ignored(self):
        context = make_builder().build("halo", task=object())

        self.assertIsNone(context.task)
        self.assertEqual(context.warnings, ["task: unsupported type (object)"])

    def test_build_never_raises_even_if_everything_fails(self):
        boom = RuntimeError("x")
        builder = make_builder(
            persona_state=boom, memory_text=boom, runtime_text=boom,
            location_text=boom, tool_summary=boom, prompt_composer=boom,
        )

        context = builder.build("halo", session_id="s1", task=FakeTask())

        self.assertEqual(context.present(), [])
        self.assertEqual(context.user_input, "halo")
        self.assertEqual(context.system_prompt, "")


# ============================================================
# INTEGRASI BRAIN / PLANNER (komponen asli; classifier & LLM dipalsukan)
# ============================================================

class FakeClassifier:
    def classify(self, prompt):
        from core.model_types import TaskClassification
        return TaskClassification(primary_label="networking", confidence=0.9, requires_tools=True)


class FakeRouter:
    def select(self, classification):
        return None   # provider_client / fake call_model memakai default


class FakeOrchestrator:
    """Merekam argumen route(); tidak menjalankan Planner."""

    def __init__(self):
        self.calls = []

    def route(self, user_input, memory, cancel_event=None, selected_model=None, context=None):
        self.calls.append({
            "user_input": user_input, "memory": memory,
            "cancel_event": cancel_event, "selected_model": selected_model,
            "context": context,
        })
        return {
            "answer": "ok", "steps": [], "token_usage": None,
            "session_token_usage": None, "error": False, "duration": 0.0,
            "interaction_schema": None,
        }


class _BrainTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            import core.brain as brain_module
        except ImportError as exc:   # dependency runtime (paramiko, pysnmp, ...) belum terpasang
            raise unittest.SkipTest(f"core.brain tidak bisa diimpor: {exc}")
        cls.brain_module = brain_module

    def patched_brain_deps(self, orchestrator_cls=FakeOrchestrator):
        return mock.patch.multiple(
            "core.brain",
            Orchestrator=orchestrator_cls,
            get_task_classifier=lambda: FakeClassifier(),
            get_model_router=lambda: FakeRouter(),
        )


class TestBrainIntegration(_BrainTestBase):

    def test_context_is_built_and_passed_to_orchestrator(self):
        memory = types.SimpleNamespace(session_id="sess-1", history=[])
        calls = {}

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory, context_builder=make_builder(calls))
            response = brain.think("cek R1")

        self.assertEqual(response.answer, "ok")
        self.assertEqual(len(brain.orchestrator.calls), 1)

        context = brain.orchestrator.calls[0]["context"]

        self.assertIsInstance(context, AIRAContext)
        self.assertEqual(context.user_input, "cek R1")
        self.assertEqual(context.session_id, "sess-1")
        self.assertEqual(context.task["primary_label"], "networking")   # task ikut terbawa
        self.assertEqual(context.present(), list(ALL_SECTIONS))
        self.assertEqual(calls["prompt_composer"], 1)

    def test_builder_failure_does_not_break_turn(self):
        class BrokenBuilder:
            def build(self, *args, **kwargs):
                raise RuntimeError("builder rusak")

        memory = types.SimpleNamespace(session_id="sess-1", history=[])

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory, context_builder=BrokenBuilder())
            response = brain.think("halo")

        self.assertEqual(response.answer, "ok")
        self.assertFalse(response.error)
        self.assertIsNone(brain.orchestrator.calls[0]["context"])   # Planner pakai fallback

    def test_cancelled_turn_never_builds_context(self):
        memory = types.SimpleNamespace(session_id="sess-1", history=[])
        calls = {}
        cancel = threading.Event()
        cancel.set()

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory, context_builder=make_builder(calls))
            response = brain.think("halo", cancel_event=cancel)

        self.assertTrue(response.cancelled)
        self.assertEqual(calls, {})
        self.assertEqual(brain.orchestrator.calls, [])

    def test_cancel_event_and_model_are_forwarded_unchanged(self):
        memory = types.SimpleNamespace(session_id="sess-1", history=[])
        cancel = threading.Event()

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory, context_builder=make_builder())
            brain.think("halo", cancel_event=cancel)

        call = brain.orchestrator.calls[0]
        self.assertIs(call["cancel_event"], cancel)
        self.assertIsNone(call["selected_model"])
        self.assertEqual(call["user_input"], "halo")   # pesan user tidak diubah builder

    def test_terminal_memory_without_session_gets_no_location(self):
        memory = types.SimpleNamespace(history=[])   # seperti ConversationMemory biasa
        calls = {}

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory, context_builder=make_builder(calls))
            brain.think("halo")

        context = brain.orchestrator.calls[0]["context"]
        self.assertIsNone(context.location)
        self.assertNotIn("location_text", calls)

    def test_default_builder_gets_tool_summary_from_orchestrator_registry(self):
        memory = types.SimpleNamespace(session_id=None, history=[])

        with self.patched_brain_deps():
            brain = self.brain_module.Brain(memory)

        self.assertIsInstance(brain.context_builder, ContextBuilder)

        summary = self.brain_module._tool_summary()
        self.assertEqual(summary["count"], len(self.brain_module.AGENT_TOOL_SCHEMAS))


class TestNoDuplicateInjection(_BrainTestBase):
    """
    Brain + Orchestrator + Planner + SessionMemory ASLI. Hanya provider LLM,
    classifier, router, dan ekstraksi memori otomatis yang dipalsukan.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            import agents.rei.planner as planner_module
            import core.orchestrator as orchestrator_module
            from api.state import SessionMemory
        except ImportError as exc:
            raise unittest.SkipTest(f"Planner/SessionMemory tidak bisa diimpor: {exc}")
        cls.planner_module = planner_module
        cls.orchestrator_module = orchestrator_module
        cls.SessionMemory = SessionMemory

    def setUp(self):
        self.sent = []   # setiap panggilan call_model -> daftar messages

        def fake_call_model(messages, tools, selected_model=None, **kwargs):
            self.sent.append([dict(m) for m in messages])
            return {
                "message": {"role": "assistant", "content": "jawaban", "tool_calls": []},
                "usage": None,
            }

        self.patches = [
            mock.patch("agents.rei.planner.call_model", fake_call_model),
            mock.patch("agents.rei.planner.extract_and_save_facts_async", lambda *a, **k: None),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()

    def _count(self, messages, marker):
        return sum(str(m.get("content") or "").count(marker) for m in messages)

    def _assert_each_block_once(self, messages):
        for marker in MARKERS + ("PERSONA_BASE",):
            self.assertEqual(self._count(messages, marker), 1, f"{marker} tidak tepat sekali")

    def test_each_context_block_reaches_the_provider_exactly_once(self):
        memory = self.SessionMemory("sess-e2e")
        calls = {}

        with self.patched_brain_deps(self.orchestrator_module.Orchestrator):
            brain = self.brain_module.Brain(memory, context_builder=make_builder(calls))
            response = brain.think("halo")

        self.assertEqual(response.answer, "jawaban")
        self.assertEqual(len(self.sent), 1)
        self._assert_each_block_once(self.sent[0])
        self.assertEqual(self.sent[0][0]["role"], "system")
        self.assertEqual(calls["runtime_text"], 1)
        self.assertEqual(calls["location_text"], 1)
        self.assertEqual(calls["prompt_composer"], 1)

    def test_no_accumulation_across_turns(self):
        memory = self.SessionMemory("sess-e2e")
        calls = {}

        with self.patched_brain_deps(self.orchestrator_module.Orchestrator):
            brain = self.brain_module.Brain(memory, context_builder=make_builder(calls))
            brain.think("pertama")
            brain.think("kedua")   # jalur yang sama dengan edit / regenerate

        self.assertEqual(len(self.sent), 2)
        self._assert_each_block_once(self.sent[1])
        self.assertEqual(calls["runtime_text"], 2)   # sekali per giliran

        # konteks tidak bocor ke riwayat percakapan
        self.assertEqual(self._count(memory.history, "MARKER"), 0)

    def test_session_memory_no_longer_injects_location(self):
        # Kalau override lokasi lama di SessionMemory kembali, blok ini ikut
        # masuk ke system prompt dan test ini gagal (=> lokasi ganda).
        fake_service = types.SimpleNamespace(
            build_prompt_block=lambda session_id: "\nLOCATION_MARKER\n",
        )

        with mock.patch("core.location.location_service", fake_service):
            content = self.SessionMemory("sess-e2e").get_messages("SYS")[0]["content"]

        self.assertEqual(content, "SYS")

    def test_planner_fallback_builds_context_once_when_none_supplied(self):
        memory = self.SessionMemory("sess-fallback")
        calls = {}
        builder = make_builder(calls)

        with mock.patch("agents.rei.planner.get_context_builder", lambda: builder):
            self.orchestrator_module.Orchestrator().route("halo", memory)

        self.assertEqual(len(self.sent), 1)
        self._assert_each_block_once(self.sent[0])
        self.assertEqual(calls["runtime_text"], 1)

    def test_planner_uses_supplied_context_without_rebuilding(self):
        memory = self.SessionMemory("sess-supplied")
        context = make_builder().build("halo", session_id="sess-supplied")

        def must_not_be_called():
            raise AssertionError("Planner tidak boleh membangun konteks kalau sudah diberi")

        with mock.patch("agents.rei.planner.get_context_builder", must_not_be_called):
            self.orchestrator_module.Orchestrator().route("halo", memory, context=context)

        self.assertEqual(len(self.sent), 1)
        self._assert_each_block_once(self.sent[0])


if __name__ == "__main__":
    unittest.main()