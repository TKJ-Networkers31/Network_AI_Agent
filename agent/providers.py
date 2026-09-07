import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from agent.long_term_memory import remember_fact, recall_facts
from agent.logger import log_error, log_llm_request, log_llm_response


BASE_DIR = Path(__file__).resolve().parents[1]

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
# exact match untuk memilih handler yang dipakai. Kalau kamu
# tulis label bebas (mis. "Open Router") di sini, call_model()
# tidak akan mengenalinya dan selalu return error
# "Tipe provider '...' tidak dikenal." — ini penyebab error
# yang kamu alami.
#
# Tinggal tambah entry baru di sini kalau mau daftarkan API lain.
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

}

DEFAULT_PROVIDER_KEY = "ollama-qwen3-4b"
ACTIVE_MODEL_FACT_KEY = "active_model_provider"


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
    bentuk seragam {"message": {...}} atau {"error": "..."}
    supaya agent/engine.py tidak perlu tahu bedanya provider.
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

        return {
            "message": data.get("message", {})
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
        # OpenRouter merekomendasikan header ini (opsional untuk
        # OpenAI/Groq/dll, tapi tidak berbahaya dikirim ke semua
        # provider kompatibel-OpenAI). Membantu OpenRouter
        # mengidentifikasi aplikasi kamu di dashboard mereka.
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

        choice = (
            data.get("choices", [{}])[0]
        )

        return {
            "message": choice.get("message", {})
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