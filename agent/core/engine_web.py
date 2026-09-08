"""
Versi "web" dari agent/core/engine.py.

KENAPA FILE TERPISAH, BUKAN EDIT engine.py:
engine.py yang lama dipakai oleh agent/main.py (mode terminal) dan
sudah bekerja dengan baik di sana (pakai UI.*, Timer, input()
untuk konfirmasi tool berbahaya). Web butuh bentuk lain: tidak ada
print ke stdout, tidak ada input() blocking, dan tiap langkah
(tool call demi tool call) perlu dikembalikan sebagai data
terstruktur supaya bisa ditampilkan di frontend.

Daripada mengubah engine.py (yang bisa merusak mode terminal),
loop agent-nya di-duplikasi di sini dalam bentuk "silent" yang
mengembalikan dict, bukan mencetak ke layar. SYSTEM_PROMPT dan
daftar TOOLS (skema function-calling) tetap di-IMPORT dari
engine.py yang lama, supaya tidak ada duplikasi besar dan kalau
kamu menambah tool baru di engine.py, otomatis kepakai juga di
web tanpa perlu ubah dua tempat.

Taruh file ini di: agent/core/engine_web.py
"""

import json
import time

from agent.core.engine import SYSTEM_PROMPT, TOOLS
from agent.core.providers import call_model
from agent.core.logger import (
    log_tool_call,
    log_tool_result,
    log_error,
)
from tools.registry import (
    TOOL_MAP,
    TOOL_CATEGORY,
    DANGEROUS_TOOLS,
    execute_tool,
)
from agent.memory_store.auto_extract import extract_and_save_facts_async


MAX_TOOL_CALLS = 10


def _track_usage(memory, response):

    usage = response.get("usage")

    if usage:
        memory.token_tracker.add(usage)


def run_web(user_input, memory):
    """
    Sama seperti run() di engine.py, tapi:
    - Tidak print apa pun / tidak pernah blocking di input()
    - Tool DANGEROUS_TOOLS otomatis DILEWATI (bukan dieksekusi)
      dengan step bertipe 'confirmation_required', supaya web
      tetap aman meski kamu nanti menambah tool berbahaya di
      DANGEROUS_TOOLS. Eksekusi manual tetap bisa lewat terminal.
    - Mengembalikan dict terstruktur, bukan string, supaya
      frontend bisa render bubble jawaban + timeline tool yang
      dipakai.

    Return:
      {
        "answer": str,
        "steps": [ {..step info..}, ... ],
        "duration": float,
        "token_usage": {...} | None,
      }
    """

    start = time.perf_counter()
    steps = []

    memory.add_user(user_input)

    response = call_model(memory.get_messages(), TOOLS)

    if "error" in response:
        return {
            "answer": f"Terjadi error saat menghubungi model: {response['error']}",
            "steps": steps,
            "duration": time.perf_counter() - start,
            "token_usage": None,
            "error": True,
        }

    _track_usage(memory, response)

    tool_count = 0

    while True:

        message = response.get("message", {})
        memory.add_message(message)

        tool_calls = message.get("tool_calls", [])

        # ------------------------------------------------------
        # SELESAI - tidak ada tool call lagi, ini jawaban final
        # ------------------------------------------------------
        if not tool_calls:

            answer = message.get("content", "")
            duration = time.perf_counter() - start

            extract_and_save_facts_async(user_input, answer)

            return {
                "answer": answer,
                "steps": steps,
                "duration": duration,
                "token_usage": memory.token_tracker.last_usage,
                "error": False,
            }

        # ------------------------------------------------------
        # JALANKAN SEMUA TOOL CALL DI GILIRAN INI
        # ------------------------------------------------------
        for call in tool_calls:

            if tool_count >= MAX_TOOL_CALLS:

                steps.append({
                    "type": "limit_reached",
                    "message": "Batas jumlah tool call tercapai.",
                })

                duration = time.perf_counter() - start

                return {
                    "answer": (
                        "Saya menghentikan proses karena jumlah "
                        "observasi sudah mencapai batas."
                    ),
                    "steps": steps,
                    "duration": duration,
                    "token_usage": memory.token_tracker.last_usage,
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

            category = TOOL_CATEGORY.get(name, "tool")

            # --------------------------------------------------
            # TOOL BERBAHAYA -> jangan auto-eksekusi di web
            # --------------------------------------------------
            if name in DANGEROUS_TOOLS:

                steps.append({
                    "type": "confirmation_required",
                    "name": name,
                    "category": category,
                    "arguments": arguments,
                })

                memory.add_tool_result(
                    json.dumps({
                        "success": False,
                        "error": (
                            "Tool ini butuh konfirmasi manual dan "
                            "dilewati otomatis di web interface."
                        ),
                    }),
                    tool_call_id=call.get("id"),
                )

                tool_count += 1
                continue

            device_name = arguments.get("device_name")

            log_tool_call(name, arguments, device_name)

            step_start = time.perf_counter()
            result = execute_tool(name, arguments)
            step_duration = time.perf_counter() - step_start

            log_tool_result(name, result)

            tool_count += 1

            steps.append({
                "type": "tool_call",
                "name": name,
                "category": category,
                "arguments": arguments,
                "success": bool(result.get("success")),
                "duration": round(step_duration, 3),
                "result_preview": _preview(result),
            })

            memory.add_tool_result(
                json.dumps(result, ensure_ascii=False),
                tool_call_id=call.get("id"),
            )

        # ------------------------------------------------------
        # MINTA MODEL MENYIMPULKAN HASIL TOOL / LANJUT TOOL LAGI
        # ------------------------------------------------------
        response = call_model(memory.get_messages(), TOOLS)

        if "error" in response:

            duration = time.perf_counter() - start

            return {
                "answer": f"Terjadi error saat menghubungi model: {response['error']}",
                "steps": steps,
                "duration": duration,
                "token_usage": memory.token_tracker.last_usage,
                "error": True,
            }

        _track_usage(memory, response)


def _preview(result, limit=400):
    """
    Ringkasan singkat hasil tool untuk ditampilkan di timeline
    frontend (bukan payload penuh - itu tetap ada di conversation
    history yang dikirim ke LLM, tapi tidak perlu dikirim penuh ke
    browser supaya response tidak berat).
    """

    text = json.dumps(result, ensure_ascii=False)

    if len(text) > limit:
        return text[:limit] + "...(truncated)"

    return text
