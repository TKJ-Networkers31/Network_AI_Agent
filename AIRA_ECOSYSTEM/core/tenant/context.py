"""
AIRA OS — Tenant Context Resolution, Scoped Execution & Repository Helpers (Networking VIII).

Provides contextvars-based propagation and repository decorators for strict tenant isolation.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import Generator, Optional

from core.tenant.models import Permission, TenantContext

logger = logging.getLogger("aira.tenant.context")

# ContextVar holding the active TenantContext for the current thread/task
_CURRENT_TENANT_CONTEXT: ContextVar[Optional[TenantContext]] = ContextVar(
    "current_tenant_context",
    default=None,
)


def get_current_tenant_context() -> Optional[TenantContext]:
    """Retrieves the TenantContext for the active request or background task."""
    return _CURRENT_TENANT_CONTEXT.get()


@contextmanager
def tenant_scope(context: TenantContext) -> Generator[TenantContext, None, None]:
    """
    Context manager that binds a TenantContext to the current execution frame.
    Automatically resets to previous state upon exit.
    """
    token = _CURRENT_TENANT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_TENANT_CONTEXT.reset(token)


class TenantScopedRepository:
    """
    Base repository mixin enforcing tenant isolation on all queries and mutations.
    Prevents Insecure Direct Object References (IDOR).
    """

    def __init__(self, tenant_id: str) -> None:
        if not tenant_id:
            raise ValueError("TenantScopedRepository requires a valid non-empty tenant_id.")
        self.tenant_id = tenant_id

    def verify_ownership(self, entity_tenant_id: str) -> None:
        """Raises PermissionError if entity tenant_id does not match repository tenant_id."""
        if entity_tenant_id != self.tenant_id:
            raise PermissionError(
                f"Tenant Isolation Violation: Attempted to access entity belonging to '{entity_tenant_id}' from tenant scope '{self.tenant_id}'."
            )
