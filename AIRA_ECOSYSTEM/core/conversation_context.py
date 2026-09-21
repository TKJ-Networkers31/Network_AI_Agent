"""
core/conversation_context.py — Conversation Context (Sprint 2.6 / Worker 2).

Lapisan BACA-SAJA di atas penyimpanan percakapan yang SUDAH ada:

    database/chat_sessions.db
        chat_sessions  (id, title, raw_history, created_at, updated_at)
        chat_turns     (id, session_id, role, content, steps_json,
                        interaction_schema_json, created_at)

Ini BUKAN database baru dan BUKAN pipeline AI baru. Tidak ada tabel yang
dibuat, tidak ada tulis, tidak ada LLM/embedding/network.

Kemampuan awal (kontrak konseptual "conversation_history.*"):

    recent(session_id, limit)         giliran terbaru, urut kronologis
    search(session_id, query, limit)  pencarian kata kunci deterministik
    summary(session_id, limit)        ringkasan EKSTRAKTIF deterministik

BATAS KERAS
-----------
* Read-only. Setiap koneksi memakai `PRAGMA query_only = ON` sehingga tulis
  gagal di level SQLite (bukan sekadar "kebetulan tidak menulis"). Semua
  query dijalankan dalam satu transaksi baca, jadi total_turns/has_more
  konsisten dengan baris yang dikembalikan.
* Isolasi sesi: SETIAP query pada chat_turns memakai `WHERE session_id = ?`
  (parameter terikat, tanpa interpolasi string). Sesi yang tidak ada ->
  SessionNotFoundError; tidak pernah "jatuh" ke sesi lain.
  Catatan: repo ini belum punya konsep user/otorisasi - batas isolasinya
  adalah session_id. Layanan ini tidak menambah maupun mem-bypass apa pun.
* Hanya kolom `content`, `role`, `id`, `created_at` dari chat_turns yang
  dibaca. `raw_history` (riwayat mentah LLM, termasuk instruksi sistem dan
  nilai form yang belum dimasker) dan `steps_json` (hasil tool mentah) TIDAK
  PERNAH dibaca. `content` yang tersimpan sudah berupa display_message (nilai
  sensitif sudah dimasker oleh agents/rei/dio_tools.py).
* Keluaran selalu dibatasi (jumlah giliran, panjang teks per giliran, jumlah
  baris yang dipindai) supaya aman dimasukkan ke konteks LLM.
* Hanya membaca data yang sudah ter-commit. chat_turns baru ditulis SETELAH
  giliran selesai (lihat api/routers/ws.py), jadi pesan user pada giliran yang
  sedang berjalan belum terlihat di sini.

Ringkasan (summary) sengaja EKSTRAKTIF: repo belum punya abstraksi peringkas
yang bisa dipakai ulang (satu-satunya pemakaian LLM di luar chat adalah
agents/rei/auto_extract.py dan core/task_classifier.py, keduanya terikat pada
tujuan masing-masing). Hasilnya terstruktur (statistik, permintaan pertama,
permintaan/jawaban terakhir, kata berulang, kutipan giliran terbaru) sehingga
peringkas LLM di masa depan cukup memakainya sebagai masukan.

Modul ini hanya mengimpor pustaka standar; core.chat_sessions diimpor LAZY
(saat koneksi pertama dibuka) supaya mengimpor modul ini tidak menyentuh disk.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger("aira.conversation_context")

# ------------------------------------------------------------------ batas

DEFAULT_RECENT_LIMIT = 10
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_SUMMARY_LIMIT = 10
MAX_LIMIT = 50                 # batas atas jumlah giliran per panggilan (di-clamp)

MAX_TURN_CHARS = 600           # panjang maksimum teks satu giliran di keluaran
SUMMARY_ITEM_CHARS = 300       # panjang maksimum item ringkasan / kutipan

SEARCH_SCAN_LIMIT = 2000       # paling banyak giliran TERBARU yang dipindai per pencarian
MAX_QUERY_CHARS = 200
MAX_QUERY_TERMS = 8
MIN_TERM_CHARS = 2
PHRASE_BONUS = 0.5

SUMMARY_KEYWORDS = 8
KEYWORD_MIN_CHARS = 3
KEYWORD_MIN_COUNT = 2

MAX_SESSION_ID_CHARS = 128

SCOPE_SESSION = "session"
SUPPORTED_SCOPES = (SCOPE_SESSION,)

METHOD_EXTRACTIVE = "deterministic_extractive"

_WORD_RE = re.compile(r"\w+", re.UNICODE)

_STOPWORDS = frozenset("""
yang dan di ke dari untuk dengan ini itu pada adalah akan atau juga saya aku kamu anda
tidak nggak gak bisa ada apa bagaimana sudah belum kalau jika karena tapi tetapi dalam
oleh sebagai agar supaya lagi aja saja dong tolong mau cara buat bikin jadi sama lebih
hanya seperti kita kami mereka dia nya yg sih deh kok
the and for with that this are was you your can not have has from what how please will
would there their them then than but all any its into about
""".split())


# ------------------------------------------------------------------ error

class ConversationContextError(Exception):
    """Basis semua kesalahan layanan ini (pesannya aman ditampilkan ke user/LLM)."""


class InvalidRequestError(ConversationContextError, ValueError):
    """Argumen tidak valid (session_id kosong, limit salah, query kosong, dst)."""


class SessionNotFoundError(ConversationContextError, LookupError):
    """session_id valid secara bentuk, tetapi tidak ada di chat_sessions."""


# ------------------------------------------------------------------ hasil

@dataclass(frozen=True)
class TurnView:
    id: int
    role: str
    content: str
    created_at: float
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class RecentResult:
    session_id: str
    turns: tuple
    limit: int
    limit_clamped: bool
    total_turns: int
    order: str = "chronological"

    @property
    def returned(self) -> int:
        return len(self.turns)

    @property
    def has_more(self) -> bool:
        return self.total_turns > self.returned

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "order": self.order,
            "limit": self.limit,
            "limit_clamped": self.limit_clamped,
            "returned": self.returned,
            "total_turns": self.total_turns,
            "has_more": self.has_more,
            "turns": [turn.to_dict() for turn in self.turns],
        }


@dataclass(frozen=True)
class SearchMatch:
    turn: TurnView
    score: float
    matched_terms: tuple

    def to_dict(self) -> dict:
        return {**self.turn.to_dict(), "score": self.score, "matched_terms": list(self.matched_terms)}


@dataclass(frozen=True)
class SearchResult:
    session_id: str
    query: str
    terms: tuple
    matches: tuple
    limit: int
    limit_clamped: bool
    total_matches: int
    scanned: int
    scan_truncated: bool
    scope: str = SCOPE_SESSION
    order: str = "relevance"

    @property
    def returned(self) -> int:
        return len(self.matches)

    @property
    def has_more(self) -> bool:
        return self.total_matches > self.returned

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "scope": self.scope,
            "query": self.query,
            "terms": list(self.terms),
            "order": self.order,
            "limit": self.limit,
            "limit_clamped": self.limit_clamped,
            "returned": self.returned,
            "total_matches": self.total_matches,
            "has_more": self.has_more,
            "scanned": self.scanned,
            "scan_truncated": self.scan_truncated,
            "matches": [match.to_dict() for match in self.matches],
        }


@dataclass(frozen=True)
class SummaryResult:
    session_id: str
    title: str
    method: str
    total_turns: int
    user_turns: int
    assistant_turns: int
    first_turn_at: Optional[float]
    last_turn_at: Optional[float]
    opening_request: Optional[TurnView]
    latest_user_request: Optional[TurnView]
    latest_assistant_reply: Optional[TurnView]
    keywords: tuple                      # ((term, count), ...)
    excerpts: tuple                      # TurnView kronologis (jendela `limit` giliran terakhir)
    window: int
    window_clamped: bool
    digest: str

    def to_dict(self) -> dict:
        def one(turn):
            return turn.to_dict() if turn is not None else None

        return {
            "session_id": self.session_id,
            "title": self.title,
            "method": self.method,
            "total_turns": self.total_turns,
            "user_turns": self.user_turns,
            "assistant_turns": self.assistant_turns,
            "first_turn_at": self.first_turn_at,
            "last_turn_at": self.last_turn_at,
            "opening_request": one(self.opening_request),
            "latest_user_request": one(self.latest_user_request),
            "latest_assistant_reply": one(self.latest_assistant_reply),
            "keywords": [{"term": term, "count": count} for term, count in self.keywords],
            "window": self.window,
            "window_clamped": self.window_clamped,
            "excerpts": [turn.to_dict() for turn in self.excerpts],
            "digest": self.digest,
        }


# ------------------------------------------------------------------ helper murni

def _clean_session_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestError("session_id wajib diisi (teks tidak kosong).")

    session_id = value.strip()

    if len(session_id) > MAX_SESSION_ID_CHARS:
        raise InvalidRequestError("session_id terlalu panjang.")

    return session_id


def _clean_limit(value: Any, default: int) -> tuple[int, bool]:
    """(limit_yang_dipakai, di-clamp?). None -> default; > MAX_LIMIT -> di-clamp."""
    if value is None:
        return default, False

    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRequestError("limit harus berupa bilangan bulat.")

    if value < 1:
        raise InvalidRequestError("limit harus >= 1.")

    if value > MAX_LIMIT:
        return MAX_LIMIT, True

    return value, False


def _window(text: str, width: int, terms: tuple = ()) -> tuple[str, bool]:
    """
    Potong `text` menjadi <= ~width karakter. Kalau ada `terms` dan salah
    satunya ditemukan, jendela dipusatkan di sekitar kemunculan pertama;
    kalau tidak, yang dipertahankan bagian awal.
    """
    if len(text) <= width:
        return text, False

    start = 0
    lowered = text.lower()

    # .lower() bisa mengubah panjang untuk beberapa aksara langka -> posisi
    # tidak bisa dipercaya, jatuh ke potongan awal.
    if terms and len(lowered) == len(text):
        found = [pos for pos in (lowered.find(term) for term in terms) if pos >= 0]
        if found:
            start = max(0, min(found) - width // 4)

    end = min(len(text), start + width)
    chunk = text[start:end]

    return ("…" if start > 0 else "") + chunk + ("…" if end < len(text) else ""), True


def _turn_view(row: sqlite3.Row, width: int = MAX_TURN_CHARS, terms: tuple = (), collapse: bool = False) -> TurnView:
    text = row["content"] or ""

    if collapse:
        text = " ".join(text.split())

    content, truncated = _window(text, width, terms)

    return TurnView(
        id=int(row["id"]), role=str(row["role"]), content=content,
        created_at=float(row["created_at"]), truncated=truncated,
    )


def _query_terms(query: Any) -> tuple[tuple, str]:
    """(terms, query_normal). Raise InvalidRequestError kalau tidak ada yang bisa dicari."""
    if not isinstance(query, str):
        raise InvalidRequestError("query harus berupa teks.")

    collapsed = " ".join(query.split())

    if not collapsed:
        raise InvalidRequestError("query tidak boleh kosong.")

    collapsed = collapsed[:MAX_QUERY_CHARS]
    folded = collapsed.casefold()

    unique = list(dict.fromkeys(_WORD_RE.findall(folded)))
    long_enough = [term for term in unique if len(term) >= MIN_TERM_CHARS]

    # Query yang seluruhnya kata pendek (mis. "r") tetap dicari apa adanya.
    terms = tuple((long_enough or unique)[:MAX_QUERY_TERMS])

    if not terms:
        raise InvalidRequestError("query tidak mengandung kata yang bisa dicari.")

    return terms, folded


def _keywords(texts) -> tuple:
    counter: Counter = Counter()

    for text in texts:
        for token in _WORD_RE.findall(text.casefold()):
            if len(token) >= KEYWORD_MIN_CHARS and not token.isdigit() and token not in _STOPWORDS:
                counter[token] += 1

    ranked = sorted(
        ((term, count) for term, count in counter.items() if count >= KEYWORD_MIN_COUNT),
        key=lambda item: (-item[1], item[0]),          # deterministik
    )

    return tuple(ranked[:SUMMARY_KEYWORDS])


def _digest(title, total, users, assistants, opening, latest_user, latest_assistant, keywords) -> str:
    if total == 0:
        return f"Sesi '{title}' belum punya giliran percakapan."

    lines = [f"Sesi '{title}': {total} giliran ({users} user, {assistants} assistant)."]

    if opening is not None:
        lines.append(f"Permintaan pertama user: {opening.content}")

    if latest_user is not None and (opening is None or latest_user.id != opening.id):
        lines.append(f"Permintaan user terakhir: {latest_user.content}")

    if latest_assistant is not None:
        lines.append(f"Jawaban assistant terakhir: {latest_assistant.content}")

    if keywords:
        lines.append("Kata yang sering muncul: " + ", ".join(f"{term} ({count})" for term, count in keywords) + ".")

    return "\n".join(lines)


# ------------------------------------------------------------------ koneksi

def _default_connect() -> sqlite3.Connection:
    """
    Pakai satu-satunya pintu koneksi milik core/chat_sessions.py. Diimpor lazy
    (impor chat_sessions menjalankan init_db()) dan dibaca saat dipanggil, jadi
    patch DB_FILE (mis. di test) otomatis ikut. Belum ada API baca "ramping"
    di chat_sessions (get_turns() menarik steps_json + interaction_schema_json
    semua giliran) - karena itu query baca di modul ini sengaja sempit.
    """
    from core import chat_sessions

    return chat_sessions._connect()


# ------------------------------------------------------------------ layanan

class ConversationContext:
    """
    Semua method mengembalikan dataclass hasil (punya .to_dict() JSON-safe) atau
    melempar ConversationContextError (InvalidRequestError / SessionNotFoundError).
    Error tak terduga dari SQLite dilempar apa adanya.
    """

    def __init__(self, connect: Optional[Callable[[], sqlite3.Connection]] = None):
        self._connect = connect or _default_connect

    # ------------------------------------------------------------ infra

    def _open(self) -> sqlite3.Connection:
        conn = self._connect()

        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")        # tulis ditolak SQLite
            if not conn.in_transaction:
                conn.execute("BEGIN")                     # satu snapshot baca
        except Exception:
            conn.close()
            raise

        return conn

    @staticmethod
    def _require_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT id, title FROM chat_sessions WHERE id = ?", (session_id,),
        ).fetchone()

        if row is None:
            raise SessionNotFoundError(f"Sesi '{session_id}' tidak ditemukan.")

        return row

    @staticmethod
    def _last_turns(conn: sqlite3.Connection, session_id: str, count: int) -> list:
        """`count` giliran terbaru, dikembalikan KRONOLOGIS (lama -> baru)."""
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM chat_turns "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, count),
        ).fetchall()

        return list(reversed(rows))

    # ------------------------------------------------------------ recent

    def recent(self, session_id: Any, limit: Any = DEFAULT_RECENT_LIMIT) -> RecentResult:
        """Giliran terbaru sesi ini, urut kronologis (lama -> baru), diurutkan berdasar id."""
        sid = _clean_session_id(session_id)
        applied, clamped = _clean_limit(limit, DEFAULT_RECENT_LIMIT)

        with closing(self._open()) as conn:
            self._require_session(conn, sid)
            rows = self._last_turns(conn, sid, applied)
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM chat_turns WHERE session_id = ?", (sid,),
            ).fetchone()["c"]

        return RecentResult(
            session_id=sid,
            turns=tuple(_turn_view(row) for row in rows),
            limit=applied, limit_clamped=clamped, total_turns=int(total),
        )

    # ------------------------------------------------------------ search

    def search(
        self,
        session_id: Any,
        query: Any,
        limit: Any = DEFAULT_SEARCH_LIMIT,
        *,
        scope: str = SCOPE_SESSION,
    ) -> SearchResult:
        """
        Pencarian kata kunci deterministik (tanpa LLM) pada SATU sesi.

        - Query dipecah jadi kata (casefold, unik, maks MAX_QUERY_TERMS). Giliran
          cocok kalau memuat >= 1 kata sebagai substring (tidak peka huruf besar/kecil,
          Unicode-aware).
        - Skor = (kata cocok / jumlah kata) + PHRASE_BONUS kalau seluruh query
          muncul berurutan (hanya untuk query > 1 kata). Urut: skor menurun,
          seri -> giliran lebih baru dulu.
        - Hanya SEARCH_SCAN_LIMIT giliran terbaru yang dipindai (scan_truncated
          memberi tahu kalau ada yang tidak terjangkau).
        - `scope`: kontrak dibuat extensible; saat ini hanya "session". Pencarian
          lintas sesi sengaja belum ada karena repo belum punya konsep pemilik
          sesi/otorisasi.
        """
        sid = _clean_session_id(session_id)

        if scope not in SUPPORTED_SCOPES:
            raise InvalidRequestError(
                f"scope '{scope}' belum didukung. Yang didukung: {', '.join(SUPPORTED_SCOPES)}."
            )

        terms, folded_query = _query_terms(query)
        applied, clamped = _clean_limit(limit, DEFAULT_SEARCH_LIMIT)
        scan_limit = SEARCH_SCAN_LIMIT

        with closing(self._open()) as conn:
            self._require_session(conn, sid)
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM chat_turns "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (sid, scan_limit + 1),
            ).fetchall()

        scan_truncated = len(rows) > scan_limit
        rows = rows[:scan_limit]

        scored = []

        for row in rows:
            folded = " ".join((row["content"] or "").casefold().split())
            hit = tuple(term for term in terms if term in folded)

            if not hit:
                continue

            score = len(hit) / len(terms)

            if len(terms) > 1 and folded_query in folded:
                score += PHRASE_BONUS

            scored.append((round(score, 3), int(row["id"]), row, hit))

        scored.sort(key=lambda item: (-item[0], -item[1]))       # skor desc, lalu terbaru

        matches = tuple(
            SearchMatch(turn=_turn_view(row, terms=hit), score=score, matched_terms=hit)
            for score, _, row, hit in scored[:applied]
        )

        return SearchResult(
            session_id=sid, query=folded_query, terms=terms, matches=matches,
            limit=applied, limit_clamped=clamped, total_matches=len(scored),
            scanned=len(rows), scan_truncated=scan_truncated, scope=scope,
        )

    # ------------------------------------------------------------ summary

    def summary(self, session_id: Any, limit: Any = DEFAULT_SUMMARY_LIMIT) -> SummaryResult:
        """
        Ringkasan EKSTRAKTIF deterministik (bukan LLM). Statistik dihitung atas
        seluruh sesi lewat agregat SQL; kutipan + kata berulang dihitung atas
        jendela `limit` giliran terakhir. Kata berulang = kata (>= 3 huruf, bukan
        stopword) yang muncul >= 2 kali di jendela itu.
        """
        sid = _clean_session_id(session_id)
        applied, clamped = _clean_limit(limit, DEFAULT_SUMMARY_LIMIT)

        with closing(self._open()) as conn:
            session = self._require_session(conn, sid)

            stats = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(role = 'user'), 0) AS users, "
                "COALESCE(SUM(role = 'assistant'), 0) AS assistants, "
                "MIN(created_at) AS first_at, MAX(created_at) AS last_at "
                "FROM chat_turns WHERE session_id = ?",
                (sid,),
            ).fetchone()

            def edge(role: str, direction: str):
                return conn.execute(
                    "SELECT id, role, content, created_at FROM chat_turns "
                    f"WHERE session_id = ? AND role = ? ORDER BY id {direction} LIMIT 1",
                    (sid, role),
                ).fetchone()

            opening_row = edge("user", "ASC")
            latest_user_row = edge("user", "DESC")
            latest_assistant_row = edge("assistant", "DESC")
            window_rows = self._last_turns(conn, sid, applied)

        def item(row):
            return _turn_view(row, SUMMARY_ITEM_CHARS, collapse=True) if row is not None else None

        opening, latest_user, latest_assistant = item(opening_row), item(latest_user_row), item(latest_assistant_row)
        excerpts = tuple(_turn_view(row, SUMMARY_ITEM_CHARS, collapse=True) for row in window_rows)
        keywords = _keywords(row["content"] or "" for row in window_rows)

        total, users, assistants = int(stats["total"]), int(stats["users"]), int(stats["assistants"])
        title = str(session["title"])

        return SummaryResult(
            session_id=sid, title=title, method=METHOD_EXTRACTIVE,
            total_turns=total, user_turns=users, assistant_turns=assistants,
            first_turn_at=stats["first_at"], last_turn_at=stats["last_at"],
            opening_request=opening, latest_user_request=latest_user,
            latest_assistant_reply=latest_assistant,
            keywords=keywords, excerpts=excerpts,
            window=applied, window_clamped=clamped,
            digest=_digest(title, total, users, assistants, opening, latest_user, latest_assistant, keywords),
        )


# ------------------------------------------------------------------ singleton

_singleton: Optional[ConversationContext] = None
_singleton_lock = threading.Lock()


def get_conversation_context() -> ConversationContext:
    """Instance global (lazy). Tidak membuka koneksi sampai method dipanggil."""
    global _singleton

    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ConversationContext()

    return _singleton