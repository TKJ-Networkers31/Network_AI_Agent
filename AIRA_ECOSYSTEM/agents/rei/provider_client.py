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
    "nvidia": "NVIDIA_API_KEY",
}

DEFAULT_ENDPOINTS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
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
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        return "connection"  # ChunkedEncodingError = stream terputus di tengah jalan
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

def _ollama_payload(model_id, messages, tools, temperature, max_tokens, think, stream: bool) -> dict:
    payload: dict = {"model": model_id, "messages": messages, "stream": stream}

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

    return payload


def _chat_ollama(model_id, messages, tools, temperature, max_tokens, think, timeout) -> dict:
    url = f"{_endpoint('ollama')}/api/chat"
    payload = _ollama_payload(model_id, messages, tools, temperature, max_tokens, think, stream=False)

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


def _open_stream(url: str, payload: dict, timeout: float, headers: Optional[dict] = None):
    """
    POST dengan stream=True. Status >= 400: body error dibaca penuh (kecil)
    supaya exc.response.text tersedia, lalu HTTPError dilempar. Status OK:
    response dikembalikan TERBUKA - pemanggil wajib menutupnya.
    """
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


def _chat_ollama_stream(
    model_id, messages, tools, temperature, max_tokens, think, timeout, on_delta, cancel_event,
) -> dict:
    """Ollama /api/chat stream=true: NDJSON, satu objek JSON per baris."""
    url = f"{_endpoint('ollama')}/api/chat"
    payload = _ollama_payload(model_id, messages, tools, temperature, max_tokens, think, stream=True)

    try:
        try:
            response = _open_stream(url, payload, timeout)
        except requests.exceptions.HTTPError as exc:
            body = _http_error_body(exc)
            if payload.get("tools") and "does not support tools" in body:
                logger.warning("Model '%s' tidak mendukung tools - mengulang tanpa tools.", model_id)
                payload.pop("tools")
                response = _open_stream(url, payload, timeout)
            elif _stream_unsupported(exc, body):
                return _stream_unsupported_result("Ollama", exc)
            else:
                raise

        parts: list[str] = []
        tool_calls: list = []
        usage = None
        done = False

        with closing(response):
            for raw in response.iter_lines(chunk_size=None):
                if _is_cancelled(cancel_event):
                    return _cancelled_result()

                if not raw:
                    continue

                try:
                    obj = json.loads(raw)
                except ValueError:
                    return {"error": "Ollama mengirim baris stream yang bukan JSON valid.", "error_type": "other"}

                if not isinstance(obj, dict):
                    continue

                if obj.get("error"):
                    return {"error": f"Ollama: {obj['error']}", "error_type": "other"}

                message = obj.get("message") or {}

                # 'thinking' (model reasoning) sengaja TIDAK diteruskan: sama
                # seperti jalur non-streaming, hanya 'content' yang jadi jawaban.
                text = message.get("content")
                if text:
                    parts.append(text)
                    _safe_delta(on_delta, text)

                if message.get("tool_calls"):
                    tool_calls.extend(message["tool_calls"])

                if obj.get("done"):
                    usage = _extract_ollama_usage(obj)
                    done = True
                    break

        if not done:
            return {
                "error": "Stream Ollama berakhir sebelum selesai (done=true tidak diterima).",
                "error_type": "connection",
            }

        message = _normalize_message({"role": "assistant", "content": "".join(parts), "tool_calls": tool_calls})
        return {"message": message, "usage": usage, "streamed": True}

    except requests.exceptions.RequestException as exc:
        return _request_error("ollama", url, exc)


def _consume_sse(response, on_delta, cancel_event) -> dict:
    """
    Baca SSE OpenAI-compatible. Teks langsung diteruskan; tool_calls datang
    sebagai fragmen (per index) dan digabung. 'finished' baru True kalau
    finish_reason atau [DONE] diterima - stream yang putus sebelum itu
    dianggap error "connection" (bukan jawaban parsial yang dianggap utuh).
    """
    parts: list[str] = []
    slots: dict = {}
    order: list = []
    last_key = None
    usage = None
    finished = False

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

            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
                _safe_delta(on_delta, text)

            for fragment in delta.get("tool_calls") or []:
                key = fragment.get("index")
                if key is None:  # sebagian provider tidak mengirim index
                    key = fragment.get("id") or last_key or 0
                last_key = key

                slot = slots.get(key)
                if slot is None:
                    slot = slots[key] = {"id": None, "name": "", "arguments": ""}
                    order.append(key)

                if fragment.get("id"):
                    slot["id"] = fragment["id"]

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

    tool_calls = [
        {
            "id": slots[key]["id"] or f"call_{index}",
            "type": "function",
            "function": {"name": slots[key]["name"], "arguments": slots[key]["arguments"]},
        }
        for index, key in enumerate(order)
        if slots[key]["name"]
    ]

    message = _normalize_message({"role": "assistant", "content": "".join(parts), "tool_calls": tool_calls})
    return {"message": message, "usage": usage, "streamed": True}


def _chat_openai_stream(
    provider, model_id, messages, tools, temperature, max_tokens, timeout, on_delta, cancel_event,
) -> dict:
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

    payload: dict = {
        "model": model_id, "messages": messages, "stream": True,
        "stream_options": {"include_usage": True},   # usage di chunk terakhir
    }
    if tools:
        payload["tools"] = tools
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        try:
            response = _open_stream(url, payload, timeout, headers=headers)
        except requests.exceptions.HTTPError as exc:
            body = _http_error_body(exc)
            if "stream_options" in body or "include_usage" in body:
                logger.warning("Provider %s menolak stream_options - mengulang tanpa usage stream.", provider)
                payload.pop("stream_options")
                response = _open_stream(url, payload, timeout, headers=headers)
            elif _stream_unsupported(exc, body):
                return _stream_unsupported_result(provider, exc)
            else:
                raise

        with closing(response):
            content_type = (response.headers.get("Content-Type") or "").lower()

            # Provider mengabaikan stream=true dan membalas JSON biasa:
            # perlakukan sebagai non-streaming (jujur: streamed=False).
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
        Streaming NYATA. on_delta(text) dipanggil untuk tiap potongan teks yang
        BARU diterima dari provider. Return sama seperti chat() plus
        "streamed": True (False bila provider membalas JSON biasa), atau
        {"error", "error_type": ... | "stream_unsupported" | "cancelled"}.
        Tidak pernah raise.
        """
        provider = (provider or "").strip().lower()

        try:
            if provider == "ollama":
                return _chat_ollama_stream(
                    model, messages, tools, temperature, max_tokens, think,
                    timeout or 300, on_delta, cancel_event,
                )

            if provider in PROVIDER_ENV_KEYS:
                return _chat_openai_stream(
                    provider, model, messages, tools, temperature, max_tokens,
                    timeout or 120, on_delta, cancel_event,
                )

            return {"error": f"Provider '{provider}' tidak dikenal.", "error_type": "other"}

        except Exception as exc:
            logger.exception("chat_stream %s gagal tak terduga", provider)
            return {"error": f"Streaming gagal: {exc}", "error_type": "other"}

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
    attempt = 0

    while "error" in result and result.get("error_type") in TRANSIENT_ERROR_TYPES and attempt < retries:
        attempt += 1
        logger.info("Retry %d/%d ke '%s' (%s).", attempt, retries, model.display_name, result["error_type"])
        time.sleep(min(2 * attempt, 5))
        result = call()

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

    fallback = policy.on_provider_failure(selected, result.get("error_type", "other"))
    if fallback is None:
        return {"error": result["error"]}

    result = _attempt(fallback, messages, tools, retries=0, stream=stream, cancel_event=cancel_event)

    if result.get("cancelled"):
        return {"error": result["error"], "error_type": "cancelled", "cancelled": True}

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