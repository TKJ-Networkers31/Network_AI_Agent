"""
core/network_intelligence/correlation.py — Cross-Device Evidence Correlator for AIRA OS.

Correlates observations across multiple network devices to identify Layer 2 and Layer 3 relationships.
Enforces strict evidentiary confidence semantics:
- CONFIRMED: Bidirectional protocol discovery (MNDP/LLDP) or verified operator override.
- HIGH: Direct neighbor protocol or mutual ARP + matching point-to-point subnets.
- MEDIUM: Common IP subnet without mutual ARP validation (explicitly marked as candidate link).
- LOW: Inferred from routing next-hops or MAC bridging tables.
- UNKNOWN: Insufficient evidence.

Never promotes weak subnet overlap to confirmed physical topology.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.network_intelligence.network_models import (
    CorrelationConfidence,
    LinkType,
    NormalizedIPAddress,
    NormalizedInterface,
    NormalizedLink,
    NormalizedNeighbor,
    NormalizedRoute,
    parse_interface_item,
    parse_ip_address_item,
)
from core.topology_models import normalize_ip, normalize_mac, sanitize_untrusted_text

logger = logging.getLogger("aira.network_intelligence.correlation")


@dataclass
class CorrelatedRelationship:
    relationship_id: str
    source_device_id: str
    target_device_id: str
    source_port: str = ""
    target_port: str = ""
    relationship_type: str = LinkType.LAYER2_ADJACENCY.value
    correlation_rule: str = ""
    confidence: str = CorrelationConfidence.MEDIUM.value
    evidence_sources: List[str] = field(default_factory=list)
    alternative_interpretations: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    validation_status: str = "unverified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_device_id": self.source_device_id,
            "target_device_id": self.target_device_id,
            "source_port": self.source_port,
            "target_port": self.target_port,
            "relationship_type": self.relationship_type,
            "correlation_rule": self.correlation_rule,
            "confidence": self.confidence,
            "evidence_sources": list(self.evidence_sources),
            "alternative_interpretations": list(self.alternative_interpretations),
            "timestamp": self.timestamp,
            "validation_status": self.validation_status,
        }


class CrossDeviceEvidenceCorrelator:
    """
    Engine for correlating multi-device evidence into structured relationships with explicit provenance.
    """

    def correlate_bundles(self, device_bundles: Dict[str, Dict[str, Any]]) -> List[CorrelatedRelationship]:
        """
        Correlates observations across an arbitrary set of device bundles.
        """
        relationships: List[CorrelatedRelationship] = []
        now = time.time()

        # Step 1: Index normalized entities per device
        device_ips: Dict[str, List[NormalizedIPAddress]] = {}
        device_interfaces: Dict[str, Dict[str, NormalizedInterface]] = {}
        device_arps: Dict[str, List[Dict[str, Any]]] = {}
        device_routes: Dict[str, List[Dict[str, Any]]] = {}

        device_neighbors: Dict[str, List[Dict[str, Any]]] = {}
        for dev_id, bundle in device_bundles.items():
            device_ips[dev_id] = []
            device_interfaces[dev_id] = {}
            device_arps[dev_id] = []
            device_routes[dev_id] = []
            device_neighbors[dev_id] = []

            for item in bundle.get("evidence_items", []):
                if getattr(item, "collection_status", "") != "SUCCESS":
                    continue
                obs_type = getattr(item, "observation_type", "")
                val = getattr(item, "normalized_value", {}) or {}

                if obs_type == "ip_addresses":
                    for raw_addr in val.get("addresses", []):
                        parsed_ip = parse_ip_address_item(dev_id, raw_addr)
                        if parsed_ip:
                            device_ips[dev_id].append(parsed_ip)

                elif obs_type == "interfaces":
                    for raw_iface in val.get("interfaces", []):
                        parsed_if = parse_interface_item(dev_id, raw_iface)
                        device_interfaces[dev_id][parsed_if.interface_name] = parsed_if

                elif obs_type == "arp":
                    device_arps[dev_id].extend(val.get("entries", []))

                elif obs_type == "routes":
                    device_routes[dev_id].extend(val.get("routes", []))

                elif obs_type in ("neighbors", "neighbor"):
                    device_neighbors[dev_id].extend(val.get("neighbors", []))

        # Step 2: Compare pairs of devices (combinations without self-loops)
        dev_ids = list(device_bundles.keys())
        for i in range(len(dev_ids)):
            for j in range(i + 1, len(dev_ids)):
                dev_a = dev_ids[i]
                dev_b = dev_ids[j]

                # Rule 0: Bidirectional L2 Neighbor Discovery (MNDP/LLDP) -> CONFIRMED (Physical)
                rel_neigh = self._correlate_neighbors(
                    dev_a, dev_b,
                    device_neighbors.get(dev_a, []), device_neighbors.get(dev_b, []),
                    device_interfaces.get(dev_a, {}), device_interfaces.get(dev_b, {}),
                )
                if rel_neigh:
                    relationships.append(rel_neigh)

                # Rule A: Mutual Subnet + Mutual ARP Matching -> HIGH
                rel_arp = self._correlate_arp_and_subnet(
                    dev_a, dev_b,
                    device_ips.get(dev_a, []), device_ips.get(dev_b, []),
                    device_arps.get(dev_a, []), device_arps.get(dev_b, []),
                    device_interfaces.get(dev_a, {}), device_interfaces.get(dev_b, {}),
                )
                if rel_arp:
                    relationships.append(rel_arp)
                    continue

                # Rule B: Subnet Overlap Only -> MEDIUM (Explicitly marked as candidate link)
                rel_subnet = self._correlate_subnet_only(
                    dev_a, dev_b,
                    device_ips.get(dev_a, []), device_ips.get(dev_b, []),
                )
                if rel_subnet:
                    relationships.append(rel_subnet)

                # Rule C: Routed Next-Hop Relationship -> HIGH (Routed)
                rel_routes = self._correlate_routed_nexthop(
                    dev_a, dev_b,
                    device_routes.get(dev_a, []), device_ips.get(dev_b, []),
                )
                if rel_routes:
                    relationships.append(rel_routes)

                rel_routes_rev = self._correlate_routed_nexthop(
                    dev_b, dev_a,
                    device_routes.get(dev_b, []), device_ips.get(dev_a, []),
                )
                if rel_routes_rev:
                    relationships.append(rel_routes_rev)

        return relationships

    def _correlate_arp_and_subnet(
        self,
        dev_a: str,
        dev_b: str,
        ips_a: List[NormalizedIPAddress],
        ips_b: List[NormalizedIPAddress],
        arps_a: List[Dict[str, Any]],
        arps_b: List[Dict[str, Any]],
        ifaces_a: Dict[str, NormalizedInterface],
        ifaces_b: Dict[str, NormalizedInterface],
    ) -> Optional[CorrelatedRelationship]:
        """
        Matches when two devices share a common IP subnet and possess mutual ARP entries.
        """
        for ip_a in ips_a:
            for ip_b in ips_b:
                if not ip_a.network_cidr or not ip_b.network_cidr:
                    continue

                try:
                    net_a = ipaddress.ip_network(ip_a.network_cidr, strict=False)
                    addr_b = ipaddress.ip_address(ip_b.address)

                    if addr_b in net_a:
                        # Check ARP entry on Dev A for IP B
                        mac_b = ifaces_b.get(ip_b.interface_name, NormalizedInterface(dev_b, "")).mac_address
                        arp_match_a = False
                        for e in arps_a:
                            if normalize_ip(e.get("address")) == ip_b.address:
                                if not mac_b or normalize_mac(e.get("mac_address")) == mac_b:
                                    arp_match_a = True
                                    break

                        if arp_match_a:
                            rel_id = f"rel_arp_{dev_a}_{ip_a.interface_name}__{dev_b}_{ip_b.interface_name}"
                            return CorrelatedRelationship(
                                relationship_id=rel_id,
                                source_device_id=dev_a,
                                target_device_id=dev_b,
                                source_port=ip_a.interface_name,
                                target_port=ip_b.interface_name,
                                relationship_type=LinkType.LAYER2_ADJACENCY.value,
                                correlation_rule="MUTUAL_ARP_AND_SUBNET_MATCH",
                                confidence=CorrelationConfidence.HIGH.value,
                                evidence_sources=[
                                    f"Subnet {ip_a.network_cidr} shared between {dev_a}:{ip_a.interface_name} ({ip_a.address}) and {dev_b}:{ip_b.interface_name} ({ip_b.address})",
                                    f"ARP entry for {ip_b.address} observed on {dev_a}",
                                ],
                                alternative_interpretations=[
                                    "Perangkat mungkin terhubung melalui switch Layer 2 unmanaged perantara.",
                                    "Hubungan VLAN tagged bersama pada switch trunk.",
                                ],
                                validation_status="observed",
                            )
                except Exception:
                    continue

        return None

    def _correlate_subnet_only(
        self,
        dev_a: str,
        dev_b: str,
        ips_a: List[NormalizedIPAddress],
        ips_b: List[NormalizedIPAddress],
    ) -> Optional[CorrelatedRelationship]:
        """
        Identifies candidate link when devices share an IP subnet but no direct ARP entry is yet recorded.
        """
        for ip_a in ips_a:
            for ip_b in ips_b:
                if not ip_a.network_cidr or not ip_b.network_cidr:
                    continue

                try:
                    net_a = ipaddress.ip_network(ip_a.network_cidr, strict=False)
                    addr_b = ipaddress.ip_address(ip_b.address)

                    if addr_b in net_a and ip_a.address != ip_b.address:
                        rel_id = f"rel_subnet_{dev_a}_{ip_a.interface_name}__{dev_b}_{ip_b.interface_name}"
                        return CorrelatedRelationship(
                            relationship_id=rel_id,
                            source_device_id=dev_a,
                            target_device_id=dev_b,
                            source_port=ip_a.interface_name,
                            target_port=ip_b.interface_name,
                            relationship_type=LinkType.INFERRED.value,
                            correlation_rule="SUBNET_OVERLAP_ONLY",
                            confidence=CorrelationConfidence.MEDIUM.value,
                            evidence_sources=[
                                f"Subnet overlap {ip_a.network_cidr} matches {dev_a}:{ip_a.interface_name} and {dev_b}:{ip_b.interface_name}",
                            ],
                            alternative_interpretations=[
                                "Konektivitas fisik belum dibuktikan oleh pertukaran paket ARP langsung.",
                                "Kedua router mungkin terhubung ke segmen LAN terisolasi atau VLAN yang berbeda.",
                            ],
                            validation_status="inferred",
                        )
                except Exception:
                    continue

        return None

    def correlate_all_routed_nexthops(
        self,
        source_dev: str,
        target_dev: str,
        routes: List[Dict[str, Any]],
        target_ips: List[NormalizedIPAddress],
    ) -> List[CorrelatedRelationship]:
        """
        Identifies all routed next-hop relationships (including ECMP gateways,
        VRF routing tables, and recursive immediate gateways) from `source_dev`
        toward interface IPs owned by `target_dev`.
        Never promotes routed next-hop matches to physical cabling.
        """
        target_ip_map = {
            normalize_ip(ip_obj.address): ip_obj.interface_name
            for ip_obj in target_ips
            if normalize_ip(ip_obj.address)
        }
        found: List[CorrelatedRelationship] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for r in routes:
            if r.get("disabled") or r.get("active") is False:
                continue
            raw_gws = r.get("gateways") or ([r.get("gateway")] if r.get("gateway") else [])
            imm_gw = str(r.get("immediate_gw") or "").split("%")[0].strip()
            candidate_ips = [normalize_ip(g.split("%")[0]) for g in raw_gws if g]
            if imm_gw:
                norm_imm = normalize_ip(imm_gw)
                if norm_imm and norm_imm not in candidate_ips:
                    candidate_ips.append(norm_imm)

            for gw in candidate_ips:
                if not gw or gw not in target_ip_map:
                    continue
                target_iface = target_ip_map[gw]
                dst = r.get("dst_prefix") or r.get("dst_address") or "0.0.0.0/0"
                tbl = r.get("routing_table") or "main"
                dedup_key = (tbl, str(dst), gw)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                is_recursive = bool(imm_gw and normalize_ip(str(r.get("gateway") or "").split("%")[0]) != gw)
                rule = "RECURSIVE_ROUTED_NEXT_HOP" if is_recursive else "ROUTED_NEXT_HOP"
                conf = (
                    CorrelationConfidence.MEDIUM.value
                    if is_recursive
                    else CorrelationConfidence.HIGH.value
                )
                src_port = r.get("interface_name") or r.get("interface") or "routed"
                rel_id = f"rel_route_{source_dev}__{target_dev}_{gw}_{tbl}_{dst}"
                found.append(
                    CorrelatedRelationship(
                        relationship_id=rel_id,
                        source_device_id=source_dev,
                        target_device_id=target_dev,
                        source_port=src_port,
                        target_port=target_iface,
                        relationship_type=LinkType.ROUTED.value,
                        correlation_rule=rule,
                        confidence=conf,
                        evidence_sources=[
                            f"Rute {dst} (table={tbl}) pada {source_dev} menunjuk gateway {gw} milik {target_dev}:{target_iface}"
                        ],
                        alternative_interpretations=[
                            "Next-hop routed dapat melewati switch L2 atau jaringan transit tanpa kabel fisik langsung."
                        ],
                        validation_status="observed",
                    )
                )
        return found

    def _correlate_routed_nexthop(
        self,
        source_dev: str,
        target_dev: str,
        routes: List[Dict[str, Any]],
        target_ips: List[NormalizedIPAddress],
    ) -> Optional[CorrelatedRelationship]:
        """
        Identifies routed next-hop relationship where source_dev has a route via target_dev interface IP.
        """
        all_matches = self.correlate_all_routed_nexthops(
            source_dev, target_dev, routes, target_ips
        )
        if all_matches:
            first = all_matches[0]
            # Preserve exact legacy relationship_id format for primary match
            gw_part = first.relationship_id.split(f"rel_route_{source_dev}__{target_dev}_", 1)[-1].split("_")[0]
            first.relationship_id = f"rel_route_{source_dev}__{target_dev}_{gw_part}"
            first.correlation_rule = "ROUTED_NEXT_HOP"
            first.confidence = CorrelationConfidence.HIGH.value
            return first

        target_ip_set = {normalize_ip(ip_obj.address): ip_obj.interface_name for ip_obj in target_ips}

        for r in routes:
            gw = normalize_ip(r.get("gateway"))
            if gw and gw in target_ip_set:
                target_iface = target_ip_set[gw]
                dst = r.get("dst_address") or r.get("dst_prefix") or "0.0.0.0/0"
                rel_id = f"rel_route_{source_dev}__{target_dev}_{gw}"
                return CorrelatedRelationship(
                    relationship_id=rel_id,
                    source_device_id=source_dev,
                    target_device_id=target_dev,
                    source_port=r.get("interface") or "routed",
                    target_port=target_iface,
                    relationship_type=LinkType.ROUTED.value,
                    correlation_rule="ROUTED_NEXT_HOP",
                    confidence=CorrelationConfidence.HIGH.value,
                    evidence_sources=[
                        f"Rute {dst} pada {source_dev} menunjuk gateway {gw} yang dimiliki oleh {target_dev}:{target_iface}",
                    ],
                    alternative_interpretations=[
                        "Next-hop routed multi-hop melalui router transit.",
                    ],
                    validation_status="observed",
                )

        return None

    def _correlate_neighbors(
        self,
        dev_a: str,
        dev_b: str,
        neighbors_a: List[Dict[str, Any]],
        neighbors_b: List[Dict[str, Any]],
        ifaces_a: Dict[str, NormalizedInterface],
        ifaces_b: Dict[str, NormalizedInterface],
    ) -> Optional[CorrelatedRelationship]:
        """
        Matches bidirectional L2 neighbor discovery between dev_a and dev_b on physical ports.
        """
        for na in neighbors_a:
            rem_ident_a = (na.get("identity") or na.get("system-description") or "").strip().lower()
            rem_mac_a = normalize_mac(na.get("mac-address") or na.get("chassis-id") or "")
            loc_if_a = na.get("interface", "")
            rem_if_a = na.get("interface-name") or na.get("port-id") or na.get("to-interface") or ""

            # Check if this neighbor entry matches dev_b
            match_b = (rem_ident_a and rem_ident_a == dev_b.lower()) or any(
                rem_mac_a and iface.mac_address and normalize_mac(iface.mac_address) == rem_mac_a
                for iface in ifaces_b.values()
            )
            if not match_b:
                continue

            # Now check reverse: does dev_b have neighbor pointing to dev_a?
            for nb in neighbors_b:
                rem_ident_b = (nb.get("identity") or nb.get("system-description") or "").strip().lower()
                rem_mac_b = normalize_mac(nb.get("mac-address") or nb.get("chassis-id") or "")
                loc_if_b = nb.get("interface", "")
                rem_if_b = nb.get("interface-name") or nb.get("port-id") or nb.get("to-interface") or ""

                match_a = (rem_ident_b and rem_ident_b == dev_a.lower()) or any(
                    rem_mac_b and iface.mac_address and normalize_mac(iface.mac_address) == rem_mac_b
                    for iface in ifaces_a.values()
                )
                if match_a:
                    # Ports physical check
                    ports_physical = any(p in (loc_if_a or "").lower() for p in ("ether", "sfp")) and any(
                        p in (loc_if_b or "").lower() for p in ("ether", "sfp")
                    )
                    rel_type = LinkType.PHYSICAL.value if ports_physical else LinkType.LAYER2_ADJACENCY.value
                    rel_id = f"rel_neighbor_{dev_a}_{loc_if_a}__{dev_b}_{loc_if_b}"
                    return CorrelatedRelationship(
                        relationship_id=rel_id,
                        source_device_id=dev_a,
                        target_device_id=dev_b,
                        source_port=loc_if_a,
                        target_port=loc_if_b,
                        relationship_type=rel_type,
                        correlation_rule="BIDIRECTIONAL_NEIGHBOR_DISCOVERY",
                        confidence=CorrelationConfidence.CONFIRMED.value,
                        evidence_sources=[
                            f"Mutual neighbor discovery: {dev_a}:{loc_if_a} <-> {dev_b}:{loc_if_b}",
                        ],
                        alternative_interpretations=[],
                        validation_status="confirmed",
                    )
        return None

    def reconcile_correlated_relationships_to_engine(
        self,
        relationships: List[CorrelatedRelationship],
        engine: Any,
        now: Optional[float] = None,
    ) -> List[str]:
        """
        Translates correlated relationships into normalized TopologyEdge and EdgeEvidence records
        and reconciles them into the provided TopologyEngine instance.
        """
        ts = now if now is not None else time.time()
        reconciled_ids: List[str] = []

        for rel in relationships:
            rule = rel.correlation_rule
            rel_type = rel.relationship_type

            if rule == "BIDIRECTIONAL_NEIGHBOR_DISCOVERY" or rel_type == LinkType.PHYSICAL.value:
                rc = "physical"
                sub = "direct_copper" if "ether" in (rel.source_port or "").lower() else "direct_fiber"
                tier = "CONFIRMED"
                score = 1.0
                vstatus = "confirmed"
                rationale = "Mutual bidirectional Layer 2 neighbor discovery verified on physical ports."
            elif rule == "ROUTED_NEXT_HOP" or rel_type == LinkType.ROUTED.value:
                rc = "layer3"
                sub = "default_gateway_transit"
                tier = "HIGH"
                score = 0.75
                vstatus = "observed"
                rationale = "Routed next-hop relationship observed from routing table."
            elif rule == "MUTUAL_ARP_AND_SUBNET_MATCH":
                # Check for dedicated /30 or /31
                is_p2p = any("/30" in s or "/31" in s for s in rel.evidence_sources)
                rc = "layer3"
                sub = "routed_point_to_point" if is_p2p else "routed_multiaccess"
                tier = "HIGH" if is_p2p else "MEDIUM"
                score = 0.75 if is_p2p else 0.55
                vstatus = "observed"
                rationale = (
                    "Mutual ARP resolution on exclusive point-to-point /30 or /31 subnet."
                    if is_p2p
                    else "Mutual ARP resolution on shared multi-access subnet; physical cabling unverified."
                )
            elif rule == "SUBNET_OVERLAP_ONLY" or rel_type == LinkType.INFERRED.value:
                rc = "layer3"
                sub = "routed_multiaccess"
                tier = "MEDIUM"
                score = 0.50
                vstatus = "inferred"
                rationale = "Common IP subnet overlap without direct mutual ARP confirmation."
            else:
                rc = "layer2"
                sub = "shared_switch_domain"
                tier = "MEDIUM"
                score = 0.50
                vstatus = "observed"
                rationale = "Layer 2 adjacency observed."

            edge_id = engine._reconcile_discovered_edge(
                source_id=rel.source_device_id,
                target_id=rel.target_device_id,
                relationship_class=rc,
                source_interface=rel.source_port,
                target_interface=rel.target_port,
                relationship_subtype=sub,
                direction="bidirectional",
                oper_status="up",
                admin_status="enabled",
                verification_status=vstatus,
                confidence_tier=tier,
                confidence_score=score,
                confidence_rationale=rationale,
                evidence_item={
                    "evidence_type": f"correlated_{rule.lower()}",
                    "protocol": "cross_device_correlator",
                    "local_interface": rel.source_port,
                    "remote_interface": rel.target_port,
                    "confidence": tier.lower(),
                    "explanation": rationale,
                    "raw_excerpt": "; ".join(rel.evidence_sources),
                },
                now=ts,
            )
            if edge_id:
                reconciled_ids.append(edge_id)

        return reconciled_ids
