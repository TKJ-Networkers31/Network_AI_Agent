"""
agents/rei/auto_extract.py — ekstraksi memori otomatis di background.

Mendukung:
- Ekstraksi memori akun global terisolasi per user (UserMemoryService)
- Ekstraksi kandidat identitas pengguna (nama, panggilan, preferensi komunikasi)
- Fallback unisolated legacy memory (remember_fact) untuk mode CLI / unauthenticated
"""

import json
import threading
import logging
from typing import Optional

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
fence. Format tiap item: {"category": "profile|preferences|technical|project|facts|workflows", "key": "slug_singkat", "value": "isi fakta"}
Kalau tidak ada yang layak disimpan, balas persis: []
"""


def _extract(user_input: str, assistant_answer: str, user_id: Optional[str] = None):
    if not assistant_answer or assistant_answer.strip() == EMPTY_RESPONSE_MARKER:
        logger.debug("auto_memory: dilewati, assistant_answer adalah EMPTY_RESPONSE_MARKER.")
        return []

    # 1. First run rule-based candidates extraction if user_id is provided
    if user_id:
        try:
            from core.tenant.memory_service import get_memory_service
            mem_svc = get_memory_service()
            rule_saved = mem_svc.extract_memory_candidates(user_input, assistant_answer, user_id=user_id)
            if rule_saved:
                logger.info(f"auto_memory: {len(rule_saved)} kandidat identitas/aturan tersimpan untuk {user_id}")
        except Exception as e:
            logger.warning(f"auto_memory: rule candidate extraction error: {e}")

    # 2. LLM-based fact extraction for deeper context
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"User: {user_input}\nAssistant: {assistant_answer}"},
    ]

    response = call_model(messages, tools=[])

    if "error" in response:
        logger.error("auto_memory gagal: %s", response["error"])
        return []

    content = response.get("message", {}).get("content", "")

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
        category = fact.get("category", "general")
        if not key or not value:
            continue

        if user_id:
            try:
                from core.tenant.memory_service import get_memory_service
                mem_svc = get_memory_service()
                mem_svc.save_memory(
                    user_id=user_id,
                    category=category,
                    content=f"{key}: {value}",
                    source="AUTO_EXTRACTED",
                    importance=0.7,
                )
                saved.append(key)
            except Exception as e:
                logger.warning(f"auto_memory: error saving user memory: {e}")
        else:
            remember_fact(key, value)
            saved.append(key)

    if saved:
        logger.info("AUTO MEMORY tersimpan otomatis: %s", saved)

    return saved


def extract_and_save_facts_async(user_input: str, assistant_answer: str, user_id: Optional[str] = None):
    # Capture current user_id from context if not passed
    if not user_id:
        try:
            from core.events import current_event_context
            user_id = current_event_context().get("user_id")
        except Exception:
            user_id = None

    def _safe_run():
        try:
            _extract(user_input, assistant_answer, user_id=user_id)
        except Exception:
            logger.exception("auto_memory_thread error")

    threading.Thread(target=_safe_run, daemon=True).start()
