import pytest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from api.main import app
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.models import TenantContext
from api.routers.auth import get_current_user_context

def test_revoke_other_sessions(tmp_path):
    db_path = str(tmp_path / "test_tenant.db")
    tm = TenantManager(db_path)
    im = IdentityManager(db_path)
    
    # Create tenant and user
    t = tm.create_tenant("Tenant One", "tenant-one")
    u = im.create_user(
        username="operator_test",
        email="operator@test.local",
        password="Password123!",
        role_type="ADMIN",
        tenant_id=t.tenant_id,
        is_internal=True
    )
    
    # Create 3 sessions
    sess1 = im.create_session(u.user_id)
    sess2 = im.create_session(u.user_id)
    sess3 = im.create_session(u.user_id)
    
    # Verify all 3 tokens are valid
    assert im.validate_session_token(sess1.token) is not None
    assert im.validate_session_token(sess2.token) is not None
    assert im.validate_session_token(sess3.token) is not None
    
    # Revoke other sessions keeping sess2
    revoked_count = im.revoke_other_sessions(u.user_id, sess2.token)
    assert revoked_count == 2
    
    # Verify sess2 is active, sess1 and sess3 are revoked
    assert im.validate_session_token(sess2.token) is not None
    assert im.validate_session_token(sess1.token) is None
    assert im.validate_session_token(sess3.token) is None

def test_change_password_and_revoke_others_api():
    client = TestClient(app)
    
    # Override auth dependency to simulate authenticated user
    mock_tenant = TenantContext(
        user_id="user_admin",
        username="admin",
        is_internal=True,
        tenant_id="tenant_default",
        roles=["PLATFORM_OWNER"],
        permissions={"settings.write", "admin.view", "workspace.view"},
        session_id="sess_current_123"
    )
    
    app.dependency_overrides[get_current_user_context] = lambda: mock_tenant
    
    try:
        # Test change password with valid new password
        res = client.post(
            "/api/v1/auth/change-password",
            json={
                "new_password": "NewSecretPassword456!"
            }
        )
        assert res.status_code == 200
        assert res.json()["success"] is True
        
        # Test sessions revoke-others
        res = client.post(
            "/api/v1/auth/sessions/revoke-others",
            headers={"Authorization": "Bearer aira_tok_fake_current_session"}
        )
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert "revoked_count" in res.json()
        
    finally:
        app.dependency_overrides.pop(get_current_user_context, None)
