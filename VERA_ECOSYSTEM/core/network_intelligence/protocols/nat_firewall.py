"""
AIRA OS — NAT & Firewall Security Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class NATFirewallAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "nat_firewall"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["interfaces"]
    optional_evidence: List[str] = ["nat_rules", "firewall_filter"]
    known_limitations: [
        "Connection tracking table state sampled via read-only command boundaries; per-packet evaluation is inferred.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        nat_rules = pdata.get("nat_rules") or []
        fw_rules = pdata.get("firewall_filter") or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "nat_rules")]

        if not nat_rules and not fw_rules:
            return findings

        # Check for masquerade rule with missing out-interface (dangerous broadcast/NAT leak)
        for idx, nr in enumerate(nat_rules):
            if not isinstance(nr, dict) or nr.get("disabled"):
                continue
            action = str(nr.get("action") or "").lower()
            out_if = nr.get("out-interface") or nr.get("out_interface")
            chain = str(nr.get("chain") or "srcnat").lower()

            if action == "masquerade" and chain == "srcnat" and not out_if:
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_nat_noint_{device_id}_{idx}_{uuid.uuid4().hex[:6]}",
                        protocol="nat_firewall",
                        device_id=device_id,
                        severity="warning",
                        category="CONFIGURATION_CHANGE",
                        summary=f"Aturan NAT masquerade pada '{device_id}' tidak memiliki `out-interface` spesifik.",
                        technical_detail="Aturan masquerade tanpa pembatasan out-interface akan mentranslasikan seluruh trafik transit internal dan berpotensi merusak routing LAN.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"nat:{device_id}:rule_{idx}"],
                        remediation_suggestion="Tetapkan `out-interface` atau `out-interface-list=WAN` pada aturan masquerade.",
                    )
                )

        return findings
