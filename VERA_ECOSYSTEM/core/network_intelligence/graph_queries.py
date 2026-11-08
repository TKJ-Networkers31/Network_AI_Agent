"""
AIRA OS — Bounded Network Knowledge Graph Query Engine (Networking VI / WP 6.2).

Implements O(V + E) iterative, cycle-safe, bounded graph queries over `NetworkKnowledgeGraph`.
Every returned query result explicitly states its underlying `evidence_ids`, `relationship_types`,
`layers`, `confidence`, and `is_inferred` flags.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.network_intelligence.entity_resolver import EntityResolver
from core.network_intelligence.intelligence_models import (
    GraphEntityType,
    GraphRelationshipType,
    KnowledgeEdge,
    KnowledgeNode,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.topology_models import normalize_ip

HARD_MAX_DEPTH = 16
HARD_MAX_VISITED = 2000


class GraphQueryEngine:
    """Bounded, evidence-traceable query executor over `NetworkKnowledgeGraph`."""

    def __init__(self, graph: NetworkKnowledgeGraph) -> None:
        self.graph = graph

    def _norm_dev_node(self, device_id: str) -> str:
        return device_id if device_id.startswith("device:") else EntityResolver.canonical_device_node_id(device_id)

    # 1. Devices connected to a selected device
    def get_connected_devices(
        self,
        device_id: str,
        layers: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        dev_node = self._norm_dev_node(device_id)
        allowed_layers = set(layers) if layers else None
        conn_rels = {
            GraphRelationshipType.PHYSICAL_ADJACENCY.value,
            GraphRelationshipType.LAYER2_ADJACENCY.value,
            GraphRelationshipType.LAYER3_REACHABILITY.value,
            GraphRelationshipType.PEERS_WITH.value,
            GraphRelationshipType.LOGICAL_RELATIONSHIP.value,
        }
        results: List[Dict[str, Any]] = []
        evidence_ids: Set[str] = set()

        for eid in self.graph.out_edges.get(dev_node, []) + self.graph.in_edges.get(dev_node, []):
            edge = self.graph.edges.get(eid)
            if not edge or edge.relationship_type not in conn_rels:
                continue
            if allowed_layers and edge.layer not in allowed_layers:
                continue
            peer_id = edge.target_id if edge.source_id == dev_node else edge.source_id
            pnode = self.graph.get_node(peer_id)
            if not pnode or pnode.entity_type != GraphEntityType.DEVICE.value or peer_id == dev_node:
                continue
            evidence_ids.update(edge.evidence_ids)
            results.append(
                {
                    "device_id": pnode.device_id or peer_id.replace("device:", ""),
                    "display_name": pnode.label,
                    "relationship_type": edge.relationship_type,
                    "layer": edge.layer,
                    "is_inferred": edge.is_inferred,
                    "confidence": edge.confidence,
                    "freshness": edge.freshness,
                    "provenance": edge.provenance,
                    "evidence_ids": list(edge.evidence_ids),
                    "attributes": dict(edge.attributes),
                }
            )

        # Deduplicate by (device_id, relationship_type, layer)
        deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for item in results:
            k = (item["device_id"], item["relationship_type"], item["layer"])
            if k not in deduped or item["confidence"] > deduped[k]["confidence"]:
                deduped[k] = item

        return {
            "query": "connected_devices",
            "target_device_id": device_id,
            "connected_devices": list(deduped.values()),
            "evidence_basis": sorted(evidence_ids),
        }

    # 2 & 4. Downstream / dependent devices (who depends on `device_id`?)
    def get_downstream_dependencies(
        self,
        device_id: str,
        max_depth: int = 6,
        max_visited: int = 500,
    ) -> Dict[str, Any]:
        """
        Traverses reverse `DEPENDS_ON` edges (`downstream -> upstream`) to find all devices
        directly or indirectly dependent on `device_id`.
        """
        cap_depth = max(1, min(max_depth, HARD_MAX_DEPTH))
        cap_visit = max(10, min(max_visited, HARD_MAX_VISITED))
        root = self._norm_dev_node(device_id)

        queue: deque[Tuple[str, int, List[str], List[str]]] = deque([(root, 0, [], [])])
        visited: Set[str] = {root}
        dependents: List[Dict[str, Any]] = []
        all_ev: Set[str] = set()

        while queue and len(visited) < cap_visit:
            curr, depth, path_nodes, path_ev = queue.popleft()
            if depth >= cap_depth:
                continue
            for eid in self.graph.in_edges.get(curr, []):
                edge = self.graph.edges.get(eid)
                if not edge or edge.relationship_type != GraphRelationshipType.DEPENDS_ON.value:
                    continue
                if edge.target_id != curr:
                    continue
                src_id = edge.source_id
                if src_id in visited:
                    continue
                visited.add(src_id)
                snode = self.graph.get_node(src_id)
                comb_ev = list(dict.fromkeys(path_ev + edge.evidence_ids))
                all_ev.update(edge.evidence_ids)
                next_path = path_nodes + [curr]
                if snode and snode.entity_type == GraphEntityType.DEVICE.value:
                    dependents.append(
                        {
                            "device_id": snode.device_id or src_id.replace("device:", ""),
                            "display_name": snode.label,
                            "hop_distance": depth + 1,
                            "dependency_type": "DIRECT" if depth == 0 else "INDIRECT",
                            "layer": edge.layer,
                            "is_inferred": edge.is_inferred,
                            "confidence": edge.confidence,
                            "freshness": edge.freshness,
                            "dependency_chain": [n.replace("device:", "") for n in next_path + [src_id]],
                            "evidence_ids": comb_ev,
                        }
                    )
                queue.append((src_id, depth + 1, next_path, comb_ev))

        return {
            "query": "downstream_dependencies",
            "target_device_id": device_id,
            "direct_dependents": [d for d in dependents if d["dependency_type"] == "DIRECT"],
            "indirect_dependents": [d for d in dependents if d["dependency_type"] == "INDIRECT"],
            "all_dependents": dependents,
            "evidence_basis": sorted(all_ev),
        }

    def get_dependent_devices(self, device_id: str, max_depth: int = 6) -> Dict[str, Any]:
        return self.get_downstream_dependencies(device_id=device_id, max_depth=max_depth)

    # 3. Upstream dependencies (what does `device_id` depend on?)
    def get_upstream_dependencies(
        self,
        device_id: str,
        max_depth: int = 6,
        max_visited: int = 500,
    ) -> Dict[str, Any]:
        cap_depth = max(1, min(max_depth, HARD_MAX_DEPTH))
        cap_visit = max(10, min(max_visited, HARD_MAX_VISITED))
        root = self._norm_dev_node(device_id)

        queue: deque[Tuple[str, int, List[str], List[str]]] = deque([(root, 0, [root], [])])
        visited: Set[str] = {root}
        upstreams: List[Dict[str, Any]] = []
        all_ev: Set[str] = set()

        while queue and len(visited) < cap_visit:
            curr, depth, chain, ev_acc = queue.popleft()
            if depth >= cap_depth:
                continue
            for eid in self.graph.out_edges.get(curr, []):
                edge = self.graph.edges.get(eid)
                if not edge or edge.relationship_type != GraphRelationshipType.DEPENDS_ON.value or edge.source_id != curr:
                    continue
                tgt_id = edge.target_id
                if tgt_id in visited:
                    continue
                visited.add(tgt_id)
                tnode = self.graph.get_node(tgt_id)
                comb_ev = list(dict.fromkeys(ev_acc + edge.evidence_ids))
                all_ev.update(edge.evidence_ids)
                new_chain = chain + [tgt_id]
                if tnode:
                    upstreams.append(
                        {
                            "node_id": tgt_id,
                            "entity_type": tnode.entity_type,
                            "device_id": tnode.device_id,
                            "label": tnode.label,
                            "hop_distance": depth + 1,
                            "layer": edge.layer,
                            "is_inferred": edge.is_inferred,
                            "confidence": edge.confidence,
                            "freshness": edge.freshness,
                            "chain": new_chain,
                            "evidence_ids": comb_ev,
                        }
                    )
                queue.append((tgt_id, depth + 1, new_chain, comb_ev))

        return {
            "query": "upstream_dependencies",
            "target_device_id": device_id,
            "upstreams": upstreams,
            "evidence_basis": sorted(all_ev),
        }

    # 5. Reachable network segments from a device
    def get_reachable_segments(
        self,
        device_id: str,
        include_inactive_routes: bool = False,
    ) -> Dict[str, Any]:
        dev_raw = device_id.replace("device:", "")
        segments: List[Dict[str, Any]] = []
        ev_ids: Set[str] = set()

        # Connected subnets via interfaces/IPs and RIB routes
        for node in self.graph.nodes.values():
            if node.device_id != dev_raw:
                continue
            if node.entity_type == GraphEntityType.IP_ADDRESS.value:
                cidr = node.attributes.get("network_cidr")
                if cidr:
                    ev_ids.update(node.evidence_ids)
                    segments.append(
                        {
                            "segment": cidr,
                            "reachability_basis": "CONNECTED_SUBNET",
                            "interface": node.attributes.get("interface_name"),
                            "is_inferred": False,
                            "evidence_ids": list(node.evidence_ids),
                        }
                    )
            elif node.entity_type == GraphEntityType.ROUTE.value:
                if not include_inactive_routes and (not node.attributes.get("active", True) or node.attributes.get("disabled") or node.attributes.get("unreachable")):
                    continue
                if node.attributes.get("route_type") in ("blackhole", "unreachable", "prohibit", "reject"):
                    continue
                pfx = node.attributes.get("dst_prefix")
                if pfx:
                    ev_ids.update(node.evidence_ids)
                    segments.append(
                        {
                            "segment": pfx,
                            "reachability_basis": f"RIB_ROUTE_{str(node.attributes.get('protocol') or 'static').upper()}",
                            "gateway": node.attributes.get("gateway"),
                            "interface": node.attributes.get("interface_name"),
                            "routing_table": node.attributes.get("routing_table") or "main",
                            "is_inferred": True,
                            "evidence_ids": list(node.evidence_ids),
                        }
                    )

        return {
            "query": "reachable_segments",
            "target_device_id": dev_raw,
            "segments": segments,
            "evidence_basis": sorted(ev_ids),
        }

    # 6. Routes using a selected next hop
    def get_routes_using_next_hop(
        self,
        next_hop_ip: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_nh = normalize_ip(next_hop_ip.strip()) or next_hop_ip.strip()
        matched_routes: List[Dict[str, Any]] = []
        ev_ids: Set[str] = set()

        for nh_node in self.graph.nodes_by_type(GraphEntityType.NEXT_HOP.value):
            if nh_node.attributes.get("gateway_ip") != clean_nh:
                continue
            if device_id and nh_node.device_id != device_id.replace("device:", ""):
                continue
            for eid in self.graph.out_edges.get(nh_node.node_id, []):
                edge = self.graph.edges.get(eid)
                if not edge or edge.relationship_type != GraphRelationshipType.NEXT_HOP_OF.value:
                    continue
                rnode = self.graph.get_node(edge.target_id)
                if rnode and rnode.entity_type == GraphEntityType.ROUTE.value:
                    ev_ids.update(rnode.evidence_ids)
                    matched_routes.append(
                        {
                            "route_node_id": rnode.node_id,
                            "device_id": rnode.device_id,
                            "dst_prefix": rnode.attributes.get("dst_prefix"),
                            "routing_table": rnode.attributes.get("routing_table"),
                            "protocol": rnode.attributes.get("protocol"),
                            "distance": rnode.attributes.get("distance"),
                            "active": rnode.attributes.get("active"),
                            "evidence_ids": list(rnode.evidence_ids),
                        }
                    )

        return {
            "query": "routes_using_next_hop",
            "next_hop_ip": clean_nh,
            "routes": matched_routes,
            "evidence_basis": sorted(ev_ids),
        }

    # 7. Interfaces carrying a selected VLAN
    def get_interfaces_carrying_vlan(
        self,
        vlan_id: int,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        vlan_node_id = f"vlan:global:{int(vlan_id)}"
        carriers: List[Dict[str, Any]] = []
        ev_ids: Set[str] = set()

        for eid in self.graph.in_edges.get(vlan_node_id, []):
            edge = self.graph.edges.get(eid)
            if not edge or edge.relationship_type != GraphRelationshipType.CARRIES.value:
                continue
            if_node = self.graph.get_node(edge.source_id)
            if not if_node:
                continue
            if device_id and if_node.device_id != device_id.replace("device:", ""):
                continue
            ev_ids.update(edge.evidence_ids)
            carriers.append(
                {
                    "interface_node_id": if_node.node_id,
                    "device_id": if_node.device_id,
                    "interface_name": if_node.attributes.get("interface_name") or if_node.label.split(":")[-1],
                    "vlan_mode": edge.attributes.get("vlan_mode", "tagged"),
                    "oper_status": if_node.attributes.get("oper_status", "unknown"),
                    "evidence_ids": list(edge.evidence_ids),
                }
            )

        return {
            "query": "interfaces_carrying_vlan",
            "vlan_id": int(vlan_id),
            "interfaces": carriers,
            "evidence_basis": sorted(ev_ids),
        }

    # 8. Devices participating in a selected protocol
    def get_protocol_participants(self, protocol: str) -> Dict[str, Any]:
        proto_clean = protocol.strip().lower()
        participants: List[Dict[str, Any]] = []
        ev_ids: Set[str] = set()

        for pnode in self.graph.nodes_by_type(GraphEntityType.ROUTING_PROTOCOL_INSTANCE.value):
            if str(pnode.attributes.get("protocol") or "").lower() != proto_clean:
                continue
            dev_id = pnode.device_id
            peers: List[Dict[str, Any]] = []
            for eid in self.graph.out_edges.get(pnode.node_id, []):
                edge = self.graph.edges.get(eid)
                if edge and edge.relationship_type == GraphRelationshipType.PEERS_WITH.value:
                    tnode = self.graph.get_node(edge.target_id)
                    if tnode:
                        peers.append(
                            {
                                "peer_node_id": tnode.node_id,
                                "label": tnode.label,
                                "state": edge.attributes.get("state") or tnode.attributes.get("state"),
                            }
                        )
            ev_ids.update(pnode.evidence_ids)
            participants.append(
                {
                    "device_id": dev_id,
                    "protocol": proto_clean,
                    "instance_node_id": pnode.node_id,
                    "attributes": dict(pnode.attributes),
                    "peers": peers,
                    "evidence_ids": list(pnode.evidence_ids),
                }
            )

        return {
            "query": "protocol_participants",
            "protocol": proto_clean,
            "participants": participants,
            "evidence_basis": sorted(ev_ids),
        }

    # 9. Services affected by a device
    def get_affected_services(self, device_id: str) -> Dict[str, Any]:
        dev_node = self._norm_dev_node(device_id)
        downstream = self.get_downstream_dependencies(device_id)
        impacted_devs = {device_id.replace("device:", "")} | {d["device_id"] for d in downstream["all_dependents"]}

        services: List[Dict[str, Any]] = []
        ev_ids: Set[str] = set(downstream["evidence_basis"])

        for snode in self.graph.nodes_by_type(GraphEntityType.SERVICE_ENDPOINT.value):
            for eid in self.graph.in_edges.get(snode.node_id, []):
                edge = self.graph.edges.get(eid)
                if not edge:
                    continue
                holder = self.graph.get_node(edge.source_id)
                if holder and (holder.device_id in impacted_devs or edge.source_id == dev_node):
                    ev_ids.update(edge.evidence_ids)
                    services.append(
                        {
                            "service_node_id": snode.node_id,
                            "label": snode.label,
                            "dependent_device_id": holder.device_id,
                            "service_type": snode.attributes.get("service_type"),
                            "evidence_ids": list(edge.evidence_ids),
                        }
                    )

        # Also check WAN connections hosted on or depended upon through impacted devices
        for wnode in self.graph.nodes_by_type(GraphEntityType.WAN_CONNECTION.value):
            if wnode.device_id == device_id.replace("device:", ""):
                ev_ids.update(wnode.evidence_ids)
                services.append(
                    {
                        "service_node_id": wnode.node_id,
                        "label": wnode.label,
                        "dependent_device_id": wnode.device_id,
                        "service_type": "wan_egress",
                        "evidence_ids": list(wnode.evidence_ids),
                    }
                )

        return {
            "query": "affected_services",
            "target_device_id": device_id,
            "services": services,
            "impacted_device_ids": sorted(impacted_devs),
            "evidence_basis": sorted(ev_ids),
        }

    # 10. Potential alternate paths between devices (excluding failed entities)
    def find_alternate_paths(
        self,
        source_device_id: str,
        target_device_id: str,
        excluded_ids: Optional[Set[str]] = None,
        max_depth: int = 8,
        max_paths: int = 5,
    ) -> Dict[str, Any]:
        cap_depth = max(1, min(max_depth, HARD_MAX_DEPTH))
        src = self._norm_dev_node(source_device_id)
        dst = self._norm_dev_node(target_device_id)
        excluded_norm: Set[str] = set()
        for x in excluded_ids or set():
            excluded_norm.add(x)
            if not x.startswith("device:") and ":" not in x:
                excluded_norm.add(f"device:{x}")

        if src in excluded_norm or dst in excluded_norm or src not in self.graph.nodes or dst not in self.graph.nodes:
            return {
                "query": "alternate_paths",
                "source_device_id": source_device_id,
                "target_device_id": target_device_id,
                "paths": [],
                "evidence_basis": [],
            }

        traversal_rels = {
            GraphRelationshipType.PHYSICAL_ADJACENCY.value,
            GraphRelationshipType.LAYER2_ADJACENCY.value,
            GraphRelationshipType.LAYER3_REACHABILITY.value,
            GraphRelationshipType.DEPENDS_ON.value,
            GraphRelationshipType.PEERS_WITH.value,
        }

        found_paths: List[Dict[str, Any]] = []
        all_ev: Set[str] = set()
        queue: deque[Tuple[str, List[str], List[str], List[str], bool]] = deque([(src, [src], [], [], False)])
        iterations = 0

        while queue and len(found_paths) < max_paths and iterations < HARD_MAX_VISITED:
            iterations += 1
            curr, node_chain, rel_chain, ev_chain, any_inferred = queue.popleft()
            if curr == dst and len(node_chain) > 1:
                found_paths.append(
                    {
                        "devices": [n.replace("device:", "") for n in node_chain],
                        "hop_count": len(node_chain) - 1,
                        "relationships": rel_chain,
                        "contains_inferred_edges": any_inferred,
                        "evidence_ids": ev_chain,
                    }
                )
                all_ev.update(ev_chain)
                continue

            if len(node_chain) - 1 >= cap_depth:
                continue

            for eid in self.graph.out_edges.get(curr, []):
                if eid in excluded_norm:
                    continue
                edge = self.graph.edges.get(eid)
                if not edge or edge.relationship_type not in traversal_rels:
                    continue
                nxt = edge.target_id if edge.source_id == curr else edge.source_id
                if nxt in excluded_norm or nxt in node_chain:
                    continue
                tnode = self.graph.get_node(nxt)
                if not tnode or tnode.entity_type != GraphEntityType.DEVICE.value:
                    continue
                queue.append(
                    (
                        nxt,
                        node_chain + [nxt],
                        rel_chain + [f"{edge.relationship_type}({edge.layer})"],
                        list(dict.fromkeys(ev_chain + edge.evidence_ids)),
                        any_inferred or edge.is_inferred,
                    )
                )

        return {
            "query": "alternate_paths",
            "source_device_id": source_device_id,
            "target_device_id": target_device_id,
            "excluded_ids": sorted(excluded_norm),
            "paths": found_paths,
            "evidence_basis": sorted(all_ev),
        }

    # 11. Dynamic discovery of gateway, edge, or WAN boundary nodes (REC-19)
    def find_gateway_nodes(self) -> List[str]:
        """Dynamically identifies edge/gateway/ISP boundary nodes from knowledge graph or inventory."""
        gw_nodes: List[str] = []
        for nid, node in self.graph.nodes.items():
            if not nid.startswith("device:"):
                continue
            dev_name = nid.replace("device:", "")
            props = getattr(node, "attributes", None) or getattr(node, "properties", {}) or {}
            role = str(props.get("role") or "").lower()
            label = str(node.label or "").lower()
            device_type = str(props.get("device_type") or "").lower()
            if (
                role in ("edge", "gateway", "isp", "wan", "border", "uplink")
                or any(k in label for k in ("isp", "edge", "gateway", "border", "wan"))
                or device_type in ("gateway", "edge_router")
            ):
                gw_nodes.append(dev_name)

        if not gw_nodes:
            try:
                import sqlite3
                from core.topology_db import topology_transaction
                with topology_transaction(write=False) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT name FROM operational_devices 
                        WHERE LOWER(role) IN ('edge', 'gateway', 'wan', 'isp', 'border') 
                           OR LOWER(name) LIKE '%isp%' 
                           OR LOWER(name) LIKE '%edge%' 
                           OR LOWER(name) LIKE '%gateway%'
                        """
                    ).fetchall()
                    for r in rows:
                        gw_nodes.append(r["name"])
            except Exception:
                pass

        # If none specifically labeled as gateway, use any other device in graph as target
        if not gw_nodes:
            for nid in self.graph.nodes:
                if nid.startswith("device:"):
                    gw_nodes.append(nid.replace("device:", ""))

        return gw_nodes or ["ISP-Edge"]
