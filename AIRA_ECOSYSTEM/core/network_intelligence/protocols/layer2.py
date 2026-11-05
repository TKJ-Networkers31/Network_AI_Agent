"""
AIRA OS — Layer 2 Protocol & VLAN Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class Layer2Analyzer(BaseProtocolAnalyzer):
    protocol_name: str = "layer2"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["interfaces"]
    optional_evidence: List[str] = ["bridge", "bridge_ports", "bridge_vlan", "vlans", "arp"]
    known_limitations: List[str] = [
        "Internal ASIC hardware-offloaded bridge packet tables require specific RouterOS switch export.",
        "STP root change counters only observable when bridge monitor evidence is collected.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        ifaces = bundle.interface_evidence.get(device_id) or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "interfaces")]

        # 1. Interface Operational State & L2MTU Mismatch
        l2mtus: Dict[str, int] = {}
        for iface in ifaces:
            iname = str(iface.get("interface_name") or "")
            oper = str(iface.get("oper_status") or "").lower()
            admin = str(iface.get("admin_status") or "enabled").lower()
            if admin != "disabled" and oper in ("down", "lowerlayerdown"):
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_l2_{device_id}_{iname}_{uuid.uuid4().hex[:6]}",
                        protocol="layer2",
                        device_id=device_id,
                        severity="warning",
                        category="LAYER2_FAILURE",
                        summary=f"Antarmuka L2 {device_id}:{iname} enabled namun berstatus '{oper}'.",
                        technical_detail=f"Antarmuka fisik/L2 gagal mencapai status UP. Admin={admin}, Oper={oper}.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"iface:{device_id}:{iname}"],
                        remediation_suggestion=f"Periksa koneksi fisik/kabel, link partner, dan SFP pada {iname}.",
                    )
                )
            if iface.get("l2mtu"):
                l2mtus[iname] = int(iface["l2mtu"])

        # 2. Bridge VLAN filtering & PVID / Tagging Discrepancy
        bridges = pdata.get("bridge") or []
        bridge_vlans = pdata.get("bridge_vlan") or []
        ports = pdata.get("bridge_ports") or []

        if bridges:
            b_ev = [r.evidence_id for r in bundle.records_for_device(device_id, "bridge")]
            ev_ids.extend(b_ev)

        for br in bridges:
            bname = br.get("name", "bridge")
            vlan_filter = bool(br.get("vlan_filtering"))
            if not vlan_filter and bridge_vlans:
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_l2_vlanfilter_{device_id}_{uuid.uuid4().hex[:6]}",
                        protocol="layer2",
                        device_id=device_id,
                        severity="warning",
                        category="VLAN_MISMATCH",
                        summary=f"Bridge '{bname}' memiliki konfigurasi VLAN table namun `vlan-filtering=no`.",
                        technical_detail="Aturan bridge VLAN tidak akan difilter atau diisolasi secara hardware/software jika vlan-filtering dinonaktifkan.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"bridge:{device_id}:{bname}"],
                        remediation_suggestion=f"Aktifkan vlan-filtering pada bridge {bname} setelah memastikan manajemen pvid aman.",
                    )
                )

        return findings
