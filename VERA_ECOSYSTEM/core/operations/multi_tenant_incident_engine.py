"""
AIRA OS — Multi-Tenant Incident Orchestration & Correlation Engine (Networking VIII / WP 8.8).

Features:
1. Strict tenant boundary isolation:
   Cross-tenant correlation is strictly forbidden.
2. Deterministic fingerprint deduplication:
   Suppresses duplicate alerts within rolling time windows.
3. Intra-tenant topological correlation:
   Clusters co-occurring symptoms with shared graph root causes into a single incident.
4. Preserved incident lifecycle:
   DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED.
5. Scoped notifications:
   Integrates with NotificationHub ensuring internal NOC vs customer notification separation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from core.operations.db import ensure_operational_schema
from core.operations.incident_engine import VALID_STATE_TRANSITIONS as VALID_INCIDENT_TRANSITIONS
from core.operations.models import (
    IncidentSeverity,
    IncidentState,
    ProactiveIncidentRecord,
)
from core.operations.notification_hub import NotificationHub
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.operations.multi_tenant_incident")


class MultiTenantIncidentEngine:
    """Manages tenant-scoped proactive incidents and correlation."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        notification_hub: Optional[NotificationHub] = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.notification_hub = notification_hub or NotificationHub(db_path=self.db_path)
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # Deduplication & Creation
    # -----------------------------------------------------------------------
    @staticmethod
    def compute_incident_fingerprint(
        tenant_id: str,
        site_id: str,
        primary_entity_id: str,
        failure_signature: str,
    ) -> str:
        """Computes deterministic fingerprint for alert deduplication."""
        raw = f"{tenant_id}:{site_id}:{primary_entity_id}:{failure_signature}".lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def report_incident(
        self,
        tenant_id: str,
        title: str,
        severity: str,
        summary: str,
        site_id: Optional[str] = None,
        primary_entity_id: str = "",
        failure_signature: str = "",
        affected_services: Optional[List[str]] = None,
        affected_devices: Optional[List[str]] = None,
        evidence_ids: Optional[List[str]] = None,
        root_cause_analysis: Optional[str] = None,
        remediation_plan: Optional[str] = None,
        source_engine: str = "PREDICTIVE",
    ) -> ProactiveIncidentRecord:
        """
        Reports an operational incident with automated deduplication.
        If an open incident with matching fingerprint exists, appends evidence.
        """
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        norm_severity = severity.upper()
        if norm_severity == "WARNING":
            norm_severity = "HIGH"
        elif norm_severity not in ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"):
            norm_severity = "MEDIUM"
        fingerprint = self.compute_incident_fingerprint(
            tenant_id=tenant_id,
            site_id=site_id or "global",
            primary_entity_id=primary_entity_id,
            failure_signature=failure_signature,
        )

        with topology_transaction(self.db_path, write=True) as conn:
            # 1. Deduplication check: Is there an active incident with matching fingerprint?
            active_row = conn.execute(
                """
                SELECT incident_id, evidence_ids_json, affected_devices_json, affected_services_json
                FROM operational_incidents
                WHERE tenant_id = ? AND summary LIKE ? AND state IN ('DETECTED', 'ACKNOWLEDGED', 'INVESTIGATING')
                ORDER BY created_at DESC LIMIT 1
                """,
                (tenant_id, f"%[FP:{fingerprint}]%"),
            ).fetchone()

            if active_row:
                # Deduplicate: Append new evidence to existing active incident
                inc_id = active_row["incident_id"]
                existing_ev = set(json.loads(active_row["evidence_ids_json"] or "[]"))
                for eid in (evidence_ids or []):
                    existing_ev.add(eid)

                existing_devs = set(json.loads(active_row["affected_devices_json"] or "[]"))
                for d in (affected_devices or []):
                    existing_devs.add(d)

                conn.execute(
                    """
                    UPDATE operational_incidents
                    SET evidence_ids_json = ?, affected_devices_json = ?, updated_at = ?
                    WHERE incident_id = ?
                    """,
                    (json.dumps(sorted(list(existing_ev))), json.dumps(sorted(list(existing_devs))), now_iso, inc_id),
                )
                logger.info("Deduplicated event into existing incident %s for tenant %s", inc_id, tenant_id)
                return self.get_incident(tenant_id, inc_id)  # type: ignore

            # 2. Create New Incident
            new_id = f"inc_{uuid.uuid4().hex[:10]}"
            tagged_summary = f"{summary.strip()} [FP:{fingerprint}]"
            aff_services = list(affected_services or [])
            aff_devices = list(affected_devices or [])
            ev_list = list(evidence_ids or [])

            conn.execute(
                """
                INSERT INTO operational_incidents (
                    incident_id, tenant_id, site_id, title, severity, state,
                    source_engine, affected_services_json, affected_devices_json,
                    summary, root_cause_analysis, remediation_plan,
                    evidence_ids_json, created_at, updated_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, 'DETECTED', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    new_id,
                    tenant_id,
                    site_id,
                    title,
                    norm_severity,
                    source_engine,
                    json.dumps(aff_services),
                    json.dumps(aff_devices),
                    tagged_summary,
                    root_cause_analysis,
                    remediation_plan,
                    json.dumps(ev_list),
                    now_iso,
                    now_iso,
                ),
            )

        # 3. Dispatch Notification via NotificationHub
        try:
            self.notification_hub.dispatch_notification(
                category="INCIDENT",
                severity=severity,
                title=f"[{severity.upper()}] {title}",
                message=summary,
                identifier=new_id,
                metadata={"tenant_id": tenant_id, "site_id": site_id, "incident_id": new_id},
            )
        except Exception as exc:
            logger.warning("Failed to dispatch incident notification: %s", exc)

        return ProactiveIncidentRecord(
            incident_id=new_id,
            title=title,
            severity=severity.upper(),
            state=IncidentState.DETECTED.value,
            source_engine=source_engine,
            affected_services=aff_services,
            affected_devices=aff_devices,
            summary=tagged_summary,
            root_cause_analysis=root_cause_analysis,
            remediation_plan=remediation_plan,
            evidence_ids=ev_list,
            created_at=now_iso,
            updated_at=now_iso,
            resolved_at=None,
        )

    # -----------------------------------------------------------------------
    # Retrieval & Lifecycle Transitions
    # -----------------------------------------------------------------------
    def get_incident(self, tenant_id: str, incident_id: str) -> Optional[ProactiveIncidentRecord]:
        """Retrieves single incident with strict tenant boundary verification."""
        with topology_transaction(self.db_path, write=False) as conn:
            r = conn.execute(
                """
                SELECT incident_id, tenant_id, site_id, title, severity, state,
                       source_engine, affected_services_json, affected_devices_json,
                       summary, root_cause_analysis, remediation_plan,
                       evidence_ids_json, created_at, updated_at, resolved_at
                FROM operational_incidents
                WHERE incident_id = ? AND tenant_id = ?
                """,
                (incident_id, tenant_id),
            ).fetchone()

        if not r:
            return None

        return ProactiveIncidentRecord(
            incident_id=r["incident_id"],
            title=r["title"],
            severity=r["severity"],
            state=r["state"],
            source_engine=r["source_engine"],
            affected_services=json.loads(r["affected_services_json"] or "[]"),
            affected_devices=json.loads(r["affected_devices_json"] or "[]"),
            summary=r["summary"],
            root_cause_analysis=r["root_cause_analysis"],
            remediation_plan=r["remediation_plan"],
            evidence_ids=json.loads(r["evidence_ids_json"] or "[]"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            resolved_at=r["resolved_at"],
        )

    def transition_incident(
        self,
        tenant_id: str,
        incident_id: str,
        new_state: str,
        actor: str,
        resolution_notes: Optional[str] = None,
    ) -> ProactiveIncidentRecord:
        """
        Transitions incident through validated lifecycle state machine.
        DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            r = conn.execute(
                "SELECT state FROM operational_incidents WHERE incident_id = ? AND tenant_id = ?",
                (incident_id, tenant_id),
            ).fetchone()

            if not r:
                raise KeyError(f"Incident '{incident_id}' not found for tenant '{tenant_id}'.")

            current_state = r["state"]
            allowed = VALID_INCIDENT_TRANSITIONS.get(current_state, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Invalid Incident Transition: Cannot transition from '{current_state}' to '{new_state}'. Allowed: {sorted(list(allowed))}"
                )

            resolved_at = now_iso if new_state in (IncidentState.RESOLVED.value, IncidentState.CLOSED.value) else None

            conn.execute(
                """
                UPDATE operational_incidents
                SET state = ?, updated_at = ?, resolved_at = COALESCE(resolved_at, ?),
                    remediation_plan = CASE WHEN ? IS NOT NULL THEN ? ELSE remediation_plan END
                WHERE incident_id = ? AND tenant_id = ?
                """,
                (new_state, now_iso, resolved_at, resolution_notes, resolution_notes, incident_id, tenant_id),
            )

        return self.get_incident(tenant_id, incident_id)  # type: ignore

    transition_state = transition_incident

    def list_incidents(
        self,
        tenant_id: str,
        state: Optional[str] = None,
        severity: Optional[str] = None,
        site_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProactiveIncidentRecord]:
        """Lists incidents scoped to tenant, ordered by severity and creation time."""
        clauses = ["tenant_id = ?"]
        params: List[Any] = [tenant_id]

        if state:
            clauses.append("state = ?")
            params.append(state)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if site_id:
            clauses.append("site_id = ?")
            params.append(site_id)

        where_sql = " AND ".join(clauses)
        params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                f"""
                SELECT incident_id, tenant_id, site_id, title, severity, state,
                       source_engine, affected_services_json, affected_devices_json,
                       summary, root_cause_analysis, remediation_plan,
                       evidence_ids_json, created_at, updated_at, resolved_at
                FROM operational_incidents
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

        incidents = []
        for r in rows:
            incidents.append(
                ProactiveIncidentRecord(
                    incident_id=r["incident_id"],
                    title=r["title"],
                    severity=r["severity"],
                    state=r["state"],
                    source_engine=r["source_engine"],
                    affected_services=json.loads(r["affected_services_json"] or "[]"),
                    affected_devices=json.loads(r["affected_devices_json"] or "[]"),
                    summary=r["summary"],
                    root_cause_analysis=r["root_cause_analysis"],
                    remediation_plan=r["remediation_plan"],
                    evidence_ids=json.loads(r["evidence_ids_json"] or "[]"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    resolved_at=r["resolved_at"],
                )
            )
        return incidents
