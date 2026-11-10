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

SPRINT 2.5 — STREAMING:
  ProviderClient.chat_stream(...)   streaming NYATA: Ollama NDJSON
        (/api/chat stream=true) dan OpenAI-compatible SSE (stream=true,
        untuk OpenRouter / Gemini / NVIDIA). Tiap potongan teks yang baru
        diterima langsung diteruskan lewat on_delta - TIDAK ada pemotongan
        respons penuh. Hasil akhirnya berbentuk SAMA dengan chat()
        ({"message","usage"} / {"error","error_type"}) ditambah
        "streamed": True.
  call_model(..., stream=sink)      jalur streaming; tanpa `stream` perilaku
        lama (non-streaming) TIDAK berubah. Retry (transient), fallback
        provider (policy), dan cek context tetap berlaku. Setiap request ke
        provider memanggil sink.start(model) - client wajib mengosongkan
        buffer teksnya karena retry/fallback memulai jawaban dari awal.
        Provider yang menolak streaming ("stream_unsupported") diulang
        non-streaming pada model yang sama.
  Stop: cancel_event dicek tiap chunk; koneksi ditutup dan hasilnya
        {"cancelled": True} (tanpa retry/fallback).
Sink streaming = objek dengan start(model: dict) dan delta(text: str).
"""

import json
import logging
import os
import time
from contextlib import closing
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from core.events import event_bus
from core.model_policy import estimate_tokens, get_model_policy
from core.model_router import get_model_router
from core.model_store import get_model_store
from core.model_types import DEFAULT_LABEL, EVENT_MODEL_FAILED, SelectedModel
from core.provider_health import FailureCategory, get_provider_health_manager

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
TRANSIENT_ERROR_TYPES = {"rate_limit", "connection", "timeout", "server_error"}
NON_RETRYABLE_ERROR_TYPES = {"circuit_open", "auth_error", "bad_request", "not_found", "cancelled"}

DEFAULT_LLM_TIMEOUT = float(os.getenv("VERA_LLM_TIMEOUT") or os.getenv("AIRA_LLM_TIMEOUT", "45"))

PROVIDER_ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API",
    "gemini": "GEMINI_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}

DEFAULT_ENDPOINTS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


# ============================================================ helpers

def _endpoint(provider: str) -> str:
    return DEFAULT_ENDPOINTS[provider].rstrip("/")


def _resolve_api_key(provider: str) -> Optional[str]:
    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API")
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if provider == "nvidia":
        return os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY")
    env_key = PROVIDER_ENV_KEYS.get(provider)
    return os.getenv(env_key) if env_key else None


def _sanitize_tools(tools: Optional[list]) -> Optional[list]:
    """
    Sanitize tools payload before sending to model provider:
    1. Removes duplicate function definitions by name (Gemini and other strict APIs reject duplicates with 400 Bad Request).
    2. Ensures every entry has a valid dictionary structure.
    """
    if not tools:
        return tools
    seen = set()
    sanitized = []
    for item in tools:
        if not isinstance(item, dict):
            sanitized.append(item)
            continue
        func = item.get("function")
        if isinstance(func, dict):
            name = func.get("name")
            if name:
                if name in seen:
                    logger.debug("Deduplicated tool function '%s' in provider payload", name)
                    continue
                seen.add(name)
        sanitized.append(item)
    return sanitized


def _classify_request_exception(exc: Exception) -> tuple[str, FailureCategory]:
    if isinstance(exc, requests.exceptions.Timeout):
        return ("timeout", FailureCategory.TIMEOUT)
    if isinstance(exc, requests.exceptions.SSLError):
        return ("tls", FailureCategory.TLS)
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        return ("connection", FailureCategory.CONNECTION)  # ChunkedEncodingError = stream terputus di tengah jalan
    if isinstance(exc, requests.exceptions.HTTPError):
        code = getattr(exc.response, "status_code", None)
        if code in (401, 403):
            return ("auth_error", FailureCategory.AUTH_ERROR)
        if code == 400:
            return ("bad_request", FailureCategory.BAD_REQUEST)
        if code == 404:
            return ("not_found", FailureCategory.NOT_FOUND)
        if code == 429:
            return ("rate_limit", FailureCategory.RATE_LIMIT)
        if code and code >= 500:
            return ("other", FailureCategory.SERVER_ERROR)
        return ("other", FailureCategory.OTHER)
    return ("other", FailureCategory.OTHER)


def _request_error(
    provider: str,
    url: str,
    exc: Exception,
    model_id: Optional[str] = None,
    record_telemetry: bool = True,
) -> dict:
    error_type, category = _classify_request_exception(exc)
    detail = str(exc)
    response = getattr(exc, "response", None)

    if response is not None:
        try:
            detail = f"{detail} | body: {response.text[:500]}"
        except Exception:
            pass

    # Record failure telemetry in centralized ProviderHealthManager
    if record_telemetry:
        try:
            health_mgr = get_provider_health_manager()
            health_mgr.record_failure(provider, category, detail, model_id=model_id, endpoint=url)
        except Exception:
            pass

    logger.error("chat %s (%s) gagal (%s): %s", provider, model_id or "unknown", error_type, detail)
    return {"error": f"Tidak bisa menghubungi {url}: {detail}", "error_type": error_type}


def _normalize_timeout(timeout=None) -> tuple[float, float]:
    health_mgr = get_provider_health_manager()
    if timeout is None:
        return health_mgr.get_timeouts()
    if isinstance(timeout, (int, float)):
        conn_to = max(health_mgr.connect_timeout, 10.0) if float(timeout) > 10.0 else health_mgr.connect_timeout
        return (conn_to, float(timeout))
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    return health_mgr.get_timeouts()


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


def _post_json(url: str, payload: dict, timeout, headers: Optional[dict] = None) -> dict:
    timeout = _normalize_timeout(timeout)
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()

def _resolve_think(think: Optional[bool]) -> Optional[bool]:
    """Eksplisit menang. Kalau None, AIRA_DISABLE_THINKING=1 di .env mematikan thinking global."""
    if think is not None:
        return think

    flag = (os.getenv("VERA_DISABLE_THINKING") or os.getenv("AIRA_DISABLE_THINKING", "")).strip().lower()
    return False if flag in ("1", "true", "yes", "on") else None


def _thinking_extras(provider: str, think: Optional[bool]) -> dict:
    """Parameter tambahan untuk mematikan reasoning di provider OpenAI-compatible.
    Nama parameter berbeda per provider/model; kalau ditolak (400/422) pemanggil
    mengulang tanpa parameter ini."""
    if think is not False:
        return {}

    if provider == "nvidia":
        return {"chat_template_kwargs": {"enable_thinking": False}}

    if provider == "openrouter":
        return {"reasoning": {"enabled": False}}

    return {}


def _sanitize_messages_for_provider(provider: str, messages: list) -> list:
    """
    Sanitize messages before sending to provider:
    For Gemini: Google's OpenAI API strictly requires thought_signature on every tool_call in assistant history.
    """
    if provider != "gemini" or not messages:
        return messages

    sanitized = []
    last_extra = None
    for msg in messages:
        if not isinstance(msg, dict):
            sanitized.append(msg)
            continue
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tcs = msg["tool_calls"]
            msg_copy = dict(msg)
            sig_extra = None
            for tc in tcs:
                if isinstance(tc, dict) and tc.get("extra_content"):
                    sig_extra = tc["extra_content"]
                    break
            if not sig_extra and msg.get("extra_content"):
                sig_extra = msg["extra_content"]
            if not sig_extra and last_extra:
                sig_extra = last_extra

            if sig_extra:
                last_extra = sig_extra
                new_tcs = []
                for tc in tcs:
                    if isinstance(tc, dict):
                        tc_copy = dict(tc)
                        if not tc_copy.get("extra_content"):
                            tc_copy["extra_content"] = sig_extra
                        new_tcs.append(tc_copy)
                    else:
                        new_tcs.append(tc)
                msg_copy["tool_calls"] = new_tcs
            sanitized.append(msg_copy)
        else:
            sanitized.append(msg)
    return sanitized


# ============================================================ adapters

def _chat_openai_compatible(
    provider, model_id, messages, tools, temperature, max_tokens, timeout, think=None, record_telemetry=True,
) -> dict:
    api_key = _resolve_api_key(provider)

    if not api_key:
        return {
            "error": f"API key {provider} belum diset (.env {PROVIDER_ENV_KEYS.get(provider, 'API_KEY')}).",
            "error_type": "other",
        }

    url = f"{_endpoint(provider)}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "VERA Platform"

    clean_messages = _sanitize_messages_for_provider(provider, messages)
    payload: dict = {"model": model_id, "messages": clean_messages}
    cleaned_tools = _sanitize_tools(tools)
    if cleaned_tools:
        payload["tools"] = cleaned_tools
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    extras = _thinking_extras(provider, think)
    payload.update(extras)

    try:
        try:
            data = _post_json(url, payload, timeout, headers=headers)
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)

            if extras and status in (400, 422):
                logger.warning(
                    "Provider %s menolak parameter thinking-off - mengulang tanpa parameter itu.", provider,
                )
                for key in extras:
                    payload.pop(key, None)
                data = _post_json(url, payload, timeout, headers=headers)
            else:
                raise

        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        msg = choice.get("message") or {}
        if not msg.get("content") and msg.get("reasoning_content"):
            msg["content"] = msg.get("reasoning_content")
        return {"message": _normalize_message(msg), "usage": data.get("usage")}

    except requests.exceptions.RequestException as exc:
        return _request_error(provider, url, exc, model_id=model_id, record_telemetry=record_telemetry)
    except ValueError as exc:
        return {"error": f"{url} membalas body bukan JSON valid: {exc}", "error_type": "other"}

# ============================================================ streaming (Sprint 2.5)

# Status HTTP yang wajar untuk "provider/model ini tidak mendukung stream".
_STREAM_UNSUPPORTED_STATUSES = {400, 404, 405, 415, 422, 501}


def _is_cancelled(cancel_event) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _cancelled_result() -> dict:
    return {"error": "Dibatalkan oleh user.", "error_type": "cancelled", "cancelled": True}


def _safe_delta(on_delta, text: str) -> None:
    """Sink yang rusak tidak boleh menjatuhkan panggilan LLM."""
    if not text:
        return
    try:
        on_delta(text)
    except Exception:
        logger.exception("on_delta gagal (diabaikan).")


def _open_stream(url: str, payload: dict, timeout, headers: Optional[dict] = None):
    """
    POST dengan stream=True. Status >= 400: body error dibaca penuh (kecil)
    supaya exc.response.text tersedia, lalu HTTPError dilempar. Status OK:
    response dikembalikan TERBUKA - pemanggil wajib menutupnya.
    """
    timeout = _normalize_timeout(timeout)
    response = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)

    if response.status_code >= 400:
        try:
            response.content
        except requests.exceptions.RequestException:
            pass
        response.close()
        response.raise_for_status()

    return response


def _http_error_body(exc: requests.exceptions.HTTPError) -> str:
    try:
        return exc.response.text.lower() if exc.response is not None else ""
    except Exception:
        return ""


def _stream_unsupported(exc: requests.exceptions.HTTPError, body: str) -> bool:
    status = getattr(exc.response, "status_code", None)
    return status in _STREAM_UNSUPPORTED_STATUSES and "stream" in body


def _stream_unsupported_result(label: str, exc: Exception) -> dict:
    return {"error": f"{label} menolak streaming: {exc}", "error_type": "stream_unsupported"}


def _stream_error_type(err) -> str:
    code = err.get("code") if isinstance(err, dict) else None
    return "rate_limit" if str(code) in ("429", "rate_limit_exceeded") else "other"


def _consume_sse(response, on_delta, cancel_event) -> dict:
    """
    Baca SSE OpenAI-compatible. Teks langsung diteruskan; tool_calls datang
    sebagai fragmen (per index) dan digabung. 'finished' baru True kalau
    finish_reason atau [DONE] diterima - stream yang putus sebelum itu
    dianggap error "connection" (bukan jawaban parsial yang dianggap utuh).
    """
    parts: list[str] = []
    reasoning_parts: list[str] = []
    slots: dict = {}
    order: list = []
    last_key = None
    usage = None
    finished = False

    delta_global_extra = None
    for raw in response.iter_lines(chunk_size=None):
        if _is_cancelled(cancel_event):
            return _cancelled_result()

        if not raw:
            continue

        line = raw.decode("utf-8", errors="replace").strip()

        # komentar keep-alive (": OPENROUTER PROCESSING"), "event:", "id:" dst.
        if not line.startswith("data:"):
            continue

        data = line[5:].strip()

        if data == "[DONE]":
            finished = True
            break

        try:
            obj = json.loads(data)
        except ValueError:
            return {"error": f"Chunk SSE bukan JSON valid: {data[:200]}", "error_type": "other"}

        if not isinstance(obj, dict):
            continue

        if obj.get("error"):
            err = obj["error"]
            return {"error": f"Provider mengirim error di tengah stream: {err}", "error_type": _stream_error_type(err)}

        if obj.get("usage"):
            usage = obj["usage"]

        for choice in obj.get("choices") or []:
            delta = choice.get("delta") or {}

            if delta.get("extra_content"):
                delta_global_extra = delta["extra_content"]

            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
                _safe_delta(on_delta, text)

            reasoning_text = delta.get("reasoning_content")
            if isinstance(reasoning_text, str) and reasoning_text:
                reasoning_parts.append(reasoning_text)

            for fragment in delta.get("tool_calls") or []:
                key = fragment.get("index")
                if key is None:  # sebagian provider tidak mengirim index
                    key = fragment.get("id") or last_key or 0
                last_key = key

                slot = slots.get(key)
                if slot is None:
                    slot = slots[key] = {"id": None, "name": "", "arguments": "", "extra_content": None}
                    order.append(key)

                if fragment.get("id"):
                    slot["id"] = fragment["id"]
                if fragment.get("extra_content"):
                    slot["extra_content"] = fragment["extra_content"]

                function = fragment.get("function") or {}
                name = function.get("name")
                if name and name != slot["name"]:
                    slot["name"] += name
                if function.get("arguments"):
                    slot["arguments"] += function["arguments"]

            reason = choice.get("finish_reason")
            if reason == "error":
                return {"error": "Provider mengakhiri stream dengan finish_reason=error.", "error_type": "other"}
            if reason:
                finished = True  # jangan break: chunk usage bisa menyusul

    if not finished:
        return {
            "error": "Stream provider berakhir sebelum selesai (finish_reason/[DONE] tidak diterima).",
            "error_type": "connection",
        }

    tool_calls = []
    for index, key in enumerate(order):
        if not slots[key]["name"]:
            continue
        entry = {
            "id": slots[key]["id"] or f"call_{index}",
            "type": "function",
            "function": {"name": slots[key]["name"], "arguments": slots[key]["arguments"]},
        }
        extra = slots[key].get("extra_content") or delta_global_extra
        if extra:
            entry["extra_content"] = extra
        tool_calls.append(entry)

    # Gemini requires thought_signature on every tool_call in multi-tool responses
    first_extra = next((tc["extra_content"] for tc in tool_calls if tc.get("extra_content")), None) or delta_global_extra
    if first_extra:
        for tc in tool_calls:
            if not tc.get("extra_content"):
                tc["extra_content"] = first_extra

    if not parts and reasoning_parts:
        parts = reasoning_parts

    message = _normalize_message({"role": "assistant", "content": "".join(parts), "tool_calls": tool_calls})
    if first_extra and "extra_content" not in message:
        message["extra_content"] = first_extra
    return {"message": message, "usage": usage, "streamed": True}


def _chat_openai_stream(
    provider, model_id, messages, tools, temperature, max_tokens, timeout, on_delta, cancel_event, think=None,
) -> dict:
    api_key = _resolve_api_key(provider)

    if not api_key:
        return {
            "error": f"API key {provider} belum diset (.env {PROVIDER_ENV_KEYS.get(provider, 'API_KEY')}).",
            "error_type": "other",
        }

    url = f"{_endpoint(provider)}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "VERA Platform"

    clean_messages = _sanitize_messages_for_provider(provider, messages)
    payload: dict = {
        "model": model_id, "messages": clean_messages, "stream": True,
        "stream_options": {"include_usage": True},
    }
    cleaned_tools = _sanitize_tools(tools)
    if cleaned_tools:
        payload["tools"] = cleaned_tools
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    extras = _thinking_extras(provider, think)
    payload.update(extras)

    try:
        response = None

        for _ in range(3):
            try:
                response = _open_stream(url, payload, timeout, headers=headers)
                break
            except requests.exceptions.HTTPError as exc:
                body = _http_error_body(exc)
                status = getattr(exc.response, "status_code", None)

                if "stream_options" in payload and ("stream_options" in body or "include_usage" in body):
                    logger.warning("Provider %s menolak stream_options - mengulang tanpa usage stream.", provider)
                    payload.pop("stream_options")
                    continue

                if extras and status in (400, 422) and not _stream_unsupported(exc, body):
                    logger.warning("Provider %s menolak parameter thinking-off - mengulang tanpa itu.", provider)
                    for key in extras:
                        payload.pop(key, None)
                    extras = {}
                    continue

                if _stream_unsupported(exc, body):
                    return _stream_unsupported_result(provider, exc)

                raise

        if response is None:
            return {"error": "Gagal membuka stream ke provider.", "error_type": "other"}

        with closing(response):
            content_type = (response.headers.get("Content-Type") or "").lower()

            # Provider mengabaikan stream=true dan membalas JSON biasa.
            if "event-stream" not in content_type and "json" in content_type:
                data = response.json()
                choices = data.get("choices") or [{}]
                choice = choices[0] if choices else {}
                return {
                    "message": _normalize_message(choice.get("message") or {}),
                    "usage": data.get("usage"),
                    "streamed": False,
                }

            return _consume_sse(response, on_delta, cancel_event)

    except requests.exceptions.RequestException as exc:
        return _request_error(provider, url, exc, model_id=model_id)
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
        record_telemetry: bool = True,
    ) -> dict:
        """
        Return {"message":..., "usage":...} atau {"error":..., "error_type":
        "timeout"|"connection"|"rate_limit"|"circuit_open"|"other"}. Tidak pernah raise.
        """
        provider = (provider or "").strip().lower()
        health_mgr = get_provider_health_manager()

        if record_telemetry and not health_mgr.acquire_probe_slot(provider):
            logger.warning("CIRCUIT BREAKER OPEN | Fast failing chat to provider '%s'", provider)
            return {
                "error": f"Circuit breaker OPEN untuk provider '{provider}'. Penyedia layanan sedang mengalami gangguan atau timeout berulang.",
                "error_type": "circuit_open",
            }

        think = _resolve_think(think)
        t0 = time.time()
        probe_settled = False

        try:
            if provider in PROVIDER_ENV_KEYS:
                result = _chat_openai_compatible(
                    provider, model, messages, tools, temperature, max_tokens,
                    timeout or DEFAULT_LLM_TIMEOUT, think, record_telemetry=record_telemetry,
                )
            else:
                result = {"error": f"Provider '{provider}' tidak dikenal.", "error_type": "other"}

            if "error" not in result and not result.get("cancelled"):
                if record_telemetry:
                    health_mgr.record_success(provider, time.time() - t0, model_id=model)
                probe_settled = True
            elif "error" in result:
                probe_settled = True

            return result
        finally:
            if not probe_settled and record_telemetry:
                health_mgr.release_probe_slot(provider)

    @staticmethod
    def chat_stream(
        provider: str,
        model: str,
        messages: list,
        tools: Optional[list] = None,
        *,
        on_delta,
        cancel_event=None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        think: Optional[bool] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        Streaming NYATA. on_delta(text) dipanggil untuk tiap potongan teks baru.
        Tidak pernah raise.
        """
        provider = (provider or "").strip().lower()
        health_mgr = get_provider_health_manager()

        if not health_mgr.acquire_probe_slot(provider):
            logger.warning("CIRCUIT BREAKER OPEN | Fast failing chat_stream to provider '%s'", provider)
            return {
                "error": f"Circuit breaker OPEN untuk provider '{provider}'. Penyedia layanan sedang mengalami gangguan atau timeout berulang.",
                "error_type": "circuit_open",
            }

        think = _resolve_think(think)
        t0 = time.time()
        probe_settled = False

        try:
            if provider in PROVIDER_ENV_KEYS:
                result = _chat_openai_stream(
                    provider, model, messages, tools, temperature, max_tokens,
                    timeout or DEFAULT_LLM_TIMEOUT, on_delta, cancel_event, think,
                )
            else:
                result = {"error": f"Provider '{provider}' tidak dikenal.", "error_type": "other"}

            if "error" not in result and not result.get("cancelled"):
                health_mgr.record_success(provider, time.time() - t0, model_id=model)
                probe_settled = True
            elif "error" in result:
                probe_settled = True

            return result

        except Exception as exc:
            logger.exception("chat_stream %s gagal tak terduga", provider)
            health_mgr.record_failure(provider, FailureCategory.OTHER, str(exc), model_id=model)
            probe_settled = True
            return {"error": f"Streaming gagal: {exc}", "error_type": "other"}
        finally:
            if not probe_settled:
                health_mgr.release_probe_slot(provider)
        
    @staticmethod
    def health_check(provider: str, model_id: Optional[str] = None) -> dict:
        provider = (provider or "").strip().lower()

        try:
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


def _call_sink(fn, *args) -> None:
    try:
        fn(*args)
    except Exception:
        logger.exception("stream sink gagal (diabaikan).")


def _stream_once(model: SelectedModel, messages: list, tools: list, stream, cancel_event) -> dict:
    """SATU request streaming ke `model`. sink.start() dipanggil tiap request."""
    _call_sink(stream.start, {
        "id": model.id, "display_name": model.display_name,
        "provider": model.provider, "fallback_from": model.fallback_from,
    })

    result = ProviderClient.chat_stream(
        provider=model.provider, model=model.model_id, messages=messages, tools=tools,
        on_delta=lambda text: _call_sink(stream.delta, text), cancel_event=cancel_event,
    )

    if result.get("error_type") == "stream_unsupported":
        logger.warning("Model '%s' menolak streaming - mengulang non-streaming.", model.display_name)
        result = ProviderClient.chat(
            provider=model.provider, model=model.model_id, messages=messages, tools=tools,
        )
        if "error" not in result:
            result["streamed"] = False

    return result


def _attempt(model: SelectedModel, messages: list, tools: list, retries: int, stream=None, cancel_event=None) -> dict:
    def call() -> dict:
        if stream is None:
            return ProviderClient.chat(
                provider=model.provider, model=model.model_id, messages=messages, tools=tools,
            )
        return _stream_once(model, messages, tools, stream, cancel_event)

    result = call()
    if result.get("error_type") in NON_RETRYABLE_ERROR_TYPES:
        return result

    attempt = 0
    while "error" in result and result.get("error_type") in TRANSIENT_ERROR_TYPES and attempt < retries:
        attempt += 1
        logger.info("Retry %d/%d ke '%s' (%s).", attempt, retries, model.display_name, result["error_type"])
        time.sleep(min(2 * attempt, 5))
        result = call()
        if result.get("error_type") in NON_RETRYABLE_ERROR_TYPES:
            return result

    return result


def call_model(
    messages: list, tools: list, selected_model=None, *,
    policy=None, router=None, stream=None, cancel_event=None,
) -> dict:
    """
    Titik masuk planner/auto_extract. `selected_model` (SelectedModel/dict)
    berasal dari Model Router; None -> default label general.
    Hasil sukses menyertakan key "model" (model yang benar-benar dipakai).

    stream (Sprint 2.5): sink dengan start(model: dict) dan delta(text: str).
    None (default) = jalur non-streaming lama, TIDAK berubah. Kalau diisi,
    retry/fallback/cek context tetap berlaku; tiap request ke provider
    (termasuk retry & fallback) memanggil sink.start() lagi. Hasil sukses
    membawa "streamed" (True bila provider benar-benar streaming). Stop
    (cancel_event) -> {"error", "error_type": "cancelled", "cancelled": True}
    tanpa retry/fallback.
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

    result = _attempt(
        selected, messages, tools, retries=policy.retry_count(),
        stream=stream, cancel_event=cancel_event,
    )

    if "error" not in result:
        result["model"] = selected.to_dict()
        return result

    if result.get("cancelled"):
        return {"error": result["error"], "error_type": "cancelled", "cancelled": True}

    _publish_model_failed(selected, result)

    error_type = result.get("error_type", "other")
    health_mgr = get_provider_health_manager()
    is_provider_degraded = (error_type == "circuit_open") or (not health_mgr.is_provider_available(selected.provider))

    req_caps = ["supports_tool_calling"] if tools else None
    fallback = policy.on_provider_failure(selected, error_type, required_capabilities=req_caps)
    if fallback is None:
        if is_provider_degraded:
            return {
                "error": f"Layanan AI tidak tersedia: Provider '{selected.provider}' sedang mengalami gangguan (circuit breaker OPEN) dan tidak ada provider alternatif independen yang aktif/terkonfigurasi.",
                "error_type": "circuit_open",
            }
        return {"error": result["error"], "error_type": error_type}

    # If the provider is degraded and fallback shares that same provider, skip attempting it
    if is_provider_degraded and fallback.provider == selected.provider:
        logger.warning(
            "PROVIDER CIRCUIT OPEN | Fast-failing same-provider fallback '%s' (%s).",
            fallback.display_name, fallback.provider,
        )
        fb_result = {
            "error": f"Layanan AI tidak tersedia: Provider '{selected.provider}' sedang mengalami gangguan (circuit breaker OPEN) dan tidak ada provider alternatif independen yang aktif/terkonfigurasi.",
            "error_type": "circuit_open",
        }
    else:
        fb_result = _attempt(fallback, messages, tools, retries=0, stream=stream, cancel_event=cancel_event)

    if fb_result.get("cancelled"):
        return {"error": fb_result["error"], "error_type": "cancelled", "cancelled": True}

    if "error" not in fb_result:
        fb_result["model"] = fallback.to_dict()
        return fb_result

    _publish_model_failed(fallback, fb_result)

    # Multi-provider fallback chain: If fallback model fails with not_found, model_missing,
    # or circuit_open, recover by attempting subsequent candidates in the enabled models chain.
    if fb_result.get("error_type") in ("not_found", "model_missing", "circuit_open") and hasattr(policy, "fallback_candidates"):
        attempted = {selected.id, fallback.id}
        for cand_row in policy.fallback_candidates(exclude_ids=attempted):
            cand_model = SelectedModel.from_row(cand_row, fallback_from=selected.id) if isinstance(cand_row, dict) else cand_row
            
            # Fast fail check: If provider circuit is OPEN or is degraded provider, do not attempt candidates
            if is_provider_degraded and cand_model.provider == selected.provider:
                continue
            if not health_mgr.is_provider_available(cand_model.provider):
                logger.info(
                    "CIRCUIT OPEN SKIP | Skipping candidate '%s' on degraded provider '%s'.",
                    cand_model.display_name, cand_model.provider,
                )
                continue
            if tools and not getattr(cand_model, "supports_tool_calling", True):
                logger.info(
                    "TOOL CAPABILITY SKIP | Skipping candidate '%s' lacking tool calling.",
                    cand_model.display_name,
                )
                continue

            logger.warning("FALLBACK CHAIN RECOVERY | %s -> %s", fallback.display_name, cand_model.display_name)
            try:
                event_bus.publish(
                    "model.fallback", agent="POLICY",
                    data={"from": selected.id, "to": cand_model.id, "reason": "fallback_chain_recovery"},
                )
            except Exception:
                pass
            cand_res = _attempt(cand_model, messages, tools, retries=0, stream=stream, cancel_event=cancel_event)
            if cand_res.get("cancelled"):
                return {"error": cand_res["error"], "error_type": "cancelled", "cancelled": True}
            if "error" not in cand_res:
                cand_res["model"] = cand_model.to_dict()
                return cand_res
            _publish_model_failed(cand_model, cand_res)

    return {"error": fb_result["error"]}


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