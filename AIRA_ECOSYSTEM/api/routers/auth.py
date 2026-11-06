"""
AIRA OS — Identity, Authentication & Session Router (Phase F.1).

Username and Password only. Mandatory authentication across all endpoints.
No Guest Mode, no Google OAuth, no email verification dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core.security.rate_limiter import auth_rate_limiter
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.entitlements import EntitlementManager
from core.tenant.token_quota_service import TokenQuotaService
from core.tenant.user_subscription import UserSubscriptionService
from core.tenant.models import TenantContext
from core.tenant.rbac_service import get_rbac_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

from core.tenant.auth_deps import _identity_mgr
_tenant_mgr = TenantManager()
_entitlement_mgr = EntitlementManager()
_sub_service = UserSubscriptionService()
_quota_service = TokenQuotaService()


class LoginRequest(BaseModel):
    username_or_email: str
    password: str
    totp_code: Optional[str] = None
    admin_only: bool = False


class ChangePasswordMandatoryRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class MfaVerifyRequest(BaseModel):
    secret: str
    code: str


def get_current_user_context(authorization: Optional[str] = Header(None)) -> TenantContext:
    """Dependency resolving authenticated user and tenant context from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi wajib. Akses tanpa login ditolak.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    ctx = _identity_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi tidak valid atau telah kedaluwarsa.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not ctx.account_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini telah dinonaktifkan oleh administrator.",
        )
    return ctx


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    """Authenticates credentials using username and password, issuing an active session token."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    # Rate limiting protection (OWASP ASVS 5.0)
    allowed, retry_after = auth_rate_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Terlalu banyak percobaan masuk dari IP Anda. Coba lagi dalam {retry_after} detik.",
            headers={"Retry-After": str(retry_after)},
        )

    res = _identity_mgr.authenticate_user_detailed(
        username_or_email=payload.username_or_email,
        password=payload.password,
        totp_code=payload.totp_code,
        admin_only=payload.admin_only,
        ip_address=client_ip,
    )

    if res.get("mfa_required"):
        return {
            "success": False,
            "mfa_required": True,
            "username": res.get("username"),
            "message": "Kode verifikasi 2FA (TOTP) diperlukan.",
        }

    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=res.get("error", "Username atau password tidak sesuai."),
        )

    # Reset rate limit counter on success
    auth_rate_limiter.reset(client_ip)

    session = res["session"]
    rbac_svc = get_rbac_service()
    user_obj = _identity_mgr.get_user_by_id(session.user_id)
    groups = [g["name"] for g in rbac_svc.get_user_groups(session.user_id)]
    effective_perms = sorted(list(rbac_svc.get_effective_permissions(session.user_id)))

    return {
        "success": True,
        "token": session.token,
        "session_id": session.session_id,
        "must_change_password": res.get("must_change_password", False),
        "user": {
            "user_id": session.user_id,
            "username": session.username,
            "display_name": user_obj.display_name if user_obj else session.username,
            "account_enabled": user_obj.account_enabled if user_obj else True,
            "is_internal": session.is_internal,
            "tenant_id": session.tenant_id,
            "roles": session.roles,
            "groups": groups,
            "permissions": effective_perms,
        },
    }


@router.post("/heartbeat")
def heartbeat(ctx: TenantContext = Depends(get_current_user_context)):
    """
    Heartbeat ping from client to maintain online status and update last activity.
    """
    rbac_svc = get_rbac_service()
    if ctx.session_id:
        rbac_svc.record_heartbeat(ctx.session_id, ctx.user_id)
    return {
        "success": True,
        "status": "ONLINE",
        "user_id": ctx.user_id,
        "username": ctx.username,
    }


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    """Revokes active session token and records LOGOUT activity event."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        ctx = _identity_mgr.validate_session_token(token)
        _identity_mgr.revoke_token(token)
        if ctx:
            rbac_svc = get_rbac_service()
            rbac_svc.log_activity_event(
                username=ctx.username,
                event_type="LOGOUT",
                user_id=ctx.user_id,
                details={"session_id": ctx.session_id},
            )
    return {"success": True, "message": "Sesi berhasil ditutup."}


@router.get("/me")
def get_current_user_profile(ctx: TenantContext = Depends(get_current_user_context)):
    """Returns profile, groups, and effective permissions of current user."""
    rbac_svc = get_rbac_service()
    user_obj = _identity_mgr.get_user_by_id(ctx.user_id)
    groups = [g["name"] for g in rbac_svc.get_user_groups(ctx.user_id)]
    effective_perms = sorted(list(rbac_svc.get_effective_permissions(ctx.user_id)))

    return {
        "success": True,
        "user": {
            "user_id": ctx.user_id,
            "username": ctx.username,
            "display_name": user_obj.display_name if user_obj else ctx.username,
            "account_enabled": user_obj.account_enabled if user_obj else True,
            "is_internal": ctx.is_internal,
            "tenant_id": ctx.tenant_id,
            "roles": ctx.roles,
            "groups": groups,
            "permissions": effective_perms,
        },
    }


@router.post("/change-password-mandatory")
def change_password_mandatory(payload: ChangePasswordMandatoryRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Mandatory password change requirement for first login (e.g. lingga_admin bootstrap)."""
    try:
        _identity_mgr.change_user_password(ctx.user_id, payload.new_password, reset_must_change=True)
        return {"success": True, "message": "Kata sandi berhasil diubah. Akun Anda kini aktif sepenuhnya."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/mfa/setup")
def setup_mfa(ctx: TenantContext = Depends(get_current_user_context)):
    """Generates standard TOTP secret and QR URI for user."""
    try:
        mfa_data = _identity_mgr.setup_mfa(ctx.user_id)
        return {"success": True, "mfa": mfa_data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/mfa/verify")
def verify_mfa(payload: MfaVerifyRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Verifies authenticator code and activates two-factor authentication."""
    try:
        _identity_mgr.verify_and_enable_mfa(ctx.user_id, payload.secret, payload.code)
        return {"success": True, "message": "Autentikasi dua faktor (MFA/TOTP) berhasil diaktifkan."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/mfa/disable")
def disable_mfa(ctx: TenantContext = Depends(get_current_user_context)):
    """Deactivates two-factor authentication."""
    try:
        _identity_mgr.disable_mfa(ctx.user_id)
        return {"success": True, "message": "Autentikasi dua faktor dinonaktifkan."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
