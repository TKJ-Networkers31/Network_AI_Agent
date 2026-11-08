"""
AIRA OS — Centralized Group-Based RBAC & User Activity Monitoring Service (Phase F.1).

Implements:
- MikroTik-style Group & Permission Management:
  Users -> Groups -> Permissions (Module.Resource.Action)
- Multiple group membership with explicit DENY taking precedence over ALLOW.
- Centralized Permission Registry (43 canonical permissions).
- 6 System Default Groups: SUPER_ADMIN, ADMIN, NOC, SOC, NETWORK_ENGINEER, READ_ONLY.
- User Activity Monitoring (Real-time online/offline via heartbeat, session monitoring & revocation).
- Operational Security & Audit Logging.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.rbac.service")

# -----------------------------------------------------------------------------
# 1. CANONICAL PERMISSIONS REGISTRY
# -----------------------------------------------------------------------------

ALL_PERMISSIONS: List[Dict[str, str]] = [
    # General
    {"permission_id": "dashboard.read", "module": "General", "resource": "dashboard", "action": "read", "description": "View main system dashboard"},
    {"permission_id": "settings.read", "module": "General", "resource": "settings", "action": "read", "description": "View system settings"},
    {"permission_id": "settings.write", "module": "General", "resource": "settings", "action": "write", "description": "Modify system settings"},

    # User Management
    {"permission_id": "users.read", "module": "User Management", "resource": "users", "action": "read", "description": "View user directory and profiles"},
    {"permission_id": "users.create", "module": "User Management", "resource": "users", "action": "create", "description": "Provision new user accounts"},
    {"permission_id": "users.update", "module": "User Management", "resource": "users", "action": "update", "description": "Update user profiles and passwords"},
    {"permission_id": "users.disable", "module": "User Management", "resource": "users", "action": "disable", "description": "Enable or disable user accounts"},
    {"permission_id": "users.delete", "module": "User Management", "resource": "users", "action": "delete", "description": "Delete user accounts"},
    {"permission_id": "groups.read", "module": "User Management", "resource": "groups", "action": "read", "description": "View group directory and details"},
    {"permission_id": "groups.create", "module": "User Management", "resource": "groups", "action": "create", "description": "Create custom access groups"},
    {"permission_id": "groups.update", "module": "User Management", "resource": "groups", "action": "update", "description": "Modify groups and permission matrix"},
    {"permission_id": "groups.delete", "module": "User Management", "resource": "groups", "action": "delete", "description": "Delete custom groups"},
    {"permission_id": "permissions.read", "module": "User Management", "resource": "permissions", "action": "read", "description": "View permissions registry"},
    {"permission_id": "permissions.assign", "module": "User Management", "resource": "permissions", "action": "assign", "description": "Assign groups and permissions to users"},

    # User Activity
    {"permission_id": "user_activity.read", "module": "User Activity", "resource": "user_activity", "action": "read", "description": "View user online status and activity"},
    {"permission_id": "user_activity.sessions.read", "module": "User Activity", "resource": "sessions", "action": "read", "description": "View active user sessions"},
    {"permission_id": "user_activity.sessions.revoke", "module": "User Activity", "resource": "sessions", "action": "revoke", "description": "Terminate active user sessions"},
    {"permission_id": "user_activity.audit.read", "module": "User Activity", "resource": "audit", "action": "read", "description": "View user login and session audit logs"},

    # Inventory
    {"permission_id": "inventory.read", "module": "Inventory", "resource": "inventory", "action": "read", "description": "View shared network inventory"},
    {"permission_id": "inventory.create", "module": "Inventory", "resource": "inventory", "action": "create", "description": "Add devices to shared inventory"},
    {"permission_id": "inventory.update", "module": "Inventory", "resource": "inventory", "action": "update", "description": "Update inventory devices and metadata"},
    {"permission_id": "inventory.delete", "module": "Inventory", "resource": "inventory", "action": "delete", "description": "Remove devices from inventory"},

    # Devices
    {"permission_id": "devices.read", "module": "Devices", "resource": "devices", "action": "read", "description": "Read device status and interfaces"},
    {"permission_id": "devices.create", "module": "Devices", "resource": "devices", "action": "create", "description": "Register network devices"},
    {"permission_id": "devices.update", "module": "Devices", "resource": "devices", "action": "update", "description": "Modify device configurations"},
    {"permission_id": "devices.delete", "module": "Devices", "resource": "devices", "action": "delete", "description": "Decommission devices"},
    {"permission_id": "devices.diagnostics", "module": "Devices", "resource": "devices", "action": "diagnostics", "description": "Run diagnostic pings, traces, ARP lookups"},

    # Topology
    {"permission_id": "topology.read", "module": "Topology", "resource": "topology", "action": "read", "description": "View network topology graph"},
    {"permission_id": "topology.create", "module": "Topology", "resource": "topology", "action": "create", "description": "Create topology nodes and wiring"},
    {"permission_id": "topology.update", "module": "Topology", "resource": "topology", "action": "update", "description": "Update topology wiring and layout"},
    {"permission_id": "topology.delete", "module": "Topology", "resource": "topology", "action": "delete", "description": "Delete topology nodes and edges"},

    # NMS
    {"permission_id": "nms.read", "module": "NMS", "resource": "nms", "action": "read", "description": "View NMS telemetry and monitoring"},
    {"permission_id": "nms.metrics.read", "module": "NMS", "resource": "metrics", "action": "read", "description": "Read interface metrics and bandwidth"},
    {"permission_id": "nms.alerts.read", "module": "NMS", "resource": "alerts", "action": "read", "description": "View network alerts and incidents"},
    {"permission_id": "nms.alerts.manage", "module": "NMS", "resource": "alerts", "action": "manage", "description": "Acknowledge and manage alerts"},

    # Configuration
    {"permission_id": "config.read", "module": "Configuration", "resource": "config", "action": "read", "description": "Read device configuration snapshots"},
    {"permission_id": "config.backup", "module": "Configuration", "resource": "config", "action": "backup", "description": "Trigger device configuration backup"},
    {"permission_id": "config.apply", "module": "Configuration", "resource": "config", "action": "apply", "description": "Deploy configuration changes to devices"},
    {"permission_id": "config.rollback", "module": "Configuration", "resource": "config", "action": "rollback", "description": "Rollback device configurations"},

    # Automation
    {"permission_id": "automation.read", "module": "Automation", "resource": "automation", "action": "read", "description": "View network automations and jobs"},
    {"permission_id": "automation.create", "module": "Automation", "resource": "automation", "action": "create", "description": "Create automated network jobs"},
    {"permission_id": "automation.update", "module": "Automation", "resource": "automation", "action": "update", "description": "Modify automation workflows"},
    {"permission_id": "automation.execute", "module": "Automation", "resource": "automation", "action": "execute", "description": "Execute network automation routines"},
    {"permission_id": "automation.approve", "module": "Automation", "resource": "automation", "action": "approve", "description": "Approve sensitive automations"},

    # Playbooks
    {"permission_id": "playbooks.read", "module": "Playbooks", "resource": "playbooks", "action": "read", "description": "View Ansible-compatible playbooks"},
    {"permission_id": "playbooks.create", "module": "Playbooks", "resource": "playbooks", "action": "create", "description": "Author new network playbooks"},
    {"permission_id": "playbooks.update", "module": "Playbooks", "resource": "playbooks", "action": "update", "description": "Edit playbook tasks and variables"},
    {"permission_id": "playbooks.delete", "module": "Playbooks", "resource": "playbooks", "action": "delete", "description": "Remove playbooks"},
    {"permission_id": "playbooks.execute", "module": "Playbooks", "resource": "playbooks", "action": "execute", "description": "Run playbooks against inventory"},

    # SOC
    {"permission_id": "soc.dashboard.read", "module": "SOC", "resource": "soc", "action": "read", "description": "View Security Operations dashboard"},
    {"permission_id": "soc.events.read", "module": "SOC", "resource": "events", "action": "read", "description": "Read security event logs"},
    {"permission_id": "soc.alerts.read", "module": "SOC", "resource": "alerts", "action": "read", "description": "View security threat alerts"},
    {"permission_id": "soc.incidents.read", "module": "SOC", "resource": "incidents", "action": "read", "description": "View security incident tickets"},
    {"permission_id": "soc.investigation.write", "module": "SOC", "resource": "investigation", "action": "write", "description": "Perform security investigations"},

    # Audit
    {"permission_id": "audit.read", "module": "Audit", "resource": "audit", "action": "read", "description": "View platform security audit logs"},
    {"permission_id": "audit.export", "module": "Audit", "resource": "audit", "action": "export", "description": "Export platform audit records"},

    # Navigation / UI Access Permissions (Phase F.2)
    {"permission_id": "dashboard.view", "module": "Navigation", "resource": "dashboard", "action": "view", "description": "Access dashboard navigation tab"},
    {"permission_id": "workspace.view", "module": "Navigation", "resource": "workspace", "action": "view", "description": "Access Ask AIRA conversational workspace"},
    {"permission_id": "inventory.view", "module": "Navigation", "resource": "inventory", "action": "view", "description": "Access infrastructure and devices tab"},
    {"permission_id": "topology.view", "module": "Navigation", "resource": "topology", "action": "view", "description": "Access network topology visualizer tab"},
    {"permission_id": "nms.view", "module": "Navigation", "resource": "nms", "action": "view", "description": "Access NMS monitoring and telemetry tab"},
    {"permission_id": "automations.view", "module": "Navigation", "resource": "automations", "action": "view", "description": "Access network automations and playbooks tab"},
    {"permission_id": "files.view", "module": "Navigation", "resource": "files", "action": "view", "description": "Access workspace file management tab"},
    {"permission_id": "models.view", "module": "Navigation", "resource": "models", "action": "view", "description": "Access AI model policies tab"},
    {"permission_id": "logs.view", "module": "Navigation", "resource": "logs", "action": "view", "description": "Access platform activity and audit logs tab"},
    {"permission_id": "settings.view", "module": "Navigation", "resource": "settings", "action": "view", "description": "Access settings navigation center"},
    {"permission_id": "admin.view", "module": "Navigation", "resource": "admin", "action": "view", "description": "Access AIRA Control Plane admin site"},

    # Models Management Permissions
    {"permission_id": "models.read", "module": "Models", "resource": "models", "action": "read", "description": "View AI models list and routing assignments"},
    {"permission_id": "models.manage", "module": "Models", "resource": "models", "action": "manage", "description": "Create, edit, delete models and update routing/fallback policy"},

    # Settings & Personalization Permissions (Phase F.2)
    {"permission_id": "settings.memory.view", "module": "Settings", "resource": "memory", "action": "view", "description": "View AI long-term memories in settings"},
    {"permission_id": "settings.memory.update", "module": "Settings", "resource": "memory", "action": "update", "description": "Create, modify or delete AI long-term memories"},
    {"permission_id": "settings.persona.view", "module": "Settings", "resource": "persona", "action": "view", "description": "View AI persona and instructions in settings"},
    {"permission_id": "settings.persona.update", "module": "Settings", "resource": "persona", "action": "update", "description": "Modify AI persona, presets, and system instructions"},

    # Granular Action Permissions (Phase F.2)
    {"permission_id": "inventory.device.create", "module": "Inventory", "resource": "device", "action": "create", "description": "Register and add new network device to inventory"},
    {"permission_id": "inventory.device.read", "module": "Inventory", "resource": "device", "action": "read", "description": "Inspect inventory device properties and specs"},
    {"permission_id": "inventory.device.update", "module": "Inventory", "resource": "device", "action": "update", "description": "Update inventory device parameters or credentials"},
    {"permission_id": "inventory.device.delete", "module": "Inventory", "resource": "device", "action": "delete", "description": "Decommission and remove device from inventory"},
    {"permission_id": "inventory.device.ssh", "module": "Inventory", "resource": "device", "action": "ssh", "description": "Open live interactive SSH terminal to inventory device"},
    {"permission_id": "topology.device.discover", "module": "Topology", "resource": "device", "action": "discover", "description": "Initiate network topology discovery scan"},
    {"permission_id": "nms.monitoring.read", "module": "NMS", "resource": "monitoring", "action": "read", "description": "Poll and view real-time NMS telemetry and statistics"},
    {"permission_id": "nms.monitoring.configure", "module": "NMS", "resource": "monitoring", "action": "configure", "description": "Configure NMS thresholds, alerts, and polling rate"},
    {"permission_id": "gateways.read", "module": "Edge Gateways", "resource": "gateways", "action": "read", "description": "View edge gateway instances and telemetry"},
]

DEFAULT_GROUP_PERMISSIONS: Dict[str, List[str]] = {
    "SUPER_ADMIN": [p["permission_id"] for p in ALL_PERMISSIONS],
    "ADMIN": [
        "dashboard.read", "settings.read", "settings.write",
        "users.read", "users.create", "users.update", "users.disable",
        "groups.read", "permissions.read", "permissions.assign",
        "user_activity.read", "user_activity.sessions.read", "user_activity.sessions.revoke", "user_activity.audit.read",
        "audit.read", "gateways.read",
        # Navigation
        "dashboard.view", "workspace.view", "inventory.view", "topology.view", "nms.view",
        "automations.view", "files.view", "logs.view", "settings.view", "admin.view",
        # Settings
        "settings.memory.view", "settings.memory.update", "settings.persona.view", "settings.persona.update",
        # Inventory read
        "inventory.read", "inventory.device.read",
    ],
    "NOC": [
        "dashboard.read", "inventory.read", "devices.read", "topology.read",
        "nms.read", "nms.metrics.read", "nms.alerts.read", "audit.read", "gateways.read", "playbooks.read",
        # Navigation
        "dashboard.view", "workspace.view", "inventory.view", "topology.view", "nms.view", "logs.view", "settings.view",
        # Settings
        "settings.memory.view", "settings.persona.view",
        # Action reads
        "inventory.device.read", "nms.monitoring.read",
    ],
    "SOC": [
        "dashboard.read", "soc.dashboard.read", "soc.events.read", "soc.alerts.read", "soc.incidents.read", "soc.investigation.write", "audit.read",
        # Navigation
        "dashboard.view", "workspace.view", "logs.view", "settings.view",
        # Settings
        "settings.memory.view", "settings.persona.view",
    ],
    "NETWORK_ENGINEER": [
        "dashboard.read", "settings.read",
        "inventory.read", "inventory.create", "inventory.update",
        "devices.read", "devices.create", "devices.update", "devices.diagnostics",
        "topology.read", "topology.create", "topology.update",
        "nms.read", "nms.metrics.read", "nms.alerts.read", "nms.alerts.manage",
        "config.read", "config.backup", "config.apply", "config.rollback",
        "automation.read", "automation.create", "automation.update", "automation.execute",
        "playbooks.read", "playbooks.create", "playbooks.update", "playbooks.execute",
        "audit.read", "gateways.read",
        # Navigation
        "dashboard.view", "workspace.view", "inventory.view", "topology.view", "nms.view",
        "automations.view", "files.view", "logs.view", "settings.view",
        # Settings
        "settings.memory.view", "settings.memory.update", "settings.persona.view", "settings.persona.update",
        # Actions
        "inventory.device.create", "inventory.device.read", "inventory.device.update",
        "inventory.device.delete", "inventory.device.ssh", "topology.device.discover",
        "nms.monitoring.read", "nms.monitoring.configure",
    ],
    "READ_ONLY": [
        "dashboard.read", "inventory.read", "devices.read", "topology.read",
        "nms.read", "nms.metrics.read", "nms.alerts.read", "soc.dashboard.read", "soc.events.read", "audit.read",
        "playbooks.read", "automation.read", "gateways.read",
        # Navigation
        "dashboard.view", "workspace.view", "inventory.view", "topology.view", "nms.view", "automations.view", "logs.view", "settings.view",
        # Settings
        "settings.memory.view", "settings.persona.view",
        # Action reads
        "inventory.device.read", "nms.monitoring.read",
    ],
    "USER": [
        "dashboard.read", "dashboard.view", "workspace.view", "settings.view",
        "settings.memory.view", "settings.memory.update",
        "settings.persona.view", "settings.persona.update",
        "inventory.read", "devices.read", "topology.read", "nms.read", "nms.metrics.read", "nms.alerts.read",
        "playbooks.read", "automation.read", "gateways.read", "audit.read",
    ],
}


class RBACService:
    """Enterprise service managing Groups, Permissions, and User Activity Monitoring."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    # -------------------------------------------------------------------------
    # 1. Effective Permissions Resolution (Deny overrides Allow)
    # -------------------------------------------------------------------------

    def get_user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns all group records assigned to a user."""
        if not user_id:
            return []

        # Resolve username to UUID if needed
        actual_uid = user_id
        if not str(actual_uid).startswith("usr_"):
            with topology_transaction(self.db_path, write=False) as conn:
                u = conn.execute("SELECT user_id FROM operational_users WHERE username = ?", (str(actual_uid),)).fetchone()
                if u:
                    actual_uid = u[0]

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT g.group_id, g.name, g.description, g.is_system, m.assigned_at
                FROM operational_groups g
                JOIN operational_user_group_memberships m ON g.group_id = m.group_id
                WHERE m.user_id = ?
                ORDER BY g.name ASC
                """,
                (actual_uid,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_user_group_ids(self, user_id: str) -> List[str]:
        return [g["group_id"] for g in self.get_user_groups(user_id)]

    def get_effective_permissions(self, user_id: str) -> Set[str]:
        """
        Computes the effective permissions for a user:
        1. If user is in SUPER_ADMIN group -> All permissions granted.
        2. Otherwise, union of all ALLOW permissions across user groups.
        3. Any explicit DENY in ANY assigned group strips that permission.
        """
        # Superadmin check by username
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            u = conn.execute("SELECT username FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if u and (u["username"] or "").lower() in {"lingga_admin", "admin"}:
                return {p["permission_id"] for p in ALL_PERMISSIONS}

        groups = self.get_user_groups(user_id)
        if not groups:
            # Check legacy role fallback (PLATFORM_OWNER has SUPER_ADMIN permissions)
            with topology_transaction(self.db_path, write=False) as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute(
                    "SELECT role_type FROM operational_user_roles WHERE user_id = ? AND role_type IN ('PLATFORM_OWNER', 'SUPERADMIN', 'PLATFORM_SUPER_ADMIN')",
                    (user_id,),
                ).fetchone()
                if r:
                    return {p["permission_id"] for p in ALL_PERMISSIONS}
            return set()

        group_names = {g["name"] for g in groups}
        group_ids = [g["group_id"] for g in groups]

        # SUPER_ADMIN gets all permissions
        if "SUPER_ADMIN" in group_names or "grp_super_admin" in group_ids:
            return {p["permission_id"] for p in ALL_PERMISSIONS}

        placeholders = ",".join(["?"] * len(group_ids))
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT permission_id, effect
                FROM operational_group_permissions
                WHERE group_id IN ({placeholders})
                """,
                group_ids,
            ).fetchall()

        allowed: Set[str] = set()
        denied: Set[str] = set()

        for row in rows:
            perm = row["permission_id"]
            effect = row["effect"].upper()
            if effect == "DENY":
                denied.add(perm)
            elif effect == "ALLOW":
                allowed.add(perm)

        # Deny strictly overrides Allow
        return allowed - denied

    def has_permission(self, user_id: str, permission: str) -> bool:
        """Evaluates whether the user holds a specific permission."""
        effective = self.get_effective_permissions(user_id)
        return permission in effective

    def get_effective_permissions_preview(self, group_ids: List[str]) -> Set[str]:
        """Calculates preview of effective permissions given a set of group IDs."""
        if not group_ids:
            return set()
        placeholders = ",".join(["?"] * len(group_ids))
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            # Check if any is SUPER_ADMIN
            names = conn.execute(
                f"SELECT name FROM operational_groups WHERE group_id IN ({placeholders})",
                group_ids,
            ).fetchall()
            if any(n["name"] == "SUPER_ADMIN" for n in names):
                return {p["permission_id"] for p in ALL_PERMISSIONS}

            rows = conn.execute(
                f"""
                SELECT permission_id, effect
                FROM operational_group_permissions
                WHERE group_id IN ({placeholders})
                """,
                group_ids,
            ).fetchall()

        allowed: Set[str] = set()
        denied: Set[str] = set()
        for r in rows:
            if r["effect"].upper() == "DENY":
                denied.add(r["permission_id"])
            else:
                allowed.add(r["permission_id"])
        return allowed - denied

    # -------------------------------------------------------------------------
    # 2. Group Management (CRUD, Duplicate, Permission Matrix)
    # -------------------------------------------------------------------------

    def list_groups(self) -> List[Dict[str, Any]]:
        """Lists all groups along with their member counts and permission count."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT g.group_id, g.name, g.description, g.is_system, g.created_at, g.updated_at,
                       (SELECT COUNT(*) FROM operational_user_group_memberships m WHERE m.group_id = g.group_id) AS member_count,
                       (SELECT COUNT(*) FROM operational_group_permissions gp WHERE gp.group_id = g.group_id AND gp.effect = 'ALLOW') AS permission_count
                FROM operational_groups g
                ORDER BY g.is_system DESC, g.name ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single group including its full permission mapping and member list."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM operational_groups WHERE group_id = ? OR name = ?",
                (group_id, group_id),
            ).fetchone()
            if not row:
                return None
            group = dict(row)
            actual_id = group["group_id"]

            # Permissions mapping
            p_rows = conn.execute(
                "SELECT permission_id, effect FROM operational_group_permissions WHERE group_id = ?",
                (actual_id,),
            ).fetchall()
            group["permissions"] = {r["permission_id"]: r["effect"] for r in p_rows}

            # Members
            m_rows = conn.execute(
                """
                SELECT u.user_id, u.username, u.display_name, m.assigned_at
                FROM operational_users u
                JOIN operational_user_group_memberships m ON u.user_id = m.user_id
                WHERE m.group_id = ?
                """,
                (actual_id,),
            ).fetchall()
            group["members"] = [dict(m) for m in m_rows]
            return group

    def create_group(
        self,
        name: str,
        description: str = "",
        permissions: Optional[List[Dict[str, str]]] = None,
        is_system: bool = False,
    ) -> Dict[str, Any]:
        """Creates a new group with specified permissions (list of {'permission_id': str, 'effect': 'ALLOW'/'DENY'})."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Group name cannot be empty.")

        now_iso = datetime.now(timezone.utc).isoformat()
        group_id = f"grp_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_groups (group_id, name, description, is_system, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (group_id, clean_name, description.strip(), 1 if is_system else 0, now_iso, now_iso),
            )
            if permissions:
                for p in permissions:
                    pid = p["permission_id"]
                    effect = p.get("effect", "ALLOW").upper()
                    conn.execute(
                        """
                        INSERT INTO operational_group_permissions (group_id, permission_id, effect, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (group_id, pid, effect, now_iso),
                    )

        return self.get_group(group_id)

    def update_group(
        self,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Updates group details and/or permission matrix."""
        existing = self.get_group(group_id)
        if not existing:
            raise ValueError(f"Group '{group_id}' not found.")

        actual_id = existing["group_id"]
        # SUPER_ADMIN cannot be renamed or deleted
        if existing["name"] == "SUPER_ADMIN" and name and name != "SUPER_ADMIN":
            raise ValueError("Cannot rename system group 'SUPER_ADMIN'.")

        now_iso = datetime.now(timezone.utc).isoformat()
        new_name = name.strip() if name is not None else existing["name"]
        new_desc = description.strip() if description is not None else existing["description"]

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_groups
                SET name = ?, description = ?, updated_at = ?
                WHERE group_id = ?
                """,
                (new_name, new_desc, now_iso, actual_id),
            )
            if permissions is not None:
                # Replace permissions
                conn.execute("DELETE FROM operational_group_permissions WHERE group_id = ?", (actual_id,))
                for p in permissions:
                    pid = p["permission_id"]
                    effect = p.get("effect", "ALLOW").upper()
                    conn.execute(
                        """
                        INSERT INTO operational_group_permissions (group_id, permission_id, effect, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (actual_id, pid, effect, now_iso),
                    )

        return self.get_group(actual_id)

    def delete_group(self, group_id: str) -> bool:
        """Deletes a custom group. System groups cannot be deleted."""
        existing = self.get_group(group_id)
        if not existing:
            return False
        if bool(existing["is_system"]) or existing["name"] == "SUPER_ADMIN":
            raise PermissionError(f"System group '{existing['name']}' is immutable and cannot be deleted.")

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute("DELETE FROM operational_groups WHERE group_id = ?", (existing["group_id"],))
            return True

    def duplicate_group(self, source_group_id: str, new_name: str) -> Dict[str, Any]:
        """Clones an existing group's permissions into a new custom group."""
        source = self.get_group(source_group_id)
        if not source:
            raise ValueError(f"Source group '{source_group_id}' not found.")

        perms = [
            {"permission_id": pid, "effect": eff}
            for pid, eff in source.get("permissions", {}).items()
        ]
        return self.create_group(
            name=new_name.strip(),
            description=f"Cloned from {source['name']}: {source.get('description', '')}",
            permissions=perms,
            is_system=False,
        )

    def assign_user_groups(self, user_id: str, group_ids_or_names: List[str]) -> bool:
        """Replaces the user's group memberships with the given groups."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            # Resolve group IDs
            resolved_ids = []
            for g in group_ids_or_names:
                row = conn.execute("SELECT group_id FROM operational_groups WHERE group_id = ? OR name = ?", (g, g)).fetchone()
                if row:
                    resolved_ids.append(row["group_id"])

            conn.execute("DELETE FROM operational_user_group_memberships WHERE user_id = ?", (user_id,))
            for gid in resolved_ids:
                conn.execute(
                    """
                    INSERT INTO operational_user_group_memberships (user_id, group_id, assigned_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, gid, now_iso),
                )
            return True

    def list_all_permissions(self) -> List[Dict[str, str]]:
        return list(ALL_PERMISSIONS)

    # -------------------------------------------------------------------------
    # 3. User Activity Monitoring & Session Management
    # -------------------------------------------------------------------------

    def log_activity_event(
        self,
        username: str,
        event_type: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Logs an authenticated security or administrative activity event."""
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = f"act_{uuid.uuid4().hex[:12]}"
        details_json = json.dumps(details or {})

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_user_activity_events
                (event_id, user_id, username, event_type, ip_address, user_agent, details_json, actor_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, user_id, username, event_type, ip_address, user_agent, details_json, actor_id, now_iso),
            )
        return {
            "event_id": event_id,
            "username": username,
            "event_type": event_type,
            "created_at": now_iso,
        }

    def record_heartbeat(self, session_id: str, user_id: str) -> bool:
        """Updates last_activity_at on the active session and on the user record."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_user_sessions SET last_activity_at = ? WHERE session_id = ? AND status = 'ACTIVE'",
                (now_iso, session_id),
            )
            conn.execute(
                "UPDATE operational_users SET last_activity_at = ? WHERE user_id = ?",
                (now_iso, user_id),
            )
            return True

    def get_user_status(self, user_id: str, idle_timeout_sec: int = 300) -> str:
        """
        Determines user online status:
        - DISABLED: account_enabled == 0
        - ONLINE: has at least one active session with heartbeat within idle_timeout_sec
        - SESSION_EXPIRED: active session exists but expired or timed out
        - OFFLINE: no active sessions
        """
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            u_row = conn.execute("SELECT account_enabled FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if u_row and not bool(u_row["account_enabled"]):
                return "DISABLED"

            now = datetime.now(timezone.utc)
            rows = conn.execute(
                "SELECT session_id, status, expires_at_utc, last_activity_at FROM operational_user_sessions WHERE user_id = ? AND status = 'ACTIVE'",
                (user_id,),
            ).fetchall()

            if not rows:
                return "OFFLINE"

            has_valid_session = False
            for s in rows:
                expires_at_str = s["expires_at_utc"]
                try:
                    exp_dt = datetime.fromisoformat(expires_at_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if exp_dt < now:
                        continue  # Expired
                except Exception:
                    pass

                last_act_str = s["last_activity_at"]
                if last_act_str:
                    try:
                        act_dt = datetime.fromisoformat(last_act_str)
                        if act_dt.tzinfo is None:
                            act_dt = act_dt.replace(tzinfo=timezone.utc)
                        delta = (now - act_dt).total_seconds()
                        if delta <= idle_timeout_sec:
                            return "ONLINE"
                        has_valid_session = True
                    except Exception:
                        pass
                else:
                    has_valid_session = True

            return "SESSION_EXPIRED" if has_valid_session else "OFFLINE"

    def list_active_sessions(self, user_id: Optional[str] = None, idle_timeout_sec: int = 300) -> List[Dict[str, Any]]:
        """Lists active user sessions with masked session ID and platform metadata."""
        now = datetime.now(timezone.utc)
        query = """
            SELECT s.session_id, s.user_id, s.status, s.created_at, s.expires_at_utc,
                   s.last_activity_at, s.ip_address, s.user_agent, u.username, u.display_name
            FROM operational_user_sessions s
            JOIN operational_users u ON s.user_id = u.user_id
            WHERE s.status = 'ACTIVE'
        """
        params: List[Any] = []
        if user_id:
            query += " AND s.user_id = ?"
            params.append(user_id)
        query += " ORDER BY s.last_activity_at DESC"

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                sid = d["session_id"]
                masked_id = f"{sid[:6]}...{sid[-4:]}" if len(sid) > 10 else sid
                d["masked_session_id"] = masked_id

                # Calculate is_online
                is_online = False
                if d.get("last_activity_at"):
                    try:
                        act_dt = datetime.fromisoformat(d["last_activity_at"])
                        if act_dt.tzinfo is None:
                            act_dt = act_dt.replace(tzinfo=timezone.utc)
                        if (now - act_dt).total_seconds() <= idle_timeout_sec:
                            is_online = True
                    except Exception:
                        pass
                d["is_online"] = is_online
                results.append(d)
            return results

    def revoke_session(self, session_id: str, actor_id: Optional[str] = None) -> bool:
        """Revokes a specific session immediately on the server."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            s_row = conn.execute("SELECT user_id FROM operational_user_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not s_row:
                return False
            user_id = s_row["user_id"]
            conn.execute("UPDATE operational_user_sessions SET status = 'REVOKED' WHERE session_id = ?", (session_id,))
            u_row = conn.execute("SELECT username FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            uname = u_row["username"] if u_row else user_id

        self.log_activity_event(
            username=uname,
            event_type="SESSION_REVOKED",
            user_id=user_id,
            details={"session_id": session_id},
            actor_id=actor_id,
        )
        return True

    def revoke_all_user_sessions(self, user_id: str, actor_id: Optional[str] = None) -> int:
        """Revokes all active sessions belonging to a user."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            u_row = conn.execute("SELECT username FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            uname = u_row["username"] if u_row else user_id
            cursor = conn.execute(
                "UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'",
                (user_id,),
            )
            count = cursor.rowcount

        self.log_activity_event(
            username=uname,
            event_type="ALL_SESSIONS_REVOKED",
            user_id=user_id,
            details={"revoked_count": count},
            actor_id=actor_id,
        )
        return count

    def list_activity_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieves paginated audit trail of user activity events."""
        query = "SELECT * FROM operational_user_activity_events WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["details"] = json.loads(item.get("details_json") or "{}")
                except Exception:
                    item["details"] = {}
                results.append(item)
            return results


_rbac_service: Optional[RBACService] = None


def get_rbac_service(db_path: Optional[Path] = None) -> RBACService:
    global _rbac_service
    if _rbac_service is None or db_path is not None:
        _rbac_service = RBACService(db_path=db_path)
    return _rbac_service
