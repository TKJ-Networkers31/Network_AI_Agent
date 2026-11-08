"""
AIRA OS — Multi-Tenant Core, Identity & Customer Inventory Services (Networking VIII).

Implements business logic, security validation, and database operations for:
- TenantManager: Tenant lifecycle, subscription tiers, and resource quota enforcement
- IdentityManager: User creation, password hashing, RBAC permission resolution, session tokens
- InventoryManager: Customer sites, groups, and network devices with RFC 1918 overlap safety
- AuditLogger: Immutable security and operational audit trail
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.tenant.db import ensure_tenant_schema
from core.tenant.models import (
    AuditEntry,
    CustomerNotificationPreferences,
    CustomerProfile,
    DeviceType,
    Permission,
    ROLE_PERMISSIONS,
    SessionStatus,
    Site,
    SiteGroup,
    SubscriptionTier,
    SupportCategory,
    SupportPriority,
    SupportRequest,
    SupportRequestComment,
    SupportStatus,
    Tenant,
    TenantConfiguration,
    TenantContext,
    TenantDevice,
    TenantResourceQuota,
    TenantStatus,
    TenantSubscription,
    User,
    UserRole,
    UserRoleType,
    UserSession,
    VALID_SUPPORT_TRANSITIONS,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.tenant.manager")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")


from core.security.password import hash_password, verify_password


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    """Computes Argon2id password hash with PBKDF2 backward compatibility (OWASP ASVS 5.0)."""
    return hash_password(password)


def _hash_token(token: str) -> str:
    """SHA-256 hash of a session token for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ===========================================================================
# 1. TENANT MANAGER (WP 8.1)
# ===========================================================================

class TenantManager:
    """Manages multi-tenant lifecycle, subscriptions, and resource quotas."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)

    def create_tenant(
        self,
        name: str,
        slug: str,
        configuration: Optional[TenantConfiguration] = None,
        tier: str = SubscriptionTier.STANDARD.value,
        max_sites: Optional[int] = None,
        max_devices: Optional[int] = None,
        max_gateways: Optional[int] = None,
    ) -> Tenant:
        """Provisions a new customer organization and assigns default resource quotas."""
        slug_clean = slug.strip().lower()
        if not _SLUG_RE.match(slug_clean):
            raise ValueError(f"Invalid slug format: '{slug_clean}'. Must be lowercase alphanumeric with hyphens/underscores.")

        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cfg = configuration or TenantConfiguration()
        config_json = json.dumps(cfg.to_dict())

        # Resource quotas per tier
        tier_upper = tier.upper().strip()
        defaults = {
            SubscriptionTier.COMMUNITY.value: (2, 20, 2),
            SubscriptionTier.STANDARD.value: (10, 100, 10),
            SubscriptionTier.ENTERPRISE.value: (50, 500, 50),
            SubscriptionTier.CUSTOM.value: (100, 1000, 100),
        }
        def_sites, def_devs, def_gws = defaults.get(tier_upper, (10, 100, 10))
        sites_limit = max_sites if max_sites is not None else def_sites
        devs_limit = max_devices if max_devices is not None else def_devs
        gws_limit = max_gateways if max_gateways is not None else def_gws

        sub_id = f"sub_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            # Insert Tenant
            conn.execute(
                """
                INSERT INTO operational_tenants (tenant_id, name, slug, status, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, name.strip(), slug_clean, TenantStatus.ACTIVE.value, config_json, now, now),
            )
            # Insert Subscription
            conn.execute(
                """
                INSERT INTO operational_tenant_subscriptions 
                (subscription_id, tenant_id, tier, max_sites, max_devices, max_gateways, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (sub_id, tenant_id, tier_upper, sites_limit, devs_limit, gws_limit, now),
            )

        logger.info("Created tenant %s (%s) with tier %s", tenant_id, slug_clean, tier_upper)
        return Tenant(
            tenant_id=tenant_id,
            name=name.strip(),
            slug=slug_clean,
            status=TenantStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
            configuration=cfg,
        )

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Retrieves tenant record by immutable ID."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT tenant_id, name, slug, status, config_json, created_at, updated_at FROM operational_tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if not row:
                return None
            cfg_dict = json.loads(row["config_json"] or "{}")
            return Tenant(
                tenant_id=row["tenant_id"],
                name=row["name"],
                slug=row["slug"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                configuration=TenantConfiguration.from_dict(cfg_dict),
            )

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Retrieves tenant record by unique human slug."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT tenant_id, name, slug, status, config_json, created_at, updated_at FROM operational_tenants WHERE slug = ?",
                (slug.strip().lower(),),
            ).fetchone()
            if not row:
                return None
            cfg_dict = json.loads(row["config_json"] or "{}")
            return Tenant(
                tenant_id=row["tenant_id"],
                name=row["name"],
                slug=row["slug"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                configuration=TenantConfiguration.from_dict(cfg_dict),
            )

    def list_tenants(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Tenant]:
        """Returns paginated list of customer organizations."""
        query = "SELECT tenant_id, name, slug, status, config_json, created_at, updated_at FROM operational_tenants"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status.upper())
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()
            results: List[Tenant] = []
            for row in rows:
                cfg_dict = json.loads(row["config_json"] or "{}")
                results.append(Tenant(
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    slug=row["slug"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    configuration=TenantConfiguration.from_dict(cfg_dict),
                ))
            return results

    def update_tenant_status(self, tenant_id: str, new_status: str) -> bool:
        """Transitions tenant status (ACTIVE, SUSPENDED, MAINTENANCE, DECOMMISSIONED)."""
        valid_statuses = {s.value for s in TenantStatus}
        st_upper = new_status.upper().strip()
        if st_upper not in valid_statuses:
            raise ValueError(f"Invalid status: '{st_upper}'. Allowed: {valid_statuses}")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_tenants SET status = ?, updated_at = ? WHERE tenant_id = ?",
                (st_upper, now, tenant_id),
            )
            # If suspended or decommissioned, revoke all active sessions immediately
            if st_upper in (TenantStatus.SUSPENDED.value, TenantStatus.DECOMMISSIONED.value):
                conn.execute(
                    "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE tenant_id = ?",
                    (tenant_id,),
                )
            return cur.rowcount > 0

    def get_tenant_quota(self, tenant_id: str) -> TenantResourceQuota:
        """Calculates current resource utilization against limits."""
        with topology_transaction(self.db_path, write=False) as conn:
            # Get subscription limits
            sub_row = conn.execute(
                "SELECT max_sites, max_devices, max_gateways FROM operational_tenant_subscriptions WHERE tenant_id = ? AND is_active = 1",
                (tenant_id,),
            ).fetchone()
            max_sites = sub_row["max_sites"] if sub_row else 10
            max_devs = sub_row["max_devices"] if sub_row else 100
            max_gws = sub_row["max_gateways"] if sub_row else 10

            # Count current sites
            site_count = conn.execute(
                "SELECT COUNT(*) FROM operational_sites WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()[0]

            # Count current devices
            dev_count = conn.execute(
                "SELECT COUNT(*) FROM operational_devices WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()[0]

            return TenantResourceQuota(
                tenant_id=tenant_id,
                current_sites=site_count,
                current_devices=dev_count,
                current_gateways=0,  # Gateways populated in WP 8.4
                max_sites=max_sites,
                max_devices=max_devs,
                max_gateways=max_gws,
            )


# ===========================================================================
# 2. IDENTITY & RBAC MANAGER (WP 8.2)
# ===========================================================================

class IdentityManager:
    """Manages users, authentication, permissions, sessions, and RBAC governance."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)

    def create_user(
        self,
        username: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        role_type: str = "USER",
        is_internal: bool = False,
        tenant_id: Optional[str] = None,
        display_name: Optional[str] = None,
        group_name: Optional[str] = None,
        account_enabled: bool = True,
    ) -> User:
        """Creates a new user and assigns their initial RBAC role and group."""
        if not password:
            raise ValueError("Password is required.")
        effective_email = email.strip().lower() if email else f"{username.strip().lower()}@aira.local"
        role_upper = role_type.upper().strip() if role_type else "USER"

        if not is_internal and not tenant_id:
            raise ValueError("Customer users must be associated with a valid tenant_id.")

        internal_roles = {
            UserRoleType.PLATFORM_SUPER_ADMIN.value,
            UserRoleType.PLATFORM_OWNER.value,
            UserRoleType.SUPERADMIN.value,
            UserRoleType.NOC_ADMIN.value,
            UserRoleType.NOC_OPERATOR.value,
            UserRoleType.NETWORK_ENGINEER.value,
            UserRoleType.NOC_ANALYST.value,
            UserRoleType.SUPPORT_OPERATOR.value,
            UserRoleType.AUDITOR.value,
        }
        if not is_internal and role_upper in internal_roles:
            raise PermissionError(f"Privilege Boundary Violation: Customer user cannot be assigned internal NOC role '{role_upper}'.")

        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        asgn_id = f"asgn_{uuid.uuid4().hex[:12]}"
        actual_display_name = (display_name or username).strip()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_users 
                (user_id, username, email, password_hash, salt, display_name, account_enabled, is_internal, tenant_id, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (user_id, username.strip().lower(), effective_email, pw_hash, salt, actual_display_name, 1 if account_enabled else 0, 1 if is_internal else 0, tenant_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO operational_user_roles (assignment_id, user_id, role_type, granted_at)
                VALUES (?, ?, ?, ?)
                """,
                (asgn_id, user_id, role_upper, now),
            )

        # Assign initial group
        from core.tenant.rbac_service import get_rbac_service
        rbac_svc = get_rbac_service(self.db_path)
        target_group = group_name or (
            None if role_upper.startswith("CUSTOMER_")
            else ("SUPER_ADMIN" if role_upper in ("PLATFORM_OWNER", "SUPERADMIN", "PLATFORM_SUPER_ADMIN")
            else ("ADMIN" if role_upper == "ADMIN"
            else ("NOC" if role_upper in ("NOC_ADMIN", "NOC_OPERATOR", "NOC_ANALYST")
            else ("NETWORK_ENGINEER" if role_upper == "NETWORK_ENGINEER"
            else "USER"))))
        )
        if target_group:
            try:
                rbac_svc.assign_user_groups(user_id, [target_group])
            except Exception:
                pass

        logger.info("Created user %s (%s, display=%s, group=%s)", user_id, username, actual_display_name, target_group)
        assigned_groups = [g["name"] for g in rbac_svc.get_user_groups(user_id)]
        effective_perms = sorted(list(rbac_svc.get_effective_permissions(user_id)))

        return User(
            user_id=user_id,
            username=username.strip().lower(),
            email=effective_email,
            password_hash=pw_hash,
            salt=salt,
            display_name=actual_display_name,
            account_enabled=account_enabled,
            is_internal=is_internal,
            tenant_id=tenant_id,
            is_active=True,
            role_type=role_upper,
            groups=assigned_groups,
            permissions=effective_perms,
            created_at=now,
            updated_at=now,
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Retrieves a user entity by username including primary role, groups, and permissions."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM operational_users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
            if not row:
                return None
            
            roles = [
                r["role_type"] for r in conn.execute(
                    "SELECT role_type FROM operational_user_roles WHERE user_id = ?",
                    (row["user_id"],),
                ).fetchall()
            ]
            primary_role = roles[0] if roles else None
            if UserRoleType.PLATFORM_OWNER.value in roles:
                primary_role = UserRoleType.PLATFORM_OWNER.value
            elif UserRoleType.SUPERADMIN.value in roles:
                primary_role = UserRoleType.SUPERADMIN.value

            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service(self.db_path)
            groups = [g["name"] for g in rbac_svc.get_user_groups(row["user_id"])]
            perms = sorted(list(rbac_svc.get_effective_permissions(row["user_id"])))

            d_name = row["display_name"] if "display_name" in row.keys() and row["display_name"] else row["username"]
            acct_en = bool(row["account_enabled"]) if "account_enabled" in row.keys() else bool(row["is_active"])
            must_ch = bool(row["must_change_password"]) if "must_change_password" in row.keys() else False
            mfa_en = bool(row["mfa_enabled"]) if "mfa_enabled" in row.keys() else False

            return User(
                user_id=row["user_id"],
                username=row["username"],
                display_name=d_name,
                account_enabled=acct_en,
                email=row["email"],
                password_hash=row["password_hash"],
                salt=row["salt"],
                is_internal=bool(row["is_internal"]),
                tenant_id=row["tenant_id"],
                is_active=bool(row["is_active"]),
                role_type=primary_role,
                last_login_at=row["last_login_at"] if "last_login_at" in row.keys() else None,
                last_activity_at=row["last_activity_at"] if "last_activity_at" in row.keys() else None,
                groups=groups,
                permissions=perms,
                must_change_password=must_ch,
                mfa_enabled=mfa_en,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieves a user entity by user_id including primary role, groups, and permissions."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM operational_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            
            roles = [
                r["role_type"] for r in conn.execute(
                    "SELECT role_type FROM operational_user_roles WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            ]
            primary_role = roles[0] if roles else None
            if UserRoleType.PLATFORM_OWNER.value in roles:
                primary_role = UserRoleType.PLATFORM_OWNER.value
            elif UserRoleType.SUPERADMIN.value in roles:
                primary_role = UserRoleType.SUPERADMIN.value

            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service(self.db_path)
            groups = [g["name"] for g in rbac_svc.get_user_groups(user_id)]
            perms = sorted(list(rbac_svc.get_effective_permissions(user_id)))

            d_name = row["display_name"] if "display_name" in row.keys() and row["display_name"] else row["username"]
            acct_en = bool(row["account_enabled"]) if "account_enabled" in row.keys() else bool(row["is_active"])
            must_ch = bool(row["must_change_password"]) if "must_change_password" in row.keys() else False
            mfa_en = bool(row["mfa_enabled"]) if "mfa_enabled" in row.keys() else False

            return User(
                user_id=row["user_id"],
                username=row["username"],
                display_name=d_name,
                account_enabled=acct_en,
                email=row["email"],
                password_hash=row["password_hash"],
                salt=row["salt"],
                is_internal=bool(row["is_internal"]),
                tenant_id=row["tenant_id"],
                is_active=bool(row["is_active"]),
                role_type=primary_role,
                last_login_at=row["last_login_at"] if "last_login_at" in row.keys() else None,
                last_activity_at=row["last_activity_at"] if "last_activity_at" in row.keys() else None,
                groups=groups,
                permissions=perms,
                must_change_password=must_ch,
                mfa_enabled=mfa_en,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def toggle_account_enabled(self, user_id: str, enabled: bool, actor_id: Optional[str] = None) -> bool:
        """Enables or disables a user account, revoking all active sessions if disabled."""
        val = 1 if enabled else 0
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_users SET account_enabled = ?, is_active = ?, updated_at = ? WHERE user_id = ?",
                (val, val, now_str, user_id),
            )
            if not enabled:
                conn.execute(
                    "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                    (user_id,),
                )
        from core.tenant.rbac_service import get_rbac_service
        rbac_svc = get_rbac_service(self.db_path)
        u = self.get_user_by_id(user_id)
        uname = u.username if u else user_id
        rbac_svc.log_activity_event(
            username=uname,
            event_type="ACCOUNT_ENABLED" if enabled else "ACCOUNT_DISABLED",
            user_id=user_id,
            details={"account_enabled": enabled},
            actor_id=actor_id,
        )
        return True

    def unlock_user_account(self, user_id: str) -> bool:
        """Unlocks a locked user account and resets failed login counters."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_users SET failed_login_attempts = 0, locked_until_utc = NULL WHERE user_id = ?",
                (user_id,),
            )
            return cur.rowcount > 0

    def list_users(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all registered users along with their groups, status, and activity timestamps."""
        from core.tenant.rbac_service import get_rbac_service
        rbac_svc = get_rbac_service(self.db_path)
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM operational_users"
            params: List[Any] = []
            if tenant_id:
                query += " WHERE tenant_id = ?"
                params.append(tenant_id)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()

        results = []
        for r in rows:
            uid = r["user_id"]
            d_name = r["display_name"] if "display_name" in r.keys() and r["display_name"] else r["username"]
            acct_en = bool(r["account_enabled"]) if "account_enabled" in r.keys() else bool(r["is_active"])
            groups = [g["name"] for g in rbac_svc.get_user_groups(uid)]
            status = rbac_svc.get_user_status(uid)
            results.append({
                "user_id": uid,
                "username": r["username"],
                "display_name": d_name,
                "email": r["email"],
                "account_enabled": acct_en,
                "is_online": status == "ONLINE",
                "status": status,
                "is_internal": bool(r["is_internal"]),
                "last_login_at": r["last_login_at"] if "last_login_at" in r.keys() else None,
                "last_activity_at": r["last_activity_at"] if "last_activity_at" in r.keys() else None,
                "groups": groups,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return results

    def update_user(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        group_names: Optional[List[str]] = None,
        password: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[User]:
        """Updates user profile attributes (display_name, password, and assigned groups)."""
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with topology_transaction(self.db_path, write=True) as conn:
            if display_name is not None:
                conn.execute(
                    "UPDATE operational_users SET display_name = ?, updated_at = ? WHERE user_id = ?",
                    (display_name.strip(), now_str, user_id),
                )
        if password:
            self.change_user_password(user_id, password, reset_must_change=True)

        if group_names is not None:
            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service(self.db_path)
            rbac_svc.assign_user_groups(user_id, group_names)

        from core.tenant.rbac_service import get_rbac_service
        rbac_svc = get_rbac_service(self.db_path)
        u = self.get_user_by_id(user_id)
        if u:
            rbac_svc.log_activity_event(
                username=u.username,
                event_type="USER_UPDATED",
                user_id=user_id,
                details={"display_name": display_name, "groups": group_names},
                actor_id=actor_id,
            )
        return u

    def get_user_roles(self, user_id: str) -> List[str]:
        """Returns all assigned role types for a user."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT role_type FROM operational_user_roles WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [r["role_type"] for r in rows]

    def authenticate_user_detailed(
        self,
        username_or_email: str,
        password: str,
        totp_code: Optional[str] = None,
        ip_address: Optional[str] = None,
        admin_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Authenticates credentials with:
        - Rate limiting & lockout protection (after 5 failed attempts, locked for 15 minutes)
        - First-login password change requirement flag
        - Two-factor authentication (TOTP) enforcement
        - Admin portal privilege barrier
        """
        identifier = username_or_email.strip().lower()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT user_id, username, email, password_hash, salt, is_internal, tenant_id, is_active, account_enabled,
                       must_change_password, mfa_enabled, mfa_secret, failed_login_attempts, locked_until_utc
                FROM operational_users 
                WHERE (username = ? OR email = ?)
                """,
                (identifier, identifier),
            ).fetchone()

            if not row:
                from core.tenant.rbac_service import get_rbac_service
                get_rbac_service(self.db_path).log_activity_event(
                    username=identifier,
                    event_type="LOGIN_FAILED",
                    ip_address=ip_address,
                    details={"reason": "User not found"},
                )
                return {"success": False, "error": "Username atau kata sandi tidak valid."}

            if not bool(row["is_active"]) or ("account_enabled" in row.keys() and not bool(row["account_enabled"])):
                from core.tenant.rbac_service import get_rbac_service
                get_rbac_service(self.db_path).log_activity_event(
                    username=row["username"],
                    event_type="LOGIN_FAILED",
                    user_id=row["user_id"],
                    ip_address=ip_address,
                    details={"reason": "Account disabled"},
                )
                return {"success": False, "error": "Akun ini telah dinonaktifkan oleh administrator."}

            user_id = row["user_id"]
            username = row["username"]
            tenant_id = row["tenant_id"]
            is_internal = bool(row["is_internal"])
            must_change = bool(row["must_change_password"])
            mfa_enabled = bool(row["mfa_enabled"])
            mfa_secret = row["mfa_secret"]
            failed_attempts = row["failed_login_attempts"] or 0
            locked_until = row["locked_until_utc"]

            # Check lockout
            if locked_until:
                try:
                    lock_dt = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
                    if now_dt < lock_dt:
                        remaining_min = max(1, int((lock_dt - now_dt).total_seconds() // 60))
                        return {
                            "success": False,
                            "error": f"Akun terkunci karena terlalu banyak percobaan login yang gagal. Silakan coba {remaining_min} menit lagi.",
                            "locked": True,
                        }
                except Exception:
                    pass

            # Check password with Argon2id and transparent legacy migration
            is_valid, needs_rehash = verify_password(password, row["password_hash"], row["salt"])
            if not is_valid:
                new_failed = failed_attempts + 1
                if new_failed >= 5:
                    lock_time = (now_dt + timedelta(minutes=15)).isoformat()
                    conn.execute(
                        "UPDATE operational_users SET failed_login_attempts = ?, locked_until_utc = ? WHERE user_id = ?",
                        (new_failed, lock_time, user_id),
                    )
                    aud_id = f"aud_{uuid.uuid4().hex[:16]}"
                    conn.execute(
                        """
                        INSERT INTO operational_audit_log
                        (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                        VALUES (?, ?, ?, ?, 'ACCOUNT_LOCKED', 'USER', ?, ?, ?, ?)
                        """,
                        (aud_id, tenant_id, user_id, username, user_id, json.dumps({"reason": "Excessive failed logins", "attempts": new_failed}), ip_address or "127.0.0.1", now_iso),
                    )
                    return {
                        "success": False,
                        "error": "Terlalu banyak percobaan gagal. Akun dikunci selama 15 menit untuk keamanan.",
                        "locked": True,
                    }
                else:
                    conn.execute(
                        "UPDATE operational_users SET failed_login_attempts = ? WHERE user_id = ?",
                        (new_failed, user_id),
                    )
                    return {"success": False, "error": "Username atau kata sandi tidak valid."}

            if needs_rehash:
                new_hash = hash_password(password)
                conn.execute(
                    "UPDATE operational_users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
                    (new_hash, now_iso, user_id),
                )
                logger.info("Transparently migrated password to Argon2id for user %s", username)

            # Verify admin role boundary if logging into admin site
            if admin_only:
                roles_rows = conn.execute("SELECT role_type FROM operational_user_roles WHERE user_id = ?", (user_id,)).fetchall()
                user_roles = [r["role_type"] for r in roles_rows]
                internal_roles = {
                    UserRoleType.PLATFORM_OWNER.value,
                    "PLATFORM_OWNER",
                    UserRoleType.SUPERADMIN.value,
                    "SUPERADMIN",
                    UserRoleType.ADMIN.value,
                    "ADMIN",
                    UserRoleType.PLATFORM_SUPER_ADMIN.value,
                    UserRoleType.NOC_ADMIN.value,
                    UserRoleType.NOC_OPERATOR.value,
                    UserRoleType.NETWORK_ENGINEER.value,
                    UserRoleType.NOC_ANALYST.value,
                    UserRoleType.SUPPORT_OPERATOR.value,
                    UserRoleType.AUDITOR.value,
                }
                if not is_internal and not any(r in internal_roles for r in user_roles):
                    return {
                        "success": False,
                        "error": "Akses ditolak. AIRA Control Plane memerlukan kredensial staf internal administrator.",
                    }

            # Verify tenant is active
            if not is_internal and tenant_id:
                t_row = conn.execute("SELECT status FROM operational_tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
                if not t_row or t_row["status"] not in (TenantStatus.ACTIVE.value, TenantStatus.MAINTENANCE.value):
                    return {"success": False, "error": f"Organisasi sedang {t_row['status'] if t_row else 'NONAKTIF'}. Hubungi administrator."}

            # MFA Verification Check
            if mfa_enabled and mfa_secret:
                from core.security.encryption import decrypt_secret
                from core.security.mfa import verify_totp_code
                plain_mfa_secret = decrypt_secret(mfa_secret) or mfa_secret
                if not totp_code:
                    return {
                        "success": False,
                        "mfa_required": True,
                        "user_id": user_id,
                        "username": username,
                        "message": "Kode verifikasi 2FA (TOTP) diperlukan.",
                    }
                if not verify_totp_code(plain_mfa_secret, totp_code):
                    return {
                        "success": False,
                        "mfa_required": True,
                        "user_id": user_id,
                        "username": username,
                        "error": "Kode verifikasi 2FA tidak sesuai atau sudah kadaluarsa.",
                    }

            # Login successful: reset failed attempts & update last_login
            conn.execute(
                """
                UPDATE operational_users
                SET failed_login_attempts = 0, locked_until_utc = NULL, last_login_at = ?, last_login_ip = ?
                WHERE user_id = ?
                """,
                (now_iso, ip_address or "127.0.0.1", user_id),
            )

        # Create active session
        session = self.create_session(user_id=user_id)
        from core.tenant.rbac_service import get_rbac_service
        get_rbac_service(self.db_path).log_activity_event(
            username=username,
            event_type="LOGIN_SUCCESS",
            user_id=user_id,
            ip_address=ip_address,
            details={"session_id": session.session_id},
        )
        return {
            "success": True,
            "session": session,
            "user_id": user_id,
            "username": username,
            "is_internal": is_internal,
            "must_change_password": must_change,
            "mfa_verified": mfa_enabled,
        }

    def authenticate_user(self, username_or_email: str, password: str) -> Optional[UserSession]:
        """Authenticates credentials and establishes a new UserSession upon success."""
        res = self.authenticate_user_detailed(username_or_email, password)
        return res.get("session") if res.get("success") else None

    def change_user_password(self, user_id: str, new_password: str, reset_must_change: bool = True) -> bool:
        """Changes user password with cryptographically fresh salt and clears mandatory change flag."""
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        salt = secrets.token_hex(16)
        pw_hash = _hash_password(new_password, salt)
        now_iso = datetime.now(timezone.utc).isoformat()
        must_change_val = 0 if reset_must_change else 1

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_users
                SET password_hash = ?, salt = ?, must_change_password = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (pw_hash, salt, must_change_val, now_iso, user_id),
            )
            # Session revocation on password change (OWASP ASVS 5.0)
            conn.execute(
                "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                (user_id,),
            )

            aud_id = f"aud_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, 'tenant_internal', ?, 'user', 'PASSWORD_CHANGED', 'USER', ?, '{}', '127.0.0.1', ?)
                """,
                (aud_id, user_id, user_id, now_iso),
            )
        return True

    def setup_mfa(self, user_id: str) -> Dict[str, Any]:
        """Initiates MFA setup by generating a TOTP secret and QR URI."""
        from core.security.mfa import generate_totp_secret, get_totp_uri
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT username, email FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError(f"User '{user_id}' not found.")
            username = row["username"]

        secret = generate_totp_secret()
        otpauth_uri = get_totp_uri(secret, username=username, issuer="AIRA OS")
        return {
            "secret": secret,
            "otpauth_uri": otpauth_uri,
            "username": username,
        }

    def verify_and_enable_mfa(self, user_id: str, secret: str, code: str) -> bool:
        """Verifies initial TOTP code and activates MFA for user."""
        from core.security.encryption import encrypt_secret
        from core.security.mfa import verify_totp_code
        if not verify_totp_code(secret, code):
            raise ValueError("Kode verifikasi 2FA tidak valid. Pastikan waktu perangkat Anda sinkron.")

        enc_secret = encrypt_secret(secret)
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_users SET mfa_enabled = 1, mfa_secret = ?, updated_at = ? WHERE user_id = ?",
                (enc_secret, now_iso, user_id),
            )
            aud_id = f"aud_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, 'tenant_internal', ?, 'user', 'MFA_ENABLED', 'USER', ?, '{}', '127.0.0.1', ?)
                """,
                (aud_id, user_id, user_id, now_iso),
            )
        return True

    def disable_mfa(self, user_id: str) -> bool:
        """Disables MFA for user."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_users SET mfa_enabled = 0, mfa_secret = NULL, updated_at = ? WHERE user_id = ?",
                (now_iso, user_id),
            )
            aud_id = f"aud_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, 'tenant_internal', ?, 'user', 'MFA_DISABLED', 'USER', ?, '{}', '127.0.0.1', ?)
                """,
                (aud_id, user_id, user_id, now_iso),
            )
        return True

    def impersonate_user(self, admin_user_id: str, target_user_id: str, reason: str, ip_address: str = "127.0.0.1") -> UserSession:
        """Allows superadmin to establish an audited impersonation session for troubleshooting."""
        if not reason or not reason.strip():
            raise ValueError("A clear, non-empty reason is mandatory for superadmin impersonation.")

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            admin_roles = conn.execute("SELECT role_type FROM operational_user_roles WHERE user_id = ?", (admin_user_id,)).fetchall()
            role_names = [r["role_type"] for r in admin_roles]
            if not any(r in (UserRoleType.PLATFORM_SUPER_ADMIN.value, "SUPERADMIN") for r in role_names):
                raise PermissionError("Only Superadmin is permitted to perform user impersonation.")

            target_row = conn.execute("SELECT username, tenant_id FROM operational_users WHERE user_id = ?", (target_user_id,)).fetchone()
            if not target_row:
                raise ValueError(f"Target user '{target_user_id}' does not exist.")

        session = self.create_session(user_id=target_user_id, duration_hours=2)

        # Audit impersonation
        now_iso = datetime.now(timezone.utc).isoformat()
        aud_id = f"aud_{uuid.uuid4().hex[:16]}"
        details = {
            "action": "SUPERADMIN_IMPERSONATION",
            "superadmin_user_id": admin_user_id,
            "target_user_id": target_user_id,
            "target_username": target_row["username"],
            "reason": reason.strip(),
            "session_id": session.session_id,
        }
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, ?, ?, 'lingga_admin', 'SUPERADMIN_IMPERSONATION', 'USER', ?, ?, ?, ?)
                """,
                (aud_id, target_row["tenant_id"], admin_user_id, target_user_id, json.dumps(details), ip_address, now_iso),
            )
        return session

    def create_session(self, user_id: str, duration_hours: int = 720, single_session_only: bool = False) -> UserSession:
        """Issues an active session token for an authenticated user (default: 30 days persistent)."""
        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        raw_token = f"aira_tok_{secrets.token_urlsafe(32)}"
        token_hash = _hash_token(raw_token)
        now_epoch = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
        exp_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch + (duration_hours * 3600)))

        with topology_transaction(self.db_path, write=True) as conn:
            u_row = conn.execute(
                "SELECT username, is_internal, tenant_id FROM operational_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not u_row:
                raise ValueError(f"User {user_id} not found.")

            # Load roles
            roles_rows = conn.execute(
                "SELECT role_type FROM operational_user_roles WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            roles = [r["role_type"] for r in roles_rows]

            # Compute permissions
            permissions: Set[str] = set()
            for r in roles:
                try:
                    rt = UserRoleType(r)
                    for p in ROLE_PERMISSIONS.get(rt, set()):
                        permissions.add(p.value)
                except ValueError:
                    pass

            if single_session_only:
                conn.execute(
                    "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                    (user_id,),
                )

            conn.execute(
                """
                INSERT INTO operational_user_sessions
                (session_id, user_id, tenant_id, is_internal, token_hash, status, created_at, expires_at_utc, last_activity_at)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (session_id, user_id, u_row["tenant_id"], u_row["is_internal"], token_hash, now_str, exp_str, now_str),
            )
            conn.execute(
                "UPDATE operational_users SET last_activity_at = ? WHERE user_id = ?",
                (now_str, user_id),
            )

        return UserSession(
            session_id=session_id,
            user_id=user_id,
            username=u_row["username"],
            tenant_id=u_row["tenant_id"],
            is_internal=bool(u_row["is_internal"]),
            token=raw_token,
            roles=roles,
            permissions=sorted(list(permissions)),
            status=SessionStatus.ACTIVE.value,
            created_at=now_str,
            expires_at_utc=exp_str,
        )

    def validate_session_token(self, token: str) -> Optional[TenantContext]:
        """Validates token and returns resolved TenantContext with permissions."""
        if not token or not token.startswith("aira_tok_"):
            return None

        token_hash = _hash_token(token)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT s.session_id, s.user_id, s.tenant_id, s.is_internal, s.status, s.expires_at_utc,
                       u.username, u.is_active, u.account_enabled, t.status as tenant_status
                FROM operational_user_sessions s
                JOIN operational_users u ON s.user_id = u.user_id
                LEFT JOIN operational_tenants t ON s.tenant_id = t.tenant_id
                WHERE s.token_hash = ? AND s.status = 'ACTIVE'
                """,
                (token_hash,),
            ).fetchone()

            if not row:
                return None

            # Expiration check
            if row["expires_at_utc"] <= now_str:
                return None

            # User and Tenant Active check
            if not row["is_active"]:
                return None
            if "account_enabled" in row.keys() and not bool(row["account_enabled"]):
                return None
            if row["tenant_id"] and row["tenant_status"] not in (TenantStatus.ACTIVE.value, TenantStatus.MAINTENANCE.value):
                return None

            user_id = row["user_id"]
            username = row["username"]
            tenant_id = row["tenant_id"]
            is_internal = bool(row["is_internal"])

            # Load roles & permissions
            roles_rows = conn.execute(
                "SELECT role_type FROM operational_user_roles WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            roles = [r["role_type"] for r in roles_rows]
            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service(self.db_path)
            groups = [g["name"] for g in rbac_svc.get_user_groups(user_id)]
            effective_permissions = rbac_svc.get_effective_permissions(user_id)
            if "READ_ONLY" in groups:
                permissions = set(effective_permissions)
            else:
                permissions = set()
                for r in roles:
                    try:
                        rt = UserRoleType(r)
                        for p in ROLE_PERMISSIONS.get(rt, set()):
                            permissions.add(p.value)
                    except ValueError:
                        pass
                for p in effective_permissions:
                    permissions.add(p)

            return TenantContext(
                user_id=user_id,
                username=username,
                is_internal=is_internal,
                tenant_id=tenant_id,
                roles=roles,
                groups=groups,
                permissions=permissions,
                session_id=row["session_id"],
                account_enabled=bool(row["account_enabled"]) if "account_enabled" in row.keys() else bool(row["is_active"]),
            )

    def revoke_session(self, session_id: str) -> bool:
        """Revokes an active session."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE session_id = ?",
                (session_id,),
            )
            return cur.rowcount > 0

    def revoke_token(self, token: str) -> bool:
        """Revokes an active session by token."""
        token_hash = _hash_token(token)
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE token_hash = ?",
                (token_hash,),
            )
            return cur.rowcount > 0

    def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revokes all active sessions for a user upon privilege modification, lock, or security event."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute(
                "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                (user_id,),
            )
            return cur.rowcount

    def revoke_other_sessions(self, user_id: str, current_token: Optional[str] = None) -> int:
        """Revokes all active sessions for a user except the current token session."""
        token_hash = _hash_token(current_token) if current_token else None
        with topology_transaction(self.db_path, write=True) as conn:
            if token_hash:
                cur = conn.execute(
                    "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE' AND token_hash != ?",
                    (user_id, token_hash),
                )
            else:
                cur = conn.execute(
                    "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                    (user_id,),
                )
            return cur.rowcount


# ===========================================================================
# 3. INVENTORY MANAGER (WP 8.3)
# ===========================================================================

class InventoryManager:
    """Manages customer sites, site groups, and network devices with RFC 1918 overlap safety."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)
        self.tenant_mgr = TenantManager(self.db_path)

    def create_site(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        timezone: str = "Asia/Jakarta",
        address: Optional[str] = None,
        contact_person: Optional[str] = None,
        notes: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> Site:
        """Creates a site belonging to a tenant, enforcing quota limits."""
        slug_clean = slug.strip().lower()
        if not _SLUG_RE.match(slug_clean):
            raise ValueError(f"Invalid slug format: '{slug_clean}'.")

        # Quota check
        quota = self.tenant_mgr.get_tenant_quota(tenant_id)
        if quota.is_site_quota_exceeded:
            raise ValueError(f"Quota Exceeded: Tenant {tenant_id} has reached maximum sites limit ({quota.max_sites}).")

        site_id = f"site_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_sites 
                (site_id, tenant_id, name, slug, group_id, address, timezone, contact_person, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (site_id, tenant_id, name.strip(), slug_clean, group_id, address, timezone, contact_person, notes, now),
            )

        logger.info("Created site %s (%s) for tenant %s", site_id, name, tenant_id)
        return Site(
            site_id=site_id,
            tenant_id=tenant_id,
            name=name.strip(),
            slug=slug_clean,
            group_id=group_id,
            address=address,
            timezone=timezone,
            contact_person=contact_person,
            notes=notes,
            created_at=now,
        )

    def get_site(self, tenant_id: str, site_id: str) -> Optional[Site]:
        """Retrieves a site enforcing tenant ownership (IDOR safe)."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT site_id, tenant_id, name, slug, group_id, address, timezone, contact_person, notes, created_at FROM operational_sites WHERE tenant_id = ? AND site_id = ?",
                (tenant_id, site_id),
            ).fetchone()
            if not row:
                return None
            return Site(
                site_id=row["site_id"],
                tenant_id=row["tenant_id"],
                name=row["name"],
                slug=row["slug"],
                group_id=row["group_id"],
                address=row["address"],
                timezone=row["timezone"],
                contact_person=row["contact_person"],
                notes=row["notes"],
                created_at=row["created_at"],
            )

    def list_sites(self, tenant_id: str, group_id: Optional[str] = None) -> List[Site]:
        """Lists sites for a tenant."""
        query = "SELECT site_id, tenant_id, name, slug, group_id, address, timezone, contact_person, notes, created_at FROM operational_sites WHERE tenant_id = ?"
        params: List[Any] = [tenant_id]
        if group_id:
            query += " AND group_id = ?"
            params.append(group_id)
        query += " ORDER BY name ASC"

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                Site(
                    site_id=r["site_id"],
                    tenant_id=r["tenant_id"],
                    name=r["name"],
                    slug=r["slug"],
                    group_id=r["group_id"],
                    address=r["address"],
                    timezone=r["timezone"],
                    contact_person=r["contact_person"],
                    notes=r["notes"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def create_device(
        self,
        tenant_id: str,
        site_id: str,
        name: str,
        management_ip: str,
        management_port: int = 22,
        device_type: str = DeviceType.ROUTER.value,
        vendor: str = "MikroTik",
        model: Optional[str] = None,
        os_version: Optional[str] = None,
        gateway_id: Optional[str] = None,
        credential_ref: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> TenantDevice:
        """
        Registers a network device.
        Enforces RFC 1918 overlap safety: Management IP is unique within (tenant_id, site_id),
        allowing Tenant A and Tenant B to each operate 192.168.1.1 without conflict.
        """
        # Quota check
        quota = self.tenant_mgr.get_tenant_quota(tenant_id)
        if quota.is_device_quota_exceeded:
            raise ValueError(f"Quota Exceeded: Tenant {tenant_id} has reached maximum devices limit ({quota.max_devices}).")

        # Verify site exists and belongs to tenant
        site = self.get_site(tenant_id, site_id)
        if not site:
            raise ValueError(f"Site {site_id} not found under tenant {tenant_id}.")

        device_id = f"dev_{tenant_id[:8]}_{site_id[:8]}_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_devices
                (device_id, tenant_id, site_id, name, management_ip, management_port, device_type, vendor, model, os_version, gateway_id, status, credential_ref, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
                """,
                (device_id, tenant_id, site_id, name.strip(), management_ip.strip(), management_port, device_type.upper(), vendor, model, os_version, gateway_id, credential_ref, notes, now, now),
            )

        logger.info("Created device %s (%s - %s) for tenant %s site %s", device_id, name, management_ip, tenant_id, site_id)
        try:
            from core.inventory_store import get_inventory_store
            inv = get_inventory_store()
            if not inv.get_device(name.strip()).get("success"):
                inv.create_device(
                    name=name.strip(),
                    host=management_ip.strip(),
                    port=management_port,
                    device_type=device_type.lower(),
                    note=notes or "",
                )
        except Exception as exc:
            logger.debug("Mirror device to InventoryStore skipped: %s", exc)

        return TenantDevice(
            device_id=device_id,
            tenant_id=tenant_id,
            site_id=site_id,
            name=name.strip(),
            management_ip=management_ip.strip(),
            management_port=management_port,
            device_type=device_type.upper(),
            vendor=vendor,
            model=model or "",
            os_version=os_version or "",
            gateway_id=gateway_id,
            status="ACTIVE",
            credential_ref=credential_ref,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

    def get_device(self, tenant_id: str, device_id: str) -> Optional[TenantDevice]:
        """Retrieves device enforcing tenant ownership (IDOR safe)."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT device_id, tenant_id, site_id, name, management_ip, management_port, device_type, vendor, model, os_version, gateway_id, status, credential_ref, notes, created_at, updated_at
                FROM operational_devices
                WHERE tenant_id = ? AND device_id = ?
                """,
                (tenant_id, device_id),
            ).fetchone()
            if not row:
                return None
            return TenantDevice(
                device_id=row["device_id"],
                tenant_id=row["tenant_id"],
                site_id=row["site_id"],
                name=row["name"],
                management_ip=row["management_ip"],
                management_port=row["management_port"],
                device_type=row["device_type"],
                vendor=row["vendor"],
                model=row["model"] or "",
                os_version=row["os_version"] or "",
                gateway_id=row["gateway_id"],
                status=row["status"],
                credential_ref=row["credential_ref"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_device_by_ip(self, tenant_id: str, site_id: str, management_ip: str) -> Optional[TenantDevice]:
        """Scoped resolution by (tenant_id, site_id, management_ip). Overlap RFC 1918 safe."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT device_id, tenant_id, site_id, name, management_ip, management_port, device_type, vendor, model, os_version, gateway_id, status, credential_ref, notes, created_at, updated_at
                FROM operational_devices
                WHERE tenant_id = ? AND site_id = ? AND management_ip = ?
                """,
                (tenant_id, site_id, management_ip.strip()),
            ).fetchone()
            if not row:
                return None
            return TenantDevice(
                device_id=row["device_id"],
                tenant_id=row["tenant_id"],
                site_id=row["site_id"],
                name=row["name"],
                management_ip=row["management_ip"],
                management_port=row["management_port"],
                device_type=row["device_type"],
                vendor=row["vendor"],
                model=row["model"] or "",
                os_version=row["os_version"] or "",
                gateway_id=row["gateway_id"],
                status=row["status"],
                credential_ref=row["credential_ref"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_devices(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        device_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[TenantDevice]:
        """Lists devices for a tenant with optional filtering."""
        query = """
            SELECT device_id, tenant_id, site_id, name, management_ip, management_port, device_type, vendor, model, os_version, gateway_id, status, credential_ref, notes, created_at, updated_at
            FROM operational_devices
            WHERE tenant_id = ?
        """
        params: List[Any] = [tenant_id]
        if site_id:
            query += " AND site_id = ?"
            params.append(site_id)
        if device_type:
            query += " AND device_type = ?"
            params.append(device_type.upper())
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        query += " ORDER BY name ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                TenantDevice(
                    device_id=r["device_id"],
                    tenant_id=r["tenant_id"],
                    site_id=r["site_id"],
                    name=r["name"],
                    management_ip=r["management_ip"],
                    management_port=r["management_port"],
                    device_type=r["device_type"],
                    vendor=r["vendor"],
                    model=r["model"] or "",
                    os_version=r["os_version"] or "",
                    gateway_id=r["gateway_id"],
                    status=r["status"],
                    credential_ref=r["credential_ref"],
                    notes=r["notes"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]


# ===========================================================================
# 4. AUDIT LOGGER
# ===========================================================================

class AuditLogger:
    """Appends immutable operational and security audit entries."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)

    def log_action(
        self,
        username: str,
        action: str,
        resource_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditEntry:
        """Appends a tamper-evident audit record."""
        audit_id = f"aud_{uuid.uuid4().hex[:16]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        det_json = json.dumps(details or {})

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, det_json, ip_address, now),
            )

        return AuditEntry(
            audit_id=audit_id,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=det_json,
            ip_address=ip_address,
            timestamp_utc=now,
        )

    def list_entries(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Lists audit entries, optionally filtered by tenant."""
        query = "SELECT audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc FROM operational_audit_log"
        params: List[Any] = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                AuditEntry(
                    audit_id=r["audit_id"],
                    tenant_id=r["tenant_id"],
                    user_id=r["user_id"],
                    username=r["username"],
                    action=r["action"],
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    details_json=r["details_json"] or "{}",
                    ip_address=r["ip_address"],
                    timestamp_utc=r["timestamp_utc"],
                )
                for r in rows
            ]


# ===========================================================================
# 5. CUSTOMER SUPPORT REQUEST MANAGER (WP 8.9.9)
# ===========================================================================

class SupportRequestManager:
    """Manages customer support requests, lifecycle state transitions, and collaboration."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)

    def create_request(
        self,
        tenant_id: str,
        requester_id: str,
        category: str,
        subject: str,
        description: str,
        priority: str = SupportPriority.MEDIUM.value,
    ) -> SupportRequest:
        """Creates a new customer support ticket in OPEN state."""
        cat_upper = category.upper()
        if cat_upper not in {c.value for c in SupportCategory}:
            raise ValueError(f"Invalid support category '{category}'.")
        prio_upper = priority.upper()
        if prio_upper not in {p.value for p in SupportPriority}:
            raise ValueError(f"Invalid support priority '{priority}'.")

        request_id = f"req_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_support_requests
                (request_id, tenant_id, requester_id, category, subject, description, priority, status, assigned_operator_id, created_at, updated_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', NULL, ?, ?, NULL)
                """,
                (request_id, tenant_id, requester_id, cat_upper, subject.strip(), description.strip(), prio_upper, now, now),
            )

        return SupportRequest(
            request_id=request_id,
            tenant_id=tenant_id,
            requester_id=requester_id,
            category=cat_upper,
            subject=subject.strip(),
            description=description.strip(),
            priority=prio_upper,
            status=SupportStatus.OPEN.value,
            assigned_operator_id=None,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            comments=[],
        )

    def get_request(self, tenant_id: str, request_id: str) -> Optional[SupportRequest]:
        """Retrieves a single support request with its comments, strictly scoped to tenant_id."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT request_id, tenant_id, requester_id, category, subject, description,
                       priority, status, assigned_operator_id, created_at, updated_at, resolved_at
                FROM operational_support_requests
                WHERE request_id = ? AND tenant_id = ?
                """,
                (request_id, tenant_id),
            ).fetchone()
            if not row:
                return None

            c_rows = conn.execute(
                """
                SELECT comment_id, request_id, tenant_id, author_id, author_name, is_internal, message, created_at
                FROM operational_support_request_comments
                WHERE request_id = ? AND tenant_id = ?
                ORDER BY created_at ASC
                """,
                (request_id, tenant_id),
            ).fetchall()

            comments = [
                SupportRequestComment(
                    comment_id=cr["comment_id"],
                    request_id=cr["request_id"],
                    tenant_id=cr["tenant_id"],
                    author_id=cr["author_id"],
                    author_name=cr["author_name"],
                    is_internal=bool(cr["is_internal"]),
                    message=cr["message"],
                    created_at=cr["created_at"],
                )
                for cr in c_rows
            ]

            return SupportRequest(
                request_id=row["request_id"],
                tenant_id=row["tenant_id"],
                requester_id=row["requester_id"],
                category=row["category"],
                subject=row["subject"],
                description=row["description"],
                priority=row["priority"],
                status=row["status"],
                assigned_operator_id=row["assigned_operator_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                resolved_at=row["resolved_at"],
                comments=comments,
            )

    def list_requests(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SupportRequest]:
        """Lists support requests scoped strictly to tenant_id."""
        clauses = ["tenant_id = ?"]
        params: List[Any] = [tenant_id]

        if status:
            clauses.append("status = ?")
            params.append(status.upper())
        if category:
            clauses.append("category = ?")
            params.append(category.upper())

        where_sql = " AND ".join(clauses)
        params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                f"""
                SELECT request_id, tenant_id, requester_id, category, subject, description,
                       priority, status, assigned_operator_id, created_at, updated_at, resolved_at
                FROM operational_support_requests
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

            return [
                SupportRequest(
                    request_id=r["request_id"],
                    tenant_id=r["tenant_id"],
                    requester_id=r["requester_id"],
                    category=r["category"],
                    subject=r["subject"],
                    description=r["description"],
                    priority=r["priority"],
                    status=r["status"],
                    assigned_operator_id=r["assigned_operator_id"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    resolved_at=r["resolved_at"],
                    comments=[],
                )
                for r in rows
            ]

    def transition_status(
        self,
        tenant_id: str,
        request_id: str,
        new_status: str,
        actor_id: str,
    ) -> SupportRequest:
        """Transitions request through validated lifecycle state machine."""
        req = self.get_request(tenant_id, request_id)
        if not req:
            raise KeyError(f"Support request '{request_id}' not found for tenant '{tenant_id}'.")

        curr_st = req.status
        target_st = new_status.upper()
        allowed = VALID_SUPPORT_TRANSITIONS.get(curr_st, set())

        if target_st not in allowed:
            raise ValueError(
                f"Invalid transition from '{curr_st}' to '{target_st}'. Allowed: {sorted(list(allowed))}"
            )

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        resolved_at = now if target_st in (SupportStatus.RESOLVED.value, SupportStatus.CLOSED.value) else req.resolved_at

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_support_requests
                SET status = ?, updated_at = ?, resolved_at = ?
                WHERE request_id = ? AND tenant_id = ?
                """,
                (target_st, now, resolved_at, request_id, tenant_id),
            )

        return self.get_request(tenant_id, request_id)  # type: ignore

    def add_comment(
        self,
        tenant_id: str,
        request_id: str,
        author_id: str,
        author_name: str,
        message: str,
        is_internal: bool = False,
    ) -> SupportRequestComment:
        """Appends a comment to an existing support ticket."""
        req = self.get_request(tenant_id, request_id)
        if not req:
            raise KeyError(f"Support request '{request_id}' not found for tenant '{tenant_id}'.")

        comment_id = f"com_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_support_request_comments
                (comment_id, request_id, tenant_id, author_id, author_name, is_internal, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (comment_id, request_id, tenant_id, author_id, author_name, 1 if is_internal else 0, message.strip(), now),
            )
            # Update request updated_at timestamp
            conn.execute(
                "UPDATE operational_support_requests SET updated_at = ? WHERE request_id = ? AND tenant_id = ?",
                (now, request_id, tenant_id),
            )

        return SupportRequestComment(
            comment_id=comment_id,
            request_id=request_id,
            tenant_id=tenant_id,
            author_id=author_id,
            author_name=author_name,
            is_internal=is_internal,
            message=message.strip(),
            created_at=now,
        )


# ===========================================================================
# 6. CUSTOMER NOTIFICATION PREFERENCE MANAGER (WP 8.9.8)
# ===========================================================================

class NotificationPreferenceManager:
    """Manages tenant user alert and notification preference settings."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_tenant_schema(self.db_path)

    def get_preferences(self, tenant_id: str, user_id: str) -> CustomerNotificationPreferences:
        """Retrieves user notification preferences or creates defaults."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT pref_id, tenant_id, user_id, notify_critical_incidents, notify_major_incidents,
                       notify_service_degradation, notify_gateway_offline, notify_sla_breach,
                       email_notifications, in_app_notifications, updated_at
                FROM operational_customer_notification_preferences
                WHERE tenant_id = ? AND user_id = ?
                """,
                (tenant_id, user_id),
            ).fetchone()

        if row:
            return CustomerNotificationPreferences(
                pref_id=row["pref_id"],
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                notify_critical_incidents=bool(row["notify_critical_incidents"]),
                notify_major_incidents=bool(row["notify_major_incidents"]),
                notify_service_degradation=bool(row["notify_service_degradation"]),
                notify_gateway_offline=bool(row["notify_gateway_offline"]),
                notify_sla_breach=bool(row["notify_sla_breach"]),
                email_notifications=bool(row["email_notifications"]),
                in_app_notifications=bool(row["in_app_notifications"]),
                updated_at=row["updated_at"],
            )

        # Create default
        pref_id = f"pref_{uuid.uuid4().hex[:12]}"
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_customer_notification_preferences
                (pref_id, tenant_id, user_id, notify_critical_incidents, notify_major_incidents,
                 notify_service_degradation, notify_gateway_offline, notify_sla_breach,
                 email_notifications, in_app_notifications, updated_at)
                VALUES (?, ?, ?, 1, 1, 1, 1, 1, 1, 1, ?)
                """,
                (pref_id, tenant_id, user_id, now),
            )
        return CustomerNotificationPreferences(
            pref_id=pref_id,
            tenant_id=tenant_id,
            user_id=user_id,
            notify_critical_incidents=True,
            notify_major_incidents=True,
            notify_service_degradation=True,
            notify_gateway_offline=True,
            notify_sla_breach=True,
            email_notifications=True,
            in_app_notifications=True,
            updated_at=now,
        )

    def update_preferences(
        self,
        tenant_id: str,
        user_id: str,
        notify_critical_incidents: Optional[bool] = None,
        notify_major_incidents: Optional[bool] = None,
        notify_service_degradation: Optional[bool] = None,
        notify_gateway_offline: Optional[bool] = None,
        notify_sla_breach: Optional[bool] = None,
        email_notifications: Optional[bool] = None,
        in_app_notifications: Optional[bool] = None,
    ) -> CustomerNotificationPreferences:
        """Updates specific notification toggles for a user."""
        curr = self.get_preferences(tenant_id, user_id)
        n_crit = curr.notify_critical_incidents if notify_critical_incidents is None else notify_critical_incidents
        n_maj = curr.notify_major_incidents if notify_major_incidents is None else notify_major_incidents
        n_deg = curr.notify_service_degradation if notify_service_degradation is None else notify_service_degradation
        n_gw = curr.notify_gateway_offline if notify_gateway_offline is None else notify_gateway_offline
        n_sla = curr.notify_sla_breach if notify_sla_breach is None else notify_sla_breach
        n_email = curr.email_notifications if email_notifications is None else email_notifications
        n_app = curr.in_app_notifications if in_app_notifications is None else in_app_notifications
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_customer_notification_preferences
                SET notify_critical_incidents = ?, notify_major_incidents = ?,
                    notify_service_degradation = ?, notify_gateway_offline = ?,
                    notify_sla_breach = ?, email_notifications = ?,
                    in_app_notifications = ?, updated_at = ?
                WHERE tenant_id = ? AND user_id = ?
                """,
                (
                    1 if n_crit else 0,
                    1 if n_maj else 0,
                    1 if n_deg else 0,
                    1 if n_gw else 0,
                    1 if n_sla else 0,
                    1 if n_email else 0,
                    1 if n_app else 0,
                    now,
                    tenant_id,
                    user_id,
                ),
            )

        return CustomerNotificationPreferences(
            pref_id=curr.pref_id,
            tenant_id=tenant_id,
            user_id=user_id,
            notify_critical_incidents=n_crit,
            notify_major_incidents=n_maj,
            notify_service_degradation=n_deg,
            notify_gateway_offline=n_gw,
            notify_sla_breach=n_sla,
            email_notifications=n_email,
            in_app_notifications=n_app,
            updated_at=now,
        )
