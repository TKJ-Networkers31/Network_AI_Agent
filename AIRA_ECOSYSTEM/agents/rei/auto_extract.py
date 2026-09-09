"""
agents/rei/auto_extract.py — ekstraksi memori otomatis di background,
port dari agent/memory_store/auto_extract.py.
"""

import json
import threading
import logging

from agents.rei.provider_client import call_model
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
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"User: {user_input}\nAssistant: {assistant_answer}"},
    ]

    response = call_model(messages, tools=[])

    if "error" in response:
        logger.error("auto_memory gagal: %s", response["error"])
        return []

    content = response.get("message", {}).get("content", "")
    if not content:
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
