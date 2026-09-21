"""
tests/test_conversation_context.py — unit test Conversation Context
(Sprint 2.6 / Worker 2).

Cakupan: recent (isi, urutan, limit, clamp), search (cocok, ranking, tidak ada
hasil, query kosong, Unicode, snippet, batas pindai), summary (statistik,
kata berulang, jendela, sesi kosong, deterministik), sesi tidak valid, isolasi
sesi, jaminan READ-ONLY (SQL yang dijalankan), batas impor (tanpa LLM/network),
dan adapter tool (sesi diikat dari event_scope, bukan dari LLM).

Semua test memakai database SEMENTARA (patch core.chat_sessions.DB_FILE) -
TIDAK menyentuh database/chat_sessions.db asli, tanpa jaringan.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_conversation_context -v
"""

import ast
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from core import chat_sessions as store
from core import conversation_context as cc
from core.conversation_context import (
    ConversationContext,
    InvalidRequestError,
    SessionNotFoundError,
)
from core.events import event_scope

from agents.rei import conversation_tools as ct


class Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "sessions_test.db"

        patcher = mock.patch.object(store, "DB_FILE", self.db)
        patcher.start()
        self.addCleanup(patcher.stop)
        store.init_db()

        self.svc = ConversationContext()

    def session(self, turns=(), title=None):
        sid = store.create_session(title)["id"]
        for role, text in turns:
            store.add_turn(sid, role, text)
        return sid

    def dump(self):
        """Isi mentah kedua tabel (untuk memastikan tidak ada yang berubah)."""
        with closing(sqlite3.connect(self.db)) as conn:
            return (
                conn.execute("SELECT * FROM chat_sessions ORDER BY id").fetchall(),
                conn.execute("SELECT * FROM chat_turns ORDER BY id").fetchall(),
                conn.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall(),
            )


def chat(n):
    """n giliran bergantian user/assistant: 'pesan-1', 'pesan-2', ..."""
    return [("user" if i % 2 else "assistant", f"pesan-{i}") for i in range(1, n + 1)]


# ============================================================ RECENT

class TestRecent(Base):

    def test_returns_last_n_in_chronological_order(self):
        sid = self.session(chat(12))

        result = self.svc.recent(sid, 5)

        self.assertEqual([t.content for t in result.turns], [f"pesan-{i}" for i in range(8, 13)])
        ids = [t.id for t in result.turns]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(result.order, "chronological")

    def test_metadata_total_and_has_more(self):
        sid = self.session(chat(12))

        result = self.svc.recent(sid, 5)

        self.assertEqual((result.returned, result.total_turns, result.has_more), (5, 12, True))

        everything = self.svc.recent(sid, 50)
        self.assertEqual((everything.returned, everything.has_more), (12, False))

    def test_default_limit_and_none(self):
        sid = self.session(chat(30))

        self.assertEqual(self.svc.recent(sid).returned, cc.DEFAULT_RECENT_LIMIT)
        self.assertEqual(self.svc.recent(sid, None).returned, cc.DEFAULT_RECENT_LIMIT)

    def test_limit_is_clamped_to_safe_maximum(self):
        sid = self.session(chat(cc.MAX_LIMIT + 10))

        result = self.svc.recent(sid, 10_000)

        self.assertEqual(result.returned, cc.MAX_LIMIT)
        self.assertEqual(result.limit, cc.MAX_LIMIT)
        self.assertTrue(result.limit_clamped)
        self.assertTrue(result.has_more)
        self.assertFalse(self.svc.recent(sid, 5).limit_clamped)

    def test_invalid_limits_are_rejected(self):
        sid = self.session(chat(3))

        for bad in (0, -1, "5", 2.5, True, [1]):
            with self.assertRaises(InvalidRequestError, msg=repr(bad)):
                self.svc.recent(sid, bad)

    def test_ordering_follows_insertion_even_if_timestamps_are_equal(self):
        sid = self.session()
        with closing(sqlite3.connect(self.db)) as conn:
            for i in range(5):
                conn.execute(
                    "INSERT INTO chat_turns (session_id, role, content, created_at) VALUES (?, 'user', ?, 100.0)",
                    (sid, f"sama-{i}"),
                )
            conn.commit()

        self.assertEqual(
            [t.content for t in self.svc.recent(sid, 5).turns], [f"sama-{i}" for i in range(5)],
        )

    def test_long_content_is_truncated_and_flagged(self):
        sid = self.session([("assistant", "x" * (cc.MAX_TURN_CHARS + 500)), ("user", "pendek")])

        long_turn, short_turn = self.svc.recent(sid, 2).turns

        self.assertTrue(long_turn.truncated)
        self.assertLessEqual(len(long_turn.content), cc.MAX_TURN_CHARS + 2)
        self.assertTrue(long_turn.content.endswith("…"))
        self.assertFalse(short_turn.truncated)

    def test_session_without_turns_returns_empty(self):
        sid = self.session()

        result = self.svc.recent(sid, 5)

        self.assertEqual((result.turns, result.returned, result.total_turns, result.has_more), ((), 0, 0, False))

    def test_result_is_json_serializable_and_lean(self):
        sid = self.session(chat(3))

        payload = self.svc.recent(sid).to_dict()

        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertEqual(set(payload["turns"][0]), {"id", "role", "content", "created_at", "truncated"})


# ============================================================ SEARCH

class TestSearch(Base):

    def test_finds_matching_turns_case_insensitively(self):
        sid = self.session([
            ("user", "Tolong cek Router MikroTik R1"),
            ("assistant", "CPU R1 normal"),
            ("user", "terima kasih"),
        ])

        result = self.svc.search(sid, "router")

        self.assertEqual([m.turn.content for m in result.matches], ["Tolong cek Router MikroTik R1"])
        self.assertEqual(result.matches[0].matched_terms, ("router",))
        self.assertEqual(result.total_matches, 1)

    def test_no_result(self):
        sid = self.session(chat(4))

        result = self.svc.search(sid, "tidak-pernah-ada")

        self.assertEqual((result.matches, result.total_matches, result.returned, result.has_more), ((), 0, 0, False))

    def test_empty_or_unusable_query_is_rejected(self):
        sid = self.session(chat(2))

        for bad in ("", "   ", "\n\t", "???", "!!! ...", None, 123, ["router"]):
            with self.assertRaises(InvalidRequestError, msg=repr(bad)):
                self.svc.search(sid, bad)

    def test_ranking_phrase_then_all_terms_then_partial(self):
        sid = self.session([
            ("user", "router mikrotik R1 sedang lambat"),          # frasa berurutan -> 1.5
            ("user", "cek vrrp di router"),                        # 1 dari 2 kata -> 0.5
            ("user", "mikrotik vrrp konfigurasi router utama"),    # semua kata, tak berurutan -> 1.0
        ])

        result = self.svc.search(sid, "router mikrotik")

        self.assertEqual(
            [(m.turn.content.split()[0], m.score) for m in result.matches],
            [("router", 1.5), ("mikrotik", 1.0), ("cek", 0.5)],
        )

    def test_equal_scores_prefer_newer_turn(self):
        sid = self.session([("user", "vrrp lama"), ("user", "vrrp tengah"), ("user", "vrrp baru")])

        result = self.svc.search(sid, "vrrp")

        self.assertEqual([m.turn.content for m in result.matches], ["vrrp baru", "vrrp tengah", "vrrp lama"])

    def test_limit_and_clamp(self):
        sid = self.session([("user", f"vrrp catatan {i}") for i in range(8)])

        limited = self.svc.search(sid, "vrrp", 3)
        self.assertEqual((limited.returned, limited.total_matches, limited.has_more), (3, 8, True))

        clamped = self.svc.search(sid, "vrrp", 9999)
        self.assertEqual((clamped.limit, clamped.limit_clamped, clamped.returned), (cc.MAX_LIMIT, True, 8))

        with self.assertRaises(InvalidRequestError):
            self.svc.search(sid, "vrrp", 0)

    def test_results_are_deterministic(self):
        sid = self.session([("user", "router a"), ("assistant", "router b"), ("user", "router c")])

        self.assertEqual(self.svc.search(sid, "router").to_dict(), self.svc.search(sid, "router").to_dict())

    def test_unicode_case_folding(self):
        sid = self.session([("user", "Sekolah ÉCOLE Paris"), ("user", "tidak relevan")])

        result = self.svc.search(sid, "école")

        self.assertEqual(result.returned, 1)

    def test_sql_wildcards_and_quotes_in_query_are_inert(self):
        sid = self.session([("user", "diskon 50% hari ini"), ("user", "biasa saja")])

        # '%' / '_' bukan wildcard (pencarian dilakukan di Python, bukan LIKE)
        self.assertEqual(self.svc.search(sid, "100%_").total_matches, 0)
        self.assertEqual(self.svc.search(sid, "x' OR '1'='1").total_matches, 0)
        self.assertEqual(self.svc.search(sid, "50%").returned, 1)

    def test_all_short_terms_fall_back_instead_of_failing(self):
        sid = self.session([("user", "titik r di sini")])

        self.assertEqual(self.svc.search(sid, "r").returned, 1)

    def test_query_is_bounded(self):
        sid = self.session([("user", "kata0 kata1 kata2 kata3 kata4 kata5 kata6 kata7 kata8 kata9")])

        result = self.svc.search(sid, " ".join(f"kata{i}" for i in range(100)))

        self.assertLessEqual(len(result.terms), cc.MAX_QUERY_TERMS)
        self.assertLessEqual(len(result.query), cc.MAX_QUERY_CHARS)

    def test_long_turn_snippet_is_centered_on_the_match(self):
        text = ("awal " * 300) + "kata-kunci-rahasia " + ("akhir " * 300)
        sid = self.session([("assistant", text)])

        (match,) = self.svc.search(sid, "kata-kunci-rahasia").matches

        self.assertTrue(match.turn.truncated)
        self.assertIn("kata-kunci-rahasia", match.turn.content)
        self.assertTrue(match.turn.content.startswith("…"))

    def test_scan_is_bounded_and_reports_truncation(self):
        sid = self.session([("user", "target lama")] + [("user", f"isi {i}") for i in range(5)])

        with mock.patch.object(cc, "SEARCH_SCAN_LIMIT", 3):
            result = self.svc.search(sid, "target")

        self.assertEqual(result.scanned, 3)
        self.assertTrue(result.scan_truncated)
        self.assertEqual(result.total_matches, 0)          # giliran tertua tak terjangkau

        self.assertFalse(self.svc.search(sid, "target").scan_truncated)
        self.assertEqual(self.svc.search(sid, "target").total_matches, 1)

    def test_only_current_session_scope_is_supported_today(self):
        sid = self.session(chat(2))

        self.assertEqual(self.svc.search(sid, "pesan", scope="session").scope, "session")

        for scope in ("all", "all_sessions", ""):
            with self.assertRaises(InvalidRequestError):
                self.svc.search(sid, "pesan", scope=scope)


# ============================================================ SUMMARY

class TestSummary(Base):

    def build(self):
        return self.session([
            ("user", "Tolong cek konfigurasi VRRP di router utama"),
            ("assistant", "VRRP di router utama berstatus master, prioritas 200"),
            ("user", "Bagaimana kalau router utama mati? VRRP pindah ke mana"),
            ("assistant", "Jika router utama mati, VRRP pindah ke router cadangan"),
        ], title="Diskusi VRRP")

    def test_statistics_cover_whole_session(self):
        sid = self.build()

        result = self.svc.summary(sid, 2)

        self.assertEqual(
            (result.total_turns, result.user_turns, result.assistant_turns, result.title),
            (4, 2, 2, "Diskusi VRRP"),
        )
        self.assertIsNotNone(result.first_turn_at)
        self.assertLessEqual(result.first_turn_at, result.last_turn_at)

    def test_edges_are_independent_of_window(self):
        sid = self.build()

        result = self.svc.summary(sid, 1)

        self.assertEqual(result.opening_request.content, "Tolong cek konfigurasi VRRP di router utama")
        self.assertTrue(result.latest_user_request.content.startswith("Bagaimana kalau router utama mati"))
        self.assertTrue(result.latest_assistant_reply.content.startswith("Jika router utama mati"))

    def test_window_limits_excerpts_not_totals(self):
        sid = self.session(chat(12))

        result = self.svc.summary(sid, 4)

        self.assertEqual([t.content for t in result.excerpts], ["pesan-9", "pesan-10", "pesan-11", "pesan-12"])
        self.assertEqual((result.window, result.total_turns), (4, 12))

    def test_keywords_repeat_only_and_skip_stopwords(self):
        sid = self.build()

        terms = dict(self.svc.summary(sid, 10).keywords)

        self.assertGreaterEqual(terms.get("vrrp", 0), 4)
        self.assertGreaterEqual(terms.get("router", 0), 4)
        self.assertNotIn("yang", terms)
        self.assertNotIn("di", terms)
        self.assertTrue(all(count >= cc.KEYWORD_MIN_COUNT for count in terms.values()))

    def test_digest_is_plain_text_with_facts(self):
        sid = self.build()

        digest = self.svc.summary(sid).digest

        self.assertIn("Sesi 'Diskusi VRRP': 4 giliran (2 user, 2 assistant).", digest)
        self.assertIn("Permintaan pertama user:", digest)
        self.assertIn("Kata yang sering muncul:", digest)

    def test_method_marks_it_as_non_llm(self):
        self.assertEqual(self.svc.summary(self.build()).method, "deterministic_extractive")

    def test_empty_session_summary(self):
        sid = self.session(title="Kosong")

        result = self.svc.summary(sid)

        self.assertEqual((result.total_turns, result.user_turns, result.assistant_turns), (0, 0, 0))
        self.assertIsNone(result.first_turn_at)
        self.assertIsNone(result.opening_request)
        self.assertIsNone(result.latest_assistant_reply)
        self.assertEqual((result.excerpts, result.keywords), ((), ()))
        self.assertIn("belum punya giliran", result.digest)

    def test_single_user_turn_is_not_repeated_as_latest(self):
        sid = self.session([("user", "halo router")])

        digest = self.svc.summary(sid).digest

        self.assertIn("Permintaan pertama user", digest)
        self.assertNotIn("Permintaan user terakhir", digest)

    def test_limit_validation_and_clamp(self):
        sid = self.build()

        with self.assertRaises(InvalidRequestError):
            self.svc.summary(sid, 0)

        self.assertTrue(self.svc.summary(sid, 9999).window_clamped)

    def test_is_deterministic_and_json_safe(self):
        sid = self.build()

        first, second = self.svc.summary(sid).to_dict(), self.svc.summary(sid).to_dict()

        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first)), first)

    def test_whitespace_is_collapsed_and_long_items_are_shortened(self):
        sid = self.session([("user", "a\n\n   b\t" + "z" * 1000)])

        item = self.svc.summary(sid).opening_request

        self.assertNotIn("\n", item.content)
        self.assertTrue(item.truncated)
        self.assertLessEqual(len(item.content), cc.SUMMARY_ITEM_CHARS + 2)


# ============================================================ SESI TIDAK VALID

class TestInvalidSession(Base):

    def test_unknown_session(self):
        for call in (
            lambda: self.svc.recent("tidak-ada"),
            lambda: self.svc.search("tidak-ada", "x1"),
            lambda: self.svc.summary("tidak-ada"),
        ):
            with self.assertRaises(SessionNotFoundError):
                call()

    def test_malformed_session_ids(self):
        for bad in (None, "", "   ", 123, ["s1"], "x" * 500):
            with self.assertRaises(InvalidRequestError, msg=repr(bad)):
                self.svc.recent(bad)

    def test_deleted_session_is_not_found(self):
        sid = self.session(chat(3))
        store.delete_session(sid)

        with self.assertRaises(SessionNotFoundError):
            self.svc.recent(sid)

    def test_error_types_are_catchable_generically(self):
        self.assertTrue(issubclass(SessionNotFoundError, cc.ConversationContextError))
        self.assertTrue(issubclass(SessionNotFoundError, LookupError))
        self.assertTrue(issubclass(InvalidRequestError, ValueError))

    def test_surrounding_whitespace_in_id_is_stripped(self):
        sid = self.session(chat(2))

        self.assertEqual(self.svc.recent(f"  {sid}  ").session_id, sid)


# ============================================================ ISOLASI SESI

class TestSessionIsolation(Base):

    def setUp(self):
        super().setUp()
        self.a = self.session([("user", "alfa123 router"), ("assistant", "jawaban A")], title="Sesi A")
        self.b = self.session([("user", "bravo456 router"), ("assistant", "jawaban B")], title="Sesi B")

    def test_recent_never_crosses_sessions(self):
        self.assertEqual([t.content for t in self.svc.recent(self.a).turns], ["alfa123 router", "jawaban A"])
        self.assertEqual([t.content for t in self.svc.recent(self.b).turns], ["bravo456 router", "jawaban B"])

    def test_search_never_crosses_sessions(self):
        self.assertEqual(self.svc.search(self.a, "bravo456").total_matches, 0)
        self.assertEqual(self.svc.search(self.a, "router").returned, 1)
        self.assertEqual(self.svc.search(self.b, "router").matches[0].turn.content, "bravo456 router")

    def test_summary_never_crosses_sessions(self):
        result = self.svc.summary(self.a)

        self.assertEqual((result.title, result.total_turns), ("Sesi A", 2))
        self.assertNotIn("bravo456", json.dumps(result.to_dict()))

    def test_injection_style_ids_do_not_leak_other_sessions(self):
        for evil in ("x' OR '1'='1", "%", "*", f"{self.a}' OR 1=1 --", "_"):
            with self.assertRaises(SessionNotFoundError, msg=evil):
                self.svc.recent(evil)

    def test_session_id_prefix_or_wildcard_does_not_match(self):
        with self.assertRaises(SessionNotFoundError):
            self.svc.recent(self.a[:6])

    def test_every_chat_turns_query_is_scoped_by_session_id(self):
        statements = []

        def traced():
            conn = store._connect()
            conn.set_trace_callback(statements.append)
            return conn

        svc = ConversationContext(connect=traced)
        svc.recent(self.a)
        svc.search(self.a, "router")
        svc.summary(self.a)

        turn_queries = [s for s in statements if "chat_turns" in s]

        self.assertTrue(turn_queries)
        for statement in turn_queries:
            self.assertIn("session_id = ", statement)


# ============================================================ READ-ONLY

class TestReadOnly(Base):

    def test_no_method_changes_any_data_or_schema(self):
        sid = self.session(chat(6), title="Judul")
        before = self.dump()

        self.svc.recent(sid, 3)
        self.svc.search(sid, "pesan")
        self.svc.summary(sid)
        for call in (lambda: self.svc.recent("tidak-ada"), lambda: self.svc.search(sid, "")):
            with self.assertRaises(cc.ConversationContextError):
                call()

        self.assertEqual(self.dump(), before)          # termasuk updated_at & daftar tabel

    def test_connection_rejects_writes_at_sqlite_level(self):
        sid = self.session(chat(2))

        with closing(self.svc._open()) as conn:
            for sql in (
                "DELETE FROM chat_turns",
                "UPDATE chat_sessions SET title = 'x'",
                "INSERT INTO chat_turns (session_id, role, content, created_at) VALUES ('s', 'user', 'x', 1)",
                "CREATE TABLE ilegal (id INTEGER)",
            ):
                with self.assertRaises(sqlite3.OperationalError, msg=sql):
                    conn.execute(sql)

        self.assertEqual(self.svc.recent(sid).total_turns, 2)

    def test_only_select_statements_run_and_raw_columns_are_never_read(self):
        sid = self.session(chat(4))
        statements = []

        def traced():
            conn = store._connect()
            conn.set_trace_callback(statements.append)
            return conn

        svc = ConversationContext(connect=traced)
        svc.recent(sid)
        svc.search(sid, "pesan")
        svc.summary(sid)

        self.assertTrue(statements)
        for statement in statements:
            head = statement.strip().split()[0].upper()
            self.assertIn(head, {"SELECT", "PRAGMA", "BEGIN", "ROLLBACK", "COMMIT"}, statement)
            for forbidden in ("raw_history", "steps_json", "interaction_schema_json", "SELECT *"):
                self.assertNotIn(forbidden, statement)

    def test_creates_no_extra_database_files(self):
        sid = self.session(chat(3))

        self.svc.recent(sid)
        self.svc.summary(sid)

        self.assertEqual({p.name for p in self.tmp.iterdir()}, {self.db.name})

    def test_import_has_no_side_effects_and_uses_no_llm_or_network(self):
        source = Path(cc.__file__).read_text(encoding="utf-8")
        allowed = {
            "__future__", "logging", "re", "sqlite3", "threading", "collections",
            "contextlib", "dataclasses", "typing", "core.chat_sessions", "core",
        }

        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names = [node.module]
            else:
                continue

            for name in names:
                self.assertIn(name, allowed, f"import tak terduga: {name}")

        for forbidden in ("provider_client", "call_model", "requests", "event_bus", ".publish("):
            self.assertNotIn(forbidden, source)


# ============================================================ ADAPTER TOOL

class TestToolAdapter(Base):

    def setUp(self):
        super().setUp()
        self.a = self.session([("user", "ip router A adalah 10.0.0.1"), ("assistant", "dicatat")], title="A")
        self.b = self.session([("user", "ip router B adalah 10.9.9.9")], title="B")

        patcher = mock.patch.object(cc, "_singleton", ConversationContext())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_tools_read_the_active_session_from_event_scope(self):
        with event_scope(session_id=self.a):
            recent = ct.conversation_history_recent(limit=5)
            search = ct.conversation_history_search(query="router")
            summary = ct.conversation_history_summary()

        for result, tool in ((recent, ct.TOOL_RECENT), (search, ct.TOOL_SEARCH), (summary, ct.TOOL_SUMMARY)):
            self.assertTrue(result["success"], result)
            self.assertEqual((result["tool"], result["session_id"]), (tool, self.a))
            self.assertEqual(json.loads(json.dumps(result)), result)

        self.assertEqual(len(recent["turns"]), 2)
        self.assertEqual(search["matches"][0]["content"], "ip router A adalah 10.0.0.1")
        self.assertEqual(summary["title"], "A")

    def test_no_active_session_fails_safe(self):
        for result in (
            ct.conversation_history_recent(),
            ct.conversation_history_search(query="router"),
            ct.conversation_history_summary(),
        ):
            self.assertFalse(result["success"])
            self.assertEqual(result["error"], ct.NO_SESSION_ERROR)

    def test_llm_supplied_session_id_cannot_read_another_session(self):
        with event_scope(session_id=self.a):
            results = [
                ct.conversation_history_recent(session_id=self.b),
                ct.conversation_history_search(query="router", session_id=self.b),
                ct.conversation_history_summary(session_id=self.b),
            ]

        for result in results:
            self.assertTrue(result["success"])
            self.assertEqual(result["session_id"], self.a)
            self.assertIn("diabaikan", result["warning"])
            self.assertNotIn("10.9.9.9", json.dumps(result))

    def test_llm_session_id_is_ignored_even_without_active_scope(self):
        result = ct.conversation_history_recent(session_id=self.b)

        self.assertFalse(result["success"])
        self.assertNotIn("10.9.9.9", json.dumps(result))

    def test_argument_coercion_and_validation(self):
        with event_scope(session_id=self.a):
            self.assertEqual(ct.conversation_history_recent(limit="1")["returned"], 1)
            self.assertEqual(ct.conversation_history_recent(limit=1.0)["returned"], 1)

            for bad in ("abc", 0, -3, True, 2.5, [1]):
                result = ct.conversation_history_recent(limit=bad)
                self.assertFalse(result["success"], bad)
                self.assertIn("limit", result["error"])

            self.assertFalse(ct.conversation_history_search(query="")["success"])
            self.assertFalse(ct.conversation_history_search()["success"])

    def test_unknown_session_in_scope_returns_error_dict(self):
        with event_scope(session_id="tidak-ada"):
            result = ct.conversation_history_recent()

        self.assertFalse(result["success"])
        self.assertIn("tidak ditemukan", result["error"])

    def test_unexpected_failure_is_contained(self):
        with event_scope(session_id=self.a), mock.patch.object(
            ConversationContext, "recent", side_effect=sqlite3.OperationalError("database is locked"),
        ), self.assertLogs("aira.rei.conversation_tools", level="ERROR"):
            result = ct.conversation_history_recent()

        self.assertEqual(result, {"success": False, "tool": ct.TOOL_RECENT, "error": "Gagal membaca riwayat percakapan."})

    def test_contract_and_schemas_are_consistent(self):
        wire_names = set(ct.TOOL_CONTRACT.values())

        self.assertEqual(set(ct.TOOL_CONTRACT), {
            "conversation_history.recent", "conversation_history.search", "conversation_history.summary",
        })
        self.assertEqual(set(ct.CONVERSATION_TOOLS), wire_names)
        self.assertEqual(set(ct.CONVERSATION_TOOL_CATEGORY), wire_names)
        self.assertEqual(ct.CONVERSATION_DANGEROUS_TOOLS, set())
        self.assertEqual({s["function"]["name"] for s in ct.CONVERSATION_TOOL_SCHEMAS}, wire_names)

        for schema in ct.CONVERSATION_TOOL_SCHEMAS:
            function = schema["function"]
            properties = function["parameters"]["properties"]

            self.assertEqual(schema["type"], "function")
            self.assertRegex(function["name"], r"^[a-zA-Z0-9_-]{1,64}$")   # tanpa titik
            self.assertNotIn("session_id", properties)                     # tidak pernah dari LLM
            self.assertTrue(function["description"])
            self.assertTrue(set(function["parameters"]["required"]) <= set(properties))

        search = next(s for s in ct.CONVERSATION_TOOL_SCHEMAS if s["function"]["name"] == ct.TOOL_SEARCH)
        self.assertEqual(search["function"]["parameters"]["required"], ["query"])

    def test_tools_are_not_registered_by_this_module(self):
        source = Path(ct.__file__).read_text(encoding="utf-8")

        for touched in ("agents.rei.registry", "agents.rei.planner", "core.orchestrator"):
            self.assertNotRegex(source, rf"^\s*(from|import)\s+{re.escape(touched)}", touched)


if __name__ == "__main__":
    unittest.main()
