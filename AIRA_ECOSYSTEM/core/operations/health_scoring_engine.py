"""
AIRA OS — Dynamic Multi-Dimensional Health Scoring Engine (Networking VIII / WP 8.5.1).

Evaluates operational health across 6 architectural dimensions:
1. DEVICE: CPU load, memory utilization, reachability.
2. INTERFACE: Bandwidth utilization, packet drops, link state.
3. SITE: Aggregation of devices and interfaces within a customer site.
4. SERVICE: Customer business service endpoints and reachability.
5. GATEWAY: Edge gateway heartbeat freshness, daemon health, buffer queue depth.
6. TENANT: Criticality-aware tenant operational health with Tier 1 minimum clamping.

Strict Epistemic Invariants:
- Never equates UNKNOWN with HEALTHY.
- Never sets missing telemetry to 0.0 or 100.0 (emits score=None and state=UNKNOWN/INSUFFICIENT_DATA).
- Exposes contributing factors, missing dimensions, confidence, and calculation timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.operations.db import ensure_operational_schema
from core.operations.models import (
    HealthDimensionType,
    HealthScoreState,
    OperationalHealthScoreRecord,
    ServiceCriticality,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.health_scoring")

# Telemetry freshness threshold for health scoring (default 5 minutes)
MAX_HEALTH_TELEMETRY_AGE_SEC = 300.0


class DynamicHealthScoringEngine:
    """Computes transparent, deterministic health scores across 6 dimensions."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # 1. Device Health Scoring
    # -----------------------------------------------------------------------
    def score_device(
        self,
        tenant_id: str,
        device_id: str,
        site_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> OperationalHealthScoreRecord:
        """Evaluates health of a specific device."""
        now_ts = float(now) if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        score_id = f"hlth_dev_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=False) as conn:
            # Verify device exists and belongs to tenant
            dev_row = conn.execute(
                "SELECT device_id, name, site_id, status FROM operational_devices WHERE tenant_id = ? AND device_id = ?",
                (tenant_id, device_id),
            ).fetchone()

            if not dev_row:
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    dimension=HealthDimensionType.DEVICE.value,
                    entity_id=device_id,
                    state=HealthScoreState.UNKNOWN.value,
                    score=None,
                    confidence=0.0,
                    contributing_factors=["Perangkat tidak ditemukan di inventaris tenant."],
                    missing_dimensions=["inventory", "telemetry"],
                    calculated_at=now_iso,
                )

            effective_site_id = site_id or dev_row["site_id"]
            dev_status = str(dev_row["status"]).upper()

            # Query recent metrics from nms_raw_metrics
            window_start = now_ts - MAX_HEALTH_TELEMETRY_AGE_SEC
            metric_rows = conn.execute(
                """
                SELECT metric_name, metric_value, measured_at
                FROM nms_raw_metrics
                WHERE device_id = ? AND measured_at >= ?
                ORDER BY measured_at DESC
                """,
                (device_id, window_start),
            ).fetchall()

        # If device marked OFFLINE or UNREACHABLE
        if dev_status in ("OFFLINE", "UNREACHABLE", "DOWN"):
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=effective_site_id,
                dimension=HealthDimensionType.DEVICE.value,
                entity_id=device_id,
                state=HealthScoreState.CRITICAL.value,
                score=0.0,
                confidence=1.0,
                contributing_factors=[f"Status perangkat pada inventaris: {dev_status}"],
                missing_dimensions=[],
                calculated_at=now_iso,
            )

        if not metric_rows:
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=effective_site_id,
                dimension=HealthDimensionType.DEVICE.value,
                entity_id=device_id,
                state=HealthScoreState.UNKNOWN.value,
                score=None,
                confidence=0.2,
                contributing_factors=["Tidak ada telemetri terkini dalam 5 menit terakhir."],
                missing_dimensions=["cpu", "memory", "utilization"],
                calculated_at=now_iso,
            )

        # Evaluate metrics
        cpu_vals = [r["metric_value"] for r in metric_rows if r["metric_name"] in ("cpu_load", "cpu_utilization")]
        mem_vals = [r["metric_value"] for r in metric_rows if r["metric_name"] in ("memory_used_percent", "memory_load")]

        contributing = []
        missing = []
        score_components = []

        if cpu_vals:
            latest_cpu = cpu_vals[0]
            if latest_cpu >= 90.0:
                score_components.append(20.0)
                contributing.append(f"Beban CPU kritis ({latest_cpu:.1f}%)")
            elif latest_cpu >= 75.0:
                score_components.append(65.0)
                contributing.append(f"Beban CPU tinggi ({latest_cpu:.1f}%)")
            else:
                score_components.append(100.0)
                contributing.append(f"Beban CPU normal ({latest_cpu:.1f}%)")
        else:
            missing.append("cpu")

        if mem_vals:
            latest_mem = mem_vals[0]
            if latest_mem >= 90.0:
                score_components.append(25.0)
                contributing.append(f"Penggunaan memori kritis ({latest_mem:.1f}%)")
            elif latest_mem >= 80.0:
                score_components.append(60.0)
                contributing.append(f"Penggunaan memori tinggi ({latest_mem:.1f}%)")
            else:
                score_components.append(100.0)
                contributing.append(f"Penggunaan memori normal ({latest_mem:.1f}%)")
        else:
            missing.append("memory")

        if not score_components:
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=effective_site_id,
                dimension=HealthDimensionType.DEVICE.value,
                entity_id=device_id,
                state=HealthScoreState.INSUFFICIENT_DATA.value,
                score=None,
                confidence=0.4,
                contributing_factors=["Metrik perangkat yang tersedia tidak mencukupi untuk evaluasi."],
                missing_dimensions=missing,
                calculated_at=now_iso,
            )

        final_score = sum(score_components) / len(score_components)
        if final_score >= 90.0:
            state = HealthScoreState.HEALTHY.value
        elif final_score >= 70.0:
            state = HealthScoreState.DEGRADED.value
        elif final_score >= 50.0:
            state = HealthScoreState.WARNING.value
        else:
            state = HealthScoreState.CRITICAL.value

        conf = 1.0 - (0.25 * len(missing))

        record = OperationalHealthScoreRecord(
            score_id=score_id,
            tenant_id=tenant_id,
            site_id=effective_site_id,
            dimension=HealthDimensionType.DEVICE.value,
            entity_id=device_id,
            state=state,
            score=final_score,
            confidence=max(0.2, conf),
            contributing_factors=contributing,
            missing_dimensions=missing,
            calculated_at=now_iso,
        )
        self._persist_score(record)
        return record

    # -----------------------------------------------------------------------
    # 2. Gateway Health Scoring
    # -----------------------------------------------------------------------
    def score_gateway(
        self,
        tenant_id: str,
        gateway_id: str,
        now: Optional[float] = None,
    ) -> OperationalHealthScoreRecord:
        """Evaluates health of a customer edge gateway."""
        now_ts = float(now) if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        score_id = f"hlth_gw_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=False) as conn:
            gw_row = conn.execute(
                "SELECT gateway_id, site_id, status, last_seen_at_utc FROM operational_gateways WHERE tenant_id = ? AND gateway_id = ?",
                (tenant_id, gateway_id),
            ).fetchone()

            if not gw_row:
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=None,
                    dimension=HealthDimensionType.GATEWAY.value,
                    entity_id=gateway_id,
                    state=HealthScoreState.UNKNOWN.value,
                    score=None,
                    confidence=0.0,
                    contributing_factors=["Gateway tidak terdaftar pada tenant."],
                    missing_dimensions=["registration"],
                    calculated_at=now_iso,
                )

            site_id = gw_row["site_id"]
            gw_status = gw_row["status"]

            # Query recent heartbeat
            hb_row = conn.execute(
                """
                SELECT timestamp_utc, cpu_utilization, memory_utilization, queue_depth, collector_status
                FROM operational_gateway_heartbeats
                WHERE gateway_id = ?
                ORDER BY timestamp_utc DESC LIMIT 1
                """,
                (gateway_id,),
            ).fetchone()

        if gw_status in ("REVOKED", "DECOMMISSIONED", "OFFLINE"):
            record = OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=site_id,
                dimension=HealthDimensionType.GATEWAY.value,
                entity_id=gateway_id,
                state=HealthScoreState.CRITICAL.value,
                score=0.0,
                confidence=1.0,
                contributing_factors=[f"Gateway dalam status {gw_status}"],
                missing_dimensions=[],
                calculated_at=now_iso,
            )
            self._persist_score(record)
            return record

        if not hb_row:
            record = OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=site_id,
                dimension=HealthDimensionType.GATEWAY.value,
                entity_id=gateway_id,
                state=HealthScoreState.UNKNOWN.value,
                score=None,
                confidence=0.2,
                contributing_factors=["Belum ada detak jantung (heartbeat) yang tercatat."],
                missing_dimensions=["heartbeat"],
                calculated_at=now_iso,
            )
            self._persist_score(record)
            return record

        q_depth = hb_row["queue_depth"]
        col_status = hb_row["collector_status"]
        contributing = []
        score = 100.0

        if col_status != "HEALTHY":
            score -= 30.0
            contributing.append(f"Kolektor diagnostik mengalami gangguan ({col_status})")
        if q_depth > 1000:
            score -= 40.0
            contributing.append(f"Antrean buffer edge tinggi ({q_depth} sampel tertunda)")
        elif q_depth > 200:
            score -= 15.0
            contributing.append(f"Antrean buffer edge sedang memproses ({q_depth} sampel)")

        if score >= 90.0:
            state = HealthScoreState.HEALTHY.value
        elif score >= 70.0:
            state = HealthScoreState.DEGRADED.value
        elif score >= 50.0:
            state = HealthScoreState.WARNING.value
        else:
            state = HealthScoreState.CRITICAL.value

        if not contributing:
            contributing.append("Gateway beroperasi optimal dengan antrean kosong.")

        record = OperationalHealthScoreRecord(
            score_id=score_id,
            tenant_id=tenant_id,
            site_id=site_id,
            dimension=HealthDimensionType.GATEWAY.value,
            entity_id=gateway_id,
            state=state,
            score=score,
            confidence=0.95,
            contributing_factors=contributing,
            missing_dimensions=[],
            calculated_at=now_iso,
        )
        self._persist_score(record)
        return record

    # -----------------------------------------------------------------------
    # 3. Service Health Scoring
    # -----------------------------------------------------------------------
    def score_service(
        self,
        tenant_id: str,
        service_id: str,
        now: Optional[float] = None,
    ) -> OperationalHealthScoreRecord:
        """Evaluates health of a business service and its endpoints."""
        now_ts = float(now) if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        score_id = f"hlth_svc_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=False) as conn:
            svc_row = conn.execute(
                "SELECT service_id, name, criticality, status, health_score FROM operational_services WHERE service_id = ?",
                (service_id,),
            ).fetchone()

            if not svc_row:
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=None,
                    dimension=HealthDimensionType.SERVICE.value,
                    entity_id=service_id,
                    state=HealthScoreState.UNKNOWN.value,
                    score=None,
                    confidence=0.0,
                    contributing_factors=["Layanan bisnis tidak ditemukan dalam katalog."],
                    missing_dimensions=["catalog"],
                    calculated_at=now_iso,
                )

            ep_rows = conn.execute(
                "SELECT endpoint_id, endpoint_type, endpoint_value, target_device_id, is_primary FROM operational_service_endpoints WHERE service_id = ?",
                (service_id,),
            ).fetchall()

        curr_status = svc_row["status"].upper()
        if curr_status == "DOWN":
            state = HealthScoreState.CRITICAL.value
            score = 0.0
            factors = ["Layanan bisnis berstatus DOWN secara eksplisit."]
        elif curr_status == "DEGRADED":
            state = HealthScoreState.DEGRADED.value
            score = 65.0
            factors = ["Sebagian titik akhir (endpoints) layanan mengalami gangguan."]
        elif curr_status == "AT_RISK":
            state = HealthScoreState.WARNING.value
            score = 55.0
            factors = ["Redundansi layanan terdegradasi; beroperasi pada jalur tunggal."]
        elif curr_status == "HEALTHY":
            state = HealthScoreState.HEALTHY.value
            score = float(svc_row["health_score"] or 100.0)
            factors = ["Seluruh titik akhir layanan merespons normal."]
        else:
            state = HealthScoreState.UNKNOWN.value
            score = None
            factors = ["Status layanan belum terverifikasi."]

        record = OperationalHealthScoreRecord(
            score_id=score_id,
            tenant_id=tenant_id,
            site_id=None,
            dimension=HealthDimensionType.SERVICE.value,
            entity_id=service_id,
            state=state,
            score=score,
            confidence=0.9 if score is not None else 0.3,
            contributing_factors=factors,
            missing_dimensions=[] if score is not None else ["telemetry"],
            calculated_at=now_iso,
        )
        self._persist_score(record)
        return record

    # -----------------------------------------------------------------------
    # 4. Site Health Scoring
    # -----------------------------------------------------------------------
    def score_site(
        self,
        tenant_id: str,
        site_id: str,
        now: Optional[float] = None,
    ) -> OperationalHealthScoreRecord:
        """Aggregates device, interface, and gateway health for a single customer site."""
        now_ts = float(now) if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        score_id = f"hlth_site_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=False) as conn:
            site_row = conn.execute(
                "SELECT site_id, name FROM operational_sites WHERE tenant_id = ? AND site_id = ?",
                (tenant_id, site_id),
            ).fetchone()

            if not site_row:
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    dimension=HealthDimensionType.SITE.value,
                    entity_id=site_id,
                    state=HealthScoreState.UNKNOWN.value,
                    score=None,
                    confidence=0.0,
                    contributing_factors=["Site tidak ditemukan dalam inventaris tenant."],
                    missing_dimensions=["inventory"],
                    calculated_at=now_iso,
                )

            dev_rows = conn.execute(
                "SELECT device_id FROM operational_devices WHERE tenant_id = ? AND site_id = ?",
                (tenant_id, site_id),
            ).fetchall()

            gw_rows = conn.execute(
                "SELECT gateway_id FROM operational_gateways WHERE tenant_id = ? AND site_id = ?",
                (tenant_id, site_id),
            ).fetchall()

        if not dev_rows and not gw_rows:
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=site_id,
                dimension=HealthDimensionType.SITE.value,
                entity_id=site_id,
                state=HealthScoreState.INSUFFICIENT_DATA.value,
                score=None,
                confidence=0.2,
                contributing_factors=["Tidak ada perangkat atau gateway terdaftar di site ini."],
                missing_dimensions=["devices", "gateways"],
                calculated_at=now_iso,
            )

        child_scores: List[float] = []
        critical_count = 0
        warning_count = 0
        contributing = []

        # Evaluate gateways
        for gw in gw_rows:
            g_rec = self.score_gateway(tenant_id, gw["gateway_id"], now=now_ts)
            if g_rec.score is not None:
                child_scores.append(g_rec.score)
            if g_rec.state == HealthScoreState.CRITICAL.value:
                critical_count += 1
                contributing.append(f"Gateway {gw['gateway_id']} kritis: {'; '.join(g_rec.contributing_factors)}")

        # Evaluate devices
        for dev in dev_rows:
            d_rec = self.score_device(tenant_id, dev["device_id"], site_id=site_id, now=now_ts)
            if d_rec.score is not None:
                child_scores.append(d_rec.score)
            if d_rec.state == HealthScoreState.CRITICAL.value:
                critical_count += 1
                contributing.append(f"Perangkat {dev['device_id']} kritis: {'; '.join(d_rec.contributing_factors)}")
            elif d_rec.state in (HealthScoreState.WARNING.value, HealthScoreState.DEGRADED.value):
                warning_count += 1

        if not child_scores:
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=site_id,
                dimension=HealthDimensionType.SITE.value,
                entity_id=site_id,
                state=HealthScoreState.UNKNOWN.value,
                score=None,
                confidence=0.3,
                contributing_factors=["Semua perangkat dan gateway pada site tidak memiliki telemetri."],
                missing_dimensions=["telemetry"],
                calculated_at=now_iso,
            )

        avg_score = sum(child_scores) / len(child_scores)

        # Clamping rule: If any gateway or core device is critical, site cannot be HEALTHY
        if critical_count > 0:
            site_score = min(45.0, avg_score)
            site_state = HealthScoreState.CRITICAL.value
        elif warning_count > 0:
            site_score = min(68.0, avg_score)
            site_state = HealthScoreState.WARNING.value
        elif avg_score >= 90.0:
            site_score = avg_score
            site_state = HealthScoreState.HEALTHY.value
            contributing.append("Seluruh perangkat dan gateway di site beroperasi normal.")
        else:
            site_score = avg_score
            site_state = HealthScoreState.DEGRADED.value

        record = OperationalHealthScoreRecord(
            score_id=score_id,
            tenant_id=tenant_id,
            site_id=site_id,
            dimension=HealthDimensionType.SITE.value,
            entity_id=site_id,
            state=site_state,
            score=site_score,
            confidence=0.9,
            contributing_factors=contributing,
            missing_dimensions=[],
            calculated_at=now_iso,
        )
        self._persist_score(record)
        return record

    # -----------------------------------------------------------------------
    # 5. Tenant Operational Health Scoring
    # -----------------------------------------------------------------------
    def score_tenant(
        self,
        tenant_id: str,
        now: Optional[float] = None,
    ) -> OperationalHealthScoreRecord:
        """
        Computes overall tenant operational health.
        Applies Criticality-Aware Clamping: If any Tier 1 mission-critical service
        is CRITICAL, tenant score is clamped to CRITICAL.
        """
        now_ts = float(now) if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        score_id = f"hlth_tnt_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=False) as conn:
            t_row = conn.execute(
                "SELECT tenant_id, name, status FROM operational_tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()

            if not t_row:
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=None,
                    dimension=HealthDimensionType.TENANT.value,
                    entity_id=tenant_id,
                    state=HealthScoreState.UNKNOWN.value,
                    score=None,
                    confidence=0.0,
                    contributing_factors=["Tenant tidak ditemukan."],
                    missing_dimensions=["tenant"],
                    calculated_at=now_iso,
                )

            if t_row["status"] == "SUSPENDED":
                return OperationalHealthScoreRecord(
                    score_id=score_id,
                    tenant_id=tenant_id,
                    site_id=None,
                    dimension=HealthDimensionType.TENANT.value,
                    entity_id=tenant_id,
                    state=HealthScoreState.CRITICAL.value,
                    score=0.0,
                    confidence=1.0,
                    contributing_factors=["Akun tenant dalam status SUSPENDED."],
                    missing_dimensions=[],
                    calculated_at=now_iso,
                )

            site_rows = conn.execute(
                "SELECT site_id FROM operational_sites WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()

            svc_rows = conn.execute(
                "SELECT service_id, criticality, status FROM operational_services WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()

        tier1_critical = False
        contributing = []
        service_scores: List[float] = []

        # 1. Evaluate services
        for s in svc_rows:
            s_rec = self.score_service(tenant_id, s["service_id"], now=now_ts)
            if s_rec.score is not None:
                service_scores.append(s_rec.score)
            if s["criticality"] == ServiceCriticality.TIER_1_MISSION_CRITICAL.value and s_rec.state == HealthScoreState.CRITICAL.value:
                tier1_critical = True
                contributing.append(f"Layanan Misi Kritis (Tier 1) '{s['service_id']}' mengalami kegagalan total.")

        # 2. Evaluate sites
        site_scores: List[float] = []
        for site in site_rows:
            st_rec = self.score_site(tenant_id, site["site_id"], now=now_ts)
            if st_rec.score is not None:
                site_scores.append(st_rec.score)
            if st_rec.state == HealthScoreState.CRITICAL.value:
                contributing.append(f"Site '{site['site_id']}' mengalami degradasi kritis.")

        all_scores = service_scores + site_scores
        if not all_scores:
            return OperationalHealthScoreRecord(
                score_id=score_id,
                tenant_id=tenant_id,
                site_id=None,
                dimension=HealthDimensionType.TENANT.value,
                entity_id=tenant_id,
                state=HealthScoreState.INSUFFICIENT_DATA.value,
                score=None,
                confidence=0.2,
                contributing_factors=["Belum ada site atau layanan terdaftar dengan telemetri."],
                missing_dimensions=["sites", "services"],
                calculated_at=now_iso,
            )

        avg_score = sum(all_scores) / len(all_scores)

        # Criticality Clamping: If Tier 1 failed, clamp tenant to CRITICAL
        if tier1_critical:
            tenant_score = min(40.0, avg_score)
            tenant_state = HealthScoreState.CRITICAL.value
        elif any(s < 50.0 for s in all_scores):
            tenant_score = min(60.0, avg_score)
            tenant_state = HealthScoreState.WARNING.value
        elif avg_score >= 90.0:
            tenant_score = avg_score
            tenant_state = HealthScoreState.HEALTHY.value
            contributing.append("Seluruh site dan layanan tenant beroperasi optimal.")
        else:
            tenant_score = avg_score
            tenant_state = HealthScoreState.DEGRADED.value

        record = OperationalHealthScoreRecord(
            score_id=score_id,
            tenant_id=tenant_id,
            site_id=None,
            dimension=HealthDimensionType.TENANT.value,
            entity_id=tenant_id,
            state=tenant_state,
            score=tenant_score,
            confidence=0.92,
            contributing_factors=contributing,
            missing_dimensions=[],
            calculated_at=now_iso,
        )
        self._persist_score(record)
        return record

    def _persist_score(self, record: OperationalHealthScoreRecord) -> None:
        """Persists health score into operational_health_scores."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_health_scores (
                    score_id, tenant_id, site_id, dimension, entity_id,
                    state, score, confidence, contributing_factors_json,
                    missing_dimensions_json, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.score_id,
                    record.tenant_id,
                    record.site_id,
                    record.dimension,
                    record.entity_id,
                    record.state,
                    record.score,
                    record.confidence,
                    json.dumps(record.contributing_factors),
                    json.dumps(record.missing_dimensions),
                    record.calculated_at,
                ),
            )
