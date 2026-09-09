"""
agents/rei/planner.py — REI (Reasoning & Executive Intelligence).

Peran REI sesuai master prompt: planning, tool selection, multi-step
reasoning, report generation, decision making. REI TIDAK bicara ke user
(itu tugas AIRA/core.brain) dan TIDAK punya akses network/vision/voice
langsung - ia hanya tahu DAFTAR NAMA tool yang tersedia (dikirim oleh
core/orchestrator.py lewat parameter `tool_map`) dan meminta orchestrator
mengeksekusikannya lewat callback `tool_executor`.

Ini adalah port dari loop agen di agent/core/engine.py::run() /
engine_web.py::run_web(), tapi dengan tanggung jawab dipersempit: REI cuma
mikir & memutuskan, eksekusi tool fisik didelegasikan balik ke orchestrator
(Dependency Inversion) supaya REI tidak pernah import AKANE/HIKARI/YUKI
langsung.
"""

import json
import logging
from typing import Callable

from agents.rei.provider_client import call_model
from core.persona import build_system_prompt

logger = logging.getLogger("aira.rei.planner")

MAX_TOOL_CALLS = 10


class Planner:

    def __init__(self, tool_map: dict):
        # tool_map di sini HANYA dipakai untuk membangun skema function-calling
        # (nama + signature), bukan untuk eksekusi - eksekusi lewat tool_executor.
        self.tool_map = tool_map

    def run(self, user_input: str, memory, tool_executor: Callable[[str, dict], dict]) -> dict:
        """
        TODO (migrasi dari engine.py::run / engine_web.py::run_web):
          1. memory.add_user(user_input)
          2. messages = memory.get_messages(build_system_prompt(extra_context))
          3. response = call_model(messages, self._tool_schemas())
          4. loop while response punya tool_calls:
               - untuk tiap call: arguments = json.loads(...) kalau string
               - result = tool_executor(name, arguments)
               - memory.add_tool_result(json.dumps(result), tool_call_id)
               - guard MAX_TOOL_CALLS
             lalu call_model lagi
          5. return {"answer": ..., "steps": [...], "token_usage": ..., "error": False}
        """
        raise NotImplementedError("TODO: port loop agent dari agent/core/engine.py::run")

    def _tool_schemas(self) -> list[dict]:
        """
        TODO: bangun skema function-calling (format OpenAI tools=[...]) dari
        self.tool_map. Skema per-tool sebaiknya didefinisikan di masing-masing
        agents/<nama>/registry.py (mis. AKANE_TOOL_SCHEMAS), lalu digabung di
        sini - supaya definisi tool tetap dekat dengan implementasinya.
        """
        raise NotImplementedError("TODO: kumpulkan skema dari agents/*/registry.py")
