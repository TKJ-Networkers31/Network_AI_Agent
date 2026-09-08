import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from agent.memory_store.long_term import remember_fact, recall_facts
from agent.core.logger import log_error, log_llm_request, log_llm_response


BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


# ============================================================
# DAFTAR PROVIDER
#
# "type": "ollama"  -> model lokal via Ollama
# "type": "openai"  -> API eksternal apa pun yang kompatibel
#                       format OpenAI (OpenAI, Groq, OpenRouter,
#                       Together, DeepSeek, Mistral, dsb).
#
# PENTING: "type" di sini HARUS persis "ollama" atau "openai",
# karena call_model() di bawah mencocokkan string ini secara
# exact match untuk memilih handler yang dipakai.
# ============================================================

PROVIDERS = {

    "ollama-qwen3-4b": {
        "label": "Ollama - qwen3:4b (lokal)",
        "type": "ollama",
        "model": "qwen3:4b",
        "url": "http://localhost:11434/api/chat",
    },

    "ollama-qwen3-1.7b": {
        "label": "Ollama - qwen3:1.7b (lokal, lebih ringan)",
        "type": "ollama",
        "model": "qwen3:1.7b",
        "url": "http://localhost:11434/api/chat",
    },

    "Nemotron 3.5 Lightning": {
        "label": "Open Router: Nemotron 3.5 Lightning",
        "type": "openai",
        "model": "nvidia/nemotron-3.5-lightning:free",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API",
    },

    "Nemotron 3 Super": {
        "label": "Open Router: Nemotron 3 Super",
        "type": "openai",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API",
    },

}

# Model paling pas untuk hardware X270 (i7-7500U, 8GB RAM,
# CPU-only) berdasarkan hasil audit performa sebelumnya.
DEFAULT_PROVIDER_KEY = "ollama-qwen3-1.7b"
ACTIVE_MODEL_FACT_KEY = "active_model_provider"

# Dipakai _normalize_message() untuk menandai respons kosong/rusak
# dari provider, dan dicek ulang oleh engine.py untuk memutuskan
# apakah perlu retry otomatis. Disatukan di sini (bukan string
# literal terpisah di 2 file) supaya tidak ada typo/ketidaksamaan
# antara yang di-set dan yang dicek.
EMPTY_RESPONSE_MARKER = (
    "(Provider mengembalikan respons kosong atau tidak valid. "
    "Kemungkinan model sedang rate-limited/bermasalah — "
    "coba lagi atau ganti model dengan mengetik 'model'.)"
)


def list_providers():
    return PROVIDERS


def get_active_provider_key():
    """
    Provider aktif disimpan di long-term memory (tabel facts),
    jadi pilihan model kamu ikut nyantol lintas sesi juga.
    """

    facts = recall_facts(ACTIVE_MODEL_FACT_KEY, limit=1)

    for fact in facts:
        if (
            fact["key"] == ACTIVE_MODEL_FACT_KEY
            and fact["value"] in PROVIDERS
        ):
            return fact["value"]

    return DEFAULT_PROVIDER_KEY


def set_active_provider_key(key):

    if key not in PROVIDERS:

        return {
            "success": False,
            "error": f"Provider '{key}' tidak ditemukan."
        }

    remember_fact(ACTIVE_MODEL_FACT_KEY, key)

    return {
        "success": True,
        "key": key,
        "label": PROVIDERS[key]["label"]
    }


def get_active_provider():

    key = get_active_provider_key()

    return key, PROVIDERS[key]


def call_model(messages, tools):
    """
    Memanggil provider yang sedang aktif. Selalu mengembalikan
    bentuk seragam {"message": {...}, "usage": {...}|None} atau
    {"error": "..."} supaya agent/core/engine.py tidak perlu tahu
    bedanya provider.
    """

    key, config = get_active_provider()

    log_llm_request(
        f"{key} ({config['model']})",
        messages
    )

    if config["type"] == "ollama":
        result = _call_ollama(config, messages, tools)

    elif config["type"] == "openai":
        result = _call_openai_compatible(config, messages, tools)

    else:
        result = {
            "error": f"Tipe provider '{config['type']}' tidak dikenal."
        }

    log_llm_response(result)

    return result


def _normalize_message(message):
    """
    Memastikan message yang diterima dari provider selalu punya
    struktur minimal yang valid sebelum disimpan ke conversation
    history.

    Kenapa ini perlu: beberapa provider (terutama model gratis di
    OpenRouter) kadang membalas HTTP 200 OK tapi field 'message'-nya
    kosong/rusak (gak ada 'role', content null, tool_calls kosong)
    — biasanya karena rate limit atau error internal provider yang
    tidak dilaporkan sebagai HTTP error.

    Kalau dict rusak ini dibiarkan lolos dan disimpan ke history,
    request BERIKUTNYA ke provider manapun akan gagal dengan error
    semacam "missing field `role`", karena history yang dikirim
    ulang sudah mengandung entry tanpa role yang valid. Jadi
    normalisasi ini mencegah satu respons buruk meracuni seluruh
    sisa sesi.
    """

    if not isinstance(message, dict):
        message = {}

    if "role" not in message or not message.get("role"):
        message["role"] = "assistant"

    has_content = bool(message.get("content"))
    has_tool_calls = bool(message.get("tool_calls"))

    if not has_content and not has_tool_calls:
        message["content"] = EMPTY_RESPONSE_MARKER

    return message


def _extract_ollama_usage(data):
    """
    Ollama tidak punya field 'usage' seperti OpenAI, tapi
    melaporkan prompt_eval_count dan eval_count di root response.
    Disamakan bentuknya ke {"prompt_tokens", "completion_tokens",
    "total_tokens"} biar konsisten dipakai TokenTracker terlepas
    dari provider mana pun.
    """

    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")

    if prompt_tokens is None and completion_tokens is None:
        return None

    prompt_tokens = prompt_tokens or 0
    completion_tokens = completion_tokens or 0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _call_ollama(config, messages, tools):

    payload = {
        "model": config["model"],
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    try:

        response = requests.post(
            config["url"],
            json=payload,
            timeout=300
        )

        response.raise_for_status()

        data = response.json()

        message = _normalize_message(
            data.get("message", {})
        )

        return {
            "message": message,
            "usage": _extract_ollama_usage(data),
        }

    except requests.exceptions.RequestException as exc:

        log_error("call_ollama", exc)

        return {
            "error": (
                f"Tidak bisa menghubungi Ollama di "
                f"{config['url']}: {exc}"
            )
        }


def _call_openai_compatible(config, messages, tools):

    api_key = os.getenv(config["api_key_env"])

    if not api_key:

        return {
            "error": (
                f"{config['api_key_env']} belum diset di .env. "
                f"Tambahkan API key untuk provider ini dulu."
            )
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Network AI Agent",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
        "tools": tools,
    }

    url = f"{config['base_url']}/chat/completions"

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120
        )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}

        message = _normalize_message(
            choice.get("message") or {}
        )

        return {
            "message": message,
            "usage": data.get("usage"),
        }

    except requests.exceptions.RequestException as exc:

        detail = str(exc)

        if getattr(exc, "response", None) is not None:
            try:
                detail = f"{detail} | body: {exc.response.text[:500]}"
            except Exception:
                pass

        log_error("call_openai_compatible", detail)

        return {
            "error": (
                f"Tidak bisa menghubungi {config['base_url']}: {detail}"
            )
        }


def get_openrouter_credits(config):
    """
    Ambil sisa saldo/kredit dari OpenRouter lewat endpoint
    terpisah /credits (bukan bagian dari response chat biasa).
    Hanya berlaku untuk provider dengan base_url openrouter.ai.
    """

    api_key = os.getenv(config["api_key_env"])

    if not api_key:

        return {
            "success": False,
            "error": f"{config['api_key_env']} belum diset di .env."
        }

    if "openrouter.ai" not in config.get("base_url", ""):

        return {
            "success": False,
            "error": (
                "Provider aktif bukan OpenRouter — cek saldo "
                "hanya didukung untuk provider OpenRouter saat ini."
            )
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:

        response = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        data = response.json().get("data", {})

        total_credits = data.get("total_credits")
        total_usage = data.get("total_usage")

        remaining = None

        if total_credits is not None and total_usage is not None:
            remaining = round(total_credits - total_usage, 4)

        return {
            "success": True,
            "total_credits": total_credits,
            "total_usage": total_usage,
            "remaining": remaining,
        }

    except requests.exceptions.RequestException as exc:

        log_error("get_openrouter_credits", exc)

        return {
            "success": False,
            "error": str(exc)
        }