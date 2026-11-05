"""
AIRA OS — Proactive Incident Intelligence Engine (Networking VII / WP 7.6).

Tracks proactive operational incidents triggered by predictive trend breaches,
anomaly detections, or change impact simulations before user degradation occurs.
Enforces strict lifecycle state transitions and preventative action plans.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from core.operations.db import ensure_operational_schema
from core.operations.models import (
    IncidentSeverity,
    IncidentState,
    PredictiveMetricProjection,
    ProactiveIncidentRecord,
    RiskLevel,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.incidents")

# Allowed state machine transitions
VALID_STATE_TRANSITIONS: Dict[str, Set[str]] = {
    IncidentState.DETECTED.value: {IncidentState.ACKNOWLEDGED.value, IncidentState.INVESTIGATING.value, IncidentState.CLOSED.value},
    IncidentState.ACKNOWLEDGED.value: {IncidentState.INVESTIGATING.value, IncidentState.MITIGATED.value, IncidentState.CLOSED.value},
    IncidentState.INVESTIGATING.value: {IncidentState.MITIGATED.value, IncidentState.RESOLVED.value, IncidentState.CLOSED.value},
    IncidentState.MITIGATED.value: {IncidentState.RESOLVED.value, IncidentState.INVESTIGATING.value, IncidentState.CLOSED.value},
    IncidentState.RESOLVED.value: {IncidentState.CLOSED.value, IncidentState.INVESTIGATING.value},
    IncidentState.CLOSED.value: set(),  # Terminal state
}


class ProactiveIncidentEngine:
    """Manages proactive incident lifecycle, state transitions, and root cause links."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_operational_schema(self.db_path)

    def create_incident(self, incident: ProactiveIncidentRecord) -> ProactiveIncidentRecord:
        """Persists a new proactive incident."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_incidents (
                    incident_id, title, severity, state, source_engine,
                    affected_services_json, affected_devices_json, summary,
                    root_cause_analysis, remediation_plan, evidence_ids_json,
                    created_at, updated_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.incident_id,
                    incident.title,
                    incident.severity,
                    incident.state,
                    incident.source_engine,
                    json.dumps(incident.affected_services or []),
                    json.dumps(incident.affected_devices or []),
                    incident.summary,
                    incident.root_cause_analysis,
                    incident.remediation_plan,
                    json.dumps(incident.evidence_ids or []),
                    incident.created_at or now_iso,
                    incident.updated_at or now_iso,
                    incident.resolved_at,
                ),
            )
        return incident

    def get_incident(self, incident_id: str) -> Optional[ProactiveIncidentRecord]:
        """Retrieves a single incident by ID."""
        with topology_transaction(self.db_path, write=False) as conn:
            r = conn.execute(
                """
                SELECT incident_id, title, severity, state, source_engine,
                       affected_services_json, affected_devices_json, summary,
                       root_cause_analysis, remediation_plan, evidence_ids_json,
                       created_at, updated_at, resolved_at
                FROM operational_incidents WHERE incident_id = ?
                """,
                (incident_id,),
            ).fetchone()

        if not r:
            return None

        return ProactiveIncidentRecord(
            incident_id=r[0],
            title=r[1],
            severity=r[2],
            state=r[3],
            source_engine=r[4],
            affected_services=json.loads(r[5] or "[]"),
            affected_devices=json.loads(r[6] or "[]"),
            summary=r[7],
            root_cause_analysis=r[8],
            remediation_plan=r[9],
            evidence_ids=json.loads(r[10] or "[]"),
            created_at=r[11],
            updated_at=r[12],
            resolved_at=r[13],
        )

    def list_incidents(
        self,
        state: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[ProactiveIncidentRecord]:
        """Lists incidents, optionally filtered by state or severity."""
        query = "SELECT incident_id FROM operational_incidents"
        conditions = []
        params = []

        if state:
            conditions.append("state = ?")
            params.append(state)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC"

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        incidents: List[ProactiveIncidentRecord] = []
        for r in rows:
            inc = self.get_incident(r[0])
            if inc:
                incidents.append(inc)
        return incidents

    def transition_state(self, incident_id: str, new_state: str) -> ProactiveIncidentRecord:
        """Transitions an incident through the state machine with validation."""
        inc = self.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident '{incident_id}' not found.")

        current = inc.state
        target = new_state.upper().strip()

        allowed = VALID_STATE_TRANSITIONS.get(current, set())
        if target not in allowed and target != current:
            raise ValueError(f"Invalid state transition from '{current}' to '{target}'. Allowed: {allowed}")

        now_iso = datetime.now(timezone.utc).isoformat()
        resolved_at = now_iso if target in (IncidentState.RESOLVED.value, IncidentState.CLOSED.value) else inc.resolved_at

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_incidents
                SET state = ?, updated_at = ?, resolved_at = ?
                WHERE incident_id = ?
                """,
                (target, now_iso, resolved_at, incident_id),
            )

        inc.state = target
        inc.updated_at = now_iso
        inc.resolved_at = resolved_at
        return inc

    def create_from_prediction(self, projection: PredictiveMetricProjection) -> Optional[ProactiveIncidentRecord]:
        """Automatically raises a proactive incident if predictive projection indicates high/critical risk."""
        if projection.risk_level not in (RiskLevel.CRITICAL.value, RiskLevel.WARNING.value):
            return None

        sev = IncidentSeverity.CRITICAL.value if projection.risk_level == RiskLevel.CRITICAL.value else IncidentSeverity.HIGH.value
        inc_id = f"inc_pred_{uuid.uuid4().hex[:8]}"
        title = f"Impending Saturation: {projection.device_id} {projection.entity_id} {projection.metric_name}"
        summary = (
            f"Predictive analysis detected rapid trend ({projection.trend_direction}) on {projection.device_id}. "
            f"Breach projected within {projection.hours_to_warning or '<24'} hours."
        )

        incident = ProactiveIncidentRecord(
            incident_id=inc_id,
            title=title,
            severity=sev,
            state=IncidentState.DETECTED.value,
            source_engine="PREDICTIVE",
            affected_devices=[projection.device_id],
            summary=summary,
            remediation_plan=projection.recommended_action,
        )

        return self.create_incident(incident)
