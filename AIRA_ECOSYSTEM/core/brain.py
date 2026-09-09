"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

Ini adalah pengganti agent/core/engine.py::run() dan engine_web.py::run_web()
LAMA. Bedanya: brain.py TIDAK tahu detail tool jaringan/visual/suara sama
sekali - ia hanya menerima teks user, delegasikan ke core/orchestrator.py,
dan mengembalikan jawaban akhir + metadata (steps, token usage) dalam bentuk
yang seragam, dipakai baik oleh CLI (agent/main.py versi baru) maupun web
(api/routers/chat.py).

Kenapa dipisah dari orchestrator.py: brain.py adalah lapisan "wajah publik"
(persona, format output ke caller), orchestrator.py adalah lapisan "otak
routing" (AIRA -> REI -> agent yang sesuai -> balik). Pemisahan ini juga
yang membuat "Jangan membuat chatbot kedua selain AIRA" mudah dijaga -
caller manapun (CLI/web) HARUS lewat brain.py, tidak boleh panggil
orchestrator atau agent langsung.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.orchestrator import Orchestrator
from core.memory import ConversationMemory

logger = logging.getLogger("aira.brain")


@dataclass
class BrainResponse:
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    token_usage: Optional[dict] = None
    error: bool = False


class Brain:
    """
    Satu instance Brain = satu sesi percakapan AIRA (dibungkus ConversationMemory).
    """

    def __init__(self, memory: ConversationMemory):
        self.memory = memory
        self.orchestrator = Orchestrator()

    def think(self, user_input: str) -> BrainResponse:
        """
        Terima input user mentah, kembalikan jawaban akhir AIRA.

        TODO (migrasi dari engine_web.run_web):
          1. self.memory.add_user(user_input)
          2. result = self.orchestrator.route(user_input, self.memory)
          3. self.memory.add_message(...)  # assistant message final
          4. return BrainResponse(...)
        """

        logger.info("BRAIN | menerima input user (%d char)", len(user_input))

        result = self.orchestrator.route(user_input, self.memory)

        return BrainResponse(
            answer=result.get("answer", ""),
            steps=result.get("steps", []),
            token_usage=result.get("token_usage"),
            error=result.get("error", False),
        )
