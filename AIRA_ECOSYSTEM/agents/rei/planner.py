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

FIX (anti-loop tool call):
Sebelumnya planner cuma berhenti kalau tool_count >= MAX_TOOL_CALLS
(10x) tanpa peduli apakah tool yang sama dipanggil berulang-ulang
dengan argumen identik (mis. web_search gagal terus tapi tetap
dicoba lagi sampai limit tercapai). Sekarang setiap signature
(nama tool + argumen) dilacak per giliran - kalau sudah diulang
lebih dari MAX_REPEATED_IDENTICAL_CALLS kali, tool call berikutnya
dengan signature yang sama otomatis DILEWATI dan model diberi tahu
supaya berhenti mencoba, bukan terus mengulang sampai limit keras
tercapai.
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

# Kalau tool+argumen yang PERSIS SAMA dipanggil lebih dari ini kali
# dalam satu giliran, panggilan berikutnya otomatis dilewati alih-alih
# dieksekusi ulang. Ini mencegah loop (mis. web_search yang terus
# gagal) menghabiskan seluruh MAX_TOOL_CALLS tanpa progres.
MAX_REPEATED_IDENTICAL_CALLS = 2


class Planner:

    def __init__(self, tool_schemas, tool_category=None, dangerous_tools=None):
        self.tool_schemas = tool_schemas
        self.tool_category = tool_category or {}
        self.dangerous_tools = dangerous_tools or set()

    def run(self, user_input, memory, tool_executor, on_event=None):
        """
        on_event: Optional[Callable[[str, dict], None]] - dipanggil sync
        untuk tiap event realtime (thinking/tool_start/tool_progress/
        tool_finish). None (default) = tidak ada perubahan perilaku,
        dipakai oleh alur REST lama yang tidak butuh streaming.
        """
        def emit(event_type, payload):
            if on_event:
                try:
                    on_event(event_type, payload)
                except Exception:
                    logger.exception("on_event callback error (diabaikan)")

        steps = []
        memory.add_user(user_input)

        emit("thinking", {"message": "Menganalisis permintaan..."})

        system_prompt = build_system_prompt(time_context_block() + build_context_snippet())

        response = self._call_with_retry(memory.get_messages(system_prompt))

        if "error" in response:
            emit("error", {"message": response["error"]})
            return {
                "answer": f"Terjadi error saat menghubungi model: {response['error']}",
                "steps": steps, "token_usage": None, "error": True,
            }

        self._track_usage(memory, response)

        tool_count = 0
        # Melacak berapa kali signature (nama tool + argumen) tertentu
        # sudah dipanggil DALAM GILIRAN INI - direset tiap kali run()
        # dipanggil ulang (giliran baru), bukan lintas sesi.
        call_signatures = {}

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

            emit("thinking", {"message": f"Menggunakan {len(tool_calls)} tool..."})

            for call in tool_calls:
                if tool_count >= MAX_TOOL_CALLS:
                    steps.append({"type": "limit_reached", "message": "Batas jumlah tool call tercapai."})
                    emit("error", {"message": "Batas jumlah tool call tercapai."})
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

                # ------------------------------------------------------
                # GUARD ANTI-LOOP: tool+argumen identik diulang terus
                # ------------------------------------------------------
                signature = f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                call_signatures[signature] = call_signatures.get(signature, 0) + 1

                if call_signatures[signature] > MAX_REPEATED_IDENTICAL_CALLS:
                    logger.warning(
                        "Tool '%s' dilewati - dipanggil berulang (%dx) dengan argumen identik.",
                        name, call_signatures[signature],
                    )
                    steps.append({
                        "type": "tool_call",
                        "name": name,
                        "category": category,
                        "arguments": arguments,
                        "success": False,
                        "duration": 0,
                        "result_preview": "dilewati (dipanggil berulang tanpa hasil baru)",
                    })
                    emit("tool_finish", {"name": name, "category": category, "success": False, "duration": 0})
                    memory.add_tool_result(
                        json.dumps({
                            "success": False,
                            "error": (
                                "Tool ini sudah dipanggil berulang kali dengan argumen yang "
                                "sama tanpa hasil baru. JANGAN memanggilnya lagi dengan "
                                "argumen ini. Jawab pertanyaan user berdasarkan pengetahuan "
                                "yang sudah ada, atau sampaikan bahwa informasi tidak "
                                "berhasil ditemukan."
                            ),
                        }),
                        tool_call_id=call.get("id"),
                    )
                    tool_count += 1
                    continue
                # ------------------------------------------------------

                if name in self.dangerous_tools:
                    steps.append({"type": "confirmation_required", "name": name, "category": category, "arguments": arguments})
                    emit("tool_finish", {"name": name, "category": category, "success": False, "skipped": True})
                    memory.add_tool_result(
                        json.dumps({"success": False, "error": "Tool ini butuh konfirmasi manual, dilewati otomatis."}),
                        tool_call_id=call.get("id"),
                    )
                    tool_count += 1
                    continue

                emit("tool_start", {"name": name, "category": category, "arguments": arguments})
                emit("tool_progress", {"name": name, "category": category, "message": f"Menjalankan {name}..."})

                step_start = time.perf_counter()
                result = tool_executor(name, arguments)
                step_duration = time.perf_counter() - step_start

                tool_count += 1

                steps.append({
                    "type": "tool_call", "name": name, "category": category,
                    "arguments": arguments, "success": bool(result.get("success")),
                    "duration": round(step_duration, 3), "result_preview": _preview(result),
                })

                emit("tool_finish", {
                    "name": name, "category": category,
                    "success": bool(result.get("success")),
                    "duration": round(step_duration, 3),
                })

                memory.add_tool_result(json.dumps(result, ensure_ascii=False), tool_call_id=call.get("id"))

            emit("thinking", {"message": "Menyusun jawaban..."})

            response = self._call_with_retry(memory.get_messages(system_prompt))

            if "error" in response:
                emit("error", {"message": response["error"]})
                return {
                    "answer": f"Terjadi error saat menghubungi model: {response['error']}",
                    "steps": steps,
                    "token_usage": memory.token_tracker.last_usage,
                    "session_token_usage": memory.token_tracker.as_dict(),
                    "error": True,
                }

            self._track_usage(memory, response)

    def _track_usage(self, memory, response):
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