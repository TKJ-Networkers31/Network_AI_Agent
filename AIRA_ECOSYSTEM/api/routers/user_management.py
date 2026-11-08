"""
AIRA OS — Admin User Management & Group RBAC Router (/api/v1/admin).

Provides MikroTik-style administration endpoints:
- User Directory & Provisioning (users.read, users.create, users.update, users.disable)
- Group & Permission Matrix Management (groups.read, groups.create, groups.update, groups.delete, permissions.read)
- User Activity Monitoring & Session Revocation (user_activity.read, user_activity.sessions.read, user_activity.sessions.revoke, user_activity.audit.read)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.tenant.auth_deps import require_permission
from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext
from core.tenant.rbac_service import get_rbac_service

router = APIRouter(prefix="/api/v1/admin", tags=["user_management"])

_identity_mgr = IdentityManager()
_rbac_svc = get_rbac_service()


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    display_name: Optional[str] = None
    email: Optional[str] = None
    group_name: Optional[str] = "READ_ONLY"
    groups: Optional[List[str]] = None


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    group: Optional[str] = None
    groups: Optional[List[str]] = None
    password: Optional[str] = None


class ToggleUserStatusRequest(BaseModel):
    enabled: bool


class PermissionItem(BaseModel):
    permission_id: str
    effect: str = "ALLOW"


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = ""
    permissions: List[PermissionItem] = Field(default_factory=list)


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[PermissionItem]] = None


class DuplicateGroupRequest(BaseModel):
    new_name: str = Field(..., min_length=2, max_length=50)


class PermissionsPreviewRequest(BaseModel):
    group_ids: List[str]


class UserSimulationRequest(BaseModel):
    user_id: str
    resource: str
    action: str
    site_id: Optional[str] = None


# -----------------------------------------------------------------------------
# 1. USER MANAGEMENT ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/users")
def list_users(
    tenant_id: Optional[str] = None,
    ctx: TenantContext = Depends(require_permission("users.read")),
) -> Dict[str, Any]:
    """Lists all registered users along with their groups, status, and activity timestamps."""
    users = _identity_mgr.list_users(tenant_id=tenant_id)
    return {"success": True, "users": users, "total": len(users)}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    ctx: TenantContext = Depends(require_permission("users.create")),
) -> Dict[str, Any]:
    """Provisions a new user account with assigned group memberships."""
    target_groups = payload.groups or ([payload.group_name] if payload.group_name else ["READ_ONLY"])
    primary_group = target_groups[0] if target_groups else "READ_ONLY"

    try:
        user = _identity_mgr.create_user(
            username=payload.username,
            password=payload.password,
            email=payload.email,
            display_name=payload.display_name,
            group_name=primary_group,
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{payload.username}' sudah terdaftar.",
            )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # If multiple groups provided, assign all
    if len(target_groups) > 1:
        _rbac_svc.assign_user_groups(user.user_id, target_groups)

    _rbac_svc.log_activity_event(
        username=user.username,
        event_type="USER_CREATED",
        user_id=user.user_id,
        details={"groups": target_groups, "display_name": user.display_name},
        actor_id=ctx.user_id,
    )

    fresh_user = _identity_mgr.get_user_by_id(user.user_id)
    return {
        "user_id": fresh_user.user_id,
        "username": fresh_user.username,
        "display_name": fresh_user.display_name,
        "email": fresh_user.email,
        "account_enabled": fresh_user.account_enabled,
        "groups": fresh_user.groups,
        "created_at": fresh_user.created_at,
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    ctx: TenantContext = Depends(require_permission("users.update")),
) -> Dict[str, Any]:
    """Updates user display_name, password, and assigned groups."""
    existing = _identity_mgr.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    target_groups = payload.groups
    if target_groups is None and payload.group is not None:
        target_groups = [payload.group]

    try:
        updated = _identity_mgr.update_user(
            user_id=user_id,
            display_name=payload.display_name,
            group_names=target_groups,
            password=payload.password,
            actor_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "user_id": updated.user_id,
        "username": updated.username,
        "display_name": updated.display_name,
        "email": updated.email,
        "account_enabled": updated.account_enabled,
        "groups": updated.groups,
        "updated_at": updated.updated_at,
    }


@router.post("/users/{user_id}/toggle-status")
def toggle_user_status(
    user_id: str,
    payload: ToggleUserStatusRequest,
    ctx: TenantContext = Depends(require_permission("users.disable")),
) -> Dict[str, Any]:
    """Enables or disables a user account. Disabling revokes all active sessions immediately."""
    existing = _identity_mgr.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    # Guard: cannot disable the active superadmin
    if existing.username == "lingga_admin" and not payload.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Akun Superadmin platform utama tidak dapat dinonaktifkan.",
        )

    _identity_mgr.toggle_account_enabled(user_id, payload.enabled, actor_id=ctx.user_id)
    return {
        "user_id": user_id,
        "account_enabled": payload.enabled,
        "message": f"Akun pengguna berhasil {'diaktifkan' if payload.enabled else 'dinonaktifkan'}.",
    }


# -----------------------------------------------------------------------------
# 2. GROUP & PERMISSION MANAGEMENT ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/groups")
def list_groups(
    ctx: TenantContext = Depends(require_permission("groups.read")),
) -> Dict[str, Any]:
    """Lists all access groups with member counts and active permission count."""
    groups = _rbac_svc.list_groups()
    return {"groups": groups, "total": len(groups)}


@router.get("/groups/{group_id}")
def get_group(
    group_id: str,
    ctx: TenantContext = Depends(require_permission("groups.read")),
) -> Dict[str, Any]:
    """Retrieves group details including full permission mapping and member list."""
    group = _rbac_svc.get_group(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Group '{group_id}' not found.")
    return group


@router.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(
    payload: CreateGroupRequest,
    ctx: TenantContext = Depends(require_permission("groups.create")),
) -> Dict[str, Any]:
    """Creates a new custom group with specified permission matrix."""
    try:
        perms_list = [{"permission_id": p.permission_id, "effect": p.effect} for p in payload.permissions]
        group = _rbac_svc.create_group(
            name=payload.name,
            description=payload.description or "",
            permissions=perms_list,
            is_system=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Group '{payload.name}' already exists.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    _rbac_svc.log_activity_event(
        username=ctx.username,
        event_type="GROUP_CREATED",
        user_id=ctx.user_id,
        details={"group_id": group["group_id"], "name": group["name"]},
        actor_id=ctx.user_id,
    )
    return group


@router.put("/groups/{group_id}")
def update_group(
    group_id: str,
    payload: UpdateGroupRequest,
    ctx: TenantContext = Depends(require_permission("groups.update")),
) -> Dict[str, Any]:
    """Updates group metadata and/or permission matrix."""
    perms_list = None
    if payload.permissions is not None:
        perms_list = [{"permission_id": p.permission_id, "effect": p.effect} for p in payload.permissions]

    try:
        updated = _rbac_svc.update_group(
            group_id=group_id,
            name=payload.name,
            description=payload.description,
            permissions=perms_list,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _rbac_svc.log_activity_event(
        username=ctx.username,
        event_type="GROUP_UPDATED",
        user_id=ctx.user_id,
        details={"group_id": group_id, "name": updated["name"]},
        actor_id=ctx.user_id,
    )
    return updated


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: str,
    ctx: TenantContext = Depends(require_permission("groups.delete")),
) -> Dict[str, Any]:
    """Deletes a custom group. System groups cannot be deleted."""
    try:
        deleted = _rbac_svc.delete_group(group_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Group '{group_id}' not found.")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _rbac_svc.log_activity_event(
        username=ctx.username,
        event_type="GROUP_DELETED",
        user_id=ctx.user_id,
        details={"group_id": group_id},
        actor_id=ctx.user_id,
    )
    return {"group_id": group_id, "deleted": True}


@router.post("/groups/{group_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_group(
    group_id: str,
    payload: DuplicateGroupRequest,
    ctx: TenantContext = Depends(require_permission("groups.create")),
) -> Dict[str, Any]:
    """Duplicates an existing group and its permission rules into a new custom group."""
    try:
        new_group = _rbac_svc.duplicate_group(group_id, payload.new_name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _rbac_svc.log_activity_event(
        username=ctx.username,
        event_type="GROUP_DUPLICATED",
        user_id=ctx.user_id,
        details={"source_group_id": group_id, "new_group_id": new_group["group_id"]},
        actor_id=ctx.user_id,
    )
    return new_group


@router.get("/permissions")
def list_permissions(
    ctx: TenantContext = Depends(require_permission("permissions.read")),
) -> Dict[str, Any]:
    """Lists all 43 canonical system permissions organized by module."""
    perms = _rbac_svc.list_all_permissions()
    return {"permissions": perms, "total": len(perms)}


@router.post("/permissions/preview")
def preview_effective_permissions(
    payload: PermissionsPreviewRequest,
    ctx: TenantContext = Depends(require_permission("permissions.read")),
) -> Dict[str, Any]:
    """Calculates and returns effective permissions preview for a combination of group IDs."""
    effective = _rbac_svc.get_effective_permissions_preview(payload.group_ids)
    return {
        "group_ids": payload.group_ids,
        "effective_permissions": sorted(list(effective)),
        "count": len(effective),
    }


@router.post("/permissions/simulate")
def simulate_permissions(
    payload: UserSimulationRequest,
    ctx: TenantContext = Depends(require_permission("permissions.read")),
) -> Dict[str, Any]:
    """Simulates permission evaluation across Org -> UserGroup -> Site -> Subtab -> Resource -> Action."""
    from core.tenant.permission_simulation import get_permission_simulation_service
    svc = get_permission_simulation_service()
    result = svc.simulate_permission(
        user_id=payload.user_id,
        resource=payload.resource,
        action=payload.action,
        site_id=payload.site_id,
    )
    return {"success": True, "simulation": result}


# -----------------------------------------------------------------------------
# 3. USER ACTIVITY & SESSION MONITORING ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/activity")
def list_activity_events(
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    ctx: TenantContext = Depends(require_permission("user_activity.audit.read")),
) -> Dict[str, Any]:
    """Retrieves paginated audit log of user activities (login, logout, config changes, etc)."""
    events = _rbac_svc.list_activity_events(user_id=user_id, event_type=event_type, limit=limit)
    return {"events": events, "total": len(events)}


@router.get("/sessions")
def list_active_sessions(
    user_id: Optional[str] = None,
    ctx: TenantContext = Depends(require_permission("user_activity.sessions.read")),
) -> Dict[str, Any]:
    """Lists currently active user sessions with masked IDs and online status."""
    sessions = _rbac_svc.list_active_sessions(user_id=user_id)
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    ctx: TenantContext = Depends(require_permission("user_activity.sessions.revoke")),
) -> Dict[str, Any]:
    """Revokes a specific user session immediately."""
    revoked = _rbac_svc.revoke_session(session_id, actor_id=ctx.user_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return {"session_id": session_id, "revoked": True}


@router.delete("/users/{user_id}/sessions")
def revoke_all_user_sessions(
    user_id: str,
    ctx: TenantContext = Depends(require_permission("user_activity.sessions.revoke")),
) -> Dict[str, Any]:
    """Revokes all active sessions for a target user."""
    count = _rbac_svc.revoke_all_user_sessions(user_id, actor_id=ctx.user_id)
    return {"user_id": user_id, "revoked_count": count}
