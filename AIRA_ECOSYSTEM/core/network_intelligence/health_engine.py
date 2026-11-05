"""
AIRA OS — Transparent Multi-Dimensional Network Health Engine (Networking VI / WP 6.6).

Evaluates 8 explicit health dimensions (`overall`, `device`, `interface`, `routing`,
`protocol`, `wan`, `dependency`, `telemetry_confidence`) backed by 12 operational sub-factors.

Non-Negotiable Epistemic Rules:
- Never collapses network state into a single opaque number.
- Never treats missing (`None`) metrics as `0.0` (neither penalizes nor inflates health).
- Explicitly distinguishes `HEALTHY`, `DEGRADED`, `CRITICAL`, `UNKNOWN`, and `INSUFFICIENT_DATA`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    AnomalyObservation,
    DimensionHealthScore,
    GraphEntityType,
    HealthStatus,
    IntelligenceFreshness,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph


def _status_from_score(score: Optional[float], force_critical: bool = False) -> str:
    if score is None:
        return HealthStatus.INSUFFICIENT_DATA.value
    if force_critical or score < 55.0:
        return HealthStatus.CRITICAL.value
    if score < 85.0:
        return HealthStatus.DEGRADED.value
    return HealthStatus.HEALTHY.value


class NetworkHealthEngine:
    """Transparent 8-dimension network health evaluator."""

    def evaluate_health(
        self,
        bundle: NetworkEvidenceBundle,
        graph: NetworkKnowledgeGraph,
        anomalies: Optional[List[AnomalyObservation]] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        curr_ts = float(now) if now is not None else time.time()
        qengine = GraphQueryEngine(graph)

        if not bundle.device_evidence:
            empty_dims = {
                dim: DimensionHealthScore(
                    dimension=dim,
                    status=HealthStatus.UNKNOWN.value,
                    score=None,
                    reasons=["Tidak ada bukti perangkat yang tersedia pada cakupan ini."],
                ).to_dict()
                for dim in (
                    "overall",
                    "device",
                    "interface",
                    "routing",
                    "protocol",
                    "wan",
                    "dependency",
                    "telemetry_confidence",
                )
            }
            return {
                "evaluated_at": curr_ts,
                "overall_status": HealthStatus.UNKNOWN.value,
                "overall_score": None,
                "dimensions": empty_dims,
                "device_health": {},
                "degraded_devices": [],
                "critical_devices": [],
            }

        # ------------------------------------------------------------------
        # 1. Per-Device Health & Device Dimension
        # ------------------------------------------------------------------
        dev_scores: List[float] = []
        dev_missing = 0
        dev_reasons: List[str] = []
        dev_ev_ids: List[str] = []
        per_device_health: Dict[str, Dict[str, Any]] = {}
        degraded_devices: List[str] = []
        critical_devices: List[str] = []

        open_inc_by_dev: Dict[str, int] = {}
        for inc in bundle.incident_evidence:
            if str(inc.get("status") or "open").lower() in ("open", "active", "acknowledged"):
                did = str(inc.get("device_id") or "")
                open_inc_by_dev[did] = open_inc_by_dev.get(did, 0) + 1

        for dev_id, dinfo in bundle.device_evidence.items():
            reach = str(dinfo.get("reachability_status") or "UNKNOWN").upper()
            cpu = dinfo.get("cpu_load_percent")
            mem = dinfo.get("memory_used_percent")
            drecs = bundle.records_for_device(dev_id, "device_resources")
            dev_ev_ids.extend([r.evidence_id for r in drecs])

            if reach == "UNKNOWN" and cpu is None and mem is None:
                dev_missing += 1
                per_device_health[dev_id] = {
                    "device_id": dev_id,
                    "status": HealthStatus.UNKNOWN.value,
                    "score": None,
                    "reasons": ["Status keterjangkauan dan metrik resource belum tersedia."],
                }
                continue

            d_reasons: List[str] = []
            if reach in ("DOWN", "UNREACHABLE", "SUSPECTED_DOWN"):
                d_score = 10.0
                d_reasons.append(f"Perangkat '{dev_id}' berstatus {reach}.")
            elif reach == "MONITORING_UNAVAILABLE":
                d_score = 65.0
                d_reasons.append(f"Probe ICMP ke '{dev_id}' berhasil namun sesi manajemen tidak tersedia.")
            elif reach == "DEGRADED":
                d_score = 70.0
                d_reasons.append(f"Keterjangkauan '{dev_id}' terdegradasi.")
            else:
                d_score = 100.0

            # CPU & memory pressure ONLY evaluated if measured (None is ignored, NEVER treated as 0.0!)
            if cpu is not None:
                fcpu = float(cpu)
                if fcpu >= 92.0:
                    d_score -= 30.0
                    d_reasons.append(f"Tekanan CPU tinggi ({fcpu:.1f}%).")
                elif fcpu >= 80.0:
                    d_score -= 15.0
                    d_reasons.append(f"Beban CPU meningkat ({fcpu:.1f}%).")
            if mem is not None:
                fmem = float(mem)
                if fmem >= 92.0:
                    d_score -= 25.0
                    d_reasons.append(f"Tekanan memori tinggi ({fmem:.1f}%).")
                elif fmem >= 82.0:
                    d_score -= 10.0
                    d_reasons.append(f"Penggunaan memori meningkat ({fmem:.1f}%).")

            inc_cnt = open_inc_by_dev.get(dev_id, 0)
            if inc_cnt > 0:
                d_score -= min(20.0, 8.0 * inc_cnt)
                d_reasons.append(f"{inc_cnt} insiden aktif tercatat pada '{dev_id}'.")

            d_score = max(0.0, min(100.0, d_score))
            d_status = _status_from_score(d_score, force_critical=(reach in ("DOWN", "UNREACHABLE")))
            if d_status == HealthStatus.CRITICAL.value:
                critical_devices.append(dev_id)
            elif d_status == HealthStatus.DEGRADED.value:
                degraded_devices.append(dev_id)
            dev_scores.append(d_score)
            dev_reasons.extend(d_reasons[:2])
            per_device_health[dev_id] = {
                "device_id": dev_id,
                "status": d_status,
                "score": round(d_score, 2),
                "reachability_status": reach,
                "cpu_load_percent": cpu,
                "memory_used_percent": mem,
                "reasons": d_reasons or ["Keterjangkauan dan resource perangkat normal."],
            }

        dim_device = DimensionHealthScore(
            dimension="device",
            status=(
                HealthStatus.UNKNOWN.value
                if not dev_scores and dev_missing > 0
                else _status_from_score(
                    sum(dev_scores) / len(dev_scores) if dev_scores else None,
                    force_critical=(len(critical_devices) > 0 and len(critical_devices) >= max(1, len(dev_scores) // 2)),
                )
            ),
            score=(sum(dev_scores) / len(dev_scores)) if dev_scores else None,
            measured_entities=len(dev_scores),
            missing_entities=dev_missing,
            reasons=dev_reasons[:5] or (["Seluruh perangkat terukur dalam kondisi sehat."] if dev_scores else ["Belum ada data metrik perangkat."]),
            evidence_ids=list(dict.fromkeys(dev_ev_ids)),
        )
        if critical_devices and dim_device.status == HealthStatus.HEALTHY.value:
            dim_device.status = HealthStatus.DEGRADED.value

        # ------------------------------------------------------------------
        # 2. Interface Dimension (oper_status, utilization, error/drop trends)
        # ------------------------------------------------------------------
        if_scores: List[float] = []
        if_missing = 0
        if_reasons: List[str] = []
        if_ev_ids: List[str] = []

        for dev_id, iflist in bundle.interface_evidence.items():
            if not iflist:
                if_missing += 1
                continue
            if_ev_ids.extend([r.evidence_id for r in bundle.records_for_device(dev_id, "interfaces")])
            for iface in iflist:
                admin = str(iface.get("admin_status") or "enabled").lower()
                if admin == "disabled":
                    continue
                oper = str(iface.get("oper_status") or "unknown").lower()
                iname = str(iface.get("interface_name") or "iface")
                if oper == "unknown":
                    if_missing += 1
                    continue
                iscore = 100.0 if oper == "up" else 25.0
                if oper != "up":
                    if_reasons.append(f"Antarmuka enabled {dev_id}:{iname} berstatus '{oper}'.")

                for ucol in ("rx_utilization_percent", "tx_utilization_percent"):
                    uval = iface.get(ucol)
                    if uval is not None:
                        fu = float(uval)
                        if fu >= 92.0:
                            iscore -= 25.0
                            if_reasons.append(f"Saturasi tinggi pada {dev_id}:{iname} ({ucol}={fu:.1f}%).")
                        elif fu >= 80.0:
                            iscore -= 10.0

                errs = [int(iface[k]) for k in ("in_errors", "out_errors", "in_drops", "out_drops") if iface.get(k) is not None]
                if errs and sum(errs) >= 20:
                    iscore -= min(35.0, 15.0 + sum(errs) / 25.0)
                    if_reasons.append(f"Error/drop terdeteksi pada {dev_id}:{iname} (total={sum(errs)}).")

                if_scores.append(max(0.0, min(100.0, iscore)))

        dim_interface = DimensionHealthScore(
            dimension="interface",
            status=_status_from_score(sum(if_scores) / len(if_scores) if if_scores else None),
            score=(sum(if_scores) / len(if_scores)) if if_scores else None,
            measured_entities=len(if_scores),
            missing_entities=if_missing,
            reasons=if_reasons[:5] or (["Antarmuka aktif beroperasi normal."] if if_scores else ["Data antarmuka belum dikumpulkan."]),
            evidence_ids=list(dict.fromkeys(if_ev_ids)),
        )

        # ------------------------------------------------------------------
        # 3. Routing Dimension (RIB presence, active routes, unreachable/inactive ratios)
        # ------------------------------------------------------------------
        rt_scores: List[float] = []
        rt_missing = 0
        rt_reasons: List[str] = []
        rt_ev_ids: List[str] = []

        for dev_id in bundle.device_evidence:
            routes = bundle.routing_evidence.get(dev_id) or []
            if not routes:
                rt_missing += 1
                continue
            rt_ev_ids.extend([r.evidence_id for r in bundle.records_for_device(dev_id, "routes")])
            active_routes = [r for r in routes if r.active and not r.disabled]
            unreach_routes = [r for r in routes if (not r.active or r.unreachable) and not r.disabled]
            rscore = 100.0
            if not active_routes:
                rscore = 20.0
                rt_reasons.append(f"Perangkat '{dev_id}' tidak memiliki rute aktif di RIB.")
            elif unreach_routes:
                penalty = min(40.0, 12.0 * len(unreach_routes))
                rscore -= penalty
                rt_reasons.append(f"{len(unreach_routes)} rute pada '{dev_id}' tidak aktif/unreachable.")
            rt_scores.append(max(0.0, rscore))

        dim_routing = DimensionHealthScore(
            dimension="routing",
            status=_status_from_score(sum(rt_scores) / len(rt_scores) if rt_scores else None),
            score=(sum(rt_scores) / len(rt_scores)) if rt_scores else None,
            measured_entities=len(rt_scores),
            missing_entities=rt_missing,
            reasons=rt_reasons[:5] or (["Tabel routing terukur stabil."] if rt_scores else ["Belum ada snapshot/bukti RIB yang tersedia."]),
            evidence_ids=list(dict.fromkeys(rt_ev_ids)),
        )

        # ------------------------------------------------------------------
        # 4. Protocol Dimension (OSPF / BGP / Tunnels — INSUFFICIENT_DATA if none configured/collected)
        # ------------------------------------------------------------------
        proto_scores: List[float] = []
        proto_missing = 0
        proto_reasons: List[str] = []
        proto_ev_ids: List[str] = []

        for dev_id, pdata in bundle.protocol_evidence.items():
            for onb in pdata.get("ospf_neighbors") or []:
                if isinstance(onb, dict):
                    proto_ev_ids.extend([r.evidence_id for r in bundle.records_for_device(dev_id, "ospf_neighbors")])
                    st = str(onb.get("state") or "").lower()
                    if "full" in st or "2-way" in st:
                        proto_scores.append(100.0)
                    else:
                        proto_scores.append(30.0)
                        proto_reasons.append(f"OSPF neighbor {onb.get('neighbor_id') or onb.get('address')} pada '{dev_id}' berstatus '{onb.get('state')}'.")
            for bp in pdata.get("bgp_peers") or []:
                if isinstance(bp, dict):
                    proto_ev_ids.extend([r.evidence_id for r in bundle.records_for_device(dev_id, "bgp_peers")])
                    st = str(bp.get("state") or "").lower()
                    if st in ("established", "up") or bp.get("established") is True:
                        proto_scores.append(100.0)
                    else:
                        proto_scores.append(25.0)
                        proto_reasons.append(f"BGP peer {bp.get('remote_address') or bp.get('name')} pada '{dev_id}' berstatus '{bp.get('state')}'.")

        if not proto_scores:
            proto_missing = len(bundle.device_evidence)

        dim_protocol = DimensionHealthScore(
            dimension="protocol",
            status=_status_from_score(sum(proto_scores) / len(proto_scores) if proto_scores else None),
            score=(sum(proto_scores) / len(proto_scores)) if proto_scores else None,
            measured_entities=len(proto_scores),
            missing_entities=proto_missing,
            reasons=proto_reasons[:5] or (["Adjacency protokol dinamis sehat."] if proto_scores else ["Tidak ada observasi sesi protokol dinamis (OSPF/BGP) yang terukur."]),
            evidence_ids=list(dict.fromkeys(proto_ev_ids)),
        )

        # ------------------------------------------------------------------
        # 5. WAN Quality Dimension (WAN nodes + latency/packet loss where WAN exists)
        # ------------------------------------------------------------------
        wan_nodes = graph.nodes_by_type(GraphEntityType.WAN_CONNECTION.value)
        wan_dev_ids = sorted({w.device_id for w in wan_nodes if w.device_id})
        wan_scores: List[float] = []
        wan_missing = 0
        wan_reasons: List[str] = []
        wan_ev_ids: List[str] = []

        for wdev in wan_dev_ids:
            dinfo = bundle.device_evidence.get(wdev, {})
            wan_ev_ids.extend([r.evidence_id for r in bundle.records_for_device(wdev, "device_resources")])
            reach = str(dinfo.get("reachability_status") or "UNKNOWN").upper()
            lat = dinfo.get("latency_ms")
            loss = dinfo.get("packet_loss_percent")
            if reach == "UNKNOWN" and lat is None and loss is None:
                wan_missing += 1
                continue
            wscore = 100.0 if reach in ("UP", "DEGRADED") else 15.0
            if reach not in ("UP", "DEGRADED"):
                wan_reasons.append(f"Gateway WAN '{wdev}' berstatus {reach}.")
            if lat is not None and float(lat) >= 100.0:
                wscore -= 25.0 if float(lat) >= 180.0 else 15.0
                wan_reasons.append(f"Latensi gateway WAN '{wdev}' tinggi ({float(lat):.1f} ms).")
            if loss is not None and float(loss) >= 2.0:
                wscore -= 35.0 if float(loss) >= 10.0 else 20.0
                wan_reasons.append(f"Packet loss gateway WAN '{wdev}' sebesar {float(loss):.1f}%.")
            wan_scores.append(max(0.0, wscore))

        dim_wan = DimensionHealthScore(
            dimension="wan",
            status=_status_from_score(sum(wan_scores) / len(wan_scores) if wan_scores else None),
            score=(sum(wan_scores) / len(wan_scores)) if wan_scores else None,
            measured_entities=len(wan_scores),
            missing_entities=wan_missing if wan_dev_ids else len(bundle.device_evidence),
            reasons=wan_reasons[:5] or (["Kualitas gateway WAN normal."] if wan_scores else ["Tidak ada rute/koneksi WAN terukur pada cakupan saat ini."]),
            evidence_ids=list(dict.fromkeys(wan_ev_ids)),
        )

        # ------------------------------------------------------------------
        # 6. Dependency Health Dimension (Health of critical upstream hubs)
        # ------------------------------------------------------------------
        dep_scores: List[float] = []
        dep_reasons: List[str] = []
        critical_hubs: List[Dict[str, Any]] = []
        for dev_id in bundle.device_evidence:
            down = qengine.get_downstream_dependencies(dev_id, max_depth=4)
            dep_cnt = len(down["all_dependents"])
            if dep_cnt > 0:
                d_h = per_device_health.get(dev_id, {})
                sc = d_h.get("score")
                critical_hubs.append({"device_id": dev_id, "dependent_count": dep_cnt, "status": d_h.get("status", "UNKNOWN")})
                if sc is not None:
                    dep_scores.append(float(sc))
                    if float(sc) < 85.0:
                        dep_reasons.append(f"Perangkat transit '{dev_id}' ({dep_cnt} dependen) berstatus {d_h.get('status')}.")

        dim_dependency = DimensionHealthScore(
            dimension="dependency",
            status=_status_from_score(sum(dep_scores) / len(dep_scores) if dep_scores else (dim_device.score if dim_device.score is not None else None)),
            score=(sum(dep_scores) / len(dep_scores)) if dep_scores else dim_device.score,
            measured_entities=len(dep_scores),
            missing_entities=0 if dep_scores or dim_device.score is not None else len(bundle.device_evidence),
            reasons=dep_reasons[:5] or (["Simpul ketergantungan transit beroperasi sehat."] if dep_scores else ["Tidak ditemukan degradasi ketergantungan lintas perangkat."]),
            evidence_ids=list(dict.fromkeys(dev_ev_ids)),
        )

        # ------------------------------------------------------------------
        # 7. Telemetry Confidence Dimension
        # ------------------------------------------------------------------
        total_recs = len(bundle.records)
        fresh_aging = (
            bundle.freshness_summary.get(IntelligenceFreshness.FRESH.value, 0)
            + bundle.freshness_summary.get(IntelligenceFreshness.AGING.value, 0)
        )
        tel_reasons: List[str] = []
        if total_recs == 0:
            tel_score: Optional[float] = None
            tel_reasons.append("Tidak ada rekaman bukti yang berhasil dikumpulkan.")
        else:
            fresh_ratio = fresh_aging / total_recs
            tel_score = 100.0 * fresh_ratio
            if bundle.collection_gaps:
                gap_pen = min(40.0, 8.0 * len(bundle.collection_gaps))
                tel_score -= gap_pen
                tel_reasons.append(f"{len(bundle.collection_gaps)} celah pengumpulan bukti (collection gap) terdeteksi.")
            if bundle.contradictions:
                contra_pen = min(30.0, 10.0 * len(bundle.contradictions))
                tel_score -= contra_pen
                tel_reasons.append(f"{len(bundle.contradictions)} kontradiksi antar-sumber bukti terdeteksi.")
            if fresh_ratio < 1.0:
                tel_reasons.append(f"{total_recs - fresh_aging} dari {total_recs} rekaman bukti berstatus STALE/EXPIRED/UNKNOWN.")
            tel_score = max(0.0, min(100.0, tel_score))

        dim_telemetry = DimensionHealthScore(
            dimension="telemetry_confidence",
            status=_status_from_score(tel_score),
            score=tel_score,
            measured_entities=total_recs,
            missing_entities=len(bundle.collection_gaps),
            reasons=tel_reasons or ["Seluruh rekaman bukti segar (FRESH/AGING) tanpa kontradiksi."],
            evidence_ids=[r.evidence_id for r in bundle.records[:12]],
        )

        # ------------------------------------------------------------------
        # 8. Overall Transparent Synthesis (Only across MEASURED dimensions!)
        # ------------------------------------------------------------------
        weights = {
            "device": (dim_device, 0.28),
            "interface": (dim_interface, 0.20),
            "routing": (dim_routing, 0.18),
            "protocol": (dim_protocol, 0.12),
            "wan": (dim_wan, 0.12),
            "dependency": (dim_dependency, 0.10),
        }
        w_num = 0.0
        w_den = 0.0
        overall_reasons: List[str] = []
        any_critical_dim = False
        for dname, (dobj, w) in weights.items():
            if dobj.score is not None:
                w_num += dobj.score * w
                w_den += w
                if dobj.status == HealthStatus.CRITICAL.value:
                    any_critical_dim = True
                    overall_reasons.append(f"Dimensi '{dname}' berstatus CRITICAL ({dobj.score:.1f}).")
                elif dobj.status == HealthStatus.DEGRADED.value:
                    overall_reasons.append(f"Dimensi '{dname}' berstatus DEGRADED ({dobj.score:.1f}).")

        fault_anomalies = [a for a in (anomalies or []) if a.is_fault_candidate]
        if w_den == 0.0:
            ov_score: Optional[float] = None
            ov_status = HealthStatus.UNKNOWN.value
            overall_reasons.append("Data telemetri belum mencukupi untuk menghitung kesehatan jaringan.")
        else:
            ov_score = w_num / w_den
            if fault_anomalies:
                ov_score = max(0.0, ov_score - min(15.0, 4.0 * len(fault_anomalies)))
                overall_reasons.append(f"{len(fault_anomalies)} anomali kandidat gangguan aktif.")
            ov_status = _status_from_score(ov_score, force_critical=any_critical_dim and ov_score < 70.0)
            if any_critical_dim and ov_status == HealthStatus.HEALTHY.value:
                ov_status = HealthStatus.DEGRADED.value

        dim_overall = DimensionHealthScore(
            dimension="overall",
            status=ov_status,
            score=ov_score,
            measured_entities=sum(1 for dobj, _ in weights.values() if dobj.score is not None),
            missing_entities=sum(1 for dobj, _ in weights.values() if dobj.score is None),
            reasons=overall_reasons or ["Seluruh dimensi jaringan yang terukur berada dalam kondisi sehat."],
            evidence_ids=list(dict.fromkeys((dev_ev_ids + if_ev_ids + rt_ev_ids)[:15])),
        )

        dimensions_dict = {
            "overall": dim_overall.to_dict(),
            "device": dim_device.to_dict(),
            "interface": dim_interface.to_dict(),
            "routing": dim_routing.to_dict(),
            "protocol": dim_protocol.to_dict(),
            "wan": dim_wan.to_dict(),
            "dependency": dim_dependency.to_dict(),
            "telemetry_confidence": dim_telemetry.to_dict(),
        }

        return {
            "evaluated_at": curr_ts,
            "overall_status": dim_overall.status,
            "overall_score": round(dim_overall.score, 2) if dim_overall.score is not None else None,
            "dimensions": dimensions_dict,
            "device_health": per_device_health,
            "degraded_devices": degraded_devices,
            "critical_devices": critical_devices,
            "critical_dependencies": sorted(critical_hubs, key=lambda x: -x["dependent_count"]),
        }
