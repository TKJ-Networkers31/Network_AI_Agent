"""
agent/memory_store/auto_extract.py

FIX (Phase 0 Stabilization) - sama seperti versi AIRA_ECOSYSTEM
(agents/rei/auto_extract.py): skip ekstraksi kalau assistant_answer
adalah EMPTY_RESPONSE_MARKER, supaya tidak buang API call + tidak
spam log "Gagal parse JSON" tiap kali provider rate-limited.

Dipertahankan untuk kompatibilitas selama masa transisi migrasi ke
AIRA_ECOSYSTEM - lihat MIGRATION_PLAN.md Tahap 5.
"""

import json
import threading

from agent.core.providers import call_model, EMPTY_RESPONSE_MARKER
from agent.memory_store.long_term import remember_fact
from agent.core.logger import log_error, logger


EXTRACTION_PROMPT = """
Kamu adalah modul ekstraksi memori untuk Network AI Agent.

Tugasmu HANYA membaca satu potongan percakapan (user + jawaban
assistant) dan memutuskan apakah ada fakta yang layak diingat
lintas sesi, TANPA user perlu memintanya secara eksplisit.

Fakta yang layak diingat, contoh:
- Nama panggilan yang diminta user untuk kamu pakai
- Preferensi cara menjawab (gaya, format, bahasa)
- Threshold/batas monitoring (CPU, memory, dsb)
- Konfigurasi/standar perangkat yang disebut user
- Instruksi standing ("selalu lakukan X ke depannya")
- Info personal relevan yang disebutkan user tentang dirinya/projectnya

Fakta yang TIDAK layak diingat:
- Basa-basi, sapaan
- Data observasi sesaat (hasil ping/resource SAAT INI - itu
  berubah-ubah, jangan disimpan sebagai fakta permanen)
- Pertanyaan umum tanpa preferensi/instruksi baru

Balas HANYA JSON array valid, tanpa teks lain, tanpa markdown
code fence. Format tiap item:
{"key": "slug_singkat_huruf_kecil", "value": "isi fakta singkat"}

Kalau tidak ada yang layak disimpan, balas persis: []
"""


def _extract(user_input, assistant_answer):

    # FIX: skip lebih awal kalau jawaban assistant hanyalah marker
    # retry provider, bukan jawaban asli.
    if not assistant_answer or assistant_answer.strip() == EMPTY_RESPONSE_MARKER:
        return []

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {
            "role": "user",
            "content": f"User: {user_input}\nAssistant: {assistant_answer}"
        }
    ]

    response = call_model(messages, tools=[])

    if "error" in response:
        log_error("auto_memory", response["error"])
        return []

    content = response.get("message", {}).get("content", "")

    # FIX: kalau giliran ekstraksi ini sendiri kena rate-limit dan
    # balas marker, jangan dianggap gagal parse - cukup skip.
    if not content or content.strip() == EMPTY_RESPONSE_MARKER:
        return []

    content = content.strip()

    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        facts = json.loads(content)
    except json.JSONDecodeError:
        log_error("auto_memory", f"Gagal parse JSON: {content!r}")
        return []

    if not isinstance(facts, list):
        return []

    saved = []

    for fact in facts:

        if not isinstance(fact, dict):
            continue

        key = fact.get("key")
        value = fact.get("value")

        if not key or not value:
            continue

        remember_fact(key, value)
        saved.append(key)

    if saved:
        logger.info(f"AUTO MEMORY | tersimpan otomatis: {saved}")

    return saved


def extract_and_save_facts_async(user_input, assistant_answer):
    """
    Dipanggil setelah jawaban final dikirim ke user. Jalan di
    background thread supaya tidak menambah latensi respons
    (penting karena inference CPU-only/model gratis sudah lambat).

    Sengaja tidak melempar exception ke pemanggil — kegagalan di
    sini tidak boleh mengganggu alur percakapan utama.
    """

    def _safe_run():
        try:
            _extract(user_input, assistant_answer)
        except Exception as exc:
            log_error("auto_memory_thread", exc)

    threading.Thread(
        target=_safe_run,
        daemon=True
    ).start()