"""
AIRA OS — Change Impact & Dependency Intelligence Analyzer (Networking VI / WP 6.7).

Analyzes the blast radius, dependent services/subnets/devices, routing/protocol dependencies,
and redundancy status when a device, interface, VLAN, route, WAN link, or protocol peer changes.

Strictly separates:
- `OBSERVED_IMPACT`: Demonstrably affected entities based on currently degraded/down evidence.
- `POTENTIAL_IMPACT`: Theoretical blast radius according to graph dependencies (never claimed as outage).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set
import uuid

from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    ConfidenceLabel,
    GraphEntityType,
    ImpactAnalysisResult,
    ImpactScopeType,
    NetworkEvidenceBundle,
    RedundancyStatus,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph


class ImpactAnalyzer:
    """Deterministic, graph-backed blast-radius & dependency impact analyzer."""

    def analyze_impact(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        target_entity_id: str,
        target_entity_type: Optional[str] = None,
        impact_scope_type: str = ImpactScopeType.POTENTIAL_IMPACT.value,
        now: Optional[float] = None,
    ) -> ImpactAnalysisResult:
        curr_ts = float(now) if now is not None else time.time()
        qengine = GraphQueryEngine(graph)
        impact_id = f"imp_{uuid.uuid4().hex[:10]}"

        # Resolve entity node
        clean_target = target_entity_id.strip()
        if not (clean_target.startswith("device:") or ":" in clean_target):
            clean_target = f"device:{clean_target}"
        node = graph.get_node(clean_target)

        ent_type = target_entity_type or (node.entity_type if node else GraphEntityType.DEVICE.value)
        dev_id = node.device_id if node else clean_target.replace("device:", "")

        evidence_ids: Set[str] = set()
        if node:
            evidence_ids.update(node.evidence_ids)

        direct_dependents: List[Dict[str, Any]] = []
        indirect_dependents: List[Dict[str, Any]] = []
        affected_devices: Set[str] = set()
        affected_subnets: Set[str] = set()
        affected_services: Set[str] = set()
        routing_deps: List[Dict[str, Any]] = []
        protocol_rels: List[Dict[str, Any]] = []
        alternate_paths: List[Dict[str, Any]] = []

        # 1. Dependency traversal via GraphQueryEngine
        if dev_id:
            dep_res = qengine.get_downstream_dependencies(dev_id, max_depth=6)
            evidence_ids.update(dep_res["evidence_basis"])
            direct_dependents = list(dep_res["direct_dependents"])
            indirect_dependents = list(dep_res["indirect_dependents"])

            for dep in dep_res["all_dependents"]:
                did = dep["device_id"]
                affected_devices.add(did)
                seg_res = qengine.get_reachable_segments(did)
                evidence_ids.update(seg_res["evidence_basis"])
                for s in seg_res["segments"]:
                    affected_subnets.add(s["segment"])

            # Services affected
            svc_res = qengine.get_affected_services(dev_id)
            evidence_ids.update(svc_res["evidence_basis"])
            for s in svc_res["services"]:
                affected_services.add(s["label"])

            # Routes using target device IP as next-hop
            target_ip = (bundle.device_evidence.get(dev_id) or {}).get("management_ip")
            if target_ip:
                routes_nh = qengine.get_routes_using_next_hop(target_ip)
                evidence_ids.update(routes_nh["evidence_basis"])
                routing_deps = list(routes_nh["routes"])

            # Protocols
            for proto in ("ospf", "bgp"):
                p_part = qengine.get_protocol_participants(proto)
                for part in p_part["participants"]:
                    if part["device_id"] == dev_id or part["device_id"] in affected_devices:
                        protocol_rels.append(part)
                        evidence_ids.update(part["evidence_ids"])

            # 2. Redundancy & Alternative Paths
            # Check if affected direct dependents have alternate paths to core/WAN bypassing dev_id
            for d in direct_dependents:
                peer_did = d["device_id"]
                alt_res = qengine.find_alternate_paths(peer_did, "ISP-Edge", excluded_ids={dev_id})
                if not alt_res["paths"]:
                    # Try finding path to another managed device
                    for cand in bundle.selected_devices:
                        if cand not in (dev_id, peer_did):
                            alt_res = qengine.find_alternate_paths(peer_did, cand, excluded_ids={dev_id})
                            if alt_res["paths"]:
                                break
                if alt_res["paths"]:
                    alternate_paths.extend(alt_res["paths"])
                    evidence_ids.update(alt_res["evidence_basis"])

        # Determine Redundancy Status
        if not direct_dependents:
            red_status = RedundancyStatus.UNKNOWN.value
            red_notes = "Tidak ada perangkat downstream yang bergantung langsung pada entitas ini."
        elif alternate_paths:
            if len(alternate_paths) >= len(direct_dependents):
                red_status = RedundancyStatus.FULL_REDUNDANCY.value
                red_notes = f"Tersedia jalur alternatif untuk seluruh ({len(direct_dependents)}) perangkat dependen langsung."
            else:
                red_status = RedundancyStatus.PARTIAL_REDUNDANCY.value
                red_notes = f"Tersedia jalur alternatif untuk sebagian perangkat dependen ({len(alternate_paths)} jalur ditemukan)."
        else:
            red_status = RedundancyStatus.NO_REDUNDANCY.value
            red_notes = "Tidak terdeteksi jalur redundansi; kegagalan entitas ini berpotensi memutus konektivitas perangkat hilir."

        # Filter if OBSERVED_IMPACT (only keep entities demonstrably down/degraded)
        if impact_scope_type == ImpactScopeType.OBSERVED_IMPACT.value:
            observed_devs = [
                d for d in affected_devices
                if str((bundle.device_evidence.get(d) or {}).get("reachability_status") or "").upper() in ("DOWN", "SUSPECTED_DOWN", "DEGRADED")
            ]
            affected_devices = set(observed_devs)

        # Historical incidents involving target or dependents
        rel_incs: List[Dict[str, Any]] = []
        for inc in bundle.incident_evidence:
            inc_did = str(inc.get("device_id") or "")
            if inc_did == dev_id or inc_did in affected_devices:
                rel_incs.append(inc)

        conf_score = 0.88 if len(evidence_ids) >= 4 else 0.70
        conf_lbl = ConfidenceLabel.HIGH.value if conf_score >= 0.80 else ConfidenceLabel.MODERATE.value

        limitations = [
            "Analisis dampak didasarkan pada dependensi graf dan RIB saat ini; tidak mensimulasikan kegagalan daya fisik eksternal.",
            "Potensi dampak (POTENTIAL_IMPACT) adalah batas teoritis blast radius, bukan konfirmasi pemadaman aktual.",
        ]

        return ImpactAnalysisResult(
            impact_id=impact_id,
            target_entity_id=clean_target,
            target_entity_type=ent_type,
            impact_scope_type=impact_scope_type,
            direct_dependents=direct_dependents,
            indirect_dependents=indirect_dependents,
            potentially_affected_subnets=sorted(affected_subnets),
            potentially_affected_devices=sorted(affected_devices),
            affected_services=sorted(affected_services),
            routing_dependencies=routing_deps,
            protocol_relationships=protocol_rels,
            alternate_paths=alternate_paths,
            redundancy_status=red_status,
            redundancy_notes=red_notes,
            historical_incidents=rel_incs,
            confidence_score=conf_score,
            confidence_label=conf_lbl,
            evidence_ids=sorted(evidence_ids),
            limitations=limitations,
            analyzed_at=curr_ts,
        )
