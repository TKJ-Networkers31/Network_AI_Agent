"""
AIRA OS — Permission Simulation & Granular Authorization Service (Workstream B).

Enforces the strict authorization hierarchy:
Org -> UserGroup -> Site -> Subtab -> Resource -> Action

Granular Action Taxonomy:
- VIEW: Inspecting/reading resource properties or telemetry
- CREATE: Provisioning new resources (devices, playbooks, users)
- UPDATE: Modifying configuration or parameters
- DELETE: Removing or decommissioning resources
- EXECUTE: Running diagnostics, scripts, or operational routines
- APPROVE: Granting operational approvals for changes
- EXPORT: Extracting topology, metrics, or audit logs
- MANAGE_PERMISSIONS: Modifying roles, groups, or access matrices
- ACCESS_SENSITIVE_DATA: Viewing credentials, secrets, or raw keys
"""

from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.tenant.permission_simulation")


class GranularAction(str, Enum):
    VIEW = "VIEW"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    APPROVE = "APPROVE"
    EXPORT = "EXPORT"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"
    ACCESS_SENSITIVE_DATA = "ACCESS_SENSITIVE_DATA"


# Mapping from (Resource Type, Granular Action) -> Required Canonical Permission(s)
RESOURCE_ACTION_MAP: Dict[Tuple[str, str], List[str]] = {
    # Devices & Inventory
    ("device", "VIEW"): ["devices.read", "inventory.device.read", "inventory.read"],
    ("device", "CREATE"): ["devices.create", "inventory.device.create"],
    ("device", "UPDATE"): ["devices.update", "inventory.device.update"],
    ("device", "DELETE"): ["devices.delete", "inventory.device.delete"],
    ("device", "EXECUTE"): ["devices.diagnostics", "inventory.device.ssh"],
    ("device", "ACCESS_SENSITIVE_DATA"): ["config.read", "settings.write"],
    ("inventory", "VIEW"): ["inventory.read"],
    ("inventory", "CREATE"): ["inventory.create", "inventory.device.create"],
    ("inventory", "UPDATE"): ["inventory.update", "inventory.device.update"],
    ("inventory", "DELETE"): ["inventory.delete", "inventory.device.delete"],
    ("inventory", "EXPORT"): ["inventory.read", "audit.export"],

    # Topology
    ("topology", "VIEW"): ["topology.read", "topology.view"],
    ("topology", "CREATE"): ["topology.create"],
    ("topology", "UPDATE"): ["topology.update"],
    ("topology", "DELETE"): ["topology.delete"],
    ("topology", "EXECUTE"): ["topology.device.discover"],
    ("topology", "EXPORT"): ["topology.read", "audit.export"],

    # NMS & Telemetry
    ("nms", "VIEW"): ["nms.read", "nms.view", "nms.metrics.read"],
    ("nms", "UPDATE"): ["nms.monitoring.configure", "nms.alerts.manage"],
    ("nms", "EXECUTE"): ["nms.alerts.manage"],

    # Network Intelligence & Operations
    ("intelligence", "VIEW"): ["dashboard.read", "dashboard.view"],
    ("intelligence", "EXECUTE"): ["automation.execute", "playbooks.execute"],
    ("intelligence", "APPROVE"): ["automation.approve"],
    ("action_center", "VIEW"): ["dashboard.read"],
    ("action_center", "EXECUTE"): ["automation.execute"],
    ("action_center", "APPROVE"): ["automation.approve"],

    # Configuration & Remediation
    ("config", "VIEW"): ["config.read"],
    ("config", "CREATE"): ["config.backup"],
    ("config", "UPDATE"): ["config.apply"],
    ("config", "EXECUTE"): ["config.apply", "config.rollback"],
    ("config", "APPROVE"): ["automation.approve"],
    ("config", "ACCESS_SENSITIVE_DATA"): ["config.read"],

    # Automations & Playbooks
    ("automation", "VIEW"): ["automation.read", "automations.view"],
    ("automation", "CREATE"): ["automation.create"],
    ("automation", "UPDATE"): ["automation.update"],
    ("automation", "EXECUTE"): ["automation.execute"],
    ("automation", "APPROVE"): ["automation.approve"],
    ("playbook", "VIEW"): ["playbooks.read", "automations.view"],
    ("playbook", "CREATE"): ["playbooks.create"],
    ("playbook", "UPDATE"): ["playbooks.update"],
    ("playbook", "DELETE"): ["playbooks.delete"],
    ("playbook", "EXECUTE"): ["playbooks.execute"],

    # User Management & Administration
    ("user", "VIEW"): ["users.read"],
    ("user", "CREATE"): ["users.create"],
    ("user", "UPDATE"): ["users.update"],
    ("user", "DELETE"): ["users.delete"],
    ("user", "MANAGE_PERMISSIONS"): ["permissions.assign", "groups.update"],
    ("group", "VIEW"): ["groups.read"],
    ("group", "CREATE"): ["groups.create"],
    ("group", "UPDATE"): ["groups.update"],
    ("group", "DELETE"): ["groups.delete"],
    ("group", "MANAGE_PERMISSIONS"): ["groups.update", "permissions.assign"],

    # Audit & Security
    ("audit", "VIEW"): ["audit.read", "user_activity.audit.read"],
    ("audit", "EXPORT"): ["audit.export"],
    ("security", "VIEW"): ["soc.dashboard.read", "soc.alerts.read"],
    ("security", "EXECUTE"): ["soc.investigation.write"],
}


class PermissionSimulationService:
    """
    Evaluates and simulates permission resolution for users across the hierarchy.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def simulate_permission(
        self,
        user_id: str,
        resource: str,
        action: str,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulates authorization evaluation for a specific user, resource, and granular action.
        """
        resolution_path: List[str] = []
        matched_rules: List[str] = []
        missing_permissions: List[str] = []
        effective_restrictions: Dict[str, Any] = {}

        action_upper = action.upper().strip()
        resource_clean = resource.strip().lower()

        # Parse resource prefix (e.g., "device:sw-core-01" -> "device")
        resource_type = resource_clean.split(":")[0] if ":" in resource_clean else resource_clean

        resolution_path.append(f"Step 1: Inspect user record for user_id='{user_id}'")

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            u_row = conn.execute(
                "SELECT user_id, username, is_internal, tenant_id, is_active, account_enabled FROM operational_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if not u_row:
                return {
                    "allowed": False,
                    "user_id": user_id,
                    "resource": resource,
                    "action": action_upper,
                    "resolution_path": ["User not found in database"],
                    "matched_rules": [],
                    "missing_permissions": ["user.exists"],
                    "effective_restrictions": {"reason": "USER_NOT_FOUND"},
                }

            username = u_row["username"]
            tenant_id = u_row["tenant_id"]
            is_internal = bool(u_row["is_internal"])
            account_enabled = bool(u_row["account_enabled"]) if "account_enabled" in u_row.keys() else True

            if not bool(u_row["is_active"]) or not account_enabled:
                resolution_path.append("Result: DENIED — User account is disabled or inactive.")
                return {
                    "allowed": False,
                    "user_id": user_id,
                    "username": username,
                    "resource": resource,
                    "action": action_upper,
                    "resolution_path": resolution_path,
                    "matched_rules": ["ACCOUNT_DISABLED"],
                    "missing_permissions": [],
                    "effective_restrictions": {"account_enabled": False},
                }

            # Step 2: Org / Tenant check
            resolution_path.append(f"Step 2: Tenant validation for tenant_id='{tenant_id}' (internal={is_internal})")
            if not is_internal and tenant_id:
                t_row = conn.execute("SELECT status FROM operational_tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
                if t_row and t_row["status"] not in ("ACTIVE", "MAINTENANCE"):
                    resolution_path.append(f"Result: DENIED — Organization '{tenant_id}' is '{t_row['status']}'")
                    return {
                        "allowed": False,
                        "user_id": user_id,
                        "username": username,
                        "resource": resource,
                        "action": action_upper,
                        "resolution_path": resolution_path,
                        "matched_rules": [f"TENANT_STATUS_{t_row['status']}"],
                        "missing_permissions": [],
                        "effective_restrictions": {"tenant_status": t_row["status"]},
                    }

            # Step 3: Load user groups and permissions
            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service(self.db_path)
            user_groups = [g["name"] for g in rbac_svc.get_user_groups(user_id)]
            effective_perms = rbac_svc.get_effective_permissions(user_id)

            resolution_path.append(f"Step 3: User belongs to groups: {user_groups}")

            # Superadmin bypass
            if "SUPER_ADMIN" in user_groups or is_internal and "ADMIN" in user_groups:
                matched_rules.append("SUPER_ADMIN_UNRESTRICTED_ACCESS")
                resolution_path.append("Step 4: Super Admin privilege detected -> ALLOW with full rights")
                return {
                    "allowed": True,
                    "user_id": user_id,
                    "username": username,
                    "resource": resource,
                    "action": action_upper,
                    "resolution_path": resolution_path,
                    "matched_rules": matched_rules,
                    "missing_permissions": [],
                    "effective_restrictions": {},
                }

            # Step 4: Resolve required canonical permissions
            required_candidates = RESOURCE_ACTION_MAP.get((resource_type, action_upper), [])
            if not required_candidates:
                # Generic fallback check
                required_candidates = [f"{resource_type}.{action_upper.lower()}", f"{resource_type}.read"]

            resolution_path.append(f"Step 4: Checking required permissions for ({resource_type}, {action_upper}): {required_candidates}")

            # Check if user has at least one matching valid permission
            has_match = False
            for req in required_candidates:
                if req in effective_perms:
                    has_match = True
                    matched_rules.append(f"PERM_ALLOWED:{req}")
                    resolution_path.append(f"Matched permission: '{req}'")
                    break

            if not has_match:
                missing_permissions.extend(required_candidates)
                resolution_path.append(f"Result: DENIED — User lacks required permission. Missing: {required_candidates}")
                return {
                    "allowed": False,
                    "user_id": user_id,
                    "username": username,
                    "resource": resource,
                    "action": action_upper,
                    "resolution_path": resolution_path,
                    "matched_rules": matched_rules,
                    "missing_permissions": missing_permissions,
                    "effective_restrictions": {"missing_permissions": missing_permissions},
                }

            # Step 5: Site Scoping Check
            if site_id:
                resolution_path.append(f"Step 5: Evaluating site boundary for site_id='{site_id}'")
                # Customer users are restricted to their tenant's sites
                if not is_internal and tenant_id:
                    s_row = conn.execute(
                        "SELECT site_id FROM operational_sites WHERE site_id = ? AND tenant_id = ?",
                        (site_id, tenant_id),
                    ).fetchone()
                    if not s_row:
                        resolution_path.append(f"Result: DENIED — Site '{site_id}' does not belong to tenant '{tenant_id}'")
                        return {
                            "allowed": False,
                            "user_id": user_id,
                            "username": username,
                            "resource": resource,
                            "action": action_upper,
                            "resolution_path": resolution_path,
                            "matched_rules": ["SITE_CROSS_TENANT_VIOLATION"],
                            "missing_permissions": [],
                            "effective_restrictions": {"site_id": site_id, "boundary_error": "CROSS_TENANT_ACCESS_DENIED"},
                        }
                resolution_path.append(f"Site '{site_id}' access authorized.")

            resolution_path.append("Step 6: All hierarchy gates passed -> ALLOW")
            return {
                "allowed": True,
                "user_id": user_id,
                "username": username,
                "resource": resource,
                "action": action_upper,
                "resolution_path": resolution_path,
                "matched_rules": matched_rules,
                "missing_permissions": [],
                "effective_restrictions": effective_restrictions,
            }


_simulation_service: Optional[PermissionSimulationService] = None


def get_permission_simulation_service(db_path: Optional[Path] = None) -> PermissionSimulationService:
    global _simulation_service
    if _simulation_service is None or db_path is not None:
        _simulation_service = PermissionSimulationService(db_path)
    return _simulation_service
