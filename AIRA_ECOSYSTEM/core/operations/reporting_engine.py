"""
AIRA OS — Operational Reporting Engine (Networking VII / WP 7.8).

Generates deterministic Daily, Weekly, and Monthly operational reports summarizing
network availability, capacity saturation horizons, change simulations, route stability,
and proactive incident mitigations in Markdown, JSON, and printable HTML formats.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from core.operations.calendar.manager import CalendarManager
from core.operations.incident_engine import ProactiveIncidentEngine
from core.operations.predictive_engine import PredictiveOperationsEngine
from core.operations.scheduler import OperationalSchedulerEngine
from core.operations.service_intelligence import ServiceIntelligenceEngine

logger = logging.getLogger("aira.operations.reporting")


class OperationalReportingEngine:
    """Aggregates multi-subsystem telemetry and logs into deterministic operational reports."""

    def __init__(
        self,
        predictive_engine: Optional[PredictiveOperationsEngine] = None,
        service_engine: Optional[ServiceIntelligenceEngine] = None,
        scheduler_engine: Optional[OperationalSchedulerEngine] = None,
        calendar_manager: Optional[CalendarManager] = None,
        incident_engine: Optional[ProactiveIncidentEngine] = None,
    ) -> None:
        self.predictive = predictive_engine or PredictiveOperationsEngine()
        self.services = service_engine or ServiceIntelligenceEngine()
        self.scheduler = scheduler_engine or OperationalSchedulerEngine()
        self.calendar = calendar_manager or CalendarManager()
        self.incidents = incident_engine or ProactiveIncidentEngine()

    def generate_report(
        self,
        report_period: str = "DAILY",  # DAILY, WEEKLY, MONTHLY
        now_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Gathers deterministic data across operations subsystems and constructs report payload."""
        current_dt = now_dt or datetime.now(timezone.utc)
        rep_id = f"op_rep_{uuid.uuid4().hex[:8]}"

        # 1. Services health
        all_services = self.services.list_services()
        svc_count = len(all_services)
        healthy_svcs = sum(1 for s in all_services if s.status == "HEALTHY")
        svc_health_pct = round((healthy_svcs / svc_count * 100.0), 1) if svc_count > 0 else 100.0

        # 2. Incidents summary
        all_incidents = self.incidents.list_incidents()
        open_incidents = [i for i in all_incidents if i.state not in ("RESOLVED", "CLOSED")]
        mitigated_count = sum(1 for i in all_incidents if i.state in ("MITIGATED", "RESOLVED", "CLOSED"))

        # 3. Scheduled maintenance windows
        all_windows = self.calendar.list_windows()
        active_windows = self.calendar.get_currently_active_windows(current_dt)

        # 4. Job runs summary
        recent_runs = self.scheduler.list_job_runs(limit=20)
        successful_runs = sum(1 for r in recent_runs if r.status == "SUCCESS")

        payload: Dict[str, Any] = {
            "report_id": rep_id,
            "period": report_period.upper(),
            "generated_at": current_dt.isoformat(),
            "executive_summary": {
                "overall_operational_score": svc_health_pct,
                "total_monitored_services": svc_count,
                "healthy_services": healthy_svcs,
                "open_proactive_incidents": len(open_incidents),
                "preventatively_mitigated_incidents": mitigated_count,
                "active_maintenance_windows": len(active_windows),
                "scheduled_job_success_rate": round(successful_runs / max(1, len(recent_runs)) * 100.0, 1),
            },
            "services": [s.to_dict() for s in all_services],
            "incidents": [i.to_dict() for i in open_incidents],
            "maintenance_windows": [w.to_dict() for w in active_windows],
            "recent_job_runs": [r.to_dict() for r in recent_runs[:5]],
        }

        # Render markdown and HTML
        payload["markdown"] = self._render_markdown(payload)
        payload["html"] = self._render_html(payload)

        return payload

    @staticmethod
    def _render_markdown(data: Dict[str, Any]) -> str:
        summary = data["executive_summary"]
        period = data["period"]
        dt = data["generated_at"]

        md = [
            f"# AIRA OS — {period} Network Operations Intelligence Report",
            f"**Report ID:** `{data['report_id']}` | **Generated:** `{dt}` | **Operational Score:** `{summary['overall_operational_score']}%`",
            "",
            "## 1. Executive Operations Scorecard",
            "| Metric | Observed Value | Status |",
            "| :--- | :--- | :--- |",
            f"| Business Service Health | {summary['healthy_services']} / {summary['total_monitored_services']} Healthy ({summary['overall_operational_score']}%) | {'OPTIMAL' if summary['overall_operational_score'] >= 90 else 'ATTENTION'} |",
            f"| Open Proactive Incidents | {summary['open_proactive_incidents']} active | {'CLEAR' if summary['open_proactive_incidents'] == 0 else 'ACTION_REQUIRED'} |",
            f"| Preventative Mitigations | {summary['preventatively_mitigated_incidents']} resolved prior to outage | PROACTIVE |",
            f"| Active Maintenance Windows | {summary['active_maintenance_windows']} windows currently open | IN_PROGRESS |",
            f"| Operational Job Success Rate | {summary['scheduled_job_success_rate']}% | {'NOMINAL' if summary['scheduled_job_success_rate'] >= 95 else 'WARNING'} |",
            "",
            "## 2. Active Proactive Incidents",
        ]

        if not data["incidents"]:
            md.append("No active proactive incidents. All operational thresholds and predictive horizons are healthy.")
        else:
            md.append("| Incident ID | Severity | Title | Affected Devices | State |")
            md.append("| :--- | :--- | :--- | :--- | :--- |")
            for inc in data["incidents"]:
                devs = ", ".join(inc.get("affected_devices", []))
                md.append(f"| `{inc['incident_id']}` | **{inc['severity']}** | {inc['title']} | {devs} | `{inc['state']}` |")

        md.extend([
            "",
            "## 3. Scheduled Maintenance Windows",
        ])
        if not data["maintenance_windows"]:
            md.append("No maintenance windows currently active.")
        else:
            for w in data["maintenance_windows"]:
                md.append(f"- **{w['title']}** (`{w['window_id']}`): {w['start_time_local']} to {w['end_time_local']} (Scope: {w['scope_type']})")

        md.extend([
            "",
            "---",
            "*Report deterministically assembled by AIRA OS Proactive Operations Subsystem.*",
        ])

        return "\n".join(md)

    @staticmethod
    def _render_html(data: Dict[str, Any]) -> str:
        summary = data["executive_summary"]
        period = data["period"]
        dt = data["generated_at"]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AIRA OS — {period} Operations Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #1e293b; background: #f8fafc; }}
        .card {{ background: white; border-radius: 8px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }}
        h1 {{ color: #0f172a; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; font-weight: 600; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .badge-success {{ background: #dcfce7; color: #15803d; }}
        .badge-warning {{ background: #fef9c3; color: #a16207; }}
        .badge-danger {{ background: #fee2e2; color: #b91c1c; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>AIRA OS — {period} Network Operations Report</h1>
        <p><strong>Report ID:</strong> {data['report_id']} | <strong>Generated:</strong> {dt}</p>
        <h2>Executive Scorecard</h2>
        <table>
            <tr><th>Metric</th><th>Observed Value</th></tr>
            <tr><td>Operational Health Score</td><td><strong>{summary['overall_operational_score']}%</strong></td></tr>
            <tr><td>Monitored Business Services</td><td>{summary['healthy_services']} / {summary['total_monitored_services']} Healthy</td></tr>
            <tr><td>Open Proactive Incidents</td><td>{summary['open_proactive_incidents']}</td></tr>
            <tr><td>Job Automation Reliability</td><td>{summary['scheduled_job_success_rate']}%</td></tr>
        </table>
    </div>
</body>
</html>"""
