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
from datetime import datetime, timezone

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

-- 14. Tenant Entitlements (Networking++ and specialized add-ons)
CREATE TABLE IF NOT EXISTS operational_tenant_entitlements (
    entitlement_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    entitlement_key TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    granted_at TEXT NOT NULL,
    expires_at_utc TEXT,
    metadata_json TEXT DEFAULT '{}',
    UNIQUE(tenant_id, entitlement_key)
);

-- 15. Token Policies (Configurable token allocation, limits & costs)
CREATE TABLE IF NOT EXISTS operational_token_policies (
    policy_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL DEFAULT 'GLOBAL' CHECK(scope_type IN ('GLOBAL', 'TENANT', 'USER')),
    scope_id TEXT,
    tier TEXT NOT NULL DEFAULT 'FREE' CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM')),
    monthly_token_allocation INTEGER NOT NULL DEFAULT 100000,
    daily_token_limit INTEGER NOT NULL DEFAULT 10000,
    networking_plus_enabled INTEGER NOT NULL DEFAULT 0,
    model_cost_mult_json TEXT NOT NULL DEFAULT '{}',
    tool_cost_matrix_json TEXT NOT NULL DEFAULT '{}',
    max_request_size_tokens INTEGER NOT NULL DEFAULT 32768,
    rate_limit_rpm INTEGER NOT NULL DEFAULT 60,
    updated_at TEXT NOT NULL,
    UNIQUE(scope_type, scope_id, tier)
);

-- 16. Token Balances (Atomic user & tenant token metering)
CREATE TABLE IF NOT EXISTS operational_token_balances (
    balance_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT,
    tier TEXT NOT NULL DEFAULT 'FREE',
    allocated_tokens INTEGER NOT NULL DEFAULT 100000,
    used_tokens INTEGER NOT NULL DEFAULT 0,
    period_start_utc TEXT NOT NULL,
    period_reset_utc TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id)
);

-- 17. Token Usage Ledger (Granular per-request and per-tool accounting)
CREATE TABLE IF NOT EXISTS operational_token_usage_ledger (
    usage_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    model_name TEXT,
    feature_name TEXT NOT NULL DEFAULT 'chat',
    tool_name TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_credits REAL NOT NULL DEFAULT 0.0,
    timestamp_utc TEXT NOT NULL
);

-- 18. Centralized Approval Preferences (Always ask, risk levels, auto-approvals)
CREATE TABLE IF NOT EXISTS operational_approval_preferences (
    pref_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT,
    policy_mode TEXT NOT NULL DEFAULT 'ASK_HIGH_RISK' CHECK(policy_mode IN ('ALWAYS_ASK', 'ASK_HIGH_RISK', 'AUTO_APPROVE_LOW_RISK', 'CUSTOM')),
    require_config_deploy_approval INTEGER NOT NULL DEFAULT 1,
    require_credential_change_approval INTEGER NOT NULL DEFAULT 1,
    require_user_change_approval INTEGER NOT NULL DEFAULT 1,
    never_auto_approve_destructive INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id)
);

-- 19. Pending Approvals Queue
CREATE TABLE IF NOT EXISTS operational_pending_approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    requester_id TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    action_name TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'CATEGORY_B' CHECK(risk_level IN ('CATEGORY_A', 'CATEGORY_B', 'CATEGORY_C')),
    target_resources_json TEXT NOT NULL DEFAULT '[]',
    params_json TEXT NOT NULL DEFAULT '{}',
    diff_text TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    reviewer_id TEXT,
    review_notes TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
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
CREATE INDEX IF NOT EXISTS idx_entitlements_lookup ON operational_tenant_entitlements(tenant_id, entitlement_key, is_enabled);
CREATE INDEX IF NOT EXISTS idx_token_policy_scope ON operational_token_policies(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_token_balance_tenant ON operational_token_balances(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_tenant ON operational_token_usage_ledger(tenant_id, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_tenant ON operational_pending_approvals(tenant_id, status);

-- 20. User-Specific Subscriptions & Entitlements (Directive Section 5)
CREATE TABLE IF NOT EXISTS operational_user_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL DEFAULT 'FREE' CHECK(plan_id IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM')),
    subscription_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(subscription_status IN ('PENDING', 'ACTIVE', 'EXPIRED', 'SUSPENDED', 'CANCELLED')),
    starts_at TEXT NOT NULL,
    expires_at TEXT,
    renewal_status TEXT NOT NULL DEFAULT 'MANUAL' CHECK(renewal_status IN ('AUTO', 'MANUAL', 'NONE')),
    token_quota INTEGER NOT NULL DEFAULT 10000,
    token_consumed INTEGER NOT NULL DEFAULT 0,
    networking_addon_status INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id)
);

-- 21. Billing Foundation — Products & Plans (Directive Section 6)
CREATE TABLE IF NOT EXISTS operational_billing_products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operational_billing_plans (
    plan_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES operational_billing_products(product_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE')),
    has_networking_plus INTEGER NOT NULL DEFAULT 0,
    monthly_tokens INTEGER NOT NULL DEFAULT 10000,
    price_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IDR',
    interval_months INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 22. Billing Foundation — Invoices & Transactions
CREATE TABLE IF NOT EXISTS operational_billing_invoices (
    invoice_id TEXT PRIMARY KEY,
    subscription_id TEXT REFERENCES operational_user_subscriptions(subscription_id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IDR',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('DRAFT', 'PENDING', 'PAID', 'FAILED', 'VOID')),
    due_date TEXT,
    paid_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operational_billing_transactions (
    transaction_id TEXT PRIMARY KEY,
    invoice_id TEXT REFERENCES operational_billing_invoices(invoice_id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    provider_name TEXT NOT NULL DEFAULT 'MOCK_GATEWAY',
    provider_ref TEXT,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'IDR',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')),
    idempotency_key TEXT UNIQUE,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operational_billing_webhook_events (
    event_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    signature TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

-- 23. Ansible-Compatible Playbooks & Workflows (Directive Section 8)
CREATE TABLE IF NOT EXISTS operational_playbooks (
    playbook_id TEXT PRIMARY KEY,
    tenant_id TEXT REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'GENERAL',
    description TEXT NOT NULL,
    yaml_content TEXT NOT NULL,
    variables_schema_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'CATEGORY_A' CHECK(risk_level IN ('CATEGORY_A', 'CATEGORY_B', 'CATEGORY_C')),
    is_builtin INTEGER NOT NULL DEFAULT 0,
    version TEXT NOT NULL DEFAULT '1.0.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 24. Token Quota Adjustments & Reset History (Directive Section 8)
CREATE TABLE IF NOT EXISTS operational_token_quota_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL,
    target_user_id TEXT NOT NULL,
    previous_quota INTEGER NOT NULL,
    new_quota INTEGER NOT NULL,
    adjustment_type TEXT NOT NULL DEFAULT 'MANUAL' CHECK(adjustment_type IN ('MANUAL', 'BONUS', 'RESET', 'MANUAL_OVERRIDE', 'BONUS_GRANT')),
    reason TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL
);

-- 25. Phase F: Network Workspaces (Isolated networking environment per user)
CREATE TABLE IF NOT EXISTS network_workspaces (
    workspace_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES operational_tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nw_workspace_user ON network_workspaces(user_id);
CREATE INDEX IF NOT EXISTS idx_nw_workspace_tenant ON network_workspaces(tenant_id);

-- 26. Phase F: User Personalization Preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    pref_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES operational_users(user_id) ON DELETE CASCADE,
    memory_enabled INTEGER NOT NULL DEFAULT 1,
    active_persona_id TEXT,
    custom_instructions TEXT DEFAULT '',
    settings_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_pref_user ON user_preferences(user_id);

-- 27. Phase F: User Memories (Isolated Context Memory with Category & Relevance)
CREATE TABLE IF NOT EXISTS user_memories (
    memory_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES operational_users(user_id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK(category IN ('learning', 'technical', 'project', 'communication', 'workflows', 'general')),
    content TEXT NOT NULL,
    source TEXT DEFAULT 'USER',
    importance REAL NOT NULL DEFAULT 0.5,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, category);
CREATE INDEX IF NOT EXISTS idx_user_memories_created ON user_memories(user_id, created_at);

-- 28. Phase F: User Personas (Custom AI Behavior Profiles & System Presets)
CREATE TABLE IF NOT EXISTS user_personas (
    persona_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES operational_users(user_id) ON DELETE CASCADE, -- NULL means system-wide built-in preset
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    response_style TEXT NOT NULL DEFAULT 'concise',
    language TEXT NOT NULL DEFAULT 'id',
    technical_depth INTEGER NOT NULL DEFAULT 80,
    explanation_preference TEXT NOT NULL DEFAULT 'technical',
    custom_instructions TEXT DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_personas_user ON user_personas(user_id);

-- Additional Indexes for Phase E & E.1 & Phase F
CREATE INDEX IF NOT EXISTS idx_user_sub_status ON operational_user_subscriptions(user_id, subscription_status);
CREATE INDEX IF NOT EXISTS idx_billing_invoice_user ON operational_billing_invoices(user_id, status);
CREATE INDEX IF NOT EXISTS idx_billing_txn_user ON operational_billing_transactions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_billing_webhook ON operational_billing_webhook_events(provider_name, event_type, processed);
CREATE INDEX IF NOT EXISTS idx_playbooks_tenant ON operational_playbooks(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_quota_adj_user ON operational_token_quota_adjustments(target_user_id, timestamp_utc DESC);


"""


def ensure_tenant_schema(db_path: Optional[Path] = None) -> None:
    """Idempotently initializes all multi-tenant, identity, and entitlement tables in topology.db."""
    target_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with topology_transaction(target_path, write=True) as conn:
        conn.executescript(TENANT_SCHEMA_SQL)
        # Safely add auth columns to operational_users if upgrading from older schema
        for col_def in [
            "email_verified INTEGER NOT NULL DEFAULT 1",
            "verification_token_hash TEXT",
            "reset_token_hash TEXT",
            "reset_token_expires_at TEXT",
            "google_id TEXT",
            "auth_provider TEXT NOT NULL DEFAULT 'LOCAL'",
            "must_change_password INTEGER NOT NULL DEFAULT 0",
            "mfa_enabled INTEGER NOT NULL DEFAULT 0",
            "mfa_secret TEXT",
            "failed_login_attempts INTEGER NOT NULL DEFAULT 0",
            "locked_until_utc TEXT",
            "last_login_at TEXT",
            "last_login_ip TEXT",
        ]:
            col_name = col_def.split()[0]
            try:
                conn.execute(f"ALTER TABLE operational_users ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Safely add quota reset columns to operational_token_policies
        for pol_col in [
            "reset_period TEXT NOT NULL DEFAULT 'MONTHLY'",
            "reset_type TEXT NOT NULL DEFAULT 'CALENDAR'",
            "reset_timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta'",
        ]:
            try:
                conn.execute(f"ALTER TABLE operational_token_policies ADD COLUMN {pol_col}")
            except sqlite3.OperationalError:
                pass
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_tenants (
                tenant_id, name, slug, status, config_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant_default",
                "Default Organization",
                "default-org",
                "ACTIVE",
                "{}",
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_tenants (
                tenant_id, name, slug, status, config_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant_guest",
                "Guest Sandbox",
                "guest-sandbox",
                "ACTIVE",
                "{}",
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_tenant_subscriptions (
                subscription_id, tenant_id, tier, max_sites, max_devices, max_gateways, is_active, created_at
            ) VALUES (?, ?, ?, 10, 100, 10, 1, ?)
            """,
            (
                "sub_default",
                "tenant_default",
                "STANDARD",
                now_iso,
            ),
        )
    
        # Seed default products & plans
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_billing_products (product_id, name, description, is_active, created_at)
            VALUES ('prod_aira_workspace', 'AIRA Workspace', 'Core AI-native Network Engineering Workspace', 1, ?)
            """,
            (now_iso,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_billing_products (product_id, name, description, is_active, created_at)
            VALUES ('prod_netplus_addon', 'Networking++ Add-on', 'Advanced topology, NMS telemetry & Playbook execution', 1, ?)
            """,
            (now_iso,),
        )
        default_plans = [
            ('plan_free', 'prod_aira_workspace', 'AIRA Free', 'FREE', 0, 10000, 0, 'IDR', 1),
            ('plan_pro', 'prod_aira_workspace', 'AIRA Pro', 'PRO', 0, 100000, 25000000, 'IDR', 1),
            ('plan_pro_netplus', 'prod_aira_workspace', 'AIRA Pro + Networking++', 'PRO', 1, 150000, 50000000, 'IDR', 1),
            ('plan_enterprise', 'prod_aira_workspace', 'AIRA Enterprise', 'ENTERPRISE', 1, 1000000, 150000000, 'IDR', 1),
            ('plan_netplus_addon', 'prod_netplus_addon', 'Networking++ Standalone Add-on', 'FREE', 1, 50000, 30000000, 'IDR', 1),
        ]
        for p in default_plans:
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_billing_plans (
                    plan_id, product_id, name, tier, has_networking_plus,
                    monthly_tokens, price_cents, currency, interval_months, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (*p, now_iso),
            )

        # Seed default token policies for GUEST, FREE, PRO, ENTERPRISE
        default_policies = [
            ("pol_global_guest", "GLOBAL", None, "GUEST", 15000, 2000, 0, "MONTHLY", "CALENDAR", "Asia/Jakarta", 20),
            ("pol_global_free", "GLOBAL", None, "FREE", 100000, 10000, 0, "MONTHLY", "CALENDAR", "Asia/Jakarta", 30),
            ("pol_global_pro", "GLOBAL", None, "PRO", 2000000, 200000, 0, "MONTHLY", "CALENDAR", "Asia/Jakarta", 120),
            ("pol_global_enterprise", "GLOBAL", None, "ENTERPRISE", 10000000, 1000000, 1, "MONTHLY", "CALENDAR", "Asia/Jakarta", 300),
        ]
        for pol in default_policies:
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_token_policies (
                    policy_id, scope_type, scope_id, tier, monthly_token_allocation, daily_token_limit,
                    networking_plus_enabled, reset_period, reset_type, reset_timezone, rate_limit_rpm, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*pol, now_iso),
            )

        # -------------------------------------------------------------
        # Phase F: Safe Migrations for Workspace Isolation & Networking
        # -------------------------------------------------------------
        networking_tables = [
            "topology_nodes", "topology_edges", "topology_links",
            "topology_snapshots", "topology_discovery_jobs",
            "nms_device_profiles", "nms_device_metrics", "nms_interface_metrics",
            "nms_raw_metrics", "nms_incidents", "operational_devices", "operational_playbooks"
        ]
        for tbl in networking_tables:
            # Check if table exists in target database
            t_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (tbl,)).fetchone()
            if t_exists:
                for col in ["workspace_id TEXT", "user_id TEXT"]:
                    try:
                        conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
                    except sqlite3.OperationalError:
                        pass
                try:
                    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_ws_user ON {tbl}(workspace_id, user_id)")
                except sqlite3.OperationalError:
                    pass

        # Seed System Built-in Personas (owner_id = NULL)
        builtin_personas = [
            (
                "preset_general", None, "General Assistant",
                "Asisten AI adaptif dan cerdas untuk bantuan harian dan pemecahan masalah umum.",
                "concise", "id", 70, "conceptual", "", 1
            ),
            (
                "preset_technical", None, "Technical Engineer",
                "Insinyur jaringan senior yang presisi, mengutamakan diagnosa berbasis RFC, CLI, dan data telemetri aktual.",
                "technical", "id", 95, "technical", "Utamakan bukti command show, latency ms, dan konfigurasi interface yang tepat.", 0
            ),
            (
                "preset_tutor", None, "Learning Tutor",
                "Tutor interaktif yang sabar menerangkan konsep jaringan, topologi, dan otomatisasi langkah demi langkah.",
                "friendly", "id", 65, "hands-on", "Jelaskan analogi yang mudah dipahami sebelum masuk ke syntax teknis.", 0
            ),
            (
                "preset_consultant", None, "Professional Consultant",
                "Konsultan arsitektur infrastruktur berorientasi rekomendasi strategis, SLA, efisiensi biaya, dan keamanan tingkat enterprise.",
                "formal", "id", 90, "strategic", "Fokus pada mitigasi risiko, compliance keamanan, dan ketahanan SLA.", 0
            ),
            (
                "preset_custom", None, "Custom Persona",
                "Persona dasar yang dapat disesuaikan penuh sesuai kebutuhan alur kerja pribadi Anda.",
                "concise", "id", 80, "technical", "", 0
            ),
        ]
        for bp in builtin_personas:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_personas (
                    persona_id, user_id, name, description, response_style,
                    language, technical_depth, explanation_preference, custom_instructions,
                    is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*bp, now_iso, now_iso),
            )

        # Legacy Data Ownership Mapping:
        # If lingga_admin exists, ensure default network workspace and associate unowned networking resources
        lingga_row = conn.execute("SELECT user_id, tenant_id FROM operational_users WHERE username = 'lingga_admin'").fetchone()
        if lingga_row:
            l_uid = lingga_row[0]
            l_tid = lingga_row[1] or "tenant_internal"
            ws_id = f"ws_lingga_default"
            conn.execute(
                """
                INSERT OR IGNORE INTO network_workspaces (
                    workspace_id, user_id, tenant_id, name, description, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, 'Lingga Primary Network Workspace', 'Default workspace for platform owner', 1, ?, ?)
                """,
                (ws_id, l_uid, l_tid, now_iso, now_iso),
            )

            # Map legacy unowned data to lingga's default workspace
            for tbl in ["topology_nodes", "operational_devices", "operational_playbooks"]:
                t_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (tbl,)).fetchone()
                if t_exists:
                    try:
                        conn.execute(
                            f"UPDATE {tbl} SET workspace_id = ?, user_id = ? WHERE workspace_id IS NULL OR workspace_id = ''",
                            (ws_id, l_uid),
                        )
                    except sqlite3.OperationalError:
                        pass

        logger.info("Multi-Tenant schema initialized successfully in %s", target_path)
