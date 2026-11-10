"""
agents/rei/auto_extract.py — ekstraksi memori otomatis di background.

Mendukung:
- Ekstraksi memori akun global terisolasi per user (UserMemoryService)
- Ekstraksi kandidat identitas pengguna (nama, panggilan, preferensi komunikasi)
- Parser JSON tangguh (resilient JSON parsing) dengan pemulihan otomatis
- Prompt ekstraksi selektif & peka hanya untuk informasi berharga jangka panjang
- Fallback unisolated legacy memory (remember_fact) untuk mode CLI / unauthenticated
"""

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

from agents.rei.provider_client import call_model, EMPTY_RESPONSE_MARKER
from core.memory import remember_fact

logger = logging.getLogger("aira.rei.auto_extract")

EXTRACTION_PROMPT = """
Kamu adalah modul ekstraksi memori jangka panjang cerdas dan selektif untuk AIRA OS.

Tugasmu: Analisis percakapan (User + Jawaban Assistant) dan putuskan fakta apa yang BERNILAI TINGGI dan RELEVAN untuk diingat lintas sesi tanpa diminta secara eksplisit.

PRINSIP KEPEKAAN DATA (SANGAT KETAT & SELEKTIF):
1. SIMPAN HANYA FAKTA PENTING JANGKA PANJANG (High-Value Facts):
   - Identitas & Sapaan: Nama lengkap, nama panggilan/sapaan akrab, peran/profesi pengguna.
   - Preferensi Kerja & Standar Teknis: Format jawaban yang disukai (step-by-step, to the point), versi OS jaringan (RouterOS v7, Cisco IOS-XE), kewajiban rollback plan, konvensi penamaan interface/VLAN.
   - Topologi & Infrastruktur Jaringan: Model router/switch utama (CCR2004, CRS326), nomor AS (ASN BGP), subnet kritis, alokasi IP gateway/DNS/NMS, segmen VLAN kantor/datacenter.
   - Proyek & Batasan Operasional: Proyek aktif, larangan maintenance window pada jam kerja, penugasan teknis.

2. JANGAN PERNAH SIMPAN HAL REMEH / SESAMBINGAN (Zero Junk / Ephemeral):
   - JANGAN simpan basa-basi, salam, atau ekspresi santai ("halo", "selamat pagi", "lagi santai", "terima kasih", "ok mantap").
   - JANGAN simpan metrik atau observasi sesaat (hasil ping sekarang, CPU load saat ini, status link detik ini).
   - JANGAN simpan pertanyaan umum/edukasi tanpa fakta spesifik ("apa itu BGP?", "jelaskan cara kerja OSPF").
   - JANGAN simpan jawaban panjang assistant sebagai fakta pengguna.

3. KATEGORI YANG VALID:
   - "profile": identitas, nama lengkap, panggilan, peran.
   - "preferences": preferensi teknis, format jawaban, standar kerja.
   - "technical": arsitektur jaringan, versi OS perangkat, model router, ASN, VLAN.
   - "project": nama proyek, batasan arsitektur, deadline/window.
   - "facts": IP penting, domain, kredensial peran non-rahasia.

Format Keluaran:
Balas HANYA JSON array valid tanpa teks pengantar dan tanpa markdown code fence. Jika tidak ada fakta penting baru, balas persis: []
Format tiap elemen:
[
  {
    "category": "profile|preferences|technical|project|facts",
    "key": "slug_singkat",
    "value": "ringkasan fakta padat dan jelas",
    "importance": 0.8
  }
]
"""


def _parse_extracted_json(content: str) -> List[Dict[str, Any]]:
    """
    Robust JSON extractor for LLM responses.
    Handles markdown code blocks, trailing/leading malformed braces, and recovers individual objects.
    """
    if not content or not content.strip():
        return []

    text = content.strip()

    # 1. Strip markdown fences if present
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            text = m.group(1).strip()
        else:
            text = text.replace("```json", "").replace("```", "").strip()

    # 2. Fast path: standard json.loads
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            for k in ("memories", "facts", "items", "data"):
                if isinstance(data.get(k), list):
                    return [d for d in data[k] if isinstance(d, dict)]
            if "key" in data or "value" in data:
                return [data]
    except json.JSONDecodeError:
        pass

    # 3. Clean trailing or malformed braces like `[ ... ]}`
    bracket_match = re.search(r"\[([\s\S]*)\]", text)
    if bracket_match:
        candidate = bracket_match.group(0).strip()
        candidate = re.sub(r"[}\]\s]+$", "]", candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    # 4. Fallback: regex search for individual JSON objects
    results = []
    for obj_match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
        try:
            obj = json.loads(obj_match.group(0))
            if isinstance(obj, dict) and ("key" in obj or "value" in obj or "category" in obj):
                results.append(obj)
        except Exception:
            continue

    return results


def _extract(user_input: str, assistant_answer: str, user_id: Optional[str] = None):
    if not assistant_answer or assistant_answer.strip() == EMPTY_RESPONSE_MARKER:
        logger.debug("auto_memory: dilewati, assistant_answer adalah EMPTY_RESPONSE_MARKER.")
        return []

    # 1. First run rule-based candidate extraction if user_id is provided
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
    try:
        from core.provider_health import get_provider_health_manager
        from core.model_router import get_model_router
        general_model = get_model_router().select_for_label("general", publish=False)
        if general_model and not get_provider_health_manager().is_provider_available(general_model.provider):
            logger.info("auto_memory: Provider '%s' circuit is OPEN, skipping background LLM extraction.", general_model.provider)
            return []
    except Exception:
        pass

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

    facts = _parse_extracted_json(content)
    if not facts:
        logger.debug("auto_memory: tidak ada fakta penting diekstrak dari respon LLM.")
        return []

    saved = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        key = fact.get("key")
        value = fact.get("value")
        category = fact.get("category", "general")
        importance = float(fact.get("importance", 0.75))

        if not key or not value:
            continue

        clean_key = str(key).strip().replace(" ", "_")
        clean_val = str(value).strip()

        if user_id:
            try:
                from core.tenant.memory_service import get_memory_service
                mem_svc = get_memory_service()
                mem_svc.save_memory(
                    user_id=user_id,
                    category=category,
                    content=f"{clean_key}: {clean_val}",
                    source="AUTO_EXTRACTED",
                    importance=importance,
                    metadata={"key": clean_key},
                )
                saved.append(clean_key)
            except Exception as e:
                logger.warning(f"auto_memory: error saving user memory: {e}")
        else:
            remember_fact(clean_key, clean_val)
            saved.append(clean_key)

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
