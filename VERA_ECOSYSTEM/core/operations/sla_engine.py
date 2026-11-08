"""
AIRA OS — SLA and Service Management Engine (Networking VIII / WP 8.7).

Features:
1. Customer SLA policies per business service with target availability and MTTR.
2. Grounded temporal categorization:
   MEASURED_UPTIME, MEASURED_DOWNTIME, INFERRED_DOWNTIME, PLANNED_MAINTENANCE, UNKNOWN.
3. Explicit maintenance window exclusions based on operational_maintenance_windows.
4. Epistemic data coverage verification:
   If data coverage is < 80%, emits INSUFFICIENT_COVERAGE rather than inventing a percentage.
5. Error budget remaining seconds and percentage accounting.
6. Persistent SLA reports in operational_sla_reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from core.operations.db import ensure_operational_schema
from core.operations.models import (
    SlaPolicyRecord,
    SlaReportRecord,
    SlaStatusType,
    SlaWindowType,
)
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.operations.sla_engine")

MIN_DATA_COVERAGE_THRESHOLD_PERCENT = 80.0


class SlaManagementEngine:
    """Computes reproducible customer SLA availability and error budgets."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # Policy Management
    # -----------------------------------------------------------------------
    def create_or_update_policy(
        self,
        tenant_id: str,
        service_id: str,
        name: str,
        target_availability: float = 99.9,
        target_response_time_ms: float = 150.0,
        target_mttr_minutes: int = 60,
        window_type: str = SlaWindowType.MONTHLY.value,
        maintenance_excluded: bool = True,
    ) -> SlaPolicyRecord:
        """Creates or updates an SLA policy for a business service."""
        now_iso = datetime.now(timezone.utc).isoformat()
        policy_id = f"sla_pol_{uuid.uuid4().hex[:10]}"

        with topology_transaction(self.db_path, write=True) as conn:
            # Check existing policy
            existing = conn.execute(
                "SELECT policy_id FROM operational_sla_policies WHERE tenant_id = ? AND service_id = ?",
                (tenant_id, service_id),
            ).fetchone()

            if existing:
                policy_id = existing["policy_id"]
                conn.execute(
                    """
                    UPDATE operational_sla_policies
                    SET name = ?, target_availability = ?, target_response_time_ms = ?,
                        target_mttr_minutes = ?, window_type = ?, maintenance_excluded = ?, updated_at = ?
                    WHERE policy_id = ?
                    """,
                    (
                        name,
                        target_availability,
                        target_response_time_ms,
                        target_mttr_minutes,
                        window_type,
                        1 if maintenance_excluded else 0,
                        now_iso,
                        policy_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO operational_sla_policies (
                        policy_id, tenant_id, service_id, name, target_availability,
                        target_response_time_ms, target_mttr_minutes, window_type,
                        maintenance_excluded, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        policy_id,
                        tenant_id,
                        service_id,
                        name,
                        target_availability,
                        target_response_time_ms,
                        target_mttr_minutes,
                        window_type,
                        1 if maintenance_excluded else 0,
                        now_iso,
                        now_iso,
                    ),
                )

        return SlaPolicyRecord(
            policy_id=policy_id,
            tenant_id=tenant_id,
            service_id=service_id,
            name=name,
            target_availability=target_availability,
            target_response_time_ms=target_response_time_ms,
            target_mttr_minutes=target_mttr_minutes,
            window_type=window_type,
            maintenance_excluded=maintenance_excluded,
            created_at=now_iso,
            updated_at=now_iso,
        )

    def get_policy(self, tenant_id: str, service_id: str) -> Optional[SlaPolicyRecord]:
        """Retrieves active SLA policy for a service."""
        with topology_transaction(self.db_path, write=False) as conn:
            r = conn.execute(
                """
                SELECT policy_id, tenant_id, service_id, name, target_availability,
                       target_response_time_ms, target_mttr_minutes, window_type,
                       maintenance_excluded, created_at, updated_at
                FROM operational_sla_policies
                WHERE tenant_id = ? AND service_id = ?
                """,
                (tenant_id, service_id),
            ).fetchone()

        if not r:
            return None

        return SlaPolicyRecord(
            policy_id=r["policy_id"],
            tenant_id=r["tenant_id"],
            service_id=r["service_id"],
            name=r["name"],
            target_availability=r["target_availability"],
            target_response_time_ms=r["target_response_time_ms"],
            target_mttr_minutes=r["target_mttr_minutes"],
            window_type=r["window_type"],
            maintenance_excluded=bool(r["maintenance_excluded"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    # -----------------------------------------------------------------------
    # Availability & Error Budget Calculation
    # -----------------------------------------------------------------------
    def calculate_sla_report(
        self,
        tenant_id: str,
        service_id: str,
        start_time_utc: str,
        end_time_utc: str,
    ) -> SlaReportRecord:
        """
        Calculates availability, maintenance exclusions, and error budget.
        Enforces reproducible mathematical formulas.
        """
        report_id = f"sla_rep_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Load Policy
        policy = self.get_policy(tenant_id, service_id)
        if not policy:
            # Default fallback policy if none defined
            policy = self.create_or_update_policy(
                tenant_id=tenant_id,
                service_id=service_id,
                name=f"Default SLA for {service_id}",
                target_availability=99.9,
            )

        # Parse time window
        start_dt = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time_utc.replace("Z", "+00:00"))
        total_window_sec = max(1.0, (end_dt - start_dt).total_seconds())

        # 2. Check Planned Maintenance Windows
        maintenance_sec = 0.0
        if policy.maintenance_excluded:
            with topology_transaction(self.db_path, write=False) as conn:
                maint_rows = conn.execute(
                    """
                    SELECT start_time_utc, end_time_utc, status
                    FROM operational_maintenance_windows
                    WHERE status IN ('ACTIVE', 'COMPLETED')
                      AND start_time_utc < ? AND end_time_utc > ?
                    """,
                    (end_time_utc, start_time_utc),
                ).fetchall()

                for m in maint_rows:
                    m_start = max(start_dt, datetime.fromisoformat(m["start_time_utc"].replace("Z", "+00:00")))
                    m_end = min(end_dt, datetime.fromisoformat(m["end_time_utc"].replace("Z", "+00:00")))
                    dur = max(0.0, (m_end - m_start).total_seconds())
                    maintenance_sec += dur

        # 3. Query Service Outage Incidents and Telemetry
        with topology_transaction(self.db_path, write=False) as conn:
            # Incidents affecting this service
            inc_rows = conn.execute(
                """
                SELECT incident_id, created_at, resolved_at, severity
                FROM operational_incidents
                WHERE (tenant_id = ? OR tenant_id IS NULL)
                  AND affected_services_json LIKE ?
                  AND created_at < ?
                """,
                (tenant_id, f"%{service_id}%", end_time_utc),
            ).fetchall()

            # Query raw metrics samples count for service endpoints
            ep_rows = conn.execute(
                "SELECT target_device_id FROM operational_service_endpoints WHERE service_id = ?",
                (service_id,),
            ).fetchall()
            target_devices = [r["target_device_id"] for r in ep_rows if r["target_device_id"]]

            start_epoch = start_dt.timestamp()
            end_epoch = end_dt.timestamp()
            sample_count = 0
            if target_devices:
                placeholders = ",".join("?" for _ in target_devices)
                cnt_row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM nms_raw_metrics WHERE device_id IN ({placeholders}) AND measured_at BETWEEN ? AND ?",
                    target_devices + [start_epoch, end_epoch],
                ).fetchone()
                sample_count = cnt_row["cnt"] if cnt_row else 0

        # Calculate actual downtime from incidents
        downtime_sec = 0.0
        incident_count = 0
        for inc in inc_rows:
            inc_start = max(start_dt, datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")))
            if inc["resolved_at"]:
                inc_end = min(end_dt, datetime.fromisoformat(inc["resolved_at"].replace("Z", "+00:00")))
            else:
                inc_end = end_dt

            dur = max(0.0, (inc_end - inc_start).total_seconds())
            if dur > 0:
                downtime_sec += dur
                incident_count += 1

        # Prevent double counting with maintenance
        downtime_sec = max(0.0, downtime_sec - maintenance_sec)

        # 4. Epistemic Data Coverage Check
        # For a healthy window with regular telemetry (samples expected every 30s)
        expected_samples = max(1.0, (total_window_sec / 30.0) * len(target_devices or [1]))
        coverage_percent = min(100.0, (sample_count / expected_samples) * 100.0)

        # If coverage is below 80% (and total window is longer than 5 minutes), emit INSUFFICIENT_COVERAGE
        if coverage_percent < MIN_DATA_COVERAGE_THRESHOLD_PERCENT and total_window_sec > 300.0:
            report = SlaReportRecord(
                report_id=report_id,
                tenant_id=tenant_id,
                service_id=service_id,
                policy_id=policy.policy_id,
                period_start_utc=start_time_utc,
                period_end_utc=end_time_utc,
                target_availability=policy.target_availability,
                measured_availability=None, # Epistemic: Never invent a percentage
                total_downtime_seconds=downtime_sec,
                maintenance_excluded_seconds=maintenance_sec,
                data_coverage_percent=coverage_percent,
                status=SlaStatusType.INSUFFICIENT_COVERAGE.value,
                error_budget_remaining_percent=None,
                incident_count=incident_count,
                details={
                    "reason": f"Cakupan data telemetri ({coverage_percent:.1f}%) di bawah ambang batas minimal ({MIN_DATA_COVERAGE_THRESHOLD_PERCENT}%).",
                    "sample_count": sample_count,
                    "expected_samples": round(expected_samples, 1),
                },
                generated_at=now_iso,
            )
            self._persist_report(report)
            return report

        # 5. Availability & Error Budget
        net_window_sec = max(1.0, total_window_sec - maintenance_sec)
        uptime_sec = max(0.0, net_window_sec - downtime_sec)
        measured_avail = (uptime_sec / net_window_sec) * 100.0

        allowed_downtime_sec = net_window_sec * (1.0 - (policy.target_availability / 100.0))
        remaining_budget_sec = allowed_downtime_sec - downtime_sec
        if allowed_downtime_sec <= 0.0:
            remaining_budget_pct = 100.0 if downtime_sec == 0.0 else 0.0
        else:
            remaining_budget_pct = (remaining_budget_sec / allowed_downtime_sec) * 100.0

        if measured_avail < policy.target_availability:
            status = SlaStatusType.BREACHED.value
        elif remaining_budget_pct < 20.0:
            status = SlaStatusType.AT_RISK.value
        else:
            status = SlaStatusType.COMPLIANT.value

        report = SlaReportRecord(
            report_id=report_id,
            tenant_id=tenant_id,
            service_id=service_id,
            policy_id=policy.policy_id,
            period_start_utc=start_time_utc,
            period_end_utc=end_time_utc,
            target_availability=policy.target_availability,
            measured_availability=measured_avail,
            total_downtime_seconds=downtime_sec,
            maintenance_excluded_seconds=maintenance_sec,
            data_coverage_percent=coverage_percent,
            status=status,
            error_budget_remaining_percent=max(-100.0, remaining_budget_pct),
            incident_count=incident_count,
            details={
                "uptime_seconds": round(uptime_sec, 1),
                "allowed_downtime_seconds": round(allowed_downtime_sec, 1),
                "remaining_budget_seconds": round(remaining_budget_sec, 1),
                "net_window_seconds": round(net_window_sec, 1),
            },
            generated_at=now_iso,
        )
        self._persist_report(report)
        return report

    def _persist_report(self, report: SlaReportRecord) -> None:
        """Saves SLA report to database."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_sla_reports (
                    report_id, tenant_id, service_id, policy_id, period_start_utc,
                    period_end_utc, target_availability, measured_availability,
                    total_downtime_seconds, maintenance_excluded_seconds,
                    data_coverage_percent, status, error_budget_remaining_percent,
                    incident_count, details_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.tenant_id,
                    report.service_id,
                    report.policy_id,
                    report.period_start_utc,
                    report.period_end_utc,
                    report.target_availability,
                    report.measured_availability,
                    report.total_downtime_seconds,
                    report.maintenance_excluded_seconds,
                    report.data_coverage_percent,
                    report.status,
                    report.error_budget_remaining_percent,
                    report.incident_count,
                    json.dumps(report.details),
                    report.generated_at,
                ),
            )
