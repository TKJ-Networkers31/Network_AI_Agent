"""
AIRA OS — Route Dependency & Recursive Failure Propagation Engine (Networking IV / WP 4.6.3).

Models how routing decisions depend on other routes, interfaces, gateways, connected subnets,
routing tables, and upstream CanonicalDevices using an ephemeral typed dependency graph.

Architectural Invariants:
- Ephemeral ROUTE_DEPENDENCY domain: NEVER persisted as permanent physical/L2 topology edges.
- Explicitly distinct from PHYSICAL_ADJACENCY, LAYER2_ADJACENCY, LAYER3_REACHABILITY, and LOGICAL_RELATIONSHIP.
- Iterative bounded recursive resolution (zero Python call-stack recursion risk) with visited
  route + gateway cycle detection and depth ceilings.
- Evidence-strict failure propagation: downstream devices are NEVER claimed affected unless
  collected route evidence proves the dependency; uncollected/partial devices are reported
  in `unknown_dependencies`.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.routing.route_analytics import (
    _is_route_eligible_unicast,
    _route_evidence_id,
    build_ip_owner_index,
)
from core.routing.route_collector import RouteCollectionResult, RouteCompleteness
from core.routing.unified_route_parser import (
    NormalizedRoute,
    _canonicalize_prefix,
    _extract_ipv4,
)


class DependencyNodeType(str, Enum):
    ROUTE = "ROUTE"
    NEXT_HOP = "NEXT_HOP"
    GATEWAY = "GATEWAY"
    INTERFACE = "INTERFACE"
    CONNECTED_NETWORK = "CONNECTED_NETWORK"
    CANONICAL_DEVICE = "CANONICAL_DEVICE"
    ROUTING_TABLE = "ROUTING_TABLE"
    RECURSIVE_ROUTE = "RECURSIVE_ROUTE"
    UPSTREAM_DEVICE = "UPSTREAM_DEVICE"


class DependencyRelationType(str, Enum):
    OWNED_BY_DEVICE = "OWNED_BY_DEVICE"
    IN_ROUTING_TABLE = "IN_ROUTING_TABLE"
    DEPENDS_ON_NEXT_HOP = "DEPENDS_ON_NEXT_HOP"
    USES_GATEWAY_IP = "USES_GATEWAY_IP"
    RESOLVES_VIA_CONNECTED_NETWORK = "RESOLVES_VIA_CONNECTED_NETWORK"
    RESOLVES_VIA_RECURSIVE_ROUTE = "RESOLVES_VIA_RECURSIVE_ROUTE"
    EGRESSES_VIA_INTERFACE = "EGRESSES_VIA_INTERFACE"
    UPSTREAM_HOSTED_ON_DEVICE = "UPSTREAM_HOSTED_ON_DEVICE"
    ALTERNATIVE_CANDIDATE_FOR_PREFIX = "ALTERNATIVE_CANDIDATE_FOR_PREFIX"


class DependencyResolutionState(str, Enum):
    DIRECTLY_CONNECTED = "DIRECTLY_CONNECTED"
    RECURSIVE_RESOLVED = "RECURSIVE_RESOLVED"
    MULTI_PATH_RESOLVED = "MULTI_PATH_RESOLVED"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    DEPTH_LIMIT_EXCEEDED = "DEPTH_LIMIT_EXCEEDED"
    GATEWAY_UNREACHABLE = "GATEWAY_UNREACHABLE"
    UNRESOLVED_MISSING_ROUTE = "UNRESOLVED_MISSING_ROUTE"
    INACTIVE_OR_DISABLED = "INACTIVE_OR_DISABLED"


class HypotheticalFailureType(str, Enum):
    INTERFACE_DOWN = "INTERFACE_DOWN"
    GATEWAY_UNREACHABLE = "GATEWAY_UNREACHABLE"
    INTERMEDIATE_ROUTER_UNAVAILABLE = "INTERMEDIATE_ROUTER_UNAVAILABLE"
    MISSING_ROUTE = "MISSING_ROUTE"
    UPSTREAM_DEFAULT_ROUTE_LOSS = "UPSTREAM_DEFAULT_ROUTE_LOSS"
    ROUTING_TABLE_MISMATCH = "ROUTING_TABLE_MISMATCH"
    RECURSIVE_NEXT_HOP_FAILURE = "RECURSIVE_NEXT_HOP_FAILURE"
    ECMP_BRANCH_LOSS = "ECMP_BRANCH_LOSS"


@dataclass
class DependencyNode:
    node_id: str
    node_type: str  # DependencyNodeType value
    label: str
    device_id: Optional[str] = None
    routing_table: Optional[str] = None
    resolved: bool = True
    depth: int = 0
    confidence: float = 1.0
    evidence_ids: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "device_id": self.device_id,
            "routing_table": self.routing_table,
            "resolved": self.resolved,
            "depth": self.depth,
            "confidence": round(self.confidence, 3),
            "evidence_ids": list(self.evidence_ids),
            "attributes": dict(self.attributes),
        }


@dataclass
class DependencyEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str  # DependencyRelationType value
    depth: int = 0
    confidence: float = 1.0
    is_alternative: bool = False
    is_cycle_edge: bool = False
    evidence_ids: List[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "semantic_domain": "ROUTE_DEPENDENCY",
            "is_physical_link": False,
            "depth": self.depth,
            "confidence": round(self.confidence, 3),
            "is_alternative": self.is_alternative,
            "is_cycle_edge": self.is_cycle_edge,
            "evidence_ids": list(self.evidence_ids),
            "explanation": self.explanation,
        }


@dataclass
class RouteDependencyResolution:
    """
    Detailed recursive/multi-branch dependency resolution result for a single NormalizedRoute.
    """
    route_id: str
    device_id: str
    routing_table: str
    dst_prefix: str
    gateway: str
    state: str  # DependencyResolutionState value
    max_depth_reached: int = 0
    cycle_detected: bool = False
    resolved_egress_interfaces: List[str] = field(default_factory=list)
    resolved_immediate_gateways: List[str] = field(default_factory=list)
    upstream_device_ids: List[str] = field(default_factory=list)
    visited_routes: List[str] = field(default_factory=list)
    visited_gateways: List[str] = field(default_factory=list)
    alternative_gateway_routes: List[Dict[str, Any]] = field(default_factory=list)
    evidence_chain: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "device_id": self.device_id,
            "routing_table": self.routing_table,
            "dst_prefix": self.dst_prefix,
            "gateway": self.gateway,
            "state": self.state,
            "max_depth_reached": self.max_depth_reached,
            "cycle_detected": self.cycle_detected,
            "resolved_egress_interfaces": list(self.resolved_egress_interfaces),
            "resolved_immediate_gateways": list(self.resolved_immediate_gateways),
            "upstream_device_ids": list(self.upstream_device_ids),
            "visited_routes": list(self.visited_routes),
            "visited_gateways": list(self.visited_gateways),
            "alternative_gateway_routes": list(self.alternative_gateway_routes),
            "evidence_chain": list(self.evidence_chain),
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
        }


@dataclass
class RouteDependencyGraph:
    """
    Ephemeral structured dependency graph (never stored as physical topology edges).
    """
    nodes: Dict[str, DependencyNode] = field(default_factory=dict)
    edges: List[DependencyEdge] = field(default_factory=list)
    resolutions: List[RouteDependencyResolution] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    unresolved_node_ids: List[str] = field(default_factory=list)
    alternative_branches: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def add_node(self, node: DependencyNode, max_nodes: int = 4000) -> bool:
        if node.node_id in self.nodes:
            existing = self.nodes[node.node_id]
            for eid in node.evidence_ids:
                if eid not in existing.evidence_ids:
                    existing.evidence_ids.append(eid)
            existing.depth = max(existing.depth, node.depth)
            if not node.resolved:
                existing.resolved = False
            return True
        if len(self.nodes) >= max_nodes:
            self.truncated = True
            return False
        self.nodes[node.node_id] = node
        if not node.resolved and node.node_id not in self.unresolved_node_ids:
            self.unresolved_node_ids.append(node.node_id)
        return True

    def add_edge(self, edge: DependencyEdge, max_edges: int = 8000) -> bool:
        if len(self.edges) >= max_edges:
            self.truncated = True
            return False
        for ex in self.edges:
            if (
                ex.source_id == edge.source_id
                and ex.target_id == edge.target_id
                and ex.relation_type == edge.relation_type
            ):
                return True
        self.edges.append(edge)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "semantic_domain": "ROUTE_DEPENDENCY",
            "persisted_as_topology_edges": False,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "truncated": self.truncated,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "resolutions": [r.to_dict() for r in self.resolutions],
            "cycles": [list(c) for c in self.cycles],
            "unresolved_node_ids": list(self.unresolved_node_ids),
            "alternative_branches": list(self.alternative_branches),
        }


@dataclass
class FailureImpactReport:
    """
    Evidence-backed hypothetical failure propagation report (WP 4.6.3 Section 7.3).
    """
    failure_type: str
    target_parameters: Dict[str, Any]
    direct_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    indirect_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    potentially_affected_destinations: List[Dict[str, Any]] = field(default_factory=list)
    alternative_paths: List[Dict[str, Any]] = field(default_factory=list)
    unknown_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_label: str = "INSUFFICIENT_EVIDENCE"
    explanation: str = ""
    limitations: List[str] = field(default_factory=lambda: [
        "Hypothetical failure analysis models control-plane route dependencies and static/dynamic RIB backups.",
        "Dynamic IGP/BGP reconvergence timers, BFD session teardown, and firewall mangle rules are not simulated.",
        "Downstream devices without collected route evidence are listed in unknown_dependencies and never assumed affected.",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "target_parameters": dict(self.target_parameters),
            "direct_dependencies": list(self.direct_dependencies),
            "indirect_dependencies": list(self.indirect_dependencies),
            "potentially_affected_destinations": list(self.potentially_affected_destinations),
            "alternative_paths": list(self.alternative_paths),
            "unknown_dependencies": list(self.unknown_dependencies),
            "supporting_evidence": list(self.supporting_evidence),
            "confidence": round(self.confidence, 3),
            "confidence_label": self.confidence_label,
            "explanation": self.explanation,
            "limitations": list(self.limitations),
        }


def _make_route_key(device_id: str, route: NormalizedRoute) -> str:
    tbl = route.routing_table or "main"
    gw = route.gateway or (route.interface_name or "none")
    return f"route:{device_id}:{tbl}:{route.dst_prefix}:{gw}:d{route.distance}"


def _find_matching_gateway_routes(
    gw_ip: str,
    table_routes: Sequence[NormalizedRoute],
    current_route_key: str,
    device_id: str,
) -> Tuple[List[NormalizedRoute], List[NormalizedRoute]]:
    """
    Finds all eligible non-default routes in `table_routes` that cover `gw_ip`,
    returning `(best_resolving_routes, alternative_lower_preference_routes)`.
    Default route `0.0.0.0/0` is intentionally excluded because RouterOS does not
    consider `0.0.0.0/0` a valid connected/recursive gateway resolver by default.
    Note: Only `current_route_key` (immediate self-lookup) is deprioritized unless
    it is the *only* matching route, allowing both mutual cycles (r_a -> r_b -> r_a)
    and self-referential cycles (r_a -> r_a) to be explicitly detected as CYCLE_DETECTED.
    """
    try:
        addr = ipaddress.ip_address(gw_ip)
    except Exception:
        return [], []

    non_self_matches: List[NormalizedRoute] = []
    self_matches: List[NormalizedRoute] = []
    for r in table_routes:
        if r.is_default_route():
            continue
        if not _is_route_eligible_unicast(r):
            continue
        r_net = r.network
        if r_net is not None and addr in r_net:
            if _make_route_key(device_id, r) == current_route_key:
                self_matches.append(r)
            else:
                non_self_matches.append(r)

    matches = non_self_matches if non_self_matches else self_matches
    if not matches:
        return [], []

    matches.sort(
        key=lambda r: (
            r.prefix_len,
            -r.distance,
            1 if r.connect else 0,
            -(r.metric if r.metric is not None else 0),
        ),
        reverse=True,
    )
    top = matches[0]
    top_sig = (top.prefix_len, top.distance, 1 if top.connect else 0, top.metric if top.metric is not None else 0)
    best = [
        r for r in matches
        if (r.prefix_len, r.distance, 1 if r.connect else 0, r.metric if r.metric is not None else 0) == top_sig
    ]
    alts = [r for r in matches if r not in best]
    return best, alts


# ---------------------------------------------------------------------------
# 7.2 & 7.4 Iterative Route Dependency Resolver & Graph Builder
# ---------------------------------------------------------------------------

class RouteDependencyAnalyzer:
    """
    Resolves route next-hop dependencies iteratively and builds ephemeral
    RouteDependencyGraphs across one or multiple CanonicalDevices.
    """

    DEFAULT_MAX_DEPTH = 16

    def resolve_single_route(
        self,
        device_id: str,
        route: NormalizedRoute,
        table_routes: Sequence[NormalizedRoute],
        *,
        ip_owner_map: Optional[Dict[str, List[str]]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        evidence_id: str = "",
    ) -> RouteDependencyResolution:
        tbl = route.routing_table or "main"
        root_key = _make_route_key(device_id, route)
        ev_id = evidence_id or _route_evidence_id(route)

        if route.disabled or not route.active or route.unreachable:
            state = (
                DependencyResolutionState.GATEWAY_UNREACHABLE.value
                if route.unreachable
                else DependencyResolutionState.INACTIVE_OR_DISABLED.value
            )
            return RouteDependencyResolution(
                route_id=root_key,
                device_id=device_id,
                routing_table=tbl,
                dst_prefix=route.dst_prefix,
                gateway=route.gateway,
                state=state,
                visited_routes=[root_key],
                evidence_chain=[{
                    "depth": 0,
                    "route_id": root_key,
                    "dst_prefix": route.dst_prefix,
                    "gateway": route.gateway,
                    "evidence_id": ev_id,
                    "active": route.active,
                }],
                confidence=0.95,
                explanation=f"Route {route.dst_prefix} on '{device_id}' is inactive, disabled, or unreachable.",
            )

        # Direct connected route or interface-only gateway
        raw_gws = route.gateways if route.gateways else ([route.gateway] if route.gateway else [])
        if route.connect or (raw_gws and all(_extract_ipv4(g) is None for g in raw_gws)):
            ifaces = [
                (route.interface_name or g).strip()
                for g in (raw_gws or [route.interface_name or ""])
                if (route.interface_name or g).strip()
            ]
            return RouteDependencyResolution(
                route_id=root_key,
                device_id=device_id,
                routing_table=tbl,
                dst_prefix=route.dst_prefix,
                gateway=route.gateway,
                state=DependencyResolutionState.DIRECTLY_CONNECTED.value,
                max_depth_reached=0,
                resolved_egress_interfaces=ifaces,
                visited_routes=[root_key],
                evidence_chain=[{
                    "depth": 0,
                    "route_id": root_key,
                    "dst_prefix": route.dst_prefix,
                    "egress_interfaces": ifaces,
                    "evidence_id": ev_id,
                    "protocol": route.protocol,
                }],
                confidence=1.0,
                explanation=f"Route {route.dst_prefix} egresses directly via interface(s) {', '.join(ifaces)}.",
            )

        # Iterative BFS/DFS over next-hop gateway chain(s)
        visited_routes_all: List[str] = [root_key]
        visited_gws_all: List[str] = []
        egress_ifaces: List[str] = []
        immediate_gws: List[str] = []
        upstream_devs: List[str] = []
        alt_gw_routes: List[Dict[str, Any]] = []
        evidence_chain: List[Dict[str, Any]] = [{
            "depth": 0,
            "route_id": root_key,
            "dst_prefix": route.dst_prefix,
            "gateways": list(raw_gws),
            "evidence_id": ev_id,
            "protocol": route.protocol,
        }]

        cycle_detected = False
        depth_exceeded = False
        any_unresolved = False
        max_seen_depth = 0
        branch_count = 0

        # Queue item: (gw_str, depth, parent_rkey, path_route_keys, path_gateways)
        queue: List[Tuple[str, int, str, Set[str], Set[str]]] = [
            (g, 1, root_key, {root_key}, set()) for g in raw_gws if g
        ]

        while queue:
            curr_gw, depth, parent_rkey, path_rkeys, path_gws = queue.pop(0)
            gw_ip = _extract_ipv4(curr_gw)

            if gw_ip is None:
                # Interface gateway reached
                iface = curr_gw.strip()
                if iface and iface not in egress_ifaces:
                    egress_ifaces.append(iface)
                branch_count += 1
                max_seen_depth = max(max_seen_depth, depth)
                continue

            if gw_ip not in visited_gws_all:
                visited_gws_all.append(gw_ip)

            if gw_ip in path_gws:
                cycle_detected = True
                evidence_chain.append({
                    "depth": depth,
                    "gateway": gw_ip,
                    "event": "CYCLE_DETECTED",
                    "evidence_id": ev_id,
                })
                continue

            if depth > max_depth:
                depth_exceeded = True
                evidence_chain.append({
                    "depth": depth,
                    "gateway": gw_ip,
                    "event": "DEPTH_LIMIT_EXCEEDED",
                    "max_depth": max_depth,
                })
                continue

            max_seen_depth = max(max_seen_depth, depth)
            best_resolvers, alt_resolvers = _find_matching_gateway_routes(
                gw_ip, table_routes, current_route_key=parent_rkey, device_id=device_id
            )

            for alt in alt_resolvers:
                alt_entry = {
                    "for_gateway": gw_ip,
                    "dst_prefix": alt.dst_prefix,
                    "gateway": alt.gateway,
                    "distance": alt.distance,
                    "protocol": alt.protocol,
                }
                if alt_entry not in alt_gw_routes:
                    alt_gw_routes.append(alt_entry)

            if not best_resolvers:
                any_unresolved = True
                evidence_chain.append({
                    "depth": depth,
                    "gateway": gw_ip,
                    "event": "UNRESOLVED_GATEWAY",
                    "evidence_id": ev_id,
                })
                continue

            for res_route in best_resolvers:
                rkey = _make_route_key(device_id, res_route)
                if rkey not in visited_routes_all:
                    visited_routes_all.append(rkey)

                if rkey in path_rkeys:
                    cycle_detected = True
                    evidence_chain.append({
                        "depth": depth,
                        "route_id": rkey,
                        "gateway": gw_ip,
                        "event": "ROUTE_CYCLE_DETECTED",
                        "evidence_id": _route_evidence_id(res_route, ev_id),
                    })
                    continue

                evidence_chain.append({
                    "depth": depth,
                    "resolving_gateway": gw_ip,
                    "via_route_id": rkey,
                    "via_prefix": res_route.dst_prefix,
                    "via_gateway": res_route.gateway,
                    "connect": res_route.connect,
                    "protocol": res_route.protocol,
                    "evidence_id": _route_evidence_id(res_route, ev_id),
                })

                if res_route.connect or not _extract_ipv4(res_route.gateway):
                    iface = (res_route.interface_name or res_route.gateway or "").strip()
                    if iface and iface not in egress_ifaces:
                        egress_ifaces.append(iface)
                    if gw_ip not in immediate_gws:
                        immediate_gws.append(gw_ip)
                    if ip_owner_map:
                        for up_dev in ip_owner_map.get(gw_ip, []):
                            if up_dev != device_id and up_dev not in upstream_devs:
                                upstream_devs.append(up_dev)
                    branch_count += 1
                else:
                    next_gws = res_route.gateways if res_route.gateways else [res_route.gateway]
                    for ng in next_gws:
                        if ng:
                            queue.append((ng, depth + 1, rkey, path_rkeys | {rkey}, path_gws | {gw_ip}))

        # Classify explicit state
        if cycle_detected:
            final_state = DependencyResolutionState.CYCLE_DETECTED.value
            conf = 0.95
            expl = f"Dependency cycle detected while resolving {route.dst_prefix} via {route.gateway}."
        elif depth_exceeded:
            final_state = DependencyResolutionState.DEPTH_LIMIT_EXCEEDED.value
            conf = 0.90
            expl = f"Recursion depth exceeded maximum limit ({max_depth}) for {route.dst_prefix}."
        elif not egress_ifaces and any_unresolved:
            final_state = DependencyResolutionState.UNRESOLVED_MISSING_ROUTE.value
            conf = 0.85
            expl = f"Gateway {route.gateway} for {route.dst_prefix} has no active resolving route in table '{tbl}'."
        elif branch_count > 1 or len(raw_gws) > 1:
            final_state = DependencyResolutionState.MULTI_PATH_RESOLVED.value
            conf = 0.92 if not any_unresolved else 0.70
            expl = (
                f"Multi-path dependency resolved across {branch_count} active branch(es) "
                f"egressing {', '.join(egress_ifaces)}."
            )
        elif max_seen_depth > 1:
            final_state = DependencyResolutionState.RECURSIVE_RESOLVED.value
            conf = 0.90
            expl = (
                f"Recursive route {route.dst_prefix} (gateway {route.gateway}) resolved at depth "
                f"{max_seen_depth} via {', '.join(egress_ifaces)}."
            )
        else:
            final_state = DependencyResolutionState.DIRECTLY_CONNECTED.value
            conf = 0.96
            expl = (
                f"Direct gateway {route.gateway} for {route.dst_prefix} resolved on connected "
                f"interface {', '.join(egress_ifaces)}."
            )

        return RouteDependencyResolution(
            route_id=root_key,
            device_id=device_id,
            routing_table=tbl,
            dst_prefix=route.dst_prefix,
            gateway=route.gateway,
            state=final_state,
            max_depth_reached=max_seen_depth,
            cycle_detected=cycle_detected,
            resolved_egress_interfaces=egress_ifaces,
            resolved_immediate_gateways=immediate_gws,
            upstream_device_ids=upstream_devs,
            visited_routes=visited_routes_all,
            visited_gateways=visited_gws_all,
            alternative_gateway_routes=alt_gw_routes,
            evidence_chain=evidence_chain,
            confidence=conf,
            explanation=expl,
        )

    def build_dependency_graph(
        self,
        collections: Dict[str, RouteCollectionResult],
        *,
        device_ips: Optional[Dict[str, List[str]]] = None,
        target_device_id: Optional[str] = None,
        routing_table: Optional[str] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> RouteDependencyGraph:
        """
        Builds a structured multi-entity RouteDependencyGraph with typed directional edges,
        cycle tracking, alternative candidate links, and upstream CanonicalDevice nodes.
        Never mutates TopologyEngine physical/L2 edges.
        """
        graph = RouteDependencyGraph()
        ip_owners = build_ip_owner_index(collections, explicit_device_ips=device_ips)

        target_devs = (
            {target_device_id: collections[target_device_id]}
            if target_device_id and target_device_id in collections
            else collections
        )

        for dev_id, col in target_devs.items():
            ev_id = col.evidence_id
            dev_node_id = f"device:{dev_id}"
            graph.add_node(
                DependencyNode(
                    node_id=dev_node_id,
                    node_type=DependencyNodeType.CANONICAL_DEVICE.value,
                    label=col.device_identity or dev_id,
                    device_id=dev_id,
                    evidence_ids=[ev_id],
                    attributes={"completeness": col.completeness, "status": col.status},
                )
            )

            by_table: Dict[str, List[NormalizedRoute]] = {}
            for r in col.routes:
                tbl = r.routing_table or "main"
                if routing_table and tbl != routing_table:
                    continue
                by_table.setdefault(tbl, []).append(r)

            for tbl, tbl_routes in by_table.items():
                tbl_node_id = f"table:{dev_id}:{tbl}"
                graph.add_node(
                    DependencyNode(
                        node_id=tbl_node_id,
                        node_type=DependencyNodeType.ROUTING_TABLE.value,
                        label=f"{dev_id}:{tbl}",
                        device_id=dev_id,
                        routing_table=tbl,
                        evidence_ids=[ev_id],
                    )
                )
                graph.add_edge(
                    DependencyEdge(
                        edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                        source_id=tbl_node_id,
                        target_id=dev_node_id,
                        relation_type=DependencyRelationType.OWNED_BY_DEVICE.value,
                        evidence_ids=[ev_id],
                        explanation=f"Routing table '{tbl}' belongs to CanonicalDevice '{dev_id}'.",
                    )
                )

                # Index connected networks in this table
                conn_node_by_key: Dict[str, str] = {}
                for r in tbl_routes:
                    if r.connect:
                        c_id = f"subnet:{dev_id}:{tbl}:{r.dst_prefix}"
                        conn_node_by_key[_make_route_key(dev_id, r)] = c_id
                        graph.add_node(
                            DependencyNode(
                                node_id=c_id,
                                node_type=DependencyNodeType.CONNECTED_NETWORK.value,
                                label=r.dst_prefix,
                                device_id=dev_id,
                                routing_table=tbl,
                                evidence_ids=[ev_id],
                                attributes={"pref_src": r.pref_src, "interface": r.interface_name or r.gateway},
                            )
                        )
                        iface_name = (r.interface_name or r.gateway or "").strip()
                        if iface_name:
                            if_id = f"interface:{dev_id}:{iface_name}"
                            graph.add_node(
                                DependencyNode(
                                    node_id=if_id,
                                    node_type=DependencyNodeType.INTERFACE.value,
                                    label=f"{dev_id}:{iface_name}",
                                    device_id=dev_id,
                                    routing_table=tbl,
                                    evidence_ids=[ev_id],
                                )
                            )
                            graph.add_edge(
                                DependencyEdge(
                                    edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                    source_id=c_id,
                                    target_id=if_id,
                                    relation_type=DependencyRelationType.EGRESSES_VIA_INTERFACE.value,
                                    evidence_ids=[ev_id],
                                    explanation=f"Connected subnet {r.dst_prefix} attaches to {iface_name}.",
                                )
                            )
                            graph.add_edge(
                                DependencyEdge(
                                    edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                    source_id=if_id,
                                    target_id=dev_node_id,
                                    relation_type=DependencyRelationType.OWNED_BY_DEVICE.value,
                                    evidence_ids=[ev_id],
                                )
                            )

                # Group routes by prefix to record alternative/backup candidates
                by_prefix: Dict[str, List[NormalizedRoute]] = {}
                for r in tbl_routes:
                    by_prefix.setdefault(r.dst_prefix, []).append(r)

                for pfx, pfx_list in by_prefix.items():
                    if len(pfx_list) > 1:
                        sorted_pfx = sorted(pfx_list, key=lambda x: (not x.active, x.distance))
                        primary_key = _make_route_key(dev_id, sorted_pfx[0])
                        for backup in sorted_pfx[1:]:
                            b_key = _make_route_key(dev_id, backup)
                            graph.alternative_branches.append({
                                "device_id": dev_id,
                                "routing_table": tbl,
                                "dst_prefix": pfx,
                                "primary_route_id": primary_key,
                                "alternative_route_id": b_key,
                                "alternative_gateway": backup.gateway,
                                "distance": backup.distance,
                                "active": backup.active,
                            })
                            graph.add_edge(
                                DependencyEdge(
                                    edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                    source_id=primary_key,
                                    target_id=b_key,
                                    relation_type=DependencyRelationType.ALTERNATIVE_CANDIDATE_FOR_PREFIX.value,
                                    is_alternative=True,
                                    evidence_ids=[ev_id],
                                    explanation=f"Backup/ECMP candidate for {pfx} (distance={backup.distance}).",
                                )
                            )

                # Resolve each route and materialize typed nodes/edges
                for r in tbl_routes:
                    res = self.resolve_single_route(
                        dev_id,
                        r,
                        tbl_routes,
                        ip_owner_map=ip_owners,
                        max_depth=max_depth,
                        evidence_id=ev_id,
                    )
                    graph.resolutions.append(res)

                    is_rec_route = res.max_depth_reached > 1
                    r_node_type = (
                        DependencyNodeType.RECURSIVE_ROUTE.value
                        if is_rec_route
                        else DependencyNodeType.ROUTE.value
                    )
                    is_resolved = res.state in (
                        DependencyResolutionState.DIRECTLY_CONNECTED.value,
                        DependencyResolutionState.RECURSIVE_RESOLVED.value,
                        DependencyResolutionState.MULTI_PATH_RESOLVED.value,
                    )
                    graph.add_node(
                        DependencyNode(
                            node_id=res.route_id,
                            node_type=r_node_type,
                            label=f"{r.dst_prefix} via {r.gateway or r.interface_name}",
                            device_id=dev_id,
                            routing_table=tbl,
                            resolved=is_resolved,
                            depth=res.max_depth_reached,
                            confidence=res.confidence,
                            evidence_ids=[ev_id],
                            attributes={
                                "dst_prefix": r.dst_prefix,
                                "gateway": r.gateway,
                                "protocol": r.protocol,
                                "distance": r.distance,
                                "active": r.active,
                                "resolution_state": res.state,
                            },
                        )
                    )
                    graph.add_edge(
                        DependencyEdge(
                            edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                            source_id=res.route_id,
                            target_id=tbl_node_id,
                            relation_type=DependencyRelationType.IN_ROUTING_TABLE.value,
                            evidence_ids=[ev_id],
                        )
                    )

                    if res.cycle_detected:
                        graph.cycles.append(list(res.visited_routes) + list(res.visited_gateways))

                    raw_gws = r.gateways if r.gateways else ([r.gateway] if r.gateway else [])
                    for gw_raw in raw_gws:
                        nh_id = f"nexthop:{dev_id}:{tbl}:{gw_raw}"
                        gw_ip = _extract_ipv4(gw_raw)
                        graph.add_node(
                            DependencyNode(
                                node_id=nh_id,
                                node_type=DependencyNodeType.NEXT_HOP.value,
                                label=gw_raw,
                                device_id=dev_id,
                                routing_table=tbl,
                                resolved=is_resolved,
                                depth=1,
                                confidence=res.confidence,
                                evidence_ids=[ev_id],
                            )
                        )
                        graph.add_edge(
                            DependencyEdge(
                                edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                source_id=res.route_id,
                                target_id=nh_id,
                                relation_type=DependencyRelationType.DEPENDS_ON_NEXT_HOP.value,
                                depth=1,
                                confidence=res.confidence,
                                evidence_ids=[ev_id],
                            )
                        )

                        if gw_ip:
                            gw_node_id = f"gateway:{gw_ip}"
                            gw_owners = [o for o in ip_owners.get(gw_ip, []) if o != dev_id]
                            graph.add_node(
                                DependencyNode(
                                    node_id=gw_node_id,
                                    node_type=DependencyNodeType.GATEWAY.value,
                                    label=gw_ip,
                                    device_id=gw_owners[0] if len(gw_owners) == 1 else None,
                                    resolved=is_resolved,
                                    depth=1,
                                    confidence=res.confidence,
                                    evidence_ids=[ev_id],
                                )
                            )
                            graph.add_edge(
                                DependencyEdge(
                                    edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                    source_id=nh_id,
                                    target_id=gw_node_id,
                                    relation_type=DependencyRelationType.USES_GATEWAY_IP.value,
                                    depth=1,
                                    confidence=res.confidence,
                                    is_cycle_edge=res.cycle_detected,
                                    evidence_ids=[ev_id],
                                )
                            )
                            if gw_owners:
                                for up_id in gw_owners:
                                    up_node_id = f"upstream:{up_id}"
                                    graph.add_node(
                                        DependencyNode(
                                            node_id=up_node_id,
                                            node_type=DependencyNodeType.UPSTREAM_DEVICE.value,
                                            label=up_id,
                                            device_id=up_id,
                                            resolved=up_id in collections,
                                            evidence_ids=[ev_id],
                                        )
                                    )
                                    graph.add_edge(
                                        DependencyEdge(
                                            edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                            source_id=gw_node_id,
                                            target_id=up_node_id,
                                            relation_type=DependencyRelationType.UPSTREAM_HOSTED_ON_DEVICE.value,
                                            confidence=0.90,
                                            evidence_ids=[ev_id],
                                            explanation=f"Gateway IP {gw_ip} belongs to upstream device '{up_id}'.",
                                        )
                                    )
                            else:
                                unres_up_id = f"upstream:unresolved:{gw_ip}"
                                graph.add_node(
                                    DependencyNode(
                                        node_id=unres_up_id,
                                        node_type=DependencyNodeType.UPSTREAM_DEVICE.value,
                                        label=f"Unregistered/External ({gw_ip})",
                                        device_id=None,
                                        resolved=False,
                                        confidence=0.40,
                                        evidence_ids=[ev_id],
                                    )
                                )
                                graph.add_edge(
                                    DependencyEdge(
                                        edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                        source_id=gw_node_id,
                                        target_id=unres_up_id,
                                        relation_type=DependencyRelationType.UPSTREAM_HOSTED_ON_DEVICE.value,
                                        confidence=0.40,
                                        evidence_ids=[ev_id],
                                        explanation=f"No registered CanonicalDevice owns gateway IP {gw_ip}.",
                                    )
                                )

                    # Link evidence chain resolving routes / connected subnets
                    for step in res.evidence_chain:
                        via_rkey = step.get("via_route_id")
                        resolving_gw = step.get("resolving_gateway")
                        if via_rkey and resolving_gw:
                            gw_node_id = f"gateway:{resolving_gw}"
                            if step.get("connect") and via_rkey in conn_node_by_key:
                                graph.add_edge(
                                    DependencyEdge(
                                        edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                        source_id=gw_node_id,
                                        target_id=conn_node_by_key[via_rkey],
                                        relation_type=DependencyRelationType.RESOLVES_VIA_CONNECTED_NETWORK.value,
                                        depth=int(step.get("depth") or 1),
                                        evidence_ids=[str(step.get("evidence_id") or ev_id)],
                                    )
                                )
                            else:
                                graph.add_edge(
                                    DependencyEdge(
                                        edge_id=f"dep_{uuid.uuid4().hex[:8]}",
                                        source_id=gw_node_id,
                                        target_id=via_rkey,
                                        relation_type=DependencyRelationType.RESOLVES_VIA_RECURSIVE_ROUTE.value,
                                        depth=int(step.get("depth") or 1),
                                        evidence_ids=[str(step.get("evidence_id") or ev_id)],
                                    )
                                )

        return graph


# ---------------------------------------------------------------------------
# 7.3 Hypothetical Failure Propagation Analyzer
# ---------------------------------------------------------------------------

class FailurePropagationAnalyzer:
    """
    Evaluates the evidence-backed blast radius of hypothetical routing, gateway,
    interface, VRF, ECMP, or intermediate-router failures without mutating network state.
    """

    def __init__(self, dep_analyzer: Optional[RouteDependencyAnalyzer] = None):
        self.dep_analyzer = dep_analyzer or RouteDependencyAnalyzer()

    def analyze_failure(
        self,
        failure_type: str,
        collections: Dict[str, RouteCollectionResult],
        *,
        device_id: Optional[str] = None,
        interface_name: Optional[str] = None,
        gateway_ip: Optional[str] = None,
        dst_prefix: Optional[str] = None,
        routing_table: str = "main",
        device_ips: Optional[Dict[str, List[str]]] = None,
        known_registered_device_ids: Optional[Sequence[str]] = None,
    ) -> FailureImpactReport:
        ftype = failure_type.strip().upper()
        params = {
            "device_id": device_id,
            "interface_name": interface_name,
            "gateway_ip": gateway_ip,
            "dst_prefix": dst_prefix,
            "routing_table": routing_table,
        }
        ip_owners = build_ip_owner_index(collections, explicit_device_ips=device_ips)

        direct_deps: List[Dict[str, Any]] = []
        indirect_deps: List[Dict[str, Any]] = []
        affected_dests: List[Dict[str, Any]] = []
        alt_paths: List[Dict[str, Any]] = []
        unknown_deps: List[Dict[str, Any]] = []
        supporting_ev: List[str] = []

        def _add_ev(eid: str) -> None:
            if eid and eid not in supporting_ev:
                supporting_ev.append(eid)

        # Record registered devices lacking complete route evidence in `unknown_dependencies`
        all_known_ids = set(collections.keys()) | set(known_registered_device_ids or [])
        for kid in sorted(all_known_ids):
            col = collections.get(kid)
            if col is None or col.completeness != RouteCompleteness.COMPLETE.value or not col.routes:
                unknown_deps.append({
                    "device_id": kid,
                    "reason": (
                        "No route evidence collected for device; downstream dependency impact cannot be verified."
                        if col is None
                        else f"Route collection completeness is '{col.completeness}'; downstream impact is indeterminate."
                    ),
                })

        # Resolve all routes across complete/partial devices
        resolutions_by_dev: Dict[str, List[Tuple[NormalizedRoute, RouteDependencyResolution]]] = {}
        routes_by_dev_table_pfx: Dict[Tuple[str, str, str], List[NormalizedRoute]] = {}

        for d_id, col in collections.items():
            if not col.routes:
                continue
            res_list: List[Tuple[NormalizedRoute, RouteDependencyResolution]] = []
            by_tbl: Dict[str, List[NormalizedRoute]] = {}
            for r in col.routes:
                by_tbl.setdefault(r.routing_table or "main", []).append(r)
                routes_by_dev_table_pfx.setdefault((d_id, r.routing_table or "main", r.dst_prefix), []).append(r)

            for r in col.routes:
                tbl_routes = by_tbl.get(r.routing_table or "main", [])
                res = self.dep_analyzer.resolve_single_route(
                    d_id, r, tbl_routes, ip_owner_map=ip_owners, evidence_id=col.evidence_id
                )
                res_list.append((r, res))
            resolutions_by_dev[d_id] = res_list

        # Track prefixes lost on primary device so we can check downstream routers pointing to it
        lost_device_prefixes: Set[Tuple[str, str, str]] = set()  # (dev_id, table, dst_prefix)

        for d_id, pairs in resolutions_by_dev.items():
            col = collections[d_id]
            for r, res in pairs:
                if not r.active or r.disabled:
                    continue
                tbl = r.routing_table or "main"
                is_direct = False
                is_indirect = False
                reason = ""

                if ftype == HypotheticalFailureType.INTERFACE_DOWN.value:
                    if d_id == device_id and interface_name:
                        if r.connect and (r.interface_name or r.gateway) == interface_name:
                            is_direct = True
                            reason = f"Connected subnet {r.dst_prefix} is directly attached to failed interface '{interface_name}'."
                        elif interface_name in res.resolved_egress_interfaces:
                            if res.max_depth_reached <= 1:
                                is_direct = True
                                reason = f"Route {r.dst_prefix} egresses directly through failed interface '{interface_name}'."
                            else:
                                is_indirect = True
                                reason = f"Recursive route {r.dst_prefix} resolves at depth {res.max_depth_reached} to '{interface_name}'."

                elif ftype == HypotheticalFailureType.GATEWAY_UNREACHABLE.value:
                    if gateway_ip and (not device_id or d_id == device_id):
                        raw_gws = r.gateways if r.gateways else ([r.gateway] if r.gateway else [])
                        if any(_extract_ipv4(g) == gateway_ip for g in raw_gws):
                            is_direct = True
                            reason = f"Route {r.dst_prefix} directly specifies unreachable gateway {gateway_ip}."
                        elif gateway_ip in res.visited_gateways:
                            is_indirect = True
                            reason = f"Route {r.dst_prefix} recursively depends on gateway {gateway_ip}."

                elif ftype == HypotheticalFailureType.INTERMEDIATE_ROUTER_UNAVAILABLE.value:
                    if device_id and d_id == device_id:
                        is_direct = True
                        reason = f"Route {r.dst_prefix} is hosted on unavailable router '{device_id}'."
                    elif device_id and device_id in res.upstream_device_ids:
                        if res.max_depth_reached <= 1:
                            is_direct = True
                            reason = f"Route {r.dst_prefix} on '{d_id}' forwards next-hop directly to unavailable router '{device_id}'."
                        else:
                            is_indirect = True
                            reason = f"Route {r.dst_prefix} on '{d_id}' recursively resolves via unavailable router '{device_id}'."

                elif ftype == HypotheticalFailureType.MISSING_ROUTE.value:
                    norm_target_pfx = _canonicalize_prefix(dst_prefix) if dst_prefix else ""
                    if d_id == device_id and tbl == routing_table and r.dst_prefix == norm_target_pfx:
                        is_direct = True
                        reason = f"Target route {r.dst_prefix} removed/missing in table '{tbl}' on '{d_id}'."
                    elif d_id == device_id and tbl == routing_table and any(
                        step.get("via_prefix") == norm_target_pfx for step in res.evidence_chain
                    ):
                        is_indirect = True
                        reason = f"Recursive route {r.dst_prefix} depends on missing resolving prefix {norm_target_pfx}."

                elif ftype == HypotheticalFailureType.UPSTREAM_DEFAULT_ROUTE_LOSS.value:
                    if d_id == device_id and r.is_default_route() and tbl == routing_table:
                        is_direct = True
                        reason = f"Default route (0.0.0.0/0) lost on upstream router '{device_id}'."

                elif ftype == HypotheticalFailureType.ROUTING_TABLE_MISMATCH.value:
                    if d_id == device_id and tbl == routing_table:
                        is_direct = True
                        reason = f"Route {r.dst_prefix} in table '{tbl}' isolated from lookups in mismatched table."

                elif ftype == HypotheticalFailureType.RECURSIVE_NEXT_HOP_FAILURE.value:
                    target_match = dst_prefix or gateway_ip or ""
                    if (not device_id or d_id == device_id) and res.max_depth_reached > 1:
                        if not target_match or target_match in res.visited_gateways or any(
                            step.get("via_prefix") == _canonicalize_prefix(target_match) for step in res.evidence_chain
                        ):
                            is_direct = True
                            reason = f"Recursive next-hop chain for {r.dst_prefix} failed ({' -> '.join(res.visited_gateways)})."

                elif ftype == HypotheticalFailureType.ECMP_BRANCH_LOSS.value:
                    raw_gws = r.gateways if r.gateways else ([r.gateway] if r.gateway else [])
                    same_pfx_active = [
                        cand for cand in routes_by_dev_table_pfx.get((d_id, tbl, r.dst_prefix), [])
                        if _is_route_eligible_unicast(cand)
                    ]
                    is_ecmp_route = len(raw_gws) > 1 or len(same_pfx_active) > 1
                    if is_ecmp_route and (not device_id or d_id == device_id):
                        if (not dst_prefix or r.dst_prefix == _canonicalize_prefix(dst_prefix)) and (
                            not gateway_ip or any(_extract_ipv4(g) == gateway_ip for g in raw_gws)
                        ):
                            is_direct = True
                            reason = f"ECMP branch ({gateway_ip or r.gateway}) lost for {r.dst_prefix} on '{d_id}'."

                if not (is_direct or is_indirect):
                    continue

                _add_ev(col.evidence_id)
                dep_record = {
                    "device_id": d_id,
                    "routing_table": tbl,
                    "dst_prefix": r.dst_prefix,
                    "gateway": r.gateway,
                    "route_id": res.route_id,
                    "evidence_id": col.evidence_id,
                    "reason": reason,
                }
                if is_direct:
                    direct_deps.append(dep_record)
                else:
                    indirect_deps.append(dep_record)

                # Evaluate surviving alternative routes (ECMP siblings, floating static backups, or supernets)
                candidates_same_pfx = routes_by_dev_table_pfx.get((d_id, tbl, r.dst_prefix), [])
                surviving_alts: List[Dict[str, Any]] = []

                # Surviving gateways inside a multi-gateway ECMP route
                raw_gws = r.gateways if r.gateways else ([r.gateway] if r.gateway else [])
                if len(raw_gws) > 1 and gateway_ip:
                    surviving_gws = [g for g in raw_gws if _extract_ipv4(g) != gateway_ip]
                    for sg in surviving_gws:
                        surviving_alts.append({
                            "device_id": d_id,
                            "routing_table": tbl,
                            "dst_prefix": r.dst_prefix,
                            "alternative_gateway": sg,
                            "mechanism": "ECMP_SURVIVING_BRANCH",
                            "distance": r.distance,
                        })

                for cand in candidates_same_pfx:
                    if cand is r or cand.disabled:
                        continue
                    cand_gw_ip = _extract_ipv4(cand.gateway)
                    if gateway_ip and cand_gw_ip == gateway_ip:
                        continue
                    if interface_name and d_id == device_id and (cand.interface_name or cand.gateway) == interface_name:
                        continue
                    surviving_alts.append({
                        "device_id": d_id,
                        "routing_table": tbl,
                        "dst_prefix": r.dst_prefix,
                        "alternative_gateway": cand.gateway,
                        "mechanism": "ECMP_SIBLING" if cand.distance == r.distance else "FLOATING_BACKUP_ROUTE",
                        "distance": cand.distance,
                    })

                for alt in surviving_alts:
                    if alt not in alt_paths:
                        alt_paths.append(alt)

                impact_state = (
                    "DEGRADED_REROUTED_VIA_ALTERNATIVE"
                    if surviving_alts
                    else "ISOLATED_NO_ALTERNATIVE"
                )
                if not surviving_alts:
                    lost_device_prefixes.add((d_id, tbl, r.dst_prefix))

                affected_dests.append({
                    "device_id": d_id,
                    "routing_table": tbl,
                    "dst_prefix": r.dst_prefix,
                    "impact_state": impact_state,
                    "has_alternative": bool(surviving_alts),
                })

        # Second pass: Bounded transitive multi-hop downstream propagation across collected devices!
        # Only propagate when collected route evidence on downstream router explicitly points to
        # an upstream device+prefix in `lost_device_prefixes` and the downstream router itself
        # has no surviving alternative route for that prefix.
        seen_indirect_route_ids: Set[str] = {d["route_id"] for d in direct_deps + indirect_deps}
        max_prop_hops = 16
        prop_hop = 0
        changed = True
        while changed and lost_device_prefixes and prop_hop < max_prop_hops:
            changed = False
            prop_hop += 1
            for d_id, pairs in resolutions_by_dev.items():
                col = collections[d_id]
                for r, res in pairs:
                    if not r.active or r.disabled or r.connect:
                        continue
                    if res.route_id in seen_indirect_route_ids:
                        continue
                    tbl = r.routing_table or "main"
                    for up_dev in res.upstream_device_ids:
                        upstream_lost_exact = (up_dev, tbl, r.dst_prefix) in lost_device_prefixes
                        upstream_lost_default = (up_dev, tbl, "0.0.0.0/0") in lost_device_prefixes
                        upstream_router_down = (
                            ftype == HypotheticalFailureType.INTERMEDIATE_ROUTER_UNAVAILABLE.value
                            and any(lp[0] == up_dev and lp[1] == tbl for lp in lost_device_prefixes)
                        )
                        if upstream_lost_exact or (r.is_default_route() and upstream_lost_default) or upstream_router_down:
                            seen_indirect_route_ids.add(res.route_id)
                            _add_ev(col.evidence_id)

                            # Check whether downstream router has an independent alternative candidate
                            cands = routes_by_dev_table_pfx.get((d_id, tbl, r.dst_prefix), [])
                            down_alts = []
                            for cand in cands:
                                if cand is r or cand.disabled:
                                    continue
                                cand_res = self.dep_analyzer.resolve_single_route(
                                    d_id, cand, [p[0] for p in pairs], ip_owner_map=ip_owners, evidence_id=col.evidence_id
                                )
                                if up_dev not in cand_res.upstream_device_ids:
                                    down_alts.append({
                                        "device_id": d_id,
                                        "routing_table": tbl,
                                        "dst_prefix": r.dst_prefix,
                                        "alternative_gateway": cand.gateway,
                                        "mechanism": "DOWNSTREAM_BACKUP_ROUTE",
                                        "distance": cand.distance,
                                    })
                            for da in down_alts:
                                if da not in alt_paths:
                                    alt_paths.append(da)

                            ind_rec = {
                                "device_id": d_id,
                                "upstream_device_id": up_dev,
                                "propagation_hop": prop_hop,
                                "routing_table": tbl,
                                "dst_prefix": r.dst_prefix,
                                "gateway": r.gateway,
                                "route_id": res.route_id,
                                "evidence_id": col.evidence_id,
                                "reason": (
                                    f"Downstream router '{d_id}' forwards {r.dst_prefix} via '{up_dev}', "
                                    f"which has lost its active forwarding path (hop={prop_hop})."
                                ),
                            }
                            indirect_deps.append(ind_rec)
                            affected_dests.append({
                                "device_id": d_id,
                                "routing_table": tbl,
                                "dst_prefix": r.dst_prefix,
                                "impact_state": (
                                    "DEGRADED_REROUTED_VIA_ALTERNATIVE"
                                    if down_alts
                                    else "DOWNSTREAM_BLACKHOLE_RISK"
                                ),
                                "has_alternative": bool(down_alts),
                            })
                            if not down_alts:
                                key_tuple = (d_id, tbl, r.dst_prefix)
                                if key_tuple not in lost_device_prefixes:
                                    lost_device_prefixes.add(key_tuple)
                                    changed = True
                            break

        # Calibrate confidence based on evidence availability
        if not supporting_ev and not collections:
            conf = 0.0
            conf_label = "INSUFFICIENT_EVIDENCE"
        elif unknown_deps:
            conf = 0.68 if supporting_ev else 0.35
            conf_label = "MEDIUM" if supporting_ev else "LOW"
        else:
            conf = 0.92 if supporting_ev else 0.75
            conf_label = "HIGH"

        expl = (
            f"Simulated {ftype}: {len(direct_deps)} direct dependency(ies), "
            f"{len(indirect_deps)} indirect dependency(ies), "
            f"{len(alt_paths)} surviving alternative path(s), and "
            f"{len(unknown_deps)} unverified device(s)."
        )

        return FailureImpactReport(
            failure_type=ftype,
            target_parameters=params,
            direct_dependencies=direct_deps,
            indirect_dependencies=indirect_deps,
            potentially_affected_destinations=affected_dests,
            alternative_paths=alt_paths,
            unknown_dependencies=unknown_deps,
            supporting_evidence=supporting_ev,
            confidence=conf,
            confidence_label=conf_label,
            explanation=expl,
        )
