"""
AIRA OS — Network Path Intelligence Engine (Networking VI / WP 6.3).

Reconstructs, classifies, explains, and compares multi-device traffic paths across
RouterOS v6/v7 and multi-vendor normalized evidence.

Supported Epistemic Modes (`PathReasoningMode`):
- `RIB_INFERRED`: Control-plane LPM + recursive gateway + L2/L3 next-hop resolution (never claimed as packet trace).
- `FIB_CONFIRMED`: Every hop carries explicit FIB / hardware-offload verification and UP egress interface.
- `OBSERVED_FORWARDING`: Corroborated by direct data-plane observations (traceroute / probe hops).
- `PARTIAL_PATH`: Initial hop(s) resolved, followed by external gateway, missing RIB, down interface, or unresolved gateway.
- `UNKNOWN_PATH`: Insufficient evidence or no matching route on starting device.
"""

from __future__ import annotations

import ipaddress
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import uuid

from core.network_intelligence.intelligence_models import (
    ConfidenceLabel,
    IntelligenceFreshness,
    NetworkEvidenceBundle,
    PathAnalysisResult,
    PathHopExplanation,
    PathReasoningMode,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.routing.route_analytics import evaluate_route_lookup
from core.routing.unified_route_parser import (
    NextHopResolutionStatus,
    NormalizedRoute,
    RouteType,
    resolve_recursive_next_hop,
)
from core.topology_models import normalize_ip

MAX_PATH_HOPS = 16


def _is_route_fib_verified(route: NormalizedRoute) -> bool:
    flags = route.raw_flags or ""
    if "H" in flags:
        return True
    if route.selected is True:
        return True
    fib_attr = route.raw_attributes.get("fib")
    if isinstance(fib_attr, bool):
        return fib_attr
    if str(fib_attr or "").lower() in ("true", "yes", "1"):
        return True
    return False


class NetworkPathIntelligenceEngine:
    """
    Deterministic multi-hop path reasoning & comparison engine built atop
    `UnifiedRouteParser`, `evaluate_route_lookup`, `resolve_recursive_next_hop`,
    `NetworkEvidenceBundle`, and `NetworkKnowledgeGraph`.
    """

    def analyze_path(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        destination_ip: str,
        source_device_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        destination_device_id: Optional[str] = None,
        routing_table: str = "main",
        vrf: Optional[str] = None,
    ) -> PathAnalysisResult:
        path_id = f"path_{uuid.uuid4().hex[:10]}"
        eff_table = (vrf or routing_table or "main").strip()
        eff_vrf = (vrf or eff_table or "main").strip()
        dst_str = (destination_ip or "").strip()

        # Resolve source_device_id from source_ip if omitted
        start_dev = (source_device_id or "").strip() or None
        if not start_dev and source_ip:
            owner, _, _ = graph.resolver.resolve_peer_by_ip(source_ip)
            start_dev = owner

        if not start_dev and dst_str:
            # Default to first managed device with routes if single-router scope
            for cand in bundle.selected_devices:
                if bundle.routing_evidence.get(cand):
                    start_dev = cand
                    break

        if not start_dev or start_dev not in bundle.device_evidence:
            return PathAnalysisResult(
                path_id=path_id,
                source_device_id=start_dev,
                source_ip=source_ip,
                destination_ip=dst_str,
                destination_device_id=destination_device_id,
                routing_table=eff_table,
                vrf=eff_vrf,
                mode=PathReasoningMode.UNKNOWN_PATH.value,
                outcome="INSUFFICIENT_EVIDENCE",
                is_directly_observed=False,
                missing_evidence=["Perangkat sumber tidak ditemukan atau belum memiliki bukti inventaris/RIB."],
                confidence_label=ConfidenceLabel.INSUFFICIENT.value,
                confidence_score=0.15,
                explanation="Jalur tidak dapat dianalisis karena perangkat awal tidak teridentifikasi di bundle bukti.",
            )

        # Validate destination IP / CIDR (IPv4 or IPv6)
        dst_ip_obj: Optional[ipaddress._BaseAddress] = None
        dst_net_obj: Optional[ipaddress._BaseNetwork] = None
        try:
            if "/" in dst_str:
                dst_net_obj = ipaddress.ip_network(dst_str, strict=False)
                dst_ip_obj = (
                    ipaddress.ip_address(int(dst_net_obj.network_address) + 1)
                    if dst_net_obj.num_addresses > 2
                    else dst_net_obj.network_address
                )
            else:
                dst_ip_obj = ipaddress.ip_address(dst_str)
        except ValueError:
            return PathAnalysisResult(
                path_id=path_id,
                source_device_id=start_dev,
                source_ip=source_ip,
                destination_ip=dst_str,
                destination_device_id=destination_device_id,
                routing_table=eff_table,
                vrf=eff_vrf,
                mode=PathReasoningMode.UNKNOWN_PATH.value,
                outcome="INSUFFICIENT_EVIDENCE",
                is_directly_observed=False,
                missing_evidence=[f"Format alamat/prefix tujuan '{dst_str}' tidak valid."],
                confidence_label=ConfidenceLabel.INSUFFICIENT.value,
                confidence_score=0.10,
                explanation=f"Tujuan '{dst_str}' bukan alamat IP atau prefix CIDR yang valid.",
            )

        if dst_ip_obj.version == 6:
            return self._analyze_ipv6_path(
                bundle=bundle,
                graph=graph,
                path_id=path_id,
                start_dev=start_dev,
                source_ip=source_ip,
                dst_str=dst_str,
                dst_ip_obj=dst_ip_obj,
                destination_device_id=destination_device_id,
                eff_table=eff_table,
                eff_vrf=eff_vrf,
            )

        # Resolve destination_device_id if known IP belongs to an inventory device
        target_dev = destination_device_id
        if not target_dev:
            owner, _, _ = graph.resolver.resolve_peer_by_ip(str(dst_ip_obj))
            target_dev = owner

        hops: List[PathHopExplanation] = []
        visited_devs: List[str] = []
        all_ev_ids: List[str] = []
        missing_ev: List[str] = []
        candidate_paths: List[List[str]] = []
        outcome = "INCOMPLETE"
        curr_dev: Optional[str] = start_dev
        curr_table = eff_table
        all_hops_fib = True
        any_stale = False

        # Check for direct observed forwarding telemetry (traceroute / packet probe) on start_dev
        fwd_obs = (bundle.protocol_evidence.get(start_dev) or {}).get("forwarding_observations") or {}
        observed_hops_list: List[str] = []
        if isinstance(fwd_obs, dict):
            obs_entry = fwd_obs.get(dst_str) or fwd_obs.get(str(dst_ip_obj))
            if isinstance(obs_entry, dict) and obs_entry.get("verified") is True:
                observed_hops_list = [str(h) for h in obs_entry.get("hops") or []]

        for hop_idx in range(1, MAX_PATH_HOPS + 1):
            if curr_dev is None:
                break
            if curr_dev in visited_devs:
                outcome = "LOOP_DETECTED"
                if hops:
                    hops[-1].warnings.append(f"Loop routing terdeteksi kembali ke perangkat {curr_dev}.")
                break
            visited_devs.append(curr_dev)

            dev_info = bundle.device_evidence.get(curr_dev, {})
            dev_name = str(dev_info.get("display_name") or curr_dev)
            dev_routes = bundle.routing_evidence.get(curr_dev) or []
            route_recs = bundle.records_for_device(curr_dev, "routes")
            for rr in route_recs:
                if rr.evidence_id not in all_ev_ids:
                    all_ev_ids.append(rr.evidence_id)
                if rr.freshness in (IntelligenceFreshness.STALE.value, IntelligenceFreshness.EXPIRED.value):
                    any_stale = True

            if not dev_routes:
                missing_ev.append(f"Tabel routing (RIB) untuk perangkat '{curr_dev}' tidak tersedia.")
                if hop_idx == 1:
                    return PathAnalysisResult(
                        path_id=path_id,
                        source_device_id=start_dev,
                        source_ip=source_ip,
                        destination_ip=dst_str,
                        destination_device_id=target_dev,
                        routing_table=eff_table,
                        vrf=eff_vrf,
                        mode=PathReasoningMode.UNKNOWN_PATH.value,
                        outcome="INSUFFICIENT_EVIDENCE",
                        is_directly_observed=False,
                        missing_evidence=missing_ev,
                        evidence_ids=all_ev_ids,
                        confidence_label=ConfidenceLabel.INSUFFICIENT.value,
                        confidence_score=0.20,
                        explanation=f"Data tabel routing pada perangkat awal '{curr_dev}' tidak tersedia.",
                    )
                outcome = "PARTIAL_MISSING_RIB"
                break

            # Run LPM evaluation on current hop
            lpm = evaluate_route_lookup(
                dev_routes,
                dst_str,
                device_id=curr_dev,
                routing_table=curr_table,
            )

            # Check if only inactive/disabled routes matched
            table_routes = [r for r in dev_routes if (r.routing_table or "main") == curr_table]
            if not lpm.matched:
                # Inspect whether an inactive or blackhole/unreachable route covers destination
                covering_special = [
                    r for r in table_routes
                    if r.network is not None and dst_ip_obj in r.network
                ]
                covering_special.sort(key=lambda x: (-x.prefix_len, x.distance))
                if covering_special:
                    top_sp = covering_special[0]
                    sp_type = top_sp.route_type.value if hasattr(top_sp.route_type, "value") else str(top_sp.route_type)
                    if sp_type in ("blackhole", "prohibit", "reject", "unreachable") or top_sp.unreachable:
                        fib_ok = _is_route_fib_verified(top_sp)
                        all_hops_fib = all_hops_fib and fib_ok
                        hops.append(
                            PathHopExplanation(
                                hop_index=hop_idx,
                                device_id=curr_dev,
                                device_name=dev_name,
                                routing_table=curr_table,
                                vrf=eff_vrf,
                                matched_prefix=top_sp.dst_prefix,
                                selected_route_summary=f"{top_sp.dst_prefix} ({sp_type}, distance={top_sp.distance})",
                                selection_reason=f"Matched {sp_type} discard route via LPM (/{top_sp.prefix_len}).",
                                administrative_distance=top_sp.distance,
                                protocol=top_sp.protocol,
                                next_hop_resolution=f"DISCARD_{sp_type.upper()}",
                                fib_confirmed=fib_ok,
                                evidence_ids=[r.evidence_id for r in route_recs],
                                warnings=[f"Trafik dihentikan oleh rute {sp_type} pada {curr_dev}."],
                            )
                        )
                        outcome = "BLACKHOLED" if sp_type == "blackhole" else "UNREACHABLE"
                        break
                    else:
                        hops.append(
                            PathHopExplanation(
                                hop_index=hop_idx,
                                device_id=curr_dev,
                                device_name=dev_name,
                                routing_table=curr_table,
                                vrf=eff_vrf,
                                matched_prefix=top_sp.dst_prefix,
                                selected_route_summary=f"{top_sp.dst_prefix} via {top_sp.gateway} (INACTIVE)",
                                selection_reason="Hanya rute tidak aktif/disabled yang cocok; tidak memenuhi syarat forwarding.",
                                administrative_distance=top_sp.distance,
                                protocol=top_sp.protocol,
                                next_hop_ip=top_sp.gateway,
                                next_hop_resolution="INACTIVE_ROUTE",
                                fib_confirmed=False,
                                evidence_ids=[r.evidence_id for r in route_recs],
                                warnings=list(lpm.warnings) + ["Rute kandidat berstatus tidak aktif (inactive/disabled)."],
                            )
                        )
                        all_hops_fib = False
                        outcome = "UNREACHABLE"
                        break

                # No route at all in curr_table
                other_tables = sorted({r.routing_table or "main" for r in dev_routes if (r.routing_table or "main") != curr_table})
                warn_msg = f"Tidak ada rute aktif di tabel '{curr_table}' menuju {dst_str}."
                if other_tables:
                    warn_msg += f" (Rute ditemukan pada VRF/tabel lain: {', '.join(other_tables)})."
                missing_ev.append(warn_msg)
                outcome = "UNREACHABLE" if hop_idx > 1 else "NO_ROUTE"
                break

            # Select best active route(s) from table_routes matching the LPM winner prefix/distance
            best_dicts = lpm.calculated_best_candidates
            best_pfx = best_dicts[0].get("dst_prefix") if best_dicts else None
            best_dist = best_dicts[0].get("distance") if best_dicts else None
            winning_routes = [
                r for r in table_routes
                if r.active and not r.disabled and not r.unreachable
                and r.dst_prefix == best_pfx and r.distance == best_dist
            ]
            if not winning_routes:
                winning_routes = [r for r in table_routes if r.active and not r.disabled and r.network and dst_ip_obj in r.network]
                winning_routes.sort(key=lambda x: (-x.prefix_len, x.distance))

            sel_route = winning_routes[0]
            fib_ok = all(_is_route_fib_verified(wr) for wr in winning_routes)
            all_hops_fib = all_hops_fib and fib_ok

            # Build selection reason explaining LPM specificity + administrative distance + ECMP
            alt_candidates = [
                r for r in table_routes
                if r.active and not r.disabled and r.network and dst_ip_obj in r.network and r is not sel_route
            ]
            reason_parts = [f"LPM terpanjang /{sel_route.prefix_len} ({sel_route.dst_prefix})"]
            reason_parts.append(f"administrative distance {sel_route.distance} ({sel_route.protocol})")
            if alt_candidates:
                less_spec = [a.dst_prefix for a in alt_candidates if a.prefix_len < sel_route.prefix_len]
                higher_dist = [f"{a.protocol}(d={a.distance})" for a in alt_candidates if a.prefix_len == sel_route.prefix_len and a.distance > sel_route.distance]
                if less_spec:
                    reason_parts.append(f"mengalahkan prefix lebih umum {', '.join(less_spec[:2])}")
                if higher_dist:
                    reason_parts.append(f"mengalahkan distance lebih tinggi {', '.join(higher_dist[:2])}")
            if lpm.is_ecmp or len(lpm.ecmp_gateways) > 1:
                reason_parts.append(f"ECMP aktif melalui {len(lpm.ecmp_gateways)} gateway ({', '.join(lpm.ecmp_gateways)})")

            # Recursive next-hop resolution
            gw_target_str = str(sel_route.immediate_gw or sel_route.gateway or "").split(",")[0].strip()
            rec_res = resolve_recursive_next_hop(gw_target_str, table_routes, max_depth=16)
            rec_chain = [str(step) for step in getattr(rec_res, "resolution_chain", []) or []]
            res_status = getattr(rec_res, "status", None)
            loop_flag = bool(getattr(rec_res, "loop_detected", False))

            if res_status in (NextHopResolutionStatus.DIRECTLY_CONNECTED, NextHopResolutionStatus.RECURSIVE_RESOLVED):
                resolved_gw = getattr(rec_res, "resolved_ip", None) or gw_target_str
                resolved_iface = getattr(rec_res, "egress_interface", None) or sel_route.interface_name
                res_status_str = res_status.value
                next_hop_unresolved = False
            elif loop_flag:
                resolved_gw = gw_target_str
                resolved_iface = sel_route.interface_name
                res_status_str = "RECURSIVE_LOOP"
                next_hop_unresolved = True
            else:
                # Check if route already binds an interface_name or matches a configured local IP subnet
                local_if_match = sel_route.interface_name
                if not local_if_match and gw_target_str:
                    try:
                        gw_ip_obj = ipaddress.ip_address(gw_target_str.split("%")[0])
                        for ip_entry in (bundle.protocol_evidence.get(curr_dev) or {}).get("ip_addresses") or []:
                            if isinstance(ip_entry, dict) and "/" in str(ip_entry.get("address") or ""):
                                net_cand = ipaddress.ip_network(str(ip_entry["address"]), strict=False)
                                if gw_ip_obj in net_cand:
                                    local_if_match = str(ip_entry.get("interface") or ip_entry.get("interface_name") or "") or None
                                    break
                    except ValueError:
                        pass
                if local_if_match:
                    resolved_gw = gw_target_str
                    resolved_iface = local_if_match
                    res_status_str = "DIRECT_INTERFACE_BOUND"
                    next_hop_unresolved = False
                else:
                    resolved_gw = gw_target_str
                    resolved_iface = None
                    res_status_str = res_status.value if hasattr(res_status, "value") else "UNRESOLVED"
                    next_hop_unresolved = True

            # Check egress interface operational status
            egress_oper = "unknown"
            hop_warnings: List[str] = list(lpm.warnings)
            for iface in bundle.interface_evidence.get(curr_dev, []):
                if iface.get("interface_name") == resolved_iface:
                    egress_oper = str(iface.get("oper_status") or "unknown").lower()
                    break
            if egress_oper in ("down", "disabled"):
                hop_warnings.append(f"Antarmuka keluar '{resolved_iface}' berstatus {egress_oper}!")
                all_hops_fib = False

            # Connected route or local IP delivery check
            if sel_route.connect or (target_dev and curr_dev == target_dev):
                hops.append(
                    PathHopExplanation(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        device_name=dev_name,
                        routing_table=curr_table,
                        vrf=eff_vrf,
                        matched_prefix=sel_route.dst_prefix,
                        selected_route_summary=f"{sel_route.dst_prefix} connected on {resolved_iface or 'local'}",
                        selection_reason="; ".join(reason_parts),
                        administrative_distance=sel_route.distance,
                        protocol=sel_route.protocol,
                        next_hop_ip=None,
                        next_hop_resolution="DIRECT_CONNECTED",
                        recursive_chain=rec_chain,
                        egress_interface=resolved_iface,
                        egress_oper_status=egress_oper,
                        next_device_id=target_dev if target_dev != curr_dev else None,
                        ecmp_gateways=list(lpm.ecmp_gateways),
                        fib_confirmed=fib_ok and egress_oper not in ("down", "disabled"),
                        observed_forwarding=bool(observed_hops_list),
                        evidence_ids=[r.evidence_id for r in route_recs],
                        warnings=hop_warnings,
                    )
                )
                outcome = "EGRESS_DOWN" if egress_oper in ("down", "disabled") else "DELIVERED"
                break

            # Unresolved recursive / next-hop check
            if next_hop_unresolved:
                hop_warnings.append(f"Next-hop '{sel_route.gateway}' gagal di-resolve ({res_status_str}).")
                hops.append(
                    PathHopExplanation(
                        hop_index=hop_idx,
                        device_id=curr_dev,
                        device_name=dev_name,
                        routing_table=curr_table,
                        vrf=eff_vrf,
                        matched_prefix=sel_route.dst_prefix,
                        selected_route_summary=f"{sel_route.dst_prefix} via {sel_route.gateway}",
                        selection_reason="; ".join(reason_parts),
                        administrative_distance=sel_route.distance,
                        protocol=sel_route.protocol,
                        next_hop_ip=sel_route.gateway,
                        next_hop_resolution=res_status_str,
                        recursive_chain=rec_chain,
                        egress_interface=resolved_iface,
                        egress_oper_status=egress_oper,
                        ecmp_gateways=list(lpm.ecmp_gateways),
                        fib_confirmed=False,
                        evidence_ids=[r.evidence_id for r in route_recs],
                        warnings=hop_warnings,
                    )
                )
                all_hops_fib = False
                outcome = "LOOP_DETECTED" if loop_flag else "UNRESOLVED_NEXT_HOP"
                break

            # Resolve next device from resolved_gw
            clean_gw = normalize_ip(str(resolved_gw or "").split("%")[0].strip())
            next_dev, _, peer_reason = graph.resolver.resolve_peer_by_ip(clean_gw or "", exclude_device_id=curr_dev)

            # Track ECMP candidate branches on first hop
            if len(lpm.ecmp_gateways) > 1:
                for egw in lpm.ecmp_gateways:
                    egw_clean = normalize_ip(egw.split("%")[0].strip())
                    b_dev, _, _ = graph.resolver.resolve_peer_by_ip(egw_clean or "", exclude_device_id=curr_dev)
                    candidate_paths.append([curr_dev, b_dev or f"gw:{egw_clean}"])

            hops.append(
                PathHopExplanation(
                    hop_index=hop_idx,
                    device_id=curr_dev,
                    device_name=dev_name,
                    routing_table=curr_table,
                    vrf=eff_vrf,
                    matched_prefix=sel_route.dst_prefix,
                    selected_route_summary=f"{sel_route.dst_prefix} via {resolved_gw or sel_route.gateway}",
                    selection_reason="; ".join(reason_parts),
                    administrative_distance=sel_route.distance,
                    protocol=sel_route.protocol,
                    next_hop_ip=clean_gw or sel_route.gateway,
                    next_hop_resolution=res_status_str,
                    recursive_chain=rec_chain,
                    egress_interface=resolved_iface,
                    egress_oper_status=egress_oper,
                    next_device_id=next_dev,
                    ecmp_gateways=list(lpm.ecmp_gateways),
                    fib_confirmed=fib_ok and egress_oper not in ("down", "disabled"),
                    observed_forwarding=(clean_gw in observed_hops_list) if clean_gw else False,
                    evidence_ids=[r.evidence_id for r in route_recs],
                    warnings=hop_warnings,
                )
            )

            if egress_oper in ("down", "disabled"):
                outcome = "EGRESS_DOWN"
                break

            if next_dev is None:
                missing_ev.append(
                    f"Gateway berikutnya '{clean_gw or sel_route.gateway}' ({peer_reason}) berada di luar inventaris terkelola; visibilitas berhenti pada batas ini."
                )
                outcome = "PARTIAL_EXTERNAL"
                break

            # Advance to next device (in main table unless same VRF exists on peer)
            peer_routes = bundle.routing_evidence.get(next_dev) or []
            peer_tables = {r.routing_table or "main" for r in peer_routes}
            curr_table = curr_table if curr_table in peer_tables else "main"
            curr_dev = next_dev

        if not candidate_paths and hops:
            chain = [h.device_id for h in hops]
            if hops[-1].next_device_id and hops[-1].next_device_id not in chain:
                chain.append(hops[-1].next_device_id)
            candidate_paths.append(chain)

        # Asymmetric return path check when both start_dev and target_dev have RIBs and source_ip is known
        asym_detected: Optional[bool] = None
        asym_notes = ""
        eff_src_ip = source_ip
        if not eff_src_ip:
            eff_src_ip = (bundle.device_evidence.get(start_dev) or {}).get("management_ip") or None
        end_dev = target_dev or (hops[-1].device_id if len(hops) >= 2 else None)
        if outcome == "DELIVERED" and end_dev and end_dev != start_dev and eff_src_ip and bundle.routing_evidence.get(end_dev):
            ret_hops_devs = self._trace_simple_device_sequence(bundle, graph, end_dev, eff_src_ip, eff_table)
            fwd_devs = [h.device_id for h in hops]
            if end_dev not in fwd_devs:
                fwd_devs.append(end_dev)
            if ret_hops_devs:
                if list(reversed(ret_hops_devs)) != fwd_devs:
                    asym_detected = True
                    asym_notes = (
                        f"Potensi routing asimetris pada RIB: jalur maju ({' -> '.join(fwd_devs)}) "
                        f"berbeda dengan jalur balik ({' -> '.join(ret_hops_devs)})."
                    )
                else:
                    asym_detected = False
                    asym_notes = "Jalur maju dan balik simetris berdasarkan RIB yang tersedia."

        # Determine final PathReasoningMode strictly according to epistemic rules
        is_observed = False
        if not hops:
            mode = PathReasoningMode.UNKNOWN_PATH.value
            conf_score, conf_lbl = 0.20, ConfidenceLabel.INSUFFICIENT.value
        elif outcome in ("PARTIAL_EXTERNAL", "PARTIAL_MISSING_RIB", "UNRESOLVED_NEXT_HOP", "EGRESS_DOWN", "LOOP_DETECTED"):
            mode = PathReasoningMode.PARTIAL_PATH.value
            conf_score = 0.55 if outcome == "PARTIAL_EXTERNAL" else 0.45
            conf_lbl = ConfidenceLabel.MODERATE.value if conf_score >= 0.50 else ConfidenceLabel.LOW.value
        elif outcome in ("BLACKHOLED", "UNREACHABLE"):
            mode = PathReasoningMode.RIB_INFERRED.value
            conf_score, conf_lbl = 0.78, ConfidenceLabel.HIGH.value
        elif observed_hops_list and outcome == "DELIVERED":
            mode = PathReasoningMode.OBSERVED_FORWARDING.value
            is_observed = True
            conf_score, conf_lbl = 0.92, ConfidenceLabel.VERY_HIGH.value
        elif all_hops_fib and outcome == "DELIVERED":
            mode = PathReasoningMode.FIB_CONFIRMED.value
            conf_score, conf_lbl = 0.86, ConfidenceLabel.VERY_HIGH.value
        else:
            mode = PathReasoningMode.RIB_INFERRED.value
            conf_score, conf_lbl = 0.76, ConfidenceLabel.HIGH.value

        if any_stale:
            conf_score = max(0.30, conf_score - 0.18)
            conf_lbl = ConfidenceLabel.MODERATE.value if conf_score >= 0.50 else ConfidenceLabel.LOW.value

        hop_chain_str = " -> ".join(h.device_name for h in hops)
        mode_note = (
            "Terverifikasi observasi forwarding langsung."
            if is_observed
            else "Diturunkan secara deterministik dari tabel kontrol (RIB/FIB); bukan rekaman paket aktual."
        )
        explanation = (
            f"Mode={mode}, Outcome={outcome} untuk tujuan {dst_str} dari {start_dev} (tabel '{eff_table}'): "
            f"Jalur={hop_chain_str or 'tidak ada'}. {mode_note}"
        )

        return PathAnalysisResult(
            path_id=path_id,
            source_device_id=start_dev,
            source_ip=eff_src_ip,
            destination_ip=dst_str,
            destination_device_id=target_dev,
            routing_table=eff_table,
            vrf=eff_vrf,
            mode=mode,
            outcome=outcome,
            is_directly_observed=is_observed,
            hops=hops,
            candidate_paths=candidate_paths,
            asymmetric_return_detected=asym_detected,
            asymmetric_notes=asym_notes,
            missing_evidence=missing_ev,
            evidence_ids=all_ev_ids,
            confidence_label=conf_lbl,
            confidence_score=conf_score,
            explanation=explanation,
        )

    def _trace_simple_device_sequence(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        start_dev: str,
        dst_ip: str,
        table: str,
    ) -> List[str]:
        seq: List[str] = []
        curr: Optional[str] = start_dev
        for _ in range(MAX_PATH_HOPS):
            if not curr or curr in seq:
                break
            seq.append(curr)
            routes = bundle.routing_evidence.get(curr) or []
            if not routes:
                break
            lpm = evaluate_route_lookup(routes, dst_ip, device_id=curr, routing_table=table)
            if not lpm.matched or not lpm.calculated_best_candidates:
                break
            top = lpm.calculated_best_candidates[0]
            if top.get("connect"):
                break
            gw = normalize_ip(str(top.get("immediate_gw") or top.get("gateway") or "").split("%")[0].strip())
            if not gw:
                break
            nxt, _, _ = graph.resolver.resolve_peer_by_ip(gw, exclude_device_id=curr)
            if not nxt:
                break
            curr = nxt
        return seq

    def _analyze_ipv6_path(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        path_id: str,
        start_dev: str,
        source_ip: Optional[str],
        dst_str: str,
        dst_ip_obj: ipaddress._BaseAddress,
        destination_device_id: Optional[str],
        eff_table: str,
        eff_vrf: str,
    ) -> PathAnalysisResult:
        """Evaluates IPv6 paths when explicit `ipv6_routes` evidence is present; otherwise reports missing IPv6 RIB."""
        pdata = bundle.protocol_evidence.get(start_dev) or {}
        v6_routes = pdata.get("ipv6_routes") or []
        if not v6_routes:
            return PathAnalysisResult(
                path_id=path_id,
                source_device_id=start_dev,
                source_ip=source_ip,
                destination_ip=dst_str,
                destination_device_id=destination_device_id,
                routing_table=eff_table,
                vrf=eff_vrf,
                mode=PathReasoningMode.UNKNOWN_PATH.value,
                outcome="INSUFFICIENT_EVIDENCE",
                is_directly_observed=False,
                missing_evidence=[
                    "Bukti tabel routing IPv6 (`ipv6_routes`) tidak tersedia (perintah `/ipv6 route print` berada di luar allowlist CLI live saat ini)."
                ],
                confidence_label=ConfidenceLabel.INSUFFICIENT.value,
                confidence_score=0.15,
                explanation="Analisis jalur IPv6 membutuhkan data `ipv6_routes` yang tervalidasi.",
            )

        matched: List[Tuple[int, int, Dict[str, Any]]] = []
        for r in v6_routes:
            if not isinstance(r, dict) or not r.get("active", True) or r.get("disabled"):
                continue
            if (r.get("routing_table") or "main") != eff_table:
                continue
            try:
                net = ipaddress.ip_network(str(r.get("dst_prefix") or "::/0"), strict=False)
                if net.version == 6 and dst_ip_obj in net:
                    matched.append((net.prefixlen, int(r.get("distance", 1)), r))
            except ValueError:
                continue

        if not matched:
            return PathAnalysisResult(
                path_id=path_id,
                source_device_id=start_dev,
                source_ip=source_ip,
                destination_ip=dst_str,
                destination_device_id=destination_device_id,
                routing_table=eff_table,
                vrf=eff_vrf,
                mode=PathReasoningMode.RIB_INFERRED.value,
                outcome="UNREACHABLE",
                is_directly_observed=False,
                confidence_label=ConfidenceLabel.MODERATE.value,
                confidence_score=0.65,
                explanation=f"Tidak ada rute IPv6 aktif pada {start_dev} tabel '{eff_table}' yang mencakup {dst_str}.",
            )

        matched.sort(key=lambda item: (-item[0], item[1]))
        plen, dist, win = matched[0]
        ev_recs = bundle.records_for_device(start_dev, "ipv6_routes")
        hop = PathHopExplanation(
            hop_index=1,
            device_id=start_dev,
            device_name=str((bundle.device_evidence.get(start_dev) or {}).get("display_name") or start_dev),
            routing_table=eff_table,
            vrf=eff_vrf,
            matched_prefix=str(win.get("dst_prefix")),
            selected_route_summary=f"{win.get('dst_prefix')} via {win.get('gateway') or win.get('interface_name')}",
            selection_reason=f"IPv6 LPM /{plen}, distance {dist}",
            administrative_distance=dist,
            protocol=str(win.get("protocol") or "static"),
            next_hop_ip=win.get("gateway"),
            next_hop_resolution="CONNECTED" if win.get("connect") else "IPV6_NEXT_HOP",
            egress_interface=win.get("interface_name"),
            evidence_ids=[r.evidence_id for r in ev_recs],
        )
        mode = PathReasoningMode.RIB_INFERRED.value if win.get("connect") else PathReasoningMode.PARTIAL_PATH.value
        return PathAnalysisResult(
            path_id=path_id,
            source_device_id=start_dev,
            source_ip=source_ip,
            destination_ip=dst_str,
            destination_device_id=destination_device_id,
            routing_table=eff_table,
            vrf=eff_vrf,
            mode=mode,
            outcome="DELIVERED" if win.get("connect") else "PARTIAL_EXTERNAL",
            is_directly_observed=False,
            hops=[hop],
            candidate_paths=[[start_dev]],
            evidence_ids=[r.evidence_id for r in ev_recs],
            confidence_label=ConfidenceLabel.MODERATE.value,
            confidence_score=0.68,
            explanation=f"IPv6 LPM pada {start_dev} memilih {win.get('dst_prefix')} (mode={mode}).",
        )

    @staticmethod
    def compare_paths(
        path_a: PathAnalysisResult,
        path_b: PathAnalysisResult,
        comparison_dimension: str = "snapshot_comparison",
    ) -> Dict[str, Any]:
        """
        Compares two `PathAnalysisResult` objects across:
        - two source devices (`source_comparison`)
        - two destinations (`destination_comparison`)
        - two VRFs (`vrf_comparison`)
        - two routing tables (`table_comparison`)
        - current vs historical snapshots / before & after route change (`snapshot_comparison`)
        """
        devs_a = [h.device_id for h in path_a.hops]
        devs_b = [h.device_id for h in path_b.hops]
        pfxs_a = [h.matched_prefix for h in path_a.hops]
        pfxs_b = [h.matched_prefix for h in path_b.hops]
        nh_a = [h.next_hop_ip for h in path_a.hops]
        nh_b = [h.next_hop_ip for h in path_b.hops]

        differences: List[str] = []
        if path_a.mode != path_b.mode:
            differences.append(f"Mode penalaran berubah dari {path_a.mode} menjadi {path_b.mode}.")
        if path_a.outcome != path_b.outcome:
            differences.append(f"Hasil akhir jalur berubah dari {path_a.outcome} menjadi {path_b.outcome}.")
        if devs_a != devs_b:
            differences.append(f"Urutan hop perangkat berubah: {' -> '.join(devs_a) or 'kosong'} vs {' -> '.join(devs_b) or 'kosong'}.")
        if pfxs_a != pfxs_b:
            differences.append(f"Prefix LPM yang cocok berubah: {pfxs_a} vs {pfxs_b}.")
        if nh_a != nh_b:
            differences.append(f"Next-hop gateway berubah: {nh_a} vs {nh_b}.")

        return {
            "comparison_dimension": comparison_dimension,
            "identical_forwarding_intent": len(differences) == 0,
            "path_a": path_a.to_dict(),
            "path_b": path_b.to_dict(),
            "hop_sequence_a": devs_a,
            "hop_sequence_b": devs_b,
            "differences": differences,
            "difference_count": len(differences),
        }
