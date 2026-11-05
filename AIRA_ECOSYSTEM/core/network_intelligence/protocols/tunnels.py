"""
AIRA OS — Tunnels & VPN Protocol Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class TunnelAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "tunnels"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["interfaces"]
    optional_evidence: List[str] = ["tunnels", "routes"]
    known_limitations: List[str] = [
        "Cryptographic pre-shared keys and private keys are strictly redacted; tunnel state evaluated via reachability and operational status.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        tuns = pdata.get("tunnels") or []
        ifaces = bundle.interface_evidence.get(device_id) or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "tunnels")]

        if not tuns:
            return findings

        iface_oper_map = {str(i.get("interface_name")): str(i.get("oper_status") or "unknown").lower() for i in ifaces}

        for tun in tuns:
            if not isinstance(tun, dict) or tun.get("disabled"):
                continue
            tname = str(tun.get("name") or "tunnel")
            ttype = str(tun.get("type") or "gre")
            oper = iface_oper_map.get(tname, "unknown")

            if oper in ("down", "disabled"):
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_tun_down_{device_id}_{tname}_{uuid.uuid4().hex[:6]}",
                        protocol="tunnels",
                        device_id=device_id,
                        severity="critical",
                        category="TUNNEL_FAILURE",
                        summary=f"Tunnel {ttype.upper()} '{tname}' pada '{device_id}' berstatus '{oper}'.",
                        technical_detail=f"Antarmuka tunnel overlay down. Endpoint remote: {tun.get('remote_address') or 'unknown'}.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"tunnel:{device_id}:{tname}"],
                        remediation_suggestion="Periksa keterjangkauan IP endpoint remote di WAN/Internet dan keepalive setting.",
                    )
                )

        return findings
