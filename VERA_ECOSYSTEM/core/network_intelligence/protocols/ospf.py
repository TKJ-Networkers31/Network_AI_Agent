"""
AIRA OS — OSPF Protocol Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class OSPFAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "ospf"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["routes"]
    optional_evidence: List[str] = ["ospf_instance", "ospf_neighbors", "ospf_interfaces"]
    known_limitations: List[str] = [
        "Cryptographic MD5/SHA authentication keys are never extracted; auth failures inferred from state timeouts.",
        "LSA database flooding details require deep OSPF debug commands not permitted on read-only boundary.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        nbrs = pdata.get("ospf_neighbors") or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "ospf_neighbors")]

        if not nbrs:
            return findings

        for nb in nbrs:
            if not isinstance(nb, dict):
                continue
            nid = str(nb.get("neighbor_id") or nb.get("address") or "unknown")
            st = str(nb.get("state") or "").lower()
            iface = str(nb.get("interface") or "")
            if "full" not in st and "2-way" not in st:
                # Distinguish ExStart/Exchange (MTU mismatch indicator) from Init/Down
                sub_cat = "MTU_OR_AUTH_MISMATCH" if ("exstart" in st or "exchange" in st) else "ADJACENCY_DOWN"
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_ospf_stuck_{device_id}_{nid}_{uuid.uuid4().hex[:6]}",
                        protocol="ospf",
                        device_id=device_id,
                        severity="critical" if "down" in st or "attempt" in st else "warning",
                        category="OSPF_FAILURE",
                        summary=f"OSPF adjacency {device_id} <-> {nid} ({iface}) tertahan pada state '{nb.get('state')}'.",
                        technical_detail=(
                            f"State '{st}' terdeteksi pada interface '{iface}'. "
                            f"{'Kemungkinan ketidakcocokan MTU (MTU mismatch) pada antarmuka.' if 'exstart' in st else 'Periksa timer hello/dead, area ID, dan autentikasi.'}"
                        ),
                        evidence_ids=ev_ids,
                        affected_entities=[f"ospf_nbr:{device_id}:{nid}"],
                        remediation_suggestion="Cocokkan MTU interface kedua belah router, pastikan Area ID dan subnet sama.",
                    )
                )

        return findings
