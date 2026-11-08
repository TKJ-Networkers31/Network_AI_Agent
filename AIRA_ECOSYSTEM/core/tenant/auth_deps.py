"""
AIRA OS — Centralized Authentication & Permission Dependencies (Phase F.1).
Guarantees mandatory authentication across all internal endpoints and group-based RBAC checks.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, status

from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext

_identity_mgr = IdentityManager()


def get_current_authenticated_user(
    authorization: Optional[str] = Header(None),
) -> TenantContext:
    """
    Enforces mandatory authentication.
    Anonymous access without a valid Bearer session token is rejected with HTTP 401 Unauthorized.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Autentikasi wajib. Akses tanpa login ditolak.",
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


@lru_cache(maxsize=128)
def require_permission(permission_id: str) -> Callable[[TenantContext], TenantContext]:
    """
    Factory dependency checking that the authenticated user's effective permissions
    include the specified permission (with explicit DENY taking precedence) and
    verifies NETWORK_PLUS entitlement on networking modules.
    """
    def _dependency(ctx: TenantContext = Depends(get_current_authenticated_user)) -> TenantContext:
        networking_prefixes = (
            "inventory.", "devices.", "topology.", "nms.", "playbooks.",
            "gateways.", "operations.", "intelligence.", "decisions.", "automation.",
        )
        if any(permission_id.startswith(p) for p in networking_prefixes):
            from core.tenant.entitlement_service import get_entitlement_service
            try:
                import api.routers.auth as _auth_mod
                target_db = getattr(getattr(_auth_mod, "_identity_mgr", None), "db_path", None)
            except Exception:
                target_db = None

            ent_svc = get_entitlement_service(db_path=target_db)
            if not ent_svc.has_entitlement(ctx, "NETWORK_PLUS"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ENTITLEMENT_REQUIRED",
                        "code": "ENTITLEMENT_REQUIRED",
                        "required_entitlement": "NETWORK_PLUS",
                        "message": "Fitur jaringan memerlukan paket langganan dengan entitlement Network++. Silakan upgrade akun Anda.",
                    },
                )

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


def require_superadmin(ctx: TenantContext = Depends(get_current_authenticated_user)) -> TenantContext:
    """Enforces that the caller is a SUPERADMIN (lingga_admin or SUPER_ADMIN group/role)."""
    uname = (ctx.username or "").lower()
    groups = {str(g).upper() for g in (ctx.groups or [])} | {str(g).lower() for g in (ctx.groups or [])}
    roles = {str(r).upper() for r in (ctx.roles or [])}

    is_super = (
        uname in {"lingga_admin", "admin"} or
        bool(groups & {"SUPER_ADMIN", "GRP_SUPER_ADMIN", "grp_super_admin", "super_admin"}) or
        bool(roles & {"PLATFORM_OWNER", "SUPERADMIN", "PLATFORM_SUPER_ADMIN"})
    )
    if not is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak: Menu Models hanya dapat diakses oleh Super Admin.",
        )
    return ctx

