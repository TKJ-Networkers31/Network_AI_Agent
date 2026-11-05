"""
AIRA OS — Networking VIII Phase A Automated Test Suite.
Verifies:
- WP 8.1: Multi-Tenant Core & Quotas
- WP 8.2: Identity, RBAC & Privilege Boundaries
- WP 8.3: Customer Network Inventory & RFC 1918 Overlap Safety
"""

import os
import sqlite3
import tempfile
import time
import pytest

from core.tenant.manager import (
    AuditLogger,
    IdentityManager,
    InventoryManager,
    TenantManager,
)
from core.tenant.models import (
    DeviceType,
    Permission,
    SessionStatus,
    SubscriptionTier,
    TenantConfiguration,
    TenantContext,
    TenantStatus,
    UserRoleType,
)


@pytest.fixture
def temp_db():
    """Provides an isolated temporary database for Phase A tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


def test_tenant_lifecycle_and_quotas(temp_db):
    """Verifies tenant creation, status updates, and quota enforcement."""
    mgr = TenantManager(db_path=temp_db)

    # 1. Create Tenant
    tenant = mgr.create_tenant(
        name="PT Teknologi Nusantara",
        slug="tekno-nusa",
        tier=SubscriptionTier.COMMUNITY.value,
        max_sites=2,
        max_devices=5,
    )
    assert tenant.tenant_id.startswith("tenant_")
    assert tenant.name == "PT Teknologi Nusantara"
    assert tenant.slug == "tekno-nusa"
    assert tenant.status == TenantStatus.ACTIVE.value

    # 2. Retrieve Tenant
    fetched = mgr.get_tenant(tenant.tenant_id)
    assert fetched is not None
    assert fetched.slug == "tekno-nusa"

    by_slug = mgr.get_tenant_by_slug("tekno-nusa")
    assert by_slug is not None
    assert by_slug.tenant_id == tenant.tenant_id

    # 3. Check Quota
    quota = mgr.get_tenant_quota(tenant.tenant_id)
    assert quota.current_sites == 0
    assert quota.max_sites == 2
    assert not quota.is_site_quota_exceeded

    # 4. Update Status to Suspended
    updated = mgr.update_tenant_status(tenant.tenant_id, TenantStatus.SUSPENDED.value)
    assert updated is True
    assert mgr.get_tenant(tenant.tenant_id).status == TenantStatus.SUSPENDED.value

    # 5. Invalid Slug
    with pytest.raises(ValueError):
        mgr.create_tenant("Invalid Slug Org", "INVALID SLUG WITH SPACES")


def test_identity_rbac_and_privilege_boundaries(temp_db):
    """Verifies password security, session lifecycle, and customer privilege boundaries."""
    tenant_mgr = TenantManager(db_path=temp_db)
    tenant = tenant_mgr.create_tenant("Acme Corp", "acme-corp")

    ident_mgr = IdentityManager(db_path=temp_db)

    # 1. Create Internal NOC Operator
    noc_user = ident_mgr.create_user(
        username="noc_lead",
        email="lead@lstechnology.id",
        password="SecureNocPassword123!",
        role_type=UserRoleType.NOC_ADMIN.value,
        is_internal=True,
    )
    assert noc_user.is_internal is True
    assert noc_user.tenant_id is None

    # 2. Create Customer User
    cust_user = ident_mgr.create_user(
        username="acme_admin",
        email="admin@acme.com",
        password="CustomerPassword456!",
        role_type=UserRoleType.CUSTOMER_ADMIN.value,
        is_internal=False,
        tenant_id=tenant.tenant_id,
    )
    assert cust_user.is_internal is False
    assert cust_user.tenant_id == tenant.tenant_id

    # 3. Privilege Boundary Enforcement: Customer CANNOT be assigned NOC role
    with pytest.raises(PermissionError):
        ident_mgr.create_user(
            username="sneaky_user",
            email="sneaky@acme.com",
            password="Password789!",
            role_type=UserRoleType.PLATFORM_SUPER_ADMIN.value,
            is_internal=False,
            tenant_id=tenant.tenant_id,
        )

    # 4. Authentication Verification
    # Wrong password
    assert ident_mgr.authenticate_user("acme_admin", "WrongPass") is None
    # Correct password
    session = ident_mgr.authenticate_user("acme_admin", "CustomerPassword456!")
    assert session is not None
    assert session.username == "acme_admin"
    assert session.status == SessionStatus.ACTIVE.value
    assert session.token.startswith("aira_tok_")

    # 5. Token Validation to TenantContext
    ctx = ident_mgr.validate_session_token(session.token)
    assert ctx is not None
    assert ctx.username == "acme_admin"
    assert ctx.is_internal is False
    assert ctx.tenant_id == tenant.tenant_id
    assert ctx.has_permission(Permission.DEVICE_READ)
    assert ctx.can_access_tenant(tenant.tenant_id) is True
    assert ctx.can_access_tenant("other_tenant") is False

    # 6. Session Revocation
    ident_mgr.revoke_session(session.session_id)
    assert ident_mgr.validate_session_token(session.token) is None


def test_customer_inventory_and_rfc1918_overlap(temp_db):
    """
    CRITICAL MULTI-TENANT TEST:
    Verifies that separate customer organizations (Tenant A and Tenant B) can each
    register identical RFC 1918 private IP addresses (e.g. 192.168.1.1) without collision.
    Also verifies IDOR prevention.
    """
    tenant_mgr = TenantManager(db_path=temp_db)
    tenant_a = tenant_mgr.create_tenant("Customer Alpha", "alpha-corp")
    tenant_b = tenant_mgr.create_tenant("Customer Beta", "beta-corp")

    inv_mgr = InventoryManager(db_path=temp_db)

    # 1. Create Sites for both tenants
    site_a1 = inv_mgr.create_site(tenant_a.tenant_id, "Alpha HQ", "alpha-hq")
    site_b1 = inv_mgr.create_site(tenant_b.tenant_id, "Beta HQ", "beta-hq")

    # 2. Register IDENTICAL IP Address (192.168.1.1) for BOTH Tenants
    dev_a = inv_mgr.create_device(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        name="Alpha-Gateway-Router",
        management_ip="192.168.1.1",
        management_port=8728,
        device_type=DeviceType.ROUTER.value,
        vendor="MikroTik",
    )

    dev_b = inv_mgr.create_device(
        tenant_id=tenant_b.tenant_id,
        site_id=site_b1.site_id,
        name="Beta-Core-Router",
        management_ip="192.168.1.1",
        management_port=8728,
        device_type=DeviceType.ROUTER.value,
        vendor="MikroTik",
    )

    # Both succeeded and received distinct globally unique IDs!
    assert dev_a.device_id != dev_b.device_id
    assert dev_a.tenant_id == tenant_a.tenant_id
    assert dev_b.tenant_id == tenant_b.tenant_id

    # 3. Scoped IP Resolution without collision
    found_a = inv_mgr.get_device_by_ip(tenant_a.tenant_id, site_a1.site_id, "192.168.1.1")
    assert found_a is not None
    assert found_a.device_id == dev_a.device_id
    assert found_a.name == "Alpha-Gateway-Router"

    found_b = inv_mgr.get_device_by_ip(tenant_b.tenant_id, site_b1.site_id, "192.168.1.1")
    assert found_b is not None
    assert found_b.device_id == dev_b.device_id
    assert found_b.name == "Beta-Core-Router"

    # 4. IDOR Prevention: Tenant A cannot retrieve Tenant B's device or site
    assert inv_mgr.get_device(tenant_a.tenant_id, dev_b.device_id) is None
    assert inv_mgr.get_site(tenant_a.tenant_id, site_b1.site_id) is None

    # 5. Collision within the SAME site is prevented
    with pytest.raises(sqlite3.IntegrityError):
        inv_mgr.create_device(
            tenant_id=tenant_a.tenant_id,
            site_id=site_a1.site_id,
            name="Duplicate-Router",
            management_ip="192.168.1.1",  # Same IP in same site!
        )


def test_audit_logger(temp_db):
    """Verifies immutable audit trail recording."""
    audit = AuditLogger(db_path=temp_db)

    entry = audit.log_action(
        username="noc_admin",
        action="TENANT_CREATED",
        resource_type="TENANT",
        resource_id="tenant_12345",
        tenant_id="tenant_12345",
        details={"slug": "test-org"},
    )
    assert entry.audit_id.startswith("aud_")
    assert entry.action == "TENANT_CREATED"

    entries = audit.list_entries(tenant_id="tenant_12345")
    assert len(entries) == 1
    assert entries[0].details_json != ""
