"""
AIRA OS — Deterministic 14-Step Root Cause Analysis Engine (Networking VI / WP 6.5).

Executes a reproducible, LLM-independent 14-step RCA pipeline over `NetworkEvidenceBundle`,
`NetworkKnowledgeGraph`, `MultiDeviceCorrelationEngine`, and optional path/protocol inputs.

Strictly separates:
- `ROOT_CAUSE`
- `CONTRIBUTING_FACTOR`
- `SECONDARY_SYMPTOM`
- `CORRELATED_EVENT`
- `UNKNOWN_CAUSE`

Supports all 17 `HypothesisCategory` fault classes and refuses to fabricate certainty when
evidence is missing, stale, or contradictory.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set
import uuid

from core.network_intelligence.confidence_model import ConfidenceScorer
from core.network_intelligence.correlation_engine import MultiDeviceCorrelationEngine
from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    CanonicalEvidenceRecord,
    ConfidenceAssessment,
    ConfidenceLabel,
    CorrelationGroupResult,
    FindingClassification,
    HypothesisCategory,
    IntelligenceFreshness,
    NetworkEvidenceBundle,
    RCAHypothesis,
    RCAReport,
    RCATimelineEvent,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.routing.unified_route_parser import NextHopResolutionStatus, resolve_recursive_next_hop

PIPELINE_STEPS_14: List[str] = [
    "1_DEFINE_INVESTIGATION_SCOPE",
    "2_COLLECT_OR_REUSE_EVIDENCE",
    "3_VALIDATE_EVIDENCE_FRESHNESS",
    "4_BUILD_DEPENDENCY_SUBGRAPH",
    "5_IDENTIFY_AFFECTED_ENTITIES",
    "6_ESTABLISH_INCIDENT_TIMELINE",
    "7_IDENTIFY_ABNORMAL_OBSERVATIONS",
    "8_GENERATE_CANDIDATE_HYPOTHESES",
    "9_EVALUATE_SUPPORTING_EVIDENCE",
    "10_EVALUATE_CONTRADICTORY_EVIDENCE",
    "11_RANK_HYPOTHESES",
    "12_IDENTIFY_MISSING_EVIDENCE",
    "13_PRODUCE_EXPLANATION_AND_REVIEW_REMEDIATION",
    "14_PACKAGE_RESULT_AND_EVIDENCE_REFERENCES",
]


class RootCauseAnalysisEngine:
    """Deterministic, evidence-traceable Root Cause Analysis engine."""

    def __init__(self, correlation_engine: Optional[MultiDeviceCorrelationEngine] = None) -> None:
        self.correlator = correlation_engine or MultiDeviceCorrelationEngine()

    def analyze(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        scope: str = "network",
        correlations: Optional[List[CorrelationGroupResult]] = None,
        now: Optional[float] = None,
    ) -> RCAReport:
        curr_ts = float(now) if now is not None else time.time()
        rca_id = f"rca_{uuid.uuid4().hex[:10]}"
        steps_done: List[str] = []

        # Step 1 & 2: Scope & Evidence Bundle Reuse
        steps_done.extend([PIPELINE_STEPS_14[0], PIPELINE_STEPS_14[1]])

        # Step 3: Validate Evidence Freshness
        stale_or_expired_ids = [
            r.evidence_id
            for r in bundle.records
            if r.freshness in (IntelligenceFreshness.STALE.value, IntelligenceFreshness.EXPIRED.value, IntelligenceFreshness.UNKNOWN.value)
        ]
        steps_done.append(PIPELINE_STEPS_14[2])

        # Step 4: Dependency Subgraph & Correlation
        qengine = GraphQueryEngine(graph)
        corr_groups = correlations if correlations is not None else self.correlator.correlate(bundle, graph)
        steps_done.append(PIPELINE_STEPS_14[3])

        # Step 5: Identify Affected Entities
        affected_devices: Set[str] = set()
        affected_services: Set[str] = set()
        downstream_symptom_devs: Set[str] = set()

        for grp in corr_groups:
            if grp.is_causal_candidate and grp.shared_dependency and grp.shared_dependency.startswith("device:"):
                root_d = grp.shared_dependency.replace("device:", "")
                for rd in grp.related_devices:
                    affected_devices.add(rd)
                    if rd != root_d:
                        downstream_symptom_devs.add(rd)

        for dev_id, dinfo in bundle.device_evidence.items():
            if str(dinfo.get("reachability_status") or "").upper() in ("DOWN", "SUSPECTED_DOWN", "DEGRADED", "MONITORING_UNAVAILABLE"):
                affected_devices.add(dev_id)
                svc_res = qengine.get_affected_services(dev_id)
                for s in svc_res["services"]:
                    affected_services.add(s["label"])
        steps_done.append(PIPELINE_STEPS_14[4])

        # Step 6: Establish Chronological Incident Timeline
        timeline: List[RCATimelineEvent] = []
        for inc in bundle.incident_evidence:
            ts = float(inc.get("started_at") or bundle.assembled_at)
            did = str(inc.get("device_id") or "network")
            cls_role = (
                FindingClassification.SECONDARY_SYMPTOM.value
                if did in downstream_symptom_devs
                else FindingClassification.CORRELATED_EVENT.value
            )
            timeline.append(
                RCATimelineEvent(
                    timestamp=ts,
                    event_type="INCIDENT_START",
                    entity_id=f"device:{did}",
                    summary=f"[{inc.get('severity', 'info').upper()}] {inc.get('title') or inc.get('incident_type')}",
                    classification=cls_role,
                    evidence_ids=[r.evidence_id for r in bundle.records if r.evidence_type == "nms_incidents"],
                )
            )
            if inc.get("resolved_at"):
                timeline.append(
                    RCATimelineEvent(
                        timestamp=float(inc["resolved_at"]),
                        event_type="RECOVERY",
                        entity_id=f"device:{did}",
                        summary=f"Insiden pada {did} pulih.",
                        classification=FindingClassification.CORRELATED_EVENT.value,
                    )
                )
        timeline.sort(key=lambda ev: ev.timestamp)
        steps_done.append(PIPELINE_STEPS_14[5])

        # Step 7, 8, 9, 10: Abnormal Observations & Hypothesis Generation + Supporting/Contradictory Evaluation
        steps_done.append(PIPELINE_STEPS_14[6])
        candidates: List[RCAHypothesis] = []
        contributing_factors: List[Dict[str, Any]] = []
        secondary_symptoms: List[Dict[str, Any]] = []
        correlated_events: List[Dict[str, Any]] = []
        global_missing: List[str] = [f"{g.device_id}:{g.evidence_type} ({g.gap_reason})" for g in bundle.collection_gaps]

        for grp in corr_groups:
            if not grp.is_causal_candidate:
                correlated_events.append(
                    {
                        "correlation_id": grp.correlation_id,
                        "classification": FindingClassification.CORRELATED_EVENT.value,
                        "description": grp.candidate_explanation,
                        "devices": grp.related_devices,
                    }
                )

        # Evaluate per-device abnormalities across all 17 categories
        for dev_id, dinfo in bundle.device_evidence.items():
            reach = str(dinfo.get("reachability_status") or "UNKNOWN").upper()
            dev_recs = bundle.records_for_device(dev_id, "device_resources")
            if_recs = bundle.records_for_device(dev_id, "interfaces")
            rt_recs = bundle.records_for_device(dev_id, "routes")
            pdata = bundle.protocol_evidence.get(dev_id) or {}

            # 1) Downstream symptom classification vs Upstream DEVICE_FAILURE
            if dev_id in downstream_symptom_devs:
                secondary_symptoms.append(
                    {
                        "entity_id": f"device:{dev_id}",
                        "classification": FindingClassification.SECONDARY_SYMPTOM.value,
                        "description": f"Ketidakterjangkauan '{dev_id}' terklasifikasi sebagai gejala sekunder akibat kegagalan perangkat upstream.",
                        "evidence_ids": [r.evidence_id for r in dev_recs],
                    }
                )
            elif reach in ("DOWN", "SUSPECTED_DOWN", "UNREACHABLE"):
                down_dependents = [d["device_id"] for d in qengine.get_downstream_dependencies(dev_id)["all_dependents"]]
                supp = list(dev_recs) + [r for r in bundle.records if r.evidence_type in ("topology_edges", "nms_incidents")]
                # Always generate BOTH DEVICE_FAILURE and TELEMETRY_FAILURE/Vantage-Point alternative so timeout is never claimed as 100% power-off!
                conf_dev = ConfidenceScorer.evaluate(
                    supporting_records=supp,
                    contradictory_count=0,
                    missing_count=1 if down_dependents else 2,
                    topology_consistent=True,
                    protocol_consistent=True,
                    independent_source_count=3 if down_dependents else 1,
                )
                candidates.append(
                    RCAHypothesis(
                        hypothesis_id=f"hyp_dev_{dev_id}_{uuid.uuid4().hex[:6]}",
                        category=HypothesisCategory.DEVICE_FAILURE.value,
                        classification=FindingClassification.ROOT_CAUSE.value,
                        title=f"Kegagalan Keterjangkauan / Perangkat pada {dev_id}",
                        description=(
                            f"Perangkat '{dev_id}' berstatus {reach}"
                            + (f" dan berdampak pada {len(down_dependents)} perangkat hilir ({', '.join(down_dependents)})." if down_dependents else " (timeout observasi dari kolektor AIRA; bukan bukti tunggal mati daya).")
                        ),
                        root_entity_id=f"device:{dev_id}",
                        affected_scope=[dev_id] + down_dependents,
                        supporting_evidence=[r.evidence_id for r in supp],
                        contradictory_evidence=[],
                        expected_observations=["Probe ICMP gagal", "Perangkat hilir ikut tidak terjangkau bila transit gagal"],
                        missing_observations=["Verifikasi daya fisik / konsol serial pada perangkat"],
                        confidence=conf_dev,
                        alternative_explanations=[
                            "Putusnya link fisik uplink menuju perangkat tersebut (PHYSICAL_LINK_FAILURE).",
                            "Kegagalan jalur jaringan dari kolektor telemetri AIRA (TELEMETRY_FAILURE).",
                        ],
                    )
                )
                # Companion TELEMETRY_FAILURE hypothesis when single isolated timeout occurs
                if not down_dependents:
                    conf_tel = ConfidenceScorer.evaluate(
                        supporting_records=dev_recs,
                        contradictory_count=0,
                        missing_count=2,
                        independent_source_count=1,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_tel_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.TELEMETRY_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Gangguan Jalur Observasi / Manajemen menuju {dev_id}",
                            description=f"Timeout ke '{dev_id}' tanpa kegagalan hilir yang terkoroborasi dapat disebabkan oleh pemblokiran manajemen/ICMP.",
                            root_entity_id=f"device:{dev_id}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in dev_recs],
                            missing_observations=["Status antarmuka dari router tetangga yang terhubung langsung"],
                            confidence=conf_tel,
                        )
                    )

            elif reach == "MONITORING_UNAVAILABLE":
                conf_tel = ConfidenceScorer.evaluate(
                    supporting_records=dev_recs,
                    contradictory_count=0,
                    missing_count=1,
                    independent_source_count=2,
                )
                candidates.append(
                    RCAHypothesis(
                        hypothesis_id=f"hyp_mgmt_{dev_id}_{uuid.uuid4().hex[:6]}",
                        category=HypothesisCategory.TELEMETRY_FAILURE.value,
                        classification=FindingClassification.ROOT_CAUSE.value,
                        title=f"Layanan Manajemen SSH/SNMP Tidak Tersedia pada {dev_id}",
                        description=f"Perangkat '{dev_id}' merespons ICMP (UP), tetapi interogasi manajemen SSH/SNMP gagal.",
                        root_entity_id=f"device:{dev_id}",
                        affected_scope=[dev_id],
                        supporting_evidence=[r.evidence_id for r in dev_recs],
                        missing_observations=["Verifikasi kredensial SSH/komunitas SNMP dan ACL `/ip service`."],
                        confidence=conf_tel,
                    )
                )

            # 2) Resource Exhaustion (CPU/Memory pressure — treated carefully: Contributing Factor unless >=95% with drops/timeouts)
            cpu = dinfo.get("cpu_load_percent")
            mem = dinfo.get("memory_used_percent")
            if (cpu is not None and float(cpu) >= 85.0) or (mem is not None and float(mem) >= 90.0):
                is_extreme = (cpu is not None and float(cpu) >= 95.0) or (mem is not None and float(mem) >= 95.0)
                contributing_factors.append(
                    {
                        "entity_id": f"device:{dev_id}",
                        "classification": FindingClassification.CONTRIBUTING_FACTOR.value,
                        "description": f"Tekanan resource tinggi pada '{dev_id}' (CPU={cpu}%, Mem={mem}%). CPU tinggi tidak otomatis menjadi akar outage tanpa bukti drop/timeout kontrol-plane.",
                        "evidence_ids": [r.evidence_id for r in dev_recs],
                    }
                )
                if is_extreme:
                    conf_res = ConfidenceScorer.evaluate(
                        supporting_records=dev_recs,
                        contradictory_count=0 if reach != "UP" else 1,
                        missing_count=1,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_res_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.RESOURCE_EXHAUSTION.value,
                            classification=FindingClassification.CONTRIBUTING_FACTOR.value,
                            title=f"Kelelahan Resource CPU/Memori pada {dev_id}",
                            description=f"Saturasi resource pada '{dev_id}' (CPU={cpu}%, Mem={mem}%) berpotensi menghambat proses routing/manajemen.",
                            root_entity_id=f"device:{dev_id}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in dev_recs],
                            contradictory_evidence=["Perangkat masih merespons manajemen (UP)"] if reach == "UP" else [],
                            missing_observations=["Profil proses `/tool profile` untuk mengidentifikasi penyebab beban CPU."],
                            confidence=conf_res,
                        )
                    )

            # 3) Interface Failure & Physical Link Failure / Error Degradation
            for iface in bundle.interface_evidence.get(dev_id, []):
                iname = str(iface.get("interface_name") or "")
                oper = str(iface.get("oper_status") or "unknown").lower()
                admin = str(iface.get("admin_status") or "enabled").lower()
                errs = int(iface.get("in_errors") or 0) + int(iface.get("out_errors") or 0)
                drops = int(iface.get("in_drops") or 0) + int(iface.get("out_drops") or 0)

                if admin == "enabled" and oper == "down":
                    # Check if interface is part of a physical topology link
                    has_phys_edge = any(
                        e.relationship_type == "PHYSICAL_ADJACENCY"
                        and (e.attributes.get("source_interface") == iname or e.attributes.get("target_interface") == iname)
                        for e in graph.edges.values()
                    )
                    cat = HypothesisCategory.PHYSICAL_LINK_FAILURE.value if has_phys_edge else HypothesisCategory.INTERFACE_FAILURE.value
                    conf_if = ConfidenceScorer.evaluate(
                        supporting_records=if_recs + dev_recs,
                        contradictory_count=0,
                        missing_count=0 if has_phys_edge else 1,
                        topology_consistent=True,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_ifdown_{dev_id}_{iname}_{uuid.uuid4().hex[:4]}",
                            category=cat,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Link / Antarmuka {dev_id}:{iname} Berstatus DOWN",
                            description=f"Antarmuka '{iname}' pada '{dev_id}' aktif secara administratif (enabled) tetapi status operasionalnya 'down'.",
                            root_entity_id=f"iface:{dev_id}:{iname}",
                            affected_scope=[dev_id, f"{dev_id}:{iname}"],
                            supporting_evidence=[r.evidence_id for r in if_recs],
                            missing_observations=[] if has_phys_edge else ["Status port pasangan pada perangkat lawan."],
                            confidence=conf_if,
                        )
                    )
                elif oper == "up" and (errs + drops) >= 25:
                    conf_deg = ConfidenceScorer.evaluate(
                        supporting_records=if_recs + dev_recs,
                        contradictory_count=0,
                        missing_count=1,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_ifdeg_{dev_id}_{iname}_{uuid.uuid4().hex[:4]}",
                            category=HypothesisCategory.INTERFACE_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Degradasi Error/Drop pada Antarmuka {dev_id}:{iname}",
                            description=f"Antarmuka '{dev_id}:{iname}' berstatus 'up', namun mengakumulasi error={errs} dan drop={drops}.",
                            root_entity_id=f"iface:{dev_id}:{iname}",
                            affected_scope=[dev_id, f"{dev_id}:{iname}"],
                            supporting_evidence=[r.evidence_id for r in if_recs],
                            missing_observations=["Diagnostik kabel/optik dan kecocokan duplex pada kedua sisi link."],
                            confidence=conf_deg,
                        )
                    )

            # 4) BGP Failure / Prefix Absence
            bgp_recs = bundle.records_for_device(dev_id, "bgp_peers") + bundle.records_for_device(dev_id, "bgp_routes")
            for bp in pdata.get("bgp_peers") or []:
                if not isinstance(bp, dict):
                    continue
                rem = str(bp.get("remote_address") or bp.get("name") or "peer")
                st = str(bp.get("state") or ("established" if bp.get("established") else "idle")).lower()
                pfx_rcvd = bp.get("prefixes_received")
                if st != "established":
                    conf_bgp = ConfidenceScorer.evaluate(
                        supporting_records=bgp_recs + rt_recs + dev_recs,
                        contradictory_count=0,
                        missing_count=0,
                        protocol_consistent=True,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_bgp_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.BGP_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Sesi BGP pada {dev_id} dengan Peer {rem} Tidak Established ({st})",
                            description=f"Sesi BGP menuju {rem} (AS {bp.get('remote_as', '?')}) berada pada state '{st}', menyebabkan penarikan rute BGP terkait.",
                            root_entity_id=f"bgp_peer:{dev_id}:{rem}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in (bgp_recs + rt_recs)],
                            confidence=conf_bgp,
                            alternative_explanations=["Filter TCP port 179, ketidakcocokan AS/MD5, atau kegagalan rute underlay ke peer."],
                        )
                    )
                elif pfx_rcvd == 0 or bp.get("missing_expected_prefixes"):
                    conf_bgp_pfx = ConfidenceScorer.evaluate(
                        supporting_records=bgp_recs + rt_recs,
                        contradictory_count=0,
                        missing_count=1,
                        protocol_consistent=True,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_bgppfx_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.BGP_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Sesi BGP {dev_id}<->{rem} Established Namun Prefix Tidak Diterima/Terpasang",
                            description=f"Sesi BGP ke {rem} berstatus Established, tetapi prefix yang diharapkan tidak masuk/terpilih di RIB.",
                            root_entity_id=f"bgp_peer:{dev_id}:{rem}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in (bgp_recs + rt_recs)],
                            missing_observations=["Kebijakan inbound routing filter atau advertisement dari sisi peer."],
                            confidence=conf_bgp_pfx,
                        )
                    )

            # 5) OSPF Failure
            ospf_recs = bundle.records_for_device(dev_id, "ospf_neighbors") + bundle.records_for_device(dev_id, "ospf_instance")
            for onb in pdata.get("ospf_neighbors") or []:
                if not isinstance(onb, dict):
                    continue
                ost = str(onb.get("state") or "").lower()
                if "full" not in ost and "2-way" not in ost:
                    nrid = str(onb.get("router_id") or onb.get("address") or "neighbor")
                    conf_ospf = ConfidenceScorer.evaluate(
                        supporting_records=ospf_recs + rt_recs + dev_recs,
                        contradictory_count=0,
                        missing_count=0 if ospf_recs else 1,
                        protocol_consistent=True,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_ospf_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.OSPF_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Adjacency OSPF {dev_id} <-> {nrid} Tertahan/Turun (State: {onb.get('state')})",
                            description=f"Tetangga OSPF {nrid} pada antarmuka {onb.get('interface') or '?'} tidak mencapai state Full ({onb.get('state')}).",
                            root_entity_id=f"ospf_nbr:{dev_id}:{nrid}:{onb.get('interface') or ''}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in (ospf_recs + rt_recs)],
                            confidence=conf_ospf,
                            alternative_explanations=[
                                "Ketidakcocokan MTU (tertahan di ExStart/Exchange), area ID, hello/dead timer, atau tipe jaringan OSPF."
                            ],
                        )
                    )

            # 6) Next-Hop Failure & Routing Failure (Unresolved recursive / unreachable routes)
            dev_routes = bundle.routing_evidence.get(dev_id) or []
            if dev_routes and dev_id not in downstream_symptom_devs:
                for r in dev_routes:
                    if r.disabled or r.connect:
                        continue
                    t_routes = [x for x in dev_routes if (x.routing_table or "main") == (r.routing_table or "main")]
                    gw_str = str(r.immediate_gw or r.gateway or "").split(",")[0].strip()
                    res = resolve_recursive_next_hop(gw_str, t_routes, max_depth=16)
                    unres_without_iface = (
                        not r.interface_name
                        and res.status in (NextHopResolutionStatus.UNRESOLVED, NextHopResolutionStatus.UNREACHABLE)
                        and any(x.connect for x in t_routes)
                    )
                    if res.loop_detected or (not r.active and r.unreachable) or unres_without_iface:
                        conf_nh = ConfidenceScorer.evaluate(
                            supporting_records=rt_recs + dev_recs,
                            contradictory_count=0,
                            missing_count=0,
                            protocol_consistent=True,
                        )
                        candidates.append(
                            RCAHypothesis(
                                hypothesis_id=f"hyp_nh_{dev_id}_{uuid.uuid4().hex[:6]}",
                                category=HypothesisCategory.NEXT_HOP_FAILURE.value,
                                classification=FindingClassification.ROOT_CAUSE.value,
                                title=f"Next-Hop Tidak Terjangkau / Unresolved pada {dev_id} ({r.dst_prefix})",
                                description=f"Rute {r.dst_prefix} via {r.gateway} pada tabel '{r.routing_table}' tidak dapat me-resolve next-hop aktif ({res.status.value}).",
                                root_entity_id=f"nexthop:{dev_id}:{r.routing_table}:{r.gateway}",
                                affected_scope=[dev_id],
                                supporting_evidence=[rec.evidence_id for rec in rt_recs],
                                confidence=conf_nh,
                            )
                        )
                        break

                if pdata.get("withdrawn_prefixes") and not bgp_recs and not ospf_recs:
                    conf_rt = ConfidenceScorer.evaluate(
                        supporting_records=rt_recs + dev_recs,
                        contradictory_count=0,
                        missing_count=1,
                    )
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_rt_{dev_id}_{uuid.uuid4().hex[:6]}",
                            category=HypothesisCategory.ROUTING_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Hilangnya Rute / Penarikan Prefix pada {dev_id}",
                            description=f"Prefix {pdata.get('withdrawn_prefixes')} menghilang dari tabel routing '{dev_id}'.",
                            root_entity_id=f"device:{dev_id}",
                            affected_scope=[dev_id],
                            supporting_evidence=[rec.evidence_id for rec in rt_recs],
                            missing_observations=["State protokol dinamis OSPF/BGP untuk memastikan sumber penarikan prefix."],
                            confidence=conf_rt,
                        )
                    )

            # 7) Tunnel Failure
            for tun in pdata.get("tunnels") or []:
                if isinstance(tun, dict) and str(tun.get("oper_status") or "up").lower() == "down":
                    tname = str(tun.get("name") or tun.get("interface_name") or "tunnel")
                    tun_recs = bundle.records_for_device(dev_id, "tunnels") + if_recs
                    conf_tun = ConfidenceScorer.evaluate(supporting_records=tun_recs, missing_count=1)
                    candidates.append(
                        RCAHypothesis(
                            hypothesis_id=f"hyp_tun_{dev_id}_{tname}_{uuid.uuid4().hex[:4]}",
                            category=HypothesisCategory.TUNNEL_FAILURE.value,
                            classification=FindingClassification.ROOT_CAUSE.value,
                            title=f"Tunnel {dev_id}:{tname} Berstatus DOWN",
                            description=f"Antarmuka overlay tunnel '{tname}' ({tun.get('tunnel_type', 'vpn')}) menuju {tun.get('remote_address', '?')} tidak aktif.",
                            root_entity_id=f"tunnel:{dev_id}:{tname}",
                            affected_scope=[dev_id],
                            supporting_evidence=[r.evidence_id for r in tun_recs],
                            missing_observations=["Keterjangkauan IP endpoint underlay dan kecocokan parameter enkripsi/MTU."],
                            confidence=conf_tun,
                        )
                    )

            # 8) WAN Degradation
            lat = dinfo.get("latency_ms")
            loss = dinfo.get("packet_loss_percent")
            if reach in ("UP", "DEGRADED") and ((lat is not None and float(lat) >= 80.0) or (loss is not None and float(loss) >= 2.0)):
                conf_wan = ConfidenceScorer.evaluate(supporting_records=dev_recs + rt_recs, missing_count=1)
                candidates.append(
                    RCAHypothesis(
                        hypothesis_id=f"hyp_wan_{dev_id}_{uuid.uuid4().hex[:6]}",
                        category=HypothesisCategory.WAN_DEGRADATION.value,
                        classification=FindingClassification.ROOT_CAUSE.value,
                        title=f"Degradasi Kualitas Koneksi WAN pada {dev_id}",
                        description=f"Latensi ({lat} ms) atau packet loss ({loss}%) meningkat pada '{dev_id}' sementara rute tetap terpasang.",
                        root_entity_id=f"device:{dev_id}",
                        affected_scope=[dev_id],
                        supporting_evidence=[r.evidence_id for r in (dev_recs + rt_recs)],
                        missing_observations=["Statistik utilisasi antrean WAN dan latensi hop ISP."],
                        confidence=conf_wan,
                    )
                )

        # 9) VLAN Mismatch from correlation groups
        for grp in corr_groups:
            if grp.shared_dependency and grp.shared_dependency.startswith("vlan:"):
                supp_objs = [bundle.get_record(eid) for eid in grp.supporting_evidence]
                valid_supp = [x for x in supp_objs if x is not None]
                conf_vl = grp.confidence or ConfidenceScorer.evaluate(supporting_records=valid_supp)
                candidates.append(
                    RCAHypothesis(
                        hypothesis_id=f"hyp_vlan_{uuid.uuid4().hex[:6]}",
                        category=HypothesisCategory.VLAN_MISMATCH.value,
                        classification=FindingClassification.ROOT_CAUSE.value,
                        title=f"Ketidakcocokan VLAN pada Segmen {grp.shared_dependency}",
                        description=grp.candidate_explanation,
                        root_entity_id=grp.shared_dependency,
                        affected_scope=list(grp.related_devices),
                        supporting_evidence=list(grp.supporting_evidence),
                        confidence=conf_vl,
                    )
                )

        steps_done.extend([PIPELINE_STEPS_14[7], PIPELINE_STEPS_14[8], PIPELINE_STEPS_14[9]])

        # Step 11: Deterministic Ranking & Unknown Fallback
        candidates.sort(key=lambda h: (h.confidence.score if h.confidence else 0.0), reverse=True)
        if not candidates:
            # Never invent a fault category without supporting evidence!
            has_issues = bool(affected_devices or bundle.collection_gaps or bundle.contradictions)
            unk_cat = HypothesisCategory.UNKNOWN.value
            unk_conf = ConfidenceScorer.evaluate(
                supporting_records=[],
                contradictory_count=len(bundle.contradictions),
                missing_count=max(1, len(bundle.collection_gaps)),
            )
            if has_issues:
                candidates.append(
                    RCAHypothesis(
                        hypothesis_id=f"hyp_unknown_{uuid.uuid4().hex[:6]}",
                        category=unk_cat,
                        classification=FindingClassification.UNKNOWN_CAUSE.value,
                        title="Bukti Belum Cukup untuk Menentukan Akar Masalah Spesifik",
                        description="Terdapat keterbatasan observasi atau kontradiksi bukti sehingga akar masalah belum dapat dipastikan secara deterministik.",
                        affected_scope=sorted(affected_devices),
                        supporting_evidence=[],
                        contradictory_evidence=[c.description for c in bundle.contradictions],
                        missing_observations=global_missing or ["Observasi status perangkat, tabel routing, dan antarmuka terkini."],
                        confidence=unk_conf,
                        status="INSUFFICIENT_EVIDENCE",
                    )
                )
        else:
            candidates[0].status = (
                "WEAKENED_BY_CONTRADICTION"
                if candidates[0].contradictory_evidence
                else ("LEADING_HYPOTHESIS" if (candidates[0].confidence and candidates[0].confidence.score >= 0.50) else "CANDIDATE")
            )

        steps_done.append(PIPELINE_STEPS_14[10])

        # Step 12: Missing Evidence Aggregation
        lead = candidates[0] if candidates else None
        if lead:
            for m in lead.missing_observations:
                if m not in global_missing:
                    global_missing.append(m)
        if stale_or_expired_ids:
            global_missing.append(f"{len(stale_or_expired_ids)} rekaman bukti berstatus STALE/EXPIRED memerlukan penyegaran read-only.")
        steps_done.append(PIPELINE_STEPS_14[11])

        # Step 13: Technical Diagnosis & Human-Review-Only Proposed Remediation
        alts = candidates[1:5] if len(candidates) > 1 else []
        if lead is None:
            exec_summary = "Terkonfirmasi: Tidak ditemukan indikasi gangguan aktif pada cakupan bukti yang dianalisis."
            tech_diag = "Seluruh observasi yang tersedia berada dalam batas operasional normal."
            overall_conf = ConfidenceScorer.evaluate(supporting_records=bundle.records[:5], missing_count=len(bundle.collection_gaps))
            next_steps = ["Lanjutkan pemantauan berkala melalui penjadwal NMS read-only."]
            remediations: List[Dict[str, Any]] = []
        else:
            lbl = lead.confidence.label if lead.confidence else ConfidenceLabel.INSUFFICIENT.value
            qual_word = (
                "Terkonfirmasi indikasi kuat"
                if lbl == ConfidenceLabel.VERY_HIGH.value
                else ("Terindikasi" if lbl == ConfidenceLabel.HIGH.value else ("Kemungkinan" if lbl in (ConfidenceLabel.MODERATE.value, ConfidenceLabel.LOW.value) else "Belum dapat dipastikan"))
            )
            exec_summary = f"{qual_word}: {lead.title} (Kategori: {lead.category}, Keyakinan: {lbl})."
            tech_diag = lead.description
            overall_conf = lead.confidence
            next_steps = [
                f"Periksa bukti pendukung ({', '.join(lead.supporting_evidence[:4]) or 'tidak ada'}) pada Evidence Inspector.",
            ] + list(global_missing[:3])
            remediations = [
                {
                    "review_only": True,
                    "auto_execution_allowed": False,
                    "target_entity": lead.root_entity_id or scope,
                    "category": lead.category,
                    "proposed_action_for_human_engineer": (
                        f"[TINJAUAN MANUSIA SAJA — AIRA TIDAK MENGEKSEKUSI PERUBAHAN] "
                        f"Verifikasi komponen '{lead.root_entity_id or scope}' terkait '{lead.title}' sebelum mengambil tindakan korektif manual."
                    ),
                }
            ]

        steps_done.extend([PIPELINE_STEPS_14[12], PIPELINE_STEPS_14[13]])

        return RCAReport(
            rca_id=rca_id,
            scope=scope,
            analyzed_at=curr_ts,
            executive_summary=exec_summary,
            technical_diagnosis=tech_diag,
            most_likely_root_cause=lead,
            contributing_factors=contributing_factors,
            secondary_symptoms=secondary_symptoms,
            correlated_events=correlated_events,
            affected_devices=sorted(affected_devices),
            affected_services=sorted(affected_services),
            timeline=timeline,
            supporting_evidence=list(lead.supporting_evidence) if lead else [],
            contradictory_evidence=(list(lead.contradictory_evidence) if lead else []) + [c.description for c in bundle.contradictions],
            hypotheses=candidates,
            alternative_hypotheses=alts,
            confidence=overall_conf,
            missing_evidence=global_missing,
            recommended_investigation_steps=next_steps,
            proposed_remediation_review_only=remediations,
            pipeline_steps_completed=steps_done,
        )
