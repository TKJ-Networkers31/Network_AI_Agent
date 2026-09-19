"""
agents/rei/provider_client.py — SATU-SATUNYA file di ekosistem AIRA yang boleh
memanggil provider LLM (Ollama / OpenRouter / Gemini).

SPRINT 1 — MODEL ROUTER:
Tidak ada lagi model default/registry di file ini. Model SELALU datang dari
luar sebagai SelectedModel (dipilih core/model_router.py, dijaga
core/model_policy.py):

  ProviderClient.chat(provider, model, messages, tools)   panggilan mentah
  call_model(messages, tools, selected_model)             titik masuk planner:
        cek context -> panggil -> retry (transient) -> fallback (policy)
  call_model tanpa selected_model (mis. auto_extract) memakai default label
  "general" dari router.

Ollama: kalau model menolak tools ("does not support tools", mis. Gemma 3),
panggilan diulang sekali TANPA tools - jawaban tetap keluar, tapi tanpa tool.
API key dibaca dari .env (PROVIDER_ENV_KEYS), tidak disimpan di database.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from core.events import event_bus
from core.model_policy import estimate_tokens, get_model_policy
from core.model_router import get_model_router
from core.model_store import get_model_store
from core.model_types import DEFAULT_LABEL, EVENT_MODEL_FAILED, SelectedModel

logger = logging.getLogger("aira.rei.provider_client")

REPO_ROOT = Path(__file__).resolve().parents[3]
AIRA_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")
load_dotenv(AIRA_ROOT / ".env", override=False)

EMPTY_RESPONSE_MARKER = (
    "(Provider mengembalikan respons kosong atau tidak valid. "
    "Kemungkinan model sedang rate-limited/bermasalah — "
    "coba lagi atau ganti model.)"
)

# Hanya error sementara yang di-retry di model yang sama (jumlah = retry_provider).
TRANSIENT_ERROR_TYPES = {"rate_limit", "connection"}

PROVIDER_ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API",
    "gemini": "GEMINI_API_KEY",
}

DEFAULT_ENDPOINTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


# ============================================================ helpers

def _endpoint(provider: str) -> str:
    return DEFAULT_ENDPOINTS[provider].rstrip("/")


def _resolve_api_key(provider: str) -> Optional[str]:
    env_key = PROVIDER_ENV_KEYS.get(provider)
    return os.getenv(env_key) if env_key else None


def _classify_request_exception(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "rate_limit" if getattr(exc.response, "status_code", None) == 429 else "other"
    return "other"


def _request_error(label: str, url: str, exc: Exception) -> dict:
    error_type = _classify_request_exception(exc)
    detail = str(exc)
    response = getattr(exc, "response", None)

    if response is not None:
        try:
            detail = f"{detail} | body: {response.text[:500]}"
        except Exception:
            pass

    logger.error("chat %s gagal (%s): %s", label, error_type, detail)
    return {"error": f"Tidak bisa menghubungi {url}: {detail}", "error_type": error_type}


def _normalize_message(message: dict) -> dict:
    if not isinstance(message, dict):
        message = {}
    if not message.get("role"):
        message["role"] = "assistant"
    if message.get("tool_calls") is None:
        message["tool_calls"] = []
    if not message.get("content") and not message["tool_calls"]:
        message["content"] = EMPTY_RESPONSE_MARKER
    return message


def _extract_ollama_usage(data: dict) -> Optional[dict]:
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    if prompt_tokens is None and completion_tokens is None:
        return None
    prompt_tokens, completion_tokens = prompt_tokens or 0, completion_tokens or 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _post_json(url: str, payload: dict, timeout: float, headers: Optional[dict] = None) -> dict:
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


# ============================================================ adapters

def _chat_ollama(model_id, messages, tools, temperature, max_tokens, think, timeout) -> dict:
    url = f"{_endpoint('ollama')}/api/chat"
    payload: dict = {"model": model_id, "messages": messages, "stream": False}

    if tools:
        payload["tools"] = tools

    options = {}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    if options:
        payload["options"] = options
    if think is not None:
        payload["think"] = think

    try:
        try:
            data = _post_json(url, payload, timeout)
        except requests.exceptions.HTTPError as exc:
            body = exc.response.text.lower() if exc.response is not None else ""
            if payload.get("tools") and "does not support tools" in body:
                logger.warning("Model '%s' tidak mendukung tools - mengulang tanpa tools.", model_id)
                payload.pop("tools")
                data = _post_json(url, payload, timeout)
            else:
                raise

        return {
            "message": _normalize_message(data.get("message", {})),
            "usage": _extract_ollama_usage(data),
        }

    except requests.exceptions.RequestException as exc:
        return _request_error("ollama", url, exc)
    except ValueError as exc:
        return {"error": f"Ollama membalas body bukan JSON valid: {exc}", "error_type": "other"}


def _chat_openai_compatible(provider, model_id, messages, tools, temperature, max_tokens, timeout) -> dict:
    api_key = _resolve_api_key(provider)

    if not api_key:
        return {
            "error": f"API key {provider} belum diset (.env {PROVIDER_ENV_KEYS[provider]}).",
            "error_type": "other",
        }

    url = f"{_endpoint(provider)}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "AIRA Ecosystem"

    payload: dict = {"model": model_id, "messages": messages}
    if tools:
        payload["tools"] = tools
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        data = _post_json(url, payload, timeout, headers=headers)
        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        return {"message": _normalize_message(choice.get("message") or {}), "usage": data.get("usage")}

    except requests.exceptions.RequestException as exc:
        return _request_error(provider, url, exc)
    except ValueError as exc:
        return {"error": f"{url} membalas body bukan JSON valid: {exc}", "error_type": "other"}


# ============================================================ public client

class ProviderClient:

    @staticmethod
    def chat(
        provider: str,
        model: str,
        messages: list,
        tools: Optional[list] = None,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        think: Optional[bool] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        Return {"message":..., "usage":...} atau {"error":..., "error_type":
        "timeout"|"connection"|"rate_limit"|"other"}. Tidak pernah raise.
        """
        provider = (provider or "").strip().lower()

        if provider == "ollama":
            return _chat_ollama(model, messages, tools, temperature, max_tokens, think, timeout or 300)

        if provider in PROVIDER_ENV_KEYS:
            return _chat_openai_compatible(provider, model, messages, tools, temperature, max_tokens, timeout or 120)

        return {"error": f"Provider '{provider}' tidak dikenal.", "error_type": "other"}

    @staticmethod
    def health_check(provider: str, model_id: Optional[str] = None) -> dict:
        provider = (provider or "").strip().lower()

        try:
            if provider == "ollama":
                response = requests.get(f"{_endpoint('ollama')}/api/tags", timeout=5)
                if response.status_code != 200:
                    return {"online": False, "message": f"HTTP {response.status_code}"}

                if model_id:
                    names = {m.get("name") for m in response.json().get("models", [])}
                    wanted = model_id if ":" in model_id else f"{model_id}:latest"
                    if wanted not in names:
                        return {"online": False, "message": f"Ollama aktif, tapi model '{model_id}' belum di-pull."}

                return {"online": True, "message": "OK"}

            if provider in PROVIDER_ENV_KEYS:
                api_key = _resolve_api_key(provider)
                if not api_key:
                    return {"online": False, "message": f"API key belum diset (.env {PROVIDER_ENV_KEYS[provider]})."}

                response = requests.get(
                    f"{_endpoint(provider)}/models",
                    headers={"Authorization": f"Bearer {api_key}"}, timeout=8,
                )
                ok = response.status_code == 200
                return {"online": ok, "message": "OK" if ok else f"HTTP {response.status_code}"}

            return {"online": False, "message": f"Provider '{provider}' tidak dikenal."}

        except (requests.exceptions.RequestException, ValueError) as exc:
            return {"online": False, "message": str(exc)}


# ============================================================ call_model

def _publish_model_failed(model: SelectedModel, result: dict) -> None:
    try:
        event_bus.publish(
            EVENT_MODEL_FAILED, agent="REI", tool=model.display_name,
            data={
                "id": model.id, "provider": model.provider, "model_id": model.model_id,
                "error_type": result.get("error_type", "other"), "error": result.get("error"),
            },
        )
    except Exception:
        logger.exception("Gagal publish model.failed (diabaikan).")


def _attempt(model: SelectedModel, messages: list, tools: list, retries: int) -> dict:
    def call() -> dict:
        return ProviderClient.chat(
            provider=model.provider, model=model.model_id, messages=messages, tools=tools,
        )

    result = call()
    attempt = 0

    while "error" in result and result.get("error_type") in TRANSIENT_ERROR_TYPES and attempt < retries:
        attempt += 1
        logger.info("Retry %d/%d ke '%s' (%s).", attempt, retries, model.display_name, result["error_type"])
        time.sleep(min(2 * attempt, 5))
        result = call()

    return result


def call_model(messages: list, tools: list, selected_model=None, *, policy=None, router=None) -> dict:
    """
    Titik masuk planner/auto_extract. `selected_model` (SelectedModel/dict)
    berasal dari Model Router; None -> default label general.
    Hasil sukses menyertakan key "model" (model yang benar-benar dipakai).
    """
    policy = policy or get_model_policy()
    router = router or get_model_router()

    if selected_model is not None:
        selected = SelectedModel.from_any(selected_model)
    else:
        selected = router.select_for_label(DEFAULT_LABEL, publish=False)

    if selected is None:
        return {"error": "Tidak ada model aktif. Tambahkan/aktifkan model di halaman Models."}

    selected = policy.check_context(selected, estimate_tokens(messages, tools))

    result = _attempt(selected, messages, tools, retries=policy.retry_count())

    if "error" not in result:
        result["model"] = selected.to_dict()
        return result

    _publish_model_failed(selected, result)

    fallback = policy.on_provider_failure(selected, result.get("error_type", "other"))
    if fallback is None:
        return {"error": result["error"]}

    result = _attempt(fallback, messages, tools, retries=0)

    if "error" in result:
        _publish_model_failed(fallback, result)
        return {"error": result["error"]}

    result["model"] = fallback.to_dict()
    return result


# ============================================================ kompatibilitas

def get_active_provider() -> tuple[Optional[str], dict]:
    """Dipakai api/routers/providers.py: model default label general."""
    store = get_model_store()
    model = store.get_model(store.get_routing().get(DEFAULT_LABEL))

    if not model:
        return None, {}

    return model["id"], {"label": model["display_name"], "type": model["provider"]}


def get_openrouter_credits(config: Optional[dict] = None) -> dict:
    api_key = _resolve_api_key("openrouter")

    if not api_key:
        return {"success": False, "error": "OPENROUTER_API belum diset di .env."}

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=15,
        )
        response.raise_for_status()

        data = response.json().get("data", {})
        total_credits, total_usage = data.get("total_credits"), data.get("total_usage")
        remaining = (
            round(total_credits - total_usage, 4)
            if total_credits is not None and total_usage is not None else None
        )
        return {"success": True, "total_credits": total_credits, "total_usage": total_usage, "remaining": remaining}

    except requests.exceptions.RequestException as exc:
        logger.error("get_openrouter_credits gagal: %s", exc)
        return {"success": False, "error": str(exc)}
    except ValueError as exc:
        return {"success": False, "error": f"Response credits bukan JSON valid: {exc}"}


def test_connection(model_record_id: str) -> dict:
    """Dipanggil api/routers/models.py (tombol Test Connection)."""
    model = get_model_store().get_model(model_record_id)

    if not model:
        return {"success": False, "error": f"Model '{model_record_id}' tidak ditemukan."}

    result = ProviderClient.health_check(model["provider"], model["model_id"])

    return {"success": True, "id": model_record_id, "online": result["online"], "message": result["message"]}