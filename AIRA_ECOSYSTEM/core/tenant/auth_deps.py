"""
AIRA OS — Centralized Authentication & Permission Dependencies (Phase F.1).
Guarantees mandatory authentication across all internal endpoints and group-based RBAC checks.
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, status

from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext

_identity_mgr = IdentityManager()


def get_current_authenticated_user(
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None, alias="X-Guest-ID"),
) -> TenantContext:
    """
    Enforces mandatory authentication or valid guest identification.
    Anonymous access without login or guest token is rejected with HTTP 401 Unauthorized.
    """
    if not authorization or not authorization.startswith("Bearer "):
        if x_guest_id and str(x_guest_id).strip().startswith("gst_"):
            return TenantContext(
                user_id=str(x_guest_id).strip(),
                username=f"guest_{str(x_guest_id).strip()[:8]}",
                tenant_id="tenant_guest",
                roles=["GUEST"],
                groups=["READ_ONLY"],
                is_internal=False,
                account_enabled=True,
                permissions={"workspace.view", "ai_assistant.view", "personalization.manage"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi wajib. Akses tanpa login ditolak.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        import api.routers.auth as _auth_mod
        mgr = getattr(_auth_mod, "_identity_mgr", _identity_mgr)
    except Exception:
        mgr = _identity_mgr
    ctx = mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi tidak valid, kedaluwarsa, atau akun dinonaktifkan.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not ctx.account_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini telah dinonaktifkan oleh administrator.",
        )

    return ctx


def require_permission(permission_id: str) -> Callable[[TenantContext], TenantContext]:
    """
    Factory dependency checking that the authenticated user's effective permissions
    include the specified permission (with explicit DENY taking precedence).
    """
    def _dependency(ctx: TenantContext = Depends(get_current_authenticated_user)) -> TenantContext:
        if not ctx.has_permission(permission_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"Akses ditolak: Akun Anda tidak memiliki izin '{permission_id}'.",
                    "required_permission": permission_id,
                },
            )
        return ctx

    return _dependency


def require_platform_admin(ctx: TenantContext = Depends(get_current_authenticated_user)) -> TenantContext:
    """Enforces that the caller holds administrative permissions or SUPER_ADMIN group."""
    admin_groups = {"SUPER_ADMIN", "ADMIN"}
    admin_roles = {"PLATFORM_OWNER", "SUPERADMIN", "PLATFORM_SUPER_ADMIN", "NOC_ADMIN"}

    has_admin_group = any(g in admin_groups for g in ctx.groups)
    has_admin_role = any(r in admin_roles for r in ctx.roles)
    has_admin_perm = ctx.has_permission("users.read") or ctx.has_permission("users.create")

    if not (ctx.is_internal or has_admin_group or has_admin_role or has_admin_perm):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administration access required. Akses ditolak: AIRA Control Plane memerlukan kredensial administrator.",
        )
    return ctx
