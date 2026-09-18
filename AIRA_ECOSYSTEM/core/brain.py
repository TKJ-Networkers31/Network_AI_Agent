"""
core/brain.py — satu-satunya pintu masuk publik ke AIRA.

FIX (Optimalisasi DIO):
BrainResponse sekarang membawa 'interaction_schema' (dict atau None),
diteruskan apa adanya dari hasil Planner.run() lewat Orchestrator.route()
- ini yang membuat form/pilihan interaktif DIO bisa sampai ke
api/routers/chat.py & ws.py, lalu ke frontend.
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
    interaction_schema: Optional[dict] = None


class Brain:

    def __init__(self, memory: ConversationMemory):
        self.memory = memory
        self.orchestrator = Orchestrator()

    def think(self, user_input: str, on_event=None) -> BrainResponse:
        logger.info("BRAIN | menerima input user (%d char)", len(user_input))

        result = self.orchestrator.route(user_input, self.memory, on_event=on_event)

        return BrainResponse(
            answer=result.get("answer", ""),
            steps=result.get("steps", []),
            token_usage=result.get("token_usage"),
            session_token_usage=result.get("session_token_usage"),
            error=result.get("error", False),
            duration=result.get("duration", 0.0),
            interaction_schema=result.get("interaction_schema"),
        )