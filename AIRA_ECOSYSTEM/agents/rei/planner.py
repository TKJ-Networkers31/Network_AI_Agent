"""
agents/rei/planner.py — REI (Reasoning & Executive Intelligence).

Loop: LLM -> tool calls -> LLM ... sampai jawaban final.

Event realtime dipublish LANGSUNG ke Event Bus (core/events.py) dengan
nama bus (thinking.start, tool.start/progress/finish, system.error).
WebSocket menerimanya lewat api/ws_bridge.py. Tidak ada lagi callback
on_event: hanya ada SATU sistem event.

Interaction schema (DIO):
  Tool di DIO_SCHEMA_TOOLS (request_structured_input,
  request_location_permission) mengembalikan 'interaction_schema'. Planner
  menyimpannya sebagai pending_interaction_schema dan menyertakannya di
  setiap return, sehingga sampai ke frontend.

session_id:
  Tool di SESSION_AWARE_TOOLS menerima session_id yang disisipkan planner
  dari memory.session_id (SessionMemory). LLM tidak diminta menyebutnya,
  dan 'arguments' di steps tetap argumen asli LLM.

Stop:
  cancel_event (threading.Event) dicek di titik aman: sebelum/sesudah
  panggilan LLM dan sebelum tiap tool. Kalau set, run() return
  {"cancelled": True} tanpa ekstraksi memori otomatis.

Model:
  'selected_model' dari Model Router diteruskan apa adanya ke call_model().
  REI tidak pernah memilih model.
"""

import json
import time
import logging

from agents.rei.provider_client import call_model, EMPTY_RESPONSE_MARKER
from agents.rei.auto_extract import extract_and_save_facts_async
from core.events import EventNames, event_bus
from core.persona import get_engine
from core.time_utils import time_context_block
from core.memory import build_context_snippet

logger = logging.getLogger("aira.rei.planner")

MAX_TOOL_CALLS = 10
MAX_EMPTY_RESPONSE_RETRIES = 1
MAX_REPEATED_IDENTICAL_CALLS = 2

# Tool yang hasilnya membawa interaction_schema untuk dirender frontend.
DIO_SCHEMA_TOOLS = {"request_structured_input", "request_location_permission"}

# Tool yang butuh session_id (diisi planner, BUKAN diminta dari LLM).
SESSION_AWARE_TOOLS = {"request_location_permission"}


class Planner:

    def __init__(self, tool_schemas, tool_category=None, dangerous_tools=None):
        self.tool_schemas = tool_schemas
        self.tool_category = tool_category or {}
        self.dangerous_tools = dangerous_tools or set()

    def run(self, user_input, memory, tool_executor, cancel_event=None, selected_model=None):

        def emit(bus_event, payload):
            try:
                event_bus.publish(
                    bus_event,
                    source="REI",
                    agent="REI",
                    tool=payload.get("name") if bus_event.startswith("tool.") else None,
                    data=dict(payload),
                )
            except Exception:
                logger.exception("event_bus.publish error (diabaikan)")

        def is_cancelled():
            return cancel_event is not None and cancel_event.is_set()

        steps = []
        memory.add_user(user_input)

        pending_interaction_schema = None

        def result_dict(answer, error=False, cancelled=False):
            return {
                "answer": answer,
                "steps": steps,
                "token_usage": memory.token_tracker.last_usage,
                "session_token_usage": memory.token_tracker.as_dict(),
                "error": error,
                "interaction_schema": None if cancelled else pending_interaction_schema,
                **({"cancelled": True} if cancelled else {}),
            }

        def cancelled_result():
            logger.info("Planner dihentikan oleh user (cancel_event).")
            return result_dict("", cancelled=True)

        emit(EventNames.THINKING_START, {"message": "Menganalisis permintaan..."})

        if is_cancelled():
            return cancelled_result()

        system_prompt = get_engine().build(time_context_block() + build_context_snippet())

        response = self._call_with_retry(memory.get_messages(system_prompt), selected_model=selected_model)

        if "error" in response:
            emit(EventNames.SYSTEM_ERROR, {"message": response["error"]})
            out = result_dict(f"Terjadi error saat menghubungi model: {response['error']}", error=True)
            out["token_usage"] = None
            return out

        self._track_usage(memory, response)

        tool_count = 0
        call_signatures = {}
        session_id = getattr(memory, "session_id", None)

        while True:
            # Titik cek utama: setelah tiap jawaban LLM, sebelum tool jalan.
            if is_cancelled():
                return cancelled_result()

            message = response.get("message", {})
            memory.add_message(message)

            tool_calls = message.get("tool_calls", [])

            if not tool_calls:
                answer = message.get("content", "")
                extract_and_save_facts_async(user_input, answer)
                return result_dict(answer)

            emit(EventNames.THINKING_START, {"message": f"Menggunakan {len(tool_calls)} tool..."})

            for call in tool_calls:
                if is_cancelled():
                    return cancelled_result()

                if tool_count >= MAX_TOOL_CALLS:
                    steps.append({"type": "limit_reached", "message": "Batas jumlah tool call tercapai."})
                    emit(EventNames.SYSTEM_ERROR, {"message": "Batas jumlah tool call tercapai."})
                    return result_dict("Saya menghentikan proses karena jumlah observasi sudah mencapai batas.")

                function = call.get("function", {})
                name = function.get("name")
                arguments = function.get("arguments", {})

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                category = self.tool_category.get(name, "tool")

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
                    emit(EventNames.TOOL_FINISH, {"name": name, "category": category, "success": False, "duration": 0})
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

                if name in self.dangerous_tools:
                    steps.append({"type": "confirmation_required", "name": name, "category": category, "arguments": arguments})
                    emit(EventNames.TOOL_FINISH, {"name": name, "category": category, "success": False, "skipped": True})
                    memory.add_tool_result(
                        json.dumps({"success": False, "error": "Tool ini butuh konfirmasi manual, dilewati otomatis."}),
                        tool_call_id=call.get("id"),
                    )
                    tool_count += 1
                    continue

                emit(EventNames.TOOL_START, {"name": name, "category": category, "arguments": arguments})
                emit(EventNames.TOOL_PROGRESS, {"name": name, "category": category, "message": f"Menjalankan {name}..."})

                # FIX: session_id disisipkan planner, bukan diminta dari LLM.
                exec_args = (
                    {**arguments, "session_id": session_id}
                    if name in SESSION_AWARE_TOOLS
                    else arguments
                )

                step_start = time.perf_counter()
                result = tool_executor(name, exec_args)
                step_duration = time.perf_counter() - step_start

                tool_count += 1

                # FIX: kedua tool DIO membawa schema keluar lewat return planner.
                if (
                    name in DIO_SCHEMA_TOOLS
                    and result.get("success")
                    and result.get("interaction_schema")
                ):
                    pending_interaction_schema = result["interaction_schema"]

                steps.append({
                    "type": "tool_call", "name": name, "category": category,
                    "arguments": arguments,  # argumen asli LLM, tanpa session_id
                    "success": bool(result.get("success")),
                    "duration": round(step_duration, 3), "result_preview": _preview(result),
                })

                emit(EventNames.TOOL_FINISH, {
                    "name": name, "category": category,
                    "success": bool(result.get("success")),
                    "duration": round(step_duration, 3),
                })

                memory.add_tool_result(json.dumps(result, ensure_ascii=False), tool_call_id=call.get("id"))

            if is_cancelled():
                return cancelled_result()

            emit(EventNames.THINKING_START, {"message": "Menyusun jawaban..."})

            response = self._call_with_retry(memory.get_messages(system_prompt), selected_model=selected_model)

            if "error" in response:
                emit(EventNames.SYSTEM_ERROR, {"message": response["error"]})
                return result_dict(f"Terjadi error saat menghubungi model: {response['error']}", error=True)

            self._track_usage(memory, response)

    def _track_usage(self, memory, response):
        usage = response.get("usage")
        if usage:
            memory.token_tracker.add(usage)

    def _call_with_retry(self, messages, selected_model=None, max_retries=MAX_EMPTY_RESPONSE_RETRIES):
        response = call_model(messages, self.tool_schemas, selected_model)
        attempt = 0

        while (
            attempt < max_retries
            and "error" not in response
            and response.get("message", {}).get("content") == EMPTY_RESPONSE_MARKER
        ):
            attempt += 1
            logger.info("Provider balas kosong, mencoba ulang (%d/%d)...", attempt, max_retries)
            response = call_model(messages, self.tool_schemas, selected_model)

        return response


def _preview(result, limit=400):
    text = json.dumps(result, ensure_ascii=False)
    return text[:limit] + "...(truncated)" if len(text) > limit else text