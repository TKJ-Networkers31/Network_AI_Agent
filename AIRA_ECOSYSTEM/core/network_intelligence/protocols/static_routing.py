"""
AIRA OS — Static Routing Protocol Analyzer (Networking VI / WP 6.8).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding
from core.routing.unified_route_parser import NextHopResolutionStatus, resolve_recursive_next_hop


class StaticRoutingAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "static_routing"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["routes"]
    optional_evidence: List[str] = ["interfaces"]
    known_limitations: List[str] = [
        "Mangle routing-marks and policy routing tables (/ip route rule) analyzed based on static table definitions.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        routes = bundle.routing_evidence.get(device_id) or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "routes")]

        if not routes:
            return findings

        # Check for recursive loops, unreachable static gateways, and blackholes
        for r in routes:
            if r.disabled:
                continue
            table_routes = [x for x in routes if (x.routing_table or "main") == (r.routing_table or "main")]
            gw_str = str(r.immediate_gw or r.gateway or "").split(",")[0].strip()

            if r.route_type.value in ("blackhole", "unreachable", "prohibit") or r.unreachable:
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_rt_special_{device_id}_{uuid.uuid4().hex[:6]}",
                        protocol="static_routing",
                        device_id=device_id,
                        severity="info",
                        category="ROUTING_FAILURE",
                        summary=f"Rute {r.dst_prefix} bertipe '{r.route_type.value}' pada tabel '{r.routing_table}'.",
                        technical_detail="Paket menuju prefix ini sengaja dibuang (blackhole/unreachable) sesuai kebijakan tabel rute.",
                        evidence_ids=ev_ids,
                        affected_entities=[f"route:{device_id}:{r.routing_table}:{r.dst_prefix}"],
                    )
                )

            if gw_str and not r.connect:
                res = resolve_recursive_next_hop(gw_str, table_routes, max_depth=16)
                if res.loop_detected:
                    findings.append(
                        ProtocolFinding(
                            finding_id=f"fnd_rt_loop_{device_id}_{uuid.uuid4().hex[:6]}",
                            protocol="static_routing",
                            device_id=device_id,
                            severity="critical",
                            category="ROUTING_FAILURE",
                            summary=f"Loop rekursif terdeteksi untuk rute {r.dst_prefix} via {gw_str}.",
                            technical_detail=f"Next-hop rekursif menghasilkan siklus: {' -> '.join(res.resolution_chain)}.",
                            evidence_ids=ev_ids,
                            affected_entities=[f"route:{device_id}:{r.routing_table}:{r.dst_prefix}"],
                            remediation_suggestion="Ubah gateway next-hop agar mengarah ke prefix yang memiliki rute langsung (connected).",
                        )
                    )
                elif res.status in (NextHopResolutionStatus.UNRESOLVED, NextHopResolutionStatus.UNREACHABLE) and not r.interface_name:
                    findings.append(
                        ProtocolFinding(
                            finding_id=f"fnd_rt_unres_{device_id}_{uuid.uuid4().hex[:6]}",
                            protocol="static_routing",
                            device_id=device_id,
                            severity="warning",
                            category="NEXT_HOP_FAILURE",
                            summary=f"Next-hop gateway '{gw_str}' pada rute {r.dst_prefix} tidak dapat di-resolve.",
                            technical_detail="Tidak ada rute connected atau LPM aktif yang dapat mencapai IP gateway.",
                            evidence_ids=ev_ids,
                            affected_entities=[f"route:{device_id}:{r.routing_table}:{r.dst_prefix}"],
                            remediation_suggestion="Pastikan antarmuka lokal memiliki IP satu subnet dengan gateway atau tambahkan rute spesifik.",
                        )
                    )

        return findings
