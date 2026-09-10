"""
agents/rei/auto_extract.py — ekstraksi memori otomatis di background.

FIX (Phase 0 Stabilization):
Sebelumnya, kalau call_model() untuk giliran utama balas
EMPTY_RESPONSE_MARKER (provider rate-limited/kosong), teks marker itu
tetap dikirim ke sini sebagai "assistant_answer" dan modul ini mencoba
mem-parsing-nya sebagai JSON - selalu gagal dan menghasilkan noise di
log ("Gagal parse JSON: ..."), plus membuang satu API call ekstra ke
provider untuk sesuatu yang sudah pasti tidak akan menghasilkan fakta.

Fix: deteksi EMPTY_RESPONSE_MARKER lebih awal dan skip ekstraksi sama
sekali kalau assistant_answer adalah marker itu.
"""

import json
import threading
import logging

from agents.rei.provider_client import call_model, EMPTY_RESPONSE_MARKER
from core.memory import remember_fact

logger = logging.getLogger("aira.rei.auto_extract")

EXTRACTION_PROMPT = """
Kamu adalah modul ekstraksi memori untuk AIRA.

Tugasmu HANYA membaca satu potongan percakapan (user + jawaban
assistant) dan memutuskan apakah ada fakta yang layak diingat
lintas sesi, TANPA user perlu memintanya secara eksplisit.

Fakta yang layak diingat: nama panggilan, preferensi gaya jawab,
threshold monitoring, konfigurasi/standar perangkat, instruksi
standing, info personal relevan tentang user/project-nya.

Fakta yang TIDAK layak diingat: basa-basi/sapaan, data observasi
sesaat (hasil ping/resource SAAT INI), pertanyaan umum tanpa
preferensi/instruksi baru.

Balas HANYA JSON array valid, tanpa teks lain, tanpa markdown code
fence. Format tiap item: {"key": "slug_singkat", "value": "isi fakta"}
Kalau tidak ada yang layak disimpan, balas persis: []
"""


def _extract(user_input, assistant_answer):
    # FIX: skip lebih awal kalau jawaban assistant adalah marker retry,
    # bukan jawaban asli - tidak ada fakta yang bisa diekstraksi dari
    # pesan error/placeholder ini.
    if not assistant_answer or assistant_answer.strip() == EMPTY_RESPONSE_MARKER:
        logger.debug("auto_memory: dilewati, assistant_answer adalah EMPTY_RESPONSE_MARKER.")
        return []

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"User: {user_input}\nAssistant: {assistant_answer}"},
    ]

    response = call_model(messages, tools=[])

    if "error" in response:
        logger.error("auto_memory gagal: %s", response["error"])
        return []

    content = response.get("message", {}).get("content", "")

    # FIX: jaga-jaga kalau giliran ekstraksi INI SENDIRI kena rate-limit
    # dan balas marker juga - jangan dianggap gagal parse, cukup skip.
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
        logger.error("auto_memory gagal parse JSON: %r", content)
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
        logger.info("AUTO MEMORY tersimpan otomatis: %s", saved)

    return saved


def extract_and_save_facts_async(user_input, assistant_answer):
    def _safe_run():
        try:
            _extract(user_input, assistant_answer)
        except Exception:
            logger.exception("auto_memory_thread error")

    threading.Thread(target=_safe_run, daemon=True).start()