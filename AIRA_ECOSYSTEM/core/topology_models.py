"""
core/topology_models.py — Domain constants, enums, sanitizers, network scope helpers,
and deterministic status/confidence calculators for AIRA Topology Fabric V2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import ipaddress
import json
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
    if not last_seen:
        return "unknown"
    try:
        ls_val = float(last_seen)
    except (TypeError, ValueError):
        try:
            from datetime import datetime
            ls_val = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00")).timestamp()
        except Exception:
            return "unknown"
    if ls_val <= 0:
        return "unknown"
    now_ts = now if now is not None else time.time()
    age = max(0.0, now_ts - ls_val)
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


# ===========================================================================
# Phase 4.1: Networking IV Graph Data Models & Normalized Entities
# ===========================================================================

class RelationshipClass(str, Enum):
    """Normalized four-class topology relationship taxonomy."""
    PHYSICAL_ADJACENCY = "physical"
    LAYER2_ADJACENCY = "layer2"
    LAYER3_REACHABILITY = "layer3"
    LOGICAL_RELATIONSHIP = "logical"


class EdgeLifecycleState(str, Enum):
    """Lifecycle states for graph edges to avoid flappiness."""
    ACTIVE = "active"
    STALE = "stale"
    TOMBSTONED = "tombstoned"


class TopologyChangeType(str, Enum):
    """Deterministic change event types for topology graph deltas."""
    NODE_ADDED = "NODE_ADDED"
    NODE_REMOVED = "NODE_REMOVED"
    NODE_MODIFIED = "NODE_MODIFIED"
    EDGE_ADDED = "EDGE_ADDED"
    EDGE_REMOVED = "EDGE_REMOVED"
    EDGE_MODIFIED = "EDGE_MODIFIED"
    STATUS_CHANGED = "STATUS_CHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    FRESHNESS_CHANGED = "FRESHNESS_CHANGED"
    CONFIDENCE_CHANGED = "CONFIDENCE_CHANGED"


class ConfidenceTier(str, Enum):
    """Hierarchical confidence tiers for topology relationships."""
    CONFIRMED = "CONFIRMED"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


RELATIONSHIP_CLASS_VALUES = ("physical", "layer2", "layer3", "logical")
EDGE_LIFECYCLE_VALUES = ("active", "stale", "tombstoned")
CONFIDENCE_TIER_VALUES = ("CONFIRMED", "HIGH", "MEDIUM", "LOW")
TOPOLOGY_CHANGE_TYPE_VALUES = (
    "NODE_ADDED",
    "NODE_REMOVED",
    "NODE_MODIFIED",
    "EDGE_ADDED",
    "EDGE_REMOVED",
    "EDGE_MODIFIED",
    "STATUS_CHANGED",
    "EVIDENCE_CHANGED",
    "EVIDENCE_EXPIRED",
    "FRESHNESS_CHANGED",
    "CONFIDENCE_CHANGED",
)


def normalize_relationship_class(val: Any) -> str:
    """Normalizes and validates relationship class against four explicit classes."""
    if val is None:
        raise ValueError("relationship_class cannot be None.")
    s = str(val).strip().lower()
    mapping = {
        "physical": "physical",
        "physical_adjacency": "physical",
        "layer2": "layer2",
        "layer2_adjacency": "layer2",
        "layer3": "layer3",
        "layer3_reachability": "layer3",
        "logical": "logical",
        "logical_relationship": "logical",
    }
    if s in mapping:
        return mapping[s]
    raise ValueError(
        f"Invalid relationship_class '{val}'. Must be one of: "
        f"{', '.join(RELATIONSHIP_CLASS_VALUES)}."
    )


def normalize_edge_lifecycle_state(val: Any) -> str:
    """Normalizes and validates edge lifecycle state."""
    if val is None:
        raise ValueError("lifecycle_state cannot be None.")
    s = str(val).strip().lower()
    if s in EDGE_LIFECYCLE_VALUES:
        return s
    raise ValueError(
        f"Invalid lifecycle_state '{val}'. Must be one of: "
        f"{', '.join(EDGE_LIFECYCLE_VALUES)}."
    )


def normalize_confidence_tier(val: Any) -> str:
    """Normalizes and validates confidence tier."""
    if val is None:
        raise ValueError("confidence_tier cannot be None.")
    s = str(val).strip().upper()
    if s in CONFIDENCE_TIER_VALUES:
        return s
    raise ValueError(
        f"Invalid confidence_tier '{val}'. Must be one of: "
        f"{', '.join(CONFIDENCE_TIER_VALUES)}."
    )


def normalize_topology_change_type(val: Any) -> str:
    """Normalizes and validates topology delta change type."""
    if val is None:
        raise ValueError("change_type cannot be None.")
    s = str(val).strip().upper()
    if s in TOPOLOGY_CHANGE_TYPE_VALUES:
        return s
    raise ValueError(
        f"Invalid change_type '{val}'. Must be one of: "
        f"{', '.join(TOPOLOGY_CHANGE_TYPE_VALUES)}."
    )


# ===========================================================================
# Phase 4.2: Evidence Protocol Weights, Half-Life Decay & Mathematical Scoring
# ===========================================================================

EVIDENCE_PROTOCOL_WEIGHTS: Dict[str, float] = {
    "operator_confirmation": 1.00,
    "user_confirmed": 1.00,
    "manual": 1.00,
    "bidirectional_l2": 0.95,
    "mndp_bidirectional": 0.95,
    "lldp_bidirectional": 0.95,
    "cdp_bidirectional": 0.95,
    "single_sided_l2": 0.80,
    "mndp_neighbor": 0.80,
    "lldp_neighbor": 0.80,
    "cdp_neighbor": 0.80,
    "mndp": 0.80,
    "lldp": 0.80,
    "cdp": 0.80,
    "overlay_tunnel": 0.85,
    "wireguard_peer": 0.85,
    "vpn": 0.85,
    "dedicated_p2p_subnet": 0.75,
    "routed_p2p": 0.75,
    "mutual_arp_multiaccess": 0.55,
    "single_sided_arp": 0.35,
    "arp_entry": 0.35,
    "arp": 0.35,
    "routing_nexthop": 0.30,
    "route_entry": 0.30,
    "routing_table": 0.30,
    "bridge_host_table": 0.25,
    "bridge_fdb": 0.25,
    "dhcp_lease": 0.20,
    "dhcp": 0.20,
    "randomized_mac": 0.05,
}

EVIDENCE_HALF_LIVES: Dict[str, float] = {
    "mndp": 180.0,
    "lldp": 180.0,
    "cdp": 180.0,
    "mndp_neighbor": 180.0,
    "lldp_neighbor": 180.0,
    "cdp_neighbor": 180.0,
    "bidirectional_l2": 180.0,
    "single_sided_l2": 180.0,
    "arp": 900.0,
    "arp_entry": 900.0,
    "single_sided_arp": 900.0,
    "mutual_arp_multiaccess": 900.0,
    "dedicated_p2p_subnet": 900.0,
    "dhcp": 900.0,
    "dhcp_lease": 900.0,
    "bridge_fdb": 900.0,
    "bridge_host_table": 900.0,
    "routing_table": 1800.0,
    "route_entry": 1800.0,
    "routing_nexthop": 1800.0,
    "overlay_tunnel": 1800.0,
    "wireguard_peer": 1800.0,
    "operator_confirmation": float("inf"),
    "user_confirmed": float("inf"),
    "manual": float("inf"),
}

DEFAULT_HALF_LIFE: float = 900.0


def calculate_edge_confidence(
    evidence_items: List[Any],
    *,
    is_bidirectional: bool = False,
    contradiction_penalty: float = 0.0,
    now_ts: Optional[float] = None,
) -> Tuple[float, str, str]:
    """
    Computes mathematical confidence score S(e), confidence tier, and qualitative rationale
    per AIRA-NET-IV-CONFIDENCE-001.

    Formula:
        S(e) = min(1.0, max(0.0, (sum(W_k * D_k(delta_t))) * C_dir * (1 - P_contra)))
    """
    now = now_ts if now_ts is not None else time.time()
    if not evidence_items:
        return 0.0, ConfidenceTier.LOW.value, "No empirical evidence observed."

    p_contra = min(1.0, max(0.0, float(contradiction_penalty)))
    if p_contra >= 1.0:
        return 0.0, ConfidenceTier.LOW.value, "Physical or operational carrier down; edge confidence collapsed."

    c_dir = 1.0 if is_bidirectional else 1.0

    weighted_sum = 0.0
    best_effective_w = 0.0
    primary_rationale = ""
    is_manual = False
    has_bidirectional = is_bidirectional

    for item in evidence_items:
        ev_type = getattr(item, "evidence_type", None) or (item.get("evidence_type") if isinstance(item, dict) else "")
        proto = getattr(item, "protocol", None) or (item.get("protocol") if isinstance(item, dict) else "")
        observed_at = getattr(item, "observed_at", None) or (item.get("observed_at") if isinstance(item, dict) else now)
        custom_explanation = getattr(item, "explanation", None) or (item.get("explanation") if isinstance(item, dict) else "")

        w = EVIDENCE_PROTOCOL_WEIGHTS.get(ev_type)
        if w is None:
            w = EVIDENCE_PROTOCOL_WEIGHTS.get(proto, 0.30)

        if ev_type in ("bidirectional_l2", "mndp_bidirectional", "lldp_bidirectional", "cdp_bidirectional"):
            has_bidirectional = True

        tau = EVIDENCE_HALF_LIVES.get(proto)
        if tau is None:
            tau = EVIDENCE_HALF_LIVES.get(ev_type, DEFAULT_HALF_LIFE)

        if tau == float("inf") or ev_type in ("operator_confirmation", "user_confirmed", "manual"):
            decay = 1.0
            is_manual = True
        else:
            delta_t = max(0.0, now - float(observed_at or now))
            decay = 2.0 ** (-delta_t / tau)

        effective_w = w * decay
        weighted_sum += effective_w

        if effective_w > best_effective_w:
            best_effective_w = effective_w
            if custom_explanation:
                primary_rationale = custom_explanation

    raw_score = weighted_sum * c_dir * (1.0 - p_contra)
    score = round(min(1.0, max(0.0, raw_score)), 3)

    if score >= 0.90 or has_bidirectional or is_manual:
        tier = ConfidenceTier.CONFIRMED.value
        if not primary_rationale:
            primary_rationale = "Bidirectional protocol verification or verified operator manual wiring."
    elif score >= 0.70:
        tier = ConfidenceTier.HIGH.value
        if not primary_rationale:
            primary_rationale = "Single-sided neighbor protocol or exclusive point-to-point /30 mutual ARP."
    elif score >= 0.40:
        tier = ConfidenceTier.MEDIUM.value
        if not primary_rationale:
            primary_rationale = "Inferred from shared multi-access subnet, routing next-hop, or tunnel configuration."
    else:
        tier = ConfidenceTier.LOW.value
        if not primary_rationale:
            primary_rationale = "Single ARP cache entry or randomized MAC address; physical connection unverified."

    return score, tier, primary_rationale


@dataclass
class TopologyEdge:
    """
    Phase 4.1 Normalized Multi-Edge Data Model.
    Supports multiple distinct edges between identical node pairs,
    strict semantic relationship separation, mandatory qualitative rationale,
    and granular lifecycle state tracking.
    """
    id: str
    source_node_id: str
    target_node_id: str
    source_interface: str = ""
    target_interface: str = ""
    relationship_class: str = "physical"
    relationship_subtype: str = "direct_copper"
    direction: str = "bidirectional"
    oper_status: str = "up"
    admin_status: str = "enabled"
    verification_status: str = "confirmed"
    confidence_tier: str = "CONFIRMED"
    confidence_score: float = 1.0
    confidence_rationale: str = ""
    bandwidth_bps: int = 1_000_000_000
    vlan_id: Optional[int] = None
    is_lag_member: bool = False
    lag_parent_edge_id: Optional[str] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_verified: Optional[float] = None
    observation_freshness: str = "fresh"
    lifecycle_state: str = "active"
    provenance: str = "discovery_managed"
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("TopologyEdge.id cannot be empty.")
        if not self.source_node_id or not str(self.source_node_id).strip():
            raise ValueError("TopologyEdge.source_node_id cannot be empty.")
        if not self.target_node_id or not str(self.target_node_id).strip():
            raise ValueError("TopologyEdge.target_node_id cannot be empty.")

        self.relationship_class = normalize_relationship_class(self.relationship_class)
        self.lifecycle_state = normalize_edge_lifecycle_state(self.lifecycle_state)
        self.confidence_tier = normalize_confidence_tier(self.confidence_tier)

        try:
            self.confidence_score = float(self.confidence_score)
        except (ValueError, TypeError):
            raise ValueError(f"confidence_score must be a float, got {self.confidence_score}")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(f"confidence_score must be between 0.0 and 1.0, got {self.confidence_score}")

        if not self.confidence_rationale or not str(self.confidence_rationale).strip():
            raise ValueError("confidence_rationale must be provided and non-empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "source_interface": self.source_interface,
            "target_interface": self.target_interface,
            "relationship_class": self.relationship_class,
            "relationship_subtype": self.relationship_subtype,
            "direction": self.direction,
            "oper_status": self.oper_status,
            "admin_status": self.admin_status,
            "verification_status": self.verification_status,
            "confidence_tier": self.confidence_tier,
            "confidence_score": self.confidence_score,
            "confidence_rationale": self.confidence_rationale,
            "bandwidth_bps": self.bandwidth_bps,
            "vlan_id": self.vlan_id,
            "is_lag_member": self.is_lag_member,
            "lag_parent_edge_id": self.lag_parent_edge_id,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "last_verified": self.last_verified,
            "observation_freshness": self.observation_freshness,
            "lifecycle_state": self.lifecycle_state,
            "provenance": self.provenance,
            "user_overrides": self.user_overrides,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TopologyEdge:
        payload = dict(data)
        if "user_overrides_json" in payload and "user_overrides" not in payload:
            raw = payload.pop("user_overrides_json")
            payload["user_overrides"] = json.loads(raw) if isinstance(raw, str) and raw else {}
        if "metadata_json" in payload and "metadata" not in payload:
            raw = payload.pop("metadata_json")
            payload["metadata"] = json.loads(raw) if isinstance(raw, str) and raw else {}
        if "is_lag_member" in payload and isinstance(payload["is_lag_member"], int):
            payload["is_lag_member"] = bool(payload["is_lag_member"])
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in payload.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class EdgeEvidence:
    """
    Phase 4.1 Verifiable Edge Evidence Model.
    Provides first-class provenance, observing device tracking, sanitized raw excerpts,
    and TTL-based freshness management.
    """
    id: Optional[int] = None
    edge_id: str = ""
    evidence_type: str = ""
    protocol: str = ""
    observing_device_id: str = ""
    local_interface: str = ""
    remote_interface: str = ""
    remote_chassis_mac: str = ""
    raw_excerpt: str = ""
    confidence_contribution: str = "medium"
    explanation: str = ""
    observed_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.edge_id or not str(self.edge_id).strip():
            raise ValueError("EdgeEvidence.edge_id cannot be empty.")
        if not self.evidence_type or not str(self.evidence_type).strip():
            raise ValueError("EdgeEvidence.evidence_type cannot be empty.")
        if not self.observing_device_id or not str(self.observing_device_id).strip():
            raise ValueError("EdgeEvidence.observing_device_id cannot be empty.")
        if self.raw_excerpt:
            self.raw_excerpt = sanitize_cli_excerpt(self.raw_excerpt, 800)
        if self.explanation:
            self.explanation = sanitize_untrusted_text(self.explanation, 400)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "edge_id": self.edge_id,
            "evidence_type": self.evidence_type,
            "protocol": self.protocol,
            "observing_device_id": self.observing_device_id,
            "local_interface": self.local_interface,
            "remote_interface": self.remote_interface,
            "remote_chassis_mac": self.remote_chassis_mac,
            "raw_excerpt": self.raw_excerpt,
            "confidence_contribution": self.confidence_contribution,
            "explanation": self.explanation,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EdgeEvidence:
        payload = dict(data)
        if "metadata_json" in payload and "metadata" not in payload:
            raw = payload.pop("metadata_json")
            payload["metadata"] = json.loads(raw) if isinstance(raw, str) and raw else {}
        if "is_active" in payload and isinstance(payload["is_active"], int):
            payload["is_active"] = bool(payload["is_active"])
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in payload.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class TopologySnapshot:
    """
    Phase 4.1 Immutable Topology Snapshot Model.
    Represents an immutable point-in-time state of the network graph
    protected by SHA-256 cryptographic verification and database triggers.
    """
    snapshot_id: str
    schema_version: str = "4.1"
    discovery_run_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    node_count: int = 0
    edge_count: int = 0
    graph_json: str = "{}"
    sha256_hash: str = ""
    trigger_type: str = "discovery_run"
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.snapshot_id or not str(self.snapshot_id).strip():
            raise ValueError("TopologySnapshot.snapshot_id cannot be empty.")
        if not self.sha256_hash and self.graph_json:
            self.sha256_hash = self.calculate_checksum()

    def calculate_checksum(self) -> str:
        return hashlib.sha256(self.graph_json.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        return self.sha256_hash == self.calculate_checksum()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "schema_version": self.schema_version,
            "discovery_run_id": self.discovery_run_id,
            "created_at": self.created_at,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "graph_json": self.graph_json,
            "sha256_hash": self.sha256_hash,
            "trigger_type": self.trigger_type,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TopologySnapshot:
        payload = dict(data)
        if "metadata_json" in payload and "metadata" not in payload:
            raw = payload.pop("metadata_json")
            payload["metadata"] = json.loads(raw) if isinstance(raw, str) and raw else {}
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in payload.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class TopologyChange:
    """
    Phase 4.1 Topology Delta Change Model.
    Tracks structural and state modifications across snapshots.
    """
    id: Optional[int] = None
    snapshot_id: Optional[str] = None
    change_type: str = "STATUS_CHANGED"
    entity_id: str = ""
    change_reason: str = ""
    attribute_name: str = ""
    before_value_json: str = ""
    after_value_json: str = ""
    detected_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.change_type = normalize_topology_change_type(self.change_type)
        if not self.entity_id or not str(self.entity_id).strip():
            raise ValueError("TopologyChange.entity_id cannot be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "change_type": self.change_type,
            "entity_id": self.entity_id,
            "change_reason": self.change_reason,
            "attribute_name": self.attribute_name,
            "before_value_json": self.before_value_json,
            "after_value_json": self.after_value_json,
            "detected_at": self.detected_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TopologyChange:
        payload = dict(data)
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in payload.items() if k in valid_keys}
        return cls(**filtered)


def normalize_interface_name(val: Any) -> str:
    """Normalizes interface identifiers for deterministic fallback comparison."""
    if not val:
        return ""
    s = str(val).strip().lower()
    return re.sub(r"\s+", "", s)


def compute_edge_canonical_key(edge: Dict[str, Any]) -> Tuple[Any, ...]:
    """
    Computes deterministic multi-edge fallback canonical identity key.
    Preserves endpoint-interface tuple pairings (T_A, T_B) and relationship semantics.
    For layer3 next_hop_reachability, preserves direction (source -> target).
    """
    rel_class = normalize_relationship_class(edge.get("relationship_class", "physical"))
    subtype = str(edge.get("relationship_subtype") or "").strip().lower()

    u = str(edge.get("source_node_id") or "").strip()
    v = str(edge.get("target_node_id") or "").strip()
    i_u = normalize_interface_name(edge.get("source_interface") or "")
    i_v = normalize_interface_name(edge.get("target_interface") or "")

    meta = edge.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    T1 = (u, i_u)
    T2 = (v, i_v)
    T_A, T_B = (T1, T2) if T1 <= T2 else (T2, T1)

    if rel_class == "physical":
        return ("physical", subtype or "ethernet", T_A, T_B)
    elif rel_class == "layer2":
        vlan_raw = meta.get("vlan_id") if "vlan_id" in meta else (meta.get("vlan") if "vlan" in meta else 0)
        try:
            vlan_id = int(vlan_raw)
        except (ValueError, TypeError):
            vlan_id = str(vlan_raw)
        return ("layer2", subtype or "bridge_domain", T_A, T_B, vlan_id)
    elif rel_class == "layer3":
        if subtype == "next_hop_reachability" or edge.get("relationship_subtype") == "next_hop_reachability":
            # Directed: source -> target MUST be preserved!
            nexthop = str(meta.get("nexthop_ip") or meta.get("next_hop") or meta.get("ip") or "").strip().lower()
            return ("layer3", "next_hop_reachability", u, v, nexthop)
        else:
            cidr = str(meta.get("subnet_cidr") or meta.get("network_cidr") or meta.get("cidr") or "").strip().lower()
            return ("layer3", subtype or "routed_point_to_point", T_A, T_B, cidr)
    elif rel_class == "logical":
        overlay = str(meta.get("tunnel_id") or meta.get("vni") or meta.get("vpn_id") or meta.get("overlay_id") or "").strip().lower()
        return ("logical", subtype or "overlay", T_A, T_B, overlay)
    else:
        return (rel_class, subtype, T_A, T_B)


@dataclass
class GraphDiffReport:
    """
    Phase 4.4A Semantic Graph Diff Report Model.
    Captures multi-edge, operational, freshness, and evidence deltas across snapshots
    with epistemic safeguards against false removals.
    """
    base_snapshot_id: str
    target_snapshot_id: str
    generated_at: float = field(default_factory=time.time)
    summary: Dict[str, int] = field(default_factory=dict)
    structural_changes: List[Dict[str, Any]] = field(default_factory=list)
    operational_changes: List[Dict[str, Any]] = field(default_factory=list)
    evidence_changes: List[Dict[str, Any]] = field(default_factory=list)
    freshness_changes: List[Dict[str, Any]] = field(default_factory=list)
    indeterminate_items: List[Dict[str, Any]] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_snapshot_id": self.base_snapshot_id,
            "target_snapshot_id": self.target_snapshot_id,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "structural_changes": self.structural_changes,
            "operational_changes": self.operational_changes,
            "evidence_changes": self.evidence_changes,
            "freshness_changes": self.freshness_changes,
            "indeterminate_items": self.indeterminate_items,
            "telemetry": self.telemetry,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphDiffReport:
        payload = dict(data)
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in payload.items() if k in valid_keys}
        return cls(**filtered)
