"""
mcp_servers/network/security.py — Security guards for Network MCP Server.

Enforces:
- Target hostname/IP validation (prevents CLI argument injection and control chars).
- Secret masking (prevents credentials leaking to LLM context).

Delegates implementation to `core.security.masking` to avoid architectural layer inversions.
"""

from __future__ import annotations

from core.security.masking import (
    _FORBIDDEN_CHARS_RE,
    _VALID_TARGET_RE,
    mask_sensitive_data,
    validate_network_target,
)

__all__ = [
    "_FORBIDDEN_CHARS_RE",
    "_VALID_TARGET_RE",
    "mask_sensitive_data",
    "validate_network_target",
]
