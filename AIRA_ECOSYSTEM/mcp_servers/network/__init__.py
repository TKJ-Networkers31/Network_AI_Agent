"""
mcp_servers.network — Dedicated Network Automation & Diagnostics MCP Server.
"""

def create_network_mcp_server():
    """Lazily loads and instantiates FastMCP server to avoid eager dependency requirements."""
    from mcp_servers.network.server import create_network_mcp_server as _create
    return _create()

__all__ = ["create_network_mcp_server"]
