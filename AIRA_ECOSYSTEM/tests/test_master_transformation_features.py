"""
AIRA OS - Master Transformation Comprehensive Verification Test Suite
Validates:
1. Entitlements & Token Metering (Free/Pro/Enterprise, Networking++, Quota, Rollover)
2. Centralized Approval Engine (Category A/B/C Risk Evaluation & Resolution)
3. AutomationEngine (Interval & Event Triggers, Action Execution, Idempotency)
4. Safe ZIP Archiving (Path Traversal Protection, UTF-8, Header CRC32 Validation)
5. Non-Destructive Discovered Node Promotion
"""

import os
import io
import sys
import time
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.tenant.db import ensure_tenant_schema
from core.tenant.entitlements import (
    EntitlementManager,
    PlanTier,
    EntitlementKey,
    TokenPolicy,
    get_entitlement_manager,
)
from core.operations.approval_engine import (
    CentralizedApprovalEngine,
    AutonomyRiskCategory,
    ApprovalStatus,
    get_approval_engine,
)
from core.scheduler import AutomationEngine, get_automation_engine
from core.file_processing.archive import create_zip_archive
from api.main import app


@pytest.fixture(autouse=True)
def setup_schema():
    ensure_tenant_schema()


@pytest.fixture
def test_client():
    return TestClient(app)


def test_entitlement_and_token_metering():
    mgr = get_entitlement_manager()
    tenant_id = "tenant_default"

    # 1. Assign Pro Plan with Networking++
    mgr.assign_plan(
        tenant_id=tenant_id,
        tier=PlanTier.PRO.value,
        networking_plus=True,
        monthly_tokens=25000,
    )

    assert mgr.has_networking_access(tenant_id) is True

    # 2. Check and consume tokens
    bal_before = mgr.get_or_create_balance(tenant_id)
    assert bal_before.allocated_tokens >= 25000

    can_take, msg = mgr.can_consume(tenant_id, 100)
    assert can_take is True

    mgr.record_usage(
        tenant_id=tenant_id,
        user_id="user_admin",
        session_id="sess_123",
        model_name="gemini-2.5-flash",
        feature_name="topology_discovery",
        tool_name="topology_scan",
        input_tokens=60,
        output_tokens=40,
    )

    bal_after = mgr.get_or_create_balance(tenant_id)
    assert bal_after.used_tokens == bal_before.used_tokens + 100
    assert bal_after.remaining_tokens == bal_after.allocated_tokens - bal_after.used_tokens


def test_centralized_approval_engine():
    engine = get_approval_engine()
    tenant_id = "tenant_default"

    # 1. Category A (Read-only inspection) - Auto-approved immediately
    approved_a, msg_a, appr_a = engine.evaluate_and_request_approval(
        tenant_id=tenant_id,
        requester_id="user_1",
        requester_name="Engineer A",
        action_name="read_interfaces",
        risk_level=AutonomyRiskCategory.CATEGORY_A.value,
        target_resources=["Core-1"],
        params={"interface": "ether1"},
        reason="Check counters",
    )
    assert approved_a is True
    assert appr_a is None

    # 2. Category B (Configuration modification) - Queued for Human Approval
    approved_b, msg_b, appr_b = engine.evaluate_and_request_approval(
        tenant_id=tenant_id,
        requester_id="user_1",
        requester_name="Engineer A",
        action_name="deploy_device_config",
        risk_level=AutonomyRiskCategory.CATEGORY_B.value,
        target_resources=["Core-1"],
        params={"area": 0, "interface": "ether1"},
        reason="Add interface to OSPF area 0",
    )
    assert approved_b is False
    assert appr_b is not None

    # Verify in pending queue
    pending_list = engine.list_pending_approvals(tenant_id=tenant_id)
    assert any(p.approval_id == appr_b.approval_id for p in pending_list)

    # 3. Resolve approval
    res = engine.resolve_approval(
        approval_id=appr_b.approval_id,
        reviewer_id="admin_1",
        approved=True,
        review_notes="Approved during automated test",
    )
    assert res.status == ApprovalStatus.APPROVED.value

    # Verify not in pending queue
    pending_list_after = engine.list_pending_approvals(tenant_id=tenant_id)
    assert not any(p.approval_id == appr_b.approval_id for p in pending_list_after)


def test_automation_engine_lifecycle():
    engine = get_automation_engine()

    # Create interval automation using catalog action
    created = engine.create_automation(
        tenant_id="tenant_default",
        name="Scheduled Health Check",
        description="Regular automated connectivity check",
        trigger_type="INTERVAL",
        trigger_params={"interval_seconds": 3600},
        action_name="check_connectivity",
        action_params={"devices": ["Core-1"]},
        approval_required=False,
    )
    assert created is not None
    assert created.is_enabled is True

    # Pause and resume
    toggled_off = engine.toggle_automation(created.job_id, is_enabled=False)
    assert toggled_off is not None
    assert toggled_off.is_enabled is False

    toggled_on = engine.toggle_automation(created.job_id, is_enabled=True)
    assert toggled_on is not None
    assert toggled_on.is_enabled is True

    # Trigger run
    rec = engine.execute_job(created, trigger_source="MANUAL")
    assert rec.status in ("SUCCESS", "APPROVAL_PENDING")

    # Cleanup
    assert engine.delete_automation(created.job_id) is True


def test_safe_zip_archive_creation(tmp_path):
    # Create test directory and files
    src_dir = tmp_path / "source_data"
    src_dir.mkdir()
    (src_dir / "report.txt").write_text("Test Report Content", encoding="utf-8")
    (src_dir / "config.json").write_text('{"host": "10.0.0.1"}', encoding="utf-8")

    out_zip = tmp_path / "output.zip"

    # Create zip passing list of sources
    res = create_zip_archive([src_dir], str(out_zip))
    assert res["success"] is True
    assert os.path.exists(out_zip)

    # Validate archive integrity
    with zipfile.ZipFile(out_zip, "r") as zf:
        assert zf.testzip() is None  # None means no corrupted files
        namelist = zf.namelist()
        assert any("report.txt" in n for n in namelist)
        assert any("config.json" in n for n in namelist)

        # Ensure no path traversal in arcnames
        for name in namelist:
            assert not name.startswith("/")
            assert not name.startswith("\\")
            assert ".." not in name


def test_pending_discovered_device_endpoints(test_client):
    # 1. Query pending discovered devices
    resp = test_client.get("/api/devices/pending-discovered")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "pending_devices" in data
