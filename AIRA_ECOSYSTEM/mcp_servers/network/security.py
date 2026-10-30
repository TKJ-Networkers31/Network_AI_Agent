"""
mcp_servers/network/security.py ? Security guards for Network MCP Server.

Enforces:
- Target hostname/IP validation (prevents CLI argument injection and control chars).
- Secret masking (prevents credentials leaking to LLM context).
"""

from __future__ import annotations

import re
from typing import Any

# Allowed hostnames (RFC 1123) and IPv4/IPv6 addresses without flags or control characters
_VALID_TARGET_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"  # domain
    r"|^(?:\d{1,3}\.){3}\d{1,3}$"  # IPv4
    r"|^[a-zA-Z0-9_.-]+$"  # hostname / device name
    r"|^[a-fA-F0-9:]+$"  # IPv6 simplified
)

_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x1f\x7f;`$&|><\s\\]")


def validate_network_target(target: str) -> str:
    """
    Validates a network target (hostname or IP).
    Rejects targets that start with '-' (flag injection) or contain command separators.
    """
    if not isinstance(target, str) or not target.strip():
        raise ValueError("Network target cannot be empty.")

    cleaned = target.strip()

    if cleaned.startswith("-") or cleaned.startswith("/"):
        raise ValueError(f"Invalid target '{cleaned}': target cannot start with options or path separators.")

    if _FORBIDDEN_CHARS_RE.search(cleaned):
        raise ValueError(f"Invalid target '{cleaned}': target contains forbidden characters.")

    if len(cleaned) > 255:
        raise ValueError(f"Invalid target '{cleaned}': target length exceeds 255 characters.")

    if not _VALID_TARGET_RE.match(cleaned):
        raise ValueError(f"Invalid target '{cleaned}': target does not conform to a valid hostname or IP address format.")

    return cleaned


def mask_sensitive_data(obj: Any) -> Any:
    """
    Recursively masks sensitive dictionary keys such as passwords, tokens, keys.
    """
    sensitive_exact = {"password", "secret", "private_key", "token", "community", "ssh_key", "api_key", "pass", "auth"}
    sensitive_suffixes = ("_key", "_secret", "_password", "_token", "_pass")
    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            is_sensitive = (
                k_lower in sensitive_exact
                or any(k_lower.endswith(sfx) for sfx in sensitive_suffixes)
                or "password" in k_lower
                or "private_key" in k_lower
                or "secret" in k_lower
                or "ssh_key" in k_lower
            )
            if is_sensitive:
                masked[k] = "***" if v else v
            else:
                masked[k] = mask_sensitive_data(v)
        return masked
    elif isinstance(obj, list):
        return [mask_sensitive_data(item) for item in obj]
    return obj
