"""
core/capability/integration.py — integration boundary between the
Capability Layer and the EXISTING tool/agent architecture (Sprint 2.7 / W1).

This is the ONLY module in core/capability/ that knows the shape of
AGENT_TOOL_SCHEMAS / AGENT_TOOL_CATEGORY / DANGEROUS_TOOLS
(core/orchestrator.py). It is imported BY callers that have that data
(e.g. api/main.py at startup, or core/orchestrator.py itself) - it is
never imported automatically by core/capability/__init__.py, so the
Capability package stays usable standalone (tests, other contexts)
without agents/* needing to exist.

It does NOT replace AGENT_TOOL_MAP/AGENT_TOOL_SCHEMAS - tool execution
still goes through Orchestrator._execute_tool() exactly as before. This
only builds a Capability *view* over the existing tool schemas so tools
become discoverable through the Capability Layer without duplicating
their definitions.

Typical wiring (left for the integrating worker/PR, not run automatically
here):

    from core.orchestrator import AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS
    from core.capability.integration import register_tool_capabilities
    register_tool_capabilities(AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS)
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from core.capability.constants import CONTEXT_CONVERSATION, PERMISSION_CONFIRMATION_REQUIRED, PERMISSION_SAFE
from core.capability.models import Capability, CapabilityUIMetadata, ToolBinding
from core.capability.registry import CapabilityAlreadyRegisteredError, CapabilityRegistry, get_capability_registry

logger = logging.getLogger("aira.capability.integration")

TOOL_CAPABILITY_ID_PREFIX = "tool."


def tool_capability_id(tool_name: str) -> str:
    return f"{TOOL_CAPABILITY_ID_PREFIX}{tool_name}"


def capability_from_tool_schema(
    schema: dict,
    *,
    category: str = "tool",
    dangerous: bool = False,
) -> Optional[Capability]:
    """One OpenAI-style tool schema entry (the shape AGENT_TOOL_SCHEMAS
    already uses: {"type": "function", "function": {"name", "description",
    "parameters"}}) -> one Capability. Returns None for a malformed entry
    (no name) instead of raising - callers should skip Nones, same
    defensive style as api/routers/tools.py::list_tools()."""
    function = schema.get("function", {}) if isinstance(schema, dict) else {}
    name = function.get("name")

    if not name:
        return None

    return Capability(
        id=tool_capability_id(name),
        name=name,
        description=function.get("description", "") or "",
        category=category,
        supported_context=[CONTEXT_CONVERSATION],
        input_schema=dict(function.get("parameters") or {}),
        output_types=["text"],
        permission=PERMISSION_CONFIRMATION_REQUIRED if dangerous else PERMISSION_SAFE,
        ui=CapabilityUIMetadata(group=category),
        tool_binding=ToolBinding(tool_names=[name]),
        metadata={"origin": "tool_schema"},
    )


def register_tool_capabilities(
    tool_schemas: Iterable,
    tool_category: Optional[dict] = None,
    dangerous_tools: Optional[set] = None,
    *,
    registry: Optional[CapabilityRegistry] = None,
    overwrite: bool = False,
) -> dict:
    """
    Bridge AGENT_TOOL_SCHEMAS (+ AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS from
    core/orchestrator.py) into the Capability Registry as one Capability
    per tool.

    Never raises for a single bad tool entry - failures are collected and
    returned, not thrown, so one malformed schema can't block every other
    tool from becoming discoverable.
    """
    registry = registry or get_capability_registry()
    tool_category = tool_category or {}
    dangerous_tools = dangerous_tools or set()

    registered: list = []
    skipped: list = []
    errors: list = []

    for schema in tool_schemas or []:
        function = schema.get("function", {}) if isinstance(schema, dict) else {}
        name = function.get("name")

        capability = capability_from_tool_schema(
            schema,
            category=tool_category.get(name, "tool"),
            dangerous=name in dangerous_tools,
        )

        if capability is None:
            skipped.append(str(schema))
            continue

        try:
            registry.register(capability, overwrite=overwrite)
            registered.append(capability.id)
        except CapabilityAlreadyRegisteredError:
            skipped.append(capability.id)
        except Exception as exc:
            logger.warning("CAPABILITY INTEGRATION | gagal register tool '%s': %s", name, exc)
            errors.append({"tool": name, "error": str(exc)})

    logger.info(
        "CAPABILITY INTEGRATION | tool bridge selesai: %d registered, %d skipped, %d error.",
        len(registered), len(skipped), len(errors),
    )

    return {"registered": registered, "skipped": skipped, "errors": errors}
