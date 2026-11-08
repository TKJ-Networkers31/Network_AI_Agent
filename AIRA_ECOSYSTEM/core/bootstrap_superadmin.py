"""
AIRA OS — Superadmin Bootstrap Engine.
Provisions and hardens the primary platform owner account: lingga_admin.

Security guarantees:
- Idempotent provisioning (will not overwrite existing password without explicit --force-reset)
- No hardcoded initial password in source code
- High-iteration PBKDF2-HMAC-SHA256 password hashing
- Must-change-password flag enforced on initial login
- Full Platform Superadmin RBAC role and Networking++ entitlement
- Immutable audit log recording
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import uuid

# Ensure root paths resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.db import ensure_tenant_schema
from core.tenant.models import UserRoleType
from core.tenant.manager import _hash_password

logger = logging.getLogger("aira.bootstrap")

SUPERADMIN_USERNAME = "lingga_admin"
SUPERADMIN_EMAIL = "admin@aira.infra.corp"


def bootstrap_superadmin(
    password: str | None = None,
    force_reset: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, any]:
    """
    Idempotently provisions the lingga_admin SUPERADMIN account.
    """
    target_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
    ensure_tenant_schema(target_path)

    now_iso = datetime.now(timezone.utc).isoformat()
    raw_password = password or os.getenv("AIRA_SUPERADMIN_PASSWORD") or secrets.token_urlsafe(16)

    with topology_transaction(target_path, write=True) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Ensure internal tenant exists
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_tenants (
                tenant_id, name, slug, status, config_json, created_at, updated_at
            ) VALUES ('tenant_internal', 'AIRA Internal Operations', 'aira-internal', 'ACTIVE', '{}', ?, ?)
            """,
            (now_iso, now_iso),
        )

        # 2. Check if lingga_admin already exists
        existing = conn.execute(
            "SELECT * FROM operational_users WHERE username = ?",
            (SUPERADMIN_USERNAME,),
        ).fetchone()

        if existing and not force_reset:
            user_id = existing["user_id"]
            # Ensure roles, group membership and active status
            conn.execute("UPDATE operational_users SET account_enabled = 1, is_active = 1 WHERE user_id = ?", (user_id,))
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_user_group_memberships (user_id, group_id, assigned_at)
                VALUES (?, 'grp_super_admin', ?)
                """,
                (user_id, now_iso),
            )
            for r in (UserRoleType.PLATFORM_OWNER.value, UserRoleType.PLATFORM_SUPER_ADMIN.value):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO operational_user_roles (assignment_id, user_id, role_type, granted_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (f"asgn_{uuid.uuid4().hex[:12]}", user_id, r, now_iso),
                )
            # Ensure audit log
            conn.execute(
                """
                INSERT INTO operational_audit_log (
                    audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, timestamp_utc
                ) VALUES (?, 'tenant_internal', ?, ?, 'SUPERADMIN_VERIFIED', 'USER', ?, '{"status": "already_exists"}', ?)
                """,
                (f"aud_{uuid.uuid4().hex[:12]}", user_id, SUPERADMIN_USERNAME, user_id, now_iso),
            )
            return {
                "success": True,
                "status": "verified",
                "created": False,
                "username": SUPERADMIN_USERNAME,
                "user_id": user_id,
                "message": f"Platform Owner account '{SUPERADMIN_USERNAME}' already exists and is active.",
            }

        # Create or reset password
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(raw_password, salt)
        user_id = existing["user_id"] if existing else f"usr_{uuid.uuid4().hex[:12]}"

        if existing:
            conn.execute(
                """
                UPDATE operational_users
                SET password_hash = ?, salt = ?, is_active = 1, is_internal = 1,
                    must_change_password = 1, updated_at = ?
                WHERE user_id = ?
                """,
                (pw_hash, salt, now_iso, user_id),
            )
            action_name = "SUPERADMIN_RESET"
        else:
            conn.execute(
                """
                INSERT INTO operational_users (
                    user_id, username, email, password_hash, salt, is_internal,
                    tenant_id, is_active, must_change_password, email_verified,
                    auth_provider, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, 'tenant_internal', 1, 1, 1, 'LOCAL', ?, ?)
                """,
                (user_id, SUPERADMIN_USERNAME, SUPERADMIN_EMAIL, pw_hash, salt, now_iso, now_iso),
            )
            action_name = "SUPERADMIN_BOOTSTRAPPED"

        # 3. Assign Groups & Roles: SUPER_ADMIN, PLATFORM_OWNER & PLATFORM_SUPER_ADMIN
        conn.execute(
            """
            INSERT OR IGNORE INTO operational_user_group_memberships (user_id, group_id, assigned_at)
            VALUES (?, 'grp_super_admin', ?)
            """,
            (user_id, now_iso),
        )
        for r in (UserRoleType.PLATFORM_OWNER.value, UserRoleType.PLATFORM_SUPER_ADMIN.value):
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_user_roles (assignment_id, user_id, role_type, granted_at)
                VALUES (?, ?, ?, ?)
                """,
                (f"asgn_{uuid.uuid4().hex[:12]}", user_id, r, now_iso),
            )

        # 4. Ensure Highest Subscription (ENTERPRISE) + Networking++ Entitlement
        conn.execute(
            """
            INSERT INTO operational_user_subscriptions (
                subscription_id, user_id, tenant_id, plan_id, subscription_status,
                starts_at, expires_at, renewal_status, token_quota, token_consumed,
                networking_addon_status, created_at, updated_at
            ) VALUES (?, ?, 'tenant_internal', 'ENTERPRISE', 'ACTIVE', ?, NULL, 'AUTO', 10000000, 0, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan_id = 'ENTERPRISE',
                subscription_status = 'ACTIVE',
                networking_addon_status = 1,
                updated_at = ?
            """,
            (f"sub_{uuid.uuid4().hex[:12]}", user_id, now_iso, now_iso, now_iso, now_iso),
        )

        conn.execute(
            """
            INSERT INTO operational_tenant_entitlements (
                entitlement_id, tenant_id, entitlement_key, is_enabled, granted_at, metadata_json
            ) VALUES (?, 'tenant_internal', 'networking_plus', 1, ?, '{"tier": "ENTERPRISE", "granted_to": "PLATFORM_OWNER"}')
            ON CONFLICT(tenant_id, entitlement_key) DO UPDATE SET is_enabled = 1
            """,
            (f"ent_{uuid.uuid4().hex[:12]}", now_iso),
        )

        # 5. Record Audit Log Entry
        conn.execute(
            """
            INSERT INTO operational_audit_log (
                audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, timestamp_utc
            ) VALUES (?, 'tenant_internal', ?, ?, ?, 'USER', ?, '{"role": "PLATFORM_SUPER_ADMIN", "must_change_password": true}', ?)
            """,
            (f"aud_{uuid.uuid4().hex[:12]}", user_id, SUPERADMIN_USERNAME, action_name, user_id, now_iso),
        )

    return {
        "success": True,
        "status": "reset" if existing else "created",
        "created": not bool(existing),
        "username": SUPERADMIN_USERNAME,
        "user_id": user_id,
        "initial_password": raw_password if (password or not existing or force_reset) else None,
        "must_change_password": True,
        "message": f"Superadmin account '{SUPERADMIN_USERNAME}' successfully provisioned.",
    }


def main():
    parser = argparse.ArgumentParser(description="Bootstrap AIRA OS Superadmin Account")
    parser.add_argument("--password", help="Initial password for lingga_admin (or uses AIRA_SUPERADMIN_PASSWORD env var)")
    parser.add_argument("--force-reset", action="store_true", help="Force reset password if account exists")
    args = parser.parse_args()

    res = bootstrap_superadmin(password=args.password, force_reset=args.force_reset)
    print("=" * 60)
    print("AIRA OS — SUPERADMIN PROVISIONING REPORT")
    print("=" * 60)
    print(f"Status       : {'SUCCESS' if res['success'] else 'FAILED'}")
    print(f"Username     : {res['username']}")
    print(f"User ID      : {res['user_id']}")
    print(f"Action       : {'Created new account' if res['created'] else 'Verified existing account'}")
    if res.get("initial_password"):
        print(f"Password     : {res['initial_password']}")
        print("Notice       : Password must be changed upon first login.")
    print("=" * 60)


if __name__ == "__main__":
    main()
