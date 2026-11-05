"""
AIRA OS — Non-Destructive In-Memory Failure Simulator (Networking VI / WP 6.7).

Provides safe, in-memory analytical simulations of network failure scenarios without
modifying real RouterOS devices or production SQLite topology state.

Supported Analytical Failure Modes:
- `UPSTREAM_ROUTER_DOWN`
- `WAN_ROUTE_LOSS`
- `OSPF_NEIGHBOR_LOSS`
- `BGP_PEER_WITHDRAWAL`
- `TRUNK_LOSS`
- `TUNNEL_DOWN`

Every result carries `is_simulation = True` and explicit assumptions/limitations.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    ConfidenceLabel,
    GraphEntityType,
    GraphRelationshipType,
    NetworkEvidenceBundle,
    SimulationResult,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph


class FailureSimulator:
    """Non-destructive in-memory network failure simulator."""

    def simulate_failure(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        failure_type: str,
        entity_id: str,
        now: Optional[float] = None,
    ) -> SimulationResult:
        curr_ts = float(now) if now is not None else time.time()
        sim_id = f"sim_{uuid.uuid4().hex[:10]}"
        ftype = failure_type.strip().upper()
        clean_ent = entity_id.strip()

        evidence_ids: Set[str] = set()
        unreachable_segments: Set[str] = set()
        isolated_devices: Set[str] = set()
        alternate_paths: List[Dict[str, Any]] = []
        assumptions: List[str] = [
            "Simulasi dijalankan murni di memori (in-memory analytical) tanpa mengubah konfigurasi atau database produksi.",
            "Semua rute konvergensi diasumsikan mengikuti tabel routing statis dan topologi bukti saat ini.",
        ]
        unknown_dependencies: List[str] = []

        qengine = GraphQueryEngine(graph)
        dev_node = clean_ent if clean_ent.startswith("device:") else f"device:{clean_ent}"
        target_dev = clean_ent.replace("device:", "")

        if ftype == "UPSTREAM_ROUTER_DOWN":
            assumptions.append(f"Perangkat upstream '{target_dev}' disimulasikan padam / tidak responsif.")
            dep_res = qengine.get_downstream_dependencies(target_dev, max_depth=6)
            evidence_ids.update(dep_res["evidence_basis"])

            for dep in dep_res["all_dependents"]:
                did = dep["device_id"]
                # Check if dependent device has alternate path bypassing target_dev
                alt = qengine.find_alternate_paths(did, "ISP-Edge", excluded_ids={target_dev})
                if alt["paths"]:
                    alternate_paths.extend(alt["paths"])
                    evidence_ids.update(alt["evidence_basis"])
                else:
                    isolated_devices.add(did)
                    seg_res = qengine.get_reachable_segments(did)
                    evidence_ids.update(seg_res["evidence_basis"])
                    for s in seg_res["segments"]:
                        unreachable_segments.add(s["segment"])

            redundancy_findings = (
                f"{len(isolated_devices)} perangkat terisolasi tanpa jalur alternatif ({', '.join(sorted(isolated_devices)) or 'tidak ada'}). "
                f"{len(alternate_paths)} jalur alternatif teridentifikasi untuk perangkat lain."
            )

        elif ftype == "WAN_ROUTE_LOSS":
            assumptions.append(f"Rute default WAN pada '{target_dev}' ditarik/hilang.")
            routes = bundle.routing_evidence.get(target_dev) or []
            default_routes = [r for r in routes if r.is_default_route() and r.active]
            if default_routes:
                evidence_ids.update([r.evidence_id for r in bundle.records_for_device(target_dev, "routes")])
                backup_routes = [r for r in routes if r.is_default_route() and not r.active]
                if backup_routes:
                    alternate_paths.append(
                        {
                            "description": "Tersedia rute cadangan (floating static/backup) di RIB yang dapat aktif jika gateway utama gagal.",
                            "backup_gateways": [r.gateway for r in backup_routes],
                        }
                    )
                    redundancy_findings = "Tersedia rute default sekunder di RIB lokal."
                else:
                    isolated_devices.add(target_dev)
                    unreachable_segments.add("0.0.0.0/0 (Internet / WAN Egress)")
                    redundancy_findings = "Tidak terdeteksi rute default WAN cadangan pada perangkat ini."
            else:
                unknown_dependencies.append(f"Perangkat '{target_dev}' tidak memiliki rute default aktif di bukti RIB.")
                redundancy_findings = "Tidak ada rute WAN yang dapat disimulasikan hilang."

        elif ftype in ("OSPF_NEIGHBOR_LOSS", "BGP_PEER_WITHDRAWAL"):
            proto_name = "OSPF" if "OSPF" in ftype else "BGP"
            assumptions.append(f"Sesi / adjacency {proto_name} pada '{target_dev}' disimulasikan putus.")
            pdata = bundle.protocol_evidence.get(target_dev) or {}
            proto_key = "ospf_neighbors" if proto_name == "OSPF" else "bgp_peers"
            peers = pdata.get(proto_key) or []
            if peers:
                evidence_ids.update([r.evidence_id for r in bundle.records_for_device(target_dev, proto_key)])
                dep_res = qengine.get_downstream_dependencies(target_dev, max_depth=3)
                evidence_ids.update(dep_res["evidence_basis"])
                for d in dep_res["all_dependents"]:
                    isolated_devices.add(d["device_id"])
                redundancy_findings = (
                    f"Putusnya {proto_name} berdampak pada {len(isolated_devices)} perangkat hilir "
                    f"yang bergantung pada rute dinamis {target_dev}."
                )
            else:
                unknown_dependencies.append(f"Bukti tetangga/peer {proto_name} tidak ditemukan pada '{target_dev}'.")
                redundancy_findings = f"Tidak ada sesi {proto_name} aktif yang teramati."

        elif ftype == "TRUNK_LOSS":
            assumptions.append(f"Trunk link/VLAN pada '{clean_ent}' disimulasikan down.")
            vlan_nodes = graph.nodes_by_type(GraphEntityType.VLAN.value)
            for vn in vlan_nodes:
                vid = vn.attributes.get("vlan_id")
                if vid:
                    unreachable_segments.add(f"VLAN {vid} L2 Domain")
            redundancy_findings = "Kehilangan trunk link mengisolasi broadcast domain VLAN yang bersangkutan."

        elif ftype == "TUNNEL_DOWN":
            assumptions.append(f"Tunnel interface '{clean_ent}' disimulasikan down.")
            tunnels = (bundle.protocol_evidence.get(target_dev) or {}).get("tunnels") or []
            if tunnels:
                evidence_ids.update([r.evidence_id for r in bundle.records_for_device(target_dev, "tunnels")])
            unreachable_segments.add(f"Overlaid Tunnel Segment ({clean_ent})")
            redundancy_findings = "Trafik transit VPN/GRE terputus kecuali terdapat rute alternatif via link fisik."

        else:
            assumptions.append(f"Tipe kegagalan '{ftype}' tidak dikenal; simulasi analitis generik.")
            redundancy_findings = "Simulasi generik tidak dapat mengevaluasi redundansi spesifik."

        conf_score = 0.85 if evidence_ids else 0.65
        conf_lbl = ConfidenceLabel.HIGH.value if conf_score >= 0.80 else ConfidenceLabel.MODERATE.value

        return SimulationResult(
            simulation_id=sim_id,
            is_simulation=True,
            simulated_failure_type=ftype,
            simulated_entity_id=clean_ent,
            affected_dependency_graph={
                "target_entity": clean_ent,
                "isolated_device_count": len(isolated_devices),
                "unreachable_segment_count": len(unreachable_segments),
                "alternate_path_count": len(alternate_paths),
            },
            potentially_unreachable_segments=sorted(unreachable_segments),
            potentially_isolated_devices=sorted(isolated_devices),
            alternate_paths_available=alternate_paths,
            redundancy_findings=redundancy_findings,
            assumptions=assumptions,
            unknown_dependencies=unknown_dependencies,
            confidence_score=conf_score,
            confidence_label=conf_lbl,
            evidence_ids=sorted(evidence_ids),
            simulated_at=curr_ts,
        )
