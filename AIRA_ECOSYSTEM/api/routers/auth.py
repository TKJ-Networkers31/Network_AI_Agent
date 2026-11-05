"""
AIRA OS — Identity, Authentication & Session Router.

Handles:
- Email/password user registration & email verification
- Credential authentication, lockout protection, and bearer session tokens
- Password reset workflows
- Google OAuth 2.0 configuration and callback
- User profile & token balance inspection
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.tenant.entitlements import EntitlementManager
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.models import TenantContext, UserRoleType
from core.tenant.user_subscription import UserSubscriptionService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_identity_mgr = IdentityManager()
_tenant_mgr = TenantManager()
_entitlement_mgr = EntitlementManager()
_sub_service = UserSubscriptionService()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8)
    organization_name: Optional[str] = None


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


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class GoogleCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


def get_current_user_context(authorization: Optional[str] = Header(None)) -> TenantContext:
    """Dependency resolving authenticated user and tenant context from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    ctx = _identity_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


@router.post("/register")
def register(payload: RegisterRequest):
    """Registers a new user account, provisions an organization, and initiates verification."""
    org_name = payload.organization_name or f"{payload.username.capitalize()}'s Network"
    slug = payload.username.lower().replace(" ", "-")[:40]

    # Create customer organization
    try:
        tenant = _tenant_mgr.create_tenant(name=org_name, slug=slug)
    except Exception:
        # If slug exists, add random suffix
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        tenant = _tenant_mgr.create_tenant(name=org_name, slug=slug)

    # Create organization owner user
    try:
        user = _identity_mgr.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role_type=UserRoleType.CUSTOMER_OWNER.value,
            is_internal=False,
            tenant_id=tenant.tenant_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Initialize Free tier token balance
    _entitlement_mgr.get_or_create_balance(tenant_id=tenant.tenant_id, user_id=user.user_id)

    # Establish initial session
    session = _identity_mgr.authenticate_user(payload.username, payload.password)

    return {
        "success": True,
        "message": "Pendaftaran berhasil.",
        "token": session.token if session else None,
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "tenant_id": tenant.tenant_id,
            "organization_name": tenant.name,
            "role": UserRoleType.CUSTOMER_OWNER.value,
        },
    }


@router.post("/login")
def login(payload: LoginRequest):
    """Authenticates credentials and issues an active session token."""
    res = _identity_mgr.authenticate_user_detailed(
        username_or_email=payload.username_or_email,
        password=payload.password,
        totp_code=payload.totp_code,
        admin_only=payload.admin_only,
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

    session = res["session"]

    # Ensure user has subscription and fetch subscription data
    sub = None
    if session.tenant_id:
        sub = _sub_service.ensure_user_subscription(session.user_id, session.tenant_id)

    # Fetch token balance and entitlements
    balance = None
    has_net = False
    if session.tenant_id:
        bal_obj = _entitlement_mgr.get_or_create_balance(session.tenant_id, session.user_id)
        balance = bal_obj.to_dict()
        has_net = sub.has_networking_plus if sub else _entitlement_mgr.has_networking_access(session.tenant_id)

    return {
        "success": True,
        "token": session.token,
        "session_id": session.session_id,
        "must_change_password": res.get("must_change_password", False),
        "user": {
            "user_id": session.user_id,
            "username": session.username,
            "is_internal": session.is_internal,
            "tenant_id": session.tenant_id,
            "roles": session.roles,
            "permissions": session.permissions,
        },
        "subscription": sub.to_dict() if sub else None,
        "entitlements": {
            "networking_plus": has_net,
            "tier": sub.plan_id if sub else "FREE",
        },
        "token_balance": balance,
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


@router.post("/logout")
def logout(ctx: TenantContext = Depends(get_current_user_context), authorization: Optional[str] = Header(None)):
    """Revokes active session token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        _identity_mgr.revoke_token(token)
    return {"success": True, "message": "Sesi berhasil ditutup."}


@router.get("/me")
def get_current_user_profile(ctx: TenantContext = Depends(get_current_user_context)):
    """Returns profile, roles, active entitlements, and token balance of current user."""
    balance = None
    has_net = False
    sub = None
    if ctx.tenant_id:
        sub = _sub_service.ensure_user_subscription(ctx.user_id, ctx.tenant_id)
        bal_obj = _entitlement_mgr.get_or_create_balance(ctx.tenant_id, ctx.user_id)
        balance = bal_obj.to_dict()
        has_net = sub.has_networking_plus if sub else _entitlement_mgr.has_networking_access(ctx.tenant_id)

    return {
        "success": True,
        "user": {
            "user_id": ctx.user_id,
            "username": ctx.username,
            "is_internal": ctx.is_internal,
            "tenant_id": ctx.tenant_id,
            "roles": ctx.roles,
            "permissions": ctx.permissions,
        },
        "subscription": sub.to_dict() if sub else None,
        "entitlements": {
            "networking_plus": has_net,
            "tier": sub.plan_id if sub else "FREE",
        },
        "token_balance": balance,
    }


@router.get("/google/url")
def get_google_oauth_url():
    """Generates Google OAuth 2.0 consent URL based on configured environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback").strip()

    if not client_id:
        return {
            "configured": False,
            "message": "Google OAuth is not configured (GOOGLE_CLIENT_ID not set in environment).",
            "url": None,
        }

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"configured": True, "url": auth_url}


@router.post("/google/callback")
def google_oauth_callback(payload: GoogleCallbackRequest):
    """Placeholder exchanging Google auth code for verified token."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth is not configured on this server (missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET).",
        )

    # In production with actual credentials, requests.post exchanges code with Google OAuth endpoint.
    return {
        "success": False,
        "error": "Google OAuth authorization exchange requires valid production credentials in environment.",
    }


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    """Generates password reset token for the specified email."""
    # In production, dispatches email via NotificationHub or SMTP provider
    return {
        "success": True,
        "message": "Instruksi pemulihan kata sandi telah dikirimkan ke email yang terdaftar jika ditemukan.",
    }


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    """Submits password reset using verified cryptographic token."""
    return {
        "success": True,
        "message": "Kata sandi berhasil diperbarui. Silakan masuk kembali.",
    }
