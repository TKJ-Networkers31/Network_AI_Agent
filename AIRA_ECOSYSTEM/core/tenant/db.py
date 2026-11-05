"""
AIRA OS — Multi-Tenant, Identity & Customer Inventory Persistence (Networking VIII).

Manages relational schema, indexes, and migrations in topology.db for:
- Tenants & Configurations
- Subscriptions & Quotas
- Users, Roles, Permissions & Active Sessions
- Sites, Groups & Customer Network Devices (Overlap RFC 1918 safe)
- Immutable Platform Audit Log
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Optional

from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.tenant.db")

TENANT_SCHEMA_SQL = """
-- 1. Tenants (Customer Organizations)
CREATE TABLE IF NOT EXISTS operational_tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('PROVISIONING', 'ACTIVE', 'SUSPENDED', 'MAINTENANCE', 'DECOMMISSIONED')),
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Tenant Subscriptions & Resource Limits
CREATE TABLE IF NOT EXISTS operational_tenant_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    tier TEXT NOT NULL DEFAULT 'STANDARD' CHECK(tier IN ('COMMUNITY', 'STANDARD', 'ENTERPRISE', 'CUSTOM')),
    max_sites INTEGER NOT NULL DEFAULT 10,
    max_devices INTEGER NOT NULL DEFAULT 100,
    max_gateways INTEGER NOT NULL DEFAULT 10,
    is_active INTEGER NOT NULL DEFAULT 1,
    valid_until_utc TEXT,
    created_at TEXT NOT NULL
);

-- 3. Customer Profile & Business Details
CREATE TABLE IF NOT EXISTS operational_customer_profiles (
    profile_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    contact_phone TEXT,
    address TEXT,
    sla_tier TEXT NOT NULL DEFAULT 'TIER_2_BUSINESS_OPERATIONAL',
    notes TEXT,
    created_at TEXT NOT NULL
);

-- 4. Users (Internal NOC and Customer Users)
CREATE TABLE IF NOT EXISTS operational_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    is_internal INTEGER NOT NULL DEFAULT 0,
    tenant_id TEXT REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 5. User Role Assignments
CREATE TABLE IF NOT EXISTS operational_user_roles (
    assignment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    role_type TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    UNIQUE(user_id, role_type)
);

-- 6. User Sessions & Tokens
CREATE TABLE IF NOT EXISTS operational_user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    tenant_id TEXT,
    is_internal INTEGER NOT NULL DEFAULT 0,
    token_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    created_at TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL
);

-- 7. Site Groups
CREATE TABLE IF NOT EXISTS operational_site_groups (
    group_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, name)
);

-- 8. Customer Sites
CREATE TABLE IF NOT EXISTS operational_sites (
    site_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    group_id TEXT REFERENCES operational_site_groups(group_id) ON DELETE SET NULL,
    address TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
    contact_person TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, slug)
);

-- 9. Customer Network Inventory (Overlap RFC 1918 Safe)
CREATE TABLE IF NOT EXISTS operational_devices (
    device_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES operational_sites(site_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    management_ip TEXT NOT NULL,
    management_port INTEGER NOT NULL DEFAULT 22,
    device_type TEXT NOT NULL DEFAULT 'ROUTER' CHECK(device_type IN ('ROUTER', 'SWITCH', 'FIREWALL', 'ACCESS_POINT', 'SERVER', 'OTHER')),
    vendor TEXT NOT NULL DEFAULT 'MikroTik',
    model TEXT,
    os_version TEXT,
    gateway_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'INACTIVE', 'MAINTENANCE', 'UNREACHABLE')),
    credential_ref TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, site_id, management_ip)
);

-- 10. Platform Audit Log (Immutable append-only audit trail)
CREATE TABLE IF NOT EXISTS operational_audit_log (
    audit_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    user_id TEXT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    ip_address TEXT,
    timestamp_utc TEXT NOT NULL
);

-- 11. Customer Support Requests (WP 8.9.9)
CREATE TABLE IF NOT EXISTS operational_support_requests (
    request_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    requester_id TEXT NOT NULL REFERENCES operational_users(user_id),
    category TEXT NOT NULL CHECK(category IN ('INCIDENT', 'SERVICE_REQUEST', 'BILLING', 'GENERAL', 'CHANGE')),
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'WAITING_CUSTOMER', 'RESOLVED', 'CLOSED')),
    assigned_operator_id TEXT REFERENCES operational_users(user_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

-- 12. Support Request Comments (WP 8.9.9)
CREATE TABLE IF NOT EXISTS operational_support_request_comments (
    comment_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES operational_support_requests(request_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    author_id TEXT NOT NULL REFERENCES operational_users(user_id),
    author_name TEXT NOT NULL,
    is_internal INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 13. Customer Notification Preferences (WP 8.9.8)
CREATE TABLE IF NOT EXISTS operational_customer_notification_preferences (
    pref_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    notify_critical_incidents INTEGER NOT NULL DEFAULT 1,
    notify_major_incidents INTEGER NOT NULL DEFAULT 1,
    notify_service_degradation INTEGER NOT NULL DEFAULT 1,
    notify_gateway_offline INTEGER NOT NULL DEFAULT 1,
    notify_sla_breach INTEGER NOT NULL DEFAULT 1,
    email_notifications INTEGER NOT NULL DEFAULT 1,
    in_app_notifications INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id)
);

-- Performance and Tenant Scoping Indexes
CREATE INDEX IF NOT EXISTS idx_tenant_status ON operational_tenants(status);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON operational_users(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON operational_user_sessions(token_hash, status);
CREATE INDEX IF NOT EXISTS idx_sites_tenant ON operational_sites(tenant_id, site_id);
CREATE INDEX IF NOT EXISTS idx_devices_tenant_site ON operational_devices(tenant_id, site_id, status);
CREATE INDEX IF NOT EXISTS idx_devices_ip_lookup ON operational_devices(tenant_id, site_id, management_ip);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON operational_audit_log(tenant_id, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_support_tenant ON operational_support_requests(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_support_requester ON operational_support_requests(requester_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_comments ON operational_support_request_comments(request_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_notif_pref ON operational_customer_notification_preferences(tenant_id, user_id);
"""


def ensure_tenant_schema(db_path: Optional[Path] = None) -> None:
    """Idempotently initializes all multi-tenant and identity tables in topology.db."""
    target_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with topology_transaction(target_path, write=True) as conn:
        conn.executescript(TENANT_SCHEMA_SQL)
    logger.info("Multi-Tenant schema initialized successfully in %s", target_path)
