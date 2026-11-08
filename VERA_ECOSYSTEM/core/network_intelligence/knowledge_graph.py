"""
AIRA OS — Multi-Layer Network Knowledge Graph & Historical Snapshot Projector (Networking VI / WP 6.2).

Constructs a rich, directed multi-layer graph over unified network evidence supporting:
- All 21 `GraphEntityType` node classes
- All 18 `GraphRelationshipType` edge classes
- Parallel edges, cycles, ECMP/redundant links, partial discovery, asymmetric knowledge, and multi-homing
- Strict epistemic separation:
  * Subnet overlap -> `MEMBER_OF` / `CONNECTS_TO` `SUBNET` (NEVER `PHYSICAL_ADJACENCY`)
  * ARP entry -> `LAYER2_ADJACENCY` (NEVER `PHYSICAL_ADJACENCY`)
  * RIB next-hop -> `NEXT_HOP_OF` / `DEPENDS_ON` with `is_inferred=True`
- Graph consistency validation (`validate_consistency`) tolerant of partial network discovery
- Immutable historical snapshot projection & snapshot-to-snapshot structural comparison
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import ipaddress
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.network_intelligence.entity_resolver import EntityResolver
from core.network_intelligence.evidence_service import evaluate_evidence_freshness
from core.network_intelligence.intelligence_models import (
    EvidenceCompleteness,
    GraphConsistencyIssue,
    GraphConsistencyReport,
    GraphEntityType,
    GraphLayer,
    GraphRelationshipType,
    IntelligenceFreshness,
    KnowledgeEdge,
    KnowledgeNode,
    NetworkEvidenceBundle,
)
from core.routing.unified_route_parser import NormalizedRoute, RouteType
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, get_topology_connection
from core.topology_models import normalize_ip, normalize_mac
from pathlib import Path

TUNNEL_IFACE_TYPES: Set[str] = {
    "gre",
    "gre-tunnel",
    "ipip",
    "ipip-tunnel",
    "eoip",
    "eoip-tunnel",
    "wg",
    "wireguard",
    "l2tp",
    "l2tp-in",
    "l2tp-out",
    "pppoe-out",
    "pppoe-in",
    "pptp-out",
    "sstp-out",
    "ovpn-out",
    "ovpn-in",
    "ipsec",
}


def _edge_id(rel_type: str, src: str, dst: str, discriminator: str = "") -> str:
    raw = f"{rel_type}|{src}|{dst}|{discriminator}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"kedge_{rel_type.lower()[:12]}_{digest}"


class NetworkKnowledgeGraph:
    """
    Directed multi-layer network knowledge representation supporting parallel edges,
    cycles, partial knowledge, and full evidence provenance.
    """

    def __init__(self, built_at: Optional[float] = None, snapshot_ref: Optional[str] = None) -> None:
        self.built_at: float = float(built_at) if built_at is not None else time.time()
        self.snapshot_ref: Optional[str] = snapshot_ref
        self.nodes: Dict[str, KnowledgeNode] = {}
        self.edges: Dict[str, KnowledgeEdge] = {}
        self.out_edges: Dict[str, List[str]] = {}
        self.in_edges: Dict[str, List[str]] = {}
        self.resolver: EntityResolver = EntityResolver()
        self._duplicate_edge_attempts: List[Tuple[str, str, str]] = []

    def add_node(self, node: KnowledgeNode) -> KnowledgeNode:
        existing = self.nodes.get(node.node_id)
        if existing is None:
            self.nodes[node.node_id] = node
            self.out_edges.setdefault(node.node_id, [])
            self.in_edges.setdefault(node.node_id, [])
            return node
        # Merge non-destructively: union evidence IDs and enrich attributes
        for ev_id in node.evidence_ids:
            if ev_id and ev_id not in existing.evidence_ids:
                existing.evidence_ids.append(ev_id)
        for k, v in node.attributes.items():
            if v is not None and (k not in existing.attributes or existing.attributes[k] in (None, "", "unknown")):
                existing.attributes[k] = v
        existing.confidence = max(existing.confidence, node.confidence)
        return existing

    def add_edge(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        if edge.edge_id in self.edges:
            self._duplicate_edge_attempts.append((edge.source_id, edge.target_id, edge.relationship_type))
            existing = self.edges[edge.edge_id]
            for ev_id in edge.evidence_ids:
                if ev_id and ev_id not in existing.evidence_ids:
                    existing.evidence_ids.append(ev_id)
            existing.confidence = max(existing.confidence, edge.confidence)
            return existing

        self.edges[edge.edge_id] = edge
        self.out_edges.setdefault(edge.source_id, []).append(edge.edge_id)
        self.in_edges.setdefault(edge.target_id, []).append(edge.edge_id)
        if edge.bidirectional:
            # Also index reverse traversal seamlessly without duplicating edge object
            if edge.edge_id not in self.out_edges.setdefault(edge.target_id, []):
                self.out_edges[edge.target_id].append(edge.edge_id)
            if edge.edge_id not in self.in_edges.setdefault(edge.source_id, []):
                self.in_edges[edge.source_id].append(edge.edge_id)
        return edge

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        return self.nodes.get(node_id)

    def nodes_by_type(self, entity_type: str) -> List[KnowledgeNode]:
        return [n for n in self.nodes.values() if n.entity_type == entity_type]

    def edges_by_type(self, relationship_type: str) -> List[KnowledgeEdge]:
        return [e for e in self.edges.values() if e.relationship_type == relationship_type]

    # ------------------------------------------------------------------
    # Graph Construction from NetworkEvidenceBundle
    # ------------------------------------------------------------------
    @classmethod
    def from_evidence_bundle(
        cls,
        bundle: NetworkEvidenceBundle,
        now: Optional[float] = None,
    ) -> "NetworkKnowledgeGraph":
        curr_ts = float(now) if now is not None else bundle.assembled_at
        graph = cls(built_at=curr_ts, snapshot_ref=bundle.topology_snapshot_ref)
        resolved_devs = graph.resolver.resolve_from_bundle(bundle)

        # Index evidence IDs per (device_id, evidence_type)
        ev_lookup: Dict[Tuple[str, str], List[str]] = {}
        for rec in bundle.records:
            ev_lookup.setdefault((rec.device_id, rec.evidence_type), []).append(rec.evidence_id)

        # 1. Devices, Telemetry Observations & Snapshots
        for dev_id, rdev in resolved_devs.items():
            dinfo = bundle.device_evidence.get(dev_id, {})
            dev_ev_ids = ev_lookup.get((dev_id, "device_resources"), [])
            obs_ts = dinfo.get("last_check_at")
            dev_fresh = evaluate_evidence_freshness("device_resources", obs_ts, curr_ts)
            dev_node_id = EntityResolver.canonical_device_node_id(dev_id)

            graph.add_node(
                KnowledgeNode(
                    node_id=dev_node_id,
                    entity_type=GraphEntityType.DEVICE.value,
                    label=rdev.display_name,
                    device_id=dev_id,
                    attributes={
                        "device_id": dev_id,
                        "identity": rdev.routeros_identity,
                        "management_ip": rdev.management_ip,
                        "mac_address": rdev.known_macs[0] if rdev.known_macs else "",
                        "model": dinfo.get("model") or "",
                        "routeros_version": dinfo.get("routeros_version") or "",
                        "device_type": dinfo.get("device_type") or "router",
                        "is_managed": rdev.is_managed,
                        "reachability_status": dinfo.get("reachability_status") or "UNKNOWN",
                        "cpu_load_percent": dinfo.get("cpu_load_percent"),
                        "memory_used_percent": dinfo.get("memory_used_percent"),
                        "latency_ms": dinfo.get("latency_ms"),
                        "uptime_seconds": dinfo.get("uptime_seconds"),
                    },
                    evidence_ids=list(dev_ev_ids),
                    provenance=",".join(rdev.provenance),
                    confidence=rdev.identity_confidence,
                    observed_at=obs_ts,
                    freshness=dev_fresh,
                    completeness=EvidenceCompleteness.PARTIAL.value if rdev.is_partial else EvidenceCompleteness.COMPLETE.value,
                )
            )

            # Telemetry Observation node (when resource metrics exist)
            if dinfo.get("cpu_load_percent") is not None or dinfo.get("latency_ms") is not None:
                tel_id = f"telemetry:{dev_id}:resources"
                graph.add_node(
                    KnowledgeNode(
                        node_id=tel_id,
                        entity_type=GraphEntityType.TELEMETRY_OBSERVATION.value,
                        label=f"Telemetry {rdev.display_name}",
                        device_id=dev_id,
                        attributes={
                            "cpu_load_percent": dinfo.get("cpu_load_percent"),
                            "memory_used_percent": dinfo.get("memory_used_percent"),
                            "latency_ms": dinfo.get("latency_ms"),
                            "packet_loss_percent": dinfo.get("packet_loss_percent"),
                        },
                        evidence_ids=list(dev_ev_ids),
                        provenance="nms_telemetry",
                        confidence=0.92,
                        observed_at=obs_ts,
                        freshness=dev_fresh,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.OBSERVED_BY.value, tel_id, dev_node_id),
                        source_id=tel_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.OBSERVED_BY.value,
                        layer=GraphLayer.TELEMETRY.value,
                        evidence_ids=list(dev_ev_ids),
                        provenance="nms_telemetry",
                        confidence=0.95,
                        observed_at=obs_ts,
                        freshness=dev_fresh,
                    )
                )

            # Configuration / Route Snapshot reference node
            snap_id = bundle.route_snapshot_refs.get(dev_id)
            if snap_id:
                csnap_node_id = f"cfgsnap:{dev_id}:{snap_id}"
                graph.add_node(
                    KnowledgeNode(
                        node_id=csnap_node_id,
                        entity_type=GraphEntityType.CONFIGURATION_SNAPSHOT.value,
                        label=f"Snapshot {snap_id}",
                        device_id=dev_id,
                        attributes={"snapshot_id": snap_id, "snapshot_type": "route_snapshot"},
                        evidence_ids=ev_lookup.get((dev_id, "routes"), []),
                        provenance="route_snapshots",
                        confidence=0.95,
                        observed_at=obs_ts,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.OBSERVED_BY.value, csnap_node_id, dev_node_id),
                        source_id=csnap_node_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.OBSERVED_BY.value,
                        layer=GraphLayer.LOGICAL.value,
                        evidence_ids=ev_lookup.get((dev_id, "routes"), []),
                        provenance="route_snapshots",
                        confidence=0.95,
                    )
                )

            # Optional DNS Service Endpoint if configured
            pdata = bundle.protocol_evidence.get(dev_id, {})
            dns_data = pdata.get("dns")
            if isinstance(dns_data, dict):
                for srv in dns_data.get("servers") or []:
                    srv_ip = normalize_ip(str(srv))
                    if srv_ip:
                        svc_id = f"service:dns:{srv_ip}"
                        graph.add_node(
                            KnowledgeNode(
                                node_id=svc_id,
                                entity_type=GraphEntityType.SERVICE_ENDPOINT.value,
                                label=f"DNS {srv_ip}",
                                attributes={"service_type": "dns", "address": srv_ip, "port": 53},
                                evidence_ids=ev_lookup.get((dev_id, "dns"), []),
                                provenance="routeros_dns",
                                confidence=0.90,
                            )
                        )
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.DEPENDS_ON.value, dev_node_id, svc_id, "dns"),
                                source_id=dev_node_id,
                                target_id=svc_id,
                                relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                                layer=GraphLayer.LOGICAL.value,
                                is_inferred=True,
                                evidence_ids=ev_lookup.get((dev_id, "dns"), []),
                                provenance="dns_configuration",
                                confidence=0.85,
                            )
                        )

        # 2. Interfaces, Tunnels, Bridges & VLANs
        for dev_id, ifaces in bundle.interface_evidence.items():
            dev_node_id = EntityResolver.canonical_device_node_id(dev_id)
            if_ev_ids = ev_lookup.get((dev_id, "interfaces"), [])
            for iface in ifaces:
                iname = str(iface.get("interface_name") or "").strip()
                if not iname:
                    continue
                itype = str(iface.get("interface_type") or "ether").lower()
                if_node_id = EntityResolver.canonical_interface_node_id(dev_id, iname)
                if_ts = iface.get("last_counter_update")
                if_fresh = evaluate_evidence_freshness("interfaces", if_ts, curr_ts)

                graph.add_node(
                    KnowledgeNode(
                        node_id=if_node_id,
                        entity_type=GraphEntityType.INTERFACE.value,
                        label=f"{dev_id}:{iname}",
                        device_id=dev_id,
                        attributes=dict(iface),
                        evidence_ids=list(if_ev_ids),
                        provenance="nms_interfaces",
                        confidence=0.95,
                        observed_at=if_ts,
                        freshness=if_fresh,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, if_node_id, dev_node_id),
                        source_id=if_node_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.HOSTED_ON.value,
                        layer=GraphLayer.PHYSICAL.value,
                        evidence_ids=list(if_ev_ids),
                        provenance="interface_inventory",
                        confidence=0.99,
                        observed_at=if_ts,
                        freshness=if_fresh,
                    )
                )

                if itype == "bridge":
                    br_id = f"bridge:{dev_id}:{iname}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=br_id,
                            entity_type=GraphEntityType.BRIDGE.value,
                            label=f"Bridge {iname} ({dev_id})",
                            device_id=dev_id,
                            attributes={"bridge_name": iname, "oper_status": iface.get("oper_status")},
                            evidence_ids=list(if_ev_ids),
                            provenance="interface_bridge",
                            confidence=0.95,
                            observed_at=if_ts,
                            freshness=if_fresh,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, br_id, dev_node_id),
                            source_id=br_id,
                            target_id=dev_node_id,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            layer=GraphLayer.LAYER2.value,
                            evidence_ids=list(if_ev_ids),
                            provenance="interface_bridge",
                            confidence=0.98,
                        )
                    )
                elif itype in TUNNEL_IFACE_TYPES:
                    tun_id = f"tunnel:{dev_id}:{iname}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=tun_id,
                            entity_type=GraphEntityType.TUNNEL.value,
                            label=f"Tunnel {iname} ({itype})",
                            device_id=dev_id,
                            attributes={
                                "tunnel_type": itype,
                                "interface_name": iname,
                                "oper_status": iface.get("oper_status"),
                                "mtu": iface.get("mtu"),
                            },
                            evidence_ids=list(if_ev_ids),
                            provenance="interface_tunnel",
                            confidence=0.92,
                            observed_at=if_ts,
                            freshness=if_fresh,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, tun_id, dev_node_id),
                            source_id=tun_id,
                            target_id=dev_node_id,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            layer=GraphLayer.TUNNEL.value,
                            evidence_ids=list(if_ev_ids),
                            provenance="interface_tunnel",
                            confidence=0.95,
                        )
                    )

        # Explicit protocol Tunnels, Bridges, Bridge Ports & VLANs
        for dev_id, pdata in bundle.protocol_evidence.items():
            dev_node_id = EntityResolver.canonical_device_node_id(dev_id)

            # Explicit Tunnels list
            for tun in pdata.get("tunnels") or []:
                if not isinstance(tun, dict):
                    continue
                tname = str(tun.get("name") or tun.get("interface_name") or "tun0")
                ttype = str(tun.get("tunnel_type") or tun.get("type") or "gre").lower()
                tun_id = f"tunnel:{dev_id}:{tname}"
                tun_ev = ev_lookup.get((dev_id, "tunnels"), [])
                graph.add_node(
                    KnowledgeNode(
                        node_id=tun_id,
                        entity_type=GraphEntityType.TUNNEL.value,
                        label=f"Tunnel {tname} ({ttype})",
                        device_id=dev_id,
                        attributes=dict(tun),
                        evidence_ids=list(tun_ev),
                        provenance="tunnel_config",
                        confidence=0.95,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, tun_id, dev_node_id),
                        source_id=tun_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.HOSTED_ON.value,
                        layer=GraphLayer.TUNNEL.value,
                        evidence_ids=list(tun_ev),
                        provenance="tunnel_config",
                        confidence=0.95,
                    )
                )
                rem_ip = normalize_ip(str(tun.get("remote_address") or ""))
                if rem_ip:
                    peer_dev, pconf, _ = graph.resolver.resolve_peer_by_ip(rem_ip, exclude_device_id=dev_id)
                    if peer_dev:
                        peer_node_id = EntityResolver.canonical_device_node_id(peer_dev)
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.CONNECTS_TO.value, tun_id, peer_node_id),
                                source_id=tun_id,
                                target_id=peer_node_id,
                                relationship_type=GraphRelationshipType.CONNECTS_TO.value,
                                layer=GraphLayer.TUNNEL.value,
                                is_inferred=True,
                                evidence_ids=list(tun_ev),
                                provenance="tunnel_remote_endpoint",
                                confidence=pconf,
                            )
                        )

            # Bridge Ports
            for bp in pdata.get("bridge_ports") or []:
                if not isinstance(bp, dict):
                    continue
                bname = str(bp.get("bridge") or "bridge1")
                pname = str(bp.get("interface") or "")
                if not pname:
                    continue
                br_id = f"bridge:{dev_id}:{bname}"
                if_id = EntityResolver.canonical_interface_node_id(dev_id, pname)
                bp_ev = ev_lookup.get((dev_id, "bridge_ports"), [])
                graph.add_node(
                    KnowledgeNode(
                        node_id=br_id,
                        entity_type=GraphEntityType.BRIDGE.value,
                        label=f"Bridge {bname} ({dev_id})",
                        device_id=dev_id,
                        attributes={"bridge_name": bname},
                        evidence_ids=list(bp_ev),
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, br_id, dev_node_id),
                        source_id=br_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.HOSTED_ON.value,
                        layer=GraphLayer.LAYER2.value,
                        evidence_ids=list(bp_ev),
                    )
                )
                if if_id not in graph.nodes:
                    graph.add_node(
                        KnowledgeNode(
                            node_id=if_id,
                            entity_type=GraphEntityType.INTERFACE.value,
                            label=f"{dev_id}:{pname}",
                            device_id=dev_id,
                            attributes={"interface_name": pname},
                            evidence_ids=list(bp_ev),
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, if_id, dev_node_id),
                            source_id=if_id,
                            target_id=dev_node_id,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            layer=GraphLayer.PHYSICAL.value,
                            evidence_ids=list(bp_ev),
                        )
                    )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.MEMBER_OF.value, if_id, br_id),
                        source_id=if_id,
                        target_id=br_id,
                        relationship_type=GraphRelationshipType.MEMBER_OF.value,
                        layer=GraphLayer.LAYER2.value,
                        evidence_ids=list(bp_ev),
                        provenance="bridge_port_table",
                        confidence=0.95,
                        attributes={"pvid": bp.get("pvid", 1)},
                    )
                )

            # VLANs & Bridge VLANs
            vlan_entries = list(pdata.get("bridge_vlan") or []) + list(pdata.get("vlans") or [])
            vlan_ev = ev_lookup.get((dev_id, "bridge_vlan"), []) + ev_lookup.get((dev_id, "vlans"), [])
            for vl in vlan_entries:
                if not isinstance(vl, dict) or vl.get("disabled") or vl.get("is_disabled"):
                    continue
                vid_raw = (
                    vl.get("vlan_id")
                    if vl.get("vlan_id") is not None
                    else (vl.get("vlan_ids") if vl.get("vlan_ids") is not None else vl.get("vlan-ids"))
                )
                if vid_raw is None:
                    continue
                parsed_vids: List[int] = []
                raw_items = vid_raw if isinstance(vid_raw, (list, tuple, set)) else str(vid_raw).split(",")
                for item in raw_items:
                    token = str(item).strip()
                    if not token:
                        continue
                    if "-" in token:
                        try:
                            lo, hi = token.split("-", 1)
                            for v_i in range(int(lo), min(int(hi) + 1, int(lo) + 32)):
                                parsed_vids.append(v_i)
                        except ValueError:
                            continue
                    else:
                        try:
                            parsed_vids.append(int(token))
                        except ValueError:
                            continue
                if not parsed_vids:
                    continue

                tagged = vl.get("tagged") or vl.get("tagged_interfaces") or []
                untagged = vl.get("untagged") or vl.get("untagged_interfaces") or []
                if isinstance(tagged, str):
                    tagged = [x.strip() for x in tagged.split(",") if x.strip()]
                if isinstance(untagged, str):
                    untagged = [x.strip() for x in untagged.split(",") if x.strip()]
                single_if = vl.get("interface")
                if single_if and single_if not in tagged and single_if not in untagged:
                    tagged = list(tagged) + [single_if]

                for vid in parsed_vids:
                    vlan_node_id = f"vlan:global:{vid}"
                    seg_node_id = f"segment:vlan:{vid}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=vlan_node_id,
                            entity_type=GraphEntityType.VLAN.value,
                            label=f"VLAN {vid}",
                            attributes={"vlan_id": vid, "name": vl.get("name") or f"vlan{vid}"},
                            evidence_ids=list(vlan_ev),
                            provenance="bridge_vlan",
                            confidence=0.95,
                        )
                    )
                    graph.add_node(
                        KnowledgeNode(
                            node_id=seg_node_id,
                            entity_type=GraphEntityType.NETWORK_SEGMENT.value,
                            label=f"L2 Segment VLAN {vid}",
                            attributes={"vlan_id": vid, "segment_type": "vlan_broadcast_domain"},
                            evidence_ids=list(vlan_ev),
                            provenance="bridge_vlan",
                            confidence=0.90,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.MEMBER_OF.value, vlan_node_id, seg_node_id),
                            source_id=vlan_node_id,
                            target_id=seg_node_id,
                            relationship_type=GraphRelationshipType.MEMBER_OF.value,
                            layer=GraphLayer.LAYER2.value,
                            evidence_ids=list(vlan_ev),
                            provenance="vlan_segment",
                            confidence=0.92,
                        )
                    )

                    for port_name, mode in [(p, "tagged") for p in tagged] + [(p, "untagged") for p in untagged]:
                        if_id = EntityResolver.canonical_interface_node_id(dev_id, port_name)
                        if if_id not in graph.nodes:
                            graph.add_node(
                                KnowledgeNode(
                                    node_id=if_id,
                                    entity_type=GraphEntityType.INTERFACE.value,
                                    label=f"{dev_id}:{port_name}",
                                    device_id=dev_id,
                                    attributes={"interface_name": port_name},
                                    evidence_ids=list(vlan_ev),
                                )
                            )
                            graph.add_edge(
                                KnowledgeEdge(
                                    edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, if_id, dev_node_id),
                                    source_id=if_id,
                                    target_id=dev_node_id,
                                    relationship_type=GraphRelationshipType.HOSTED_ON.value,
                                    layer=GraphLayer.PHYSICAL.value,
                                    evidence_ids=list(vlan_ev),
                                )
                            )
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.CARRIES.value, if_id, vlan_node_id, mode),
                                source_id=if_id,
                                target_id=vlan_node_id,
                                relationship_type=GraphRelationshipType.CARRIES.value,
                                layer=GraphLayer.LAYER2.value,
                                evidence_ids=list(vlan_ev),
                                provenance="bridge_vlan_membership",
                                confidence=0.95,
                                attributes={"vlan_mode": mode, "vlan_id": vid},
                            )
                        )

            # 3. IP Addresses & Subnets (Subnet overlap -> MEMBER_OF/CONNECTS_TO SUBNET, NEVER PHYSICAL_ADJACENCY)
            ip_ev = ev_lookup.get((dev_id, "ip_addresses"), [])
            for ip_rec in pdata.get("ip_addresses") or []:
                if not isinstance(ip_rec, dict) or ip_rec.get("disabled") or ip_rec.get("is_disabled"):
                    continue
                raw_cidr = str(ip_rec.get("address") or "").strip()
                if "/" not in raw_cidr and ip_rec.get("prefix_len") is not None:
                    raw_cidr = f"{raw_cidr}/{ip_rec['prefix_len']}"
                if not raw_cidr:
                    continue
                try:
                    ip_if = ipaddress.ip_interface(raw_cidr)
                except ValueError:
                    continue
                addr_str = str(ip_if.ip)
                plen = ip_if.network.prefixlen
                net_cidr = str(ip_if.network)
                ifname = str(ip_rec.get("interface") or ip_rec.get("interface_name") or "").strip()

                ip_node_id = f"ip:{dev_id}:{addr_str}/{plen}"
                sub_node_id = f"subnet:main:{net_cidr}"
                seg_sub_id = f"segment:subnet:{net_cidr}"

                graph.add_node(
                    KnowledgeNode(
                        node_id=ip_node_id,
                        entity_type=GraphEntityType.IP_ADDRESS.value,
                        label=f"{addr_str}/{plen}",
                        device_id=dev_id,
                        attributes={
                            "address": addr_str,
                            "prefix_len": plen,
                            "network_cidr": net_cidr,
                            "interface_name": ifname,
                            "family": "ipv6" if ip_if.version == 6 else "ipv4",
                        },
                        evidence_ids=list(ip_ev),
                        provenance="ip_addresses",
                        confidence=0.96,
                    )
                )
                graph.add_node(
                    KnowledgeNode(
                        node_id=sub_node_id,
                        entity_type=GraphEntityType.SUBNET.value,
                        label=net_cidr,
                        attributes={"network_cidr": net_cidr, "prefix_len": plen, "vrf": "main"},
                        evidence_ids=list(ip_ev),
                        provenance="ip_addresses",
                        confidence=0.95,
                    )
                )
                graph.add_node(
                    KnowledgeNode(
                        node_id=seg_sub_id,
                        entity_type=GraphEntityType.NETWORK_SEGMENT.value,
                        label=f"Subnet Segment {net_cidr}",
                        attributes={"subnet_cidr": net_cidr, "segment_type": "l3_subnet"},
                        evidence_ids=list(ip_ev),
                        provenance="ip_addresses",
                        confidence=0.90,
                    )
                )

                target_holder = (
                    EntityResolver.canonical_interface_node_id(dev_id, ifname)
                    if ifname and EntityResolver.canonical_interface_node_id(dev_id, ifname) in graph.nodes
                    else dev_node_id
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.ADDRESSED_WITH.value, target_holder, ip_node_id),
                        source_id=target_holder,
                        target_id=ip_node_id,
                        relationship_type=GraphRelationshipType.ADDRESSED_WITH.value,
                        layer=GraphLayer.LAYER3.value,
                        evidence_ids=list(ip_ev),
                        provenance="ip_addresses",
                        confidence=0.96,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.MEMBER_OF.value, ip_node_id, sub_node_id),
                        source_id=ip_node_id,
                        target_id=sub_node_id,
                        relationship_type=GraphRelationshipType.MEMBER_OF.value,
                        layer=GraphLayer.LAYER3.value,
                        evidence_ids=list(ip_ev),
                        provenance="subnet_derivation",
                        confidence=0.98,
                    )
                )
                if target_holder.startswith("iface:"):
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.CONNECTS_TO.value, target_holder, seg_sub_id),
                            source_id=target_holder,
                            target_id=seg_sub_id,
                            relationship_type=GraphRelationshipType.CONNECTS_TO.value,
                            layer=GraphLayer.LAYER3.value,
                            evidence_ids=list(ip_ev),
                            provenance="interface_subnet_attachment",
                            confidence=0.92,
                        )
                    )

            # 4. ARP Entries -> LAYER2_ADJACENCY / LAYER3_REACHABILITY (NEVER PHYSICAL_ADJACENCY!)
            arp_ev = ev_lookup.get((dev_id, "arp"), [])
            for arp in pdata.get("arp") or []:
                if not isinstance(arp, dict):
                    continue
                arp_ip = normalize_ip(str(arp.get("address") or arp.get("ip") or ""))
                if not arp_ip:
                    continue
                peer_dev, pconf, _ = graph.resolver.resolve_peer_by_ip(arp_ip, exclude_device_id=dev_id)
                if peer_dev:
                    peer_node_id = EntityResolver.canonical_device_node_id(peer_dev)
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.LAYER2_ADJACENCY.value, dev_node_id, peer_node_id, f"arp:{arp_ip}"),
                            source_id=dev_node_id,
                            target_id=peer_node_id,
                            relationship_type=GraphRelationshipType.LAYER2_ADJACENCY.value,
                            layer=GraphLayer.LAYER2.value,
                            is_inferred=True,
                            evidence_ids=list(arp_ev),
                            provenance="arp_table_not_physical_proof",
                            confidence=min(0.75, pconf),
                            attributes={"arp_ip": arp_ip, "interface": arp.get("interface") or ""},
                        )
                    )

            # 5. OSPF & BGP Protocol Instances and Peers
            ospf_nbrs = pdata.get("ospf_neighbors") or []
            ospf_inst = pdata.get("ospf_instance")
            if ospf_nbrs or ospf_inst:
                ospf_ev = ev_lookup.get((dev_id, "ospf_neighbors"), []) + ev_lookup.get((dev_id, "ospf_instance"), [])
                inst_id = f"proto:{dev_id}:ospf:default"
                rid = ospf_inst.get("router_id") if isinstance(ospf_inst, dict) else ""
                graph.add_node(
                    KnowledgeNode(
                        node_id=inst_id,
                        entity_type=GraphEntityType.ROUTING_PROTOCOL_INSTANCE.value,
                        label=f"OSPF ({dev_id})",
                        device_id=dev_id,
                        attributes={"protocol": "ospf", "router_id": rid},
                        evidence_ids=list(ospf_ev),
                        provenance="ospf_state",
                        confidence=0.95,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, inst_id, dev_node_id),
                        source_id=inst_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.HOSTED_ON.value,
                        layer=GraphLayer.PROTOCOL.value,
                        evidence_ids=list(ospf_ev),
                    )
                )
                for nbr in ospf_nbrs:
                    if not isinstance(nbr, dict):
                        continue
                    nbr_rid = str(nbr.get("router_id") or nbr.get("router-id") or nbr.get("address") or "unknown")
                    nbr_addr = normalize_ip(str(nbr.get("address") or "")) or ""
                    nbr_if = str(nbr.get("interface") or "")
                    nbr_state = str(nbr.get("state") or "Unknown")
                    onode_id = f"ospf_nbr:{dev_id}:{nbr_rid}:{nbr_if}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=onode_id,
                            entity_type=GraphEntityType.OSPF_NEIGHBOR.value,
                            label=f"OSPF Nbr {nbr_rid} ({nbr_state})",
                            device_id=dev_id,
                            attributes={
                                "router_id": nbr_rid,
                                "address": nbr_addr,
                                "interface": nbr_if,
                                "state": nbr_state,
                                "area": nbr.get("area") or "backbone",
                            },
                            evidence_ids=list(ospf_ev),
                            provenance="ospf_neighbors",
                            confidence=0.95,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.PEERS_WITH.value, inst_id, onode_id),
                            source_id=inst_id,
                            target_id=onode_id,
                            relationship_type=GraphRelationshipType.PEERS_WITH.value,
                            layer=GraphLayer.PROTOCOL.value,
                            evidence_ids=list(ospf_ev),
                            provenance="ospf_neighbors",
                            confidence=0.95,
                            attributes={"state": nbr_state},
                        )
                    )
                    if nbr_addr:
                        peer_dev, pconf, _ = graph.resolver.resolve_peer_by_ip(nbr_addr, exclude_device_id=dev_id)
                        if peer_dev:
                            peer_node_id = EntityResolver.canonical_device_node_id(peer_dev)
                            graph.add_edge(
                                KnowledgeEdge(
                                    edge_id=_edge_id(GraphRelationshipType.PEERS_WITH.value, dev_node_id, peer_node_id, f"ospf:{nbr_rid}"),
                                    source_id=dev_node_id,
                                    target_id=peer_node_id,
                                    relationship_type=GraphRelationshipType.PEERS_WITH.value,
                                    layer=GraphLayer.PROTOCOL.value,
                                    evidence_ids=list(ospf_ev),
                                    provenance="ospf_adjacency",
                                    confidence=pconf,
                                    attributes={"protocol": "ospf", "state": nbr_state},
                                )
                            )

            bgp_peers = pdata.get("bgp_peers") or []
            if bgp_peers:
                bgp_ev = ev_lookup.get((dev_id, "bgp_peers"), [])
                binst_id = f"proto:{dev_id}:bgp:default"
                local_as = bgp_peers[0].get("local_as") if isinstance(bgp_peers[0], dict) else None
                graph.add_node(
                    KnowledgeNode(
                        node_id=binst_id,
                        entity_type=GraphEntityType.ROUTING_PROTOCOL_INSTANCE.value,
                        label=f"BGP ({dev_id})",
                        device_id=dev_id,
                        attributes={"protocol": "bgp", "local_as": local_as},
                        evidence_ids=list(bgp_ev),
                        provenance="bgp_state",
                        confidence=0.95,
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, binst_id, dev_node_id),
                        source_id=binst_id,
                        target_id=dev_node_id,
                        relationship_type=GraphRelationshipType.HOSTED_ON.value,
                        layer=GraphLayer.PROTOCOL.value,
                        evidence_ids=list(bgp_ev),
                    )
                )
                for bp in bgp_peers:
                    if not isinstance(bp, dict):
                        continue
                    rem_addr = normalize_ip(str(bp.get("remote_address") or bp.get("remote-address") or "")) or str(bp.get("name") or "peer")
                    bstate = str(bp.get("state") or ("established" if bp.get("established") else "idle"))
                    bpeer_id = f"bgp_peer:{dev_id}:{rem_addr}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=bpeer_id,
                            entity_type=GraphEntityType.BGP_PEER.value,
                            label=f"BGP Peer {rem_addr} (AS{bp.get('remote_as', '?')})",
                            device_id=dev_id,
                            attributes=dict(bp),
                            evidence_ids=list(bgp_ev),
                            provenance="bgp_peers",
                            confidence=0.95,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.PEERS_WITH.value, binst_id, bpeer_id),
                            source_id=binst_id,
                            target_id=bpeer_id,
                            relationship_type=GraphRelationshipType.PEERS_WITH.value,
                            layer=GraphLayer.PROTOCOL.value,
                            evidence_ids=list(bgp_ev),
                            provenance="bgp_peers",
                            confidence=0.95,
                            attributes={"state": bstate},
                        )
                    )
                    for adv_pfx in bp.get("advertised_prefixes") or []:
                        sub_id = f"subnet:main:{adv_pfx}"
                        graph.add_node(
                            KnowledgeNode(
                                node_id=sub_id,
                                entity_type=GraphEntityType.SUBNET.value,
                                label=str(adv_pfx),
                                attributes={"network_cidr": str(adv_pfx), "vrf": "main"},
                                evidence_ids=list(bgp_ev),
                            )
                        )
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.ADVERTISES.value, binst_id, sub_id, rem_addr),
                                source_id=binst_id,
                                target_id=sub_id,
                                relationship_type=GraphRelationshipType.ADVERTISES.value,
                                layer=GraphLayer.PROTOCOL.value,
                                evidence_ids=list(bgp_ev),
                                provenance="bgp_advertisements",
                                confidence=0.92,
                            )
                        )
                    peer_dev, pconf, _ = graph.resolver.resolve_peer_by_ip(rem_addr, exclude_device_id=dev_id)
                    if peer_dev:
                        peer_node_id = EntityResolver.canonical_device_node_id(peer_dev)
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.PEERS_WITH.value, dev_node_id, peer_node_id, f"bgp:{rem_addr}"),
                                source_id=dev_node_id,
                                target_id=peer_node_id,
                                relationship_type=GraphRelationshipType.PEERS_WITH.value,
                                layer=GraphLayer.PROTOCOL.value,
                                evidence_ids=list(bgp_ev),
                                provenance="bgp_peering",
                                confidence=pconf,
                                attributes={"protocol": "bgp", "state": bstate},
                            )
                        )

        # 6. Routing Tables, VRFs, Routes, Next-Hops, Gateways & WAN Connections
        for dev_id, routes in bundle.routing_evidence.items():
            if not routes:
                continue
            dev_node_id = EntityResolver.canonical_device_node_id(dev_id)
            if dev_node_id not in graph.nodes:
                graph.add_node(
                    KnowledgeNode(
                        node_id=dev_node_id,
                        entity_type=GraphEntityType.DEVICE.value,
                        label=dev_id,
                        device_id=dev_id,
                    )
                )
            r_ev_ids = ev_lookup.get((dev_id, "routes"), [])

            for idx, r in enumerate(routes):
                if not isinstance(r, NormalizedRoute):
                    continue
                tbl = r.routing_table or "main"
                vrf_id = f"vrf:{dev_id}:{tbl}"
                rtbl_id = f"rtable:{dev_id}:{tbl}"

                if tbl != "main" and vrf_id not in graph.nodes:
                    graph.add_node(
                        KnowledgeNode(
                            node_id=vrf_id,
                            entity_type=GraphEntityType.VRF.value,
                            label=f"VRF {tbl} ({dev_id})",
                            device_id=dev_id,
                            attributes={"vrf_name": tbl},
                            evidence_ids=list(r_ev_ids),
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, vrf_id, dev_node_id),
                            source_id=vrf_id,
                            target_id=dev_node_id,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            layer=GraphLayer.ROUTING.value,
                            evidence_ids=list(r_ev_ids),
                        )
                    )

                if rtbl_id not in graph.nodes:
                    graph.add_node(
                        KnowledgeNode(
                            node_id=rtbl_id,
                            entity_type=GraphEntityType.ROUTING_TABLE.value,
                            label=f"Table {tbl} ({dev_id})",
                            device_id=dev_id,
                            attributes={"table_name": tbl},
                            evidence_ids=list(r_ev_ids),
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.HOSTED_ON.value, rtbl_id, dev_node_id),
                            source_id=rtbl_id,
                            target_id=dev_node_id,
                            relationship_type=GraphRelationshipType.HOSTED_ON.value,
                            layer=GraphLayer.ROUTING.value,
                            evidence_ids=list(r_ev_ids),
                        )
                    )

                gw_key = r.gateway or r.interface_name or f"idx{idx}"
                route_node_id = f"route:{dev_id}:{tbl}:{r.dst_prefix}:{gw_key}:{r.distance}"
                rtype_val = r.route_type.value if hasattr(r.route_type, "value") else str(r.route_type)
                graph.add_node(
                    KnowledgeNode(
                        node_id=route_node_id,
                        entity_type=GraphEntityType.ROUTE.value,
                        label=f"{r.dst_prefix} via {gw_key}",
                        device_id=dev_id,
                        attributes={
                            "dst_prefix": r.dst_prefix,
                            "prefix_len": r.prefix_len,
                            "gateway": r.gateway,
                            "gateways": list(r.gateways),
                            "interface_name": r.interface_name,
                            "routing_table": tbl,
                            "distance": r.distance,
                            "scope": r.scope,
                            "target_scope": r.target_scope,
                            "protocol": r.protocol,
                            "route_type": rtype_val,
                            "active": r.active,
                            "disabled": r.disabled,
                            "unreachable": r.unreachable,
                            "fib": getattr(r, "fib", False),
                        },
                        evidence_ids=list(r_ev_ids),
                        provenance="rib_route_table",
                        confidence=0.95,
                    )
                )

                if r.dynamic or r.protocol in ("ospf", "bgp", "rip", "dhcp"):
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.LEARNS.value, rtbl_id, route_node_id),
                            source_id=rtbl_id,
                            target_id=route_node_id,
                            relationship_type=GraphRelationshipType.LEARNS.value,
                            layer=GraphLayer.ROUTING.value,
                            evidence_ids=list(r_ev_ids),
                            provenance=f"dynamic_{r.protocol}",
                            confidence=0.94,
                        )
                    )
                else:
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.MEMBER_OF.value, route_node_id, rtbl_id),
                            source_id=route_node_id,
                            target_id=rtbl_id,
                            relationship_type=GraphRelationshipType.MEMBER_OF.value,
                            layer=GraphLayer.ROUTING.value,
                            evidence_ids=list(r_ev_ids),
                            provenance="static_or_connected_rib",
                            confidence=0.96,
                        )
                    )

                sub_id = f"subnet:{tbl}:{r.dst_prefix}"
                graph.add_node(
                    KnowledgeNode(
                        node_id=sub_id,
                        entity_type=GraphEntityType.SUBNET.value,
                        label=r.dst_prefix,
                        attributes={"network_cidr": r.dst_prefix, "prefix_len": r.prefix_len, "vrf": tbl},
                        evidence_ids=list(r_ev_ids),
                    )
                )
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.ROUTES_TO.value, route_node_id, sub_id),
                        source_id=route_node_id,
                        target_id=sub_id,
                        relationship_type=GraphRelationshipType.ROUTES_TO.value,
                        layer=GraphLayer.ROUTING.value,
                        is_inferred=True,
                        evidence_ids=list(r_ev_ids),
                        provenance="rib_destination",
                        confidence=0.94 if r.active else 0.50,
                    )
                )

                # Next hops & Gateways
                gw_candidates = list(r.gateways) if r.gateways else ([r.gateway] if r.gateway else [])
                for raw_gw in gw_candidates:
                    gw_clean = normalize_ip(str(raw_gw).split("%")[0].strip())
                    if not gw_clean:
                        continue
                    nh_id = f"nexthop:{dev_id}:{tbl}:{gw_clean}"
                    gw_node_id = f"gateway:{gw_clean}"
                    graph.add_node(
                        KnowledgeNode(
                            node_id=nh_id,
                            entity_type=GraphEntityType.NEXT_HOP.value,
                            label=f"NextHop {gw_clean} ({dev_id})",
                            device_id=dev_id,
                            attributes={"gateway_ip": gw_clean, "interface_name": r.interface_name, "routing_table": tbl},
                            evidence_ids=list(r_ev_ids),
                        )
                    )
                    peer_dev, pconf, _ = graph.resolver.resolve_peer_by_ip(gw_clean, exclude_device_id=dev_id)
                    graph.add_node(
                        KnowledgeNode(
                            node_id=gw_node_id,
                            entity_type=GraphEntityType.GATEWAY.value,
                            label=f"Gateway {gw_clean}",
                            device_id=peer_dev,
                            attributes={"ip_address": gw_clean, "owner_device_id": peer_dev, "is_external": peer_dev is None},
                            evidence_ids=list(r_ev_ids),
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.NEXT_HOP_OF.value, nh_id, route_node_id),
                            source_id=nh_id,
                            target_id=route_node_id,
                            relationship_type=GraphRelationshipType.NEXT_HOP_OF.value,
                            layer=GraphLayer.ROUTING.value,
                            is_inferred=True,
                            evidence_ids=list(r_ev_ids),
                            provenance="rib_next_hop",
                            confidence=0.95,
                        )
                    )
                    graph.add_edge(
                        KnowledgeEdge(
                            edge_id=_edge_id(GraphRelationshipType.DEPENDS_ON.value, route_node_id, gw_node_id),
                            source_id=route_node_id,
                            target_id=gw_node_id,
                            relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                            layer=GraphLayer.ROUTING.value,
                            is_inferred=True,
                            evidence_ids=list(r_ev_ids),
                            provenance="rib_gateway_dependency",
                            confidence=0.90,
                        )
                    )

                    # Default route defines WAN_CONNECTION dependency when pointing to external or upstream gateway
                    if r.dst_prefix in ("0.0.0.0/0", "::/0") and r.active and not r.disabled:
                        wan_id = f"wan:{dev_id}:{r.interface_name or gw_clean}"
                        d_ev = bundle.device_evidence.get(dev_id, {})
                        graph.add_node(
                            KnowledgeNode(
                                node_id=wan_id,
                                entity_type=GraphEntityType.WAN_CONNECTION.value,
                                label=f"WAN via {gw_clean} ({dev_id})",
                                device_id=dev_id,
                                attributes={
                                    "egress_interface": r.interface_name,
                                    "gateway_ip": gw_clean,
                                    "distance": r.distance,
                                    "latency_ms": d_ev.get("latency_ms"),
                                    "packet_loss_percent": d_ev.get("packet_loss_percent"),
                                },
                                evidence_ids=list(r_ev_ids),
                                provenance="default_route_egress",
                                confidence=0.88,
                            )
                        )
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.CONNECTS_TO.value, wan_id, gw_node_id),
                                source_id=wan_id,
                                target_id=gw_node_id,
                                relationship_type=GraphRelationshipType.CONNECTS_TO.value,
                                layer=GraphLayer.WAN.value,
                                is_inferred=True,
                                evidence_ids=list(r_ev_ids),
                                provenance="default_route_wan",
                                confidence=0.88,
                            )
                        )
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.DEPENDS_ON.value, dev_node_id, wan_id),
                                source_id=dev_node_id,
                                target_id=wan_id,
                                relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                                layer=GraphLayer.WAN.value,
                                is_inferred=True,
                                evidence_ids=list(r_ev_ids),
                                provenance="default_route_dependency",
                                confidence=0.88,
                            )
                        )

                    # Routing-inferred device dependency (strictly marked is_inferred=True, layer="routing")
                    if peer_dev and r.active and not r.disabled:
                        peer_dev_node = EntityResolver.canonical_device_node_id(peer_dev)
                        graph.add_edge(
                            KnowledgeEdge(
                                edge_id=_edge_id(GraphRelationshipType.DEPENDS_ON.value, dev_node_id, peer_dev_node, f"nh:{gw_clean}:{r.dst_prefix}"),
                                source_id=dev_node_id,
                                target_id=peer_dev_node,
                                relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                                layer=GraphLayer.ROUTING.value,
                                is_inferred=True,
                                evidence_ids=list(r_ev_ids),
                                provenance="rib_next_hop_dependency",
                                confidence=min(0.88, pconf),
                                attributes={"dst_prefix": r.dst_prefix, "gateway": gw_clean, "distance": r.distance},
                            )
                        )

        # 7. Topology Edges (preserving PHYSICAL vs LAYER2 vs LAYER3 vs LOGICAL)
        topo_ev_ids = [r.evidence_id for r in bundle.records if r.evidence_type == "topology_edges"]
        for tedge in bundle.topology_evidence:
            src_dev = str(tedge.get("source_node_id") or tedge.get("source_id") or "").strip()
            dst_dev = str(tedge.get("target_node_id") or tedge.get("target_id") or "").strip()
            if not src_dev or not dst_dev:
                continue
            src_node = EntityResolver.canonical_device_node_id(src_dev)
            dst_node = EntityResolver.canonical_device_node_id(dst_dev)

            # Ensure endpoint nodes exist (marking unknown ones partial for consistency check)
            for did, dnode in ((src_dev, src_node), (dst_dev, dst_node)):
                if dnode not in graph.nodes:
                    graph.add_node(
                        KnowledgeNode(
                            node_id=dnode,
                            entity_type=GraphEntityType.DEVICE.value,
                            label=did,
                            device_id=did,
                            attributes={"device_id": did, "is_managed": False, "unknown_reference": True},
                            completeness=EvidenceCompleteness.PARTIAL.value,
                            confidence=0.50,
                        )
                    )

            rel_cls = str(tedge.get("relationship_class") or tedge.get("link_type") or "LOGICAL").upper()
            src_if = str(tedge.get("source_interface") or tedge.get("local_interface_id") or "")
            dst_if = str(tedge.get("target_interface") or tedge.get("remote_interface_id") or "")
            e_ts = tedge.get("last_verified_at") or tedge.get("last_seen_at") or tedge.get("observed_at")
            e_fresh = tedge.get("freshness") or evaluate_evidence_freshness("topology_edges", e_ts, curr_ts)

            if "PHYSICAL" in rel_cls:
                rel_type = GraphRelationshipType.PHYSICAL_ADJACENCY.value
                layer = GraphLayer.PHYSICAL.value
                inferred = False
            elif "LAYER2" in rel_cls or "L2" in rel_cls or "BRIDGE" in rel_cls:
                rel_type = GraphRelationshipType.LAYER2_ADJACENCY.value
                layer = GraphLayer.LAYER2.value
                inferred = False
            elif "LAYER3" in rel_cls or "L3" in rel_cls or "ROUTED" in rel_cls:
                rel_type = GraphRelationshipType.LAYER3_REACHABILITY.value
                layer = GraphLayer.LAYER3.value
                inferred = True
            else:
                rel_type = GraphRelationshipType.LOGICAL_RELATIONSHIP.value
                layer = GraphLayer.LOGICAL.value
                inferred = True

            disc = f"{src_if}:{dst_if}:{tedge.get('edge_id') or tedge.get('id') or ''}"
            graph.add_edge(
                KnowledgeEdge(
                    edge_id=_edge_id(rel_type, src_node, dst_node, disc),
                    source_id=src_node,
                    target_id=dst_node,
                    relationship_type=rel_type,
                    layer=layer,
                    bidirectional=(rel_type in (GraphRelationshipType.PHYSICAL_ADJACENCY.value, GraphRelationshipType.LAYER2_ADJACENCY.value)),
                    is_inferred=inferred,
                    evidence_ids=list(topo_ev_ids),
                    provenance=str(tedge.get("provenance") or rel_cls.lower()),
                    confidence=float(tedge.get("confidence_score") or 0.85),
                    observed_at=e_ts,
                    freshness=e_fresh,
                    attributes={
                        "source_interface": src_if,
                        "target_interface": dst_if,
                        "lifecycle_state": tedge.get("lifecycle_state") or "ACTIVE",
                    },
                )
            )

            # Optional explicit upstream dependency if annotated in topology edge
            if tedge.get("upstream_device_id"):
                up_id = str(tedge["upstream_device_id"])
                down_id = dst_dev if up_id == src_dev else src_dev
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.DEPENDS_ON.value, f"device:{down_id}", f"device:{up_id}", "topo"),
                        source_id=f"device:{down_id}",
                        target_id=f"device:{up_id}",
                        relationship_type=GraphRelationshipType.DEPENDS_ON.value,
                        layer=GraphLayer.PHYSICAL.value,
                        is_inferred=False,
                        evidence_ids=list(topo_ev_ids),
                        provenance="topology_upstream_dependency",
                        confidence=0.90,
                        observed_at=e_ts,
                        freshness=e_fresh,
                    )
                )

        # 8. Incidents (`AFFECTS`)
        inc_ev_ids = [r.evidence_id for r in bundle.records if r.evidence_type == "nms_incidents"]
        for inc in bundle.incident_evidence:
            inc_id_raw = inc.get("id") or inc.get("incident_id") or uuid.uuid4().hex[:8]
            inc_node_id = f"incident:nms:{inc_id_raw}"
            dev_id = str(inc.get("device_id") or "").strip()
            graph.add_node(
                KnowledgeNode(
                    node_id=inc_node_id,
                    entity_type=GraphEntityType.INCIDENT.value,
                    label=str(inc.get("title") or inc.get("incident_type") or f"Incident {inc_id_raw}"),
                    device_id=dev_id or None,
                    attributes=dict(inc),
                    evidence_ids=list(inc_ev_ids),
                    provenance="nms_incidents",
                    confidence=0.95,
                    observed_at=inc.get("started_at"),
                )
            )
            if dev_id and f"device:{dev_id}" in graph.nodes:
                graph.add_edge(
                    KnowledgeEdge(
                        edge_id=_edge_id(GraphRelationshipType.AFFECTS.value, inc_node_id, f"device:{dev_id}"),
                        source_id=inc_node_id,
                        target_id=f"device:{dev_id}",
                        relationship_type=GraphRelationshipType.AFFECTS.value,
                        layer=GraphLayer.TELEMETRY.value,
                        evidence_ids=list(inc_ev_ids),
                        provenance="nms_incidents",
                        confidence=0.95,
                        observed_at=inc.get("started_at"),
                    )
                )

        return graph

    # ------------------------------------------------------------------
    # Graph Consistency Validation (Tolerant of Partial Knowledge)
    # ------------------------------------------------------------------
    def validate_consistency(self, bundle: Optional[NetworkEvidenceBundle] = None, now: Optional[float] = None) -> GraphConsistencyReport:
        curr_ts = float(now) if now is not None else self.built_at
        issues: List[GraphConsistencyIssue] = []
        structural_error = False
        is_partial = False

        # 1. Unknown devices & incomplete discovery
        for node in self.nodes_by_type(GraphEntityType.DEVICE.value):
            if node.attributes.get("unknown_reference"):
                is_partial = True
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="UNKNOWN_DEVICE",
                        severity="warning",
                        description=f"Device '{node.label}' referenced by topology/routing edge is not in inventory.",
                        affected_ids=[node.node_id],
                    )
                )
            elif node.completeness == EvidenceCompleteness.PARTIAL.value or not node.attributes.get("is_managed", True):
                is_partial = True
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="INCOMPLETE_DISCOVERY",
                        severity="info",
                        description=f"Device '{node.label}' has partial/unmanaged visibility; conclusions involving it carry bounded confidence.",
                        affected_ids=[node.node_id],
                        evidence_ids=list(node.evidence_ids),
                    )
                )

        # 2. Orphaned interfaces (interfaces lacking a HOSTED_ON -> DEVICE edge)
        for if_node in self.nodes_by_type(GraphEntityType.INTERFACE.value):
            hosted_targets = [
                self.edges[eid].target_id
                for eid in self.out_edges.get(if_node.node_id, [])
                if self.edges[eid].relationship_type == GraphRelationshipType.HOSTED_ON.value
            ]
            if not hosted_targets or any(t not in self.nodes for t in hosted_targets):
                structural_error = True
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="ORPHANED_INTERFACE",
                        severity="error",
                        description=f"Interface '{if_node.node_id}' is not hosted on a valid device node.",
                        affected_ids=[if_node.node_id],
                    )
                )

        # 3. Invalid relationship endpoints, stale evidence & expired dependencies
        for edge in self.edges.values():
            if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
                structural_error = True
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="INVALID_ENDPOINT",
                        severity="error",
                        description=f"Edge '{edge.edge_id}' references missing endpoint ({edge.source_id} -> {edge.target_id}).",
                        affected_ids=[edge.source_id, edge.target_id],
                    )
                )
            if edge.freshness in (IntelligenceFreshness.STALE.value, IntelligenceFreshness.EXPIRED.value):
                itype = "EXPIRED_DEPENDENCY" if (edge.relationship_type == GraphRelationshipType.DEPENDS_ON.value and edge.freshness == IntelligenceFreshness.EXPIRED.value) else "STALE_EVIDENCE"
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type=itype,
                        severity="warning",
                        description=f"Relationship {edge.relationship_type} ({edge.source_id} -> {edge.target_id}) relies on {edge.freshness} evidence.",
                        affected_ids=[edge.edge_id, edge.source_id, edge.target_id],
                        evidence_ids=list(edge.evidence_ids),
                    )
                )
            if edge.valid_until is not None and curr_ts > edge.valid_until:
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="EXPIRED_DEPENDENCY",
                        severity="warning",
                        description=f"Relationship '{edge.edge_id}' exceeded validity interval.",
                        affected_ids=[edge.edge_id],
                    )
                )

        # 4. Duplicate relationship attempts
        for src, dst, rtype in self._duplicate_edge_attempts:
            issues.append(
                GraphConsistencyIssue(
                    issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                    issue_type="DUPLICATE_RELATIONSHIP",
                    severity="info",
                    description=f"Merged duplicate {rtype} observation between {src} and {dst}.",
                    affected_ids=[src, dst],
                )
            )

        # 5. Identity conflicts from EntityResolver
        for conflict in self.resolver.identity_conflicts:
            issues.append(
                GraphConsistencyIssue(
                    issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                    issue_type="IDENTITY_CONFLICT",
                    severity="warning",
                    description=conflict["description"],
                    affected_ids=[f"device:{d}" for d in conflict.get("devices", [])],
                )
            )

        # 6. Conflicting observations from bundle
        if bundle is not None:
            for contra in bundle.contradictions:
                issues.append(
                    GraphConsistencyIssue(
                        issue_id=f"gci_{uuid.uuid4().hex[:8]}",
                        issue_type="CONFLICTING_OBSERVATION",
                        severity=contra.severity,
                        description=contra.description,
                        affected_ids=[f"device:{d}" for d in contra.involved_devices],
                        evidence_ids=list(contra.evidence_ids),
                    )
                )
            if bundle.collection_gaps:
                is_partial = True

        return GraphConsistencyReport(
            is_consistent=(not structural_error),
            is_partial_network=is_partial,
            total_nodes=len(self.nodes),
            total_edges=len(self.edges),
            issues=issues,
            checked_at=curr_ts,
        )

    # ------------------------------------------------------------------
    # Immutable Historical Snapshot Graph Projection & Diff
    # ------------------------------------------------------------------
    @classmethod
    def from_historical_snapshot_dicts(
        cls,
        snapshot_id: str,
        snapshot_ts: float,
        topology_nodes: List[Dict[str, Any]],
        topology_edges: List[Dict[str, Any]],
        route_snapshots_by_device: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        eval_time: Optional[float] = None,
    ) -> "NetworkKnowledgeGraph":
        """Reconstructs a `NetworkKnowledgeGraph` strictly in-memory from immutable snapshot payloads."""
        devices_syn: Dict[str, Any] = {}
        for n in topology_nodes:
            did = str(n.get("id") or n.get("node_id") or "")
            if not did:
                continue
            status_raw = str(n.get("status") or n.get("nms_status") or "UP").upper()
            reach = "DOWN" if status_raw in ("OFFLINE", "DOWN", "UNREACHABLE") else "UP"
            devices_syn[did] = {
                "display_name": n.get("name") or did,
                "identity": n.get("identity") or "",
                "management_ip": n.get("ip") or "",
                "mac_address": n.get("mac") or "",
                "reachability_status": reach,
                "observed_at": snapshot_ts,
                "routes": (route_snapshots_by_device or {}).get(did, []),
                "routes_observed_at": snapshot_ts,
            }
        from core.network_intelligence.evidence_service import UnifiedEvidenceService
        svc = UnifiedEvidenceService()
        syn_bundle = svc.assemble_evidence_bundle(
            scope=f"snapshot:{snapshot_id}",
            synthetic_data={
                "topology_snapshot_ref": snapshot_id,
                "devices": devices_syn,
                "topology_edges": [dict(e, observed_at=snapshot_ts) for e in topology_edges],
            },
            now=eval_time if eval_time is not None else snapshot_ts,
        )
        return cls.from_evidence_bundle(syn_bundle, now=eval_time if eval_time is not None else snapshot_ts)

    @staticmethod
    def compare_graphs(
        before_graph: "NetworkKnowledgeGraph",
        after_graph: "NetworkKnowledgeGraph",
        coinciding_incidents: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministically diffs two `NetworkKnowledgeGraph` instances without mutating either.
        Answers what relationships appeared/disappeared, route dependency shifts, unreachable devices, and stale items.
        """
        before_rels = {
            (e.source_id, e.target_id, e.relationship_type, e.layer): e
            for e in before_graph.edges.values()
        }
        after_rels = {
            (e.source_id, e.target_id, e.relationship_type, e.layer): e
            for e in after_graph.edges.values()
        }

        disappeared = [
            before_rels[k].to_dict()
            for k in sorted(set(before_rels.keys()) - set(after_rels.keys()))
        ]
        appeared = [
            after_rels[k].to_dict()
            for k in sorted(set(after_rels.keys()) - set(before_rels.keys()))
        ]

        route_dep_before = {
            k for k in before_rels if k[2] in (GraphRelationshipType.DEPENDS_ON.value, GraphRelationshipType.ROUTES_TO.value) and k[3] == GraphLayer.ROUTING.value
        }
        route_dep_after = {
            k for k in after_rels if k[2] in (GraphRelationshipType.DEPENDS_ON.value, GraphRelationshipType.ROUTES_TO.value) and k[3] == GraphLayer.ROUTING.value
        }
        route_dependencies_removed = [before_rels[k].to_dict() for k in sorted(route_dep_before - route_dep_after)]
        route_dependencies_added = [after_rels[k].to_dict() for k in sorted(route_dep_after - route_dep_before)]

        newly_unreachable: List[str] = []
        for node_id, anode in after_graph.nodes.items():
            if anode.entity_type != GraphEntityType.DEVICE.value:
                continue
            bnode = before_graph.nodes.get(node_id)
            a_reach = str(anode.attributes.get("reachability_status") or "").upper()
            b_reach = str(bnode.attributes.get("reachability_status") or "UP").upper() if bnode else "UP"
            if a_reach in ("DOWN", "SUSPECTED_DOWN", "UNREACHABLE") and b_reach not in ("DOWN", "SUSPECTED_DOWN", "UNREACHABLE"):
                newly_unreachable.append(anode.device_id or node_id)

        stale_observations = [
            e.to_dict()
            for e in after_graph.edges.values()
            if e.freshness in (IntelligenceFreshness.STALE.value, IntelligenceFreshness.EXPIRED.value)
        ]

        return {
            "before_snapshot_ref": before_graph.snapshot_ref,
            "after_snapshot_ref": after_graph.snapshot_ref,
            "relationships_disappeared": disappeared,
            "relationships_appeared": appeared,
            "route_dependencies_removed": route_dependencies_removed,
            "route_dependencies_added": route_dependencies_added,
            "devices_became_unreachable": newly_unreachable,
            "coinciding_incidents": list(coinciding_incidents or []),
            "stale_observations": stale_observations,
            "summary": {
                "disappeared_count": len(disappeared),
                "appeared_count": len(appeared),
                "route_dep_changes": len(route_dependencies_removed) + len(route_dependencies_added),
                "newly_unreachable_count": len(newly_unreachable),
                "stale_count": len(stale_observations),
            },
        }

    def to_dict(self, max_nodes: int = 500, max_edges: int = 1000) -> Dict[str, Any]:
        nodes_list = [n.to_dict() for n in list(self.nodes.values())[:max_nodes]]
        edges_list = [e.to_dict() for e in list(self.edges.values())[:max_edges]]
        by_type: Dict[str, int] = {}
        for n in self.nodes.values():
            by_type[n.entity_type] = by_type.get(n.entity_type, 0) + 1
        by_rel: Dict[str, int] = {}
        for e in self.edges.values():
            by_rel[e.relationship_type] = by_rel.get(e.relationship_type, 0) + 1
        return {
            "built_at": self.built_at,
            "snapshot_ref": self.snapshot_ref,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "entity_counts": by_type,
            "relationship_counts": by_rel,
            "nodes": nodes_list,
            "edges": edges_list,
            "truncated": len(self.nodes) > max_nodes or len(self.edges) > max_edges,
        }
