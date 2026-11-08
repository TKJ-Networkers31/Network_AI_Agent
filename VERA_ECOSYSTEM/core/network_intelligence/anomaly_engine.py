"""
AIRA OS — Resource-Efficient Network Anomaly Intelligence Engine (Networking VI / WP 6.6).

Detects and explains anomalies across device resources, interface utilization, traffic rates,
error/drop counter acceleration, and routing/protocol stability using `BaselineEngine`
(Rolling Median, MAD, EWMA) and deterministic domain thresholds.

Key Epistemic Rules:
- Never treats `None` missing telemetry as `0.0`.
- Never creates baseline-deviation anomalies from insufficient/invalidated baselines.
- Never labels benign traffic spikes as faults (`is_fault_candidate = False` when traffic
  increases without accompanying errors, packet drops, saturation >= 90%, or loss).
- Provides complete 9-point operational explanations for every `AnomalyObservation`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
import uuid

from core.network_intelligence.baseline_engine import BaselineEngine
from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    AnomalyObservation,
    MetricBaselineRecord,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph

MAD_SCALE_CONSTANT = 1.4826

# Minimum dispersion floors to prevent division-by-zero on flat constant series
METRIC_DISPERSION_FLOORS: Dict[str, float] = {
    "cpu_load_percent": 4.0,
    "memory_used_percent": 3.0,
    "latency_ms": 2.5,
    "packet_loss_percent": 0.5,
    "rx_utilization_percent": 5.0,
    "tx_utilization_percent": 5.0,
    "rx_rate_bps": 250_000.0,
    "tx_rate_bps": 250_000.0,
    "active_route_count": 1.0,
    "error_drop_delta": 2.0,
}


class AnomalyEngine:
    """Deterministic statistical & domain anomaly detector over `NetworkEvidenceBundle`."""

    def __init__(self, baseline_engine: Optional[BaselineEngine] = None) -> None:
        self.baseline_engine = baseline_engine or BaselineEngine()

    @staticmethod
    def compute_robust_zscore(value: float, baseline: MetricBaselineRecord) -> float:
        floor = METRIC_DISPERSION_FLOORS.get(baseline.metric_name, 1.0)
        scaled_mad = max(MAD_SCALE_CONSTANT * baseline.mad_value, floor)
        return (value - baseline.median_value) / scaled_mad

    def detect_anomalies(
        self,
        bundle: NetworkEvidenceBundle,
        graph: Optional[NetworkKnowledgeGraph] = None,
        update_baselines_after: bool = False,
        now: Optional[float] = None,
    ) -> List[AnomalyObservation]:
        curr_ts = float(now) if now is not None else time.time()
        qengine = GraphQueryEngine(graph) if graph is not None else None
        anomalies: List[AnomalyObservation] = []

        for dev_id, dinfo in bundle.device_evidence.items():
            obs_ts = float(dinfo.get("last_check_at") or bundle.assembled_at)
            dev_key = f"device:{dev_id}"
            dev_ev_ids = [r.evidence_id for r in bundle.records_for_device(dev_id, "device_resources")]
            if_ev_ids = [r.evidence_id for r in bundle.records_for_device(dev_id, "interfaces")]
            rt_ev_ids = [r.evidence_id for r in bundle.records_for_device(dev_id, "routes")]

            affected_downstream: List[str] = []
            if qengine is not None:
                dep_res = qengine.get_downstream_dependencies(dev_id, max_depth=4)
                affected_downstream = [d["device_id"] for d in dep_res["all_dependents"]]

            dev_pkt_loss = dinfo.get("packet_loss_percent")
            dev_latency = dinfo.get("latency_ms")

            # ------------------------------------------------------------------
            # 1. Device Resource & WAN Quality Anomalies (CPU, Memory, Latency, Loss)
            # ------------------------------------------------------------------
            for mname, label_id in (
                ("cpu_load_percent", "Beban CPU"),
                ("memory_used_percent", "Penggunaan Memori"),
                ("latency_ms", "Latensi Probe"),
                ("packet_loss_percent", "Packet Loss"),
            ):
                val = dinfo.get(mname)
                if val is None:
                    continue
                fval = float(val)
                b_rec = self.baseline_engine.get_baseline(dev_id, dev_key, mname)

                if b_rec and b_rec.status == "ACTIVE":
                    z = self.compute_robust_zscore(fval, b_rec)
                    # Rate-of-change vs EWMA check
                    ewma_jump = fval - b_rec.ewma_value
                    if z >= 3.5 or (mname == "cpu_load_percent" and fval >= 85.0 and ewma_jump >= 25.0):
                        anom_type = (
                            "RATE_OF_CHANGE"
                            if abs(ewma_jump) > 2.0 * abs(b_rec.ewma_value - b_rec.median_value) + 20.0
                            else "BASELINE_DEVIATION"
                        )
                        sev = "critical" if (z >= 6.0 or (mname == "packet_loss_percent" and fval >= 10.0) or (mname == "cpu_load_percent" and fval >= 95.0)) else "warning"
                        # High CPU alone without loss/incidents is a potential risk, whereas packet loss / extreme CPU is a fault candidate
                        is_fault = bool(
                            mname in ("packet_loss_percent", "latency_ms")
                            or fval >= 90.0
                            or (dev_pkt_loss is not None and float(dev_pkt_loss) > 1.0)
                        )
                        anomalies.append(
                            AnomalyObservation(
                                anomaly_id=f"anom_{dev_id}_{mname[:6]}_{uuid.uuid4().hex[:6]}",
                                device_id=dev_id,
                                interface_name=None,
                                entity_key=dev_key,
                                metric_name=mname,
                                anomaly_type=anom_type,
                                severity=sev,
                                is_fault_candidate=is_fault,
                                what_changed=(
                                    f"{label_id} pada '{dev_id}' meningkat ke {fval:.2f} "
                                    f"(baseline median={b_rec.median_value:.2f}, MAD={b_rec.mad_value:.2f}, z={z:.2f})."
                                ),
                                began_at=obs_ts,
                                detected_at=curr_ts,
                                observed_value=fval,
                                baseline_reference=b_rec.to_dict(),
                                unusualness_score=abs(z),
                                evidence_ids=list(dev_ev_ids),
                                potentially_affected=list(affected_downstream),
                                additional_evidence_needed=[
                                    "Profil proses RouterOS (`/tool profile` tidak dieksekusi otomatis) atau pengecekan trafik kontrol/firewall."
                                ] if mname == "cpu_load_percent" else [
                                    "Uji kualitas link upstream dan antrean interface keluar."
                                ],
                            )
                        )
                else:
                    # Without an active baseline, only flag extreme hard operational thresholds honestly
                    if mname == "packet_loss_percent" and fval >= 5.0:
                        anomalies.append(
                            AnomalyObservation(
                                anomaly_id=f"anom_{dev_id}_loss_{uuid.uuid4().hex[:6]}",
                                device_id=dev_id,
                                interface_name=None,
                                entity_key=dev_key,
                                metric_name=mname,
                                anomaly_type="RATE_OF_CHANGE",
                                severity="critical" if fval >= 20.0 else "warning",
                                is_fault_candidate=True,
                                what_changed=f"Packet loss terukur {fval:.1f}% pada '{dev_id}' (belum ada baseline historis aktif).",
                                began_at=obs_ts,
                                detected_at=curr_ts,
                                observed_value=fval,
                                baseline_reference=b_rec.to_dict() if b_rec else None,
                                unusualness_score=fval / 2.5,
                                evidence_ids=list(dev_ev_ids),
                                potentially_affected=list(affected_downstream),
                                additional_evidence_needed=["Sampel historis tambahan untuk baseline adaptif dan cek error interface fisik."],
                            )
                        )

            # ------------------------------------------------------------------
            # 2. Interface Traffic, Utilization & Error Acceleration Anomalies
            # ------------------------------------------------------------------
            for iface in bundle.interface_evidence.get(dev_id, []):
                iname = str(iface.get("interface_name") or "")
                if not iname:
                    continue
                if_key = f"iface:{dev_id}:{iname}"
                if_ts = float(iface.get("last_counter_update") or obs_ts)

                in_err = int(iface.get("in_errors") or 0) if iface.get("in_errors") is not None else None
                out_err = int(iface.get("out_errors") or 0) if iface.get("out_errors") is not None else None
                in_drp = int(iface.get("in_drops") or 0) if iface.get("in_drops") is not None else None
                out_drp = int(iface.get("out_drops") or 0) if iface.get("out_drops") is not None else None
                has_local_errors_or_drops = any(v is not None and v > 0 for v in (in_err, out_err, in_drp, out_drp))
                has_loss_context = has_local_errors_or_drops or (dev_pkt_loss is not None and float(dev_pkt_loss) > 0.5)

                # A) Traffic rate / utilization spike evaluation (with NON-FAULT spike guard!)
                for rate_metric, is_util in (
                    ("rx_utilization_percent", True),
                    ("tx_utilization_percent", True),
                    ("rx_rate_bps", False),
                    ("tx_rate_bps", False),
                ):
                    rval = iface.get(rate_metric)
                    if rval is None:
                        continue
                    frval = float(rval)
                    b_rate = self.baseline_engine.get_baseline(dev_id, if_key, rate_metric)
                    if b_rate and b_rate.status == "ACTIVE":
                        z_r = self.compute_robust_zscore(frval, b_rate)
                        if z_r >= 3.5:
                            saturated = is_util and frval >= 90.0
                            # CRITICAL RULE (Section 11.5): Do NOT label every traffic spike as a fault!
                            is_fault_spike = bool(saturated or has_loss_context)
                            sev = "critical" if (saturated and has_loss_context) else ("warning" if is_fault_spike else "info")
                            anom_t = "UTILIZATION_DEVIATION" if is_util else "TRAFFIC_PATTERN_DEVIATION"
                            qual_note = (
                                "Disertai indikasi saturasi/error/drop sehingga berpotensi mengganggu layanan."
                                if is_fault_spike
                                else "Lonjakan volume trafik tanpa disertai error, drop, atau packet loss (bukan kandidat gangguan/fault otomatis)."
                            )
                            anomalies.append(
                                AnomalyObservation(
                                    anomaly_id=f"anom_{dev_id}_{iname}_{rate_metric[:5]}_{uuid.uuid4().hex[:6]}",
                                    device_id=dev_id,
                                    interface_name=iname,
                                    entity_key=if_key,
                                    metric_name=rate_metric,
                                    anomaly_type=anom_t,
                                    severity=sev,
                                    is_fault_candidate=is_fault_spike,
                                    what_changed=(
                                        f"Metrik {rate_metric} pada {dev_id}:{iname} mencapai {frval:.2f} "
                                        f"(baseline median={b_rate.median_value:.2f}, z={z_r:.2f}). {qual_note}"
                                    ),
                                    began_at=if_ts,
                                    detected_at=curr_ts,
                                    observed_value=frval,
                                    baseline_reference=b_rate.to_dict(),
                                    unusualness_score=abs(z_r),
                                    evidence_ids=list(if_ev_ids),
                                    potentially_affected=list(affected_downstream),
                                    additional_evidence_needed=[
                                        f"Periksa counter queue/QoS dan distribusi sesi pada antarmuka {dev_id}:{iname}."
                                    ],
                                )
                            )

                # B) Error / Drop Counter Acceleration
                non_null_errs = [float(v) for v in (in_err, out_err, in_drp, out_drp) if v is not None]
                if non_null_errs:
                    err_sum = sum(non_null_errs)
                    b_err = self.baseline_engine.get_baseline(dev_id, if_key, "error_drop_delta")
                    if err_sum >= 25.0:
                        z_e = self.compute_robust_zscore(err_sum, b_err) if (b_err and b_err.status == "ACTIVE") else (err_sum / 10.0)
                        if z_e >= 3.0:
                            anomalies.append(
                                AnomalyObservation(
                                    anomaly_id=f"anom_{dev_id}_{iname}_err_{uuid.uuid4().hex[:6]}",
                                    device_id=dev_id,
                                    interface_name=iname,
                                    entity_key=if_key,
                                    metric_name="error_drop_counters",
                                    anomaly_type="ERROR_ACCELERATION",
                                    severity="critical" if err_sum >= 250.0 else "warning",
                                    is_fault_candidate=True,
                                    what_changed=(
                                        f"Akumulasi error/drop pada {dev_id}:{iname} meningkat "
                                        f"(in_err={in_err}, out_err={out_err}, in_drop={in_drp}, out_drop={out_drp})."
                                    ),
                                    began_at=if_ts,
                                    detected_at=curr_ts,
                                    observed_value=err_sum,
                                    baseline_reference=b_err.to_dict() if b_err else None,
                                    unusualness_score=float(z_e),
                                    evidence_ids=list(if_ev_ids),
                                    potentially_affected=list(affected_downstream),
                                    additional_evidence_needed=[
                                        f"Cek negosiasi duplex, redaman SFP/kabel fisik, dan MTU pada {dev_id}:{iname}."
                                    ],
                                )
                            )

            # ------------------------------------------------------------------
            # 3. Routing & Protocol Instability Anomalies
            # ------------------------------------------------------------------
            routes = bundle.routing_evidence.get(dev_id)
            if routes is not None:
                active_cnt = float(sum(1 for r in routes if r.active and not r.disabled))
                b_rt = self.baseline_engine.get_baseline(dev_id, dev_key, "active_route_count")
                if b_rt and b_rt.status == "ACTIVE" and b_rt.median_value >= 2.0:
                    z_rt = self.compute_robust_zscore(active_cnt, b_rt)
                    if z_rt <= -3.0 and active_cnt < b_rt.median_value:
                        anomalies.append(
                            AnomalyObservation(
                                anomaly_id=f"anom_{dev_id}_routes_{uuid.uuid4().hex[:6]}",
                                device_id=dev_id,
                                interface_name=None,
                                entity_key=dev_key,
                                metric_name="active_route_count",
                                anomaly_type="PROTOCOL_INSTABILITY",
                                severity="critical" if active_cnt == 0 else "warning",
                                is_fault_candidate=True,
                                what_changed=(
                                    f"Jumlah rute aktif pada '{dev_id}' turun dari baseline {b_rt.median_value:.0f} "
                                    f"menjadi {active_cnt:.0f} (z={z_rt:.2f})."
                                ),
                                began_at=obs_ts,
                                detected_at=curr_ts,
                                observed_value=active_cnt,
                                baseline_reference=b_rt.to_dict(),
                                unusualness_score=abs(z_rt),
                                evidence_ids=list(rt_ev_ids),
                                potentially_affected=list(affected_downstream),
                                additional_evidence_needed=[
                                    f"Periksa status sesi OSPF/BGP dan antarmuka transit pada '{dev_id}'."
                                ],
                            )
                        )

            pdata = bundle.protocol_evidence.get(dev_id) or {}
            for bp in pdata.get("bgp_peers") or []:
                if isinstance(bp, dict):
                    st = str(bp.get("state") or "").lower()
                    flaps = int(bp.get("flap_count") or bp.get("updates_withdrawn") or 0)
                    if (st and st not in ("established", "up") and not bp.get("established")) or flaps >= 5:
                        peer_ip = str(bp.get("remote_address") or bp.get("name") or "peer")
                        bgp_ev = [r.evidence_id for r in bundle.records_for_device(dev_id, "bgp_peers")]
                        anomalies.append(
                            AnomalyObservation(
                                anomaly_id=f"anom_{dev_id}_bgp_{uuid.uuid4().hex[:6]}",
                                device_id=dev_id,
                                interface_name=None,
                                entity_key=f"bgp_peer:{dev_id}:{peer_ip}",
                                metric_name="bgp_peer_stability",
                                anomaly_type="PROTOCOL_INSTABILITY",
                                severity="critical" if st not in ("established", "up") else "warning",
                                is_fault_candidate=True,
                                what_changed=f"Ketidakstabilan BGP peer {peer_ip} pada '{dev_id}' (state='{st or 'unknown'}', flaps={flaps}).",
                                began_at=obs_ts,
                                detected_at=curr_ts,
                                observed_value=float(flaps if flaps else 1.0),
                                baseline_reference=None,
                                unusualness_score=5.0 if st not in ("established", "up") else float(flaps),
                                evidence_ids=bgp_ev,
                                potentially_affected=list(affected_downstream),
                                additional_evidence_needed=["Periksa hold-timer, keterjangkauan TCP:179, dan log BGP peer."],
                            )
                        )

        # Cross-link correlated anomalies occurring across shared devices/time windows
        if len(anomalies) >= 2:
            for i, a in enumerate(anomalies):
                peers = [
                    b.anomaly_id
                    for j, b in enumerate(anomalies)
                    if i != j and (b.device_id == a.device_id or b.device_id in a.potentially_affected or a.device_id in b.potentially_affected)
                ]
                if peers:
                    a.is_correlated = True
                    a.correlated_with = peers[:10]

        if update_baselines_after:
            self.baseline_engine.update_from_bundle(bundle)

        return anomalies
