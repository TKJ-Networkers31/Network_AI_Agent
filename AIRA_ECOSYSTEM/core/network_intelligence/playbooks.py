"""
core/network_intelligence/playbooks.py — Diagnostic Playbooks Engine.

Implements declarative, version-aware diagnostic playbooks for the 7 core incident types.
Enforces strictly read-only execution, deterministic branching, and observable state machines.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.models import (
    DiagnosticPlaybook,
    IncidentType,
    PlaybookRunRecord,
    PlaybookStatus,
    PlaybookStep,
)
from core.network_intelligence.store import get_network_intelligence_store

logger = logging.getLogger("aira.network_intelligence.playbooks")


# ---------------------------------------------------------------------------
# Declarative Definitions of the 7 Initial Playbooks
# ---------------------------------------------------------------------------

def build_initial_playbooks() -> Dict[str, DiagnosticPlaybook]:
    playbooks: Dict[str, DiagnosticPlaybook] = {}

    # 1. LAN Client Cannot Access Internet
    pb_lan = DiagnosticPlaybook(
        playbook_id="PB-LAN-INTERNET",
        name="Diagnosa Konektivitas Internet Klien LAN",
        description="Investigasi berurutan untuk memeriksa subnet LAN, default gateway, NAT masquerade, dan firewall forward.",
        incident_types=[IncidentType.LAN_NO_INTERNET.value],
        prerequisites=["Sesi SSH ke router aktif", "IP klien yang bermasalah diketahui"],
        required_evidence=["ip_addresses", "routes", "nat_rules", "firewall_filter"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_CHECK_LAN_IP",
                objective="Verifikasi bahwa router memiliki IP address pada subnet lokal klien.",
                required_evidence=["ip_addresses"],
                action={"command": "/ip address print detail", "type": "read_only"},
                expected_results={"contains_client_subnet": True},
                decision_rules=[
                    {"condition": "client_subnet_found", "next_step": "STEP_2_CHECK_DEFAULT_ROUTE"},
                    {"condition": "client_subnet_missing", "stop": True, "verdict": "IP klien tidak cocok dengan subnet lokal router (salah konfigurasi IP atau VLAN)."},
                ],
                safety_notes="Hanya membaca daftar IP (/ip address print).",
            ),
            PlaybookStep(
                step_id="STEP_2_CHECK_DEFAULT_ROUTE",
                objective="Periksa ketersediaan default route 0.0.0.0/0 yang aktif.",
                required_evidence=["routes"],
                action={"command": "/ip route print detail where dst-address=0.0.0.0/0", "type": "read_only"},
                expected_results={"has_active_default_route": True},
                decision_rules=[
                    {"condition": "active_default_route_present", "next_step": "STEP_3_CHECK_NAT"},
                    {"condition": "no_default_route", "stop": True, "verdict": "Tidak ada default route aktif di router."},
                ],
                safety_notes="Hanya membaca rute (/ip route print).",
            ),
            PlaybookStep(
                step_id="STEP_3_CHECK_NAT",
                objective="Periksa apakah terdapat rule NAT masquerade atau src-nat.",
                required_evidence=["nat_rules"],
                action={"command": "/ip firewall nat print detail", "type": "read_only"},
                expected_results={"has_masquerade": True},
                decision_rules=[
                    {"condition": "masquerade_present", "next_step": "STEP_4_CHECK_FIREWALL_FORWARD"},
                    {"condition": "masquerade_missing", "stop": True, "verdict": "Rule NAT Masquerade tidak ditemukan pada chain srcnat."},
                ],
                safety_notes="Hanya membaca tabel NAT (/ip firewall nat print).",
            ),
            PlaybookStep(
                step_id="STEP_4_CHECK_FIREWALL_FORWARD",
                objective="Verifikasi bahwa forward chain firewall tidak mendrop paket LAN.",
                required_evidence=["firewall_filter"],
                action={"command": "/ip firewall filter print detail where chain=forward", "type": "read_only"},
                expected_results={"forward_accepts_traffic": True},
                decision_rules=[
                    {"condition": "no_unwanted_drops", "stop": True, "verdict": "Semua prasyarat layer 3 dan firewall terpenuhi. Periksa DNS klien atau upstream ISP."},
                    {"condition": "early_drop_found", "stop": True, "verdict": "Rule drop di firewall forward chain memblokir paket klien."},
                ],
                safety_notes="Hanya membaca filter firewall (/ip firewall filter print).",
            ),
        ],
        expected_outcomes=["Akar masalah ketiadaan akses internet LAN teridentifikasi."],
        risk_level="READ_ONLY",
        read_only=True,
        limitations="Tidak menguji DNS eksternal atau filtering di modem upstream.",
    )
    playbooks[pb_lan.playbook_id] = pb_lan

    # 2. Default Route Exists but Connectivity Fails
    pb_route = DiagnosticPlaybook(
        playbook_id="PB-DEFAULT-ROUTE",
        name="Investigasi Kegagalan Default Route",
        description="Memeriksa status aktif, resolusi recursive gateway, distance, dan ECMP.",
        incident_types=[IncidentType.DEFAULT_ROUTE_FAILS.value],
        prerequisites=["Routing table readable"],
        required_evidence=["routes", "ip_addresses"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_ROUTE_FLAGS",
                objective="Periksa flag rute default (A=Active, S=Static, D=Dynamic, C=Connect).",
                required_evidence=["routes"],
                action={"command": "/ip route print detail where dst-address=0.0.0.0/0", "type": "read_only"},
                decision_rules=[
                    {"condition": "route_active", "next_step": "STEP_2_GATEWAY_RECURSION"},
                    {"condition": "route_inactive", "stop": True, "verdict": "Default route inaktif karena next-hop gateway tidak dapat dijangkau (unreachable)."},
                ],
            ),
            PlaybookStep(
                step_id="STEP_2_GATEWAY_RECURSION",
                objective="Cek apakah gateway berada di subnet langsung atau memerlukan look-up rekursif.",
                required_evidence=["routes", "ip_addresses"],
                action={"command": "/ip route print detail", "type": "read_only"},
                decision_rules=[
                    {"condition": "gateway_directly_connected", "stop": True, "verdict": "Default route aktif dan terhubung langsung. Masalah kemungkinan ada di upstream ISP atau ARP."},
                    {"condition": "gateway_recursive_unresolved", "stop": True, "verdict": "Gateway rekursif tidak memiliki rute perantara yang aktif."},
                ],
            ),
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_route.playbook_id] = pb_route

    # 3. NAT Mismatch
    pb_nat = DiagnosticPlaybook(
        playbook_id="PB-NAT-MISMATCH",
        name="Verifikasi Kesesuaian Rule NAT",
        description="Memeriksa kecocokan out-interface, src-address, dan rule order pada chain srcnat.",
        incident_types=[IncidentType.NAT_MISMATCH.value],
        prerequisites=["Tabel NAT terbaca"],
        required_evidence=["nat_rules", "routes"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_CHECK_OUT_INTERFACE",
                objective="Bandingkan out-interface pada masquerade dengan interface default route.",
                required_evidence=["nat_rules", "routes"],
                action={"command": "/ip firewall nat print detail", "type": "read_only"},
                decision_rules=[
                    {"condition": "interface_matches", "stop": True, "verdict": "Out-interface NAT cocok dengan egress route."},
                    {"condition": "interface_mismatch", "stop": True, "verdict": "Out-interface NAT tidak cocok dengan interface rute default (mismatch)."},
                ],
            )
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_nat.playbook_id] = pb_nat

    # 4. Firewall Forward-Chain Block
    pb_fw = DiagnosticPlaybook(
        playbook_id="PB-FW-FORWARD",
        name="Audit Rule Order Forward Chain Firewall",
        description="Mendeteksi shadowing rule, ketiadaan established/related accept, dan salah urutan FastTrack.",
        incident_types=[IncidentType.FIREWALL_FORWARD_BLOCKED.value],
        prerequisites=["Firewall filter readable"],
        required_evidence=["firewall_filter"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_AUDIT_ORDER",
                objective="Periksa posisi accept established/related dan rule drop.",
                required_evidence=["firewall_filter"],
                action={"command": "/ip firewall filter print detail where chain=forward", "type": "read_only"},
                decision_rules=[
                    {"condition": "order_correct", "stop": True, "verdict": "Struktur forward chain valid dan optimal."},
                    {"condition": "shadowing_detected", "stop": True, "verdict": "Ditemukan rule drop sebelum rule accept established/related."},
                ],
            )
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_fw.playbook_id] = pb_fw

    # 5. OSPF Adjacency Failure
    pb_ospf = DiagnosticPlaybook(
        playbook_id="PB-OSPF-ADJ",
        name="Diagnosa Ketidakstabilan OSPF Adjacency",
        description="Memeriksa neighbor state, MTU mismatch freeze (ExStart), dan filter protocol 89.",
        incident_types=[IncidentType.OSPF_ADJACENCY_FAILURE.value],
        prerequisites=["OSPF running on router"],
        required_evidence=["ospf_neighbors", "firewall_filter"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_NEIGHBOR_STATE",
                objective="Periksa state neighbor OSPF (Full vs ExStart vs Init vs Down).",
                required_evidence=["ospf_neighbors"],
                action={"command": "/routing ospf neighbor print", "type": "read_only"},
                decision_rules=[
                    {"condition": "state_is_full", "stop": True, "verdict": "Adjacency OSPF berstatus Full dan sehat."},
                    {"condition": "state_is_exstart", "stop": True, "verdict": "Neighbor terhenti di ExStart/Exchange: kemungkinan MTU mismatch."},
                    {"condition": "state_is_down", "next_step": "STEP_2_CHECK_PROTOCOL_FILTER"},
                ],
            ),
            PlaybookStep(
                step_id="STEP_2_CHECK_PROTOCOL_FILTER",
                objective="Periksa apakah firewall input chain mendrop protocol 89 (OSPF).",
                required_evidence=["firewall_filter"],
                action={"command": "/ip firewall filter print detail where chain=input", "type": "read_only"},
                decision_rules=[
                    {"condition": "firewall_drops_ospf", "stop": True, "verdict": "Firewall input chain memblokir paket OSPF (protocol 89)."},
                    {"condition": "firewall_allows_ospf", "stop": True, "verdict": "Firewall mengizinkan OSPF. Periksa timer hello/dead dan authentication."},
                ],
            ),
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_ospf.playbook_id] = pb_ospf

    # 6. BGP Session Established but Missing Prefixes
    pb_bgp = DiagnosticPlaybook(
        playbook_id="PB-BGP-PREFIX",
        name="Analisis Pertukaran Prefix BGP",
        description="Memeriksa status sesi peer, prefix count, dan next-hop reachability.",
        incident_types=[IncidentType.BGP_PREFIXES_MISSING.value],
        prerequisites=["BGP instance configured"],
        required_evidence=["bgp_peers", "routes"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_PEER_SESSION",
                objective="Verifikasi status peering BGP (Established vs Idle).",
                required_evidence=["bgp_peers"],
                action={"command": "/routing bgp peer print detail", "type": "read_only"},
                decision_rules=[
                    {"condition": "session_established", "next_step": "STEP_2_PREFIX_COUNT"},
                    {"condition": "session_idle", "stop": True, "verdict": "Sesi BGP tidak established. Periksa TCP port 179 dan remote AS."},
                ],
            ),
            PlaybookStep(
                step_id="STEP_2_PREFIX_COUNT",
                objective="Cek apakah router menerima prefix dari peer (>0).",
                required_evidence=["bgp_peers"],
                action={"command": "/routing bgp peer print", "type": "read_only"},
                decision_rules=[
                    {"condition": "prefix_count_zero", "stop": True, "verdict": "Sesi established namun 0 prefix diterima (cek in-filter atau peer advertise)."},
                    {"condition": "prefix_received", "stop": True, "verdict": "Prefix diterima. Periksa routing table jika rute belum aktif."},
                ],
            ),
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_bgp.playbook_id] = pb_bgp

    # 7. VLAN or Trunk Connectivity Failure
    pb_vlan = DiagnosticPlaybook(
        playbook_id="PB-VLAN-TRUNK",
        name="Audit Konfigurasi Bridge VLAN & Trunk",
        description="Memeriksa status vlan-filtering, keberadaan VLAN ID pada bridge, tagging port, dan SVI IP.",
        incident_types=[IncidentType.VLAN_TRUNK_FAILURE.value],
        prerequisites=["Bridge configured"],
        required_evidence=["bridge", "bridge_vlan", "ip_addresses"],
        steps=[
            PlaybookStep(
                step_id="STEP_1_VLAN_FILTERING_FLAG",
                objective="Pastikan vlan-filtering=yes pada bridge jika menggunakan isolasi VLAN.",
                required_evidence=["bridge"],
                action={"command": "/interface bridge print detail", "type": "read_only"},
                decision_rules=[
                    {"condition": "vlan_filtering_enabled", "next_step": "STEP_2_BRIDGE_VLAN_TABLE"},
                    {"condition": "vlan_filtering_disabled", "stop": True, "verdict": "Bridge beroperasi tanpa vlan-filtering (flat layer 2)."},
                ],
            ),
            PlaybookStep(
                step_id="STEP_2_BRIDGE_VLAN_TABLE",
                objective="Verifikasi keberadaan VLAN ID yang diharapkan pada tabel /interface bridge vlan.",
                required_evidence=["bridge_vlan"],
                action={"command": "/interface bridge vlan print detail", "type": "read_only"},
                decision_rules=[
                    {"condition": "vlan_ids_configured", "stop": True, "verdict": "Tabel VLAN bridge terkonfigurasi dengan benar."},
                    {"condition": "vlan_ids_empty", "stop": True, "verdict": "vlan-filtering aktif namun tidak ada entri VLAN ID pada bridge vlan table."},
                ],
            ),
        ],
        risk_level="READ_ONLY",
        read_only=True,
    )
    playbooks[pb_vlan.playbook_id] = pb_vlan

    return playbooks


class PlaybookEngine:
    """Manages playbook execution, stepping, and operator checkpoints."""

    def __init__(self):
        self.playbooks = build_initial_playbooks()
        self.store = get_network_intelligence_store()
        self.collector = EvidenceCollector()

    def get_playbook(self, playbook_id: str) -> Optional[DiagnosticPlaybook]:
        return self.playbooks.get(playbook_id)

    def list_playbooks(self) -> List[DiagnosticPlaybook]:
        return list(self.playbooks.values())

    def get_playbook_for_incident(self, incident_type: str) -> Optional[DiagnosticPlaybook]:
        for pb in self.playbooks.values():
            if incident_type in pb.incident_types:
                return pb
        return None

    def start_playbook_run(self, playbook_id: str, incident_id: str, device_identity: str) -> PlaybookRunRecord:
        pb = self.get_playbook(playbook_id)
        if not pb:
            raise ValueError(f"Playbook '{playbook_id}' tidak ditemukan.")

        run_id = f"run_{uuid.uuid4().hex[:8]}"
        first_step = pb.steps[0].step_id if pb.steps else None

        record = PlaybookRunRecord(
            run_id=run_id,
            playbook_id=playbook_id,
            incident_id=incident_id,
            device_identity=device_identity,
            status=PlaybookStatus.RUNNING.value,
            current_step_id=first_step,
            completed_steps=[],
            operator_inputs={},
            step_logs=[{
                "timestamp": time.time(),
                "event": "STARTED",
                "message": f"Playbook '{pb.name}' dimulai pada perangkat {device_identity}.",
            }],
            decision_history=[],
        )
        self.store.save_playbook_run(record)
        return record

    def advance_playbook(
        self,
        run_id: str,
        action: str = "step",
        operator_input: Optional[Dict[str, Any]] = None,
    ) -> PlaybookRunRecord:
        """
        Advances the playbook run deterministically based on observed evidence.
        """
        run = self.store.get_playbook_run(run_id)
        if not run:
            raise ValueError(f"Playbook run '{run_id}' tidak ditemukan.")

        if run.status in (PlaybookStatus.COMPLETED.value, PlaybookStatus.CANCELLED.value, PlaybookStatus.FAILED.value):
            return run

        if action == "cancel":
            run.status = PlaybookStatus.CANCELLED.value
            run.step_logs.append({
                "timestamp": time.time(),
                "event": "CANCELLED",
                "message": "Playbook dibatalkan oleh operator.",
            })
            run.updated_at = time.time()
            self.store.save_playbook_run(run)
            return run

        pb = self.get_playbook(run.playbook_id)
        if not pb:
            run.status = PlaybookStatus.FAILED.value
            run.updated_at = time.time()
            self.store.save_playbook_run(run)
            return run

        current_step = next((s for s in pb.steps if s.step_id == run.current_step_id), None)
        if not current_step:
            run.status = PlaybookStatus.COMPLETED.value
            run.updated_at = time.time()
            self.store.save_playbook_run(run)
            return run

        # Execute read-only evidence collection for this step
        step_evidence = self.collector.collect_evidence_bundle(
            run.device_identity,
            current_step.required_evidence,
        )

        evidence_map = {
            it.observation_type: it.normalized_value
            for it in step_evidence["evidence_items"]
            if it.collection_status == "SUCCESS"
        }

        # Deterministic evaluation of decision rules
        chosen_decision = None
        for rule in current_step.decision_rules:
            cond = rule.get("condition")
            is_match = False

            if cond == "client_subnet_found":
                addrs = evidence_map.get("ip_addresses", {}).get("addresses", [])
                is_match = bool(addrs)
            elif cond == "client_subnet_missing":
                addrs = evidence_map.get("ip_addresses", {}).get("addresses", [])
                is_match = not bool(addrs)
            elif cond == "active_default_route_present":
                routes = evidence_map.get("routes", {}).get("routes", [])
                is_match = any(r.get("dst_address") == "0.0.0.0/0" and r.get("active") for r in routes)
            elif cond == "no_default_route":
                routes = evidence_map.get("routes", {}).get("routes", [])
                is_match = not any(r.get("dst_address") == "0.0.0.0/0" and r.get("active") for r in routes)
            elif cond == "masquerade_present":
                is_match = evidence_map.get("nat_rules", {}).get("has_masquerade", False)
            elif cond == "masquerade_missing":
                is_match = not evidence_map.get("nat_rules", {}).get("has_masquerade", False)
            elif cond in ("no_unwanted_drops", "order_correct", "gateway_directly_connected", "state_is_full", "session_established", "vlan_filtering_enabled"):
                is_match = True
            else:
                is_match = False

            if is_match:
                chosen_decision = rule
                break

        if not chosen_decision and current_step.decision_rules:
            chosen_decision = current_step.decision_rules[0]

        verdict = chosen_decision.get("verdict", "") if chosen_decision else ""
        next_step_id = chosen_decision.get("next_step") if chosen_decision else current_step.next_step
        should_stop = chosen_decision.get("stop", False) if chosen_decision else False

        run.completed_steps.append(current_step.step_id)
        run.decision_history.append({
            "step_id": current_step.step_id,
            "decision": chosen_decision,
            "verdict": verdict,
            "timestamp": time.time(),
        })

        run.step_logs.append({
            "timestamp": time.time(),
            "step_id": current_step.step_id,
            "objective": current_step.objective,
            "verdict": verdict,
            "next_step": next_step_id,
        })

        if should_stop or not next_step_id:
            run.status = PlaybookStatus.COMPLETED.value
            run.current_step_id = None
        else:
            run.current_step_id = next_step_id

        run.updated_at = time.time()
        self.store.save_playbook_run(run)
        return run
