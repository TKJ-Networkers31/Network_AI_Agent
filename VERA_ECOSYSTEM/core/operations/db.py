"""
AIRA OS — Operations Persistence & Schema Management (Networking VII).

Manages SQLite schema creation, migrations, and transactional access for:
1. Business services & endpoints (WP 7.3)
2. Operational jobs & execution logs (WP 7.4)
3. Maintenance windows & calendar events (WP 7.5)
4. Proactive operational incidents (WP 7.6)
5. Controlled operational notifications (WP 7.7)
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Optional

from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    get_topology_connection,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.db")

OPERATIONAL_SCHEMA_SQL = """
-- 1. Business Services Catalog
CREATE TABLE IF NOT EXISTS operational_services (
    service_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    criticality TEXT NOT NULL CHECK(criticality IN ('TIER_1_MISSION_CRITICAL', 'TIER_2_BUSINESS_OPERATIONAL', 'TIER_3_OFFICE_PRODUCTIVITY', 'TIER_4_DEVELOPMENT_TEST')),
    owner_team TEXT,
    health_score REAL DEFAULT 100.0,
    status TEXT NOT NULL DEFAULT 'HEALTHY' CHECK(status IN ('HEALTHY', 'DEGRADED', 'AT_RISK', 'DOWN', 'UNKNOWN')),
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Service Endpoints & Network Bindings
CREATE TABLE IF NOT EXISTS operational_service_endpoints (
    endpoint_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL REFERENCES operational_services(service_id) ON DELETE CASCADE,
    endpoint_type TEXT NOT NULL CHECK(endpoint_type IN ('IP_PORT', 'SUBNET', 'VLAN', 'URL', 'HOSTNAME')),
    endpoint_value TEXT NOT NULL,
    target_device_id TEXT,
    target_interface TEXT,
    is_primary INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 3. Operational Scheduled Jobs
CREATE TABLE IF NOT EXISTS operational_jobs (
    job_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    description TEXT,
    schedule_type TEXT NOT NULL CHECK(schedule_type IN ('CRON', 'INTERVAL', 'DAILY', 'WEEKLY', 'MONTHLY')),
    schedule_expression TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    missed_strategy TEXT NOT NULL DEFAULT 'RUN_IMMEDIATELY' CHECK(missed_strategy IN ('RUN_IMMEDIATELY', 'SKIP', 'RESCHEDULE')),
    parameters_json TEXT DEFAULT '{}',
    last_run_at TEXT,
    last_status TEXT,
    next_due_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 4. Operational Job Run History
CREATE TABLE IF NOT EXISTS operational_job_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES operational_jobs(job_id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL CHECK(trigger_type IN ('SCHEDULED', 'MANUAL', 'MISSED_RECOVERY')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCESS', 'WARNING', 'FAILED', 'SKIPPED')),
    duration_ms INTEGER,
    result_summary TEXT,
    result_data_json TEXT,
    error_message TEXT
);

-- 5. Maintenance Windows & Calendar Events
CREATE TABLE IF NOT EXISTS operational_maintenance_windows (
    window_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    source_provider TEXT NOT NULL DEFAULT 'LOCAL' CHECK(source_provider IN ('LOCAL', 'GOOGLE', 'ICS')),
    external_event_id TEXT,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('DEVICE', 'SERVICE', 'INTERFACE', 'GLOBAL')),
    target_entities_json TEXT NOT NULL DEFAULT '[]',
    start_time_utc TEXT NOT NULL,
    end_time_utc TEXT NOT NULL,
    start_time_local TEXT NOT NULL,
    end_time_local TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    suppress_alerts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 6. Proactive Operational Incidents
CREATE TABLE IF NOT EXISTS operational_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    state TEXT NOT NULL DEFAULT 'DETECTED' CHECK(state IN ('DETECTED', 'ACKNOWLEDGED', 'INVESTIGATING', 'MITIGATED', 'RESOLVED', 'CLOSED')),
    source_engine TEXT NOT NULL CHECK(source_engine IN ('PREDICTIVE', 'ANOMALY', 'CHANGE_SIMULATION', 'MANUAL')),
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    affected_devices_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    root_cause_analysis TEXT,
    remediation_plan TEXT,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

-- 7. Operational Notifications Log
CREATE TABLE IF NOT EXISTS operational_notifications (
    notification_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'SENT' CHECK(delivery_status IN ('SENT', 'QUEUED_QUIET_HOURS', 'SUPPRESSED_COOLDOWN')),
    target_channels_json TEXT NOT NULL DEFAULT '["IN_APP", "WEBSOCKET"]',
    metadata_json TEXT DEFAULT '{}',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Performance and deduplication indexes
CREATE INDEX IF NOT EXISTS idx_op_jobs_next_due ON operational_jobs(is_enabled, next_due_at);
CREATE INDEX IF NOT EXISTS idx_op_runs_job_id ON operational_job_runs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_maint_times ON operational_maintenance_windows(start_time_utc, end_time_utc, status);
CREATE INDEX IF NOT EXISTS idx_op_incidents_state ON operational_incidents(state, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_notif_dedup ON operational_notifications(dedup_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_notif_read ON operational_notifications(is_read, created_at DESC);

-- ===========================================================================
-- NETWORKING VIII / PHASE C: OPERATIONAL DECISION INTELLIGENCE & SLA ENGINE
-- ===========================================================================

-- 8. Operational Decisions (WP 8.5)
CREATE TABLE IF NOT EXISTS operational_decisions (
    decision_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    site_id TEXT,
    title TEXT NOT NULL,
    priority_score REAL NOT NULL,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'INFO', 'WATCH', 'WARNING', 'UNKNOWN')),
    status TEXT NOT NULL DEFAULT 'GENERATED' CHECK(status IN ('GENERATED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'DEFERRED', 'EXPIRED', 'COMPLETED', 'VERIFIED')),
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    affected_devices_json TEXT NOT NULL DEFAULT '[]',
    assessment_json TEXT NOT NULL,
    recommendation_json TEXT NOT NULL,
    sla_impact_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 9. Append-Only Decision History
CREATE TABLE IF NOT EXISTS operational_decision_history (
    history_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES operational_decisions(decision_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 10. Multi-Dimensional Health Scores (WP 8.5.1)
CREATE TABLE IF NOT EXISTS operational_health_scores (
    score_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    site_id TEXT,
    dimension TEXT NOT NULL CHECK(dimension IN ('DEVICE', 'INTERFACE', 'SITE', 'SERVICE', 'GATEWAY', 'TENANT')),
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('HEALTHY', 'DEGRADED', 'WARNING', 'CRITICAL', 'UNKNOWN', 'INSUFFICIENT_DATA')),
    score REAL,
    confidence REAL NOT NULL DEFAULT 1.0,
    contributing_factors_json TEXT NOT NULL DEFAULT '[]',
    missing_dimensions_json TEXT NOT NULL DEFAULT '[]',
    calculated_at TEXT NOT NULL
);

-- 11. Customer SLA Policies (WP 8.7)
CREATE TABLE IF NOT EXISTS operational_sla_policies (
    policy_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_availability REAL NOT NULL DEFAULT 99.9,
    target_response_time_ms REAL DEFAULT 150.0,
    target_mttr_minutes INTEGER DEFAULT 60,
    window_type TEXT NOT NULL DEFAULT 'MONTHLY' CHECK(window_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'ROLLING_30D')),
    maintenance_excluded INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, service_id)
);

-- 12. SLA Measurement Reports (WP 8.7)
CREATE TABLE IF NOT EXISTS operational_sla_reports (
    report_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    policy_id TEXT NOT NULL REFERENCES operational_sla_policies(policy_id) ON DELETE CASCADE,
    period_start_utc TEXT NOT NULL,
    period_end_utc TEXT NOT NULL,
    target_availability REAL NOT NULL,
    measured_availability REAL,
    total_downtime_seconds REAL NOT NULL DEFAULT 0.0,
    maintenance_excluded_seconds REAL NOT NULL DEFAULT 0.0,
    data_coverage_percent REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('COMPLIANT', 'AT_RISK', 'BREACHED', 'INSUFFICIENT_COVERAGE')),
    error_budget_remaining_percent REAL,
    incident_count INTEGER NOT NULL DEFAULT 0,
    details_json TEXT DEFAULT '{}',
    generated_at TEXT NOT NULL
);

-- Phase C Indexes
CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON operational_decisions(tenant_id, site_id, status);
CREATE INDEX IF NOT EXISTS idx_decisions_priority ON operational_decisions(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_decision_hist_dec ON operational_decision_history(decision_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_lookup ON operational_health_scores(tenant_id, dimension, entity_id, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_state ON operational_health_scores(tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_sla_report_lookup ON operational_sla_reports(tenant_id, service_id, period_start_utc DESC);
"""


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Safely adds a column to an existing table if it does not already exist."""
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if cols and column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except Exception as exc:
        logger.debug("Column addition check (%s.%s) skipped: %s", table, column, exc)


def ensure_operational_schema(db_path: Optional[Path] = None) -> None:
    """Idempotently initializes all operational tables and indexes in topology.db."""
    target_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with topology_transaction(target_path, write=True) as conn:
        conn.executescript(OPERATIONAL_SCHEMA_SQL)
        # Idempotently ensure tenant_id & site_id columns on legacy operational tables
        _add_column_if_missing(conn, "operational_services", "tenant_id", "TEXT")
        _add_column_if_missing(conn, "operational_services", "site_id", "TEXT")
        _add_column_if_missing(conn, "operational_service_endpoints", "tenant_id", "TEXT")
        _add_column_if_missing(conn, "operational_incidents", "tenant_id", "TEXT")
        _add_column_if_missing(conn, "operational_incidents", "site_id", "TEXT")
        _add_column_if_missing(conn, "operational_notifications", "tenant_id", "TEXT")
    logger.info("Operational schema verified in %s", target_path)
