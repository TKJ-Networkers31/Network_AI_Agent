"""
tests/test_semantic_memory.py — unit test Semantic Memory (Sprint 2.4).

Cakupan: model & serialisasi, embedding deterministik, cosine similarity,
importance score, CRUD SQLite, retrieval (ranking, top_k, filter kategori,
isolasi sesi, hasil kosong), fasad SemanticMemory, dan batasan Sprint 2.4
(tanpa network, tanpa dependency ML, tanpa import modul AIRA lain).

Semua test memakai database SEMENTARA (tempfile) - TIDAK PERNAH menyentuh
database/semantic_memory.db asli - dan berjalan tanpa internet.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_semantic_memory -v
"""

import ast
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import core.semantic_memory as sm
import core.semantic_memory.retriever as retriever_module
import core.semantic_memory.store as store_module
from core.semantic_memory import (
    DefaultEmbeddingProvider,
    EmbeddingProvider,
    MemoryCategory,
    MemoryRecord,
    MemoryRetriever,
    MemoryStore,
    RetrievalResult,
    SemanticMemory,
    category_weight,
    combine_score,
    cosine_similarity,
    importance_score,
    recency_score,
)
from core.semantic_memory import defaults

ROOT = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
PACKAGE_DIR = ROOT / "core" / "semantic_memory"
DAY = 86400.0


# ============================================================ helper

class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class KeywordProvider(EmbeddingProvider):
    """Provider palsu dengan 4 dimensi (jumlah kemunculan kata kunci) - hasil bisa dihitung tangan."""

    WORDS = ("alpha", "beta", "gamma", "delta")

    def embed(self, text):
        tokens = text.lower().split()
        return [float(tokens.count(word)) for word in self.WORDS]


class TempCase(unittest.TestCase):
    """Basis: satu folder sementara + database sementara per test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "semantic_memory_test.db"
        self.clock = FakeClock()

    def tearDown(self):
        self._tmp.cleanup()

    def store(self, **kwargs):
        return MemoryStore(self.db, clock=self.clock, **kwargs)

    def memory(self, embedder=None):
        return SemanticMemory(db_path=self.db, embedder=embedder, clock=self.clock)


def rec(**kwargs):
    fields = {"session_id": "s1", "text": "catatan"}
    fields.update(kwargs)
    return MemoryRecord(**fields)


# ============================================================ MODEL

class TestModels(unittest.TestCase):

    def test_category_enum_has_the_six_required_values(self):
        self.assertEqual(
            {c.value for c in MemoryCategory},
            {"user_preference", "network", "project", "personal", "knowledge", "task"},
        )

    def test_category_coerce_accepts_strings_case_insensitive(self):
        self.assertEqual(MemoryCategory.coerce("NETWORK"), MemoryCategory.NETWORK)
        self.assertEqual(MemoryCategory.coerce(" task "), MemoryCategory.TASK)
        self.assertEqual(MemoryCategory.coerce(MemoryCategory.PROJECT), MemoryCategory.PROJECT)

    def test_category_coerce_rejects_unknown(self):
        for bad in ("bogus", "", None, 5):
            with self.assertRaises(ValueError):
                MemoryCategory.coerce(bad)

    def test_record_defaults(self):
        record = rec()

        self.assertTrue(record.id)
        self.assertEqual(record.category, MemoryCategory.KNOWLEDGE)
        self.assertEqual(record.importance, defaults.DEFAULT_IMPORTANCE)
        self.assertEqual(record.embedding, [])
        self.assertEqual(record.metadata, {})
        self.assertEqual(record.updated_at, record.created_at)

    def test_record_ids_are_unique(self):
        self.assertEqual(len({rec().id for _ in range(200)}), 200)

    def test_record_rejects_empty_text_and_session(self):
        with self.assertRaises(ValueError):
            rec(text="   ")
        with self.assertRaises(ValueError):
            rec(session_id="")
        with self.assertRaises(ValueError):
            rec(session_id=None)

    def test_record_strips_text_and_session(self):
        record = rec(text="  halo  ", session_id=" s9 ")
        self.assertEqual((record.text, record.session_id), ("halo", "s9"))

    def test_record_importance_is_clamped_and_validated(self):
        self.assertEqual(rec(importance=7).importance, 1.0)
        self.assertEqual(rec(importance=-3).importance, 0.0)

        for bad in ("tinggi", float("nan"), True):
            with self.assertRaises(ValueError):
                rec(importance=bad)

    def test_record_rejects_non_finite_embedding(self):
        with self.assertRaises(ValueError):
            rec(embedding=[0.1, float("inf")])
        with self.assertRaises(ValueError):
            rec(embedding="bukan-list")

    def test_record_rejects_non_dict_metadata(self):
        with self.assertRaises(ValueError):
            rec(metadata=["x"])

    def test_record_json_serialization_roundtrip_is_exact(self):
        record = rec(
            category="network", importance=0.8, metadata={"sumber": "chat", "n": 3},
            embedding=[0.1, 1 / 3, -2.5e-5], created_at=1.5, updated_at=2.5,
        )

        payload = json.loads(record.to_json())

        self.assertEqual(payload["category"], "network")          # nilai enum, bukan objek
        self.assertEqual(MemoryRecord.from_dict(payload), record)
        self.assertEqual(MemoryRecord.from_json(record.to_json()), record)

    def test_to_dict_can_exclude_embedding(self):
        record = rec(embedding=[1.0, 2.0])

        self.assertIn("embedding", record.to_dict())
        self.assertNotIn("embedding", record.to_dict(include_embedding=False))

    def test_from_dict_requires_session_and_text(self):
        with self.assertRaises(ValueError):
            MemoryRecord.from_dict({"text": "x"})
        with self.assertRaises(ValueError):
            MemoryRecord.from_dict("bukan-dict")

        record = MemoryRecord.from_dict({"session_id": "s", "text": "x", "category": "TASK"})
        self.assertEqual(record.category, MemoryCategory.TASK)

    def test_retrieval_result_is_json_serializable(self):
        result = RetrievalResult(record=rec(embedding=[1.0]), similarity=0.5, importance=0.6, score=0.52)

        payload = json.loads(result.to_json())

        self.assertEqual(payload["record"]["text"], "catatan")
        self.assertNotIn("embedding", payload["record"])
        self.assertIn("embedding", result.to_dict(include_embedding=True)["record"])


# ============================================================ EMBEDDER

class TestEmbedder(unittest.TestCase):

    def test_same_text_same_vector(self):
        provider = DefaultEmbeddingProvider()
        self.assertEqual(provider.embed("router mikrotik"), provider.embed("router mikrotik"))

    def test_different_instances_agree(self):
        self.assertEqual(
            DefaultEmbeddingProvider().embed("cek resource R1"),
            DefaultEmbeddingProvider().embed("cek resource R1"),
        )

    def test_deterministic_across_processes_regardless_of_hash_seed(self):
        code = (
            "import json; from core.semantic_memory import DefaultEmbeddingProvider as P; "
            "print(json.dumps(P().embed('router mikrotik hAP ax3')))"
        )
        outputs = []

        for seed in ("1", "2"):
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT)}
            done = subprocess.run(
                [sys.executable, "-c", code], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            outputs.append(json.loads(done.stdout))

        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], DefaultEmbeddingProvider().embed("router mikrotik hAP ax3"))

    def test_dimension_and_unit_norm(self):
        vector = DefaultEmbeddingProvider().embed("konfigurasi VRRP dua router")

        self.assertEqual(len(vector), defaults.EMBEDDING_DIMENSION)
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in vector)), 1.0, places=9)

    def test_custom_dimension(self):
        provider = DefaultEmbeddingProvider(dimension=64)

        self.assertEqual(provider.dimension, 64)
        self.assertEqual(len(provider.embed("halo dunia")), 64)

    def test_invalid_constructor_arguments(self):
        for kwargs in ({"dimension": 2}, {"dimension": "x"}, {"ngram_size": 0}):
            with self.assertRaises(ValueError):
                DefaultEmbeddingProvider(**kwargs)

    def test_text_without_tokens_gives_zero_vector(self):
        provider = DefaultEmbeddingProvider()

        for text in ("", "   ", "!!! ???"):
            self.assertEqual(set(provider.embed(text)), {0.0})

    def test_case_and_whitespace_are_ignored(self):
        provider = DefaultEmbeddingProvider()
        self.assertEqual(provider.embed("Router   MikroTik"), provider.embed("router mikrotik"))

    def test_similar_text_is_closer_than_unrelated_text(self):
        provider = DefaultEmbeddingProvider()
        base = provider.embed("router mikrotik rb4011")

        near = cosine_similarity(base, provider.embed("mikrotik router"))
        far = cosine_similarity(base, provider.embed("resep nasi goreng pedas"))

        self.assertGreater(near, 0.5)
        self.assertGreater(near, far + 0.3)

    def test_non_string_input_raises(self):
        with self.assertRaises(TypeError):
            DefaultEmbeddingProvider().embed(None)

    def test_embed_many_matches_embed(self):
        provider = DefaultEmbeddingProvider()
        texts = ["satu", "dua tiga"]

        self.assertEqual(provider.embed_many(texts), [provider.embed(t) for t in texts])

    def test_provider_interface_is_abstract_and_pluggable(self):
        with self.assertRaises(TypeError):
            EmbeddingProvider()

        self.assertEqual(KeywordProvider().embed("alpha alpha beta"), [2.0, 1.0, 0.0, 0.0])
        self.assertEqual(KeywordProvider().name, "KeywordProvider")


# ============================================================ SCORER

class TestCosine(unittest.TestCase):

    def test_identical_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 2, 3], [1, 2, 3]), 1.0)

    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)

    def test_opposite_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 2], [-1, -2]), -1.0)

    def test_known_value(self):
        self.assertAlmostEqual(
            cosine_similarity([1, 2, 3], [4, 5, 6]), 32 / math.sqrt(14 * 77), places=12,
        )

    def test_scale_invariant(self):
        self.assertAlmostEqual(cosine_similarity([1, 2, 3], [10, 20, 30]), 1.0)

    def test_zero_or_empty_vector_gives_zero(self):
        self.assertEqual(cosine_similarity([0, 0], [1, 2]), 0.0)
        self.assertEqual(cosine_similarity([], []), 0.0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            cosine_similarity([1, 2], [1, 2, 3])


class TestImportance(unittest.TestCase):

    NOW = 10_000_000.0

    def test_recency_half_life(self):
        self.assertAlmostEqual(recency_score(self.NOW, self.NOW), 1.0)
        self.assertAlmostEqual(recency_score(self.NOW - 30 * DAY, self.NOW, half_life_days=30), 0.5)
        self.assertAlmostEqual(recency_score(self.NOW - 60 * DAY, self.NOW, half_life_days=30), 0.25)

    def test_recency_future_timestamp_counts_as_fresh(self):
        self.assertEqual(recency_score(self.NOW + 5 * DAY, self.NOW), 1.0)

    def test_recency_rejects_bad_half_life(self):
        with self.assertRaises(ValueError):
            recency_score(self.NOW, self.NOW, half_life_days=0)

    def test_category_weight_ordering_and_unknown_default(self):
        self.assertGreater(category_weight("user_preference"), category_weight(MemoryCategory.KNOWLEDGE))
        self.assertEqual(category_weight(MemoryCategory.NETWORK), defaults.CATEGORY_WEIGHTS["network"])
        self.assertEqual(category_weight("tidak-ada"), defaults.DEFAULT_CATEGORY_WEIGHT)

    def test_factor_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(defaults.IMPORTANCE_FACTOR_WEIGHTS.values()), 1.0)

    def test_importance_matches_formula(self):
        record = rec(category="user_preference", importance=1.0, created_at=self.NOW)

        self.assertAlmostEqual(importance_score(record, self.NOW), 0.4 * 1.0 + 0.35 * 0.9 + 0.25 * 1.0)

    def test_importance_stays_within_zero_one(self):
        top = rec(category="user_preference", importance=1.0, created_at=self.NOW)
        bottom = rec(category="knowledge", importance=0.0, created_at=self.NOW - 3650 * DAY)

        self.assertLessEqual(importance_score(top, self.NOW), 1.0)
        self.assertGreaterEqual(importance_score(bottom, self.NOW), 0.0)
        self.assertLess(importance_score(bottom, self.NOW), 0.2)

    def test_importance_rises_with_manual_importance(self):
        low = rec(importance=0.1, created_at=self.NOW)
        high = rec(importance=0.9, created_at=self.NOW)

        self.assertGreater(importance_score(high, self.NOW), importance_score(low, self.NOW))

    def test_importance_falls_with_age(self):
        fresh = rec(created_at=self.NOW)
        old = rec(created_at=self.NOW - 90 * DAY)

        self.assertGreater(importance_score(fresh, self.NOW), importance_score(old, self.NOW))

    def test_importance_depends_on_category(self):
        pref = rec(category="user_preference", created_at=self.NOW)
        know = rec(category="knowledge", created_at=self.NOW)

        self.assertGreater(importance_score(pref, self.NOW), importance_score(know, self.NOW))

    def test_importance_uses_updated_at_for_recency(self):
        record = rec(created_at=self.NOW - 200 * DAY, updated_at=self.NOW)

        self.assertAlmostEqual(
            importance_score(record, self.NOW), importance_score(rec(created_at=self.NOW), self.NOW),
        )

    def test_combine_score(self):
        self.assertAlmostEqual(combine_score(1.0, 1.0), 1.0)
        self.assertAlmostEqual(combine_score(0.5, 0.5), 0.5)
        self.assertAlmostEqual(combine_score(-0.4, 0.5), defaults.IMPORTANCE_WEIGHT * 0.5)


# ============================================================ STORE

class TestStore(TempCase):

    def test_add_and_get_roundtrip_preserves_every_field(self):
        store = self.store()
        record = rec(
            text="R1 memakai MikroTik", category="network", importance=0.7,
            metadata={"sumber": "chat"}, embedding=[0.1, 0.2, 1 / 3],
        )

        store.add(record)

        self.assertEqual(store.get(record.id), record)

    def test_add_duplicate_id_raises(self):
        store = self.store()
        record = store.add(rec())

        with self.assertRaises(ValueError):
            store.add(rec(id=record.id))

    def test_add_rejects_non_record(self):
        with self.assertRaises(TypeError):
            self.store().add({"text": "x"})

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store().get("tidak-ada"))

    def test_update_changes_fields_and_bumps_updated_at_only(self):
        store = self.store()
        record = store.add(rec(created_at=self.clock.now, text="lama", category="task"))

        self.clock.advance(500)
        updated = store.update(
            record.id, text="baru", category="project", importance=0.9,
            metadata={"a": 1}, embedding=[1.0, 2.0],
        )

        self.assertEqual(updated.text, "baru")
        self.assertEqual(updated.category, MemoryCategory.PROJECT)
        self.assertEqual(updated.importance, 0.9)
        self.assertEqual(updated.metadata, {"a": 1})
        self.assertEqual(updated.embedding, [1.0, 2.0])
        self.assertEqual(updated.created_at, record.created_at)
        self.assertEqual(updated.updated_at, record.created_at + 500)
        self.assertEqual(updated.session_id, record.session_id)
        self.assertEqual(store.get(record.id), updated)             # benar-benar tersimpan

    def test_update_metadata_replaces_and_empty_dict_clears(self):
        store = self.store()
        record = store.add(rec(metadata={"a": 1}))

        self.assertEqual(store.update(record.id, metadata={"b": 2}).metadata, {"b": 2})
        self.assertEqual(store.update(record.id, metadata={}).metadata, {})

    def test_update_without_changes_does_not_touch_timestamp(self):
        store = self.store()
        record = store.add(rec(created_at=self.clock.now))

        self.clock.advance(999)

        self.assertEqual(store.update(record.id).updated_at, record.updated_at)

    def test_update_missing_returns_none(self):
        self.assertIsNone(self.store().update("tidak-ada", text="x"))

    def test_update_invalid_value_raises_and_keeps_old_data(self):
        store = self.store()
        record = store.add(rec(text="asli"))

        with self.assertRaises(ValueError):
            store.update(record.id, category="bogus")

        self.assertEqual(store.get(record.id).text, "asli")

    def test_delete(self):
        store = self.store()
        record = store.add(rec())

        self.assertTrue(store.delete(record.id))
        self.assertIsNone(store.get(record.id))
        self.assertFalse(store.delete(record.id))

    def test_list_is_scoped_to_session_and_newest_first(self):
        store = self.store()
        old = store.add(rec(text="lama", created_at=1.0))
        new = store.add(rec(text="baru", created_at=2.0))
        store.add(rec(session_id="s2", text="milik sesi lain"))

        self.assertEqual([r.id for r in store.list("s1")], [new.id, old.id])
        self.assertEqual([r.text for r in store.list("s2")], ["milik sesi lain"])
        self.assertEqual(store.list("kosong"), [])

    def test_list_limit_and_category_filter(self):
        store = self.store()
        for index in range(5):
            store.add(rec(text=f"n{index}", category="network", created_at=float(index)))
        store.add(rec(text="t", category="task", created_at=9.0))

        self.assertEqual(len(store.list("s1", limit=2)), 2)
        self.assertEqual(len(store.list("s1", category="network")), 5)
        self.assertEqual([r.text for r in store.list("s1", category=MemoryCategory.TASK)], ["t"])

        with self.assertRaises(ValueError):
            store.list("s1", limit=-1)

    def test_search_by_category_across_sessions_or_one_session(self):
        store = self.store()
        store.add(rec(session_id="s1", text="a", category="network"))
        store.add(rec(session_id="s2", text="b", category="network"))
        store.add(rec(session_id="s1", text="c", category="task"))

        self.assertEqual({r.text for r in store.search_by_category("network")}, {"a", "b"})
        self.assertEqual([r.text for r in store.search_by_category("network", session_id="s2")], ["b"])
        self.assertEqual(store.search_by_category("personal"), [])
        self.assertEqual(len(store.search_by_category("network", limit=1)), 1)

        with self.assertRaises(ValueError):
            store.search_by_category("bogus")

    def test_count_and_clear(self):
        store = self.store()
        for session in ("s1", "s1", "s2"):
            store.add(rec(session_id=session))

        self.assertEqual((store.count(), store.count("s1"), store.count("s2")), (3, 2, 1))
        self.assertEqual(store.clear("s1"), 2)
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.clear(), 1)
        self.assertEqual(store.count(), 0)

    def test_data_persists_across_store_instances(self):
        record = self.store().add(rec(text="tahan restart", embedding=[0.5]))

        self.assertEqual(self.store().get(record.id), record)

    def test_only_its_own_database_file_is_created(self):
        self.store().add(rec())

        self.assertEqual({p.name for p in self.tmp.iterdir()}, {self.db.name})

    def test_default_database_is_semantic_memory_db_in_database_folder(self):
        self.assertEqual(defaults.DEFAULT_DB_FILE.name, "semantic_memory.db")
        self.assertEqual(defaults.DEFAULT_DB_FILE.parent.name, "database")

    def test_importing_the_package_does_not_touch_the_default_db(self):
        # DB asli baru dibuat saat MemoryStore() dibuat, BUKAN saat import.
        target = defaults.DEFAULT_DB_FILE
        before = (target.exists(), target.stat().st_mtime if target.exists() else None)

        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        done = subprocess.run(
            [sys.executable, "-c", "import core.semantic_memory"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
        )

        after = (target.exists(), target.stat().st_mtime if target.exists() else None)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(before, after)

    def test_corrupt_embedding_json_is_tolerated(self):
        store = self.store()
        record = store.add(rec(embedding=[1.0, 2.0]))

        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE semantic_memory SET embedding = 'bukan json' WHERE id = ?", (record.id,))
            conn.commit()

        loaded = store.get(record.id)

        self.assertEqual(loaded.text, record.text)
        self.assertEqual(loaded.embedding, [])

    def test_unreadable_row_is_skipped_not_raised(self):
        store = self.store()
        good = store.add(rec(text="baik"))
        bad = store.add(rec(text="rusak"))

        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE semantic_memory SET category = 'bogus' WHERE id = ?", (bad.id,))
            conn.commit()

        with self.assertLogs("aira.semantic_memory.store", level="WARNING"):
            self.assertIsNone(store.get(bad.id))

        with self.assertLogs("aira.semantic_memory.store", level="WARNING"):
            self.assertEqual([r.id for r in store.list("s1")], [good.id])

    def test_concurrent_adds_from_threads(self):
        store = self.store()
        errors = []

        def worker(index):
            try:
                for n in range(10):
                    store.add(rec(session_id=f"s{index % 2}", text=f"t{index}-{n}"))
            except Exception as exc:  # pragma: no cover - hanya kalau ada bug
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(store.count(), 80)
        self.assertEqual(store.count("s0") + store.count("s1"), 80)


# ============================================================ RETRIEVER

class TestRetriever(TempCase):

    def kw_memory(self):
        return self.memory(embedder=KeywordProvider())

    def test_empty_store_returns_empty_list(self):
        self.assertEqual(self.memory().retrieve("router", "s1"), [])

    def test_ranking_puts_best_match_first(self):
        memory = self.memory()
        memory.remember("s1", "Router utama memakai MikroTik RB4011 dengan RouterOS 7", category="network")
        memory.remember("s1", "Pengguna suka jawaban singkat dan berbentuk tabel", category="user_preference")
        memory.remember("s1", "Deadline laporan proyek AIRA hari Jumat", category="task")

        results = memory.retrieve("router MikroTik RouterOS", "s1")

        self.assertEqual(results[0].record.category, MemoryCategory.NETWORK)
        self.assertEqual([r.score for r in results], sorted((r.score for r in results), reverse=True))

    def test_result_scores_are_consistent_with_scorer(self):
        memory = self.kw_memory()
        record = memory.remember("s1", "alpha beta")

        (result,) = memory.retrieve("alpha", "s1")

        self.assertAlmostEqual(result.similarity, 1 / math.sqrt(2))
        self.assertAlmostEqual(result.importance, importance_score(record, self.clock.now))
        self.assertAlmostEqual(result.score, combine_score(result.similarity, result.importance))

    def test_top_k_limits_results(self):
        memory = self.kw_memory()
        for index in range(6):
            memory.remember("s1", f"alpha n{index}")

        self.assertEqual(len(memory.retrieve("alpha", "s1", top_k=3)), 3)
        self.assertEqual(len(memory.retrieve("alpha", "s1", top_k=50)), 6)
        self.assertEqual(len(memory.retrieve("alpha", "s1")), defaults.DEFAULT_TOP_K)

    def test_top_k_zero_returns_empty_and_negative_raises(self):
        memory = self.kw_memory()
        memory.remember("s1", "alpha")

        self.assertEqual(memory.retrieve("alpha", "s1", top_k=0), [])

        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                memory.retrieve("alpha", "s1", top_k=bad)

    def test_top_k_keeps_the_best_ones(self):
        memory = self.kw_memory()
        memory.remember("s1", "alpha alpha alpha beta gamma")     # lemah
        best = memory.remember("s1", "alpha")                      # cosine 1.0

        (top,) = memory.retrieve("alpha", "s1", top_k=1)

        self.assertEqual(top.record.id, best.id)

    def test_category_filter(self):
        memory = self.kw_memory()
        network = memory.remember("s1", "alpha", category="network")
        memory.remember("s1", "alpha", category="task")

        results = memory.retrieve("alpha", "s1", category="network")

        self.assertEqual([r.record.id for r in results], [network.id])

    def test_session_isolation(self):
        memory = self.kw_memory()
        mine = memory.remember("s1", "alpha")
        memory.remember("s2", "alpha")

        self.assertEqual([r.record.id for r in memory.retrieve("alpha", "s1")], [mine.id])
        self.assertEqual(memory.retrieve("alpha", "sesi-tanpa-data"), [])

    def test_global_facts_only_with_include_global(self):
        memory = self.kw_memory()
        mine = memory.remember("s1", "alpha")
        shared = memory.remember(defaults.GLOBAL_SESSION_ID, "alpha")

        self.assertEqual([r.record.id for r in memory.retrieve("alpha", "s1")], [mine.id])
        self.assertEqual(
            {r.record.id for r in memory.retrieve("alpha", "s1", include_global=True)},
            {mine.id, shared.id},
        )

    def test_global_session_is_not_duplicated(self):
        memory = self.kw_memory()
        memory.remember(defaults.GLOBAL_SESSION_ID, "alpha")

        results = memory.retrieve("alpha", defaults.GLOBAL_SESSION_ID, include_global=True)

        self.assertEqual(len(results), 1)

    def test_blank_query_or_zero_vector_query_returns_empty(self):
        memory = self.kw_memory()
        memory.remember("s1", "alpha")

        self.assertEqual(memory.retrieve("", "s1"), [])
        self.assertEqual(memory.retrieve("   ", "s1"), [])
        self.assertEqual(memory.retrieve("kata tak dikenal", "s1"), [])   # vektor nol

    def test_invalid_arguments(self):
        memory = self.kw_memory()

        with self.assertRaises(ValueError):
            memory.retrieve("alpha", "")
        with self.assertRaises(TypeError):
            memory.retrieve(None, "s1")

    def test_unrelated_records_are_not_returned(self):
        memory = self.kw_memory()
        memory.remember("s1", "beta")

        self.assertEqual(memory.retrieve("alpha", "s1"), [])         # similarity 0

    def test_min_similarity_threshold(self):
        memory = self.kw_memory()
        memory.remember("s1", "alpha")                               # query "alpha beta" -> 0.707

        self.assertEqual(len(memory.retrieve("alpha beta", "s1", min_similarity=0.5)), 1)
        self.assertEqual(memory.retrieve("alpha beta", "s1", min_similarity=0.8), [])

    def test_records_with_wrong_dimension_or_no_embedding_are_skipped(self):
        memory = self.kw_memory()
        good = memory.remember("s1", "alpha")
        memory.store.add(rec(text="dimensi salah", embedding=[1.0, 0.0, 0.0]))
        memory.store.add(rec(text="belum di-embed"))

        self.assertEqual([r.record.id for r in memory.retrieve("alpha", "s1")], [good.id])

    def test_importance_breaks_similarity_ties(self):
        memory = self.kw_memory()
        low = memory.remember("s1", "alpha", importance=0.1)
        high = memory.remember("s1", "alpha", importance=0.9)

        results = memory.retrieve("alpha", "s1")

        self.assertEqual([r.record.id for r in results], [high.id, low.id])
        self.assertEqual(results[0].similarity, results[1].similarity)

    def test_similarity_dominates_importance_by_default(self):
        memory = self.kw_memory()
        exact = memory.remember("s1", "alpha", importance=0.0, category="knowledge")
        vague = memory.remember("s1", "alpha beta gamma delta", importance=1.0, category="user_preference")

        results = memory.retrieve("alpha", "s1")

        self.assertEqual(results[0].record.id, exact.id)
        self.assertEqual(results[1].record.id, vague.id)

    def test_newer_record_ranks_above_older_one(self):
        memory = self.kw_memory()
        old = memory.remember("s1", "alpha")
        self.clock.advance(120 * DAY)
        new = memory.remember("s1", "alpha")

        results = memory.retrieve("alpha", "s1")

        self.assertEqual([r.record.id for r in results], [new.id, old.id])

    def test_full_tie_is_broken_deterministically_by_id(self):
        memory = self.kw_memory()
        for record_id in ("b-id", "a-id", "c-id"):
            memory.add(rec(id=record_id, text="alpha", created_at=5.0))

        order = [r.record.id for r in memory.retrieve("alpha", "s1")]

        self.assertEqual(order, ["a-id", "b-id", "c-id"])

    def test_retrieval_does_not_modify_the_store(self):
        memory = self.kw_memory()
        record = memory.remember("s1", "alpha")

        memory.retrieve("alpha", "s1")

        self.assertEqual(memory.get(record.id), record)
        self.assertEqual(memory.count(), 1)

    def test_results_are_json_serializable(self):
        memory = self.memory()
        memory.remember("s1", "Router MikroTik utama", category="network")

        payload = [r.to_dict() for r in memory.retrieve("router mikrotik", "s1")]

        self.assertEqual(json.loads(json.dumps(payload))[0]["record"]["category"], "network")

    def test_custom_weights_change_ranking(self):
        memory = self.kw_memory()
        exact = memory.remember("s1", "alpha", importance=0.0, category="knowledge")
        important = memory.remember("s1", "alpha beta", importance=1.0, category="user_preference")

        retriever = MemoryRetriever(
            memory.store, KeywordProvider(), similarity_weight=0.0, importance_weight=1.0, clock=self.clock,
        )

        self.assertEqual(retriever.retrieve("alpha", "s1")[0].record.id, important.id)
        self.assertEqual(memory.retrieve("alpha", "s1")[0].record.id, exact.id)


# ============================================================ FASAD

class TestSemanticMemory(TempCase):

    def test_remember_embeds_and_persists(self):
        memory = self.memory()

        record = memory.remember("s1", "  VLAN 20 untuk kamera  ", category="network", importance=0.8, metadata={"k": 1})

        stored = memory.get(record.id)

        self.assertEqual(stored, record)
        self.assertEqual(stored.text, "VLAN 20 untuk kamera")
        self.assertEqual(len(stored.embedding), defaults.EMBEDDING_DIMENSION)
        self.assertEqual(stored.created_at, self.clock.now)

    def test_remember_validates_input(self):
        memory = self.memory()

        with self.assertRaises(ValueError):
            memory.remember("s1", "   ")
        with self.assertRaises(ValueError):
            memory.remember("s1", "x", category="bogus")

        self.assertEqual(memory.count(), 0)

    def test_add_embeds_record_without_embedding_and_keeps_existing_one(self):
        memory = self.memory(embedder=KeywordProvider())

        embedded = memory.add(rec(text="alpha"))
        preset = memory.add(rec(text="alpha", embedding=[9.0, 9.0, 9.0, 9.0]))

        self.assertEqual(embedded.embedding, [1.0, 0.0, 0.0, 0.0])
        self.assertEqual(preset.embedding, [9.0, 9.0, 9.0, 9.0])

    def test_update_text_re_embeds_so_retrieval_follows(self):
        memory = self.memory(embedder=KeywordProvider())
        record = memory.remember("s1", "alpha")

        self.clock.advance(10)
        updated = memory.update(record.id, text="beta")

        self.assertEqual(updated.embedding, [0.0, 1.0, 0.0, 0.0])
        self.assertEqual(memory.retrieve("alpha", "s1"), [])
        self.assertEqual([r.record.id for r in memory.retrieve("beta", "s1")], [record.id])

    def test_update_without_text_keeps_embedding(self):
        memory = self.memory(embedder=KeywordProvider())
        record = memory.remember("s1", "alpha")

        updated = memory.update(record.id, category="task", importance=0.2)

        self.assertEqual(updated.embedding, record.embedding)
        self.assertEqual(updated.category, MemoryCategory.TASK)
        self.assertIsNone(memory.update("tidak-ada", text="x"))

    def test_delete_removes_from_retrieval(self):
        memory = self.memory(embedder=KeywordProvider())
        record = memory.remember("s1", "alpha")

        self.assertTrue(memory.delete(record.id))
        self.assertEqual(memory.retrieve("alpha", "s1"), [])
        self.assertFalse(memory.delete(record.id))

    def test_list_search_count_clear_passthrough(self):
        memory = self.memory()
        memory.remember("s1", "a", category="network")
        memory.remember("s1", "b", category="task")
        memory.remember("s2", "c", category="network")

        self.assertEqual(len(memory.list("s1")), 2)
        self.assertEqual(len(memory.search_by_category("network")), 2)
        self.assertEqual(memory.count(), 3)
        self.assertEqual(memory.clear("s1"), 2)
        self.assertEqual(memory.count(), 1)

    def test_injected_embedding_provider_is_used(self):
        provider = KeywordProvider()
        memory = self.memory(embedder=provider)

        self.assertIs(memory.embedder, provider)
        self.assertIs(memory.retriever.embedder, provider)
        self.assertEqual(memory.remember("s1", "gamma").embedding, [0.0, 0.0, 1.0, 0.0])

    def test_components_can_be_injected(self):
        store = self.store()
        retriever = MemoryRetriever(store, KeywordProvider(), clock=self.clock)

        memory = SemanticMemory(retriever=retriever)

        self.assertIs(memory.store, store)
        self.assertIsInstance(memory.embedder, KeywordProvider)

    def test_end_to_end_works_without_any_network(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network dipakai!")):
            memory = self.memory()
            memory.remember("s1", "Gateway utama 192.168.43.1", category="network")
            memory.remember("s1", "Pengguna lebih suka GUI daripada CLI", category="user_preference")

            results = memory.retrieve("gateway 192.168.43.1", "s1", top_k=1)

        self.assertEqual(results[0].record.category, MemoryCategory.NETWORK)

    def test_get_semantic_memory_is_a_lazy_singleton(self):
        target = self.tmp / "singleton.db"

        with mock.patch.object(retriever_module, "_singleton", None), \
                mock.patch.object(store_module, "DEFAULT_DB_FILE", target):
            self.assertFalse(target.exists())                 # belum dibuat sebelum dipanggil

            first = sm.get_semantic_memory()
            second = sm.get_semantic_memory()

            self.assertIs(first, second)
            self.assertTrue(target.exists())


# ============================================================ API & BATASAN

class TestPublicApiAndConstraints(unittest.TestCase):

    def test_required_public_api_is_exposed(self):
        for name in ("SemanticMemory", "MemoryRecord", "MemoryRetriever", "EmbeddingProvider"):
            self.assertIn(name, sm.__all__)
            self.assertTrue(hasattr(sm, name))

    def test_expected_files_exist(self):
        for name in ("__init__", "models", "store", "embedder", "retriever", "scorer", "defaults"):
            self.assertTrue((PACKAGE_DIR / f"{name}.py").is_file(), name)

    def test_package_imports_nothing_forbidden(self):
        """Tanpa numpy/ML, tanpa network, dan tanpa modul AIRA selain dirinya sendiri
        (Brain, Context Builder, Event Bus, REI, model router, api, dst)."""
        banned_external = (
            "numpy", "scipy", "sklearn", "torch", "tensorflow", "transformers",
            "sentence_transformers", "faiss", "requests", "httpx", "aiohttp",
            "urllib", "http", "socket", "openai",
        )

        for path in sorted(PACKAGE_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                else:
                    continue

                for name in names:
                    top = name.split(".")[0]

                    self.assertNotIn(top, banned_external, f"{path.name} mengimpor {name}")

                    if top in ("core", "agents", "api", "tools"):
                        self.assertTrue(
                            name.startswith("core.semantic_memory"),
                            f"{path.name} mengimpor modul AIRA lain: {name}",
                        )

    def test_package_does_not_publish_to_event_bus(self):
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")

            self.assertNotIn("event_bus", source, path.name)
            self.assertNotIn(".publish(", source, path.name)


if __name__ == "__main__":
    unittest.main()
