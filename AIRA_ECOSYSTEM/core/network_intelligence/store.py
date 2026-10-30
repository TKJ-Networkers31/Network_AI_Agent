"""
core/network_intelligence/store.py — SQLite persistence for Network Intelligence records.

Follows the single-db-per-domain convention: owns database/network_intelligence.db exclusively.
Manages incident investigations, evidence items, playbook runs, and configuration plans.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.network_intelligence.models import (
    ConfigurationPlan,
    EvidenceItem,
    IncidentRecord,
    PlaybookRunRecord,
)

logger = logging.getLogger("aira.network_intelligence.store")

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "database" / "network_intelligence.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    device_identity TEXT NOT NULL,
    related_devices_json TEXT NOT NULL DEFAULT '[]',
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    symptoms_json TEXT NOT NULL DEFAULT '[]',
    user_description TEXT NOT NULL DEFAULT '',
    observed_facts_json TEXT NOT NULL DEFAULT '[]',
    inferred_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    recommended_tests_json TEXT NOT NULL DEFAULT '[]',
    evidence_sources_json TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence_explanation TEXT NOT NULL DEFAULT '',
    investigation_status TEXT NOT NULL DEFAULT 'CREATED',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    limitations_disclosure TEXT NOT NULL DEFAULT '',
    related_plan_ids_json TEXT NOT NULL DEFAULT '[]',
    correlation_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_incidents_device ON incidents(device_identity);
CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(investigation_status);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    device_identity TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    source_command TEXT NOT NULL,
    collection_timestamp REAL NOT NULL,
    collection_status TEXT NOT NULL,
    normalized_value_json TEXT NOT NULL DEFAULT '{}',
    raw_excerpt TEXT NOT NULL DEFAULT '',
    freshness TEXT NOT NULL DEFAULT 'FRESH',
    is_derived INTEGER NOT NULL DEFAULT 0,
    limitations TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'OBSERVED'
);
CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence_items(incident_id);
CREATE INDEX IF NOT EXISTS idx_evidence_device ON evidence_items(device_identity);

CREATE TABLE IF NOT EXISTS playbook_runs (
    run_id TEXT PRIMARY KEY,
    playbook_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    device_identity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY',
    current_step_id TEXT,
    completed_steps_json TEXT NOT NULL DEFAULT '[]',
    operator_inputs_json TEXT NOT NULL DEFAULT '{}',
    step_logs_json TEXT NOT NULL DEFAULT '[]',
    decision_history_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_playbook_incident ON playbook_runs(incident_id);

CREATE TABLE IF NOT EXISTS configuration_plans (
    plan_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    incident_id TEXT,
    target_devices_json TEXT NOT NULL DEFAULT '[]',
    desired_state_json TEXT NOT NULL DEFAULT '{}',
    baseline_snapshot_reference TEXT,
    preconditions_json TEXT NOT NULL DEFAULT '[]',
    proposed_changes_json TEXT NOT NULL DEFAULT '[]',
    configuration_diff TEXT NOT NULL DEFAULT '',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    blast_radius_json TEXT NOT NULL DEFAULT '{}',
    management_connectivity_risk INTEGER NOT NULL DEFAULT 0,
    management_risk_explanation TEXT NOT NULL DEFAULT '',
    validation_results_json TEXT NOT NULL DEFAULT '[]',
    simulation_results_json TEXT,
    expected_postconditions_json TEXT NOT NULL DEFAULT '[]',
    rollback_considerations_json TEXT NOT NULL DEFAULT '[]',
    required_operator_inputs_json TEXT NOT NULL DEFAULT '[]',
    approval_requirements_json TEXT NOT NULL DEFAULT '[]',
    limitations_disclosure TEXT NOT NULL DEFAULT '',
    plan_status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_incident ON configuration_plans(incident_id);
CREATE INDEX IF NOT EXISTS idx_plans_status ON configuration_plans(plan_status);
"""


class NetworkIntelligenceStore:
    """Thread-safe SQLite store for Network Intelligence data."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA_SQL)
            try:
                conn.execute("ALTER TABLE evidence_items ADD COLUMN state TEXT NOT NULL DEFAULT 'OBSERVED'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE incidents ADD COLUMN correlation_id TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    # -----------------------------------------------------------------------
    # Incidents
    # -----------------------------------------------------------------------

    def save_incident(self, inc: IncidentRecord) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    incident_id, device_identity, related_devices_json, incident_type,
                    severity, symptoms_json, user_description, observed_facts_json,
                    inferred_hypotheses_json, missing_evidence_json, recommended_tests_json,
                    evidence_sources_json, confidence, confidence_explanation,
                    investigation_status, created_at, updated_at, limitations_disclosure,
                    related_plan_ids_json, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    device_identity = excluded.device_identity,
                    related_devices_json = excluded.related_devices_json,
                    incident_type = excluded.incident_type,
                    severity = excluded.severity,
                    symptoms_json = excluded.symptoms_json,
                    user_description = excluded.user_description,
                    observed_facts_json = excluded.observed_facts_json,
                    inferred_hypotheses_json = excluded.inferred_hypotheses_json,
                    missing_evidence_json = excluded.missing_evidence_json,
                    recommended_tests_json = excluded.recommended_tests_json,
                    evidence_sources_json = excluded.evidence_sources_json,
                    confidence = excluded.confidence,
                    confidence_explanation = excluded.confidence_explanation,
                    investigation_status = excluded.investigation_status,
                    updated_at = excluded.updated_at,
                    limitations_disclosure = excluded.limitations_disclosure,
                    related_plan_ids_json = excluded.related_plan_ids_json,
                    correlation_id = excluded.correlation_id
                """,
                (
                    inc.incident_id,
                    inc.device_identity,
                    json.dumps(inc.related_devices),
                    inc.incident_type,
                    inc.severity,
                    json.dumps(inc.symptoms),
                    inc.user_description,
                    json.dumps(inc.observed_facts),
                    json.dumps(inc.inferred_hypotheses),
                    json.dumps(inc.missing_evidence),
                    json.dumps(inc.recommended_tests),
                    json.dumps(inc.evidence_sources),
                    inc.confidence,
                    inc.confidence_explanation,
                    inc.investigation_status,
                    inc.created_at,
                    inc.updated_at,
                    inc.limitations_disclosure,
                    json.dumps(inc.related_plan_ids),
                    inc.correlation_id or "",
                ),
            )
            conn.commit()

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def list_incidents(self, limit: int = 50, device_identity: Optional[str] = None) -> List[IncidentRecord]:
        with closing(self._connect()) as conn:
            if device_identity:
                rows = conn.execute(
                    "SELECT * FROM incidents WHERE device_identity = ? ORDER BY created_at DESC LIMIT ?",
                    (device_identity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_incident(r) for r in rows]

    def _row_to_incident(self, row: sqlite3.Row) -> IncidentRecord:
        return IncidentRecord(
            incident_id=row["incident_id"],
            device_identity=row["device_identity"],
            related_devices=json.loads(row["related_devices_json"] or "[]"),
            incident_type=row["incident_type"],
            severity=row["severity"],
            symptoms=json.loads(row["symptoms_json"] or "[]"),
            user_description=row["user_description"] or "",
            observed_facts=json.loads(row["observed_facts_json"] or "[]"),
            inferred_hypotheses=json.loads(row["inferred_hypotheses_json"] or "[]"),
            missing_evidence=json.loads(row["missing_evidence_json"] or "[]"),
            recommended_tests=json.loads(row["recommended_tests_json"] or "[]"),
            evidence_sources=json.loads(row["evidence_sources_json"] or "[]"),
            confidence=row["confidence"] or "MEDIUM",
            confidence_explanation=row["confidence_explanation"] or "",
            investigation_status=row["investigation_status"] or "CREATED",
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            limitations_disclosure=row["limitations_disclosure"] or "",
            related_plan_ids=json.loads(row["related_plan_ids_json"] or "[]"),
            correlation_id=row["correlation_id"] if "correlation_id" in row.keys() else "",
        )

    # -----------------------------------------------------------------------
    # Evidence Items
    # -----------------------------------------------------------------------

    def save_evidence_items(self, incident_id: str, items: List[EvidenceItem]) -> None:
        with self._lock, closing(self._connect()) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO evidence_items (
                        evidence_id, incident_id, device_identity, observation_type,
                        source_command, collection_timestamp, collection_status,
                        normalized_value_json, raw_excerpt, freshness, is_derived, limitations,
                        state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(evidence_id) DO UPDATE SET
                        collection_status = excluded.collection_status,
                        normalized_value_json = excluded.normalized_value_json,
                        raw_excerpt = excluded.raw_excerpt,
                        freshness = excluded.freshness,
                        limitations = excluded.limitations,
                        state = excluded.state
                    """,
                    (
                        item.evidence_id,
                        incident_id,
                        item.device_identity,
                        item.observation_type,
                        item.source_command,
                        item.collection_timestamp,
                        item.collection_status,
                        json.dumps(item.normalized_value),
                        item.raw_excerpt,
                        item.freshness,
                        1 if item.is_derived else 0,
                        item.limitations,
                        getattr(item, "state", "OBSERVED"),
                    ),
                )
            conn.commit()

    def get_evidence_for_incident(self, incident_id: str) -> List[EvidenceItem]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_items WHERE incident_id = ? ORDER BY collection_timestamp ASC",
                (incident_id,),
            ).fetchall()
            items = []
            for r in rows:
                state_val = r["state"] if ("state" in r.keys() and r["state"]) else "OBSERVED"
                items.append(EvidenceItem(
                    evidence_id=r["evidence_id"],
                    device_identity=r["device_identity"],
                    observation_type=r["observation_type"],
                    source_command=r["source_command"],
                    collection_timestamp=float(r["collection_timestamp"]),
                    collection_status=r["collection_status"],
                    normalized_value=json.loads(r["normalized_value_json"] or "{}"),
                    raw_excerpt=r["raw_excerpt"] or "",
                    freshness=r["freshness"] or "FRESH",
                    is_derived=bool(r["is_derived"]),
                    limitations=r["limitations"] or "",
                    state=state_val,
                ))
            return items

    # -----------------------------------------------------------------------
    # Playbook Runs
    # -----------------------------------------------------------------------

    def save_playbook_run(self, run: PlaybookRunRecord) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO playbook_runs (
                    run_id, playbook_id, incident_id, device_identity, status,
                    current_step_id, completed_steps_json, operator_inputs_json,
                    step_logs_json, decision_history_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    current_step_id = excluded.current_step_id,
                    completed_steps_json = excluded.completed_steps_json,
                    operator_inputs_json = excluded.operator_inputs_json,
                    step_logs_json = excluded.step_logs_json,
                    decision_history_json = excluded.decision_history_json,
                    updated_at = excluded.updated_at
                """,
                (
                    run.run_id,
                    run.playbook_id,
                    run.incident_id,
                    run.device_identity,
                    run.status,
                    run.current_step_id,
                    json.dumps(run.completed_steps),
                    json.dumps(run.operator_inputs),
                    json.dumps(run.step_logs),
                    json.dumps(run.decision_history),
                    run.created_at,
                    run.updated_at,
                ),
            )
            conn.commit()

    def get_playbook_run(self, run_id: str) -> Optional[PlaybookRunRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM playbook_runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return PlaybookRunRecord(
                run_id=row["run_id"],
                playbook_id=row["playbook_id"],
                incident_id=row["incident_id"],
                device_identity=row["device_identity"],
                status=row["status"],
                current_step_id=row["current_step_id"],
                completed_steps=json.loads(row["completed_steps_json"] or "[]"),
                operator_inputs=json.loads(row["operator_inputs_json"] or "{}"),
                step_logs=json.loads(row["step_logs_json"] or "[]"),
                decision_history=json.loads(row["decision_history_json"] or "[]"),
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
            )

    # -----------------------------------------------------------------------
    # Configuration Plans
    # -----------------------------------------------------------------------

    def save_plan(self, plan: ConfigurationPlan) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO configuration_plans (
                    plan_id, operation_id, incident_id, target_devices_json,
                    desired_state_json, baseline_snapshot_reference, preconditions_json,
                    proposed_changes_json, configuration_diff, dependencies_json,
                    risk_level, blast_radius_json, management_connectivity_risk,
                    management_risk_explanation, validation_results_json,
                    simulation_results_json, expected_postconditions_json,
                    rollback_considerations_json, required_operator_inputs_json,
                    approval_requirements_json, limitations_disclosure,
                    plan_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    incident_id = excluded.incident_id,
                    target_devices_json = excluded.target_devices_json,
                    desired_state_json = excluded.desired_state_json,
                    baseline_snapshot_reference = excluded.baseline_snapshot_reference,
                    preconditions_json = excluded.preconditions_json,
                    proposed_changes_json = excluded.proposed_changes_json,
                    configuration_diff = excluded.configuration_diff,
                    dependencies_json = excluded.dependencies_json,
                    risk_level = excluded.risk_level,
                    blast_radius_json = excluded.blast_radius_json,
                    management_connectivity_risk = excluded.management_connectivity_risk,
                    management_risk_explanation = excluded.management_risk_explanation,
                    validation_results_json = excluded.validation_results_json,
                    simulation_results_json = excluded.simulation_results_json,
                    expected_postconditions_json = excluded.expected_postconditions_json,
                    rollback_considerations_json = excluded.rollback_considerations_json,
                    required_operator_inputs_json = excluded.required_operator_inputs_json,
                    approval_requirements_json = excluded.approval_requirements_json,
                    limitations_disclosure = excluded.limitations_disclosure,
                    plan_status = excluded.plan_status,
                    updated_at = excluded.updated_at
                """,
                (
                    plan.plan_id,
                    plan.operation_id,
                    plan.incident_id,
                    json.dumps(plan.target_devices),
                    json.dumps(plan.desired_state),
                    plan.baseline_snapshot_reference,
                    json.dumps(plan.preconditions),
                    json.dumps(plan.proposed_changes),
                    plan.configuration_diff,
                    json.dumps(plan.dependencies),
                    plan.risk_level,
                    json.dumps(plan.blast_radius),
                    1 if plan.management_connectivity_risk else 0,
                    plan.management_risk_explanation,
                    json.dumps(plan.validation_results),
                    json.dumps(plan.simulation_results) if plan.simulation_results is not None else None,
                    json.dumps(plan.expected_postconditions),
                    json.dumps(plan.rollback_considerations),
                    json.dumps(plan.required_operator_inputs),
                    json.dumps(plan.approval_requirements),
                    plan.limitations_disclosure,
                    plan.plan_status,
                    plan.created_at,
                    plan.updated_at,
                ),
            )
            conn.commit()

    def get_plan(self, plan_id: str) -> Optional[ConfigurationPlan]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM configuration_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            return self._row_to_plan(row)

    def list_plans(self, limit: int = 50, incident_id: Optional[str] = None) -> List[ConfigurationPlan]:
        with closing(self._connect()) as conn:
            if incident_id:
                rows = conn.execute(
                    "SELECT * FROM configuration_plans WHERE incident_id = ? ORDER BY created_at DESC LIMIT ?",
                    (incident_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM configuration_plans ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_plan(r) for r in rows]

    def _row_to_plan(self, row: sqlite3.Row) -> ConfigurationPlan:
        sim_json = row["simulation_results_json"]
        sim_res = json.loads(sim_json) if sim_json else None
        return ConfigurationPlan(
            plan_id=row["plan_id"],
            operation_id=row["operation_id"],
            incident_id=row["incident_id"],
            target_devices=json.loads(row["target_devices_json"] or "[]"),
            desired_state=json.loads(row["desired_state_json"] or "{}"),
            baseline_snapshot_reference=row["baseline_snapshot_reference"],
            preconditions=json.loads(row["preconditions_json"] or "[]"),
            proposed_changes=json.loads(row["proposed_changes_json"] or "[]"),
            configuration_diff=row["configuration_diff"] or "",
            dependencies=json.loads(row["dependencies_json"] or "[]"),
            risk_level=row["risk_level"] or "LOW",
            blast_radius=json.loads(row["blast_radius_json"] or "{}"),
            management_connectivity_risk=bool(row["management_connectivity_risk"]),
            management_risk_explanation=row["management_risk_explanation"] or "",
            validation_results=json.loads(row["validation_results_json"] or "[]"),
            simulation_results=sim_res,
            expected_postconditions=json.loads(row["expected_postconditions_json"] or "[]"),
            rollback_considerations=json.loads(row["rollback_considerations_json"] or "[]"),
            required_operator_inputs=json.loads(row["required_operator_inputs_json"] or "[]"),
            approval_requirements=json.loads(row["approval_requirements_json"] or "[]"),
            limitations_disclosure=row["limitations_disclosure"] or "",
            plan_status=row["plan_status"] or "DRAFT",
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )


_store_singleton: Optional[NetworkIntelligenceStore] = None
_store_lock = threading.Lock()


def get_network_intelligence_store() -> NetworkIntelligenceStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = NetworkIntelligenceStore()
    return _store_singleton
