"""
agents/rei/planner.py — REI (Reasoning & Executive Intelligence).
Port dari loop agen agent/core/engine.py::run() / engine_web.py::run_web(),
dipersempit: REI cuma mikir & memutuskan, eksekusi tool fisik lewat
callback tool_executor yang di-inject orchestrator (Dependency Inversion).

FIX (Phase 0 Stabilization - token tracker):
Sebelumnya usage dari call_model() cuma dikembalikan di response akhir
(response.get("usage") - HANYA usage giliran TERAKHIR), padahal satu
input user bisa memicu beberapa kali call_model() kalau ada tool-call
berantai. Sekarang tiap kali call_model() sukses, usage-nya langsung
ditambahkan ke memory.token_tracker (kumulatif per SESI, bukan cuma
per panggilan API), sesuai perilaku sistem lama.
"""

import json
import time
import logging

from agents.rei.provider_client import call_model, EMPTY_RESPONSE_MARKER
from agents.rei.auto_extract import extract_and_save_facts_async
from core.persona import build_system_prompt
from core.time_utils import time_context_block
from core.memory import build_context_snippet

logger = logging.getLogger("aira.rei.planner")

MAX_TOOL_CALLS = 10
MAX_EMPTY_RESPONSE_RETRIES = 1


class Planner:

    def __init__(self, tool_schemas, tool_category=None, dangerous_tools=None):
        self.tool_schemas = tool_schemas
        self.tool_category = tool_category or {}
        self.dangerous_tools = dangerous_tools or set()

    def run(self, user_input, memory, tool_executor):
        steps = []
        memory.add_user(user_input)

        system_prompt = build_system_prompt(time_context_block() + build_context_snippet())

        response = self._call_with_retry(memory.get_messages(system_prompt))

        if "error" in response:
            return {
                "answer": f"Terjadi error saat menghubungi model: {response['error']}",
                "steps": steps, "token_usage": None, "error": True,
            }

        self._track_usage(memory, response)

        tool_count = 0

        while True:
            message = response.get("message", {})
            memory.add_message(message)

            tool_calls = message.get("tool_calls", [])

            if not tool_calls:
                answer = message.get("content", "")
                extract_and_save_facts_async(user_input, answer)
                return {
                    "answer": answer,
                    "steps": steps,
                    "token_usage": memory.token_tracker.last_usage,
                    "session_token_usage": memory.token_tracker.as_dict(),
                    "error": False,
                }

            for call in tool_calls:
                if tool_count >= MAX_TOOL_CALLS:
                    steps.append({"type": "limit_reached", "message": "Batas jumlah tool call tercapai."})
                    return {
                        "answer": "Saya menghentikan proses karena jumlah observasi sudah mencapai batas.",
                        "steps": steps,
                        "token_usage": memory.token_tracker.last_usage,
                        "session_token_usage": memory.token_tracker.as_dict(),
                        "error": False,
                    }

                function = call.get("function", {})
                name = function.get("name")
                arguments = function.get("arguments", {})

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                category = self.tool_category.get(name, "tool")

                if name in self.dangerous_tools:
                    steps.append({"type": "confirmation_required", "name": name, "category": category, "arguments": arguments})
                    memory.add_tool_result(
                        json.dumps({"success": False, "error": "Tool ini butuh konfirmasi manual, dilewati otomatis."}),
                        tool_call_id=call.get("id"),
                    )
                    tool_count += 1
                    continue

                step_start = time.perf_counter()
                result = tool_executor(name, arguments)
                step_duration = time.perf_counter() - step_start

                tool_count += 1

                steps.append({
                    "type": "tool_call", "name": name, "category": category,
                    "arguments": arguments, "success": bool(result.get("success")),
                    "duration": round(step_duration, 3), "result_preview": _preview(result),
                })

                memory.add_tool_result(json.dumps(result, ensure_ascii=False), tool_call_id=call.get("id"))

            response = self._call_with_retry(memory.get_messages(system_prompt))

            if "error" in response:
                return {
                    "answer": f"Terjadi error saat menghubungi model: {response['error']}",
                    "steps": steps,
                    "token_usage": memory.token_tracker.last_usage,
                    "session_token_usage": memory.token_tracker.as_dict(),
                    "error": True,
                }

            self._track_usage(memory, response)

    def _track_usage(self, memory, response):
        """
        Catat usage dari SATU respons LLM ke token_tracker milik sesi
        ini. Dipanggil setelah setiap call_model() yang sukses -
        karena satu giliran user bisa memicu beberapa kali call_model()
        kalau ada tool call berantai, ini menjamin token_tracker
        mengakumulasi SEMUA panggilan dalam giliran itu, bukan cuma
        yang terakhir.
        """
        usage = response.get("usage")
        if usage:
            memory.token_tracker.add(usage)

    def _call_with_retry(self, messages, max_retries=MAX_EMPTY_RESPONSE_RETRIES):
        response = call_model(messages, self.tool_schemas)
        attempt = 0

        while (
            attempt < max_retries
            and "error" not in response
            and response.get("message", {}).get("content") == EMPTY_RESPONSE_MARKER
        ):
            attempt += 1
            logger.info("Provider balas kosong, mencoba ulang (%d/%d)...", attempt, max_retries)
            response = call_model(messages, self.tool_schemas)

        return response


def _preview(result, limit=400):
    text = json.dumps(result, ensure_ascii=False)
    return text[:limit] + "...(truncated)" if len(text) > limit else text