"""
core/topology_models.py — Domain constants, enums, sanitizers, network scope helpers,
and deterministic status/confidence calculators for AIRA Topology Fabric V2.
"""

from __future__ import annotations

import ipaddress
import platform
import re
import subprocess
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerated Domain Values (kept as strings for SQLite & JSON compatibility)
# ---------------------------------------------------------------------------

OWNERSHIP_VALUES = ("owned", "managed_external", "third_party", "unknown")
TOPOLOGY_SCOPE_VALUES = (
    "enterprise_internal",
    "enterprise_edge",
    "isp_upstream",
    "external",
    "vpn_remote",
    "unclassified",
)
TRUST_ZONE_VALUES = ("internal", "dmz", "edge", "isp", "external", "vpn", "unknown")
DISCOVERY_STATUS_VALUES = ("discovered", "manual", "candidate", "pending_review", "excluded")

REACHABILITY_VALUES = ("reachable", "unreachable", "unknown")
MANAGEMENT_STATUS_VALUES = ("managed", "management_unavailable", "not_attempted", "not_authorized")
FRESHNESS_VALUES = ("fresh", "stale", "expired", "unknown")

LINK_TYPE_VALUES = (
    "physical",
    "layer2_adjacency",
    "routed",
    "vpn",
    "wireless",
    "inferred",
    # Legacy aliases accepted on input and normalized where appropriate:
    "ethernet",
    "fiber",
)

VERIFICATION_STATUS_VALUES = ("confirmed", "observed", "inferred", "manual", "conflicting", "unknown")
PROVENANCE_VALUES = ("discovery_managed", "user_managed", "hybrid")
OBSERVABILITY_VALUES = ("fully_observable", "partially_observable", "not_observable", "not_attempted")

DISCOVERY_MODE_VALUES = ("seed_only", "enterprise_managed", "authorized_expansion")
VIEW_MODE_VALUES = ("internal_only", "internal_and_edge", "all_observed")

EVIDENCE_TYPE_VALUES = (
    "mndp_neighbor",
    "lldp_neighbor",
    "cdp_neighbor",
    "arp_entry",
    "route_entry",
    "dhcp_lease",
    "snmp_interface_data",
    "icmp_ping",
    "ssh_identity",
    "user_confirmed",
    "manual_link",
    "interface_mac_table",
    "bridge_host_table",
    "vpn_interface",
    "traceroute_hop",
)

DEFAULT_TOPOLOGY_POLICY: Dict[str, Any] = {
    "enterprise_id": "default-enterprise",
    "seed_device_id": "",
    "discovery_mode": "seed_only",
    "view_mode": "internal_and_edge",
    "management_subnets": [],
    "enterprise_subnets": [],
    "approved_discovery_scopes": [],
    "excluded_subnets": [],
    "isp_boundary_interfaces": [],
    "known_isp_devices": [],
    "known_external_devices": [],
    "approved_discovery_protocols": ["mndp", "lldp", "cdp", "arp", "route", "bridge", "dhcp"],
    "discovery_depth": 1,
    "allow_routed_expansion": False,
    "auto_include_unknown_neighbors": True,
    "require_review_for_unknown_devices": True,
    "freshness_threshold_sec": 300,
    "expire_threshold_sec": 3600,
    "probe_cooldown_sec": 15,
    "probe_timeout_sec": 4,
    "probe_retries": 1,
    "max_concurrency": 2,
    "max_scan_duration_sec": 45,
}


# ---------------------------------------------------------------------------
# Security & Input Sanitization
# ---------------------------------------------------------------------------

_SECRET_KV_RE = re.compile(
    r"(?i)\b("
    r"password|passphrase|secret|wpa-pre-shared-key|wpa2-pre-shared-key|"
    r"private-key|api-key|api_key|token|snmp-community|community|auth-password|priv-password"
    r")\s*([=:])\s*(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9\-._~+/]+=*")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]{1,200}>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_untrusted_text(value: Any, max_len: int = 512) -> str:
    """
    Sanitizes untrusted CLI/SNMP/neighbor strings for storage and UI rendering.
    Redacts secrets, removes control characters and HTML tags, and bounds length.
    """
    if value is None:
        return ""
    text = str(value)
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    text = _SECRET_KV_RE.sub(r"\1\2[REDACTED]", text)
    text = _BEARER_RE.sub(r"\1 [REDACTED]", text)
    text = _CTRL_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def sanitize_cli_excerpt(raw: str, max_len: int = 800) -> str:
    """Redacts sensitive parameters from multi-line CLI snippets while preserving line breaks."""
    if not raw:
        return ""
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY]", str(raw))
    text = _SECRET_KV_RE.sub(r"\1\2[REDACTED]", text)
    text = _BEARER_RE.sub(r"\1 [REDACTED]", text)
    text = _CTRL_RE.sub("", text)
    # Strip potentially sensitive RouterOS comments containing credentials
    text = re.sub(
        r'(?i)comment=(?:"[^"]*(?:pass|key|secret|token|pin)[^"]*"|\S*(?:pass|key|secret|token)\S*)',
        'comment="[REDACTED_COMMENT]"',
        text,
    )
    text = text.strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# IP / Subnet / MAC Normalization & Validation Helpers
# ---------------------------------------------------------------------------

def normalize_mac(mac: Optional[str]) -> str:
    """Normalizes MAC address to uppercase AA:BB:CC:DD:EE:FF, or '' if invalid."""
    if not mac:
        return ""
    hex_digits = re.sub(r"[^0-9A-Fa-f]", "", str(mac))
    if len(hex_digits) != 12:
        return ""
    return ":".join(hex_digits[i : i + 2].upper() for i in range(0, 12, 2))


def is_randomized_or_local_mac(mac: str) -> bool:
    """Checks IEEE 802 locally-administered bit (bit 1 of first octet) often used in MAC randomization."""
    norm = normalize_mac(mac)
    if not norm:
        return False
    try:
        first_octet = int(norm.split(":")[0], 16)
        return bool(first_octet & 0x02) and not bool(first_octet & 0x01)
    except ValueError:
        return False


def normalize_ip(ip_str: Optional[str]) -> str:
    """Extracts and validates an IPv4/IPv6 address (stripping CIDR prefix or %zone if present)."""
    if not ip_str:
        return ""
    candidate = str(ip_str).strip()
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]
    if "/" in candidate:
        candidate = candidate.split("/", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return ""


def ip_in_subnets(ip_str: str, subnets: Iterable[str]) -> bool:
    """Returns True if ip_str belongs to any valid CIDR or single IP in subnets."""
    norm = normalize_ip(ip_str)
    if not norm:
        return False
    try:
        addr = ipaddress.ip_address(norm)
    except ValueError:
        return False

    for net_str in subnets or []:
        s = str(net_str or "").strip()
        if not s:
            continue
        try:
            net = ipaddress.ip_network(s, strict=False)
            if addr in net:
                return True
        except ValueError:
            continue
    return False


def validate_subnet_list(subnets: Iterable[Any]) -> List[str]:
    """Validates and normalizes a list of CIDR subnets."""
    cleaned: List[str] = []
    for item in subnets or []:
        s = str(item or "").strip()
        if not s:
            continue
        try:
            net = ipaddress.ip_network(s, strict=False)
            cleaned.append(str(net))
        except ValueError as exc:
            raise ValueError(f"Invalid subnet/CIDR '{s}': {exc}") from exc
    return cleaned


def is_vpn_or_tunnel_interface(iface_name: str, iface_type: str = "") -> bool:
    """Detects VPN or logical tunnel interfaces from name or RouterOS interface type."""
    combined = f"{iface_name or ''} {iface_type or ''}".lower()
    vpn_markers = (
        "wg",
        "wireguard",
        "ovpn",
        "openvpn",
        "l2tp",
        "pptp",
        "sstp",
        "ipip",
        "gre",
        "eoip",
        "vxlan",
        "zerotier",
        "tailscale",
        "ipsec",
        "sit",
        "tun",
        "tap",
    )
    return any(
        re.search(rf"(^|[^a-z0-9]){re.escape(m)}([^a-z0-9]|\d|$)", combined)
        for m in vpn_markers
    )


def extract_physical_port_name(raw_iface: str) -> Tuple[str, bool]:
    """
    Extracts underlying physical port from RouterOS interface strings such as
    'ether2,bridge-lan' or 'bridge1'.
    Returns (port_name, is_multipoint_bridge_only).
    """
    if not raw_iface:
        return "", False
    parts = [p.strip() for p in str(raw_iface).split(",") if p.strip()]
    if not parts:
        return "", False

    # Prefer physical port names over logical bridge/vlan wrappers when both are listed
    for p in parts:
        pl = p.lower()
        if not pl.startswith("bridge") and not pl.startswith("vlan"):
            return sanitize_untrusted_text(p, 64), False

    first = sanitize_untrusted_text(parts[0], 64)
    is_bridge = first.lower().startswith("bridge")
    return first, is_bridge


# ---------------------------------------------------------------------------
# ICMP Probe Parser & Bounded Execution
# ---------------------------------------------------------------------------

def parse_ping_output(stdout: str, returncode: int) -> Dict[str, Any]:
    """
    Parses Windows and Unix/Linux ping stdout accurately.
    Note: On Windows, 'Destination host unreachable' from local interface can still exit 0!
    """
    text = stdout or ""
    lower = text.lower()

    # Detect actual echo replies (TTL= on Windows, ttl= / bytes from on Unix)
    has_reply = bool(
        re.search(r"\bttl=\d+", lower)
        or re.search(r"\d+\s+bytes\s+from\s+", lower)
    )
    if "destination host unreachable" in lower or "destination net unreachable" in lower:
        if not re.search(r"ttl=\d+", lower):
            has_reply = False

    alive = (returncode == 0 and has_reply) or has_reply

    avg_rtt: Optional[float] = None
    # Windows: Average = 2ms / Rata-rata = 2ms
    m_win = re.search(r"(?:average|rata-rata)\s*=\s*(\d+(?:\.\d+)?)\s*ms", lower)
    if m_win:
        avg_rtt = float(m_win.group(1))
    else:
        # Unix: min/avg/max/mdev = 0.412/0.523/0.611/0.050 ms
        m_unix = re.search(r"=\s*\d+(?:\.\d+)?/(\d+(?:\.\d+)?)/\d+(?:\.\d+)?", lower)
        if m_unix:
            avg_rtt = float(m_unix.group(1))
        else:
            # Single reply fallback: time=2ms or time<1ms
            m_single = re.search(r"time[=<](\d+(?:\.\d+)?)\s*ms", lower)
            if m_single:
                val = float(m_single.group(1))
                avg_rtt = 0.5 if "time<" in lower and val == 1.0 else val

    return {
        "alive": alive,
        "avg_rtt_ms": round(avg_rtt, 2) if avg_rtt is not None else 0.0,
    }


def bounded_icmp_ping(
    target_ip: str,
    count: int = 1,
    timeout_sec: int = 3,
    retries: int = 1,
) -> Dict[str, Any]:
    """Executes a bounded, timeout-enforced ICMP probe without shell interpolation."""
    clean_ip = normalize_ip(target_ip)
    if not clean_ip:
        return {"success": False, "alive": False, "avg_rtt_ms": 0.0, "error": "Invalid IP address."}

    is_windows = platform.system().lower() == "windows"
    attempts = max(1, min(int(retries) + 1, 3))
    timeout_sec = max(1, min(int(timeout_sec), 10))
    count = max(1, min(int(count), 4))

    last_err = ""
    for _ in range(attempts):
        try:
            extra_kwargs = {}
            if is_windows:
                cmd = ["ping", "-n", str(count), "-w", str(timeout_sec * 1000), clean_ip]
                extra_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            else:
                cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), clean_ip]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec * count + 2,
                **extra_kwargs,
            )
            parsed = parse_ping_output(proc.stdout, proc.returncode)
            if parsed["alive"]:
                return {
                    "success": True,
                    "alive": True,
                    "avg_rtt_ms": parsed["avg_rtt_ms"],
                    "raw_excerpt": sanitize_cli_excerpt(proc.stdout, 300),
                }
            last_err = "No ICMP echo reply received."
        except subprocess.TimeoutExpired:
            last_err = f"ICMP probe timed out after {timeout_sec}s."
        except Exception as exc:
            last_err = sanitize_untrusted_text(str(exc), 160)

    return {
        "success": True,
        "alive": False,
        "avg_rtt_ms": 0.0,
        "error": last_err or "Host did not respond to ICMP echo.",
    }


# ---------------------------------------------------------------------------
# Deterministic Freshness & Multi-Dimensional Node Status Calculation
# ---------------------------------------------------------------------------

def compute_observation_freshness(
    last_seen: Optional[float],
    now: Optional[float] = None,
    fresh_sec: float = 300.0,
    expire_sec: float = 3600.0,
) -> str:
    if not last_seen or last_seen <= 0:
        return "unknown"
    now_ts = now if now is not None else time.time()
    age = max(0.0, now_ts - float(last_seen))
    if age <= fresh_sec:
        return "fresh"
    if age <= expire_sec:
        return "stale"
    return "expired"


def calculate_deterministic_node_status(
    *,
    evidence_list: List[Dict[str, Any]],
    last_seen: Optional[float],
    last_probe_at: Optional[float],
    last_ping_alive: Optional[bool],
    ssh_ok: Optional[bool],
    management_authorized: bool,
    provenance: str,
    current_legacy_status: str = "online",
    now: Optional[float] = None,
    fresh_sec: float = 300.0,
    expire_sec: float = 3600.0,
) -> Dict[str, str]:
    """
    Computes independent reachability_status, management_status, observation_freshness,
    availability_reason, and backward-compatible legacy status ('online'|'warning'|'offline').
    Never treats ARP-only or route-only observations as proof of live reachability.
    """
    now_ts = now if now is not None else time.time()
    freshness = compute_observation_freshness(last_seen, now=now_ts, fresh_sec=fresh_sec, expire_sec=expire_sec)

    # 1. Management status
    if ssh_ok is True:
        mgmt_status = "managed"
    elif ssh_ok is False:
        mgmt_status = "management_unavailable"
    elif not management_authorized:
        mgmt_status = "not_authorized"
    else:
        mgmt_status = "not_attempted"

    # Gather fresh active evidence types
    ev_types = {e.get("evidence_type") for e in (evidence_list or [])}
    fresh_l2 = any(
        e.get("evidence_type") in ("mndp_neighbor", "lldp_neighbor", "cdp_neighbor")
        and compute_observation_freshness(e.get("observed_at"), now=now_ts, fresh_sec=fresh_sec, expire_sec=expire_sec) == "fresh"
        for e in (evidence_list or [])
    )
    fresh_ssh = any(
        e.get("evidence_type") == "ssh_identity"
        and compute_observation_freshness(e.get("observed_at"), now=now_ts, fresh_sec=fresh_sec, expire_sec=expire_sec) == "fresh"
        for e in (evidence_list or [])
    )
    ping_fresh = (
        last_probe_at is not None
        and compute_observation_freshness(last_probe_at, now=now_ts, fresh_sec=fresh_sec, expire_sec=expire_sec) == "fresh"
    )

    is_pure_manual = (
        provenance == "user_managed"
        and ev_types.issubset({"user_confirmed"})
        and last_ping_alive is None
        and ssh_ok is None
    )

    # 2. Reachability status & reason
    if ssh_ok is True or (ssh_ok is None and fresh_ssh):
        reachability = "reachable"
        reason = "Authenticated SSH management interrogation succeeded."
    elif last_ping_alive is True and ping_fresh:
        reachability = "reachable"
        if ssh_ok is False:
            reason = "Responds to ICMP ping, but SSH management service is unavailable."
        else:
            reason = "Verified reachable via recent ICMP echo reply."
    elif fresh_l2:
        if last_ping_alive is False and ping_fresh:
            reachability = "reachable"
            reason = "Active L2 neighbor advertisements received (ICMP echo blocked or unanswered)."
        elif ssh_ok is False:
            reachability = "reachable"
            reason = "Active L2 neighbor advertisements received, though management port is unreachable."
        else:
            reachability = "reachable"
            reason = "Observed via fresh Layer 2 discovery advertisements (MNDP/LLDP/CDP)."
    elif last_ping_alive is False and ping_fresh:
        reachability = "unreachable"
        reason = "Recent ICMP echo probe timed out and no fresh Layer 2 or SSH telemetry is present."
    elif ssh_ok is False:
        reachability = "unknown"
        reason = "SSH management service is unavailable; device may still be forwarding traffic."
    elif ev_types and ev_types.issubset({"arp_entry", "dhcp_lease", "route_entry"}):
        reachability = "unknown"
        if "arp_entry" in ev_types:
            reason = "Observed in ARP table only; cached ARP entries do not independently confirm active availability."
        elif "route_entry" in ev_types:
            reason = "Inferred from routing table next-hop; reachability has not been actively verified."
        else:
            reason = "Observed via DHCP lease record only; live reachability unverified."
    elif freshness in ("stale", "expired") and not is_pure_manual:
        reachability = "unknown"
        reason = f"Last observation is {freshness}; current device reachability is unconfirmed."
    elif is_pure_manual:
        if current_legacy_status == "offline":
            reachability = "unreachable"
            reason = "Manually set to offline by administrator."
        elif current_legacy_status == "online":
            reachability = "unknown"
            reason = "Manually added node; awaiting active reachability verification."
        else:
            reachability = "unknown"
            reason = "Manually configured node."
    else:
        reachability = "unknown"
        reason = "Insufficient live telemetry to confirm reachability."

    # 3. Derive backward-compatible legacy status
    if is_pure_manual:
        legacy_status = current_legacy_status or "online"
    elif reachability == "unreachable":
        legacy_status = "offline"
    elif reachability == "reachable" and freshness == "fresh" and mgmt_status != "management_unavailable":
        legacy_status = "online"
    elif reachability == "reachable" and mgmt_status == "management_unavailable":
        legacy_status = "warning"
    else:
        legacy_status = "warning"

    return {
        "reachability_status": reachability,
        "management_status": mgmt_status,
        "observation_freshness": freshness,
        "availability_reason": reason,
        "legacy_status": legacy_status,
    }
