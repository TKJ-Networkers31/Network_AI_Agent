"""
AIRA OS — IPv6 Addressing & Routing Protocol Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class IPv6Analyzer(BaseProtocolAnalyzer):
    protocol_name: str = "ipv6"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["interfaces"]
    optional_evidence: List[str] = ["ipv6_addresses", "ipv6_routes", "ipv6_neighbors"]
    known_limitations: List[str] = [
        "Read-only SSH allowlist does not execute live `/ipv6 route print`; analysis runs when explicit ipv6 evidence is present.",
        "IPv6 neighbor discovery (NDP) state requires explicit observation.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        v6_addrs = pdata.get("ipv6_addresses") or []
        v6_routes = pdata.get("ipv6_routes") or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "ipv6_addresses")]

        if not v6_addrs and not v6_routes:
            return findings

        # Check global unicast vs link-local
        has_gua = False
        has_link_local = False
        for entry in v6_addrs:
            if not isinstance(entry, dict) or entry.get("disabled"):
                continue
            addr_str = str(entry.get("address") or "")
            try:
                ip_obj = ipaddress.ip_interface(addr_str).ip
                if ip_obj.is_link_local:
                    has_link_local = True
                elif ip_obj.is_global:
                    has_gua = True
            except ValueError:
                continue

        if has_gua and v6_routes:
            has_v6_default = any(
                str(r.get("dst_prefix") or "").strip() == "::/0" and r.get("active", True)
                for r in v6_routes
            )
            if not has_v6_default:
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_ip6_nodefault_{device_id}_{uuid.uuid4().hex[:6]}",
                        protocol="ipv6",
                        device_id=device_id,
                        severity="info",
                        category="ROUTING_FAILURE",
                        summary=f"Perangkat '{device_id}' memiliki alamat IPv6 global unicast namun tidak ada default route (::/0).",
                        technical_detail="IPv6 GUA aktif tanpa default gateway ::/0; trafik internet IPv6 tidak akan diteruskan.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"device:{device_id}"],
                        remediation_suggestion="Tambahkan rute default IPv6 ::/0 via SLAAC, RA, atau gateway statis.",
                    )
                )

        return findings
