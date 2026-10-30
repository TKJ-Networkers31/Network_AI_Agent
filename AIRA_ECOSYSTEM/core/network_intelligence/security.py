"""
core/network_intelligence/security.py — Read-Only Security Policy and Command Allowlist.

Enforces strict boundaries between read-only diagnostics and state-changing mutations:
1. Explicit canonical allowlist for RouterOS v6/v7 diagnostic commands.
2. Hard rejection of mutating verbs (add, set, remove, enable, disable, reset, reboot).
3. Injection prevention (rejecting semicolons, newlines, pipes, backticks).
4. Secret redaction (passwords, private keys, tokens, SNMP community strings).
5. Output and execution bounds (max runtime, max output characters).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.topology_models import sanitize_cli_excerpt
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.network_intelligence.security")

# Maximum execution constraints
MAX_COMMAND_LENGTH = 512
MAX_OUTPUT_CHARACTERS = 8000
MAX_READONLY_TIMEOUT_SECONDS = 30.0

# Mutating verbs that must NEVER be executed in read-only paths
MUTATING_VERBS = {
    "add",
    "set",
    "remove",
    "enable",
    "disable",
    "reset",
    "reboot",
    "shutdown",
    "edit",
    "comment",
    "export",
    "import",
    "run",
    "delete",
    "install",
    "upgrade",
    "downgrade",
    "uninstall",
    "format",
    "flash",
    "restore",
}

# Approved read-only print command namespaces
APPROVED_PRINT_PREFIXES = (
    "/system identity print",
    "/system resource print",
    "/system routerboard print",
    "/system clock print",
    "/system package print",
    "/interface print",
    "/interface bridge print",
    "/interface bridge port print",
    "/interface bridge vlan print",
    "/interface vlan print",
    "/interface ethernet print",
    "/interface wireless print",
    "/ip address print",
    "/ip route print",
    "/ip route rule print",
    "/ip firewall filter print",
    "/ip firewall nat print",
    "/ip firewall mangle print",
    "/ip firewall raw print",
    "/ip firewall address-list print",
    "/ip firewall connection print",
    "/ip arp print",
    "/ip neighbor print",
    "/ip dns print",
    "/ip pool print",
    "/ip dhcp-server print",
    "/ip dhcp-server lease print",
    "/ip dhcp-client print",
    "/routing rule print",
    "/routing table print",
    "/routing filter rule print",
    "/routing filter print",
    "/routing ospf neighbor print",
    "/routing ospf instance print",
    "/routing ospf interface print",
    "/routing ospf interface-template print",
    "/routing bgp peer print",
    "/routing bgp connection print",
    "/routing bgp session print",
)

# Compiled regex patterns for backwards compatibility
READONLY_ALLOWLIST_PATTERNS = [
    re.compile(r"^" + re.escape(p) + r"(\s+.*)?$", re.IGNORECASE) for p in APPROVED_PRINT_PREFIXES
] + [
    re.compile(r"^/ping\s+[a-zA-Z0-9\.\-:]+(\s+count=[1-5])?(\s+size=[0-9]+)?(\s+interface=[^\s]+)?$", re.IGNORECASE),
    re.compile(r"^/tool\s+traceroute\s+[a-zA-Z0-9\.\-:]+(\s+count=[1-3])?$", re.IGNORECASE),
    re.compile(r"^/export(\s+(compact|verbose=no))?$", re.IGNORECASE),
]

# Sensitive keys to redact
SENSITIVE_KEY_PATTERNS = [
    re.compile(r'(password=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(wpa2?-pre-shared-key=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(passphrase=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(secret=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(community=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(token=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
    re.compile(r'(private-key=["\']?)([^"\'\s]+)(["\']?)', re.IGNORECASE),
]


def redact_sensitive_values(text: str) -> str:
    """Masks secrets, passwords, tokens, and keys from raw text and CLI outputs."""
    if not text:
        return ""
    result = text
    for pat in SENSITIVE_KEY_PATTERNS:
        result = pat.sub(r'\1******\3', result)
    result = mask_sensitive_data(result)
    return result


def validate_readonly_command(command: str) -> Tuple[bool, str]:
    """
    Deterministically validates whether a CLI command is strictly read-only.
    Enforces RouterOS syntax awareness, structured argument checks, and defense-in-depth:
    1. Input sanity and maximum length bounds.
    2. Shell metacharacter and control character rejection.
    3. RouterOS command substitution '[' and ']' rejection.
    4. RouterOS script code blocks '{' and '}' rejection.
    5. RouterOS colon scripting command prefix rejection (e.g., :execute, :set).
    6. File output redirection rejection ('file=', 'append=').
    7. Unbounded streaming rejection ('interval=', 'follow', 'freeze', 'continuous').
    8. Unclosed quote detection (fails closed).
    9. Namespace allowlisting and bounded parameter validation.
    10. Token-level mutating verb rejection outside string literals.

    Returns (is_valid, reason).
    """
    if not command or not isinstance(command, str):
        return False, "Command kosong atau bukan string."

    cmd_clean = command.strip()
    if not cmd_clean:
        return False, "Command hanya berisi whitespace."

    if len(cmd_clean) > MAX_COMMAND_LENGTH:
        return False, f"Command melebihi batas panjang maksimum ({MAX_COMMAND_LENGTH} karakter)."

    # 1. Shell metacharacters and control characters
    if any(c in cmd_clean for c in ("\0", "\n", "\r", ";", "|", "`", "$", "&", "<", ">")):
        return False, "Command mengandung karakter terlarang (newline, semicolon, pipe, backtick, dollar, ampersand, redirect)."

    # 2. RouterOS command substitution via square brackets [...]
    if "[" in cmd_clean or "]" in cmd_clean:
        return False, "Command mengandung kurung siku (command substitution terlarang pada jalur read-only)."

    # 3. RouterOS script code blocks via curly braces {...}
    if "{" in cmd_clean or "}" in cmd_clean:
        return False, "Command mengandung kurung kurawal (script block / code block terlarang pada jalur read-only)."

    # 4. RouterOS colon script command prefixes (e.g. :execute, :put, :delay)
    if re.search(r'(?:^|\s):[a-zA-Z]', cmd_clean):
        return False, "Command mengandung perintah scripting RouterOS dengan awalan ':' (terlarang pada jalur read-only)."

    # 5. Output redirection and file writes (file=, append=, stats-file=)
    if re.search(r'(?i)\b[\w-]*file\s*=', cmd_clean):
        return False, "Parameter 'file=' / penulisan file terlarang pada jalur read-only (mencegah mutasi filesystem router)."

    if re.search(r'(?i)\bappend\s*=', cmd_clean):
        return False, "Parameter 'append=' terlarang pada jalur read-only (mencegah mutasi filesystem router)."

    # 6. Unbounded streaming and interactive loop parameters
    if re.search(r'(?i)\binterval\s*=', cmd_clean):
        return False, "Parameter 'interval=' terlarang (mencegah streaming tak berbatas pada sesi diagnostik)."

    if re.search(r'(?i)\b(follow|follow-only|freeze|continuous)\b', cmd_clean):
        return False, "Parameter streaming ('follow', 'freeze', 'continuous') terlarang pada jalur read-only."

    # 7. Check unclosed quotes (fail closed on malformed syntax)
    double_quotes = cmd_clean.count('"')
    single_quotes = cmd_clean.count("'")
    if double_quotes % 2 != 0 or single_quotes % 2 != 0:
        return False, "Command mengandung tanda kutip yang tidak tertutup (unclosed quotes)."

    normalized = " ".join(cmd_clean.split())
    norm_lower = normalized.lower()

    # 8. Special bounded tool commands
    if norm_lower.startswith("/ping"):
        if re.match(r"^/ping\s+[a-zA-Z0-9\.\-:]+(\s+count=[1-5])?(\s+size=[0-9]+)?(\s+interface=[a-zA-Z0-9\.\-_]+)?$", normalized, re.IGNORECASE):
            return True, "Valid read-only command."
        return False, "Parameter command /ping tidak valid atau melebihi batas count (maks 5)."

    if norm_lower.startswith("/tool traceroute"):
        if re.match(r"^/tool\s+traceroute\s+[a-zA-Z0-9\.\-:]+(\s+count=[1-3])?$", normalized, re.IGNORECASE):
            return True, "Valid read-only command."
        return False, "Parameter command /tool traceroute tidak valid atau melebihi batas count (maks 3)."

    if norm_lower.startswith("/export"):
        if re.match(r"^/export(\s+(compact|verbose=no))?$", normalized, re.IGNORECASE):
            return True, "Valid read-only command."
        return False, "Command /export hanya diizinkan dengan parameter compact atau verbose=no."

    # 9. Match approved print prefix
    matched_prefix = None
    for prefix in sorted(APPROVED_PRINT_PREFIXES, key=len, reverse=True):
        if norm_lower == prefix or norm_lower.startswith(prefix + " "):
            matched_prefix = prefix
            break

    if not matched_prefix:
        return False, f"Command '{cmd_clean}' tidak diizinkan oleh allowlist read-only policy."

    args_str = normalized[len(matched_prefix):].strip()
    if not args_str:
        return True, "Valid read-only command."

    # 10. Check for mutating verbs in arguments outside string literals
    unquoted = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', args_str)
    tokens = [t.lower() for t in unquoted.split()]
    for raw_tok in tokens:
        # Also split comma-separated arguments if any (e.g. key1=val1,key2=val2)
        for tok in raw_tok.split(","):
            if not tok:
                continue
            if "=" in tok:
                parts = tok.split("=", 1)
                k = re.sub(r'[^a-zA-Z0-9_-]', '', parts[0])
                v = re.sub(r'[^a-zA-Z0-9_-]', '', parts[1])
                # Property keys cannot be mutating verbs (except "comment" property filter)
                if k in MUTATING_VERBS and k != "comment":
                    return False, f"Argumen mengandung kata kerja mutasi terlarang pada parameter: '{k}'."
                # Unquoted property values cannot be mutating verbs
                if v in MUTATING_VERBS:
                    return False, f"Argumen mengandung kata kerja mutasi terlarang: '{v}'."
            else:
                clean_word = re.sub(r'[^a-zA-Z0-9_-]', '', tok)
                if clean_word in MUTATING_VERBS and clean_word != "comment":
                    return False, f"Argumen mengandung kata kerja mutasi terlarang: '{clean_word}'."

    return True, "Valid read-only command."


def execute_safe_readonly_command(
    cm: Any,
    device_id: str,
    command: str,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Executes a validated read-only command with bounded timeout, output limit, and redaction.
    """
    is_valid, reason = validate_readonly_command(command)
    if not is_valid:
        logger.warning("Read-only security policy blocked command '%s': %s", command, reason)
        return {
            "success": False,
            "error": f"Security policy violation: {reason}",
            "command": command,
            "device": device_id,
            "blocked": True,
        }

    clamped_timeout = min(max(1.0, float(timeout)), MAX_READONLY_TIMEOUT_SECONDS)
    res = cm.execute_for_device(device_id, command, timeout=clamped_timeout)

    if not res.get("success"):
        return {
            "success": False,
            "error": res.get("error", "Execution failed"),
            "command": command,
            "device": device_id,
            "blocked": False,
        }

    raw_output = res.get("output", "")
    redacted = redact_sensitive_values(raw_output)
    truncated = sanitize_cli_excerpt(redacted, max_chars=MAX_OUTPUT_CHARACTERS)

    return {
        "success": True,
        "output": truncated,
        "command": command,
        "device": device_id,
        "latency_ms": res.get("latency_ms", 0.0),
        "blocked": False,
    }
