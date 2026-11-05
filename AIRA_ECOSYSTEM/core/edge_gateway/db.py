"""
AIRA OS — Edge Gateway Persistence & Schema Management (Networking VIII / WP 8.4).

Manages relational tables and composite indexes in topology.db for:
- Registered edge gateways
- Short-lived single-use enrollment tokens
- Monotonic sequence numbers and replay tracking
- Gateway heartbeat logs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.edge_gateway.db")

GATEWAY_SCHEMA_SQL = """
-- 1. Edge Gateways
CREATE TABLE IF NOT EXISTS operational_gateways (
    gateway_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES operational_sites(site_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('PROVISIONING', 'ENROLLMENT_PENDING', 'ACTIVE', 'DEGRADED', 'OFFLINE', 'REVOKED', 'DECOMMISSIONED')),
    version TEXT NOT NULL DEFAULT '1.0.0',
    certificate_fingerprint TEXT,
    auth_token_hash TEXT,
    last_seen_at_utc TEXT,
    last_ip TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, site_id, name)
);

-- 2. Short-Lived Single-Use Enrollment Tokens
CREATE TABLE IF NOT EXISTS operational_gateway_tokens (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES operational_sites(site_id) ON DELETE CASCADE,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'REDEEMED', 'EXPIRED', 'REVOKED')),
    expires_at_utc TEXT NOT NULL,
    redeemed_at_utc TEXT,
    created_at TEXT NOT NULL
);

-- 3. Monotonic Sequence Tracking & Replay Prevention
CREATE TABLE IF NOT EXISTS operational_gateway_sequences (
    gateway_id TEXT PRIMARY KEY REFERENCES operational_gateways(gateway_id) ON DELETE CASCADE,
    last_sequence_number INTEGER NOT NULL DEFAULT 0,
    last_received_at_utc TEXT NOT NULL,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    dropped_count INTEGER NOT NULL DEFAULT 0
);

-- 4. Gateway Heartbeat History
CREATE TABLE IF NOT EXISTS operational_gateway_heartbeats (
    heartbeat_id TEXT PRIMARY KEY,
    gateway_id TEXT NOT NULL REFERENCES operational_gateways(gateway_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    cpu_utilization REAL DEFAULT 0.0,
    memory_utilization REAL DEFAULT 0.0,
    queue_depth INTEGER DEFAULT 0,
    collector_status TEXT DEFAULT 'HEALTHY',
    raw_json TEXT DEFAULT '{}'
);

-- Performance and Tenant Scoping Indexes
CREATE INDEX IF NOT EXISTS idx_gateways_tenant_site ON operational_gateways(tenant_id, site_id, status);
CREATE INDEX IF NOT EXISTS idx_gateway_tokens_lookup ON operational_gateway_tokens(token_hash, status);
CREATE INDEX IF NOT EXISTS idx_gateway_hb_time ON operational_gateway_heartbeats(gateway_id, timestamp_utc DESC);

-- 5. NMS Raw Metrics (Shared Telemetry Store)
CREATE TABLE IF NOT EXISTS nms_raw_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    interface_name TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '%',
    semantic_type TEXT NOT NULL DEFAULT 'COUNTER_RATE',
    source_protocol TEXT NOT NULL DEFAULT 'EDGE_GATEWAY',
    quality TEXT NOT NULL DEFAULT 'RELIABLE',
    measured_at REAL NOT NULL,
    collected_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nms_raw_query ON nms_raw_metrics(device_id, metric_name, measured_at);
CREATE INDEX IF NOT EXISTS idx_nms_raw_iface ON nms_raw_metrics(device_id, interface_name, metric_name, measured_at);
CREATE INDEX IF NOT EXISTS idx_nms_raw_cleanup ON nms_raw_metrics(measured_at);
"""


def ensure_gateway_schema(db_path: Optional[Path] = None) -> None:
    """Idempotently initializes all edge gateway tables and indexes in topology.db."""
    target_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with topology_transaction(target_path, write=True) as conn:
        conn.executescript(GATEWAY_SCHEMA_SQL)
    logger.info("Edge Gateway schema initialized successfully in %s", target_path)
