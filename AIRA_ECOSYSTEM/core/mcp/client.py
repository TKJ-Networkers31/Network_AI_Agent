"""
core/mcp/client.py — MCP Client integration layer for AIRA OS.

Provides:
- In-process and transport-based connectivity to MCP Servers.
- Dynamic tool discovery and translation to standard OpenAI function schemas.
- Synchronous and asynchronous dispatch with bounded concurrency, explicit timeouts,
  and normalized error responses.
- Category classification and dangerous/state-changing tool tagging for AIRA Orchestrator.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Any, Callable, Optional

from mcp.server.mcpserver import MCPServer
from mcp_servers.network.server import create_network_mcp_server

logger = logging.getLogger("aira.core.mcp.client")


def _run_async(coro):
    """Safely executes an async coroutine from either sync or running-async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class MCPClient:
    """Client wrapper for an MCPServer instance or transport."""

    def __init__(self, server: MCPServer, server_name: str = "network"):
        self.server = server
        self.server_name = server_name
        self._tools_cache: dict[str, Any] = {}
        self._schemas_cache: list[dict] = []
        self._categories_cache: dict[str, str] = {}
        self._dangerous_tools: set[str] = set()

    async def initialize_async(self) -> None:
        """Discovers tools from the MCP server and populates schemas and categories."""
        raw_tools = await self.server.list_tools()
        schemas = []
        tool_map = {}
        categories = {}
        dangerous = set()

        for t in raw_tools:
            name = t.name
            desc = t.description or ""
            # Inspect parameters schema
            params = getattr(t, "parameters", None) or getattr(t, "inputSchema", None) or {
                "type": "object",
                "properties": {},
            }

            # Map category based on naming convention
            if name.startswith("network_"):
                cat = "network"
            elif name.startswith("mikrotik_"):
                cat = "mikrotik"
            elif name.startswith("snmp_"):
                cat = "snmp"
            elif name.startswith("device_"):
                cat = "inventory"
            else:
                cat = "network"

            categories[name] = cat

            # Tag state-changing / sensitive tools
            if name in {"mikrotik_apply_config", "device_disconnect"}:
                dangerous.add(name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params,
                },
            })

            # Create a callable dispatch wrapper
            def make_caller(tool_name: str) -> Callable[..., dict]:
                def caller(**kwargs) -> dict:
                    return self.call_tool(tool_name, kwargs)
                caller.__name__ = tool_name
                caller.__doc__ = desc
                return caller

            tool_map[name] = make_caller(name)

        self._tools_cache = tool_map
        self._schemas_cache = schemas
        self._categories_cache = categories
        self._dangerous_tools = dangerous
        logger.info(
            "MCP CLIENT | Server '%s' initialized with %d tools.",
            self.server_name, len(tool_map),
        )

    def initialize(self) -> None:
        _run_async(self.initialize_async())

    @property
    def tools(self) -> dict[str, Callable[..., dict]]:
        if not self._tools_cache:
            self.initialize()
        return self._tools_cache

    @property
    def schemas(self) -> list[dict]:
        if not self._schemas_cache:
            self.initialize()
        return self._schemas_cache

    @property
    def categories(self) -> dict[str, str]:
        if not self._categories_cache:
            self.initialize()
        return self._categories_cache

    @property
    def dangerous_tools(self) -> set[str]:
        if not self._dangerous_tools:
            self.initialize()
        return self._dangerous_tools

    async def call_tool_async(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> dict:
        """Asynchronously dispatches a tool call to the MCP server."""
        try:
            call_coro = self.server.call_tool(tool_name, arguments)
            result = await asyncio.wait_for(call_coro, timeout=timeout)

            # Extract structured content if available
            if hasattr(result, "structured_content") and result.structured_content:
                if isinstance(result.structured_content, dict) and "result" in result.structured_content and isinstance(result.structured_content["result"], dict):
                    return result.structured_content["result"]
                return result.structured_content

            # Parse from TextContent
            if hasattr(result, "content") and result.content:
                first = result.content[0]
                text = getattr(first, "text", "")
                try:
                    return json.loads(text)
                except Exception:
                    return {"success": True, "output": text}

            return {"success": True, "result": str(result)}

        except asyncio.TimeoutError:
            logger.error("MCP tool '%s' timed out after %.1fs", tool_name, timeout)
            return {"success": False, "tool": tool_name, "error": f"Tool execution timed out after {timeout} seconds."}
        except Exception as exc:
            logger.exception("MCP tool '%s' call failed", tool_name)
            return {"success": False, "tool": tool_name, "error": str(exc)}

    def call_tool(self, tool_name: str, arguments: dict, timeout: float = 30.0) -> dict:
        """Synchronously dispatches a tool call."""
        return _run_async(self.call_tool_async(tool_name, arguments, timeout=timeout))


_network_mcp_client: Optional[MCPClient] = None


def get_network_mcp_client() -> MCPClient:
    """Singleton getter for the primary Network MCP Client."""
    global _network_mcp_client
    if _network_mcp_client is None:
        server = create_network_mcp_server()
        client = MCPClient(server, server_name="network")
        client.initialize()
        _network_mcp_client = client
    return _network_mcp_client
