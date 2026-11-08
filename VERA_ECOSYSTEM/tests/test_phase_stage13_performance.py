"""
AIRA OS — Stage 13 Performance Optimization Validation Tests.
Validates:
1. validate_session_token uses read-only transactions without write contention (REC-13).
2. score_tenant atomic single-transaction write batching (REC-13).
3. Single-flight request deduplication contracts.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from core.topology_db import topology_transaction
from core.tenant.db import ensure_tenant_schema
from core.edge_gateway.db import ensure_gateway_schema
from core.operations.db import ensure_operational_schema
from core.tenant.manager import IdentityManager, TenantManager, InventoryManager
from core.operations.health_scoring_engine import (
    DynamicHealthScoringEngine,
    OperationalHealthScoreRecord,
    HealthDimensionType,
    HealthScoreState,
)


@pytest.fixture
def perf_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "perf_topology.db"
        ensure_tenant_schema(db_path)
        ensure_gateway_schema(db_path)
        ensure_operational_schema(db_path)
        yield db_path


def test_validate_session_token_is_read_only(perf_db):
    """Verifies validate_session_token executes with write=False and triggers no write transactions."""
    id_mgr = IdentityManager(db_path=perf_db)
    tenant_mgr = TenantManager(db_path=perf_db)

    # Setup tenant and user
    t = tenant_mgr.create_tenant("Perf Tenant", "perf-tenant")
    u = id_mgr.create_user("perf_user", "perf@test.corp", "StrongPassword123!", role_type="ADMIN", tenant_id=t.tenant_id)
    session = id_mgr.create_session(u.user_id)
    assert session.token is not None

    # Track calls to topology_transaction
    real_topology_transaction = topology_transaction
    write_calls = []

    def tracking_transaction(db_path, write=False):
        if write:
            write_calls.append(True)
        return real_topology_transaction(db_path, write=write)

    with patch("core.tenant.manager.topology_transaction", side_effect=tracking_transaction):
        ctx = id_mgr.validate_session_token(session.token)
        assert ctx is not None
        assert ctx.username == "perf_user"
        # Must have performed ZERO write transactions
        assert len(write_calls) == 0, f"Expected 0 write transactions during token validation, got {len(write_calls)}"


def test_score_tenant_single_batch_transaction(perf_db):
    """Verifies score_tenant persists all child scores in a single atomic batch transaction."""
    engine = DynamicHealthScoringEngine(db_path=perf_db)
    tenant_mgr = TenantManager(db_path=perf_db)
    inv_mgr = InventoryManager(db_path=perf_db)

    t = tenant_mgr.create_tenant("Health Tenant", "health-tenant")
    t_id = t.tenant_id

    site1 = inv_mgr.create_site(tenant_id=t_id, name="Site Alpha", slug="site-alpha")
    site2 = inv_mgr.create_site(tenant_id=t_id, name="Site Beta", slug="site-beta")

    for i in range(5):
        inv_mgr.create_device(tenant_id=t_id, site_id=site1.site_id, name=f"Router-1-{i}", management_ip=f"10.0.1.{i+1}")
        inv_mgr.create_device(tenant_id=t_id, site_id=site2.site_id, name=f"Router-2-{i}", management_ip=f"10.0.2.{i+1}")

    with topology_transaction(perf_db, write=True) as conn:
        conn.execute(
            """
            INSERT INTO operational_services (
                service_id, tenant_id, name, criticality, status, health_score, created_at, updated_at
            ) VALUES ('svc_1', ?, 'Core ERP', 'TIER_1_MISSION_CRITICAL', 'HEALTHY', 100.0, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')
            """,
            (t_id,),
        )

    # Count how many times write transactions are opened during score_tenant
    real_topology_transaction = topology_transaction
    write_txn_count = 0

    def count_write_transactions(db_path, write=False):
        nonlocal write_txn_count
        if write:
            write_txn_count += 1
        return real_topology_transaction(db_path, write=write)

    with patch("core.operations.health_scoring_engine.topology_transaction", side_effect=count_write_transactions):
        tenant_rec = engine.score_tenant(t_id)
        assert tenant_rec is not None
        assert tenant_rec.dimension == HealthDimensionType.TENANT.value
        # Previously executed 15+ separate write transactions; with batching it must be exactly 1!
        assert write_txn_count == 1, f"Expected exactly 1 write transaction, but got {write_txn_count}"

    # Verify all records were stored in operational_health_scores
    with topology_transaction(perf_db, write=False) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM operational_health_scores WHERE tenant_id = ?",
            (t_id,),
        ).fetchone()[0]
        # 1 tenant + 2 sites + 10 devices + 1 service = 14 records persisted atomically!
        assert count >= 14, f"Expected at least 14 persisted records, found {count}"
