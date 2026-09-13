"""
agents/rei/provider_client.py — SATU-SATUNYA file di ekosistem AIRA yang
boleh memanggil provider LLM eksternal (OpenRouter) atau lokal (Ollama).

Taruh file ini di: AIRA_ECOSYSTEM/agents/rei/provider_client.py (TIMPA file
lama).

PHASE 1.2 — MODEL MANAGEMENT SYSTEM
--------------------------------------
Provider config TIDAK LAGI hardcoded di file ini (PROVIDERS dict versi lama
dihapus). Semua model diregistrasi di SQLite lewat core/model_registry.py
dan dikelola oleh REI Model Manager (CRUD via api/routers/models.py).

Provider yang didukung: "ollama", "openrouter", "gemini". OpenRouter dan
Gemini sama-sama memakai format API "OpenAI-compatible" (endpoint
/chat/completions, bentuk request/response identik), jadi keduanya berbagi
satu fungsi _call_openai_compatible() — bedanya cuma endpoint default dan
nama env var API key. Ini contoh nyata kenapa menambah provider baru TIDAK
perlu mengubah orchestrator/planner: cukup tambah 1 baris di PROVIDER_ENV_KEYS
+ DEFAULT_ENDPOINTS, lalu daftarkan di _PROVIDER_CALLERS/_PROVIDER_HEALTH_CHECKS.

File ini murni jadi EXECUTOR:
  1. Ambil model default dari registry -> panggil provider yang sesuai
     lewat adapter generik (_PROVIDER_CALLERS). Tambah provider baru
     TIDAK PERLU mengubah orchestrator/planner - cukup tambah entry di
     _PROVIDER_CALLERS + _PROVIDER_HEALTH_CHECKS di bawah.
  2. AUTO FAILOVER: kalau model default gagal karena salah satu dari
     HTTP 429 (rate limit), Timeout, atau Connection Error, otomatis
     coba model yang ditandai is_fallback=1, lalu publish event
     "model.failed" dan "model.switched" lewat core/events.py.
  3. Menyediakan fungsi kompatibilitas (list_providers, get_active_provider,
     set_active_provider_key, get_openrouter_credits) supaya
     api/routers/providers.py dan SettingsPage.jsx lama TETAP JALAN tanpa
     perubahan, sekarang dukungannya diarahkan ke registry baru.

call_model(messages, tools) - SIGNATURE TIDAK BERUBAH dari versi lama,
jadi agents/rei/planner.py dan agents/rei/auto_extract.py tidak perlu
disentuh sama sekali.
"""

import os
import json
import logging
from typing import Any, Callable, Optional

import requests
from dotenv import load_dotenv
from pathlib import Path

from core import model_registry as registry
from core.events import event_bus

logger = logging.getLogger("aira.rei.provider_client")

# parents[0]=rei, [1]=agents, [2]=AIRA_ECOSYSTEM, [3]=repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
AIRA_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")
load_dotenv(AIRA_ROOT / ".env", override=False)

EMPTY_RESPONSE_MARKER = (
    "(Provider mengembalikan respons kosong atau tidak valid. "
    "Kemungkinan model sedang rate-limited/bermasalah — "
    "coba lagi atau ganti model.)"
)

# Tipe error yang MEMICU auto-failover. Error lain (mis. JSON tidak valid,
# argumen salah) TIDAK memicu failover karena kemungkinan besar akan gagal
# juga di model fallback (bukan masalah ketersediaan provider).
FAILOVER_ERROR_TYPES = {"timeout", "connection", "rate_limit"}

# Nama env var .env per provider - dibaca kalau kolom api_key di registry
# dikosongkan. Tambah provider baru berbasis API key tinggal tambah 1 baris
# di sini (dan di DEFAULT_ENDPOINTS kalau perlu endpoint default).
PROVIDER_ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API",
    "gemini": "GEMINI_API_KEY",
}

# Endpoint default per provider kalau kolom endpoint di registry dikosongkan.
DEFAULT_ENDPOINTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


# ============================================================
# HELPERS
# ============================================================

def _resolve_api_key(model: dict) -> Optional[str]:
    """
    Urutan resolusi API key: kolom api_key di registry dulu, kalau kosong
    fallback ke .env sesuai PROVIDER_ENV_KEYS (supaya kompatibel dengan
    setup lama yang menaruh OPENROUTER_API di .env tanpa perlu isi ulang
    lewat UI, dan berlaku sama untuk provider baru seperti Gemini).
    """

    if model.get("api_key"):
        return model["api_key"]

    env_key = PROVIDER_ENV_KEYS.get(model.get("provider"))

    return os.getenv(env_key) if env_key else None


def _resolve_endpoint(model: dict) -> str:
    return (model.get("endpoint") or DEFAULT_ENDPOINTS.get(model["provider"], "")).rstrip("/")


def _classify_request_exception(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"

    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection"

    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return "rate_limit" if status == 429 else "other"

    return "other"


def _normalize_message(message: dict) -> dict:
    if not isinstance(message, dict):
        message = {}

    if "role" not in message or not message.get("role"):
        message["role"] = "assistant"

    if message.get("tool_calls") is None:
        message["tool_calls"] = []

    has_content = bool(message.get("content"))
    has_tool_calls = bool(message.get("tool_calls"))

    if not has_content and not has_tool_calls:
        message["content"] = EMPTY_RESPONSE_MARKER

    return message


def _extract_ollama_usage(data: dict) -> Optional[dict]:
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


# ============================================================
# PROVIDER ADAPTERS — CALL
# ============================================================
# Tambah provider baru: tulis fungsi _call_<provider>(model, messages, tools)
# dengan bentuk return {"message":..., "usage":...} ATAU
# {"error": "...", "error_type": "timeout"|"connection"|"rate_limit"|"other"},
# lalu daftarkan di _PROVIDER_CALLERS di bagian bawah file ini.

def _call_ollama(model: dict, messages: list, tools: list) -> dict:
    base_url = _resolve_endpoint(model)
    url = f"{base_url}/api/chat"

    payload = {
        "model": model["model_id"],
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            return {
                "error": f"Ollama di {url} membalas body bukan JSON valid: {exc}",
                "error_type": "other",
            }

        message = _normalize_message(data.get("message", {}))

        return {"message": message, "usage": _extract_ollama_usage(data)}

    except requests.exceptions.RequestException as exc:
        error_type = _classify_request_exception(exc)
        logger.error("call_ollama gagal (%s): %s", error_type, exc)

        return {
            "error": f"Tidak bisa menghubungi Ollama di {url}: {exc}",
            "error_type": error_type,
        }


def _call_openai_compatible(model: dict, messages: list, tools: list, provider_label: str) -> dict:
    """
    Dipakai bersama oleh OpenRouter DAN Gemini — keduanya menyediakan
    endpoint bergaya OpenAI (/chat/completions, bentuk request/response
    identik). Kalau nanti mau tambah provider lain yang juga OpenAI-
    compatible (Groq, Together, DeepSeek, dst), cukup buat wrapper tipis
    seperti _call_openrouter/_call_gemini di bawah, TANPA menulis ulang
    logic HTTP-nya.
    """

    api_key = _resolve_api_key(model)

    if not api_key:
        env_key = PROVIDER_ENV_KEYS.get(model["provider"], "")
        return {
            "error": (
                f"API key {provider_label} belum diset (kolom api_key model "
                f"atau .env {env_key})."
            ),
            "error_type": "other",
        }

    base_url = _resolve_endpoint(model)
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Header tambahan khusus OpenRouter (opsional bagi provider lain,
    # tidak masalah kalau diabaikan provider yang tidak butuh).
    if model["provider"] == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "AIRA Ecosystem"

    payload = {"model": model["model_id"], "messages": messages, "tools": tools}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            return {
                "error": f"{base_url} membalas body bukan JSON valid: {exc}",
                "error_type": "other",
            }

        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        message = _normalize_message(choice.get("message") or {})

        return {"message": message, "usage": data.get("usage")}

    except requests.exceptions.RequestException as exc:
        error_type = _classify_request_exception(exc)
        detail = str(exc)

        if getattr(exc, "response", None) is not None:
            try:
                detail = f"{detail} | body: {exc.response.text[:500]}"
            except Exception:
                pass

        logger.error("call_%s gagal (%s): %s", model["provider"], error_type, detail)

        return {
            "error": f"Tidak bisa menghubungi {base_url}: {detail}",
            "error_type": error_type,
        }


def _call_openrouter(model: dict, messages: list, tools: list) -> dict:
    return _call_openai_compatible(model, messages, tools, provider_label="OpenRouter")


def _call_gemini(model: dict, messages: list, tools: list) -> dict:
    return _call_openai_compatible(model, messages, tools, provider_label="Gemini")


_PROVIDER_CALLERS: dict[str, Callable[[dict, list, list], dict]] = {
    "ollama": _call_ollama,
    "openrouter": _call_openrouter,
    "gemini": _call_gemini,
}


# ============================================================
# PROVIDER ADAPTERS — HEALTH CHECK
# ============================================================
# Dipakai tombol "Test Connection" di UI. Return {"online": bool, "message": str}.

def _health_check_ollama(model: dict) -> dict:
    base_url = _resolve_endpoint(model)

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        online = response.status_code == 200
        return {"online": online, "message": "OK" if online else f"HTTP {response.status_code}"}

    except requests.exceptions.RequestException as exc:
        return {"online": False, "message": str(exc)}


def _health_check_openai_compatible(model: dict) -> dict:
    """Dipakai bersama OpenRouter dan Gemini - keduanya mendukung GET
    {endpoint}/models dengan Authorization Bearer untuk cek konektivitas
    ringan tanpa memanggil model (tidak makan kuota generation)."""

    api_key = _resolve_api_key(model)

    if not api_key:
        return {"online": False, "message": "API key belum diset."}

    base_url = _resolve_endpoint(model)

    try:
        response = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        online = response.status_code == 200
        return {"online": online, "message": "OK" if online else f"HTTP {response.status_code}"}

    except requests.exceptions.RequestException as exc:
        return {"online": False, "message": str(exc)}


_PROVIDER_HEALTH_CHECKS: dict[str, Callable[[dict], dict]] = {
    "ollama": _health_check_ollama,
    "openrouter": _health_check_openai_compatible,
    "gemini": _health_check_openai_compatible,
}


def test_connection(nickname: str) -> dict:
    """Dipanggil oleh api/routers/models.py::test_connection endpoint."""

    model = registry.get_model(nickname, mask_api_key=False)

    if not model:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    checker = _PROVIDER_HEALTH_CHECKS.get(model["provider"])

    if not checker:
        return {
            "success": False,
            "error": f"Provider '{model['provider']}' tidak punya health check terdaftar.",
        }

    result = checker(model)
    registry.touch_ping(nickname, result["online"], result.get("message", ""))

    return {
        "success": True,
        "nickname": nickname,
        "online": result["online"],
        "message": result.get("message", ""),
    }


# ============================================================
# DISPATCH + AUTO FAILOVER
# ============================================================

def _dispatch(model: dict, messages: list, tools: list) -> dict:
    caller = _PROVIDER_CALLERS.get(model["provider"])

    if not caller:
        return {
            "error": f"Provider '{model['provider']}' tidak dikenal oleh provider_client.",
            "error_type": "other",
        }

    return caller(model, messages, tools)


def _publish_model_failed(model: dict, error_type: str, error: str) -> None:
    try:
        event_bus.publish(
            "model.failed",
            agent="REI",
            tool=model["nickname"],
            data={
                "provider": model["provider"],
                "model_id": model["model_id"],
                "error_type": error_type,
                "error": error,
            },
        )
    except Exception:
        logger.exception("Gagal publish event model.failed (diabaikan).")


def _publish_model_switched(from_nickname: str, to_nickname: str, reason: str) -> None:
    try:
        event_bus.publish(
            "model.switched",
            agent="REI",
            data={"from": from_nickname, "to": to_nickname, "reason": reason},
        )
    except Exception:
        logger.exception("Gagal publish event model.switched (diabaikan).")


def call_model(messages: list, tools: list) -> dict:
    """
    Titik masuk yang dipanggil agents/rei/planner.py dan
    agents/rei/auto_extract.py — SIGNATURE SAMA seperti versi lama, supaya
    kedua file itu tidak perlu diubah sama sekali.

    Alur:
      1. Ambil model default (is_default=1, enabled=1) dari registry.
      2. Panggil provider-nya. Kalau sukses -> return langsung.
      3. Kalau gagal karena timeout/connection/rate_limit -> publish
         "model.failed", cari model fallback (is_fallback=1, enabled=1,
         beda dari yang gagal), coba panggil.
      4. Kalau fallback sukses -> publish "model.switched", return hasil
         fallback. Kalau fallback juga gagal -> publish "model.failed"
         untuk fallback juga, return error terakhir ke pemanggil.

    Riwayat percakapan (chat history) TIDAK disentuh oleh fungsi ini -
    failover murni terjadi di level pemilihan provider, bukan di memory.
    """

    primary = registry.get_default_model(mask_api_key=False)

    if not primary:
        return {
            "error": (
                "Tidak ada model aktif di registry. Tambahkan/aktifkan model "
                "lewat halaman Model Management (REI)."
            )
        }

    result = _dispatch(primary, messages, tools)

    if "error" not in result:
        return result

    error_type = result.get("error_type", "other")

    if error_type not in FAILOVER_ERROR_TYPES:
        return {"error": result["error"]}

    logger.warning(
        "Model default '%s' gagal (%s): %s", primary["nickname"], error_type, result["error"]
    )
    _publish_model_failed(primary, error_type, result["error"])

    fallback = registry.get_fallback_model(
        exclude_nickname=primary["nickname"], mask_api_key=False
    )

    if not fallback:
        logger.warning("AUTO FAILOVER | tidak ada model fallback yang tersedia.")
        return {"error": result["error"]}

    logger.info("AUTO FAILOVER | %s -> %s (alasan: %s)", primary["nickname"], fallback["nickname"], error_type)

    fallback_result = _dispatch(fallback, messages, tools)

    if "error" not in fallback_result:
        _publish_model_switched(primary["nickname"], fallback["nickname"], error_type)
        return fallback_result

    logger.error(
        "AUTO FAILOVER GAGAL | fallback '%s' juga gagal: %s",
        fallback["nickname"],
        fallback_result["error"],
    )
    _publish_model_failed(
        fallback, fallback_result.get("error_type", "other"), fallback_result["error"]
    )

    return {"error": fallback_result["error"]}


# ============================================================
# KOMPATIBILITAS LAMA — dipakai api/routers/providers.py & SettingsPage.jsx
# ============================================================
# Fungsi-fungsi ini dipertahankan namanya 1:1 dari versi lama supaya router
# & halaman Settings lama TIDAK PERLU diubah, tapi isinya sekarang membaca
# dari registry baru alih-alih PROVIDERS dict hardcoded / fact di Memory.

def list_providers() -> dict[str, dict[str, str]]:
    models = registry.list_models(mask_api_key=True)

    return {
        m["nickname"]: {"label": m["nickname"], "type": m["provider"]}
        for m in models
    }


def get_active_provider() -> tuple[Optional[str], dict[str, str]]:
    model = registry.get_default_model(mask_api_key=True)

    if not model:
        return None, {}

    return model["nickname"], {"label": model["nickname"], "type": model["provider"]}


def set_active_provider_key(key: str) -> dict:
    result = registry.set_default(key)

    if not result.get("success"):
        return result

    return {"success": True, "key": key, "label": key}


def get_openrouter_credits(config: Optional[dict] = None) -> dict:
    model = None

    if config and config.get("nickname"):
        model = registry.get_model(config["nickname"], mask_api_key=False)

    if model is None:
        model = registry.get_default_model(mask_api_key=False)

    if not model or model["provider"] != "openrouter":
        return {"success": False, "error": "Model aktif bukan OpenRouter (tidak ada saldo)."}

    api_key = _resolve_api_key(model)

    if not api_key:
        return {"success": False, "error": "API key OpenRouter belum diset."}

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()

        data = response.json().get("data", {})
        total_credits = data.get("total_credits")
        total_usage = data.get("total_usage")

        remaining = (
            round(total_credits - total_usage, 4)
            if total_credits is not None and total_usage is not None
            else None
        )

        return {
            "success": True,
            "total_credits": total_credits,
            "total_usage": total_usage,
            "remaining": remaining,
        }

    except requests.exceptions.RequestException as exc:
        logger.error("get_openrouter_credits gagal: %s", exc)
        return {"success": False, "error": str(exc)}

    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"Response credits bukan JSON valid: {exc}"}