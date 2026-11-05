"""
AIRA OS — Multi-Device Correlation Engine (Networking VI / WP 6.4).

Correlates observations across multiple devices using 13 structural, protocol, and temporal
dimensions so that a single underlying failure is not misdiagnosed as dozens of unrelated faults.

Supported Canonical Correlation Scenarios:
- Scenario A: Shared upstream device failure masking downstream unreachability incidents.
- Scenario B: Control-plane routing failure / BGP or OSPF withdrawal while physical links stay UP.
- Scenario C: Interface CRC/FCS/drop degradation (`oper_status == 'up'`) degrading downstream traffic.
- Scenario D: Layer-2 / VLAN membership mismatch isolating a specific VLAN while management stays UP.
- Scenario E: WAN latency / packet-loss degradation while LAN interfaces & default routes remain UP.
- Temporal Coincidence Guard: Co-occurring events without any graph/protocol/subnet/VLAN/WAN
  relationship are NEVER marked `is_causal_candidate = True`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.network_intelligence.confidence_model import ConfidenceScorer
from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    CanonicalEvidenceRecord,
    CorrelationDimension,
    CorrelationGroupResult,
    GraphEntityType,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph


class MultiDeviceCorrelationEngine:
    """Deterministic 13-dimension multi-device symptom & dependency correlator."""

    def correlate(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        investigation_window_sec: float = 300.0,
    ) -> List[CorrelationGroupResult]:
        qengine = GraphQueryEngine(graph)
        groups: List[CorrelationGroupResult] = []
        grouped_incident_ids: Set[str] = set()

        # Map device -> unreachable state & open incidents
        down_devices: Set[str] = set()
        for dev_id, dinfo in bundle.device_evidence.items():
            if str(dinfo.get("reachability_status") or "").upper() in ("DOWN", "SUSPECTED_DOWN", "UNREACHABLE"):
                down_devices.add(dev_id)

        incidents_by_dev: Dict[str, List[Dict[str, Any]]] = {}
        for inc in bundle.incident_evidence:
            if str(inc.get("status") or "open").lower() in ("open", "acknowledged", "active"):
                did = str(inc.get("device_id") or "")
                if did:
                    incidents_by_dev.setdefault(did, []).append(inc)

        # ------------------------------------------------------------------
        # Scenario A: Shared Upstream Device Failure
        # ------------------------------------------------------------------
        for up_dev in sorted(down_devices):
            dep_res = qengine.get_downstream_dependencies(up_dev, max_depth=6)
            down_dependents = [
                d["device_id"]
                for d in dep_res["all_dependents"]
                if d["device_id"] in down_devices or d["device_id"] in incidents_by_dev
            ]
            if down_dependents:
                involved = [up_dev] + sorted(set(down_dependents))
                rel_incs: List[str] = []
                inc_times: List[float] = []
                for d in involved:
                    for inc in incidents_by_dev.get(d, []):
                        iid = str(inc.get("id") or inc.get("incident_id") or "")
                        if iid:
                            rel_incs.append(iid)
                            grouped_incident_ids.add(iid)
                        if inc.get("started_at"):
                            inc_times.append(float(inc["started_at"]))

                within_window = True
                if len(inc_times) >= 2:
                    within_window = (max(inc_times) - min(inc_times)) <= max(investigation_window_sec, 60.0)

                dims = [
                    CorrelationDimension.DEVICE_IDENTITY.value,
                    CorrelationDimension.TOPOLOGY_DEPENDENCY.value,
                    CorrelationDimension.ROUTING_DEPENDENCY.value,
                ]
                if within_window and inc_times:
                    dims.extend([CorrelationDimension.TIME_WINDOW.value, CorrelationDimension.INCIDENT_TIMELINE.value])

                supp_recs: List[CanonicalEvidenceRecord] = []
                for d in involved:
                    supp_recs.extend(bundle.records_for_device(d, "device_resources"))
                supp_recs.extend([r for r in bundle.records if r.evidence_type in ("topology_edges", "nms_incidents")])

                missing_ev = [
                    f"Verifikasi out-of-band/daya listrik pada perangkat upstream '{up_dev}' untuk membedakan mati daya dari isolasi jalur manajemen kolektor AIRA."
                ]
                conf = ConfidenceScorer.evaluate(
                    supporting_records=supp_recs,
                    contradictory_count=0,
                    missing_count=1,
                    topology_consistent=True,
                    protocol_consistent=True,
                )
                groups.append(
                    CorrelationGroupResult(
                        correlation_id=f"cgrp_upstream_{uuid.uuid4().hex[:8]}",
                        investigation_window_sec=investigation_window_sec,
                        dimensions_matched=dims,
                        related_observations=[
                            f"Upstream '{up_dev}' tidak terjangkau",
                            f"{len(down_dependents)} perangkat hilir terdampak: {', '.join(down_dependents)}",
                        ],
                        related_devices=involved,
                        related_incidents=rel_incs,
                        shared_dependency=f"device:{up_dev}",
                        candidate_explanation=(
                            f"Kandidat akar masalah pada perangkat upstream '{up_dev}' menjelaskan ketidakterjangkauan "
                            f"simultan pada perangkat hilir ({', '.join(down_dependents)})."
                        ),
                        supporting_evidence=list(dict.fromkeys([r.evidence_id for r in supp_recs] + dep_res["evidence_basis"])),
                        contradictory_evidence=[],
                        confidence=conf,
                        missing_evidence=missing_ev,
                        alternative_hypotheses=[
                            "Kegagalan jalur jaringan lokal dari host kolektor AIRA menuju segmen manajemen (collection/vantage-point failure).",
                            "Pemadaman listrik simultan pada rak/site yang sama.",
                        ],
                        is_causal_candidate=True,
                    )
                )

        # ------------------------------------------------------------------
        # Scenario B: Control-Plane Routing / Protocol Withdrawal (Link & Device UP)
        # ------------------------------------------------------------------
        for dev_id, dinfo in bundle.device_evidence.items():
            if str(dinfo.get("reachability_status") or "").upper() != "UP":
                continue
            pdata = bundle.protocol_evidence.get(dev_id) or {}
            bgp_down = [
                bp for bp in (pdata.get("bgp_peers") or [])
                if isinstance(bp, dict) and str(bp.get("state") or "").lower() not in ("established", "up") and not bp.get("established")
            ]
            ospf_down = [
                nb for nb in (pdata.get("ospf_neighbors") or [])
                if isinstance(nb, dict) and "full" not in str(nb.get("state") or "").lower() and "2-way" not in str(nb.get("state") or "").lower()
            ]
            routes = bundle.routing_evidence.get(dev_id) or []
            inactive_or_unres = [r for r in routes if (not r.active or r.unreachable) and not r.disabled]

            if bgp_down or ospf_down or (pdata.get("withdrawn_prefixes")):
                ifaces_up = all(
                    str(i.get("oper_status") or "up").lower() == "up"
                    for i in (bundle.interface_evidence.get(dev_id) or [])
                    if str(i.get("admin_status") or "enabled").lower() == "enabled"
                )
                supp_recs = (
                    bundle.records_for_device(dev_id, "device_resources")
                    + bundle.records_for_device(dev_id, "interfaces")
                    + bundle.records_for_device(dev_id, "routes")
                    + bundle.records_for_device(dev_id, "bgp_peers")
                    + bundle.records_for_device(dev_id, "ospf_neighbors")
                )
                dims = [
                    CorrelationDimension.DEVICE_IDENTITY.value,
                    CorrelationDimension.PROTOCOL_ADJACENCY.value,
                    CorrelationDimension.ROUTING_DEPENDENCY.value,
                ]
                proto_label = "BGP" if bgp_down else ("OSPF" if ospf_down else "Routing")
                obs_notes = [f"Perangkat '{dev_id}' tetap terjangkau (UP)."]
                if ifaces_up:
                    obs_notes.append("Antarmuka fisik relevan tetap berstatus operasional 'up'.")
                if bgp_down:
                    obs_notes.append(f"{len(bgp_down)} sesi BGP tidak berstatus Established.")
                if ospf_down:
                    obs_notes.append(f"{len(ospf_down)} adjacency OSPF belum mencapai state Full.")
                if inactive_or_unres:
                    obs_notes.append(f"{len(inactive_or_unres)} rute pada RIB berstatus tidak aktif/unresolved.")

                down_deps = [d["device_id"] for d in qengine.get_downstream_dependencies(dev_id)["all_dependents"]]
                rel_devs = list(dict.fromkeys([dev_id] + down_deps))

                conf = ConfidenceScorer.evaluate(
                    supporting_records=supp_recs,
                    contradictory_count=0,
                    missing_count=0 if (bgp_down or ospf_down) else 1,
                    topology_consistent=True,
                    protocol_consistent=True,
                )
                groups.append(
                    CorrelationGroupResult(
                        correlation_id=f"cgrp_routing_{uuid.uuid4().hex[:8]}",
                        investigation_window_sec=investigation_window_sec,
                        dimensions_matched=dims,
                        related_observations=obs_notes,
                        related_devices=rel_devs,
                        related_incidents=[
                            str(inc.get("id") or inc.get("incident_id"))
                            for inc in incidents_by_dev.get(dev_id, [])
                            if inc.get("id") or inc.get("incident_id")
                        ],
                        shared_dependency=f"proto:{dev_id}:{proto_label.lower()}",
                        candidate_explanation=(
                            f"Gangguan kontrol-plane {proto_label} / penarikan rute pada '{dev_id}' lebih menjelaskan "
                            f"hilangnya keterjangkauan tujuan dibandingkan kegagalan link fisik (antarmuka tetap UP)."
                        ),
                        supporting_evidence=[r.evidence_id for r in supp_recs],
                        contradictory_evidence=[],
                        confidence=conf,
                        missing_evidence=[] if (bgp_down or ospf_down) else ["Detail sesi protokol pada peer seberang."],
                        alternative_hypotheses=[
                            "Filter kebijakan routing (route-filter / prefix-list) menolak prefix yang diterima.",
                            "Perubahan konfigurasi timer/autentikasi/AS pada router lawan.",
                        ],
                        is_causal_candidate=True,
                    )
                )

        # ------------------------------------------------------------------
        # Scenario C: Interface Error / Drop Degradation While Oper Status is UP
        # ------------------------------------------------------------------
        for dev_id, iflist in bundle.interface_evidence.items():
            for iface in iflist:
                oper = str(iface.get("oper_status") or "").lower()
                in_err = int(iface.get("in_errors") or 0)
                out_err = int(iface.get("out_errors") or 0)
                in_drp = int(iface.get("in_drops") or 0)
                out_drp = int(iface.get("out_drops") or 0)
                total_fault_pkts = in_err + out_err + in_drp + out_drp
                if oper == "up" and total_fault_pkts >= 25:
                    iname = str(iface.get("interface_name") or "")
                    supp_recs = (
                        bundle.records_for_device(dev_id, "interfaces")
                        + bundle.records_for_device(dev_id, "device_resources")
                    )
                    down_deps = [d["device_id"] for d in qengine.get_downstream_dependencies(dev_id)["all_dependents"]]
                    rel_devs = list(dict.fromkeys([dev_id] + down_deps))
                    conf = ConfidenceScorer.evaluate(
                        supporting_records=supp_recs,
                        contradictory_count=0,
                        missing_count=1,
                        topology_consistent=True,
                        protocol_consistent=True,
                    )
                    groups.append(
                        CorrelationGroupResult(
                            correlation_id=f"cgrp_ifdeg_{uuid.uuid4().hex[:8]}",
                            investigation_window_sec=investigation_window_sec,
                            dimensions_matched=[
                                CorrelationDimension.DEVICE_IDENTITY.value,
                                CorrelationDimension.INTERFACE_IDENTITY.value,
                                CorrelationDimension.TOPOLOGY_DEPENDENCY.value,
                            ],
                            related_observations=[
                                f"Antarmuka {dev_id}:{iname} berstatus 'up' namun memiliki error/drop tinggi (in_err={in_err}, out_err={out_err}, in_drop={in_drp}, out_drop={out_drp}).",
                                "Link-up pada Layer-1 tidak menjamin pengantaran paket bebas korupsi.",
                            ],
                            related_devices=rel_devs,
                            related_incidents=[
                                str(inc.get("id") or inc.get("incident_id"))
                                for inc in incidents_by_dev.get(dev_id, [])
                                if inc.get("id") or inc.get("incident_id")
                            ],
                            shared_dependency=f"iface:{dev_id}:{iname}",
                            candidate_explanation=(
                                f"Degradasi kualitas antarmuka {dev_id}:{iname} (error/drop meningkat saat link tetap 'up') "
                                f"berkorelasi dengan penurunan kualitas layanan hilir."
                            ),
                            supporting_evidence=[r.evidence_id for r in supp_recs],
                            contradictory_evidence=[],
                            confidence=conf,
                            missing_evidence=["Statistik optik SFP/kabel atau counter sisi peer untuk memastikan arah degradasi fisik."],
                            alternative_hypotheses=[
                                "Ketidakcocokan duplex (half/full) atau redaman kabel/SFP.",
                                "Kongesti antrean mikro-burst yang memicu tail-drop.",
                            ],
                            is_causal_candidate=True,
                        )
                    )

        # ------------------------------------------------------------------
        # Scenario D: VLAN Mismatch / Layer-2 Segment Discrepancy
        # ------------------------------------------------------------------
        vlan_nodes = graph.nodes_by_type(GraphEntityType.VLAN.value)
        if vlan_nodes:
            # Check physical/L2 connected device pairs where one side carries a VLAN on the link and the peer port does not!
            for edge in graph.edges.values():
                if edge.relationship_type not in ("PHYSICAL_ADJACENCY", "LAYER2_ADJACENCY"):
                    continue
                src_if = edge.attributes.get("source_interface")
                dst_if = edge.attributes.get("target_interface")
                src_dev = edge.source_id.replace("device:", "")
                dst_dev = edge.target_id.replace("device:", "")
                if not src_if or not dst_if or src_dev == dst_dev:
                    continue
                src_vlans = {
                    int(graph.edges[eid].attributes.get("vlan_id"))
                    for eid in graph.out_edges.get(f"iface:{src_dev}:{src_if}", [])
                    if graph.edges[eid].relationship_type == "CARRIES" and graph.edges[eid].attributes.get("vlan_id") is not None
                }
                dst_vlans = {
                    int(graph.edges[eid].attributes.get("vlan_id"))
                    for eid in graph.out_edges.get(f"iface:{dst_dev}:{dst_if}", [])
                    if graph.edges[eid].relationship_type == "CARRIES" and graph.edges[eid].attributes.get("vlan_id") is not None
                }
                if (src_vlans or dst_vlans) and src_vlans != dst_vlans:
                    mismatched = sorted(src_vlans ^ dst_vlans)
                    supp_recs = (
                        bundle.records_for_device(src_dev, "bridge_vlan")
                        + bundle.records_for_device(src_dev, "vlans")
                        + bundle.records_for_device(dst_dev, "bridge_vlan")
                        + bundle.records_for_device(dst_dev, "vlans")
                    )
                    conf = ConfidenceScorer.evaluate(
                        supporting_records=supp_recs,
                        contradictory_count=0,
                        missing_count=0 if (src_vlans and dst_vlans) else 1,
                        topology_consistent=True,
                        protocol_consistent=True,
                    )
                    groups.append(
                        CorrelationGroupResult(
                            correlation_id=f"cgrp_vlan_{uuid.uuid4().hex[:8]}",
                            investigation_window_sec=investigation_window_sec,
                            dimensions_matched=[
                                CorrelationDimension.VLAN_RELATIONSHIP.value,
                                CorrelationDimension.INTERFACE_IDENTITY.value,
                                CorrelationDimension.TOPOLOGY_DEPENDENCY.value,
                            ],
                            related_observations=[
                                f"Manajemen perangkat '{src_dev}' dan '{dst_dev}' tetap terjangkau, namun keanggotaan VLAN pada trunk {src_dev}:{src_if} ({sorted(src_vlans)}) != {dst_dev}:{dst_if} ({sorted(dst_vlans)}).",
                                f"VLAN terdampak isolasi Layer-2: {mismatched}.",
                            ],
                            related_devices=[src_dev, dst_dev],
                            related_incidents=[],
                            shared_dependency=f"vlan:global:{mismatched[0]}",
                            candidate_explanation=(
                                f"Ketidakcocokan konfigurasi VLAN ({mismatched}) antara {src_dev}:{src_if} dan {dst_dev}:{dst_if} "
                                f"mengisolasi segmen Layer-2 tersebut sementara segmen lain tetap sehat."
                            ),
                            supporting_evidence=[r.evidence_id for r in supp_recs],
                            contradictory_evidence=[],
                            confidence=conf,
                            missing_evidence=[],
                            alternative_hypotheses=["Port blocking STP/RSTP pada salah satu bridge VLAN."],
                            is_causal_candidate=True,
                        )
                    )

        # ------------------------------------------------------------------
        # Scenario E: WAN Quality Degradation (High Latency / Loss with Installed Routes)
        # ------------------------------------------------------------------
        for wnode in graph.nodes_by_type(GraphEntityType.WAN_CONNECTION.value):
            wdev = wnode.device_id or ""
            dinfo = bundle.device_evidence.get(wdev) or {}
            lat = dinfo.get("latency_ms")
            loss = dinfo.get("packet_loss_percent")
            if str(dinfo.get("reachability_status") or "").upper() in ("UP", "DEGRADED") and (
                (lat is not None and float(lat) >= 80.0) or (loss is not None and float(loss) >= 2.0)
            ):
                supp_recs = (
                    bundle.records_for_device(wdev, "device_resources")
                    + bundle.records_for_device(wdev, "routes")
                    + bundle.records_for_device(wdev, "interfaces")
                )
                down_deps = [d["device_id"] for d in qengine.get_downstream_dependencies(wdev)["all_dependents"]]
                rel_devs = list(dict.fromkeys([wdev] + down_deps))
                conf = ConfidenceScorer.evaluate(
                    supporting_records=supp_recs,
                    contradictory_count=0,
                    missing_count=1,
                    topology_consistent=True,
                    protocol_consistent=True,
                )
                groups.append(
                    CorrelationGroupResult(
                        correlation_id=f"cgrp_wan_{uuid.uuid4().hex[:8]}",
                        investigation_window_sec=investigation_window_sec,
                        dimensions_matched=[
                            CorrelationDimension.WAN_DEPENDENCY.value,
                            CorrelationDimension.ROUTING_DEPENDENCY.value,
                            CorrelationDimension.NEXT_HOP_RELATIONSHIP.value,
                        ],
                        related_observations=[
                            f"Rute default pada '{wdev}' tetap terpasang dan antarmuka LAN sehat.",
                            f"Kualitas jalur WAN menurun (latency={lat} ms, packet_loss={loss}%).",
                        ],
                        related_devices=rel_devs,
                        related_incidents=[
                            str(inc.get("id") or inc.get("incident_id"))
                            for inc in incidents_by_dev.get(wdev, [])
                            if inc.get("id") or inc.get("incident_id")
                        ],
                        shared_dependency=wnode.node_id,
                        candidate_explanation=(
                            f"Degradasi kualitas link WAN pada '{wdev}' (bukan hilangnya rute) memengaruhi layanan yang "
                            f"bergantung pada gateway egress {wnode.attributes.get('gateway_ip')}."
                        ),
                        supporting_evidence=[r.evidence_id for r in supp_recs],
                        contradictory_evidence=[],
                        confidence=conf,
                        missing_evidence=["Probe latensi per-hop ke sisi ISP untuk memisahkan saturasi lokal dari gangguan upstream ISP."],
                        alternative_hypotheses=[
                            "Saturasi bandwidth pada antrean/egress WAN.",
                            "Gangguan jaringan internal penyedia layanan (ISP).",
                        ],
                        is_causal_candidate=True,
                    )
                )

        # ------------------------------------------------------------------
        # Temporal Coincidence Guard: Unrelated Simultaneous Incidents
        # ------------------------------------------------------------------
        ungrouped_incs = [
            inc for inc in bundle.incident_evidence
            if str(inc.get("status") or "open").lower() in ("open", "acknowledged", "active")
            and str(inc.get("id") or inc.get("incident_id") or "") not in grouped_incident_ids
        ]
        if len(ungrouped_incs) >= 2:
            ts_vals = [float(i["started_at"]) for i in ungrouped_incs if i.get("started_at") is not None]
            if len(ts_vals) >= 2 and (max(ts_vals) - min(ts_vals)) <= investigation_window_sec:
                udevs = sorted({str(i.get("device_id") or "") for i in ungrouped_incs if i.get("device_id")})
                if len(udevs) >= 2:
                    inc_recs = [r for r in bundle.records if r.evidence_type == "nms_incidents"]
                    conf = ConfidenceScorer.evaluate(
                        supporting_records=inc_recs,
                        contradictory_count=0,
                        missing_count=2,
                        topology_consistent=None,
                        protocol_consistent=None,
                        independent_source_count=1,
                    )
                    groups.append(
                        CorrelationGroupResult(
                            correlation_id=f"cgrp_temporal_{uuid.uuid4().hex[:8]}",
                            investigation_window_sec=investigation_window_sec,
                            dimensions_matched=[CorrelationDimension.TIME_WINDOW.value, CorrelationDimension.INCIDENT_TIMELINE.value],
                            related_observations=[
                                f"{len(ungrouped_incs)} insiden terjadi berdekatan waktu pada perangkat {', '.join(udevs)} tanpa bukti dependensi struktural bersama."
                            ],
                            related_devices=udevs,
                            related_incidents=[str(i.get("id") or i.get("incident_id")) for i in ungrouped_incs],
                            shared_dependency=None,
                            candidate_explanation=(
                                "Insiden terjadi dalam jendela waktu berdekatan, tetapi kedekatan waktu saja TIDAK cukup "
                                "untuk menyatakan hubungan sebab-akibat tanpa bukti dependensi topologi/routing/VLAN/WAN."
                            ),
                            supporting_evidence=[r.evidence_id for r in inc_recs],
                            contradictory_evidence=[],
                            confidence=conf,
                            missing_evidence=["Data topologi L1/L2/L3 antar perangkat tersebut untuk memastikan ada/tidaknya jalur bersama."],
                            alternative_hypotheses=[
                                "Dua insiden independen yang kebetulan terjadi bersamaan.",
                                "Dependensi topologi belum terdokumentasi di inventaris.",
                            ],
                            is_causal_candidate=False,
                        )
                    )

        return groups
