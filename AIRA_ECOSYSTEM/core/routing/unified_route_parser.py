"""
AIRA OS - Unified Route Parser & Routing Intelligence Engine (Phase 4.6 / WP 4.6.0).

Authoritative parser for MikroTik RouterOS v6 and v7 routing tables.
Standardizes routing outputs into canonical NormalizedRoute records,
provides deterministic Longest Prefix Match (LPM) evaluation with strict
active/inactive FIB filtering (D6 remediation), and handles recursive
gateway resolution with loop detection.
"""

from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RouteProtocol(str, Enum):
    CONNECTED = "connected"
    STATIC = "static"
    OSPF = "ospf"
    BGP = "bgp"
    RIP = "rip"
    MME = "mme"
    VPN = "vpn"
    UNKNOWN = "unknown"


class RouteType(str, Enum):
    UNICAST = "unicast"
    BLACKHOLE = "blackhole"
    UNREACHABLE = "unreachable"
    PROHIBIT = "prohibit"


class NextHopResolutionStatus(str, Enum):
    DIRECTLY_CONNECTED = "DIRECTLY_CONNECTED"
    RECURSIVE_RESOLVED = "RECURSIVE_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    UNREACHABLE = "UNREACHABLE"
    AMBIGUOUS = "AMBIGUOUS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# Canonical Data Models
# ---------------------------------------------------------------------------

@dataclass
class NormalizedRoute:
    """
    Canonical representation of an IP route across RouterOS v6 and v7.
    Forward-compatible with IPv6 and maintains backward compatibility
    with legacy ParsedRoute and topology dictionary consumers.
    """
    # Addressing & Identification
    dst_prefix: str = "0.0.0.0/0"
    gateway: str = ""
    device_id: str = ""
    interface_name: Optional[str] = None
    routing_table: str = "main"
    address_family: str = "ipv4"

    # Forwarding & Next-Hop State (FIB)
    gateways: List[str] = field(default_factory=list)
    immediate_gw: Optional[str] = None
    pref_src: Optional[str] = None

    # Metrics & Protocol
    protocol: str = "static"
    distance: int = 1
    metric: Optional[int] = None
    scope: Optional[int] = None
    target_scope: Optional[int] = None

    # Operational Status
    active: bool = True
    disabled: bool = False
    unreachable: bool = False
    selected: Optional[bool] = None  # None unless explicitly proven by FIB evidence
    dynamic: bool = False
    connect: bool = False
    static: bool = False
    ospf: bool = False
    bgp: bool = False
    rip: bool = False
    route_type: RouteType = RouteType.UNICAST

    # Metadata & Raw Provenance
    source_ros_version: Optional[int] = None  # 6 or 7
    raw_flags: str = ""
    prefix_len: int = 0
    collection_timestamp: Optional[float] = None
    parser_version: str = "1.0.0"
    evidence_provenance: Dict[str, Any] = field(default_factory=dict)
    raw_attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # 1. Normalize and canonicalize destination prefix
        self.dst_prefix = _canonicalize_prefix(self.dst_prefix)
        slash = self.dst_prefix.find("/")
        if slash != -1:
            try:
                self.prefix_len = int(self.dst_prefix[slash + 1:])
            except ValueError:
                self.prefix_len = 0
            self.address_family = "ipv6" if ":" in self.dst_prefix else "ipv4"
        else:
            self.prefix_len = 32 if "." in self.dst_prefix else 0
            self.address_family = "ipv4"

        # 2. Synchronize gateways list
        if not self.gateways and self.gateway:
            if "," in self.gateway:
                self.gateways = [g.strip() for g in self.gateway.split(",") if g.strip()]
            else:
                self.gateways = [self.gateway.strip()]
        elif self.gateways and not self.gateway:
            self.gateway = self.gateways[0]

        # 3. Synchronize protocol boolean flags
        proto_lower = str(self.protocol).lower()
        if "connect" in proto_lower:
            self.connect = True
            self.protocol = RouteProtocol.CONNECTED.value
        elif "static" in proto_lower:
            self.static = True
            self.protocol = RouteProtocol.STATIC.value
        elif "ospf" in proto_lower:
            self.ospf = True
            self.protocol = RouteProtocol.OSPF.value
        elif "bgp" in proto_lower:
            self.bgp = True
            self.protocol = RouteProtocol.BGP.value
        elif "rip" in proto_lower:
            self.rip = True
            self.protocol = RouteProtocol.RIP.value

        # 4. If disabled or unreachable, cannot be active in FIB
        if self.disabled or self.unreachable:
            self.active = False

    @property
    def destination(self) -> str:
        return self.dst_prefix

    @property
    def dst_address(self) -> str:
        return self.dst_prefix

    @property
    def interface(self) -> Optional[str]:
        return self.interface_name

    @property
    def network(self) -> Optional[ipaddress.IPv4Network]:
        try:
            net = ipaddress.ip_network(self.dst_prefix, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                return net
            return None
        except Exception:
            return None

    def is_default_route(self) -> bool:
        return self.dst_prefix in ("0.0.0.0/0", "::/0")

    def matches_address(self, ip_str: str) -> bool:
        """Evaluates whether an IP address matches this route's destination prefix."""
        try:
            target = ipaddress.ip_address(ip_str.strip())
            net = ipaddress.ip_network(self.dst_prefix, strict=False)
            return target in net
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Comprehensive dictionary representation preserving legacy and new fields."""
        return {
            "device_id": self.device_id,
            "dst_prefix": self.dst_prefix,
            "destination": self.dst_prefix,
            "gateway": self.gateway,
            "gateways": list(self.gateways),
            "immediate_gw": self.immediate_gw,
            "interface_name": self.interface_name,
            "interface": self.interface_name,
            "routing_table": self.routing_table,
            "address_family": self.address_family,
            "protocol": self.protocol,
            "distance": self.distance,
            "metric": self.metric,
            "scope": self.scope,
            "target_scope": self.target_scope,
            "pref_src": self.pref_src,
            "active": self.active,
            "disabled": self.disabled,
            "unreachable": self.unreachable,
            "selected": self.selected,
            "dynamic": self.dynamic,
            "connect": self.connect,
            "static": self.static,
            "ospf": self.ospf,
            "bgp": self.bgp,
            "rip": self.rip,
            "route_type": self.route_type.value if hasattr(self.route_type, "value") else str(self.route_type),
            "prefix_len": self.prefix_len,
            "raw_flags": self.raw_flags,
            "source_ros_version": self.source_ros_version,
            "parser_version": self.parser_version,
            "collection_timestamp": self.collection_timestamp,
        }

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Backward-compatible dict conforming to ParsedRoute schema."""
        return {
            "dst_address": self.dst_prefix,
            "pref_src": self.pref_src,
            "gateway": self.gateway,
            "gateway_status": self.immediate_gw or self.gateway,
            "distance": self.distance,
            "scope": self.scope,
            "target_scope": self.target_scope,
            "active": self.active,
            "dynamic": self.dynamic,
            "connect": self.connect,
            "static": self.static,
            "ospf": self.ospf,
            "bgp": self.bgp,
            "disabled": self.disabled,
            "interface": self.interface_name,
            "raw_flags": self.raw_flags,
            "routing_table": self.routing_table,
        }

    def to_topology_dict(self) -> Dict[str, Any]:
        """Backward-compatible dict conforming to core/topology_parsers schema."""
        gw_ip = _extract_ipv4(self.gateway) if not self.connect else None
        return {
            "dst": self.dst_prefix,
            "gateway_ip": gw_ip,
            "gateway_raw": self.gateway,
            "interface": self.interface_name or (self.gateway if self.connect else ""),
            "active": self.active,
            "connected": self.connect,
            "distance": self.distance,
            "scope": self.scope,
            "target_scope": self.target_scope,
            "flags": self.raw_flags,
            "protocol": self.protocol,
            "raw": self.raw_attributes.get("_raw", ""),
        }


@dataclass
class NextHopResolution:
    """Result of recursive next-hop resolution."""
    status: NextHopResolutionStatus
    target_gateway: str
    resolved_ip: Optional[str] = None
    egress_interface: Optional[str] = None
    depth: int = 0
    resolution_chain: List[str] = field(default_factory=list)
    loop_detected: bool = False
    confidence: float = 1.0
    reason: str = ""


@dataclass
class RouteParseReport:
    """Report detailing execution metrics and large-table thresholds."""
    status: str = "COMPLETE"  # COMPLETE, WARNING_LARGE_TABLE, LIMIT_EXCEEDED, EMPTY, ERROR
    total_parsed: int = 0
    active_count: int = 0
    elapsed_ms: float = 0.0
    warning: Optional[str] = None
    is_partial: bool = False


# ---------------------------------------------------------------------------
# Authoritative Unified Route Parser
# ---------------------------------------------------------------------------

class UnifiedRouteParser:
    """
    Unified, high-performance, line-folding route parser supporting
    RouterOS v6 and v7 detail and tabular CLI formats.
    """

    # Configurable limits per Decision 9
    MAX_NORMAL_ROUTES: int = 5000       # Tier 1 threshold
    MAX_WARNING_ROUTES: int = 20000     # Tier 2 ceiling
    MAX_ABSOLUTE_ROUTES: int = 20000    # Tier 3 hard limit
    EXECUTION_TIMEOUT_SEC: float = 15.0

    # Regex matches key=value where value can contain spaces (unquoted phrases like gateway-status)
    # up to the next key=value or end of line.
    _KV_RE = re.compile(r'([a-zA-Z0-9_\-]+)=(.*?)(?=\s+[a-zA-Z0-9_\-]+=\S+|\Z)')
    _TAB_LINE_RE = re.compile(r'^\s*(\d+)\s+([A-Za-z\s]{1,6}?)\s+([0-9\.\/]+)\s+(.*)$')

    def __init__(self, max_routes: int = MAX_ABSOLUTE_ROUTES):
        self.max_routes = max_routes

    def parse(
        self,
        raw_text: str,
        device_id: str = "",
        ros_version: Optional[int] = None,
    ) -> List[NormalizedRoute]:
        """Parses raw RouterOS route output into a list of NormalizedRoute records."""
        routes, _ = self.parse_with_report(raw_text, device_id=device_id, ros_version=ros_version)
        return routes

    def parse_with_report(
        self,
        raw_text: str,
        device_id: str = "",
        ros_version: Optional[int] = None,
    ) -> Tuple[List[NormalizedRoute], RouteParseReport]:
        """
        Parses raw text and returns both the normalized routes and an observability report
        detailing parser execution metrics, large-table warnings, and status.
        """
        t0 = time.perf_counter()
        report = RouteParseReport()

        if not raw_text or not raw_text.strip():
            report.status = "EMPTY"
            report.elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return [], report

        lower = raw_text.lower()
        if any(err in lower for err in ("bad command name", "no such item", "syntax error")):
            report.status = "ERROR"
            report.warning = "RouterOS CLI error detected in command output."
            report.elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return [], report

        # Auto-detect RouterOS version if not specified
        detected_version = ros_version
        if detected_version is None:
            if "columns:" in lower or "immediate-gw" in lower or "suppress-hw-offload" in lower:
                detected_version = 7
            elif "gateway-status" in lower:
                detected_version = 6

        # Check format: Detail format has 'dst-address='
        is_detail = "dst-address=" in raw_text

        if is_detail:
            folded_blocks = self._fold_continuation_lines(raw_text)
            routes = self._parse_detail_blocks(folded_blocks, device_id=device_id, ros_version=detected_version)
        else:
            routes = self._parse_tabular_lines(raw_text.splitlines(), device_id=device_id, ros_version=detected_version)

        # Enforce bounded resource thresholds (Decision 9)
        total_count = len(routes)
        if total_count > self.MAX_WARNING_ROUTES:
            report.status = "LIMIT_EXCEEDED"
            report.warning = (
                f"Route table size ({total_count}) exceeds hard threshold of {self.MAX_WARNING_ROUTES}. "
                "Table truncated to preserve system stability (Tier 3 policy)."
            )
            report.is_partial = True
            routes = routes[:self.MAX_WARNING_ROUTES]
        elif total_count > self.MAX_NORMAL_ROUTES:
            report.status = "WARNING_LARGE_TABLE"
            report.warning = (
                f"Route table size ({total_count}) exceeds standard threshold of {self.MAX_NORMAL_ROUTES}. "
                "Bounded analysis engaged (Tier 2 policy)."
            )

        report.total_parsed = len(routes)
        report.active_count = sum(1 for r in routes if r.active)
        report.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return routes, report

    # -----------------------------------------------------------------------
    # Line Folding (D4 remediation)
    # -----------------------------------------------------------------------

    def _fold_continuation_lines(self, raw_text: str) -> List[str]:
        """
        Folds multi-line RouterOS detail outputs into single logical route records.
        Lines beginning with whitespace (continuation lines) are merged into the
        previous record. Resolves Defect D4.
        """
        blocks: List[str] = []
        current: List[str] = []

        for line in raw_text.splitlines():
            s = line.rstrip()
            if not s:
                continue
            s_strip = s.strip()
            if s_strip.startswith("Flags:") or s_strip.startswith("Columns:"):
                continue

            # Record header check: starts with optional spaces + digits + spaces,
            # OR unnumbered RouterOS v7 dynamic detail header (e.g. "   DAc   dst-address=...")
            if re.match(r"^\s*\d+\s+", s) or re.match(r"^\s*[A-Za-z+]+\s+dst-address=", s):
                if current:
                    blocks.append(" ".join(current))
                current = [s_strip]
            elif current:
                # Indented continuation line
                current.append(s_strip)

        if current:
            blocks.append(" ".join(current))

        return blocks

    # -----------------------------------------------------------------------
    # Detail Record Parsing (D3, D4, D5, D7, D8, D9, D10 remediation)
    # -----------------------------------------------------------------------

    def _parse_detail_blocks(
        self,
        blocks: List[str],
        device_id: str,
        ros_version: Optional[int],
    ) -> List[NormalizedRoute]:
        parsed: List[NormalizedRoute] = []

        for blk in blocks:
            # 1. Extract record index and header flags (D3, plus unnumbered ROS v7 dynamic detail blocks)
            m_head = re.match(r"^\s*(?:(\d+)\s+)?([A-Za-z+\s]+?)\s+(?=[a-zA-Z0-9_\-]+=\S+)(.*)$", blk)
            flags = ""
            body = blk
            if m_head:
                flags = m_head.group(2).strip()
                body = m_head.group(3).strip()
            else:
                m_num = re.match(r"^\s*(\d+)\s+(.*)$", blk)
                if m_num:
                    body = m_num.group(2).strip()

            # 2. Extract Key-Value pairs
            kvs: Dict[str, str] = {}
            for m in self._KV_RE.finditer(body):
                key = m.group(1)
                val = m.group(2).strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                kvs[key] = val or ""

            if not kvs:
                continue

            # 3. Destination Prefix (D10)
            raw_dst = kvs.get("dst-address", "0.0.0.0/0")
            canonical_dst = _canonicalize_prefix(raw_dst)

            # 4. Gateway and ECMP (D7)
            raw_gw = kvs.get("gateway", "")
            gateways = [g.strip() for g in raw_gw.split(",") if g.strip()] if raw_gw else []
            primary_gw = gateways[0] if gateways else ""

            # 5. Immediate Gateway, Gateway-Status, and Interface (D5)
            gw_status = kvs.get("gateway-status", "")
            immediate_gw = kvs.get("immediate-gw", "")
            egress_iface = kvs.get("interface", "")

            # Parse gateway status details
            if immediate_gw:
                # v7 format: immediate-gw=10.66.38.1%ether1
                if "%" in immediate_gw:
                    parts = immediate_gw.split("%", 1)
                    if not egress_iface:
                        egress_iface = parts[1].strip()
                elif not egress_iface and not _extract_ipv4(immediate_gw):
                    egress_iface = immediate_gw.strip()

            if gw_status:
                # v6 format: gateway-status=192.168.10.1 recursive via 10.0.0.1 ether1
                m_rec = re.search(r"recursive\s+via\s+([0-9\.]+)\s+([a-zA-Z0-9_\.\-]+)", gw_status)
                if m_rec:
                    if not immediate_gw:
                        immediate_gw = m_rec.group(1)
                    if not egress_iface:
                        egress_iface = m_rec.group(2)
                else:
                    m_reach = re.search(r"([0-9\.]+)\s+reachable\s+via\s+([a-zA-Z0-9_\.\-]+)", gw_status)
                    if m_reach:
                        if not immediate_gw:
                            immediate_gw = m_reach.group(1)
                        if not egress_iface:
                            egress_iface = m_reach.group(2)
                    else:
                        m_reach_simple = re.search(r"reachable\s+via\s+([a-zA-Z0-9_\.\-]+)", gw_status)
                        if m_reach_simple and not egress_iface:
                            egress_iface = m_reach_simple.group(1)
                        if not immediate_gw and _extract_ipv4(primary_gw):
                            immediate_gw = primary_gw

            # If gateway is an interface name itself (connected route)
            if not egress_iface and primary_gw and not _extract_ipv4(primary_gw):
                egress_iface = primary_gw

            # 6. Flag evaluation (D2, D3, D6)
            is_disabled = (
                "X" in flags or "disabled" in flags.lower()
                or kvs.get("disabled") == "yes"
            )
            is_dynamic = (
                "D" in flags or "dynamic" in flags.lower()
                or kvs.get("dynamic") == "yes"
            )
            is_inactive = (
                "I" in flags or "inactive" in flags.lower()
                or kvs.get("active") == "no"
                or is_disabled
            )

            # In v7, 'A' explicitly marks active; in v6, absence of 'X' on static route is active
            has_active_flag = "A" in flags or kvs.get("active") == "yes"
            is_active = (
                not is_inactive
                and not is_disabled
                and (has_active_flag or (not flags and kvs.get("active") != "no"))
            )

            # 7. Protocol classification (D2)
            flags_lower = flags.lower()
            protocol = RouteProtocol.STATIC.value
            is_connect = False
            is_static = False
            is_ospf = False
            is_bgp = False
            is_rip = False

            if "c" in flags_lower or kvs.get("connect") == "yes" or "connect" in flags_lower:
                protocol = RouteProtocol.CONNECTED.value
                is_connect = True
            elif "o" in flags_lower or kvs.get("ospf") == "yes" or "ospf" in flags_lower:
                protocol = RouteProtocol.OSPF.value
                is_ospf = True
            elif "b" in flags_lower or kvs.get("bgp") == "yes" or "bgp" in flags_lower:
                protocol = RouteProtocol.BGP.value
                is_bgp = True
            elif "r" in flags_lower or kvs.get("rip") == "yes" or "rip" in flags_lower:
                protocol = RouteProtocol.RIP.value
                is_rip = True
            else:
                protocol = RouteProtocol.STATIC.value
                is_static = True

            # 8. Distance and Metrics
            raw_dist = kvs.get("distance")
            if raw_dist and raw_dist.isdigit():
                distance = int(raw_dist)
            elif is_connect:
                distance = 0
            else:
                distance = 1

            raw_metric = kvs.get("metric") or kvs.get("ospf-metric")
            metric = int(raw_metric) if (raw_metric and raw_metric.isdigit()) else None

            # 9. Scopes (D8)
            scope = int(kvs["scope"]) if (kvs.get("scope") and kvs["scope"].isdigit()) else None
            target_scope = int(kvs["target-scope"]) if (kvs.get("target-scope") and kvs["target-scope"].isdigit()) else None

            # 10. Routing Table / VRF (D9)
            routing_table = kvs.get("routing-table") or kvs.get("routing-mark") or "main"

            route = NormalizedRoute(
                dst_prefix=canonical_dst,
                gateway=primary_gw,
                device_id=device_id,
                interface_name=egress_iface,
                routing_table=routing_table,
                gateways=gateways,
                immediate_gw=immediate_gw or None,
                pref_src=kvs.get("pref-src"),
                protocol=protocol,
                distance=distance,
                metric=metric,
                scope=scope,
                target_scope=target_scope,
                active=is_active,
                disabled=is_disabled,
                dynamic=is_dynamic,
                connect=is_connect,
                static=is_static,
                ospf=is_ospf,
                bgp=is_bgp,
                rip=is_rip,
                source_ros_version=ros_version,
                raw_flags=flags,
                raw_attributes=dict(kvs),
            )
            parsed.append(route)

        return parsed

    # -----------------------------------------------------------------------
    # Columnar / Tabular Record Parsing (D1, D2, D10 remediation)
    # -----------------------------------------------------------------------

    def _parse_tabular_lines(
        self,
        lines: List[str],
        device_id: str,
        ros_version: Optional[int],
    ) -> List[NormalizedRoute]:
        parsed: List[NormalizedRoute] = []

        for line in lines:
            line_s = line.rstrip()
            if not line_s:
                continue
            s_clean = line_s.strip()
            if s_clean.startswith("Flags:") or s_clean.startswith("Columns:") or s_clean.startswith("#"):
                continue

            # Robust columnar regex capturing index, spaced flags, and destination CIDR (D1)
            m = self._TAB_LINE_RE.match(line_s)
            if not m:
                continue

            idx_str, flags_raw, raw_dst, rest = m.groups()
            flags = flags_raw.strip()
            tokens = rest.split()
            if not tokens:
                continue

            canonical_dst = _canonicalize_prefix(raw_dst)

            # Analyze tokens:
            # v6 tabular: [PREF-SRC], GATEWAY, DISTANCE
            # v7 tabular: GATEWAY, DISTANCE
            pref_src: Optional[str] = None
            primary_gw: str = ""
            distance: int = 1

            if len(tokens) >= 3:
                # E.g. [192.168.88.1, ether2, 0]
                if _extract_ipv4(tokens[0]):
                    pref_src = tokens[0]
                    primary_gw = tokens[1]
                    if tokens[2].isdigit():
                        distance = int(tokens[2])
                else:
                    primary_gw = tokens[0]
                    if tokens[-1].isdigit():
                        distance = int(tokens[-1])
            elif len(tokens) == 2:
                # E.g. [192.168.1.1, 1] or [ether2, 0]
                primary_gw = tokens[0]
                if tokens[1].isdigit():
                    distance = int(tokens[1])
            elif len(tokens) == 1:
                primary_gw = tokens[0]

            # Flag normalization (D2)
            flags_lower = flags.lower()
            is_disabled = "x" in flags_lower
            is_dynamic = "d" in flags_lower
            is_inactive = "i" in flags_lower or is_disabled
            has_active_flag = "a" in flags_lower

            is_active = not is_inactive and not is_disabled and (has_active_flag or not flags)

            is_connect = "c" in flags_lower
            is_static = "s" in flags_lower
            is_ospf = "o" in flags_lower
            is_bgp = "b" in flags_lower
            is_rip = "r" in flags_lower

            if is_connect:
                protocol = RouteProtocol.CONNECTED.value
                if distance == 1:
                    distance = 0
            elif is_ospf:
                protocol = RouteProtocol.OSPF.value
            elif is_bgp:
                protocol = RouteProtocol.BGP.value
            elif is_rip:
                protocol = RouteProtocol.RIP.value
            else:
                protocol = RouteProtocol.STATIC.value
                is_static = True

            egress_iface = primary_gw if is_connect and not _extract_ipv4(primary_gw) else None

            route = NormalizedRoute(
                dst_prefix=canonical_dst,
                gateway=primary_gw,
                device_id=device_id,
                interface_name=egress_iface,
                routing_table="main",
                gateways=[primary_gw] if primary_gw else [],
                pref_src=pref_src,
                protocol=protocol,
                distance=distance,
                active=is_active,
                disabled=is_disabled,
                dynamic=is_dynamic,
                connect=is_connect,
                static=is_static,
                ospf=is_ospf,
                bgp=is_bgp,
                rip=is_rip,
                source_ros_version=ros_version,
                raw_flags=flags,
                raw_attributes={"_raw": line_s},
            )
            parsed.append(route)

        return parsed


# ---------------------------------------------------------------------------
# Routing Intelligence: Longest Prefix Match (D6 remediation)
# ---------------------------------------------------------------------------

def evaluate_longest_prefix_match(
    routes: List[Any],
    target_ip: str,
    require_active: bool = True,
    routing_table: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates Longest Prefix Match (LPM) for destination IPv4 forwarding.
    Resolves Defect D6: Inactive or disabled routes are filtered out of forwarding decisions.
    Respects routing table / VRF context when specified.
    """
    clean_ip = _extract_ipv4(target_ip)
    if not clean_ip:
        return {
            "matched": False,
            "error": f"Invalid target IPv4 address: '{target_ip}'",
            "matching_routes_count": 0,
            "best_route": None,
        }

    try:
        addr = ipaddress.ip_address(clean_ip)
    except ValueError as exc:
        return {
            "matched": False,
            "error": str(exc),
            "matching_routes_count": 0,
            "best_route": None,
        }

    # Normalize candidate routes into objects supporting dst_prefix and active
    matching_routes: List[Tuple[Any, int]] = []

    for r in routes:
        if routing_table is not None:
            r_table = getattr(r, "routing_table", None)
            if r_table is None and isinstance(r, dict):
                r_table = r.get("routing_table") or r.get("routing_mark") or "main"
            if (r_table or "main") != routing_table:
                continue

        net = getattr(r, "network", None)
        if net is None:
            raw_dst = getattr(r, "dst_prefix", None) or getattr(r, "dst_address", None)
            if raw_dst:
                try:
                    net = ipaddress.ip_network(_canonicalize_prefix(raw_dst), strict=False)
                except Exception:
                    net = None

        if net and addr in net:
            plen = net.prefixlen
            matching_routes.append((r, plen))

    if not matching_routes:
        return {
            "matched": False,
            "target_ip": clean_ip,
            "matching_routes_count": 0,
            "best_route": None,
            "reason": "No route matches this destination IP (unreachable destination, missing default route).",
            "all_matches": [],
            "observed_facts": [f"Tidak ditemukan rute yang mencakup target IP {clean_ip}."],
            "inferred_hypotheses": ["Destinasi tidak dapat dijangkau dari perangkat ini."],
            "missing_evidence": ["Default route (0.0.0.0/0) tidak terpasang di routing table."],
            "recommendations": ["Tambahkan default route (0.0.0.0/0) atau static route spesifik untuk subnet destinasi."],
        }

    # Format all matched routes for diagnostics
    all_matches = []
    for r, plen in matching_routes:
        dst = getattr(r, "dst_prefix", None) or getattr(r, "dst_address", "0.0.0.0/0")
        gw = getattr(r, "gateway", "")
        dist = getattr(r, "distance", 1)
        act = getattr(r, "active", True)
        flags = getattr(r, "raw_flags", "")
        all_matches.append({
            "dst_address": dst,
            "gateway": gw,
            "prefix_len": plen,
            "distance": dist,
            "active": act,
            "flags": flags,
            "is_default_route": dst in ("0.0.0.0/0", "::/0"),
        })

    # D6 Remediation: Filter eligible forwarding candidates (must be active and not disabled)
    eligible_candidates: List[Tuple[Any, int]] = []
    for r, plen in matching_routes:
        is_active = getattr(r, "active", True)
        is_disabled = getattr(r, "disabled", False)
        is_unreachable = getattr(r, "unreachable", False)
        if not require_active or (is_active and not is_disabled and not is_unreachable):
            eligible_candidates.append((r, plen))

    if not eligible_candidates:
        return {
            "matched": False,
            "target_ip": clean_ip,
            "matching_routes_count": len(matching_routes),
            "eligible_routes_count": 0,
            "best_route": None,
            "reason": (
                f"Matching routes found for {clean_ip}, but none are active in the Forwarding "
                "Information Base (all candidates are INACTIVE, DISABLED, or UNREACHABLE)."
            ),
            "all_matches": all_matches,
            "observed_facts": [
                f"Ditemukan {len(matching_routes)} rute yang mencakup target IP {clean_ip}, "
                "namun SELURUHNYA berstatus INACTIVE/DISABLED di FIB."
            ],
            "inferred_hypotheses": [
                "Trafik akan di-drop karena tidak ada rute aktif yang memenuhi syarat forwarding."
            ],
            "missing_evidence": [
                "Periksa status link interface gateway atau keterjangkauan recursive next-hop."
            ],
            "recommendations": [
                "Aktifkan interface uplink atau periksa konfigurasi check-gateway pada rute statis terkait."
            ],
            "limits_disclosure": "LPM mengevaluasi tabel rute 'main' standar untuk status forwarding aktif (FIB).",
        }

    # Sort eligible routes:
    # 1. Longest prefix length (most specific)
    # 2. Lowest administrative distance
    # 3. Connected route preference
    def eligible_sort_key(item: Tuple[Any, int]):
        r, plen = item
        dist = getattr(r, "distance", 1)
        is_conn = 1 if getattr(r, "connect", False) else 0
        return (plen, -dist, is_conn)

    eligible_candidates.sort(key=eligible_sort_key, reverse=True)
    best_route, best_plen = eligible_candidates[0]

    # Audit ECMP (D7)
    best_dst = getattr(best_route, "dst_prefix", None) or getattr(best_route, "dst_address", "")
    best_dist = getattr(best_route, "distance", 1)

    ecmp_gateways: List[str] = []
    if getattr(best_route, "gateways", None) and len(best_route.gateways) > 1:
        ecmp_gateways = list(best_route.gateways)
    elif "," in getattr(best_route, "gateway", ""):
        ecmp_gateways = [g.strip() for g in best_route.gateway.split(",") if g.strip()]
    else:
        same_cost = [
            r for r, plen in eligible_candidates
            if (getattr(r, "dst_prefix", None) or getattr(r, "dst_address", "")) == best_dst
            and getattr(r, "distance", 1) == best_dist
            and getattr(r, "gateway", "") != getattr(best_route, "gateway", "")
        ]
        if same_cost:
            ecmp_gateways = [getattr(best_route, "gateway", "")] + [getattr(r, "gateway", "") for r in same_cost]

    is_ecmp = len(ecmp_gateways) > 1
    best_gw = getattr(best_route, "gateway", "")
    is_iface_gw = bool(best_gw and not _extract_ipv4(best_gw))

    # Evaluate recursive candidate indicator (D5)
    recursive_candidate = False
    if best_gw and not is_iface_gw and best_dst not in ("0.0.0.0/0", "::/0"):
        gw_ip = _extract_ipv4(best_gw)
        if gw_ip:
            try:
                gw_addr = ipaddress.ip_address(gw_ip)
                for r in routes:
                    r_dst = getattr(r, "dst_prefix", None) or getattr(r, "dst_address", "")
                    if r_dst not in ("0.0.0.0/0", "::/0", best_dst):
                        try:
                            r_net = ipaddress.ip_network(_canonicalize_prefix(r_dst), strict=False)
                            if gw_addr in r_net:
                                recursive_candidate = True
                                break
                        except Exception:
                            pass
            except Exception:
                pass

    observed_facts = [
        f"Ditemukan {len(matching_routes)} rute yang mencakup target IP {clean_ip} ({len(eligible_candidates)} aktif).",
        f"Rute terseleksi di FIB: dst={best_dst} via {best_gw} (prefix_len=/{best_plen}, distance={best_dist}, active=True).",
    ]
    if is_ecmp:
        observed_facts.append(f"Rute menggunakan ECMP multi-gateway: {', '.join(ecmp_gateways)}.")

    inferred_hypotheses = [
        f"LPM memilih rute aktif prefix terpanjang (/{best_plen}) dengan distance terendah ({best_dist})."
    ]
    if recursive_candidate:
        inferred_hypotheses.append("Next-hop gateway memerlukan resolusi rekursif (bukan directly connected IP).")

    return {
        "matched": True,
        "target_ip": clean_ip,
        "matching_routes_count": len(matching_routes),
        "eligible_routes_count": len(eligible_candidates),
        "is_ecmp": is_ecmp,
        "ecmp_gateways": ecmp_gateways,
        "recursive_gateway_candidate": recursive_candidate,
        "best_route": {
            "dst_address": best_dst,
            "gateway": best_gw,
            "prefix_len": best_plen,
            "distance": best_dist,
            "active": True,
            "flags": getattr(best_route, "raw_flags", ""),
            "is_default_route": best_dst in ("0.0.0.0/0", "::/0"),
            "is_ecmp": is_ecmp,
            "is_interface_gateway": is_iface_gw,
        },
        "all_matches": all_matches,
        "is_default_route_match": best_dst in ("0.0.0.0/0", "::/0"),
        "observed_facts": observed_facts,
        "inferred_hypotheses": inferred_hypotheses,
        "missing_evidence": [
            "Policy routing rules (/ip route rule atau /routing rule) belum dievaluasi.",
            "Routing mark / mangle table rules belum dievaluasi.",
        ],
        "recommendations": [],
        "limits_disclosure": (
            "LPM mengevaluasi tabel rute 'main' standar. Forwarding aktual pada RouterOS dapat "
            "berbeda jika terdapat routing-mark (mangle), policy rules (/ip route rule), "
            "atau VRF terisolasi."
        ),
    }


# ---------------------------------------------------------------------------
# Routing Intelligence: Recursive Next-Hop Resolution (D3, D5)
# ---------------------------------------------------------------------------

def resolve_recursive_next_hop(
    target_gateway: str,
    candidate_routes: List[NormalizedRoute],
    max_depth: int = 16,
) -> NextHopResolution:
    """
    Recursively resolves an IP gateway against candidate routes to find
    the egress interface and directly-connected next hop.
    Prevents infinite recursion and detects routing loops.
    """
    clean_gw = _extract_ipv4(target_gateway)
    if not clean_gw:
        # Gateway is an interface name directly
        return NextHopResolution(
            status=NextHopResolutionStatus.DIRECTLY_CONNECTED,
            target_gateway=target_gateway,
            resolved_ip=None,
            egress_interface=target_gateway.strip(),
            depth=0,
            resolution_chain=[target_gateway.strip()],
            confidence=1.0,
            reason="Gateway is directly specified as an interface.",
        )

    visited_ips: Set[str] = set()
    current_gw = clean_gw
    chain: List[str] = [current_gw]
    depth = 0

    while depth < max_depth:
        depth += 1
        visited_ips.add(current_gw)

        # Find LPM for current_gw among active routes, ignoring default route for direct resolution
        lpm = evaluate_longest_prefix_match(candidate_routes, current_gw, require_active=True)
        if not lpm.get("matched") or not lpm.get("best_route"):
            return NextHopResolution(
                status=NextHopResolutionStatus.UNRESOLVED,
                target_gateway=target_gateway,
                resolved_ip=current_gw,
                depth=depth,
                resolution_chain=chain,
                confidence=0.0,
                reason=f"No active route found to resolve gateway IP {current_gw}.",
            )

        match_route = lpm["best_route"]
        matched_dst = match_route["dst_address"]
        matched_gw = match_route["gateway"]

        # Rule: A gateway reachable only through default route (0.0.0.0/0) is NOT directly connected
        if matched_dst in ("0.0.0.0/0", "::/0"):
            return NextHopResolution(
                status=NextHopResolutionStatus.UNRESOLVED,
                target_gateway=target_gateway,
                resolved_ip=current_gw,
                depth=depth,
                resolution_chain=chain + ["0.0.0.0/0 (default route cannot resolve recursive gateway)"],
                confidence=0.2,
                reason=f"Gateway {target_gateway} falls back to default route; cannot confirm reachability.",
            )

        chain.append(f"{matched_dst} via {matched_gw}")

        # Check if matched route is directly connected (gateway is an interface)
        if match_route.get("is_interface_gateway") or not _extract_ipv4(matched_gw):
            return NextHopResolution(
                status=NextHopResolutionStatus.RECURSIVE_RESOLVED if depth > 1 else NextHopResolutionStatus.DIRECTLY_CONNECTED,
                target_gateway=target_gateway,
                resolved_ip=current_gw,
                egress_interface=matched_gw,
                depth=depth,
                resolution_chain=chain,
                confidence=1.0 if depth == 1 else 0.9,
                reason=f"Resolved to egress interface {matched_gw} at depth {depth}.",
            )

        # Otherwise next hop is another IP -> continue recursion
        next_ip = _extract_ipv4(matched_gw)
        if not next_ip:
            break

        if next_ip in visited_ips:
            # Routing loop detected!
            return NextHopResolution(
                status=NextHopResolutionStatus.UNREACHABLE,
                target_gateway=target_gateway,
                resolved_ip=next_ip,
                depth=depth,
                resolution_chain=chain + [f"LOOP: {next_ip}"],
                loop_detected=True,
                confidence=0.0,
                reason=f"Recursive routing loop detected for gateway {target_gateway} at {next_ip}.",
            )

        current_gw = next_ip

    return NextHopResolution(
        status=NextHopResolutionStatus.UNRESOLVED,
        target_gateway=target_gateway,
        depth=depth,
        resolution_chain=chain,
        confidence=0.0,
        reason=f"Recursion depth exceeded maximum limit ({max_depth}).",
    )


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

_IPV4_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")


def _canonicalize_prefix(prefix_or_ip: str) -> str:
    """Normalizes bare IP addresses and subnets into canonical CIDR strings (D10)."""
    p = prefix_or_ip.strip()
    if not p:
        return "0.0.0.0/0"
    slash = p.find("/")
    if slash != -1:
        return p
    # Bare IP without mask -> append /32 (D10)
    parts = p.split(".")
    if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        return f"{p}/32"
    return p


def _extract_ipv4(text: str) -> Optional[str]:
    """Extracts first valid IPv4 address from text, or returns None."""
    if not text:
        return None
    m = _IPV4_RE.search(text)
    if m:
        candidate = m.group(1)
        parts = candidate.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return candidate
    return None
