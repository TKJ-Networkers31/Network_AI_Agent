"""
AIRA OS — IPv4 Addressing & Subnet Protocol Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class IPv4Analyzer(BaseProtocolAnalyzer):
    protocol_name: str = "ipv4"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["ip_addresses", "interfaces"]
    optional_evidence: List[str] = ["routes", "arp"]
    known_limitations: [
        "Dynamic DHCP client lease changes not monitored unless reflected in /ip address list.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        ip_list = pdata.get("ip_addresses") or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "ip_addresses")]

        if not ip_list:
            return findings

        # Check for overlapping subnets on distinct interfaces of the same device
        parsed_subnets: List[Dict[str, Any]] = []
        for entry in ip_list:
            if not isinstance(entry, dict) or entry.get("disabled"):
                continue
            addr_str = str(entry.get("address") or "")
            iname = str(entry.get("interface") or "")
            if "/" not in addr_str:
                continue
            try:
                net = ipaddress.ip_network(addr_str, strict=False)
                parsed_subnets.append({"net": net, "iface": iname, "raw": addr_str})
            except ValueError:
                continue

        for i, sub_a in enumerate(parsed_subnets):
            for j, sub_b in enumerate(parsed_subnets):
                if i < j and sub_a["iface"] != sub_b["iface"]:
                    if sub_a["net"].overlaps(sub_b["net"]):
                        findings.append(
                            ProtocolFinding(
                                finding_id=f"fnd_ip4_overlap_{device_id}_{uuid.uuid4().hex[:6]}",
                                protocol="ipv4",
                                device_id=device_id,
                                severity="critical",
                                category="ROUTING_FAILURE",
                                summary=f"Konflik subnet IPv4 tumpang tindih antara {sub_a['iface']} ({sub_a['raw']}) dan {sub_b['iface']} ({sub_b['raw']}).",
                                technical_detail="Subnet tumpang tindih pada interface berbeda menyebabkan kebingungan LPM dan rute connected yang saling mematikan.",
                                evidence_ids=ev_ids,
                                affected_entities=[f"iface:{device_id}:{sub_a['iface']}", f"iface:{device_id}:{sub_b['iface']}"],
                                remediation_suggestion="Ganti skema pengalamatan IP agar subnet pada antarmuka lokal tidak saling tumpang tindih.",
                            )
                        )

        # Check default route presence
        routes = bundle.routing_evidence.get(device_id) or []
        has_default = any(r.is_default_route() and r.active for r in routes)
        if not has_default and any(p["iface"].startswith("ether1") or "wan" in p["iface"].lower() for p in parsed_subnets):
            findings.append(
                ProtocolFinding(
                    finding_id=f"fnd_ip4_nodefault_{device_id}_{uuid.uuid4().hex[:6]}",
                    protocol="ipv4",
                    device_id=device_id,
                    severity="warning",
                    category="ROUTING_FAILURE",
                    summary=f"Perangkat '{device_id}' memiliki antarmuka WAN/upstream namun tidak memiliki default route (0.0.0.0/0) aktif.",
                    technical_detail="Tidak ada rute 0.0.0.0/0 aktif pada RIB. Trafik menuju Internet atau subnet luar akan di-drop.",
                    evidence_ids=[r.evidence_id for r in bundle.records_for_device(device_id, "routes")],
                    affected_entities=[f"device:{device_id}"],
                    remediation_suggestion="Konfigurasikan default route atau pastikan DHCP client/BGP/OSPF menginjeksi default route.",
                )
            )

        return findings
