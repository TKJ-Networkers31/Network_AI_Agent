"""
core/log_store.py — SQLite-backed structured log store untuk AIRA.

Menyimpan setiap log event (bukan cuma teks ke file) ke tabel SQLite supaya
bisa di-query dengan filter (kategori, level, keyword, rentang waktu) dari
endpoint API dan ditampilkan di halaman "Logs" pada PWA.

TERPISAH dari core/memory.py (long_term_memory.db) - skema dan tujuan beda
(audit/observability runtime, bukan fakta yang diingat AI).
"""

import sqlite3
import time
import json
import threading
from pathlib import Path
from contextlib import closing
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "logs.db"

DATABASE_DIR.mkdir(exist_ok=True)

CATEGORY_INFO = {
    "system": {
        "label": "System",
        "description": "Event startup/shutdown AIRA: setup logging, boot server, konfigurasi awal.",
        "triggered_by": "Dipanggil sekali saat api/main.py atau run_chat.py pertama kali start.",
    },
    "api": {
        "label": "API / HTTP",
        "description": "Request masuk dan keluar lewat endpoint FastAPI (chat, devices, sessions, dll).",
        "triggered_by": "Setiap kali frontend PWA memanggil endpoint /api/*.",
    },
    "brain": {
        "label": "Brain",
        "description": "Titik masuk tunggal AIRA memproses pesan user sebelum diteruskan ke orchestrator.",
        "triggered_by": "Setiap pesan chat baru dari user (core/brain.py::think()).",
    },
    "orchestrator": {
        "label": "Orchestrator",
        "description": "Routing permintaan ke agent internal (AKANE/REI/HIKARI) dan eksekusi tool yang dipilih.",
        "triggered_by": "Setiap kali planner memutuskan tool apa yang harus dijalankan.",
    },
    "planner": {
        "label": "Planner (REI)",
        "description": "Alur reasoning: kirim pesan ke LLM, baca tool_calls, ulangi sampai jawaban final.",
        "triggered_by": "Tiap giliran percakapan - mencatat retry provider kosong, batas tool call, dsb.",
    },
    "llm": {
        "label": "LLM Request/Response",
        "description": "Isi lengkap request & response mentah ke model (Ollama/OpenRouter), termasuk token usage.",
        "triggered_by": "Setiap kali call_model() dipanggil ke provider LLM aktif.",
    },
    "provider_client": {
        "label": "Provider Client",
        "description": "Koneksi ke provider LLM: pilih provider, error koneksi, error format JSON dari provider.",
        "triggered_by": "Kegagalan/keberhasilan komunikasi HTTP ke Ollama atau OpenRouter.",
    },
    "tool": {
        "label": "Tool Execution",
        "description": "Eksekusi generik sebuah tool (nama, argumen, hasil sukses/gagal, durasi).",
        "triggered_by": "Setiap tool_call yang dijalankan LLM lewat orchestrator._execute_tool().",
    },
    "ssh": {
        "label": "SSH (AKANE)",
        "description": "Koneksi & eksekusi perintah SSH ke perangkat MikroTik (connect, retry, command output).",
        "triggered_by": "Tool network yang butuh SSH: get_interfaces, get_routes, get_resources, dsb.",
    },
    "snmp": {
        "label": "SNMP (AKANE)",
        "description": "Query SNMP ke perangkat (system info, traffic interface) beserta OID dan hasil walk/get.",
        "triggered_by": "Tool snmp_get_system_info dan snmp_get_interface_traffic.",
    },
    "mikrotik": {
        "label": "MikroTik RouterOS",
        "description": "Perintah RouterOS spesifik yang dikirim lewat SSH (mis. /interface print).",
        "triggered_by": "Semua tool get_* yang menyentuh konfigurasi MikroTik.",
    },
    "network": {
        "label": "Network Diagnostics",
        "description": "Ping, traceroute, nslookup - hasil mentah command line beserta exit code.",
        "triggered_by": "Tool ping/traceroute/nslookup dari AKANE.",
    },
    "web": {
        "label": "Web Search/Fetch (REI)",
        "description": "Pencarian internet (web_search) dan pengambilan konten halaman (web_fetch).",
        "triggered_by": "LLM memanggil tool web_search atau web_fetch untuk info terkini.",
    },
    "vision": {
        "label": "Vision (HIKARI)",
        "description": "Loading model YOLO, hasil deteksi objek dari webcam, path snapshot.",
        "triggered_by": "Tool detect_objects/recognize_object atau fusion suara+visual otomatis.",
    },
    "voice": {
        "label": "Voice (YUKI)",
        "description": "Status mic listener, hasil transkripsi STT, status TTS bicara.",
        "triggered_by": "Mode suara aktif: mulai/berhenti dengar, tiap utterance yang ditranskrip.",
    },
    "memory": {
        "label": "Long-term Memory",
        "description": "Operasi simpan/hapus/cari fakta permanen (remember/recall/forget) di database.",
        "triggered_by": "Tool remember/recall/forget, atau auto-extract yang menyimpan fakta baru.",
    },
    "auto_extract": {
        "label": "Auto Memory Extraction",
        "description": "Proses background yang membaca tiap giliran chat dan memutuskan ada fakta baru untuk diingat.",
        "triggered_by": "Berjalan otomatis di thread terpisah setelah SETIAP jawaban assistant selesai.",
    },
    "session": {
        "label": "Chat Session",
        "description": "Pembuatan, rename, hapus, dan penyimpanan riwayat percakapan (chat_sessions.db).",
        "triggered_by": "User membuat chat baru, mengganti judul, atau menghapus sesi dari sidebar.",
    },
}

KNOWN_CATEGORIES = list(CATEGORY_INFO.keys())

_write_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                logger_name TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT,
                duration_ms REAL,
                success INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at)")
        conn.commit()


init_db()


def insert_log(
    category: str,
    level: str,
    logger_name: str,
    message: str,
    context: Optional[dict] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    created_at: Optional[float] = None,
) -> None:
    now = created_at if created_at is not None else time.time()

    context_json = None
    if context is not None:
        try:
            context_json = json.dumps(context, ensure_ascii=False, default=str)
        except Exception:
            context_json = json.dumps({"_unserializable": str(context)})

    success_val = None if success is None else (1 if success else 0)

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute(
                "INSERT INTO logs "
                "(created_at, category, level, logger_name, message, context, duration_ms, success) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, category, level, logger_name, message, context_json, duration_ms, success_val),
            )
            conn.commit()


def query_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if level and level != "all":
        conditions.append("level = ?")
        params.append(level.upper())

    if search:
        conditions.append("(message LIKE ? OR context LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    if until is not None:
        conditions.append("created_at <= ?")
        params.append(until)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM logs {where} ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        if item.get("context"):
            try:
                item["context"] = json.loads(item["context"])
            except (json.JSONDecodeError, TypeError):
                pass
        item["success"] = None if item.get("success") is None else bool(item["success"])
        results.append(item)

    return results


def count_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> int:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if level and level != "all":
        conditions.append("level = ?")
        params.append(level.upper())

    if search:
        conditions.append("(message LIKE ? OR context LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    if until is not None:
        conditions.append("created_at <= ?")
        params.append(until)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT COUNT(*) as total FROM logs {where}", params).fetchone()

    return row["total"] if row else 0


def get_categories_with_counts() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM logs GROUP BY category ORDER BY count DESC"
        ).fetchall()

    found = {row["category"]: row["count"] for row in rows}

    categories = []
    for cat in KNOWN_CATEGORIES:
        info = CATEGORY_INFO.get(cat, {})
        categories.append({
            "category": cat,
            "count": found.pop(cat, 0),
            "label": info.get("label", cat),
            "description": info.get("description", ""),
            "triggered_by": info.get("triggered_by", ""),
        })

    for cat, count in found.items():
        categories.append({
            "category": cat, "count": count, "label": cat,
            "description": "", "triggered_by": "",
        })

    return categories


def get_stats(since: Optional[float] = None) -> dict:
    conditions = []
    params: list[Any] = []

    if since is not None:
        conditions.append("created_at >= ?")
        params.append(since)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT level, COUNT(*) as count FROM logs {where} GROUP BY level", params
        ).fetchall()

    return {row["level"]: row["count"] for row in rows}


def clear_logs(category: Optional[str] = None, older_than: Optional[float] = None) -> int:
    conditions = []
    params: list[Any] = []

    if category and category != "all":
        conditions.append("category = ?")
        params.append(category)

    if older_than is not None:
        conditions.append("created_at < ?")
        params.append(older_than)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with _write_lock:
        with closing(_connect()) as conn:
            cursor = conn.execute(f"DELETE FROM logs {where}", params)
            conn.commit()
            return cursor.rowcount