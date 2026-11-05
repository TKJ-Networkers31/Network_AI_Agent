"""
AIRA OS — Cross-Device Route Intelligence & Topology Route Overlay Engine (Networking IV / WP 4.6.5).

Combines CanonicalDevice identity, MultiDeviceRouteCollector evidence, NormalizedRoute,
TopologyEdge/EdgeEvidence, CrossDeviceEvidenceCorrelator, NMS operational status, and
RouteHistoryStore to reconstruct network-wide routing paths, verify inter-router relationships,
detect 12 classes of cross-device routing inconsistencies, and emit non-destructive SVG
route-overlay payloads for TopologyPage and MultiDeviceRouteInspector.

Epistemic & Semantic Guarantees:
- Never infers PHYSICAL_ADJACENCY from subnet overlap alone, shared external default gateway,
  or a single weak ARP observation.
- Never claims asymmetric packet forwarding as a confirmed fact from forward RIB tables alone.
- Never mutates or inserts unsupported physical edges into TopologyEngine.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.network_intelligence.network_models import NormalizedIPAddress
from core.routing.route_analytics import (
    PathResultState,
    RoutePathEvaluationResult,
    RoutePathEvaluator,
    RouteTableAnalyzer,
    _is_route_eligible_unicast,
    build_ip_owner_index,
    evaluate_route_lookup,
)
from core.routing.route_collector import RouteCollectionResult, RouteCompleteness
from core.routing.route_dependency import RouteDependencyAnalyzer
from core.routing.unified_route_parser import NormalizedRoute, _extract_ipv4


class CrossDeviceInconsistencyType(str, Enum):
    MISSING_RETURN_ROUTE = "MISSING_RETURN_ROUTE"
    ONE_WAY_REACHABILITY_HYPOTHESIS = "ONE_WAY_REACHABILITY_HYPOTHESIS"
    INCONSISTENT_ROUTING_TABLES = "INCONSISTENT_ROUTING_TABLES"
    WRONG_NEXT_HOP_HYPOTHESIS = "WRONG_NEXT_HOP_HYPOTHESIS"
    MISSING_UPSTREAM_ROUTE = "MISSING_UPSTREAM_ROUTE"
    UNEXPECTED_DEFAULT_ROUTE = "UNEXPECTED_DEFAULT_ROUTE"
    ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP = "ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP"
    CONFLICTING_DESTINATION_PREFIXES = "CONFLICTING_DESTINATION_PREFIXES"
    INCORRECT_VRF_ASSOCIATION = "INCORRECT_VRF_ASSOCIATION"
    POTENTIAL_ROUTING_LOOP = "POTENTIAL_ROUTING_LOOP"
    INCONSISTENT_ROUTE_STATE_ACROSS_CONNECTED_DEVICES = "INCONSISTENT_ROUTE_STATE_ACROSS_CONNECTED_DEVICES"
    UNEXPECTED_PATH_DIVERGENCE = "UNEXPECTED_PATH_DIVERGENCE"


class OverlaySegmentType(str, Enum):
    INFERRED_ROUTE_PATH = "INFERRED_ROUTE_PATH"
    RECURSIVE_NEXT_HOP_DEPENDENCY = "RECURSIVE_NEXT_HOP_DEPENDENCY"
    ROUTE_UNCERTAINTY = "ROUTE_UNCERTAINTY"


@dataclass
class VerifiedRouteRelationship:
    relationship_id: str
    source_device_id: str
    target_device_id: Optional[str]
    routing_table: str
    dst_prefix: str
    gateway_ip: str
    egress_interface: str
    verification_state: str  # TOPOLOGY_CONFIRMED | GATEWAY_IP_VERIFIED | SUBNET_INFERRED | TOPOLOGY_CONFLICT | UNRESOLVED_EXTERNAL
    is_physical_adjacency: bool
    topology_edge_id: Optional[str] = None
    topology_oper_status: Optional[str] = None
    evidence_sources: List[str] = field(default_factory=list)
    confidence: float = 0.5
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_device_id": self.source_device_id,
            "target_device_id": self.target_device_id,
            "semantic_type": "ROUTED_NEXT_HOP_RELATIONSHIP",
            "is_physical_adjacency": self.is_physical_adjacency,
            "routing_table": self.routing_table,
            "dst_prefix": self.dst_prefix,
            "gateway_ip": self.gateway_ip,
            "egress_interface": self.egress_interface,
            "verification_state": self.verification_state,
            "topology_edge_id": self.topology_edge_id,
            "topology_oper_status": self.topology_oper_status,
            "evidence_sources": list(self.evidence_sources),
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
        }


@dataclass
class CrossDeviceInconsistencyFinding:
    finding_id: str
    inconsistency_type: str  # CrossDeviceInconsistencyType value
    epistemic_class: str  # OBSERVED_FACT | STRONG_HYPOTHESIS | HYPOTHESIS
    affected_devices: List[str]
    routing_table: str
    dst_prefix: str
    gateway: str
    severity: str  # critical | high | medium | low
    confidence: float
    evidence_ids: List[str] = field(default_factory=list)
    explanation: str = ""
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "inconsistency_type": self.inconsistency_type,
            "epistemic_class": self.epistemic_class,
            "affected_devices": list(self.affected_devices),
            "routing_table": self.routing_table,
            "dst_prefix": self.dst_prefix,
            "gateway": self.gateway,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "evidence_ids": list(self.evidence_ids),
            "explanation": self.explanation,
            "limitations": list(self.limitations),
        }


@dataclass
class CrossDeviceRouteIntelligenceReport:
    source_device: Optional[str]
    destination: Optional[str]
    routing_table: str
    devices_evaluated: List[str]
    incomplete_devices: List[str]
    unavailable_devices: List[str]
    verified_relationships: List[VerifiedRouteRelationship]
    inconsistencies: List[CrossDeviceInconsistencyFinding]
    path_evaluation: Optional[Dict[str, Any]]
    topology_overlay: Dict[str, Any]
    historical_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_device": self.source_device,
            "destination": self.destination,
            "routing_table": self.routing_table,
            "devices_evaluated": list(self.devices_evaluated),
            "incomplete_devices": list(self.incomplete_devices),
            "unavailable_devices": list(self.unavailable_devices),
            "verified_relationships_count": len(self.verified_relationships),
            "verified_relationships": [r.to_dict() for r in self.verified_relationships],
            "inconsistencies_count": len(self.inconsistencies),
            "inconsistencies": [i.to_dict() for i in self.inconsistencies],
            "path_evaluation": self.path_evaluation,
            "topology_overlay": self.topology_overlay,
            "historical_context": dict(self.historical_context),
        }


# ---------------------------------------------------------------------------
# Cross-Device Route Intelligence Engine
# ---------------------------------------------------------------------------

class CrossDeviceRouteIntelligenceEngine:
    """
    Correlates multi-device NormalizedRoute tables with CanonicalDevice IPs,
    TopologyEngine edges, NMS operational states, and historical route deltas.
    """

    def __init__(self) -> None:
        from core.network_intelligence.correlation import CrossDeviceEvidenceCorrelator
        self.correlator = CrossDeviceEvidenceCorrelator()
        self.path_evaluator = RoutePathEvaluator()
        self.table_analyzer = RouteTableAnalyzer()
        self.dep_analyzer = RouteDependencyAnalyzer()

    def analyze_network_routing(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        device_ips: Optional[Dict[str, List[str]]] = None,
        topology_edges: Optional[Sequence[Dict[str, Any]]] = None,
        device_oper_states: Optional[Dict[str, str]] = None,
        registered_device_ids: Optional[Sequence[str]] = None,
        source_device: Optional[str] = None,
        destination: Optional[str] = None,
        routing_table: str = "main",
        source_prefix_for_return: Optional[str] = None,
        expected_next_hop_device: Optional[str] = None,
        recent_route_changes: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> CrossDeviceRouteIntelligenceReport:
        edges = list(topology_edges or [])
        oper_states = {k: str(v).lower() for k, v in (device_oper_states or {}).items()}
        ip_owners = build_ip_owner_index(collections, explicit_device_ips=device_ips)

        all_reg = sorted(set(collections.keys()) | set(registered_device_ids or []))
        incomplete_devs: List[str] = []
        unavailable_devs: List[str] = []

        for d_id in all_reg:
            col = collections.get(d_id)
            nms_st = oper_states.get(d_id, "")
            if nms_st in ("offline", "unreachable", "down"):
                unavailable_devs.append(d_id)
            elif col is not None and col.completeness == RouteCompleteness.UNREACHABLE.value:
                unavailable_devs.append(d_id)

            if col is None or col.completeness != RouteCompleteness.COMPLETE.value:
                incomplete_devs.append(d_id)

        # Index confirmed L1/L2 topology adjacencies & interface wiring
        confirmed_adj: Set[Tuple[str, str]] = set()
        edge_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
        port_peer_map: Dict[Tuple[str, str], str] = {}  # (src_dev, port_lower) -> target_dev

        for e in edges:
            s_id = str(e.get("source_node_id") or e.get("source") or "")
            t_id = str(e.get("target_node_id") or e.get("target") or "")
            if not s_id or not t_id:
                continue
            rel_cls = str(e.get("relationship_class") or e.get("link_type") or "").lower()
            conf_tier = str(e.get("confidence_tier") or e.get("verification_status") or "").lower()
            is_conf_l1_l2 = (
                ("physical" in rel_cls or "layer2" in rel_cls or rel_cls == "ethernet")
                and conf_tier in ("confirmed", "high", "manual")
            )
            edge_by_pair[(s_id, t_id)] = e
            edge_by_pair.setdefault((t_id, s_id), e)
            if is_conf_l1_l2:
                confirmed_adj.add((s_id, t_id))
                confirmed_adj.add((t_id, s_id))
                s_port = str(e.get("source_interface") or e.get("source_port") or "").strip().lower()
                t_port = str(e.get("target_interface") or e.get("target_port") or "").strip().lower()
                if s_port:
                    port_peer_map[(s_id, s_port)] = t_id
                if t_port:
                    port_peer_map[(t_id, t_port)] = s_id

        # 1. Verify cross-device route relationships (Section 9.1 & 9.2)
        verified_rels, topology_conflicts = self._verify_relationships(
            collections,
            ip_owners=ip_owners,
            confirmed_adj=confirmed_adj,
            edge_by_pair=edge_by_pair,
            port_peer_map=port_peer_map,
        )

        # 2. Reconstruct multi-device path when source_device + destination are given (Section 9.3)
        path_eval_obj: Optional[RoutePathEvaluationResult] = None
        if source_device and destination:
            # Infer source LAN prefix if not explicitly provided
            src_ret_pfx = source_prefix_for_return
            if not src_ret_pfx and source_device in collections:
                for r in collections[source_device].routes:
                    if r.connect and (r.routing_table or "main") == routing_table:
                        # Prefer a non-transit LAN connected subnet if present
                        src_ret_pfx = r.dst_prefix
                        break

            path_eval_obj = self.path_evaluator.evaluate_path(
                source_device,
                destination,
                collections,
                routing_table=routing_table,
                device_ips=device_ips,
                verified_adjacencies=confirmed_adj,
                source_prefix_for_symmetry=src_ret_pfx,
            )

        # 3. Detect all 12 classes of network-wide routing inconsistencies (Section 9.4)
        inconsistencies = self._detect_inconsistencies(
            collections,
            ip_owners=ip_owners,
            unavailable_devs=set(unavailable_devs),
            edge_by_pair=edge_by_pair,
            topology_conflicts=topology_conflicts,
            path_eval=path_eval_obj,
            source_device=source_device,
            destination=destination,
            routing_table=routing_table,
            source_prefix_for_return=source_prefix_for_return,
            expected_next_hop_device=expected_next_hop_device,
        )

        # 4. Build non-destructive Topology UI Route Overlay (Section 9.5 & 9.6)
        overlay = self.build_topology_route_overlay(
            collections=collections,
            verified_relationships=verified_rels,
            path_eval=path_eval_obj,
            inconsistencies=inconsistencies,
            unavailable_devs=set(unavailable_devs),
            incomplete_devs=set(incomplete_devs),
            routing_table=routing_table,
            destination=destination,
        )

        hist_ctx: Dict[str, Any] = {
            "recent_changes_count": len(recent_route_changes or []),
            "recent_changes": list(recent_route_changes or [])[:25],
        }

        return CrossDeviceRouteIntelligenceReport(
            source_device=source_device,
            destination=destination,
            routing_table=routing_table,
            devices_evaluated=sorted(collections.keys()),
            incomplete_devices=incomplete_devs,
            unavailable_devices=unavailable_devs,
            verified_relationships=verified_rels,
            inconsistencies=inconsistencies,
            path_evaluation=path_eval_obj.to_dict() if path_eval_obj else None,
            topology_overlay=overlay,
            historical_context=hist_ctx,
        )

    def _verify_relationships(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        ip_owners: Dict[str, List[str]],
        confirmed_adj: Set[Tuple[str, str]],
        edge_by_pair: Dict[Tuple[str, str], Dict[str, Any]],
        port_peer_map: Dict[Tuple[str, str], str],
    ) -> Tuple[List[VerifiedRouteRelationship], List[Dict[str, Any]]]:
        """
        Verifies routed next-hop relationships using CrossDeviceEvidenceCorrelator
        and TopologyEngine edges while enforcing Section 9.2 anti-fabrication rules:
        - Never promotes subnet overlap alone to physical adjacency.
        - Never infers direct router-to-router connectivity from a shared external default gateway.
        - Explicitly detects conflicts between route egress port/next-hop and TopologyEdge wiring.
        """
        verified: List[VerifiedRouteRelationship] = []
        conflicts: List[Dict[str, Any]] = []

        # Build NormalizedIPAddress lists per device for CrossDeviceEvidenceCorrelator reuse
        norm_ips_by_dev: Dict[str, List[NormalizedIPAddress]] = {}
        for dev_id, col in collections.items():
            ips: List[NormalizedIPAddress] = []
            for r in col.routes:
                if r.connect and r.pref_src and "/" in r.dst_prefix:
                    plen = int(r.dst_prefix.split("/")[1])
                    ips.append(
                        NormalizedIPAddress(
                            device_id=dev_id,
                            address=r.pref_src,
                            prefix_len=plen,
                            interface_name=r.interface_name or r.gateway or "",
                        )
                    )
            for ip_str, owners in ip_owners.items():
                if dev_id in owners and all(x.address != ip_str for x in ips):
                    ips.append(NormalizedIPAddress(device_id=dev_id, address=ip_str, prefix_len=32, interface_name=""))
            norm_ips_by_dev[dev_id] = ips

        for src_id, col in collections.items():
            if not col.routes:
                continue
            by_table: Dict[str, List[NormalizedRoute]] = {}
            for r in col.routes:
                by_table.setdefault(r.routing_table or "main", []).append(r)

            # Reuse CrossDeviceEvidenceCorrelator for direct/recursive target IP matches
            route_dicts = [r.to_dict() for r in col.routes]
            correlator_hits: Set[Tuple[str, str]] = set()
            for peer_id, peer_ips in norm_ips_by_dev.items():
                if peer_id == src_id:
                    continue
                for rel in self.correlator.correlate_all_routed_nexthops(src_id, peer_id, route_dicts, peer_ips):
                    correlator_hits.add((src_id, rel.target_device_id))

            for r in col.routes:
                if not _is_route_eligible_unicast(r) or r.connect:
                    continue
                tbl = r.routing_table or "main"
                dep_res = self.dep_analyzer.resolve_single_route(
                    src_id, r, by_table.get(tbl, []), ip_owner_map=ip_owners, evidence_id=col.evidence_id
                )
                eff_gws = dep_res.resolved_immediate_gateways or [
                    _extract_ipv4(g) for g in (r.gateways or [r.gateway]) if _extract_ipv4(g)
                ]
                egress_if = (
                    dep_res.resolved_egress_interfaces[0]
                    if dep_res.resolved_egress_interfaces
                    else (r.interface_name or "")
                )

                for gw_ip in eff_gws:
                    if not gw_ip:
                        continue
                    owners = [o for o in ip_owners.get(gw_ip, []) if o != src_id]
                    if not owners:
                        # External / unregistered gateway (note: shared default gateway across two routers
                        # remains UNRESOLVED_EXTERNAL and NEVER creates a router-to-router link!)
                        verified.append(
                            VerifiedRouteRelationship(
                                relationship_id=f"vrel_{uuid.uuid4().hex[:8]}",
                                source_device_id=src_id,
                                target_device_id=None,
                                routing_table=tbl,
                                dst_prefix=r.dst_prefix,
                                gateway_ip=gw_ip,
                                egress_interface=egress_if,
                                verification_state="UNRESOLVED_EXTERNAL",
                                is_physical_adjacency=False,
                                evidence_sources=[col.evidence_id],
                                confidence=0.45,
                                explanation=(
                                    f"Gateway {gw_ip} on '{src_id}' is outside registered CanonicalDevice inventory."
                                ),
                            )
                        )
                        continue

                    for tgt_id in owners:
                        topo_edge = edge_by_pair.get((src_id, tgt_id))
                        topo_oper = str(topo_edge.get("oper_status") or topo_edge.get("status") or "up") if topo_edge else None
                        topo_id = str(topo_edge.get("id")) if topo_edge and topo_edge.get("id") else None

                        # Check if confirmed L1/L2 port wiring contradicts the routed next-hop target!
                        wired_peer = (
                            port_peer_map.get((src_id, egress_if.lower()))
                            if egress_if
                            else None
                        )
                        if wired_peer and wired_peer != tgt_id:
                            conflicts.append({
                                "source_device_id": src_id,
                                "expected_route_peer": tgt_id,
                                "actual_topology_peer": wired_peer,
                                "egress_interface": egress_if,
                                "dst_prefix": r.dst_prefix,
                                "gateway_ip": gw_ip,
                                "routing_table": tbl,
                                "evidence_id": col.evidence_id,
                            })
                            v_state = "TOPOLOGY_CONFLICT"
                            conf = 0.35
                            expl = (
                                f"Conflict: Route {r.dst_prefix} on '{src_id}' egresses '{egress_if}' toward "
                                f"'{tgt_id}' ({gw_ip}), but confirmed TopologyEdge wires '{egress_if}' to '{wired_peer}'."
                            )
                        elif (src_id, tgt_id) in confirmed_adj:
                            v_state = "TOPOLOGY_CONFIRMED"
                            conf = 0.96
                            expl = (
                                f"Gateway {gw_ip} on '{tgt_id}' verified by both RIB next-hop and confirmed topology adjacency."
                            )
                        elif (src_id, tgt_id) in correlator_hits:
                            v_state = "GATEWAY_IP_VERIFIED"
                            conf = 0.84
                            expl = (
                                f"Gateway {gw_ip} matches registered interface IP on '{tgt_id}' (routed L3 relationship; "
                                "physical cabling not assumed without L1/L2 neighbor evidence)."
                            )
                        else:
                            v_state = "SUBNET_INFERRED"
                            conf = 0.65
                            expl = f"Next-hop relationship toward '{tgt_id}' inferred from subnet/IP ownership."

                        ev_srcs = [col.evidence_id]
                        if tgt_id in collections:
                            ev_srcs.append(collections[tgt_id].evidence_id)
                        if topo_id:
                            ev_srcs.append(f"topo_edge:{topo_id}")

                        verified.append(
                            VerifiedRouteRelationship(
                                relationship_id=f"vrel_{uuid.uuid4().hex[:8]}",
                                source_device_id=src_id,
                                target_device_id=tgt_id,
                                routing_table=tbl,
                                dst_prefix=r.dst_prefix,
                                gateway_ip=gw_ip,
                                egress_interface=egress_if,
                                verification_state=v_state,
                                is_physical_adjacency=(v_state == "TOPOLOGY_CONFIRMED"),
                                topology_edge_id=topo_id,
                                topology_oper_status=topo_oper,
                                evidence_sources=ev_srcs,
                                confidence=conf,
                                explanation=expl,
                            )
                        )

        return verified, conflicts

    def _detect_inconsistencies(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        ip_owners: Dict[str, List[str]],
        unavailable_devs: Set[str],
        edge_by_pair: Dict[Tuple[str, str], Dict[str, Any]],
        topology_conflicts: Sequence[Dict[str, Any]],
        path_eval: Optional[RoutePathEvaluationResult],
        source_device: Optional[str],
        destination: Optional[str],
        routing_table: str,
        source_prefix_for_return: Optional[str],
        expected_next_hop_device: Optional[str],
    ) -> List[CrossDeviceInconsistencyFinding]:
        findings: List[CrossDeviceInconsistencyFinding] = []

        def _emit(
            itype: CrossDeviceInconsistencyType,
            epistemic: str,
            devs: Sequence[str],
            tbl: str,
            pfx: str,
            gw: str,
            sev: str,
            conf: float,
            evs: Sequence[str],
            expl: str,
            limits: Optional[Sequence[str]] = None,
        ) -> None:
            findings.append(
                CrossDeviceInconsistencyFinding(
                    finding_id=f"xdev_{uuid.uuid4().hex[:8]}",
                    inconsistency_type=itype.value,
                    epistemic_class=epistemic,
                    affected_devices=list(dict.fromkeys(devs)),
                    routing_table=tbl,
                    dst_prefix=pfx,
                    gateway=gw,
                    severity=sev,
                    confidence=conf,
                    evidence_ids=list(dict.fromkeys(e for e in evs if e)),
                    explanation=expl,
                    limitations=list(limits or [
                        "Evaluated from read-only RIB control-plane snapshots; policy-routing mangle rules are not simulated."
                    ]),
                )
            )

        # 1 & 2: MISSING_RETURN_ROUTE & ONE_WAY_REACHABILITY_HYPOTHESIS
        if path_eval is not None and path_eval.primary_hops:
            last_hop = path_eval.primary_hops[-1]
            term_dev = last_hop.device_id
            ret_target = source_prefix_for_return
            if not ret_target and source_device and source_device in collections:
                # Pick a non-shared LAN subnet on source_device
                for r in collections[source_device].routes:
                    if r.connect and (r.routing_table or "main") == routing_table:
                        # Check if terminal device also directly connects to this subnet
                        term_connects = term_dev in collections and any(
                            tr.connect and tr.dst_prefix == r.dst_prefix
                            for tr in collections[term_dev].routes
                        )
                        if not term_connects:
                            ret_target = r.dst_prefix
                            break

            if (
                ret_target
                and source_device
                and term_dev != source_device
                and term_dev in collections
                and path_eval.state in (
                    PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value,
                    PathResultState.PATH_INFERRED.value,
                )
            ):
                ret_path = self.path_evaluator.evaluate_path(
                    term_dev,
                    ret_target.split("/")[0],
                    collections,
                    routing_table=routing_table,
                )
                if ret_path.state in (
                    PathResultState.PATH_UNREACHABLE.value,
                    PathResultState.PATH_UNRESOLVED.value,
                ):
                    evs = [
                        collections[source_device].evidence_id,
                        collections[term_dev].evidence_id,
                    ]
                    _emit(
                        CrossDeviceInconsistencyType.MISSING_RETURN_ROUTE,
                        "STRONG_HYPOTHESIS",
                        [source_device, term_dev],
                        routing_table,
                        ret_target,
                        last_hop.gateway or "",
                        "high",
                        0.86,
                        evs,
                        f"Forward route from '{source_device}' reaches '{term_dev}' for {destination}, "
                        f"but '{term_dev}' has no active return route toward source network {ret_target}.",
                    )
                    _emit(
                        CrossDeviceInconsistencyType.ONE_WAY_REACHABILITY_HYPOTHESIS,
                        "HYPOTHESIS",
                        [source_device, term_dev],
                        routing_table,
                        destination or ret_target,
                        last_hop.gateway or "",
                        "medium",
                        0.74,
                        evs,
                        f"Hypothesis: One-way reachability between '{source_device}' ({ret_target}) and '{term_dev}' "
                        "(NAT masquerade on intermediate routers could still permit return traffic; not a confirmed packet failure).",
                        limits=[
                            "Asymmetric/one-way routing is reported strictly as a hypothesis because outbound NAT/masquerade may rewrite source IPs."
                        ],
                    )
                else:
                    fwd_devs = [h.device_id for h in path_eval.primary_hops]
                    rev_devs = list(reversed([h.device_id for h in ret_path.primary_hops]))
                    if len(fwd_devs) > 1 and len(rev_devs) > 1 and set(fwd_devs) != set(rev_devs):
                        _emit(
                            CrossDeviceInconsistencyType.ONE_WAY_REACHABILITY_HYPOTHESIS,
                            "HYPOTHESIS",
                            fwd_devs + rev_devs,
                            routing_table,
                            destination or ret_target,
                            "",
                            "low",
                            0.65,
                            [collections[source_device].evidence_id, collections[term_dev].evidence_id],
                            f"Asymmetric forward ({' -> '.join(fwd_devs)}) vs return ({' -> '.join([h.device_id for h in ret_path.primary_hops])}) "
                            "RIB path hypothesis detected (never marked as confirmed asymmetric traffic without packet capture).",
                        )

        # 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 across all collected routers
        conn_prefixes: Dict[Tuple[str, str], List[str]] = {}
        tables_by_prefix: Dict[str, Dict[str, Set[str]]] = {}  # prefix -> {table -> {dev_ids}}

        for dev_id, col in collections.items():
            if not col.routes:
                continue
            by_tbl: Dict[str, List[NormalizedRoute]] = {}
            for r in col.routes:
                tbl = r.routing_table or "main"
                by_tbl.setdefault(tbl, []).append(r)
                if not r.is_default_route() and not r.connect and r.active and not r.disabled:
                    tables_by_prefix.setdefault(r.dst_prefix, {}).setdefault(tbl, set()).add(dev_id)
                if r.connect and r.active and not r.disabled:
                    # Track /32 or non-point-to-point duplicate subnet claims
                    conn_prefixes.setdefault((tbl, r.dst_prefix), []).append(dev_id)

            # Check unexpected default routes (multiple non-ECMP conflicting active defaults or default to unreachable)
            for tbl, trs in by_tbl.items():
                active_defs = [r for r in trs if r.is_default_route() and _is_route_eligible_unicast(r)]
                distinct_dists = {r.distance for r in active_defs}
                if len(distinct_dists) > 1:
                    _emit(
                        CrossDeviceInconsistencyType.UNEXPECTED_DEFAULT_ROUTE,
                        "OBSERVED_FACT",
                        [dev_id],
                        tbl,
                        "0.0.0.0/0",
                        ",".join(r.gateway for r in active_defs),
                        "medium",
                        0.88,
                        [col.evidence_id],
                        f"Device '{dev_id}' has multiple active default routes with conflicting distances ({sorted(distinct_dists)}).",
                    )

                for r in trs:
                    if not _is_route_eligible_unicast(r) or r.connect:
                        continue
                    dep = self.dep_analyzer.resolve_single_route(
                        dev_id, r, trs, ip_owner_map=ip_owners, evidence_id=col.evidence_id
                    )

                    # 4: WRONG_NEXT_HOP_HYPOTHESIS (explicit expectation or pointing away from owner of destination)
                    if (
                        expected_next_hop_device
                        and dev_id == source_device
                        and destination
                        and r.network is not None
                    ):
                        try:
                            t_ip = ipaddress.ip_address(destination.split("/")[0])
                            if t_ip in r.network and dep.upstream_device_ids and expected_next_hop_device not in dep.upstream_device_ids:
                                _emit(
                                    CrossDeviceInconsistencyType.WRONG_NEXT_HOP_HYPOTHESIS,
                                    "STRONG_HYPOTHESIS",
                                    [dev_id, *dep.upstream_device_ids],
                                    tbl,
                                    r.dst_prefix,
                                    r.gateway,
                                    "high",
                                    0.85,
                                    [col.evidence_id],
                                    f"Route {r.dst_prefix} on '{dev_id}' forwards to {dep.upstream_device_ids} ({r.gateway}) "
                                    f"instead of expected next-hop device '{expected_next_hop_device}'.",
                                )
                        except Exception:
                            pass

                    for up_dev in dep.upstream_device_ids:
                        # 7: ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP
                        pair_edge = edge_by_pair.get((dev_id, up_dev))
                        edge_down = pair_edge is not None and str(pair_edge.get("oper_status") or pair_edge.get("status") or "up").lower() == "down"
                        if up_dev in unavailable_devs or edge_down:
                            _emit(
                                CrossDeviceInconsistencyType.ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP,
                                "STRONG_HYPOTHESIS",
                                [dev_id, up_dev],
                                tbl,
                                r.dst_prefix,
                                r.gateway,
                                "critical",
                                0.91,
                                [col.evidence_id],
                                f"Active route {r.dst_prefix} on '{dev_id}' points to next-hop '{up_dev}' ({r.gateway}), "
                                f"which is currently {'unavailable/offline' if up_dev in unavailable_devs else 'on a DOWN link'}.",
                            )

                        # Check upstream device table in same VRF
                        if up_dev in collections and collections[up_dev].completeness == RouteCompleteness.COMPLETE.value:
                            up_col = collections[up_dev]
                            test_ip = (
                                "8.8.8.8"
                                if r.is_default_route()
                                else str(ipaddress.ip_network(r.dst_prefix, strict=False).network_address)
                            )
                            up_lpm = evaluate_route_lookup(
                                up_col.routes, test_ip, device_id=up_dev, routing_table=tbl
                            )
                            # Check if upstream holds an exact/more-specific route in a DIFFERENT VRF while
                            # `tbl` either lacks a match or only falls back to 0.0.0.0/0!
                            best_in_tbl_only_default = (
                                not r.is_default_route()
                                and bool(up_lpm.calculated_best_candidates)
                                and all(c.get("dst_prefix") == "0.0.0.0/0" for c in up_lpm.calculated_best_candidates)
                            )
                            if not up_lpm.calculated_best_candidates or best_in_tbl_only_default:
                                # Check if upstream has the route in a DIFFERENT VRF! (9: INCORRECT_VRF_ASSOCIATION)
                                other_vrf_hit = [
                                    ur.routing_table
                                    for ur in up_col.routes
                                    if (ur.routing_table or "main") != tbl
                                    and _is_route_eligible_unicast(ur)
                                    and not ur.is_default_route()
                                    and ur.network is not None
                                    and ipaddress.ip_address(test_ip) in ur.network
                                ]
                                if other_vrf_hit:
                                    _emit(
                                        CrossDeviceInconsistencyType.INCORRECT_VRF_ASSOCIATION,
                                        "STRONG_HYPOTHESIS",
                                        [dev_id, up_dev],
                                        tbl,
                                        r.dst_prefix,
                                        r.gateway,
                                        "high",
                                        0.88,
                                        [col.evidence_id, up_col.evidence_id],
                                        f"VRF mismatch: '{dev_id}' forwards {r.dst_prefix} in table '{tbl}' to '{up_dev}', "
                                        f"but '{up_dev}' holds matching non-default routes only in table(s) {sorted(set(other_vrf_hit))}.",
                                    )
                                elif not up_lpm.calculated_best_candidates:
                                    # 5: MISSING_UPSTREAM_ROUTE & 4: WRONG_NEXT_HOP_HYPOTHESIS (dead-end neighbor when another router owns prefix)
                                    other_owners = [
                                        oid for oid, ocol in collections.items()
                                        if oid not in (dev_id, up_dev)
                                        and any(oroute.connect and oroute.dst_prefix == r.dst_prefix for oroute in ocol.routes)
                                    ]
                                    if other_owners:
                                        _emit(
                                            CrossDeviceInconsistencyType.WRONG_NEXT_HOP_HYPOTHESIS,
                                            "STRONG_HYPOTHESIS",
                                            [dev_id, up_dev, *other_owners],
                                            tbl,
                                            r.dst_prefix,
                                            r.gateway,
                                            "high",
                                            0.87,
                                            [col.evidence_id, up_col.evidence_id],
                                            f"Wrong next-hop hypothesis: '{dev_id}' sends {r.dst_prefix} to '{up_dev}' (which lacks a route), "
                                            f"whereas {other_owners} directly owns {r.dst_prefix}.",
                                        )
                                    _emit(
                                        CrossDeviceInconsistencyType.MISSING_UPSTREAM_ROUTE,
                                        "OBSERVED_FACT",
                                        [dev_id, up_dev],
                                        tbl,
                                        r.dst_prefix,
                                        r.gateway,
                                        "high",
                                        0.92,
                                        [col.evidence_id, up_col.evidence_id],
                                        f"Downstream router '{dev_id}' forwards {r.dst_prefix} to upstream '{up_dev}', "
                                        f"but '{up_dev}' has no eligible route covering {r.dst_prefix} in table '{tbl}'.",
                                    )
                                    _emit(
                                        CrossDeviceInconsistencyType.INCONSISTENT_ROUTING_TABLES,
                                        "OBSERVED_FACT",
                                        [dev_id, up_dev],
                                        tbl,
                                        r.dst_prefix,
                                        r.gateway,
                                        "medium",
                                        0.89,
                                        [col.evidence_id, up_col.evidence_id],
                                        f"Inconsistent RIB state between '{dev_id}' and next-hop '{up_dev}' for {r.dst_prefix}.",
                                    )
                            else:
                                # Check 10: POTENTIAL_ROUTING_LOOP (up_dev points right back to dev_id for same prefix!)
                                for best_up in up_lpm.calculated_best_candidates:
                                    up_gw = _extract_ipv4(str(best_up.get("gateway") or ""))
                                    if up_gw and dev_id in ip_owners.get(up_gw, []):
                                        _emit(
                                            CrossDeviceInconsistencyType.POTENTIAL_ROUTING_LOOP,
                                            "OBSERVED_FACT",
                                            [dev_id, up_dev],
                                            tbl,
                                            r.dst_prefix,
                                            r.gateway,
                                            "critical",
                                            0.96,
                                            [col.evidence_id, up_col.evidence_id],
                                            f"Routing loop detected: '{dev_id}' forwards {r.dst_prefix} to '{up_dev}' ({r.gateway}) "
                                            f"and '{up_dev}' forwards {best_up.get('dst_prefix')} back to '{dev_id}' ({up_gw}).",
                                        )

                            # 11: INCONSISTENT_ROUTE_STATE_ACROSS_CONNECTED_DEVICES (upstream has matching route disabled/unreachable)
                            disabled_on_peer = [
                                ur for ur in up_col.routes
                                if (ur.routing_table or "main") == tbl
                                and ur.dst_prefix == r.dst_prefix
                                and (ur.disabled or not ur.active or ur.unreachable)
                            ]
                            if disabled_on_peer and not up_lpm.calculated_best_candidates:
                                _emit(
                                    CrossDeviceInconsistencyType.INCONSISTENT_ROUTE_STATE_ACROSS_CONNECTED_DEVICES,
                                    "OBSERVED_FACT",
                                    [dev_id, up_dev],
                                    tbl,
                                    r.dst_prefix,
                                    r.gateway,
                                    "high",
                                    0.90,
                                    [col.evidence_id, up_col.evidence_id],
                                    f"Route {r.dst_prefix} is ACTIVE on '{dev_id}' toward '{up_dev}', "
                                    f"but '{up_dev}' has {r.dst_prefix} marked inactive/disabled/unreachable.",
                                )

        # 8: CONFLICTING_DESTINATION_PREFIXES (3+ devices claiming identical /30 or 2+ devices claiming same /32 loopback)
        for (tbl, pfx), owners in conn_prefixes.items():
            uniq_owners = sorted(set(owners))
            plen = int(pfx.split("/")[1]) if "/" in pfx else 32
            if (plen == 32 and len(uniq_owners) > 1) or (plen == 30 and len(uniq_owners) > 2):
                _emit(
                    CrossDeviceInconsistencyType.CONFLICTING_DESTINATION_PREFIXES,
                    "OBSERVED_FACT",
                    uniq_owners,
                    tbl,
                    pfx,
                    "",
                    "high",
                    0.90,
                    [collections[o].evidence_id for o in uniq_owners if o in collections],
                    f"Conflicting connected prefix {pfx} (/{plen}) claimed simultaneously by {uniq_owners} in table '{tbl}'.",
                )

        # 9: Cross-device VRF table split for same non-connected destination prefix
        for pfx, tbl_map in tables_by_prefix.items():
            if len(tbl_map) > 1:
                all_devs = sorted({d for ds in tbl_map.values() for d in ds})
                if len(all_devs) > 1:
                    _emit(
                        CrossDeviceInconsistencyType.INCORRECT_VRF_ASSOCIATION,
                        "HYPOTHESIS",
                        all_devs,
                        ",".join(sorted(tbl_map.keys())),
                        pfx,
                        "",
                        "medium",
                        0.72,
                        [collections[d].evidence_id for d in all_devs if d in collections],
                        f"Prefix {pfx} is placed in different routing tables across routers ({ {t: sorted(ds) for t, ds in tbl_map.items()} }); "
                        "verify intentional VRF separation vs VRF table mismatch.",
                    )

        # 12: UNEXPECTED_PATH_DIVERGENCE (Topology conflict or ECMP branch divergence)
        for tc in topology_conflicts:
            _emit(
                CrossDeviceInconsistencyType.UNEXPECTED_PATH_DIVERGENCE,
                "STRONG_HYPOTHESIS",
                [tc["source_device_id"], tc["expected_route_peer"], tc["actual_topology_peer"]],
                tc["routing_table"],
                tc["dst_prefix"],
                tc["gateway_ip"],
                "high",
                0.88,
                [tc["evidence_id"]],
                f"Topology vs Routing conflict on '{tc['source_device_id']}' port '{tc['egress_interface']}': "
                f"RIB expects next-hop '{tc['expected_route_peer']}' ({tc['gateway_ip']}), "
                f"but confirmed TopologyEdge connects '{tc['egress_interface']}' to '{tc['actual_topology_peer']}'.",
            )

        if path_eval is not None and len(path_eval.ecmp_branches) > 1:
            branch_terminals = {
                b[-1].device_id for b in path_eval.ecmp_branches if b
            }
            if len(branch_terminals) > 1 and path_eval.state in (
                PathResultState.PATH_PARTIAL.value,
                PathResultState.PATH_AMBIGUOUS.value,
            ):
                _emit(
                    CrossDeviceInconsistencyType.UNEXPECTED_PATH_DIVERGENCE,
                    "HYPOTHESIS",
                    sorted(branch_terminals),
                    routing_table,
                    destination or "",
                    "",
                    "medium",
                    0.75,
                    path_eval.evidence_ids,
                    f"ECMP branches toward {destination} diverge to distinct terminal states/devices {sorted(branch_terminals)}.",
                )

        if path_eval is not None and path_eval.loop_detected:
            loop_devs = [h.device_id for h in path_eval.primary_hops]
            if not any(f.inconsistency_type == CrossDeviceInconsistencyType.POTENTIAL_ROUTING_LOOP.value for f in findings):
                _emit(
                    CrossDeviceInconsistencyType.POTENTIAL_ROUTING_LOOP,
                    "OBSERVED_FACT",
                    loop_devs,
                    routing_table,
                    destination or "",
                    "",
                    "critical",
                    0.95,
                    path_eval.evidence_ids,
                    f"Multi-router forwarding loop detected along path {' -> '.join(loop_devs)}.",
                )

        return findings

    def build_topology_route_overlay(
        self,
        *,
        collections: Dict[str, RouteCollectionResult],
        verified_relationships: Sequence[VerifiedRouteRelationship],
        path_eval: Optional[RoutePathEvaluationResult],
        inconsistencies: Sequence[CrossDeviceInconsistencyFinding],
        unavailable_devs: Set[str],
        incomplete_devs: Set[str],
        routing_table: str = "main",
        destination: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates a focused, non-destructive SVG route overlay payload for `TopologyPage`
        and `MultiDeviceRouteInspector` (Sections 9.5 & 9.6).
        Never mutates physical/L2 topology edges.
        """
        segments: List[Dict[str, Any]] = []
        conflict_pairs = {
            (r.source_device_id, r.target_device_id)
            for r in verified_relationships
            if r.verification_state == "TOPOLOGY_CONFLICT" and r.target_device_id
        }

        if path_eval is not None and path_eval.primary_hops:
            hop_sources: List[Tuple[str, Any]] = []
            if len(path_eval.ecmp_branches) > 1:
                for b_idx, branch in enumerate(path_eval.ecmp_branches, start=1):
                    for h in branch:
                        hop_sources.append((f"ecmp_{b_idx}", h))
            else:
                for h in path_eval.primary_hops:
                    hop_sources.append(("primary", h))

            for branch_id, hop in hop_sources:
                src_id = hop.device_id
                tgt_id = hop.next_device_id
                is_terminal = hop.hop_state == "DIRECT_CONNECTED"
                is_uncertain = (
                    not tgt_id
                    or tgt_id in unavailable_devs
                    or tgt_id in incomplete_devs
                    or (src_id, tgt_id) in conflict_pairs
                    or hop.hop_state in ("EXTERNAL_OR_MISSING_ROUTER", "UNRESOLVED_GATEWAY", "NO_ROUTE", "LOOP_DETECTED", "AMBIGUOUS_NEXT_HOP", "INCOMPLETE_EVIDENCE")
                )
                if is_uncertain and not is_terminal:
                    seg_type = OverlaySegmentType.ROUTE_UNCERTAINTY.value
                elif hop.is_recursive:
                    seg_type = OverlaySegmentType.RECURSIVE_NEXT_HOP_DEPENDENCY.value
                else:
                    seg_type = OverlaySegmentType.INFERRED_ROUTE_PATH.value

                src_col = collections.get(src_id)
                comp = src_col.completeness if src_col else hop.completeness
                confirmed_adj_flag = (
                    (src_id, tgt_id) not in conflict_pairs
                    and (
                        hop.topology_verified
                        or any(
                            vr.source_device_id == src_id
                            and vr.target_device_id == tgt_id
                            and vr.verification_state == "TOPOLOGY_CONFIRMED"
                            for vr in verified_relationships
                        )
                    )
                )
                hop_conf = 0.96 if confirmed_adj_flag else (0.52 if (is_uncertain and not is_terminal) else path_eval.confidence)

                segments.append({
                    "segment_id": f"ovseg_{branch_id}_{hop.hop_index}_{src_id}",
                    "overlay_segment_type": seg_type,
                    "is_physical_link": False,
                    "hop_index": hop.hop_index,
                    "branch_id": branch_id,
                    "source_device_id": src_id,
                    "target_device_id": tgt_id,
                    "destination_prefix": hop.matched_prefix or (destination or ""),
                    "routing_table": hop.routing_table or routing_table,
                    "selected_route_candidate": {
                        "dst_prefix": hop.matched_prefix,
                        "protocol": hop.protocol,
                        "gateway": hop.gateway,
                        "immediate_gateway": hop.immediate_gateway or hop.resolved_gateway_ip,
                        "egress_interface": hop.egress_interface,
                    },
                    "gateway": hop.gateway or "",
                    "immediate_gateway": hop.immediate_gateway or hop.resolved_gateway_ip or "",
                    "egress_interface": hop.egress_interface or "",
                    "next_device_hypothesis": tgt_id or (
                        "CONNECTED_DESTINATION" if is_terminal else "UNRESOLVED_OR_EXTERNAL_ROUTER"
                    ),
                    "recursive_dependency": list(hop.recursion_chain),
                    "is_recursive": hop.is_recursive,
                    "is_terminal": is_terminal,
                    "confirmed_by_topology_adjacency": confirmed_adj_flag,
                    "evidence_sources": list(hop.evidence_ids),
                    "confidence": round(hop_conf, 3),
                    "completeness": comp,
                    "unresolved_info": list(hop.notes),
                })
        else:
            # Focused summary mode when no single destination path is requested:
            # emit deduplicated inter-router next-hop summary relationships (bounded to 100!)
            seen_pairs: Set[Tuple[str, Optional[str], str]] = set()
            for vr in verified_relationships:
                key = (vr.source_device_id, vr.target_device_id, vr.routing_table)
                if key in seen_pairs or len(segments) >= 100:
                    continue
                seen_pairs.add(key)
                is_unc = (
                    vr.verification_state in ("TOPOLOGY_CONFLICT", "UNRESOLVED_EXTERNAL")
                    or (vr.target_device_id in unavailable_devs if vr.target_device_id else True)
                )
                seg_type = (
                    OverlaySegmentType.ROUTE_UNCERTAINTY.value
                    if is_unc
                    else OverlaySegmentType.INFERRED_ROUTE_PATH.value
                )
                src_col = collections.get(vr.source_device_id)
                segments.append({
                    "segment_id": vr.relationship_id,
                    "overlay_segment_type": seg_type,
                    "is_physical_link": False,
                    "hop_index": 1,
                    "branch_id": "summary",
                    "source_device_id": vr.source_device_id,
                    "target_device_id": vr.target_device_id,
                    "destination_prefix": vr.dst_prefix,
                    "routing_table": vr.routing_table,
                    "selected_route_candidate": {
                        "dst_prefix": vr.dst_prefix,
                        "gateway": vr.gateway_ip,
                        "egress_interface": vr.egress_interface,
                    },
                    "gateway": vr.gateway_ip,
                    "immediate_gateway": vr.gateway_ip,
                    "egress_interface": vr.egress_interface,
                    "next_device_hypothesis": vr.target_device_id or "UNRESOLVED_EXTERNAL",
                    "recursive_dependency": [],
                    "is_recursive": False,
                    "is_terminal": False,
                    "confirmed_by_topology_adjacency": vr.verification_state == "TOPOLOGY_CONFIRMED",
                    "evidence_sources": list(vr.evidence_sources),
                    "confidence": vr.confidence,
                    "completeness": src_col.completeness if src_col else "MISSING",
                    "unresolved_info": (
                        [vr.explanation] if is_unc else []
                    ),
                })

        return {
            "semantic_domain": "TOPOLOGY_ROUTE_OVERLAY",
            "mutates_physical_topology": False,
            "routing_table": routing_table,
            "destination": destination,
            "path_state": path_eval.state if path_eval else "SUMMARY_OVERLAY",
            "path_confidence": round(path_eval.confidence, 3) if path_eval else None,
            "segments_count": len(segments),
            "segments": segments,
            "inconsistencies_count": len(inconsistencies),
        }
