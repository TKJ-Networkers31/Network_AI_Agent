"""
core/network_intelligence/simulator.py — Static Forwarding Simulation & Before/After Comparison.

Evaluates modeled control-plane effects of candidate configuration changes against baseline observations.
Explicitly discloses unmodeled dataplane behaviors (FastTrack, hardware offload, ECMP hashing, conntrack).
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, List, Optional, Tuple

from agents.akane.reasoning_engine import (
    ParsedRoute,
    evaluate_longest_prefix_match,
    parse_routeros_routes,
)
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.models import (
    ConfigurationPlan,
    SimulationResult,
)

logger = logging.getLogger("aira.network_intelligence.simulator")

UNMODELED_BEHAVIORS_DISCLOSURE = [
    "FastTrack Connection Offload: Paket koneksi yang telah established memotong evaluasi firewall dan routing secara dinamik di kernel.",
    "Hardware Offload (Switch Chip / ASIC): Frame switching Layer 2 diteruskan langsung oleh switch chip tanpa melewati CPU router.",
    "Connection Tracking Table State & Timeouts: Status dinamis conntrack (ESTABLISHED, SYN_RECV, UDP stream timeouts) tidak dimodelkan.",
    "ECMP Hashing Algorithm: Pembagian beban trafik multi-gateway bergantung pada 5-tuple hash runtime yang tidak deterministik secara statis.",
    "IPsec / Tunnel Overhead: Penurunan Maximum Transmission Unit (MTU) akibat enkapsulasi IPsec/GRE/WireGuard tidak dimodelkan.",
    "Dynamic Protocol Convergence: Waktu dan latensi propagasi konvergensi rute OSPF/BGP membutuhkan pertukaran paket kontrol aktual.",
]


class StaticSimulator:
    """Simulates modeled effects of proposed changes without touching production routers."""

    def __init__(self):
        self.collector = EvidenceCollector()

    def simulate_plan(self, plan: ConfigurationPlan, test_destinations: Optional[List[str]] = None) -> SimulationResult:
        """
        Runs static simulation comparing baseline state against modeled post-change state.
        Discloses modeled and unmodeled forwarding effects transparently.
        """
        target = plan.target_devices[0] if plan.target_devices else "unknown"
        c_type = plan.desired_state.get("change_type", "").upper()
        params = plan.desired_state.get("parameters", {})

        # Fetch baseline routes and interfaces
        bundle = self.collector.collect_evidence_bundle(target, ["routes", "ip_addresses", "interfaces"])
        routes_norm = next((it.normalized_value for it in bundle["evidence_items"] if it.observation_type == "routes" and it.collection_status == "SUCCESS"), None) or {}
        baseline_routes = routes_norm.get("routes", [])

        # Formulate modeled post-change routes
        modeled_routes = list(baseline_routes)
        if c_type == "ADD_STATIC_ROUTE":
            dst = params.get("dst_address", "")
            gw = params.get("gateway", "")
            dist = int(params.get("distance", 1))
            if dst and gw:
                modeled_routes.append({
                    "dst_address": dst,
                    "gateway": gw,
                    "distance": dist,
                    "active": True,
                    "dynamic": False,
                    "connect": False,
                    "static": True,
                    "prefix_len": int(dst.split("/")[1]) if "/" in dst else 32,
                    "raw_flags": "AS",
                })

        # Test forwarding simulation for sample or given destinations
        test_ips = test_destinations or ["8.8.8.8", "1.1.1.1"]
        if "dst_address" in params and "/" in params["dst_address"]:
            # Add an IP inside the newly targeted subnet for verification
            try:
                target_net = ipaddress.ip_network(params["dst_address"], strict=False)
                for host_ip in target_net.hosts():
                    test_ips.append(str(host_ip))
                    break
            except Exception:
                pass

        baseline_lpm_routes = [
            ParsedRoute(
                dst_address=r.get("dst_address", "0.0.0.0/0"),
                gateway=r.get("gateway", ""),
                distance=r.get("distance", 1),
                active=r.get("active", True),
            )
            for r in baseline_routes
        ]
        post_lpm_routes = [
            ParsedRoute(
                dst_address=r.get("dst_address", "0.0.0.0/0"),
                gateway=r.get("gateway", ""),
                distance=r.get("distance", 1),
                active=r.get("active", True),
            )
            for r in modeled_routes
        ]

        forwarding_comparison: Dict[str, Any] = {}
        for tip in test_ips:
            res_before = evaluate_longest_prefix_match(baseline_lpm_routes, tip)
            res_after = evaluate_longest_prefix_match(post_lpm_routes, tip)

            gw_before = (res_before.get("best_route") or {}).get("gateway", "NONE")
            gw_after = (res_after.get("best_route") or {}).get("gateway", "NONE")
            p_len_before = (res_before.get("best_route") or {}).get("prefix_len", 0)
            p_len_after = (res_after.get("best_route") or {}).get("prefix_len", 0)

            changed = (gw_before != gw_after) or (p_len_before != p_len_after)

            forwarding_comparison[tip] = {
                "before": {"gateway": gw_before, "prefix_len": p_len_before, "matched": res_before.get("matched")},
                "after": {"gateway": gw_after, "prefix_len": p_len_after, "matched": res_after.get("matched")},
                "route_changed": changed,
            }

        # Determine explicit simulation status: PASS, FAIL, or UNKNOWN
        has_unmatched = any(not forwarding_comparison[tip]["after"]["matched"] for tip in test_ips)
        evidence_failed = (
            routes_norm is None
            or not bundle.get("evidence_items")
            or any(it.collection_status != "SUCCESS" for it in bundle["evidence_items"])
        )

        if evidence_failed:
            sim_status = "UNKNOWN"
            expected_result = "Bukti baseline rute tidak lengkap atau tidak dapat diakses; hasil forwarding tidak dapat dipastikan (UNKNOWN)."
        elif has_unmatched:
            sim_status = "FAIL"
            expected_result = "Simulasi forwarding menunjukkan beberapa paket uji mengalami unroutable/drop (FAIL)."
        else:
            sim_status = "PASS"
            expected_result = f"Perubahan '{c_type}' berhasil disimulasikan pada model forwarding statis (PASS)."

        sim_result = SimulationResult(
            simulation_status=sim_status,
            inputs_summary={
                "target_device": target,
                "change_type": c_type,
                "baseline_routes_count": len(baseline_routes),
                "modeled_routes_count": len(modeled_routes),
            },
            assumptions=[
                "Semua interface yang berstatus running diasumsikan tetap UP.",
                "Tidak ada policy routing (routing marks) yang mengesampingkan rute 'main'.",
            ],
            modeled_behavior={
                "forwarding_comparison": forwarding_comparison,
            },
            expected_result=expected_result,
            unmodeled_behavior=UNMODELED_BEHAVIORS_DISCLOSURE,
            confidence_limitations=(
                "Simulasi ini mengevaluasi algoritma Longest Prefix Match (LPM) standar. "
                "Data path aktual pada RouterBOARD dapat berbeda jika FastTrack atau HW offload aktif."
            ),
        )

        plan.simulation_results = sim_result.to_dict()
        return sim_result
