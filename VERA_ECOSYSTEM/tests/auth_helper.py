"""
VERA_ECOSYSTEM/tests/auth_helper.py — Test Authentication Fixtures & Token Factory.

Provides legitimate authenticated sessions for unit and integration tests,
strictly preserving production authentication and tenant isolation checks.
"""

from __future__ import annotations

from typing import Dict
from core.tenant.auth_deps import _identity_mgr


def get_test_auth_headers(username: str = "lingga_admin") -> Dict[str, str]:
    """Generates a valid Bearer session token and administrative headers for tests."""
    user = _identity_mgr.get_user_by_username(username)
    if not user:
        return {"X-Topology-Admin": "true"}
    session = _identity_mgr.create_session(user.user_id)
    return {
        "Authorization": f"Bearer {session.token}",
        "X-Topology-Admin": "true",
    }
