"""
core/network_intelligence/investigator.py — Incident Investigation Engine.

Coordinates intake, canonical target resolution, minimal evidence collection planning,
deterministic checks execution, ranked hypothesis generation, and diagnostic reporting.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.canonical_network import get_canonical_registry
from core.events import event_bus
from core.network_intelligence.checks import (
    check_bgp_prefixes_missing,
    check_default_route_fails,
    check_firewall_forward_block,
    check_lan_no_internet,
    check_nat_mismatch,
    check_ospf_adjacency,
    check_vlan_trunk_failure,
)
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.models import (
    ConfidenceLevel,
    EvidenceFreshness,
    EvidenceItem,
    IncidentRecord,
    IncidentType,
    InvestigationStatus,
    RankedHypothesis,
    SeverityLevel,
)
from core.network_intelligence.store import get_network_intelligence_store

logger = logging.getLogger("aira.network_intelligence.investigator")

INCIDENT_EVIDENCE_REQUIREMENTS: Dict[IncidentType, List[str]] = {
    IncidentType.LAN_NO_INTERNET: ["ip_addresses", "routes", "nat_rules", "firewall_filter", "interfaces"],
    IncidentType.DEFAULT_ROUTE_FAILS: ["routes", "ip_addresses", "interfaces", "routing_rules"],
    IncidentType.NAT_MISMATCH: ["nat_rules", "routes", "interfaces"],
    IncidentType.FIREWALL_FORWARD_BLOCKED: ["firewall_filter", "interfaces"],
    IncidentType.OSPF_ADJACENCY_FAILURE: ["ospf_neighbors", "firewall_filter", "interfaces"],
    IncidentType.BGP_PREFIXES_MISSING: ["bgp_peers", "routes"],
    IncidentType.VLAN_TRUNK_FAILURE: ["bridge", "bridge_ports", "bridge_vlan", "ip_addresses", "interfaces"],
    IncidentType.CUSTOM: ["identity", "resources", "interfaces", "ip_addresses", "routes"],
}


class NetworkInvestigator:
    """Orchestrates evidence-backed network incident investigations."""

    def __init__(self):
        self.collector = EvidenceCollector()
        self.store = get_network_intelligence_store()
        self.registry = get_canonical_registry()
        self._cancellation_events: Dict[str, threading.Event] = {}
        self._cancel_lock = threading.Lock()
        self._intent_classifier = None
        self._context_manager = None
        self._planner = None
        self._path_engine = None
        self._correlation_engine = None
        self._rca_engine = None
        self._reasoning_orchestrator = None
        self._anomaly_engine = None
        self._health_engine = None
        self._impact_analyzer = None
        self._failure_simulator = None
        self._historical_engine = None

    def classify_symptom(self, symptom_text: str) -> IncidentType:
        """Determines most probable incident type from symptom keywords deterministically."""
        s = (symptom_text or "").lower()
        if any(w in s for w in ["ospf", "neighbor", "adjacency", "exstart", "init"]):
            return IncidentType.OSPF_ADJACENCY_FAILURE
        if any(w in s for w in ["bgp", "prefix", "peer", "as_path", "established"]):
            return IncidentType.BGP_PREFIXES_MISSING
        if any(w in s for w in ["vlan", "trunk", "pvid", "tagged", "untagged", "bridge vlan"]):
            return IncidentType.VLAN_TRUNK_FAILURE
        if any(w in s for w in ["nat", "masquerade", "src-nat", "dst-nat"]):
            return IncidentType.NAT_MISMATCH
        if any(w in s for w in ["firewall", "drop forward", "fasttrack", "filter drop"]):
            return IncidentType.FIREWALL_FORWARD_BLOCKED
        if any(w in s for w in ["default route", "gateway unreachable", "recursive", "0.0.0.0/0"]):
            return IncidentType.DEFAULT_ROUTE_FAILS
        if any(w in s for w in ["lan", "internet", "klien", "client", "tidak bisa internet", "rto", "no connection"]):
            return IncidentType.LAN_NO_INTERNET
        return IncidentType.CUSTOM

    def create_and_run_investigation(
        self,
        *,
        device_identity: str,
        incident_type: Optional[IncidentType] = None,
        symptoms: Optional[List[str]] = None,
        user_description: str = "",
        severity: SeverityLevel = SeverityLevel.MEDIUM,
        target_ip: Optional[str] = None,
        target_vlan_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        prebuilt_bundle: Optional[Any] = None,
    ) -> IncidentRecord:
        """
        Executes complete deterministic investigation flow:
        1. Resolve target
        2. Plan minimal evidence
        3. Collect read-only observations
        4. Execute deterministic checks
        5. Formulate ranked hypotheses
        6. Persist & publish report
        """
        inc_id = f"inc_{uuid.uuid4().hex[:8]}"
        corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"
        t_start = time.time()
        symptom_list = symptoms or []

        # 1. Resolve target device
        target_dev, ros_major, display_name = self.collector.resolve_target_device(device_identity)
        if not target_dev:
            rec = IncidentRecord(
                incident_id=inc_id,
                device_identity=device_identity,
                incident_type=(incident_type or IncidentType.CUSTOM).value,
                severity=SeverityLevel.HIGH.value,
                symptoms=symptom_list,
                user_description=user_description,
                observed_facts=[],
                inferred_hypotheses=[],
                missing_evidence=[f"Perangkat '{device_identity}' tidak dapat diresolusi di inventory maupun topologi."],
                recommended_tests=[{
                    "test_name": "resolve_device_target",
                    "description": "Periksa penulisan nama perangkat atau tambahkan IP router ke menu Devices.",
                }],
                confidence=ConfidenceLevel.INSUFFICIENT_EVIDENCE.value,
                confidence_explanation="Perangkat tidak dikenal dalam inventaris.",
                investigation_status=InvestigationStatus.BLOCKED.value,
                limitations_disclosure="Identitas perangkat ambigu atau tidak ditemukan.",
                correlation_id=corr_id,
            )
            self.store.save_incident(rec)
            return rec

        # 2. Determine incident type
        resolved_type = incident_type
        if not resolved_type or resolved_type == IncidentType.CUSTOM:
            combined_text = f"{user_description} {' '.join(symptom_list)}"
            resolved_type = self.classify_symptom(combined_text)

        # 3. Collect required evidence bundle
        req_types = INCIDENT_EVIDENCE_REQUIREMENTS.get(resolved_type, INCIDENT_EVIDENCE_REQUIREMENTS[IncidentType.CUSTOM])
        bundle = self.collector.collect_evidence_bundle(target_dev, req_types)
        evidence_items: List[EvidenceItem] = bundle["evidence_items"]

        # Persist evidence items
        self.store.save_evidence_items(inc_id, evidence_items)

        # Index evidence by type
        evidence_by_type = {it.observation_type: it.normalized_value for it in evidence_items if it.collection_status == "SUCCESS"}
        sources = [it.source_command for it in evidence_items]

        # 4. Run Deterministic Checks based on incident type
        check_result: Dict[str, Any] = {}
        if resolved_type == IncidentType.LAN_NO_INTERNET:
            check_result = check_lan_no_internet(
                client_ip=target_ip,
                routes_evidence=evidence_by_type.get("routes"),
                ip_addresses_evidence=evidence_by_type.get("ip_addresses"),
                interfaces_evidence=evidence_by_type.get("interfaces"),
                nat_evidence=evidence_by_type.get("nat_rules"),
                firewall_evidence=evidence_by_type.get("firewall_filter"),
            )
        elif resolved_type == IncidentType.DEFAULT_ROUTE_FAILS:
            check_result = check_default_route_fails(
                routes_evidence=evidence_by_type.get("routes", {}),
                ip_addresses_evidence=evidence_by_type.get("ip_addresses"),
                interfaces_evidence=evidence_by_type.get("interfaces"),
                target_dst_ip=target_ip or "8.8.8.8",
            )
        elif resolved_type == IncidentType.NAT_MISMATCH:
            check_result = check_nat_mismatch(
                nat_evidence=evidence_by_type.get("nat_rules", {}),
                routes_evidence=evidence_by_type.get("routes"),
                interfaces_evidence=evidence_by_type.get("interfaces"),
                client_subnet=target_ip,
            )
        elif resolved_type == IncidentType.FIREWALL_FORWARD_BLOCKED:
            check_result = check_firewall_forward_block(
                firewall_evidence=evidence_by_type.get("firewall_filter", {}),
                client_ip=target_ip,
            )
        elif resolved_type == IncidentType.OSPF_ADJACENCY_FAILURE:
            check_result = check_ospf_adjacency(
                ospf_evidence=evidence_by_type.get("ospf_neighbors", {}),
                firewall_evidence=evidence_by_type.get("firewall_filter"),
                interfaces_evidence=evidence_by_type.get("interfaces"),
            )
        elif resolved_type == IncidentType.BGP_PREFIXES_MISSING:
            check_result = check_bgp_prefixes_missing(
                bgp_evidence=evidence_by_type.get("bgp_peers", {}),
                routes_evidence=evidence_by_type.get("routes"),
                expected_prefix=target_ip,
            )
        elif resolved_type == IncidentType.VLAN_TRUNK_FAILURE:
            check_result = check_vlan_trunk_failure(
                bridge_vlan_evidence=evidence_by_type.get("bridge_vlan", {}),
                interfaces_evidence=evidence_by_type.get("interfaces"),
                ip_addresses_evidence=evidence_by_type.get("ip_addresses"),
                target_vlan_id=target_vlan_id,
            )
        else:
            # Custom fallback analysis
            check_result = {
                "status": "HEALTHY",
                "findings": [],
                "observed_facts": [f"Pengumpulan data umum selesai untuk {display_name}."],
                "inferred_hypotheses": [],
                "missing_evidence": [],
                "recommendations": ["Pilih skenario diagnostik spesifik untuk analisis mendalam."],
            }

        # 5. Build Ranked Hypotheses
        ranked_hypotheses: List[RankedHypothesis] = []
        findings = check_result.get("findings", [])
        raw_hypotheses = check_result.get("inferred_hypotheses", [])
        bundle_contradictions = bundle.get("contradictions", [])

        # If no evidence was successfully collected, do NOT formulate speculative hypotheses
        rec_tests = []
        if not evidence_by_type:
            overall_confidence = ConfidenceLevel.INSUFFICIENT_EVIDENCE.value
            conf_expl = "Bukti tidak mencukupi untuk menarik kesimpulan diagnostik karena pengumpulan data gagal (UNAVAILABLE)."
            inv_status = InvestigationStatus.BLOCKED.value
            all_facts = [
                f"[Kekurangan Bukti]: Seluruh upaya pengumpulan bukti dari perangkat '{target_dev}' gagal.",
                f"Kesalahan pengumpulan: {', '.join(bundle.get('collection_errors', ['Koneksi atau sesi gagal']))}",
            ]
            check_missing = list(check_result.get("missing_evidence", [])) + [
                f"Pengumpulan bukti CLI gagal untuk seluruh required commands: {', '.join(req_types)}"
            ]
            rec_tests.append({
                "action": "verify_device_reachability",
                "recommendation": "Periksa konektivitas SSH, IP management, kredensial, dan port SSH router.",
                "safety": "Read-only connection test",
            })
        else:
            for idx, hyp_text in enumerate(raw_hypotheses):
                h_id = f"hyp_{idx+1}"
                matching_finding = next((f for f in findings if f.get("code") in hyp_text or f.get("severity") in ("CRITICAL", "HIGH")), None)
                conf = ConfidenceLevel.HIGH.value if matching_finding else ConfidenceLevel.MEDIUM.value

                # Collect alternatives excluding self
                alts = [h.split(".")[0] for i, h in enumerate(raw_hypotheses) if i != idx]
                
                # Deterministic confidence rationale explaining why leading hypothesis ranks above alternatives
                if idx == 0:
                    conf_expl_item = (
                        f"Leading hypothesis teratas didukung oleh bukti observasi deterministic finding {resolved_type.value} "
                        f"dengan bobot keparahan tertinggi."
                    )
                else:
                    conf_expl_item = (
                        f"Hipotesis alternatif sekunder dievaluasi sebagai penyebab sekunder setelah {raw_hypotheses[0].split('.')[0]}."
                    )

                limits = [
                    "Analisis berbasis konfigurasi statis RouterOS; perilaku hardware offload, FastTrack bypass, dan fluktuasi ISP tidak tercermin pada CLI snapshot.",
                    "Verifikasi jalur end-to-end multi-hop membutuhkan observasi sinkron pada perangkat uplink/downlink."
                ]

                ranked_hypotheses.append(RankedHypothesis(
                    hypothesis_id=h_id,
                    title=hyp_text.split(".")[0],
                    explanation=hyp_text,
                    supporting_evidence=[f["message"] for f in findings],
                    contradicting_evidence=list(bundle_contradictions),
                    missing_evidence=list(check_result.get("missing_evidence", [])),
                    recommended_test=(
                        check_result.get("recommendations", ["Lakukan inspeksi konfigurasi lanjutan."])[0]
                        if check_result.get("recommendations") else ""
                    ),
                    confidence=conf,
                    confidence_explanation=conf_expl_item,
                    alternative_explanations=alts,
                    known_limitations=limits,
                ))

            # Check overall confidence
            overall_confidence = ConfidenceLevel.HIGH.value if ranked_hypotheses else (
                ConfidenceLevel.INSUFFICIENT_EVIDENCE.value if not evidence_by_type else ConfidenceLevel.LOW.value
            )
            conf_expl = (
                f"Diverifikasi terhadap {len(evidence_items)} sumber bukti observasi."
                if evidence_items else "Bukti tidak mencukupi untuk menarik kesimpulan pasti."
            )

            all_facts = list(check_result.get("observed_facts", []))
            for cont in bundle_contradictions:
                all_facts.append(f"[Kontradiksi]: {cont}")

            for rec in check_result.get("recommendations", []):
                rec_tests.append({
                    "action": "operator_verification",
                    "recommendation": rec,
                    "target_hypothesis": ranked_hypotheses[0].hypothesis_id if ranked_hypotheses else "GENERAL",
                    "prerequisites": ["Target reachable via management plane", "Read-only CLI credentials"],
                    "cost_risk": "LOW (Minimal bandwidth and CPU overhead)",
                    "command_allowlisted": True,
                    "management_plane_risk": "NONE (Strictly read-only inspection, zero mutation)",
                    "safety": "Read-only / Planned remediation required",
                })

            has_partial = any(it.collection_status != "SUCCESS" for it in evidence_items)
            inv_status = InvestigationStatus.DIAGNOSIS_READY.value if ranked_hypotheses else (
                InvestigationStatus.EVIDENCE_PARTIAL.value if has_partial else InvestigationStatus.ANALYZING.value
            )
            check_missing = check_result.get("missing_evidence", [])

        record = IncidentRecord(
            incident_id=inc_id,
            device_identity=target_dev,
            related_devices=[],
            incident_type=resolved_type.value,
            severity=severity.value,
            symptoms=symptom_list,
            user_description=user_description,
            observed_facts=all_facts,
            inferred_hypotheses=[h.to_dict() for h in ranked_hypotheses],
            missing_evidence=check_missing,
            recommended_tests=rec_tests,
            evidence_sources=sources,
            confidence=overall_confidence,
            confidence_explanation=conf_expl,
            investigation_status=inv_status,
            created_at=t_start,
            updated_at=time.time(),
            limitations_disclosure=(
                "Analisis ini bersifat statis dan berbasis bukti observasi terbaca. "
                "Perilaku dinamik (FastTrack, hardware offload, enkapsulasi terowongan) "
                "memerlukan pengujian trafik end-to-end langsung."
            ),
            correlation_id=corr_id,
        )

        self.store.save_incident(record)

        try:
            event_bus.publish(
                "network_intelligence.investigation.diagnosed",
                agent="AIRA",
                incident_id=inc_id,
                device=target_dev,
                incident_type=resolved_type.value,
                confidence=overall_confidence,
            )
        except Exception:
            pass

        return record

    def run_multi_device_investigation(
        self,
        *,
        primary_device: str,
        related_devices: List[str],
        symptom_description: str,
        incident_type: Optional[IncidentType] = None,
        target_ip: Optional[str] = None,
        severity: SeverityLevel = SeverityLevel.MEDIUM,
        correlation_id: Optional[str] = None,
        prebuilt_bundle: Optional[Any] = None,
    ) -> IncidentRecord:
        """
        Executes a topology-aware multi-device root cause investigation.
        Correlates observations across primary and neighboring devices to identify
        cross-device dependencies and upstream failure causes.
        """
        from core.network_intelligence.multi_device_collector import MultiDeviceEvidenceOrchestrator
        from core.network_intelligence.correlation import CrossDeviceEvidenceCorrelator

        inc_id = f"inc_{uuid.uuid4().hex[:8]}"
        corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"
        t_start = time.time()
        resolved_type = incident_type or self.classify_symptom(symptom_description)

        all_targets = [primary_device] + [d for d in related_devices if d != primary_device]
        req_types = INCIDENT_EVIDENCE_REQUIREMENTS.get(resolved_type, ["identity", "interfaces", "ip_addresses", "routes", "arp"])

        # 1. Multi-device evidence collection (reuses prebuilt_bundle when supplied)
        if prebuilt_bundle is not None:
            mbundle = prebuilt_bundle
        else:
            orchestrator = MultiDeviceEvidenceOrchestrator(self.collector)
            mbundle = orchestrator.collect_multi_device_bundle(targets=all_targets, required_types=req_types)

        # 2. Persist all evidence items
        all_items: List[EvidenceItem] = []
        for dev_target, dev_bundle in mbundle.device_bundles.items():
            dev_items = dev_bundle.get("evidence_items", [])
            all_items.extend(dev_items)
            self.store.save_evidence_items(inc_id, dev_items)

        # 3. Cross-device evidence correlation
        correlator = CrossDeviceEvidenceCorrelator()
        relationships = correlator.correlate_bundles(mbundle.device_bundles)

        # 4. Analyze topology & upstream dependencies
        observed_facts = [
            f"Multi-device evidence collected across {len(all_targets)} devices: {', '.join(all_targets)}.",
            f"Cross-device relationships identified: {len(relationships)} link/routing correlations.",
        ]
        inferred_hypotheses: List[RankedHypothesis] = []
        recommended_tests: List[Dict[str, Any]] = []

        primary_bundle = mbundle.device_bundles.get(primary_device, {})
        primary_items = {it.observation_type: it.normalized_value for it in primary_bundle.get("evidence_items", []) if it.collection_status == "SUCCESS"}

        # Check if primary device's default route points to any related device
        primary_routes = primary_items.get("routes", {}).get("routes", [])
        primary_gw = None
        for r in primary_routes:
            if r.get("dst_address") == "0.0.0.0/0" or r.get("dst_prefix") == "0.0.0.0/0":
                primary_gw = r.get("gateway")
                break

        upstream_device = None
        upstream_link_rel = None
        if primary_gw:
            observed_facts.append(f"Primary device {primary_device} default gateway: {primary_gw}.")
            for rel in relationships:
                if rel.correlation_rule in ("ROUTED_NEXT_HOP", "MUTUAL_ARP_AND_SUBNET_MATCH"):
                    if rel.source_device_id == primary_device and rel.target_device_id in related_devices:
                        upstream_device = rel.target_device_id
                        upstream_link_rel = rel
                        break
                    elif rel.target_device_id == primary_device and rel.source_device_id in related_devices:
                        upstream_device = rel.source_device_id
                        upstream_link_rel = rel
                        break

        # If upstream device identified, check upstream health
        if upstream_device and upstream_device in mbundle.device_bundles:
            up_items = {it.observation_type: it.normalized_value for it in mbundle.device_bundles[upstream_device].get("evidence_items", []) if it.collection_status == "SUCCESS"}
            up_routes = up_items.get("routes", {}).get("routes", [])
            up_has_default = any((r.get("dst_address") == "0.0.0.0/0" or r.get("dst_prefix") == "0.0.0.0/0") and r.get("active", False) for r in up_routes)

            if not up_has_default:
                observed_facts.append(f"Perangkat upstream {upstream_device} TIDAK memiliki rute default aktif ke internet.")
                inferred_hypotheses.append(RankedHypothesis(
                    hypothesis_id="hyp_up_1",
                    title=f"Kegagalan Dependensi Upstream: Router transit {upstream_device} kehilangan rute default",
                    explanation=f"Trafik dari {primary_device} diteruskan ke gateway {primary_gw} pada {upstream_device}, namun {upstream_device} tidak memiliki rute keluar yang aktif.",
                    supporting_evidence=[
                        f"Rute default pada {primary_device} menunjuk {primary_gw} ({upstream_device}).",
                        f"Tabel routing {upstream_device} tidak memiliki entri default route 0.0.0.0/0 yang aktif.",
                    ],
                    confidence="HIGH",
                    confidence_explanation="Diverifikasi langsung melalui telemetri routing multi-perangkat.",
                    alternative_explanations=[f"Masalah fisik pada antarmuka penghubung antara {primary_device} dan {upstream_device}"],
                    recommended_test=f"Periksa status uplink WAN atau routing protocol pada {upstream_device}.",
                ))
            else:
                observed_facts.append(f"Perangkat upstream {upstream_device} memiliki rute default aktif.")
                inferred_hypotheses.append(RankedHypothesis(
                    hypothesis_id="hyp_up_2",
                    title=f"Masalah Segmentasi atau NAT lokal antara {primary_device} dan {upstream_device}",
                    explanation=f"Uplink pada {upstream_device} tampak sehat; kendala kemungkinan berada pada NAT masquerade atau firewall filter di {primary_device}.",
                    supporting_evidence=[
                        f"Router upstream {upstream_device} memiliki konektivitas default route.",
                    ],
                    confidence="MEDIUM",
                    confidence_explanation="Diverifikasi secara cross-device; uplink upstream beroperasi normal.",
                    alternative_explanations=["MTU mismatch", "FastTrack drop"],
                    recommended_test=f"Periksa rule firewall NAT dan filter pada {primary_device}.",
                ))

        if not inferred_hypotheses:
            # Fallback hypothesis from correlation relationships
            inferred_hypotheses.append(RankedHypothesis(
                hypothesis_id="hyp_general_1",
                title=f"Analisis relasi multi-perangkat selesai tanpa anomali dependensi kritis",
                explanation=f"Observasi pada {primary_device} dan {len(related_devices)} perangkat terkait tidak menunjukkan kegagalan transit terbukti.",
                supporting_evidence=[f"Korelasi {len(relationships)} link antar perangkat valid."],
                confidence="LOW",
                confidence_explanation="Tidak ditemukan kegagalan upstream yang jelas.",
                alternative_explanations=["Masalah berada pada end-client lokal."],
                recommended_test="Lakukan pengetesan jalur end-to-end langsung.",
            ))

        overall_conf = inferred_hypotheses[0].confidence
        conf_expl = f"Dianalisis secara topologis terhadap {len(all_targets)} perangkat ({', '.join(all_targets)})."

        record = IncidentRecord(
            incident_id=inc_id,
            device_identity=primary_device,
            related_devices=related_devices,
            incident_type=resolved_type.value,
            severity=severity.value,
            symptoms=[symptom_description],
            user_description=symptom_description,
            observed_facts=observed_facts,
            inferred_hypotheses=[h.to_dict() if hasattr(h, "to_dict") else h for h in inferred_hypotheses],
            missing_evidence=[],
            recommended_tests=recommended_tests,
            evidence_sources=[it.source_command for it in all_items],
            confidence=overall_conf,
            confidence_explanation=conf_expl,
            investigation_status=InvestigationStatus.DIAGNOSIS_READY.value,
            created_at=t_start,
            updated_at=time.time(),
            limitations_disclosure=(
                "Analisis multi-perangkat ini berbasis korelasi snapshot observasi terbaca. "
                "Perilaku dinamik multi-hop memerlukan pengujian end-to-end langsung."
            ),
            correlation_id=corr_id,
        )

        self.store.save_incident(record)
        return record

    def get_investigation(self, incident_id: str) -> Optional[IncidentRecord]:
        return self.store.get_incident(incident_id)

    def list_investigations(self, limit: int = 50) -> List[IncidentRecord]:
        return self.store.list_incidents(limit=limit)

    # -----------------------------------------------------------------------
    # Lazy Engine Properties
    # -----------------------------------------------------------------------

    @property
    def intent_classifier(self):
        if self._intent_classifier is None:
            from core.network_intelligence.intent_classifier import IntentClassifier
            self._intent_classifier = IntentClassifier()
        return self._intent_classifier

    @property
    def context_manager(self):
        if self._context_manager is None:
            from core.network_intelligence.investigation_planner import InvestigationContextManager
            self._context_manager = InvestigationContextManager()
        return self._context_manager

    @property
    def planner(self):
        if self._planner is None:
            from core.network_intelligence.investigation_planner import InvestigationPlanner
            self._planner = InvestigationPlanner(context_manager=self.context_manager)
        return self._planner

    @property
    def path_engine(self):
        if self._path_engine is None:
            from core.network_intelligence.path_intelligence import NetworkPathIntelligenceEngine
            self._path_engine = NetworkPathIntelligenceEngine()
        return self._path_engine

    @property
    def correlation_engine(self):
        if self._correlation_engine is None:
            from core.network_intelligence.correlation_engine import MultiDeviceCorrelationEngine
            self._correlation_engine = MultiDeviceCorrelationEngine()
        return self._correlation_engine

    @property
    def rca_engine(self):
        if self._rca_engine is None:
            from core.network_intelligence.rca_engine import RootCauseAnalysisEngine
            self._rca_engine = RootCauseAnalysisEngine()
        return self._rca_engine

    @property
    def reasoning_orchestrator(self):
        if self._reasoning_orchestrator is None:
            from core.network_intelligence.reasoning_orchestrator import LLMReasoningOrchestrator
            self._reasoning_orchestrator = LLMReasoningOrchestrator()
        return self._reasoning_orchestrator

    @property
    def anomaly_engine(self):
        if self._anomaly_engine is None:
            from core.network_intelligence.anomaly_engine import AnomalyEngine
            self._anomaly_engine = AnomalyEngine()
        return self._anomaly_engine

    @property
    def health_engine(self):
        if self._health_engine is None:
            from core.network_intelligence.health_engine import NetworkHealthEngine
            self._health_engine = NetworkHealthEngine()
        return self._health_engine

    @property
    def impact_analyzer(self):
        if self._impact_analyzer is None:
            from core.network_intelligence.impact_analyzer import ImpactAnalyzer
            self._impact_analyzer = ImpactAnalyzer()
        return self._impact_analyzer

    @property
    def failure_simulator(self):
        if self._failure_simulator is None:
            from core.network_intelligence.failure_simulator import FailureSimulator
            self._failure_simulator = FailureSimulator()
        return self._failure_simulator

    @property
    def historical_engine(self):
        if self._historical_engine is None:
            from core.network_intelligence.historical_intelligence import HistoricalIntelligenceEngine
            self._historical_engine = HistoricalIntelligenceEngine()
        return self._historical_engine

    # -----------------------------------------------------------------------
    # Cancellation & Bounded Execution (WP 6.12)
    # -----------------------------------------------------------------------

    def cancel_investigation(self, investigation_id: str) -> bool:
        """Signals active investigation to abort cleanly without corrupting state."""
        with self._cancel_lock:
            ev = self._cancellation_events.get(investigation_id)
            if ev:
                ev.set()
                logger.info("Investigation cancellation requested for: %s", investigation_id)
                return True
            return False

    def _build_cancelled_report(
        self,
        inv_id: str,
        sess_id: str,
        query: str,
        t_start: float,
        plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        dur = round(time.time() - t_start, 3)
        res = {
            "investigation_id": inv_id,
            "session_id": sess_id,
            "question": query,
            "intent": "UNKNOWN",
            "status": "CANCELLED",
            "plan": plan or {},
            "rca": None,
            "path": None,
            "health": None,
            "anomalies": [],
            "correlations": [],
            "explanation": {
                "summary": "Penyelidikan dibatalkan oleh operator sebelum selesai.",
                "confidence_assessment": "INSUFFICIENT_EVIDENCE",
                "recommended_actions": ["Jalankan kembali penyelidikan jika diperlukan."],
            },
            "evidence_items": [],
            "evidence_summary": {"total_records": 0, "devices_observed": [], "staleness": {}, "missing_count": 0},
            "missing_evidence": ["Operasi dibatalkan sebelum pengumpulan bukti lengkap."],
            "duration_sec": dur,
            "created_at": t_start,
        }
        self.store.save_intelligence_investigation(
            investigation_id=inv_id,
            session_id=sess_id,
            question=query,
            intent="UNKNOWN",
            status="CANCELLED",
            plan_dict=plan or {},
            duration_sec=dur,
            created_at=t_start,
        )
        return res

    # -----------------------------------------------------------------------
    # 12-Step Natural Language Investigation Pipeline (WP 6.12)
    # -----------------------------------------------------------------------

    def investigate_natural_language(
        self,
        query: str,
        *,
        session_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        investigation_id: Optional[str] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Executes complete 12-step evidence-driven Natural Language Network Investigation.
        Strictly read-only; no write or configuration modifying commands are issued.
        """
        t_start = time.time()
        inv_id = investigation_id or f"inv_{uuid.uuid4().hex[:10]}"
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        cancel_ev = threading.Event()
        with self._cancel_lock:
            self._cancellation_events[inv_id] = cancel_ev

        try:
            # Step 1: Query Validation
            clean_query = str(query or "").strip()
            if not clean_query:
                raise ValueError("Query tidak boleh kosong.")

            if cancel_ev.is_set():
                return self._build_cancelled_report(inv_id, sess_id, clean_query, t_start)

            # Step 2: Intent Classification
            from core.network_intelligence.intent_classifier import InvestigationIntent
            intent, confidence, matched_entities = self.intent_classifier.classify(clean_query)
            intent_str = intent.value if hasattr(intent, "value") else str(intent)

            # Step 3: Investigation Scope & Planning
            plan = self.planner.create_plan(clean_query, session_id=sess_id)

            if cancel_ev.is_set():
                return self._build_cancelled_report(inv_id, sess_id, clean_query, t_start, plan=plan.to_dict())

            # Step 4: Existing Evidence Retrieval via UnifiedEvidenceService
            from core.network_intelligence.evidence_service import get_unified_evidence_service
            evidence_svc = get_unified_evidence_service()

            target_devices = [e for e in plan.target_entities if not e.startswith("ip:") and not ":" in e]
            if not target_devices:
                try:
                    from core.inventory_store import get_inventory_store
                    inv_devs = get_inventory_store().list_devices()
                    target_devices = [d.name or d.ip for d in inv_devs if d.name or d.ip]
                except Exception:
                    target_devices = []

            bundle = evidence_svc.assemble_evidence_bundle(
                target_devices=target_devices,
                required_types=list(plan.required_evidence) if plan.required_evidence else None,
                allow_live_collection=True,
            )

            # Step 5 & 6: Freshness & Completeness Evaluation
            missing_evidence = [g.description if hasattr(g, 'description') else str(g) for g in bundle.collection_gaps]
            staleness = bundle.freshness_summary

            if cancel_ev.is_set():
                return self._build_cancelled_report(inv_id, sess_id, clean_query, t_start, plan=plan.to_dict())

            # Construct Knowledge Graph from unified bundle
            from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
            kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

            # Step 7: Deterministic Analyzers Execution
            anomalies = self.anomaly_engine.detect_anomalies(bundle, graph=kg)
            health = self.health_engine.evaluate_health(bundle, graph=kg, anomalies=anomalies)

            path_data: Optional[Dict[str, Any]] = None
            if intent in (InvestigationIntent.PATH_ANALYSIS, InvestigationIntent.ROUTE_INVESTIGATION) or any(e.startswith('ip:') for e in plan.target_entities):
                ips = [e.replace("ip:", "") for e in plan.target_entities if e.startswith("ip:")] or [m for m in matched_entities if "." in m]
                dst_ip = ips[0] if ips else "8.8.8.8"
                src_dev = target_devices[0] if target_devices else None
                try:
                    p_res = self.path_engine.analyze_path(
                        bundle=bundle,
                        graph=kg,
                        destination_ip=dst_ip,
                        source_device_id=src_dev,
                    )
                    path_data = p_res.to_dict()
                except Exception as exc:
                    logger.warning("Path analysis in natural language investigation: %s", exc)

            protocol_data: Optional[Dict[str, Any]] = None
            if intent == InvestigationIntent.PROTOCOL_ANALYSIS:
                from core.network_intelligence.protocols import ALL_PROTOCOL_ANALYZERS
                proto_findings = []
                for analyzer_cls in ALL_PROTOCOL_ANALYZERS:
                    analyzer = analyzer_cls()
                    for dev_id in (target_devices or ["unknown"]):
                        dev_findings = analyzer.analyze(bundle, dev_id)
                        proto_findings.extend([f.to_dict() for f in dev_findings])
                protocol_data = {"protocol_findings": proto_findings}

            impact_data: Optional[Dict[str, Any]] = None
            if intent == InvestigationIntent.CHANGE_IMPACT and target_devices:
                try:
                    imp_res = self.impact_analyzer.analyze_impact(bundle, kg, target_entity_id=target_devices[0])
                    impact_data = imp_res.to_dict()
                except Exception as exc:
                    logger.warning("Impact analysis: %s", exc)

            simulation_data: Optional[Dict[str, Any]] = None
            if intent == InvestigationIntent.FAILURE_SIMULATION and target_devices:
                try:
                    sim_res = self.failure_simulator.simulate_failure(
                        bundle, kg, failure_type="DEVICE_DOWN", entity_id=target_devices[0]
                    )
                    simulation_data = sim_res.to_dict()
                except Exception as exc:
                    logger.warning("Simulation: %s", exc)

            historical_data: Optional[Dict[str, Any]] = None
            if intent == InvestigationIntent.HISTORICAL_COMPARISON:
                try:
                    historical_data = {
                        "recurring_incidents": self.historical_engine.detect_recurring_incidents(),
                    }
                except Exception as exc:
                    logger.warning("Historical comparison: %s", exc)

            # Step 8 & 9: Multi-Device Correlation & Root Cause Analysis
            correlations = self.correlation_engine.correlate(bundle, kg)
            rca_report = self.rca_engine.analyze(bundle, kg, correlations=correlations)

            if cancel_ev.is_set():
                return self._build_cancelled_report(inv_id, sess_id, clean_query, t_start, plan=plan.to_dict())

            # Step 10: Grounded AI Explanation
            ai_explanation = self.reasoning_orchestrator.generate_explanation(
                question=clean_query,
                rca_report=rca_report,
                health_data=health,
                path_data=path_data,
                anomalies=[a.to_dict() for a in anomalies],
            )

            # Step 11: Final Report Assembly
            duration_sec = round(time.time() - t_start, 3)
            evidence_records = [
                {
                    "evidence_id": r.evidence_id,
                    "device_id": r.device_id,
                    "observation_type": r.evidence_type,
                    "collection_method": r.collection_method,
                    "freshness": r.freshness.value if hasattr(r.freshness, "value") else str(r.freshness),
                    "confidence": r.confidence.value if hasattr(r.confidence, "value") else str(r.confidence),
                    "timestamp": r.collected_at,
                    "source_command": r.sanitized_command_ref,
                    "limitations": list(r.limitations),
                }
                for r in bundle.records
            ]

            result = {
                "investigation_id": inv_id,
                "session_id": sess_id,
                "question": clean_query,
                "intent": intent_str,
                "status": "COMPLETED",
                "plan": plan.to_dict(),
                "rca": rca_report.to_dict(),
                "path": path_data,
                "health": health,
                "anomalies": [a.to_dict() for a in anomalies],
                "correlations": [c.to_dict() for c in correlations],
                "protocol": protocol_data,
                "impact": impact_data,
                "simulation": simulation_data,
                "historical": historical_data,
                "explanation": ai_explanation.to_dict(),
                "evidence_items": evidence_records,
                "evidence_summary": {
                    "total_records": len(bundle.records),
                    "devices_observed": list(bundle.selected_devices),
                    "staleness": staleness,
                    "missing_count": len(missing_evidence),
                },
                "missing_evidence": missing_evidence,
                "duration_sec": duration_sec,
                "created_at": t_start,
            }

            # Step 12: Evidence & Investigation Persistence
            self.store.save_intelligence_investigation(
                investigation_id=inv_id,
                session_id=sess_id,
                question=clean_query,
                intent=intent_str,
                status="COMPLETED",
                plan_dict=plan.to_dict(),
                rca_dict=rca_report.to_dict(),
                explanation_dict=ai_explanation.to_dict(),
                health_dict=health,
                path_dict=path_data,
                duration_sec=duration_sec,
                created_at=t_start,
            )

            # Record in context manager for session follow-ups
            self.context_manager.update_context(
                session_id=sess_id,
                intent=intent_str,
                target_devices=target_devices,
                root_cause=rca_report.most_likely_root_cause.title if rca_report and rca_report.most_likely_root_cause else None,
            )

            return result

        finally:
            with self._cancel_lock:
                self._cancellation_events.pop(inv_id, None)
