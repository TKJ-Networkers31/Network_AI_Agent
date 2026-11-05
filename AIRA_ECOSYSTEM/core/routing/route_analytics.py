"""
AIRA OS — Route Analytics & Network Path Evaluation Engine (Networking IV / WP 4.6.2).

Extends WP 4.6.0's authoritative UnifiedRouteParser, evaluate_longest_prefix_match, and
resolve_recursive_next_hop with:
1. Five-tier forwarding epistemology LPM lookup (RIB matches -> Eligible -> Calculated best
   -> Verified FIB -> Observed packet path), VRF isolation, ECMP, and metric tie-breaking.
2. Multi-dimensional RouteTableAnalyzer detecting 12 classes of single- and cross-device
   routing anomalies with explicit evidence IDs, confidence, and limitations.
3. Multi-hop RoutePathEvaluator reconstructing inferred/confirmed/partial/ambiguous paths
   across routers while preserving ECMP branches, detecting loops and missing intermediate
   routers, and never inventing unknown devices.
"""

from __future__ import annotations

import ipaddress
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from core.network_intelligence.models import EvidenceFreshness
from core.routing.route_collector import RouteCollectionResult, RouteCompleteness
from core.routing.unified_route_parser import (
    NextHopResolution,
    NextHopResolutionStatus,
    NormalizedRoute,
    RouteType,
    _canonicalize_prefix,
    _extract_ipv4,
    evaluate_longest_prefix_match,
    resolve_recursive_next_hop,
)


class PathResultState(str, Enum):
    PATH_CONFIRMED_BY_EVIDENCE = "PATH_CONFIRMED_BY_EVIDENCE"
    PATH_INFERRED = "PATH_INFERRED"
    PATH_PARTIAL = "PATH_PARTIAL"
    PATH_AMBIGUOUS = "PATH_AMBIGUOUS"
    PATH_UNRESOLVED = "PATH_UNRESOLVED"
    PATH_UNREACHABLE = "PATH_UNREACHABLE"
    PATH_NOT_ENOUGH_EVIDENCE = "PATH_NOT_ENOUGH_EVIDENCE"


class RouteFindingType(str, Enum):
    MISSING_DESTINATION_ROUTE = "MISSING_DESTINATION_ROUTE"
    MISSING_DEFAULT_ROUTE = "MISSING_DEFAULT_ROUTE"
    UNEXPECTED_DEFAULT_ROUTE = "UNEXPECTED_DEFAULT_ROUTE"
    OVERLAPPING_PREFIXES = "OVERLAPPING_PREFIXES"
    DUPLICATE_ROUTE_CANDIDATES = "DUPLICATE_ROUTE_CANDIDATES"
    CONFLICTING_ROUTE_ADVERTISEMENTS = "CONFLICTING_ROUTE_ADVERTISEMENTS"
    UNREACHABLE_NEXT_HOP = "UNREACHABLE_NEXT_HOP"
    RECURSIVE_GATEWAY_DEPENDENCY = "RECURSIVE_GATEWAY_DEPENDENCY"
    UNEXPECTED_ROUTING_TABLE_ASSIGNMENT = "UNEXPECTED_ROUTING_TABLE_ASSIGNMENT"
    ASYMMETRIC_ROUTE_HYPOTHESIS = "ASYMMETRIC_ROUTE_HYPOTHESIS"
    ECMP_CONFIGURATION = "ECMP_CONFIGURATION"
    INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES = "INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES"


DEFAULT_ANALYSIS_LIMITATIONS = [
    "Calculated route selection is derived from control-plane RIB output and is not proof of hardware/kernel FIB installation.",
    "Standard LPM evaluation does not dynamically simulate firewall mangle routing-marks, FastTrack offload, or policy routing rules (/ip route rule, /routing rule).",
    "Inferred routing paths represent control-plane forwarding intent, not observed data-plane packet telemetry.",
]


@dataclass
class RouteFinding:
    """
    Structured routing anomaly or operational observation backed by explicit evidence IDs.
    """
    finding_type: str
    device_id: str
    routing_table: str
    dst_prefix: str
    gateway: str
    evidence_ids: List[str]
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    confidence: str  # CONFIRMED, HIGH, MEDIUM, LOW, HYPOTHESIS
    explanation: str
    limitations: List[str] = field(default_factory=lambda: list(DEFAULT_ANALYSIS_LIMITATIONS))
    finding_id: str = field(default_factory=lambda: f"rfind_{uuid.uuid4().hex[:10]}")
    related_device_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "finding_type": self.finding_type,
            "device_id": self.device_id,
            "related_device_id": self.related_device_id,
            "routing_table": self.routing_table,
            "dst_prefix": self.dst_prefix,
            "gateway": self.gateway,
            "evidence_ids": list(self.evidence_ids),
            "severity": self.severity,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


@dataclass
class LPMEvaluationResult:
    """
    Extended LPM evaluation result strictly separating:
    1. matching_rib_routes
    2. eligible_route_candidates
    3. calculated_best_candidates (RIB calculation — never labeled confirmed FIB)
    4. verified_forwarding_info (only when explicit FIB flag/evidence exists)
    5. observed_traffic_path (only when live packet/traceroute telemetry exists)
    """
    device_id: str
    destination_query: str
    lookup_ip: str
    routing_table: str
    matched: bool
    ambiguous_selection: bool
    is_ecmp: bool
    ecmp_gateways: List[str]
    missing_evidence: bool
    matching_rib_routes: List[Dict[str, Any]]
    eligible_route_candidates: List[Dict[str, Any]]
    calculated_best_candidates: List[Dict[str, Any]]
    verified_forwarding_info: Dict[str, Any]
    observed_traffic_path: Dict[str, Any]
    recursive_resolution: Optional[Dict[str, Any]] = None
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=lambda: list(DEFAULT_ANALYSIS_LIMITATIONS))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "destination_query": self.destination_query,
            "lookup_ip": self.lookup_ip,
            "routing_table": self.routing_table,
            "matched": self.matched,
            "ambiguous_selection": self.ambiguous_selection,
            "is_ecmp": self.is_ecmp,
            "ecmp_gateways": list(self.ecmp_gateways),
            "missing_evidence": self.missing_evidence,
            "matching_rib_routes": list(self.matching_rib_routes),
            "eligible_route_candidates": list(self.eligible_route_candidates),
            "calculated_best_candidates": list(self.calculated_best_candidates),
            "verified_forwarding_info": dict(self.verified_forwarding_info),
            "observed_traffic_path": dict(self.observed_traffic_path),
            "recursive_resolution": self.recursive_resolution,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass
class RoutePathHop:
    hop_index: int
    device_id: str
    routing_table: str
    matched_prefix: Optional[str] = None
    gateway: Optional[str] = None
    immediate_gateway: Optional[str] = None
    resolved_gateway_ip: Optional[str] = None
    egress_interface: Optional[str] = None
    protocol: Optional[str] = None
    distance: Optional[int] = None
    next_device_id: Optional[str] = None
    hop_state: str = "RESOLVED"  # DIRECT_CONNECTED, NEXT_HOP_RESOLVED, RECURSIVE_RESOLVED, EXTERNAL_OR_MISSING_ROUTER, UNRESOLVED_GATEWAY, NO_ROUTE, NULL_ROUTE, LOOP_DETECTED, AMBIGUOUS_NEXT_HOP, INCOMPLETE_EVIDENCE
    is_recursive: bool = False
    recursion_chain: List[str] = field(default_factory=list)
    is_ecmp_branch: bool = False
    evidence_ids: List[str] = field(default_factory=list)
    freshness: str = EvidenceFreshness.FRESH.value
    completeness: str = RouteCompleteness.COMPLETE.value
    topology_verified: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hop_index": self.hop_index,
            "device_id": self.device_id,
            "routing_table": self.routing_table,
            "matched_prefix": self.matched_prefix,
            "gateway": self.gateway,
            "immediate_gateway": self.immediate_gateway,
            "resolved_gateway_ip": self.resolved_gateway_ip,
            "egress_interface": self.egress_interface,
            "protocol": self.protocol,
            "distance": self.distance,
            "next_device_id": self.next_device_id,
            "hop_state": self.hop_state,
            "is_recursive": self.is_recursive,
            "recursion_chain": list(self.recursion_chain),
            "is_ecmp_branch": self.is_ecmp_branch,
            "evidence_ids": list(self.evidence_ids),
            "freshness": self.freshness,
            "completeness": self.completeness,
            "topology_verified": self.topology_verified,
            "notes": list(self.notes),
        }


@dataclass
class RoutePathEvaluationResult:
    source_device_id: str
    destination: str
    routing_table: str
    state: str  # PathResultState value
    confidence: float
    primary_hops: List[RoutePathHop] = field(default_factory=list)
    ecmp_branches: List[List[RoutePathHop]] = field(default_factory=list)
    loop_detected: bool = False
    is_ecmp: bool = False
    stale_evidence_detected: bool = False
    incomplete_evidence_detected: bool = False
    contradictions: List[str] = field(default_factory=list)
    missing_intermediate_gateways: List[str] = field(default_factory=list)
    ambiguous_gateways: List[str] = field(default_factory=list)
    return_path_hypothesis: Optional[Dict[str, Any]] = None
    evidence_ids: List[str] = field(default_factory=list)
    explanation: str = ""
    limitations: List[str] = field(default_factory=lambda: list(DEFAULT_ANALYSIS_LIMITATIONS))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_device_id": self.source_device_id,
            "destination": self.destination,
            "routing_table": self.routing_table,
            "state": self.state,
            "confidence": round(self.confidence, 3),
            "loop_detected": self.loop_detected,
            "is_ecmp": self.is_ecmp,
            "stale_evidence_detected": self.stale_evidence_detected,
            "incomplete_evidence_detected": self.incomplete_evidence_detected,
            "primary_hops": [h.to_dict() for h in self.primary_hops],
            "ecmp_branches": [[h.to_dict() for h in br] for br in self.ecmp_branches],
            "contradictions": list(self.contradictions),
            "missing_intermediate_gateways": list(self.missing_intermediate_gateways),
            "ambiguous_gateways": list(self.ambiguous_gateways),
            "return_path_hypothesis": self.return_path_hypothesis,
            "evidence_ids": list(self.evidence_ids),
            "explanation": self.explanation,
            "limitations": list(self.limitations),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_destination_target(destination: str) -> Tuple[Optional[ipaddress.IPv4Address], Optional[ipaddress.IPv4Network]]:
    """
    Parses a destination query (either a host IP like '10.10.10.5' or a CIDR prefix like '10.10.10.0/24')
    into (representative_lookup_ip, target_network_or_none).
    """
    raw = (destination or "").strip()
    if not raw:
        return None, None
    if "/" in raw:
        try:
            net = ipaddress.ip_network(raw, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                if net.prefixlen == 0:
                    return ipaddress.IPv4Address("0.0.0.0"), net
                if net.prefixlen < 31:
                    rep = ipaddress.IPv4Address(int(net.network_address) + 1)
                else:
                    rep = net.network_address
                return rep, net
        except Exception:
            return None, None
    else:
        try:
            ip_obj = ipaddress.ip_address(raw)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                return ip_obj, None
        except Exception:
            return None, None
    return None, None


def _route_evidence_id(route: NormalizedRoute, fallback: str = "") -> str:
    prov = route.evidence_provenance or {}
    return str(prov.get("evidence_id") or fallback or "ev_unknown")


def _is_route_eligible_unicast(r: NormalizedRoute) -> bool:
    rtype = r.route_type.value if hasattr(r.route_type, "value") else str(r.route_type)
    return (
        bool(r.active)
        and not bool(r.disabled)
        and not bool(r.unreachable)
        and rtype == RouteType.UNICAST.value
    )


def _has_verified_fib_marker(r: NormalizedRoute) -> bool:
    if r.selected is True:
        return True
    flags = (r.raw_flags or "")
    # RouterOS v7 uses 'H' for hardware-offloaded FIB or explicit fib attribute in raw_attributes
    if "H" in flags:
        return True
    if str(r.raw_attributes.get("fib", "")).lower() in ("true", "yes", "1"):
        return True
    return False


# ---------------------------------------------------------------------------
# 6.1 Extended Longest Prefix Match Engine
# ---------------------------------------------------------------------------

def evaluate_route_lookup(
    routes: Sequence[NormalizedRoute],
    destination: str,
    *,
    device_id: str = "",
    routing_table: str = "main",
    completeness: str = RouteCompleteness.COMPLETE.value,
    observed_hops: Optional[List[str]] = None,
) -> LPMEvaluationResult:
    """
    Evaluates destination routing lookup by extending WP 4.6.0's evaluate_longest_prefix_match.
    Strictly separates RIB matches, eligible candidates, calculated LPM winners, verified FIB
    forwarding state, and observed packet paths.
    """
    target_table = (routing_table or "main").strip()
    warnings: List[str] = []

    lookup_ip_obj, target_net = _parse_destination_target(destination)
    if lookup_ip_obj is None:
        return LPMEvaluationResult(
            device_id=device_id,
            destination_query=destination,
            lookup_ip="",
            routing_table=target_table,
            matched=False,
            ambiguous_selection=False,
            is_ecmp=False,
            ecmp_gateways=[],
            missing_evidence=False,
            matching_rib_routes=[],
            eligible_route_candidates=[],
            calculated_best_candidates=[],
            verified_forwarding_info={
                "is_verified_fib": False,
                "status": "NOT_VERIFIED",
                "reason": "Invalid IPv4 destination query.",
            },
            observed_traffic_path={
                "is_observed": False,
                "status": "NOT_OBSERVED",
                "hops": [],
            },
            reason=f"Invalid IPv4 address or CIDR prefix '{destination}'.",
        )

    lookup_ip_str = str(lookup_ip_obj)
    missing_ev = completeness in (
        RouteCompleteness.FAILED.value,
        RouteCompleteness.UNREACHABLE.value,
        RouteCompleteness.CANCELLED.value,
        RouteCompleteness.EMPTY.value,
    ) or len(routes) == 0

    if completeness == RouteCompleteness.PARTIAL.value:
        warnings.append("Route dataset is PARTIAL; more specific prefixes may have been omitted.")

    table_routes = [r for r in routes if (r.routing_table or "main") == target_table]
    if not table_routes:
        other_tables = sorted({r.routing_table or "main" for r in routes if (r.routing_table or "main") != target_table})
        if other_tables:
            warnings.append(
                f"No routes exist in table '{target_table}', though routes exist in VRF/tables: {', '.join(other_tables)}."
            )

    # Delegate foundational host LPM check to WP 4.6.0 engine (no logic duplication!)
    base_lpm = evaluate_longest_prefix_match(
        list(table_routes),
        lookup_ip_str,
        require_active=True,
        routing_table=target_table,
    )

    # Filter RIB covering routes (if a subnet CIDR was queried, route network must cover the whole target_net!)
    matching_rib: List[NormalizedRoute] = []
    partial_subnet_routes: List[NormalizedRoute] = []
    for r in table_routes:
        r_net = r.network
        if r_net is None:
            continue
        if target_net is not None:
            if target_net.subnet_of(r_net):
                matching_rib.append(r)
            elif r_net.overlaps(target_net):
                partial_subnet_routes.append(r)
        else:
            if lookup_ip_obj in r_net:
                matching_rib.append(r)

    if partial_subnet_routes and not matching_rib:
        warnings.append(
            f"Destination network {target_net} is only partially covered by more-specific subnet routes."
        )

    # Separate null/reject routes from unicast forwarding-eligible routes
    eligible: List[NormalizedRoute] = [r for r in matching_rib if _is_route_eligible_unicast(r)]
    active_null_routes: List[NormalizedRoute] = [
        r for r in matching_rib
        if r.active and not r.disabled and not r.unreachable and not _is_route_eligible_unicast(r)
    ]

    # Sort eligible candidates:
    # 1. Longest prefix_len (descending)
    # 2. Lowest administrative distance (ascending)
    # 3. Connected route preference
    # 4. Lowest metric when present (ascending; None treated as 0 for static/connected)
    def _candidate_key(r: NormalizedRoute) -> Tuple[int, int, int, int]:
        metric_val = r.metric if r.metric is not None else 0
        conn_bonus = 1 if r.connect else 0
        return (r.prefix_len, -r.distance, conn_bonus, -metric_val)

    eligible_sorted = sorted(eligible, key=_candidate_key, reverse=True)

    # Check if an active blackhole/unreachable/prohibit route is MORE specific than any unicast candidate
    best_null = max(active_null_routes, key=lambda r: (r.prefix_len, -r.distance), default=None)
    best_unicast = eligible_sorted[0] if eligible_sorted else None

    calculated_best: List[NormalizedRoute] = []
    ambiguous = False
    ecmp_gws: List[str] = []
    reason = base_lpm.get("reason", "")

    if best_null is not None and (
        best_unicast is None
        or (best_null.prefix_len, -best_null.distance) > (best_unicast.prefix_len, -best_unicast.distance)
    ):
        r_type_str = best_null.route_type.value if hasattr(best_null.route_type, "value") else str(best_null.route_type)
        reason = f"Destination matches active {r_type_str} null/reject route {best_null.dst_prefix}."
        matched = False
    elif best_unicast is not None:
        matched = True
        top_tuple = (
            best_unicast.prefix_len,
            best_unicast.distance,
            best_unicast.metric if best_unicast.metric is not None else 0,
        )
        tied = [
            r for r in eligible_sorted
            if (r.prefix_len, r.distance, r.metric if r.metric is not None else 0) == top_tuple
        ]
        calculated_best = tied

        # Collect ECMP gateways across single multi-gw route or multiple equal-cost routes
        for r in tied:
            gws = r.gateways if r.gateways else ([r.gateway] if r.gateway else [])
            for g in gws:
                if g and g not in ecmp_gws:
                    ecmp_gws.append(g)

        # Detect ambiguous selection: distinct protocols or conflicting interfaces at identical prefix/distance
        distinct_protocols = {r.protocol for r in tied}
        if len(distinct_protocols) > 1:
            ambiguous = True
            warnings.append(
                f"Ambiguous route tie: multiple protocols ({', '.join(sorted(distinct_protocols))}) "
                f"share prefix /{best_unicast.prefix_len} and distance {best_unicast.distance}."
            )
        reason = (
            f"Calculated best RIB match {best_unicast.dst_prefix} via "
            f"{', '.join(ecmp_gws) or best_unicast.interface_name or 'connected'} "
            f"(table={target_table}, distance={best_unicast.distance})."
        )
    else:
        matched = False
        if not reason:
            reason = f"No eligible active route matches {destination} in table '{target_table}'."

    is_ecmp = len(ecmp_gws) > 1

    # Recursive resolution on primary calculated gateway (filtered strictly to target_table!)
    rec_dict: Optional[Dict[str, Any]] = None
    if matched and calculated_best:
        primary_gw = ecmp_gws[0] if ecmp_gws else calculated_best[0].gateway
        if primary_gw and not calculated_best[0].connect:
            rec = resolve_recursive_next_hop(primary_gw, table_routes, max_depth=16)
            rec_dict = {
                "status": rec.status.value,
                "target_gateway": rec.target_gateway,
                "resolved_ip": rec.resolved_ip,
                "egress_interface": rec.egress_interface,
                "depth": rec.depth,
                "resolution_chain": list(rec.resolution_chain),
                "loop_detected": rec.loop_detected,
                "confidence": rec.confidence,
                "reason": rec.reason,
            }

    # Tier 4: Verified FIB state (NEVER conflated with calculated RIB winner!)
    fib_verified_routes = [r.to_dict() for r in calculated_best if _has_verified_fib_marker(r)]
    verified_fib_info = {
        "is_verified_fib": len(fib_verified_routes) > 0,
        "status": "FIB_FLAG_VERIFIED" if fib_verified_routes else "CALCULATED_ONLY_NOT_FIB_VERIFIED",
        "verified_routes": fib_verified_routes,
        "disclosure": (
            "Hardware/FIB flag explicitly observed on route entry."
            if fib_verified_routes
            else "Calculated from RIB CLI output; actual kernel/ASIC FIB installation is not independently verified."
        ),
    }

    # Tier 5: Observed data-plane traffic path
    has_obs = bool(observed_hops)
    observed_path_info = {
        "is_observed": has_obs,
        "status": "OBSERVED_TRACEROUTE" if has_obs else "NOT_OBSERVED",
        "hops": list(observed_hops) if observed_hops else [],
        "disclosure": (
            "Observed from active probe/traceroute evidence."
            if has_obs
            else "No active packet path observation provided; forwarding path is control-plane inferred."
        ),
    }

    return LPMEvaluationResult(
        device_id=device_id,
        destination_query=destination,
        lookup_ip=lookup_ip_str,
        routing_table=target_table,
        matched=matched,
        ambiguous_selection=ambiguous,
        is_ecmp=is_ecmp,
        ecmp_gateways=ecmp_gws,
        missing_evidence=missing_ev,
        matching_rib_routes=[r.to_dict() for r in matching_rib],
        eligible_route_candidates=[r.to_dict() for r in eligible_sorted],
        calculated_best_candidates=[
            {
                **r.to_dict(),
                "selection_state": "CALCULATED_BEST_CANDIDATE",
                "confirmed_fib": _has_verified_fib_marker(r),
            }
            for r in calculated_best
        ],
        verified_forwarding_info=verified_fib_info,
        observed_traffic_path=observed_path_info,
        recursive_resolution=rec_dict,
        reason=reason,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 6.2 Route Table & Cross-Device Anomaly Analyzer
# ---------------------------------------------------------------------------

class RouteTableAnalyzer:
    """
    Analyzes single-device and multi-device NormalizedRoute datasets for all 12
    routing anomaly classes required by WP 4.6.2.
    """

    def analyze_device_routes(
        self,
        device_id: str,
        routes: Sequence[NormalizedRoute],
        *,
        evidence_id: str = "",
        target_destination: Optional[str] = None,
        expected_tables: Optional[Set[str]] = None,
        require_default_route: bool = True,
        expected_default_gateways: Optional[Set[str]] = None,
    ) -> List[RouteFinding]:
        findings: List[RouteFinding] = []
        ev_ids = [evidence_id] if evidence_id else []
        if not ev_ids:
            ev_ids = sorted({_route_evidence_id(r) for r in routes if _route_evidence_id(r) != "ev_unknown"})

        by_table: Dict[str, List[NormalizedRoute]] = {}
        for r in routes:
            tbl = r.routing_table or "main"
            by_table.setdefault(tbl, []).append(r)

        # 1. Missing default route in 'main'
        main_routes = by_table.get("main", [])
        active_defaults = [
            r for r in main_routes
            if r.is_default_route() and _is_route_eligible_unicast(r)
        ]
        if require_default_route and not active_defaults:
            inactive_defaults = [r for r in main_routes if r.is_default_route()]
            gw_hint = inactive_defaults[0].gateway if inactive_defaults else ""
            findings.append(
                RouteFinding(
                    finding_type=RouteFindingType.MISSING_DEFAULT_ROUTE.value,
                    device_id=device_id,
                    routing_table="main",
                    dst_prefix="0.0.0.0/0",
                    gateway=gw_hint,
                    evidence_ids=ev_ids,
                    severity="HIGH",
                    confidence="CONFIRMED" if routes else "LOW",
                    explanation=(
                        f"Device '{device_id}' has an inactive/disabled default route in table 'main'."
                        if inactive_defaults
                        else f"Device '{device_id}' has no active default route (0.0.0.0/0) in table 'main'."
                    ),
                )
            )

        # 2. Unexpected default route (conflicting default gateways or unexpected gateway)
        if expected_default_gateways and active_defaults:
            for d_rt in active_defaults:
                gws = d_rt.gateways or ([d_rt.gateway] if d_rt.gateway else [])
                for g in gws:
                    if g not in expected_default_gateways:
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.UNEXPECTED_DEFAULT_ROUTE.value,
                                device_id=device_id,
                                routing_table="main",
                                dst_prefix="0.0.0.0/0",
                                gateway=g,
                                evidence_ids=ev_ids or [_route_evidence_id(d_rt)],
                                severity="HIGH",
                                confidence="HIGH",
                                explanation=(
                                    f"Active default route on '{device_id}' points to unexpected gateway '{g}' "
                                    f"(expected one of: {', '.join(sorted(expected_default_gateways))})."
                                ),
                            )
                        )
        elif len(active_defaults) > 1:
            distinct_protos = {r.protocol for r in active_defaults}
            if len(distinct_protos) > 1:
                findings.append(
                    RouteFinding(
                        finding_type=RouteFindingType.UNEXPECTED_DEFAULT_ROUTE.value,
                        device_id=device_id,
                        routing_table="main",
                        dst_prefix="0.0.0.0/0",
                        gateway=", ".join(r.gateway for r in active_defaults),
                        evidence_ids=ev_ids,
                        severity="MEDIUM",
                        confidence="HIGH",
                        explanation=(
                            f"Multiple active default routes learned via different protocols "
                            f"({', '.join(sorted(distinct_protos))}) in table 'main'."
                        ),
                    )
                )

        # 3. Missing destination route (when target_destination is specified)
        if target_destination:
            lpm = evaluate_route_lookup(routes, target_destination, device_id=device_id, routing_table="main")
            if not lpm.matched:
                # Check if destination exists only in a non-main VRF table!
                vrf_hits = [
                    tbl for tbl in by_table
                    if tbl != "main"
                    and evaluate_route_lookup(routes, target_destination, device_id=device_id, routing_table=tbl).matched
                ]
                findings.append(
                    RouteFinding(
                        finding_type=RouteFindingType.MISSING_DESTINATION_ROUTE.value,
                        device_id=device_id,
                        routing_table="main",
                        dst_prefix=target_destination,
                        gateway="",
                        evidence_ids=ev_ids,
                        severity="HIGH",
                        confidence="HIGH" if routes else "LOW",
                        explanation=(
                            f"No active route matches destination '{target_destination}' in table 'main' on '{device_id}'."
                            + (f" Matching routes exist in VRF table(s): {', '.join(vrf_hits)}." if vrf_hits else "")
                        ),
                    )
                )

        # Per-table inspections
        known_tables = expected_tables or {"main"}
        for tbl, tbl_routes in by_table.items():
            # 4. Unexpected routing-table assignment (isolated non-main table without connected interface or unexpected VRF)
            if expected_tables is not None and tbl not in known_tables:
                findings.append(
                    RouteFinding(
                        finding_type=RouteFindingType.UNEXPECTED_ROUTING_TABLE_ASSIGNMENT.value,
                        device_id=device_id,
                        routing_table=tbl,
                        dst_prefix=tbl_routes[0].dst_prefix,
                        gateway=tbl_routes[0].gateway,
                        evidence_ids=ev_ids,
                        severity="MEDIUM",
                        confidence="HIGH",
                        explanation=(
                            f"Routes found in unexpected routing table '{tbl}' on '{device_id}' "
                            f"(count={len(tbl_routes)})."
                        ),
                    )
                )
            elif tbl != "main":
                has_conn = any(r.connect for r in tbl_routes)
                if not has_conn:
                    # Check if gateways in this VRF cannot resolve within the same VRF
                    unresolved_vrf = [
                        r for r in tbl_routes
                        if not r.connect and _extract_ipv4(r.gateway)
                        and resolve_recursive_next_hop(r.gateway, tbl_routes, max_depth=8).status
                        in (NextHopResolutionStatus.UNRESOLVED, NextHopResolutionStatus.UNREACHABLE)
                    ]
                    if unresolved_vrf:
                        r0 = unresolved_vrf[0]
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.UNEXPECTED_ROUTING_TABLE_ASSIGNMENT.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=r0.dst_prefix,
                                gateway=r0.gateway,
                                evidence_ids=ev_ids or [_route_evidence_id(r0)],
                                severity="MEDIUM",
                                confidence="MEDIUM",
                                explanation=(
                                    f"Routing table '{tbl}' on '{device_id}' contains static/dynamic route "
                                    f"{r0.dst_prefix} via {r0.gateway} with no connected subnet in table '{tbl}' "
                                    "(possible VRF / table assignment mismatch)."
                                ),
                            )
                        )

            # Group by dst_prefix within table
            by_prefix: Dict[str, List[NormalizedRoute]] = {}
            for r in tbl_routes:
                by_prefix.setdefault(r.dst_prefix, []).append(r)

            for pfx, pfx_routes in by_prefix.items():
                # 5. Duplicate route candidates & 6. Conflicting route advertisements & 7. ECMP configuration
                if len(pfx_routes) > 1:
                    active_pfx = [r for r in pfx_routes if _is_route_eligible_unicast(r)]
                    distinct_gws = {r.gateway for r in pfx_routes if r.gateway}
                    distinct_protos = {r.protocol for r in pfx_routes}

                    # ECMP check: >=2 active routes sharing minimum distance
                    if len(active_pfx) > 1:
                        min_d = min(r.distance for r in active_pfx)
                        ecmp_set = [r for r in active_pfx if r.distance == min_d]
                        if len(ecmp_set) > 1:
                            findings.append(
                                RouteFinding(
                                    finding_type=RouteFindingType.ECMP_CONFIGURATION.value,
                                    device_id=device_id,
                                    routing_table=tbl,
                                    dst_prefix=pfx,
                                    gateway=", ".join(r.gateway for r in ecmp_set),
                                    evidence_ids=ev_ids,
                                    severity="INFO",
                                    confidence="CONFIRMED",
                                    explanation=(
                                        f"Equal-Cost Multi-Path (ECMP) active for {pfx} in table '{tbl}' "
                                        f"across {len(ecmp_set)} next-hops (distance={min_d})."
                                    ),
                                )
                            )

                    if len(distinct_protos) > 1 and len(distinct_gws) > 1:
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.CONFLICTING_ROUTE_ADVERTISEMENTS.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=pfx,
                                gateway=", ".join(sorted(distinct_gws)),
                                evidence_ids=ev_ids,
                                severity="MEDIUM",
                                confidence="HIGH",
                                explanation=(
                                    f"Prefix {pfx} in table '{tbl}' is present via multiple protocols "
                                    f"({', '.join(sorted(distinct_protos))}) pointing to distinct gateways "
                                    f"({', '.join(sorted(distinct_gws))})."
                                ),
                            )
                        )
                    else:
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.DUPLICATE_ROUTE_CANDIDATES.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=pfx,
                                gateway=", ".join(sorted(distinct_gws)),
                                evidence_ids=ev_ids,
                                severity="LOW",
                                confidence="CONFIRMED",
                                explanation=(
                                    f"Multiple ({len(pfx_routes)}) route candidates exist for {pfx} in table '{tbl}' "
                                    f"(distances={sorted({r.distance for r in pfx_routes})})."
                                ),
                            )
                        )
                else:
                    # Single route entry with multi-gateway comma list -> ECMP!
                    r_only = pfx_routes[0]
                    if _is_route_eligible_unicast(r_only) and len(r_only.gateways) > 1:
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.ECMP_CONFIGURATION.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=pfx,
                                gateway=", ".join(r_only.gateways),
                                evidence_ids=ev_ids or [_route_evidence_id(r_only)],
                                severity="INFO",
                                confidence="CONFIRMED",
                                explanation=(
                                    f"Single-entry ECMP route active for {pfx} in table '{tbl}' "
                                    f"with gateways: {', '.join(r_only.gateways)}."
                                ),
                            )
                        )

            # 8. Unreachable next-hop & 9. Recursive gateway dependency
            for r in tbl_routes:
                if r.disabled or r.connect:
                    continue
                gw_ip = _extract_ipv4(r.gateway)
                if r.unreachable or (not r.active and not r.disabled):
                    findings.append(
                        RouteFinding(
                            finding_type=RouteFindingType.UNREACHABLE_NEXT_HOP.value,
                            device_id=device_id,
                            routing_table=tbl,
                            dst_prefix=r.dst_prefix,
                            gateway=r.gateway,
                            evidence_ids=ev_ids or [_route_evidence_id(r)],
                            severity="HIGH",
                            confidence="CONFIRMED",
                            explanation=(
                                f"Route {r.dst_prefix} via '{r.gateway}' in table '{tbl}' on '{device_id}' "
                                f"is inactive/unreachable (flags='{r.raw_flags}')."
                            ),
                        )
                    )
                    continue

                if gw_ip:
                    rec = resolve_recursive_next_hop(gw_ip, tbl_routes, max_depth=16)
                    if rec.status in (NextHopResolutionStatus.UNRESOLVED, NextHopResolutionStatus.UNREACHABLE):
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.UNREACHABLE_NEXT_HOP.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=r.dst_prefix,
                                gateway=r.gateway,
                                evidence_ids=ev_ids or [_route_evidence_id(r)],
                                severity="HIGH",
                                confidence="HIGH",
                                explanation=(
                                    f"Gateway IP {gw_ip} for route {r.dst_prefix} in table '{tbl}' cannot be "
                                    f"resolved to a directly connected interface: {rec.reason}"
                                ),
                            )
                        )
                    elif rec.status == NextHopResolutionStatus.RECURSIVE_RESOLVED or rec.depth > 1:
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.RECURSIVE_GATEWAY_DEPENDENCY.value,
                                device_id=device_id,
                                routing_table=tbl,
                                dst_prefix=r.dst_prefix,
                                gateway=r.gateway,
                                evidence_ids=ev_ids or [_route_evidence_id(r)],
                                severity="LOW",
                                confidence="CONFIRMED",
                                explanation=(
                                    f"Route {r.dst_prefix} depends recursively (depth={rec.depth}) on "
                                    f"{' -> '.join(rec.resolution_chain)}."
                                ),
                                metadata={"depth": rec.depth, "chain": rec.resolution_chain},
                            )
                        )

            # 10. Overlapping prefixes (non-default active supernet/subnet with divergent gateways)
            non_default_active = [
                r for r in tbl_routes
                if _is_route_eligible_unicast(r) and not r.is_default_route() and r.network is not None
            ]
            # Bound pairwise overlap check to <= 300 non-default routes per table to protect CPU on huge BGP tables
            sample_overlap = non_default_active[:300]
            reported_overlaps: Set[Tuple[str, str]] = set()
            for i in range(len(sample_overlap)):
                ra = sample_overlap[i]
                net_a = ra.network
                assert net_a is not None
                for j in range(i + 1, len(sample_overlap)):
                    rb = sample_overlap[j]
                    net_b = rb.network
                    assert net_b is not None
                    if ra.dst_prefix == rb.dst_prefix:
                        continue
                    if net_a.overlaps(net_b) and ra.gateway != rb.gateway:
                        pair_key = tuple(sorted((ra.dst_prefix, rb.dst_prefix)))
                        if pair_key not in reported_overlaps:
                            reported_overlaps.add(pair_key)
                            findings.append(
                                RouteFinding(
                                    finding_type=RouteFindingType.OVERLAPPING_PREFIXES.value,
                                    device_id=device_id,
                                    routing_table=tbl,
                                    dst_prefix=f"{pair_key[0]} / {pair_key[1]}",
                                    gateway=f"{ra.gateway} vs {rb.gateway}",
                                    evidence_ids=ev_ids,
                                    severity="LOW",
                                    confidence="CONFIRMED",
                                    explanation=(
                                        f"Overlapping active prefixes in table '{tbl}': {ra.dst_prefix} (via {ra.gateway}) "
                                        f"and {rb.dst_prefix} (via {rb.gateway}) steer subsets of address space differently."
                                    ),
                                )
                            )

        return findings

    def analyze_multi_device_routes(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        device_ips: Optional[Dict[str, List[str]]] = None,
        target_destination: Optional[str] = None,
    ) -> List[RouteFinding]:
        """
        Runs per-device anomaly checks plus cross-device inconsistency and asymmetric
        route hypothesis analysis across multiple routers.
        """
        findings: List[RouteFinding] = []
        ip_owner_map = build_ip_owner_index(collections, explicit_device_ips=device_ips)

        for dev_id, col in collections.items():
            findings.extend(
                self.analyze_device_routes(
                    dev_id,
                    col.routes,
                    evidence_id=col.evidence_id,
                    target_destination=target_destination,
                )
            )

        # Cross-device checks:
        # 11. INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES
        # 12. ASYMMETRIC_ROUTE_HYPOTHESIS (strictly marked HYPOTHESIS, never confirmed fact!)
        connected_prefixes_by_dev: Dict[str, Set[str]] = {}
        for dev_id, col in collections.items():
            connected_prefixes_by_dev[dev_id] = {
                r.dst_prefix
                for r in col.routes
                if r.connect and r.active and not r.is_default_route() and (r.routing_table or "main") == "main"
            }

        for dev_a, col_a in collections.items():
            for ra in col_a.routes:
                if not _is_route_eligible_unicast(ra) or ra.connect:
                    continue
                gw_ip = _extract_ipv4(ra.gateway)
                if not gw_ip:
                    continue
                owners = ip_owner_map.get(gw_ip, [])
                if len(owners) != 1:
                    continue
                dev_b = owners[0]
                if dev_b == dev_a or dev_b not in collections:
                    continue
                col_b = collections[dev_b]
                tbl = ra.routing_table or "main"

                # Does dev_b actually have an active route for ra.dst_prefix in the same table?
                lpm_b = evaluate_route_lookup(
                    col_b.routes,
                    ra.dst_prefix,
                    device_id=dev_b,
                    routing_table=tbl,
                    completeness=col_b.completeness,
                )
                if not lpm_b.matched and col_b.completeness == RouteCompleteness.COMPLETE.value:
                    findings.append(
                        RouteFinding(
                            finding_type=RouteFindingType.INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES.value,
                            device_id=dev_a,
                            related_device_id=dev_b,
                            routing_table=tbl,
                            dst_prefix=ra.dst_prefix,
                            gateway=gw_ip,
                            evidence_ids=[col_a.evidence_id, col_b.evidence_id],
                            severity="HIGH",
                            confidence="HIGH",
                            explanation=(
                                f"Device '{dev_a}' forwards {ra.dst_prefix} to next-hop '{dev_b}' ({gw_ip}), "
                                f"but '{dev_b}' has no eligible active route covering {ra.dst_prefix} in table '{tbl}'."
                            ),
                        )
                    )
                elif lpm_b.matched and lpm_b.calculated_best_candidates:
                    # Check immediate 2-hop loop or return-route asymmetry hypothesis
                    best_b = lpm_b.calculated_best_candidates[0]
                    gw_b_ip = _extract_ipv4(str(best_b.get("gateway") or ""))
                    if gw_b_ip and dev_a in ip_owner_map.get(gw_b_ip, []):
                        findings.append(
                            RouteFinding(
                                finding_type=RouteFindingType.INCONSISTENT_ROUTE_STATE_BETWEEN_DEVICES.value,
                                device_id=dev_a,
                                related_device_id=dev_b,
                                routing_table=tbl,
                                dst_prefix=ra.dst_prefix,
                                gateway=gw_ip,
                                evidence_ids=[col_a.evidence_id, col_b.evidence_id],
                                severity="CRITICAL",
                                confidence="HIGH",
                                explanation=(
                                    f"Contradictory mutual next-hop loop between '{dev_a}' and '{dev_b}' for "
                                    f"destination {ra.dst_prefix} in table '{tbl}'."
                                ),
                            )
                        )

                # Asymmetric route hypothesis check for connected LAN prefixes of dev_a
                if not ra.is_default_route():
                    for src_lan in sorted(connected_prefixes_by_dev.get(dev_a, set())):
                        # Ignore shared transit subnet connecting dev_a and dev_b
                        try:
                            lan_net = ipaddress.ip_network(src_lan, strict=False)
                            if ipaddress.ip_address(gw_ip) in lan_net:
                                continue
                        except Exception:
                            continue

                        ret_lpm = evaluate_route_lookup(
                            col_b.routes,
                            src_lan,
                            device_id=dev_b,
                            routing_table=tbl,
                            completeness=col_b.completeness,
                        )
                        if not ret_lpm.matched and col_b.completeness == RouteCompleteness.COMPLETE.value:
                            findings.append(
                                RouteFinding(
                                    finding_type=RouteFindingType.ASYMMETRIC_ROUTE_HYPOTHESIS.value,
                                    device_id=dev_b,
                                    related_device_id=dev_a,
                                    routing_table=tbl,
                                    dst_prefix=src_lan,
                                    gateway="",
                                    evidence_ids=[col_a.evidence_id, col_b.evidence_id],
                                    severity="MEDIUM",
                                    confidence="HYPOTHESIS",
                                    explanation=(
                                        f"Asymmetric/missing return route hypothesis: '{dev_a}' routes {ra.dst_prefix} "
                                        f"via '{dev_b}', but '{dev_b}' has no return route to '{dev_a}' source subnet {src_lan} "
                                        "(unless NAT masquerade is applied on '{dev_a}')."
                                    ),
                                )
                            )
                        elif ret_lpm.matched and ret_lpm.calculated_best_candidates:
                            ret_gw = _extract_ipv4(str(ret_lpm.calculated_best_candidates[0].get("gateway") or ""))
                            ret_owners = ip_owner_map.get(ret_gw, []) if ret_gw else []
                            if ret_owners and dev_a not in ret_owners:
                                findings.append(
                                    RouteFinding(
                                        finding_type=RouteFindingType.ASYMMETRIC_ROUTE_HYPOTHESIS.value,
                                        device_id=dev_b,
                                        related_device_id=dev_a,
                                        routing_table=tbl,
                                        dst_prefix=src_lan,
                                        gateway=ret_gw or "",
                                        evidence_ids=[col_a.evidence_id, col_b.evidence_id],
                                        severity="LOW",
                                        confidence="HYPOTHESIS",
                                        explanation=(
                                            f"Asymmetric return path hypothesis: forward traffic from '{dev_a}' ({src_lan}) "
                                            f"to {ra.dst_prefix} enters '{dev_b}', whereas '{dev_b}' routes return traffic for "
                                            f"{src_lan} toward '{ret_owners[0]}' ({ret_gw})."
                                        ),
                                    )
                                )

        return findings


def build_ip_owner_index(
    collections: Dict[str, RouteCollectionResult],
    explicit_device_ips: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    """
    Maps clean IPv4 addresses -> list of owning CanonicalDevice IDs using:
    1. Explicit NormalizedIPAddress / interface IPs when provided
    2. `pref_src` on connected routes (`DAC`) in NormalizedRoute
    3. `management_ip` on RouteCollectionResult
    """
    ip_owners: Dict[str, List[str]] = {}

    def _add(ip_val: Optional[str], dev_id: str) -> None:
        clean = _extract_ipv4(str(ip_val or "").split("/")[0])
        if clean and clean not in ("0.0.0.0", "127.0.0.1"):
            owners = ip_owners.setdefault(clean, [])
            if dev_id not in owners:
                owners.append(dev_id)

    for dev_id, ips in (explicit_device_ips or {}).items():
        for raw in ips or []:
            _add(raw, dev_id)

    for dev_id, col in collections.items():
        if col.management_ip:
            _add(col.management_ip, dev_id)
        for r in col.routes:
            if r.pref_src:
                _add(r.pref_src, dev_id)

    return ip_owners


# ---------------------------------------------------------------------------
# 6.3 & 6.4 Multi-Device Route Path Reconstruction Engine
# ---------------------------------------------------------------------------

class RoutePathEvaluator:
    """
    Reconstructs inferred or evidence-confirmed forwarding paths across multiple
    routers from collected NormalizedRoute datasets without inventing unknown devices.
    """

    MAX_HOPS = 16
    MAX_ECMP_BRANCHES = 8

    def evaluate_path(
        self,
        source_device_id: str,
        destination: str,
        collections: Dict[str, RouteCollectionResult],
        *,
        routing_table: str = "main",
        device_ips: Optional[Dict[str, List[str]]] = None,
        device_ip_tables: Optional[Dict[Tuple[str, str], str]] = None,
        verified_adjacencies: Optional[Set[Tuple[str, str]]] = None,
        down_interfaces: Optional[Set[Tuple[str, str]]] = None,
        observed_traceroute_hops: Optional[List[str]] = None,
        source_prefix_for_symmetry: Optional[str] = None,
        now: Optional[float] = None,
    ) -> RoutePathEvaluationResult:
        eval_time = now if now is not None else time.time()
        start_table = (routing_table or "main").strip()

        lookup_ip_obj, _ = _parse_destination_target(destination)
        if lookup_ip_obj is None:
            return RoutePathEvaluationResult(
                source_device_id=source_device_id,
                destination=destination,
                routing_table=start_table,
                state=PathResultState.PATH_UNRESOLVED.value,
                confidence=0.0,
                explanation=f"Invalid IPv4 destination '{destination}'.",
            )

        src_col = collections.get(source_device_id)
        if (
            src_col is None
            or src_col.completeness
            in (
                RouteCompleteness.FAILED.value,
                RouteCompleteness.UNREACHABLE.value,
                RouteCompleteness.CANCELLED.value,
                RouteCompleteness.EMPTY.value,
            )
            or len(src_col.routes) == 0
        ):
            return RoutePathEvaluationResult(
                source_device_id=source_device_id,
                destination=destination,
                routing_table=start_table,
                state=PathResultState.PATH_NOT_ENOUGH_EVIDENCE.value,
                confidence=0.0,
                incomplete_evidence_detected=True,
                explanation=(
                    f"Source device '{source_device_id}' has no usable route evidence "
                    f"(completeness={src_col.completeness if src_col else 'MISSING'})."
                ),
            )

        ip_owners = build_ip_owner_index(collections, explicit_device_ips=device_ips)
        adj_set: Set[Tuple[str, str]] = set()
        for a, b in verified_adjacencies or set():
            adj_set.add((a, b))
            adj_set.add((b, a))
        down_ifaces = down_interfaces or set()

        completed_branches: List[Tuple[str, List[RoutePathHop]]] = []
        loop_found = False
        stale_found = False
        incomplete_found = False
        is_ecmp_any = False
        missing_gateways: List[str] = []
        ambiguous_gateways: List[str] = []
        contradictions: List[str] = []
        all_ev_ids: List[str] = []

        def _record_ev(eid: str) -> None:
            if eid and eid not in all_ev_ids:
                all_ev_ids.append(eid)

        # Iterative DFS queue: (curr_dev, curr_table, visited_pairs, hops_so_far, is_ecmp_flag)
        stack: List[Tuple[str, str, Set[Tuple[str, str]], List[RoutePathHop], bool]] = [
            (source_device_id, start_table, set(), [], False)
        ]

        while stack and len(completed_branches) < self.MAX_ECMP_BRANCHES:
            curr_dev, curr_tbl, visited, hops, branch_ecmp = stack.pop(0)
            hop_idx = len(hops) + 1

            if hop_idx > self.MAX_HOPS:
                hops_ext = hops + [
                    RoutePathHop(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        routing_table=curr_tbl,
                        hop_state="MAX_HOPS_EXCEEDED",
                        notes=[f"Exceeded maximum hop limit ({self.MAX_HOPS})."],
                    )
                ]
                completed_branches.append((PathResultState.PATH_UNRESOLVED.value, hops_ext))
                continue

            if (curr_dev, curr_tbl) in visited:
                loop_found = True
                hops_ext = hops + [
                    RoutePathHop(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        routing_table=curr_tbl,
                        hop_state="LOOP_DETECTED",
                        notes=[f"Routing loop detected: revisited ({curr_dev}, table={curr_tbl})."],
                    )
                ]
                completed_branches.append((PathResultState.PATH_UNREACHABLE.value, hops_ext))
                continue

            next_visited = set(visited) | {(curr_dev, curr_tbl)}
            col = collections.get(curr_dev)

            if (
                col is None
                or col.completeness
                in (
                    RouteCompleteness.FAILED.value,
                    RouteCompleteness.UNREACHABLE.value,
                    RouteCompleteness.CANCELLED.value,
                    RouteCompleteness.EMPTY.value,
                )
                or len(col.routes) == 0
            ):
                incomplete_found = True
                hops_ext = hops + [
                    RoutePathHop(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        routing_table=curr_tbl,
                        hop_state="INCOMPLETE_EVIDENCE",
                        completeness=col.completeness if col else RouteCompleteness.UNREACHABLE.value,
                        freshness=EvidenceFreshness.UNKNOWN.value,
                        notes=[f"Intermediate router '{curr_dev}' has no available route evidence."],
                    )
                ]
                completed_branches.append((PathResultState.PATH_PARTIAL.value, hops_ext))
                continue

            _record_ev(col.evidence_id)
            fresh = col.freshness(now=eval_time)
            if fresh != EvidenceFreshness.FRESH.value:
                stale_found = True
            if col.completeness != RouteCompleteness.COMPLETE.value:
                incomplete_found = True

            lpm = evaluate_route_lookup(
                col.routes,
                destination,
                device_id=curr_dev,
                routing_table=curr_tbl,
                completeness=col.completeness,
            )

            if lpm.ambiguous_selection:
                contradictions.extend(lpm.warnings)

            if not lpm.matched or not lpm.calculated_best_candidates:
                hop_state = "NULL_ROUTE" if "null/reject" in lpm.reason else "NO_ROUTE"
                hops_ext = hops + [
                    RoutePathHop(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        routing_table=curr_tbl,
                        hop_state=hop_state,
                        evidence_ids=[col.evidence_id],
                        freshness=fresh,
                        completeness=col.completeness,
                        notes=[lpm.reason],
                    )
                ]
                completed_branches.append((PathResultState.PATH_UNREACHABLE.value, hops_ext))
                continue

            best_cand = lpm.calculated_best_candidates[0]
            matched_pfx = str(best_cand.get("dst_prefix") or "0.0.0.0/0")
            proto = str(best_cand.get("protocol") or "static")
            dist = int(best_cand.get("distance") or 1)
            is_conn = bool(best_cand.get("connect"))

            # Directly connected destination subnet on curr_dev (or destination IP owned directly by curr_dev)
            if str(lookup_ip_obj) in ip_owners and curr_dev in ip_owners[str(lookup_ip_obj)]:
                is_conn = True

            if is_conn and matched_pfx not in ("0.0.0.0/0", "::/0"):
                egress_if = str(best_cand.get("interface_name") or best_cand.get("gateway") or "")
                if egress_if and (curr_dev, egress_if) in down_ifaces:
                    contradictions.append(
                        f"Route {matched_pfx} on '{curr_dev}' appears active, but interface '{egress_if}' is operationally DOWN."
                    )
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            hop_state="INTERFACE_DOWN",
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[f"Connected egress interface '{egress_if}' is DOWN."],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_UNREACHABLE.value, hops_ext))
                    continue

                hops_ext = hops + [
                    RoutePathHop(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        routing_table=curr_tbl,
                        matched_prefix=matched_pfx,
                        gateway=str(best_cand.get("gateway") or ""),
                        immediate_gateway=best_cand.get("immediate_gw"),
                        egress_interface=egress_if,
                        protocol=proto,
                        distance=dist,
                        hop_state="DIRECT_CONNECTED",
                        is_ecmp_branch=branch_ecmp,
                        evidence_ids=[col.evidence_id],
                        freshness=fresh,
                        completeness=col.completeness,
                        topology_verified=True,
                        notes=[f"Destination {destination} is directly connected on '{curr_dev}' ({egress_if})."],
                    )
                ]
                branch_state = (
                    PathResultState.PATH_AMBIGUOUS.value
                    if lpm.ambiguous_selection
                    else PathResultState.PATH_INFERRED.value
                )
                completed_branches.append((branch_state, hops_ext))
                continue

            # Expand ECMP or single next-hop gateway(s)
            gateways = lpm.ecmp_gateways if lpm.ecmp_gateways else [str(best_cand.get("gateway") or "")]
            if len(gateways) > 1:
                is_ecmp_any = True

            table_routes = [r for r in col.routes if (r.routing_table or "main") == curr_tbl]

            for gw in gateways:
                rec = resolve_recursive_next_hop(gw, table_routes, max_depth=16)
                is_rec = rec.status == NextHopResolutionStatus.RECURSIVE_RESOLVED or rec.depth > 1
                egress_if = rec.egress_interface or best_cand.get("interface_name")
                nh_ip = rec.resolved_ip or _extract_ipv4(gw)

                if rec.loop_detected:
                    loop_found = True
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            gateway=gw,
                            resolved_gateway_ip=nh_ip,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            hop_state="LOOP_DETECTED",
                            is_recursive=is_rec,
                            recursion_chain=list(rec.resolution_chain),
                            is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[rec.reason],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_UNREACHABLE.value, hops_ext))
                    continue

                if rec.status in (NextHopResolutionStatus.UNRESOLVED, NextHopResolutionStatus.UNREACHABLE):
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            gateway=gw,
                            resolved_gateway_ip=nh_ip,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            hop_state="UNRESOLVED_GATEWAY",
                            is_recursive=is_rec,
                            recursion_chain=list(rec.resolution_chain),
                            is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[rec.reason],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_UNRESOLVED.value, hops_ext))
                    continue

                if egress_if and (curr_dev, egress_if) in down_ifaces:
                    contradictions.append(
                        f"Route {matched_pfx} via {gw} on '{curr_dev}' resolves to DOWN interface '{egress_if}'."
                    )
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            gateway=gw,
                            resolved_gateway_ip=nh_ip,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            hop_state="INTERFACE_DOWN",
                            is_recursive=is_rec,
                            recursion_chain=list(rec.resolution_chain),
                            is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[f"Egress interface '{egress_if}' is operationally DOWN."],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_UNREACHABLE.value, hops_ext))
                    continue

                owners = [o for o in ip_owners.get(nh_ip or "", []) if o != curr_dev]

                if len(owners) > 1:
                    if nh_ip and nh_ip not in ambiguous_gateways:
                        ambiguous_gateways.append(nh_ip)
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            gateway=gw,
                            immediate_gateway=best_cand.get("immediate_gw"),
                            resolved_gateway_ip=nh_ip,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            hop_state="AMBIGUOUS_NEXT_HOP",
                            is_recursive=is_rec,
                            recursion_chain=list(rec.resolution_chain),
                            is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[f"Gateway IP {nh_ip} is claimed by multiple devices: {', '.join(owners)}."],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_AMBIGUOUS.value, hops_ext))
                    continue

                if len(owners) == 0:
                    # Do NOT invent unknown devices! Mark missing intermediate / external next-hop explicitly.
                    if nh_ip and nh_ip not in missing_gateways:
                        missing_gateways.append(nh_ip)
                    hops_ext = hops + [
                        RoutePathHop(
                            hop_index=hop_idx,
                            device_id=curr_dev,
                            routing_table=curr_tbl,
                            matched_prefix=matched_pfx,
                            gateway=gw,
                            immediate_gateway=best_cand.get("immediate_gw"),
                            resolved_gateway_ip=nh_ip,
                            egress_interface=egress_if,
                            protocol=proto,
                            distance=dist,
                            next_device_id=None,
                            hop_state="EXTERNAL_OR_MISSING_ROUTER",
                            is_recursive=is_rec,
                            recursion_chain=list(rec.resolution_chain),
                            is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                            evidence_ids=[col.evidence_id],
                            freshness=fresh,
                            completeness=col.completeness,
                            notes=[
                                f"Next-hop {nh_ip or gw} via {egress_if or 'unknown'} is not associated with any "
                                "registered device in the collected route dataset (unmanaged upstream or missing intermediate router)."
                            ],
                        )
                    ]
                    completed_branches.append((PathResultState.PATH_PARTIAL.value, hops_ext))
                    continue

                next_dev = owners[0]
                topo_ok = (curr_dev, next_dev) in adj_set
                next_tbl = (
                    device_ip_tables.get((next_dev, nh_ip or ""), curr_tbl)
                    if device_ip_tables
                    else curr_tbl
                )

                hop_obj = RoutePathHop(
                    hop_index=hop_idx,
                    device_id=curr_dev,
                    routing_table=curr_tbl,
                    matched_prefix=matched_pfx,
                    gateway=gw,
                    immediate_gateway=best_cand.get("immediate_gw"),
                    resolved_gateway_ip=nh_ip,
                    egress_interface=egress_if,
                    protocol=proto,
                    distance=dist,
                    next_device_id=next_dev,
                    hop_state="RECURSIVE_RESOLVED" if is_rec else "NEXT_HOP_RESOLVED",
                    is_recursive=is_rec,
                    recursion_chain=list(rec.resolution_chain),
                    is_ecmp_branch=branch_ecmp or len(gateways) > 1,
                    evidence_ids=[col.evidence_id],
                    freshness=fresh,
                    completeness=col.completeness,
                    topology_verified=topo_ok,
                    notes=[f"Next-hop {nh_ip} resolves to registered router '{next_dev}'."],
                )
                stack.append(
                    (next_dev, next_tbl, next_visited, hops + [hop_obj], branch_ecmp or len(gateways) > 1)
                )

        # Aggregate final path state across explored branches
        if not completed_branches:
            return RoutePathEvaluationResult(
                source_device_id=source_device_id,
                destination=destination,
                routing_table=start_table,
                state=PathResultState.PATH_NOT_ENOUGH_EVIDENCE.value,
                confidence=0.0,
                explanation="Unable to evaluate path branches.",
            )

        # Rank branches so healthy reaching branches appear as primary when ECMP/alternatives exist
        state_priority = {
            PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value: 6,
            PathResultState.PATH_INFERRED.value: 5,
            PathResultState.PATH_AMBIGUOUS.value: 4,
            PathResultState.PATH_PARTIAL.value: 3,
            PathResultState.PATH_UNRESOLVED.value: 2,
            PathResultState.PATH_UNREACHABLE.value: 1,
            PathResultState.PATH_NOT_ENOUGH_EVIDENCE.value: 0,
        }
        completed_branches.sort(key=lambda item: state_priority.get(item[0], 0), reverse=True)
        best_branch_state, primary_hops = completed_branches[0]
        all_branch_hops = [br for _, br in completed_branches]

        # Upgrade PATH_INFERRED -> PATH_CONFIRMED_BY_EVIDENCE ONLY when genuinely supported:
        # 1. Not stale, not incomplete, zero contradictions, not ambiguous
        # 2. Every inter-device hop is verified by L1/L2 adjacency OR observed_traceroute_hops matches
        if best_branch_state == PathResultState.PATH_INFERRED.value:
            all_hops_verified = all(h.topology_verified for h in primary_hops)
            obs_verified = bool(observed_traceroute_hops)
            if (
                not stale_found
                and not incomplete_found
                and not contradictions
                and not ambiguous_gateways
                and (all_hops_verified or obs_verified)
            ):
                final_state = PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value
            elif incomplete_found:
                final_state = PathResultState.PATH_PARTIAL.value
            else:
                final_state = PathResultState.PATH_INFERRED.value
        elif ambiguous_gateways:
            final_state = PathResultState.PATH_AMBIGUOUS.value
        else:
            final_state = best_branch_state

        # Compute calibrated confidence
        base_conf_map = {
            PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value: 0.96,
            PathResultState.PATH_INFERRED.value: 0.84,
            PathResultState.PATH_PARTIAL.value: 0.55,
            PathResultState.PATH_AMBIGUOUS.value: 0.45,
            PathResultState.PATH_UNRESOLVED.value: 0.30,
            PathResultState.PATH_UNREACHABLE.value: 0.85 if not incomplete_found else 0.40,
            PathResultState.PATH_NOT_ENOUGH_EVIDENCE.value: 0.0,
        }
        conf = base_conf_map.get(final_state, 0.5)
        if stale_found:
            conf = max(0.2, conf - 0.20)
        if contradictions:
            conf = max(0.2, conf - 0.15)

        # Optional return-path symmetry hypothesis check (from final device back to source_prefix_for_symmetry)
        ret_hypothesis: Optional[Dict[str, Any]] = None
        if source_prefix_for_symmetry and primary_hops:
            terminal_dev = primary_hops[-1].device_id
            if terminal_dev != source_device_id and terminal_dev in collections:
                ret_eval = self.evaluate_path(
                    terminal_dev,
                    source_prefix_for_symmetry,
                    collections,
                    routing_table=start_table,
                    device_ips=device_ips,
                    device_ip_tables=device_ip_tables,
                    verified_adjacencies=verified_adjacencies,
                    down_interfaces=down_interfaces,
                    source_prefix_for_symmetry=None,
                    now=eval_time,
                )
                fwd_devs = [h.device_id for h in primary_hops]
                ret_devs = [h.device_id for h in ret_eval.primary_hops]
                symmetric = (
                    ret_eval.state in (
                        PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value,
                        PathResultState.PATH_INFERRED.value,
                    )
                    and list(reversed(fwd_devs)) == ret_devs
                )
                ret_hypothesis = {
                    "classification": "HYPOTHESIS",
                    "return_state": ret_eval.state,
                    "forward_devices": fwd_devs,
                    "return_devices": ret_devs,
                    "is_symmetric_control_plane": symmetric,
                    "note": (
                        "Return control-plane route traverses the reverse router sequence."
                        if symmetric
                        else "Return control-plane route differs from forward path or is missing (asymmetric or NAT hypothesis; not confirmed without packet/NAT verification)."
                    ),
                }

        hop_chain_str = " -> ".join(h.device_id for h in primary_hops)
        explanation = (
            f"Path evaluation from '{source_device_id}' to '{destination}' (table='{start_table}') "
            f"resulted in {final_state} across [{hop_chain_str}] "
            f"(hops={len(primary_hops)}, ecmp={is_ecmp_any}, stale={stale_found})."
        )

        return RoutePathEvaluationResult(
            source_device_id=source_device_id,
            destination=destination,
            routing_table=start_table,
            state=final_state,
            confidence=conf,
            primary_hops=primary_hops,
            ecmp_branches=all_branch_hops if len(all_branch_hops) > 1 else [],
            loop_detected=loop_found,
            is_ecmp=is_ecmp_any,
            stale_evidence_detected=stale_found,
            incomplete_evidence_detected=incomplete_found,
            contradictions=contradictions,
            missing_intermediate_gateways=missing_gateways,
            ambiguous_gateways=ambiguous_gateways,
            return_path_hypothesis=ret_hypothesis,
            evidence_ids=all_ev_ids,
            explanation=explanation,
        )
