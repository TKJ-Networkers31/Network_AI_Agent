"""
core/orchestrator.py — otak routing AIRA.
User -> AIRA -> REI (Planning) -> AKANE/HIKARI/REI-tools -> AIRA -> User
"""

import logging
import time
from typing import Any

from agents.rei.planner import Planner
from agents.rei.registry import REI_TOOLS, REI_TOOL_CATEGORY, REI_TOOL_SCHEMAS
from agents.akane.registry import (
    AKANE_TOOLS, AKANE_DANGEROUS_TOOLS, AKANE_TOOL_CATEGORY, AKANE_TOOL_SCHEMAS,
)
from agents.hikari.registry import (
    HIKARI_TOOLS, HIKARI_DANGEROUS_TOOLS, HIKARI_TOOL_CATEGORY, HIKARI_TOOL_SCHEMAS,
)

logger = logging.getLogger("aira.orchestrator")

AGENT_TOOL_MAP: dict[str, Any] = {**AKANE_TOOLS, **HIKARI_TOOLS, **REI_TOOLS}
AGENT_TOOL_CATEGORY: dict[str, str] = {**AKANE_TOOL_CATEGORY, **HIKARI_TOOL_CATEGORY, **REI_TOOL_CATEGORY}
AGENT_TOOL_SCHEMAS: list[dict] = [*AKANE_TOOL_SCHEMAS, *HIKARI_TOOL_SCHEMAS, *REI_TOOL_SCHEMAS]
DANGEROUS_TOOLS: set[str] = set(AKANE_DANGEROUS_TOOLS) | set(HIKARI_DANGEROUS_TOOLS)


class Orchestrator:

    def __init__(self):
        self.planner = Planner(
            tool_schemas=AGENT_TOOL_SCHEMAS,
            tool_category=AGENT_TOOL_CATEGORY,
            dangerous_tools=DANGEROUS_TOOLS,
        )

    def route(self, user_input: str, memory) -> dict:
        start = time.perf_counter()
        result = self.planner.run(user_input, memory, tool_executor=self._execute_tool)
        result["duration"] = round(time.perf_counter() - start, 3)
        return result

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        if name not in AGENT_TOOL_MAP:
            return {"success": False, "error": f"Tool '{name}' tidak dikenal oleh orchestrator."}
        try:
            return AGENT_TOOL_MAP[name](**arguments)
        except Exception as exc:
            logger.exception("Tool '%s' gagal", name)
            return {"success": False, "tool": name, "error": str(exc)}
