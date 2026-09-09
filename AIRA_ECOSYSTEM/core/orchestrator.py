"""
core/orchestrator.py — otak routing AIRA.

Implementasi flow wajib dari master prompt:

    User -> AIRA -> Detect Intent -> REI (Planning) -> Agent yang diperlukan
         -> AIRA -> User

Orchestrator TIDAK bicara ke user secara langsung (itu tugas core/brain.py
+ core/persona.py) dan TIDAK memanggil OpenRouter/Ollama langsung (itu
tugas agents/rei/provider_client.py). Tanggung jawab orchestrator murni:

  1. Minta REI menyusun rencana (tool apa yang perlu dipanggil, kalau ada).
  2. Kalau REI minta tool AKANE/HIKARI/YUKI, panggil agent yang bersangkutan
     lewat registry masing-masing (bukan import tools/* langsung).
  3. Serahkan hasil observasi balik ke REI untuk disimpulkan jadi jawaban
     akhir.
  4. Kembalikan dict seragam {"answer", "steps", "token_usage", "error"}
     ke core/brain.py.

Ini adalah hasil pemecahan dari agent/core/engine.py::run() versi lama -
loop "tool_calls while True" yang lama sekarang tinggal di sini, tapi
resolusi nama tool -> fungsi python dipindah ke masing-masing
agents/<nama>/registry.py supaya orchestrator tidak perlu tahu isi
internal tiap agent.
"""

import logging
from typing import Any

from agents.rei.planner import Planner
from agents.akane.registry import AKANE_TOOLS
from agents.hikari import vision as hikari_vision  # noqa: F401  (placeholder import)
from agents.yuki import voice_io as yuki_voice_io  # noqa: F401  (placeholder import)

logger = logging.getLogger("aira.orchestrator")

MAX_TOOL_CALLS = 10

# Registry gabungan semua agent internal - orchestrator hanya tahu "nama tool
# -> agent mana yang punya", tidak tahu implementasi di baliknya.
AGENT_TOOL_MAP: dict[str, Any] = {
    **AKANE_TOOLS,
    # TODO: tambahkan HIKARI_TOOLS dan YUKI_TOOLS begitu registry-nya siap
    # (lihat agents/hikari/vision.py dan agents/yuki/*.py).
}


class Orchestrator:

    def __init__(self):
        self.planner = Planner(tool_map=AGENT_TOOL_MAP)

    def route(self, user_input: str, memory) -> dict:
        """
        Jalankan satu giliran penuh: analisis -> (mungkin beberapa) tool call
        -> kesimpulan akhir.

        TODO (migrasi dari agent/core/engine.py::run / engine_web.py::run_web):
          - port loop "while True: tool_calls..." dari sana ke sini,
            tapi ganti `execute_tool(name, arguments)` jadi
            `AGENT_TOOL_MAP[name](**arguments)`.
          - port MAX_TOOL_CALLS guard, logging tool_call/tool_result,
            auto-retry response kosong (EMPTY_RESPONSE_MARKER) - semua
            pindah ke agents/rei/planner.py + provider_client.py.
        """

        logger.info("ORCHESTRATOR | routing input untuk sesi ini")

        return self.planner.run(user_input, memory, tool_executor=self._execute_tool)

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        """
        Satu-satunya tempat orchestrator "menyentuh" agent internal - dengan
        nama tool sebagai kunci, tanpa tahu itu AKANE/HIKARI/YUKI.
        """

        if name not in AGENT_TOOL_MAP:
            return {"success": False, "error": f"Tool '{name}' tidak dikenal oleh orchestrator."}

        try:
            return AGENT_TOOL_MAP[name](**arguments)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ORCHESTRATOR | tool '%s' gagal", name)
            return {"success": False, "tool": name, "error": str(exc)}
