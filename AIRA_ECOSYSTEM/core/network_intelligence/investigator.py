"""
core/network_intelligence/investigator.py — Incident Investigation Engine.

Coordinates intake, canonical target resolution, minimal evidence collection planning,
deterministic checks execution, ranked hypothesis generation, and diagnostic reporting.
"""

from __future__ import annotations

import logging
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

    def get_investigation(self, incident_id: str) -> Optional[IncidentRecord]:
        return self.store.get_incident(incident_id)

    def list_investigations(self, limit: int = 50) -> List[IncidentRecord]:
        return self.store.list_incidents(limit=limit)
