"""
agents/rei/provider_client.py — SATU-SATUNYA file di ekosistem AIRA yang
boleh memanggil provider LLM eksternal (OpenRouter) atau lokal (Ollama).
Port dari agent/core/providers.py, hanya sumber long-term memory yang
berubah: dulu agent.memory_store.long_term, sekarang core.memory.
"""

import os
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

from core.memory import remember_fact, recall_facts

logger = logging.getLogger("aira.rei.provider_client")

# parents[0]=rei, [1]=agents, [2]=AIRA_ECOSYSTEM, [3]=repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
AIRA_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")
load_dotenv(AIRA_ROOT / ".env", override=False)

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

DEFAULT_PROVIDER_KEY = "ollama-qwen3-1.7b"
ACTIVE_MODEL_FACT_KEY = "active_model_provider"

EMPTY_RESPONSE_MARKER = (
    "(Provider mengembalikan respons kosong atau tidak valid. "
    "Kemungkinan model sedang rate-limited/bermasalah — "
    "coba lagi atau ganti model.)"
)


def list_providers():
    return PROVIDERS


def get_active_provider_key():
    facts = recall_facts(ACTIVE_MODEL_FACT_KEY, limit=1)
    for fact in facts:
        if fact["key"] == ACTIVE_MODEL_FACT_KEY and fact["value"] in PROVIDERS:
            return fact["value"]
    return DEFAULT_PROVIDER_KEY


def set_active_provider_key(key):
    if key not in PROVIDERS:
        return {"success": False, "error": f"Provider '{key}' tidak ditemukan."}
    remember_fact(ACTIVE_MODEL_FACT_KEY, key)
    return {"success": True, "key": key, "label": PROVIDERS[key]["label"]}


def get_active_provider():
    key = get_active_provider_key()
    return key, PROVIDERS[key]


def call_model(messages, tools):
    key, config = get_active_provider()

    if config["type"] == "ollama":
        result = _call_ollama(config, messages, tools)
    elif config["type"] == "openai":
        result = _call_openai_compatible(config, messages, tools)
    else:
        result = {"error": f"Tipe provider '{config['type']}' tidak dikenal."}

    return result


def _normalize_message(message):
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
    payload = {"model": config["model"], "messages": messages, "tools": tools, "stream": False}

    try:
        response = requests.post(config["url"], json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        message = _normalize_message(data.get("message", {}))
        return {"message": message, "usage": _extract_ollama_usage(data)}
    except requests.exceptions.RequestException as exc:
        logger.error("call_ollama gagal: %s", exc)
        return {"error": f"Tidak bisa menghubungi Ollama di {config['url']}: {exc}"}


def _call_openai_compatible(config, messages, tools):
    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        return {"error": f"{config['api_key_env']} belum diset di .env."}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "AIRA Ecosystem",
    }

    payload = {"model": config["model"], "messages": messages, "tools": tools}
    url = f"{config['base_url']}/chat/completions"

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        message = _normalize_message(choice.get("message") or {})
        return {"message": message, "usage": data.get("usage")}
    except requests.exceptions.RequestException as exc:
        detail = str(exc)
        if getattr(exc, "response", None) is not None:
            try:
                detail = f"{detail} | body: {exc.response.text[:500]}"
            except Exception:
                pass
        logger.error("call_openai_compatible gagal: %s", detail)
        return {"error": f"Tidak bisa menghubungi {config['base_url']}: {detail}"}


def get_openrouter_credits(config=None):
    if config is None:
        _, config = get_active_provider()

    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        return {"success": False, "error": f"{config['api_key_env']} belum diset di .env."}

    if "openrouter.ai" not in config.get("base_url", ""):
        return {"success": False, "error": "Provider aktif bukan OpenRouter."}

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = requests.get("https://openrouter.ai/api/v1/credits", headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json().get("data", {})
        total_credits = data.get("total_credits")
        total_usage = data.get("total_usage")
        remaining = (
            round(total_credits - total_usage, 4)
            if total_credits is not None and total_usage is not None else None
        )
        return {"success": True, "total_credits": total_credits, "total_usage": total_usage, "remaining": remaining}
    except requests.exceptions.RequestException as exc:
        logger.error("get_openrouter_credits gagal: %s", exc)
        return {"success": False, "error": str(exc)}
