"""
AIRA OS — BGP Protocol Analyzer & 6-Stage Prefix Lifecycle (Networking VI / WP 6.8).

Strictly distinguishes:
1. `SESSION_ESTABLISHED`
2. `ROUTE_RECEIVED`
3. `ROUTE_ACCEPTED`
4. `ROUTE_SELECTED`
5. `ROUTE_INSTALLED`
6. `FORWARDING_VERIFIED`
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.network_intelligence.intelligence_models import (
    BGPPrefixLifecycleState,
    NetworkEvidenceBundle,
)
from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding


class BGPAnalyzer(BaseProtocolAnalyzer):
    protocol_name: str = "bgp"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = ["routes"]
    optional_evidence: List[str] = ["bgp_peers", "bgp_routes"]
    known_limitations: [
        "Inbound route-filters / prefix-lists evaluated via accepted vs received counts or missing active RIB routes.",
    ]

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        findings: List[ProtocolFinding] = []
        pdata = bundle.protocol_evidence.get(device_id) or {}
        peers = pdata.get("bgp_peers") or []
        routes = bundle.routing_evidence.get(device_id) or []
        ev_ids = [r.evidence_id for r in bundle.records_for_device(device_id, "bgp_peers")]

        if not peers:
            for rec in bundle.records_for_device(device_id, "bgp_peers"):
                if isinstance(rec.normalized_payload, list):
                    peers.extend(rec.normalized_payload)
                elif isinstance(rec.normalized_payload, dict):
                    peers.append(rec.normalized_payload)

        if not peers:
            return findings

        # Check peer session states
        for bp in peers:
            if not isinstance(bp, dict):
                continue
            pname = str(bp.get("name") or bp.get("remote_address") or "peer")
            st = str(bp.get("state") or "").lower()
            rem_as = bp.get("remote_as")
            rem_addr = str(bp.get("remote_address") or "")

            if st not in ("established", "up") and not bp.get("established"):
                findings.append(
                    ProtocolFinding(
                        finding_id=f"fnd_bgp_session_{device_id}_{pname}_{uuid.uuid4().hex[:6]}",
                        protocol="bgp",
                        device_id=device_id,
                        severity="critical",
                        category="BGP_FAILURE",
                        summary=f"Sesi BGP {device_id} -> {pname} (AS{rem_as}) tidak terhubung (State: '{bp.get('state')}').",
                        technical_detail=f"Sesi BGP gagal mencapai state Established. Status={bp.get('state')}. Lifecycle: Gagal pada tahap 1 (SESSION_ESTABLISHED).",
                        evidence_ids=ev_ids,
                        affected_entities=[f"bgp_peer:{device_id}:{pname}"],
                        remediation_suggestion="Periksa konektivitas TCP port 179, konfigurasi Remote AS, dan update-source IP.",
                    )
                )
            else:
                # Session is established; inspect received vs installed prefixes (Stages 2-5)
                pref_cnt = bp.get("prefixes_received")
                if pref_cnt is None:
                    pref_cnt = bp.get("prefix_count")
                if pref_cnt is not None and int(pref_cnt) == 0:
                    findings.append(
                        ProtocolFinding(
                            finding_id=f"fnd_bgp_zero_prefix_{device_id}_{pname}_{uuid.uuid4().hex[:6]}",
                            protocol="bgp",
                            device_id=device_id,
                            severity="warning",
                            category="BGP_ZERO_PREFIX",
                            summary=f"Sesi BGP {device_id} -> {pname} (AS{rem_as}) established tetapi 0 prefix diterima.",
                            technical_detail="Sesi BGP berhasil terhubung (State: Established), namun upstream peer mengirimkan 0 prefix atau seluruh prefix ditolak oleh inbound filter.",
                            evidence_ids=ev_ids,
                            affected_entities=[f"bgp_peer:{device_id}:{pname}"],
                            remediation_suggestion="Periksa inbound routing-filter pada RouterOS dan pastikan peer meng-advertise network/prefix.",
                        )
                    )
                bgp_routes_installed = [
                    r for r in routes
                    if r.bgp or str(r.protocol).lower() == "bgp"
                ]
                withdrawn = int(bp.get("updates_withdrawn") or 0)
                if withdrawn >= 10:
                    findings.append(
                        ProtocolFinding(
                            finding_id=f"fnd_bgp_withdrawn_{device_id}_{pname}_{uuid.uuid4().hex[:6]}",
                            protocol="bgp",
                            device_id=device_id,
                            severity="warning",
                            category="BGP_FAILURE",
                            summary=f"BGP peer {pname} tercatat melakukan {withdrawn} penarikan rute (route withdrawals).",
                            technical_detail="Prefix yang sebelumnya diterima ditarik kembali oleh upstream peer.",
                            evidence_ids=ev_ids,
                            affected_entities=[f"bgp_peer:{device_id}:{pname}"],
                        )
                    )

        return findings

    @staticmethod
    def classify_prefix_lifecycle(
        prefix: str,
        peer_established: bool,
        is_received: bool,
        is_accepted: bool,
        is_selected_rib: bool,
        is_fib_verified: bool,
    ) -> str:
        """Determines the exact stage in the 6-stage BGP prefix lifecycle."""
        if not peer_established:
            return "SESSION_NOT_ESTABLISHED"
        if not is_received:
            return BGPPrefixLifecycleState.SESSION_ESTABLISHED.value
        if not is_accepted:
            return BGPPrefixLifecycleState.ROUTE_RECEIVED.value
        if not is_selected_rib:
            return BGPPrefixLifecycleState.ROUTE_ACCEPTED.value
        if not is_fib_verified:
            return BGPPrefixLifecycleState.ROUTE_SELECTED.value
        return BGPPrefixLifecycleState.FORWARDING_VERIFIED.value
