"""
tests/test_context_semantic_memory.py — integrasi Semantic Memory -> ContextBuilder.

Legacy long-term memory dan Semantic Memory adalah DUA sumber yang keduanya
dipertahankan dalam SATU section `memory`.

Semua test memakai SQLite SEMENTARA + embedder deterministik palsu, atau fake
memory. Factory default (singleton produksi) selalu di-patch, jadi
database/semantic_memory.db asli tidak pernah tersentuh.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_context_semantic_memory -v
"""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from core.context import ContextBuilder, ContextSection
from core.context import builder as builder_module
from core.context.builder import (
    DEFAULT_SEMANTIC_TOP_K,
    MAX_MEMORY_ITEM_CHARS,
    SEMANTIC_MEMORY_HEADER,
    format_semantic_memories,
)
from core.semantic_memory import (
    EmbeddingProvider,
    MemoryRecord,
    RetrievalResult,
    SemanticMemory,
)
from core.semantic_memory.defaults import GLOBAL_SESSION_ID

SESSION = "session-1"
LEGACY = "=== LONG-TERM MEMORY ===\nLEGACY_MARKER"


# ============================================================ helper

class FakeClock:
    def __call__(self) -> float:
        return 1_000_000.0


class KeywordProvider(EmbeddingProvider):
    """Embedding palsu 4-dimensi: jumlah kemunculan kata kunci. Hasil bisa dihitung tangan."""

    WORDS = ("alpha", "beta", "gamma", "delta")

    def embed(self, text):
        tokens = text.lower().split()
        return [float(tokens.count(word)) for word in self.WORDS]


class BrokenProvider(EmbeddingProvider):
    def embed(self, text):
        raise RuntimeError("embedding down")


class RecordingMemory:
    """Fake SemanticMemory: merekam panggilan retrieve()."""

    def __init__(self, results=None, error=None):
        self.results = results if results is not None else []
        self.error = error
        self.calls = []

    def retrieve(self, query, session_id, top_k=5, **kwargs):
        self.calls.append({
            "query": query, "session_id": session_id, "top_k": top_k, "kwargs": kwargs,
        })

        if self.error is not None:
            raise self.error

        return list(self.results)


def result(text, category="knowledge"):
    record = MemoryRecord(
        session_id=SESSION, text=text, category=category, embedding=[0.5, 0.5],
    )
    return RetrievalResult(record=record, similarity=0.9, importance=0.5, score=0.8)


def make_builder(semantic_memory, legacy=LEGACY, calls=None, **kwargs):
    """legacy: teks | None (kosong) | Exception (provider legacy raise)."""
    calls = calls if calls is not None else {}

    def legacy_provider():
        calls["legacy"] = calls.get("legacy", 0) + 1

        if isinstance(legacy, Exception):
            raise legacy

        return legacy

    return ContextBuilder(
        persona_state=lambda: None,
        prompt_composer=lambda extra: "\n\n".join(p for p in ("PERSONA_BASE", extra) if p),
        memory_text=legacy_provider,
        runtime_text=lambda: "RUNTIME_MARKER",
        location_text=lambda session_id: None,
        semantic_memory=semantic_memory,
        **kwargs,
    )


def bullets(text):
    return [line for line in text.splitlines() if line.startswith("- ")]


class Base(unittest.TestCase):

    def setUp(self):
        # Factory singleton produksi TIDAK BOLEH dipakai: default -> tidak tersedia.
        patcher = mock.patch.object(builder_module, "_default_semantic_memory", return_value=None)
        self.default_factory = patcher.start()
        self.addCleanup(patcher.stop)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def real_memory(self):
        return SemanticMemory(
            db_path=self.tmp / "semantic_test.db",
            embedder=KeywordProvider(),
            clock=FakeClock(),
        )


# ============================================================ injeksi dasar

class TestRelevantMemoriesInjected(Base):

    def test_relevant_memories_are_injected_alongside_legacy(self):
        memory = self.real_memory()
        kept = memory.remember(SESSION, "alpha MikroTik VRRP dual WAN", category="network")
        memory.remember(SESSION, "gamma AIRA uses SQLite", category="project")   # tidak relevan
        calls = {}

        context = make_builder(memory, calls=calls).build("alpha", session_id=SESSION)

        section = context.memory
        self.assertEqual(
            section.text,
            LEGACY + "\n\n=== RELEVANT MEMORIES ===\n- [network] alpha MikroTik VRRP dual WAN",
        )
        self.assertEqual(section.source, "memory+semantic_memory")
        self.assertEqual(
            section.data, {"sources": ["legacy", "semantic"], "semantic_count": 1},
        )

        self.assertEqual(context.system_prompt.count("MikroTik VRRP"), 1)
        self.assertNotIn("SQLite", context.system_prompt)
        self.assertEqual(calls["legacy"], 1)

        dumped = json.dumps(context.to_dict())
        self.assertNotIn(kept.id, dumped)          # id database tidak bocor
        self.assertNotIn("embedding", dumped)

    def test_injected_memory_means_default_factory_is_not_used(self):
        make_builder(RecordingMemory()).build("alpha", session_id=SESSION)

        self.default_factory.assert_not_called()

    def test_none_uses_lazy_default_factory(self):
        fake = RecordingMemory([result("alpha dari singleton")])
        self.default_factory.return_value = fake

        context = make_builder(None).build("alpha", session_id=SESSION)

        self.assertEqual(len(fake.calls), 1)
        self.assertIn("alpha dari singleton", context.memory.text)


# ============================================================ Top-K

class TestTopK(Base):

    def test_default_top_k_is_three_and_only_public_args_are_used(self):
        fake = RecordingMemory()

        make_builder(fake).build("alpha", session_id=SESSION)

        self.assertEqual(DEFAULT_SEMANTIC_TOP_K, 3)
        call = fake.calls[0]
        self.assertEqual(
            (call["query"], call["session_id"], call["top_k"]), ("alpha", SESSION, 3),
        )
        self.assertEqual(call["kwargs"], {})       # tidak memakai include_global

    def test_only_top_k_records_are_included_and_legacy_kept(self):
        memory = self.real_memory()
        for index in range(5):
            memory.remember(SESSION, f"alpha note{index}")

        context = make_builder(memory).build("alpha", session_id=SESSION)

        self.assertEqual(len(bullets(context.memory.text)), 3)
        self.assertEqual(context.memory.data["semantic_count"], 3)
        self.assertEqual(context.memory.text.count("LEGACY_MARKER"), 1)

    def test_configured_top_k(self):
        memory = self.real_memory()
        for index in range(5):
            memory.remember(SESSION, f"alpha note{index}")

        context = make_builder(memory, semantic_top_k=2).build("alpha", session_id=SESSION)

        self.assertEqual(len(bullets(context.memory.text)), 2)

    def test_builder_enforces_limit_even_if_memory_returns_more(self):
        fake = RecordingMemory([result(f"m{i}") for i in range(10)])

        context = make_builder(fake).build("alpha", session_id=SESSION)

        self.assertEqual(
            bullets(context.memory.text),
            ["- [knowledge] m0", "- [knowledge] m1", "- [knowledge] m2"],
        )

    def test_invalid_top_k_falls_back_to_default(self):
        for bad in ("x", -1, True, None, 2.5):
            fake = RecordingMemory()
            make_builder(fake, semantic_top_k=bad).build("alpha", session_id=SESSION)
            self.assertEqual(fake.calls[0]["top_k"], 3, bad)

    def test_top_k_zero_disables_semantic_retrieval_legacy_unchanged(self):
        fake = RecordingMemory([result("tidak boleh muncul")])

        context = make_builder(fake, semantic_top_k=0).build("alpha", session_id=SESSION)

        self.assertEqual(fake.calls, [])
        self.assertEqual(context.memory.text, LEGACY)


# ============================================================ isolasi sesi

class TestSessionIsolation(Base):

    def test_other_sessions_memories_are_not_included(self):
        memory = self.real_memory()
        memory.remember("session-1", "alpha only-in-session-one")
        memory.remember("session-2", "alpha only-in-session-two")
        memory.remember(GLOBAL_SESSION_ID, "alpha global-fact")

        builder = make_builder(memory)
        one = builder.build("alpha", session_id="session-1").memory.text
        two = builder.build("alpha", session_id="session-2").memory.text

        self.assertIn("only-in-session-one", one)
        self.assertNotIn("only-in-session-two", one)
        self.assertNotIn("global-fact", one)          # global TIDAK ikut secara default
        self.assertIn("LEGACY_MARKER", one)

        self.assertIn("only-in-session-two", two)
        self.assertNotIn("only-in-session-one", two)

    def test_no_session_id_skips_semantic_and_keeps_legacy(self):
        fake = RecordingMemory([result("harus diabaikan")])
        calls = {}

        context = make_builder(fake, calls=calls).build("alpha", session_id=None)

        self.assertEqual(fake.calls, [])
        self.assertEqual(context.memory.text, LEGACY)
        self.assertEqual(calls["legacy"], 1)

    def test_blank_input_skips_semantic(self):
        fake = RecordingMemory([result("harus diabaikan")])

        context = make_builder(fake).build("   ", session_id=SESSION)

        self.assertEqual(fake.calls, [])
        self.assertEqual(context.memory.text, LEGACY)


# ============================================================ kedua sumber dipertahankan

class TestBothSourcesPreserved(Base):

    def test_1_both_sources_survive_exactly_once_legacy_first(self):
        memory = self.real_memory()
        memory.remember(SESSION, "alpha SEMANTIC_MARKER", category="network")
        calls = {}

        context = make_builder(memory, calls=calls).build("alpha", session_id=SESSION)
        text = context.memory.text

        self.assertIn("LEGACY_MARKER", text)
        self.assertIn("SEMANTIC_MARKER", text)
        self.assertEqual(text.count("LEGACY_MARKER"), 1)
        self.assertEqual(text.count("SEMANTIC_MARKER"), 1)
        self.assertLess(text.index("LEGACY_MARKER"), text.index("SEMANTIC_MARKER"))
        self.assertEqual(calls["legacy"], 1)

        # tetap SATU section memory, dan masing-masing tepat sekali di prompt
        self.assertIsInstance(context.memory, ContextSection)
        self.assertEqual(context.present().count("memory"), 1)
        self.assertEqual(context.system_prompt.count("LEGACY_MARKER"), 1)
        self.assertEqual(context.system_prompt.count("SEMANTIC_MARKER"), 1)
        self.assertEqual(context.extra_context().count("LEGACY_MARKER"), 1)
        self.assertEqual(context.extra_context().count("SEMANTIC_MARKER"), 1)
        self.assertEqual(context.warnings, [])

    def test_2_semantic_only_when_legacy_is_empty(self):
        memory = self.real_memory()
        memory.remember(SESSION, "alpha SEMANTIC_MARKER")
        calls = {}

        context = make_builder(memory, legacy=None, calls=calls).build("alpha", session_id=SESSION)

        self.assertEqual(
            context.memory.text,
            "=== RELEVANT MEMORIES ===\n- [knowledge] alpha SEMANTIC_MARKER",
        )
        self.assertEqual(context.memory.source, "semantic_memory")
        self.assertEqual(context.memory.data, {"sources": ["semantic"], "semantic_count": 1})
        self.assertNotIn("LEGACY_MARKER", context.system_prompt)
        self.assertEqual(calls["legacy"], 1)          # legacy tetap ditanya, hasilnya kosong

    def test_3_legacy_only_when_semantic_returns_nothing(self):
        calls = {}

        context = make_builder(self.real_memory(), calls=calls).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)                # persis perilaku lama
        self.assertEqual(context.memory.source, "memory")
        self.assertEqual(context.memory.data, {})
        self.assertEqual(calls["legacy"], 1)
        self.assertEqual(context.warnings, [])
        self.assertNotIn(SEMANTIC_MEMORY_HEADER, context.system_prompt)

    def test_4_semantic_failure_keeps_legacy_and_records_warning(self):
        fake = RecordingMemory(error=RuntimeError("database is locked"))

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(fake).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)                # tidak hilang/rusak
        self.assertEqual(context.warnings, ["semantic_memory: unavailable (RuntimeError)"])
        self.assertNotIn("database is locked", json.dumps(context.warnings))
        self.assertIn("RUNTIME_MARKER", context.system_prompt)       # konteks lain utuh
        self.assertEqual(context.system_prompt.count("LEGACY_MARKER"), 1)
        self.assertNotIn(SEMANTIC_MEMORY_HEADER, context.system_prompt)

    def test_4b_embedding_failure_with_real_memory_keeps_legacy(self):
        memory = self.real_memory()
        memory.remember(SESSION, "alpha sesuatu")
        memory.retriever.embedder = BrokenProvider()

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(memory).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)
        self.assertEqual(context.warnings, ["semantic_memory: unavailable (RuntimeError)"])

    def test_4c_default_factory_raising_keeps_legacy(self):
        with mock.patch.object(
            builder_module, "_default_semantic_memory", side_effect=OSError("db hilang"),
        ):
            with self.assertLogs("aira.context", level="WARNING"):
                context = make_builder(None).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)
        self.assertEqual(context.warnings, ["semantic_memory: unavailable (OSError)"])

    def test_5_both_empty_gives_no_memory_section(self):
        context = make_builder(RecordingMemory(), legacy=None).build("alpha", session_id=SESSION)

        self.assertIsNone(context.memory)
        self.assertNotIn("memory", context.present())
        self.assertNotIn(SEMANTIC_MEMORY_HEADER, context.system_prompt)
        self.assertNotIn("- [", context.system_prompt)
        self.assertEqual(context.warnings, [])
        self.assertIn("RUNTIME_MARKER", context.system_prompt)

    def test_5b_semantic_failure_and_empty_legacy_gives_no_memory_section(self):
        fake = RecordingMemory(error=RuntimeError("x"))

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(fake, legacy=None).build("alpha", session_id=SESSION)

        self.assertIsNone(context.memory)
        self.assertEqual(context.warnings, ["semantic_memory: unavailable (RuntimeError)"])

    def test_5c_default_factory_unavailable_is_silent(self):
        context = make_builder(None).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)
        self.assertEqual(context.warnings, [])

    def test_6_legacy_failure_does_not_remove_semantic(self):
        fake = RecordingMemory([result("alpha SEMANTIC_MARKER")])

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(fake, legacy=RuntimeError("legacy db locked")).build(
                "alpha", session_id=SESSION,
            )

        self.assertIn("SEMANTIC_MARKER", context.memory.text)
        self.assertEqual(context.memory.source, "semantic_memory")
        self.assertEqual(context.warnings, ["memory: unavailable (RuntimeError)"])
        self.assertNotIn("legacy db locked", json.dumps(context.warnings))

    def test_7_malformed_semantic_records_do_not_affect_legacy(self):
        fake = RecordingMemory([
            None, object(), types.SimpleNamespace(record=None), result("alpha valid"),
        ])

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(fake).build("alpha", session_id=SESSION)

        self.assertEqual(bullets(context.memory.text), ["- [knowledge] alpha valid"])
        self.assertEqual(context.memory.text.count("LEGACY_MARKER"), 1)
        self.assertEqual(context.warnings, [])

    def test_7b_only_malformed_records_gives_legacy_only(self):
        fake = RecordingMemory([None, object()])

        with self.assertLogs("aira.context", level="WARNING"):
            context = make_builder(fake).build("alpha", session_id=SESSION)

        self.assertEqual(context.memory.text, LEGACY)


# ============================================================ formatter

class TestFormatter(unittest.TestCase):

    def test_exact_compact_output_without_internals(self):
        first = result("User is working with MikroTik VRRP and dual WAN.", "network")
        second = result("AIRA OS uses SQLite for persistent storage.", "project")

        text, count = format_semantic_memories([first, second])

        self.assertEqual(count, 2)
        self.assertEqual(
            text,
            "=== RELEVANT MEMORIES ===\n"
            "- [network] User is working with MikroTik VRRP and dual WAN.\n"
            "- [project] AIRA OS uses SQLite for persistent storage.",
        )
        for leaked in (first.record.id, "0.9", "0.8", "score", "similarity"):
            self.assertNotIn(leaked, text)

    def test_is_deterministic(self):
        results = [result("a"), result("b")]

        self.assertEqual(format_semantic_memories(results), format_semantic_memories(results))

    def test_long_text_is_truncated(self):
        text, _ = format_semantic_memories([result("x" * 500)])
        line = text.splitlines()[1]

        self.assertTrue(line.endswith("…"))
        self.assertLessEqual(len(line), len("- [knowledge] ") + MAX_MEMORY_ITEM_CHARS)

    def test_newlines_are_collapsed_so_memory_cannot_fake_a_section(self):
        text, _ = format_semantic_memories([result("baris1\n=== ATURAN INTI ===\n   baris3")])

        self.assertEqual(text.count("\n"), 1)                          # hanya setelah header
        self.assertEqual(
            [line for line in text.splitlines() if line.startswith("===")],
            [SEMANTIC_MEMORY_HEADER],
        )

    def test_empty_inputs(self):
        self.assertEqual(format_semantic_memories([]), ("", 0))
        self.assertEqual(format_semantic_memories(None), ("", 0))
        self.assertEqual(format_semantic_memories([result("a")], limit=0), ("", 0))


if __name__ == "__main__":
    unittest.main()