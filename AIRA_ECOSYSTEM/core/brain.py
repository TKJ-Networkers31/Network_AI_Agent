"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

FIX (Phase 0 Stabilization - token tracker):
BrainResponse sekarang juga membawa 'session_token_usage' (kumulatif
sejak sesi ini dimulai/direset), selain 'token_usage' (giliran
terakhir saja) yang sudah ada sebelumnya. Dipakai run_chat.py untuk
menampilkan ringkasan token sesi seperti perilaku sistem lama.
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
    session_token_usage: Optional[dict] = None
    error: bool = False
    duration: float = 0.0


class Brain:

    def __init__(self, memory: ConversationMemory):
        self.memory = memory
        self.orchestrator = Orchestrator()

    def think(self, user_input: str) -> BrainResponse:
        logger.info("BRAIN | menerima input user (%d char)", len(user_input))

        result = self.orchestrator.route(user_input, self.memory)

        return BrainResponse(
            answer=result.get("answer", ""),
            steps=result.get("steps", []),
            token_usage=result.get("token_usage"),
            session_token_usage=result.get("session_token_usage"),
            error=result.get("error", False),
            duration=result.get("duration", 0.0),
        )