"""
AIRA OS — QoS & Traffic Management Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class QoSAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "qos"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["interfaces"]
    optional_evidence: List[str] = ["qos_queues"]
    known_limitations: List[str] = [
        "Queue tree packet drops evaluated from sampled counters.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        queues = pdata.get("qos_queues") or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "qos_queues")]

        if not queues:
            return findings

        for q in queues:
            if not isinstance(q, dict) or q.get("disabled"):
                continue
            qname = str(q.get("name") or "queue")
            drops = int(q.get("dropped") or q.get("drops") or 0)
            cur_rate = float(q.get("rate") or 0.0)
            max_limit = float(q.get("max_limit") or q.get("limit_at") or 0.0)

            if drops >= 50 or (max_limit > 0 and cur_rate >= 0.95 * max_limit):
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_qos_drop_{device_id}_{qname}_{uuid.uuid4().hex[:6]}",
                        protocol="qos",
                        device_id=device_id,
                        severity="warning",
                        category="RESOURCE_EXHAUSTION",
                        summary=f"Antrean QoS '{qname}' pada '{device_id}' mengalami paket drop atau saturasi ({drops} drops).",
                        technical_detail=f"Trafik antrean mencapai rate {cur_rate:.0f} bps mendekati batas limit {max_limit:.0f} bps.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"qos:{device_id}:{qname}"],
                        remediation_suggestion="Naikkan max-limit atau prioritaskan paket interaktif pada queue tree.",
                    )
                )

        return findings
