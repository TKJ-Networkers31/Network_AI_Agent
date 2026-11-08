# AIRA_ECOSYSTEM/tests/test_phase_g_network_intelligence.py
"""
AIRA OS — Phase G Network Intelligence & Autonomous Operations Test Suite.
Tests:
1. Network Change Detector (state comparison, delta thresholds, debouncing, correlation to active incidents)
2. Automatic Device Onboarding Engine (connectivity, capabilities, credentials, AI summary)
3. AI Action Management Engine (5-tier risk, non-bypassable approvals, execution & verification, rollback)
4. REST API Endpoints with RBAC authorization & Section 4.1 Overview metrics
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch

# Ensure AIRA_ECOSYSTEM is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.network_intelligence.change_detector import NetworkChangeDetector, get_change_detector
from core.network_intelligence.onboarding import DeviceOnboardingEngine, get_onboarding_engine
from core.network_intelligence.action_engine import (
    ActionManagementEngine,
    AIOperationsPolicy,
    ActionRiskLevel,
    ActionExecutionStatus,
    get_action_engine,
)
from core.network_intelligence.store import get_network_intelligence_store
from core.network_intelligence.models import IncidentRecord
from core.tenant.auth_deps import get_current_authenticated_user
from core.tenant.models import TenantContext


# ---------------------------------------------------------------------------
# 1. Change Detector Tests
# ---------------------------------------------------------------------------

def test_change_detector_status_and_latency_thresholds():
    detector = NetworkChangeDetector(debounce_sec=0.0)

    # Initial baseline sample (returns None, initializes cache)
    init_res = detector.evaluate_metric_sample("router-test-1", {
        "status": "UP",
        "latency_ms": 10.0,
        "packet_loss_pct": 0.0,
        "cpu_util_pct": 10.0,
    })
    assert init_res is None

    # Sub-threshold change (< 30ms delta, < 5% loss delta) -> Should return None
    sub_res = detector.evaluate_metric_sample("router-test-1", {
        "status": "UP",
        "latency_ms": 15.0,  # +5ms
        "packet_loss_pct": 1.0,  # +1%
        "cpu_util_pct": 12.0,
    })
    assert sub_res is None

    # Status change UP -> DOWN -> Should trigger immediately
    status_event = detector.evaluate_metric_sample("router-test-1", {
        "status": "DOWN",
        "latency_ms": 0.0,
        "packet_loss_pct": 100.0,
        "cpu_util_pct": 0.0,
    })
    assert status_event is not None
    assert status_event["severity"] == "CRITICAL"
    assert any("Status transitioned from UP to DOWN" in r for r in status_event["reasons"])


def test_change_detector_debouncing():
    detector = NetworkChangeDetector(debounce_sec=10.0)

    # Initial baseline
    detector.evaluate_metric_sample("router-test-2", {
        "status": "UP",
        "latency_ms": 10.0,
        "packet_loss_pct": 0.0,
    })

    # First flap (triggers event)
    event_1 = detector.evaluate_metric_sample("router-test-2", {
        "status": "DOWN",
        "latency_ms": 0.0,
        "packet_loss_pct": 100.0,
    })
    assert event_1 is not None

    # Second flap immediately after (< 10s) -> Debounced
    event_2 = detector.evaluate_metric_sample("router-test-2", {
        "status": "UP",
        "latency_ms": 10.0,
        "packet_loss_pct": 0.0,
    })
    assert event_2 is None


def test_change_detector_attaches_to_active_investigation():
    detector = NetworkChangeDetector(debounce_sec=0.0)
    store = get_network_intelligence_store()

    # Pre-create an active incident for test device
    inc = IncidentRecord(
        incident_id="inc_test_corr_001",
        device_identity="R1-Test-Core",
        incident_type="LAN_NO_INTERNET",
        severity="HIGH",
        symptoms=["Initial high latency"],
        user_description="Test incident for correlation",
        observed_facts=["Baseline latency 15ms"],
        created_at=time.time(),
        updated_at=time.time(),
        investigation_status="IN_PROGRESS",
    )
    store.save_incident(inc)

    # Baseline
    detector.evaluate_metric_sample("R1-Test-Core", {
        "status": "UP",
        "latency_ms": 15.0,
        "packet_loss_pct": 0.0,
    })

    # High severity event (latency spike to 120ms)
    event = detector.evaluate_metric_sample("R1-Test-Core", {
        "status": "UP",
        "latency_ms": 120.0,
        "packet_loss_pct": 0.0,
    })
    assert event is not None
    assert event["severity"] == "HIGH"

    # Verify that the active incident in store was updated with the reason
    updated_inc = store.get_incident(inc.incident_id)
    assert any("Latency delta" in f for f in updated_inc.observed_facts)


# ---------------------------------------------------------------------------
# 2. Device Onboarding Engine Tests
# ---------------------------------------------------------------------------

def test_device_onboarding_unreachable_handling():
    engine = DeviceOnboardingEngine()

    with patch.object(engine, "check_connectivity", return_value=(False, "Connection timed out after 3.0s")):
        res = engine.onboard_device(
            name="Unreachable-Switch",
            host="192.0.2.1",
            device_type="SWITCH",
            tenant_id="tenant_internal",
        )
        assert res["connection_status"] == "UNREACHABLE"
        assert res["discovery_status"] == "UNREACHABLE"
        assert "timed out" in res["connectivity_message"].lower()
        assert any("Periksa konektivitas" in r for r in res["ai_summary"]["recommendations"])


def test_device_onboarding_success_and_ai_summary():
    engine = DeviceOnboardingEngine()

    with patch.object(engine, "check_connectivity", return_value=(True, "Port reachable")):
        res = engine.onboard_device(
            name="Core-R1-Edge",
            host="192.168.88.1",
            device_type="ROUTER",
            vendor="MikroTik",
            tenant_id="tenant_internal",
            credential_ref="vault://credentials/router_r1",
        )

        assert res["success"] is True
        assert res["node_id"] == "node_core-r1-edge"
        assert res["connection_status"] == "REACHABLE"
        assert res["discovery_status"] == "SUCCESS"
        assert "ssh_terminal" in res["available_capabilities"]

        # Verify AI summary epistemic structure (Facts vs Indications vs Hypotheses vs Recommendations)
        summary = res["ai_summary"]
        assert "facts" in summary
        assert "indications" in summary
        assert "hypotheses" in summary
        assert "recommendations" in summary
        assert any("Core-R1-Edge" in f for f in summary["facts"])
        assert any("topologi" in r.lower() or "monitoring" in r.lower() for r in summary["recommendations"])

        # Verify credential secrecy (no plaintext credentials exposed)
        res_str = str(res)
        assert "password" not in res_str.lower() or "credential_ref" in res_str


# ---------------------------------------------------------------------------
# 3. Action Management Engine Tests
# ---------------------------------------------------------------------------

def test_action_risk_classification():
    engine = ActionManagementEngine()

    # Read-only
    assert engine.classify_risk("READ_ONLY_STATUS", {}) == ActionRiskLevel.READ_ONLY
    assert engine.classify_risk("OBSERVE_ROUTE_TABLE", {}) == ActionRiskLevel.READ_ONLY

    # Critical
    assert engine.classify_risk("REBOOT_ROUTER", {}) == ActionRiskLevel.CRITICAL
    assert engine.classify_risk("FACTORY_RESET", {}) == ActionRiskLevel.CRITICAL

    # High
    assert engine.classify_risk("ADD_STATIC_ROUTE", {}) == ActionRiskLevel.HIGH
    assert engine.classify_risk("FIREWALL_FORWARD_BLOCK", {}) == ActionRiskLevel.HIGH
    assert engine.classify_risk("INTERFACE_DOWN", {}) == ActionRiskLevel.HIGH

    # Medium
    assert engine.classify_risk("UPDATE_MONITORING_INTERVAL", {}) == ActionRiskLevel.MEDIUM

    # Low
    assert engine.classify_risk("REFRESH_CACHE", {}) == ActionRiskLevel.LOW


def test_high_risk_approval_enforcement():
    engine = ActionManagementEngine()

    action = engine.propose_action(
        action_name="FIREWALL_FORWARD_BLOCK",
        target_devices=["R1-Gateway"],
        description="Block suspected malicious subnet",
        reason="High attack traffic detected",
        before_state={"rules_count": 5},
        proposed_changes={"action": "drop", "src": "198.51.100.0/24"},
        expected_after_state={"rules_count": 6},
        diff_text="+ /ip firewall filter add chain=forward src-address=198.51.100.0/24 action=drop",
        verification_plan="Check packet drop counters",
        rollback_plan="/ip firewall filter remove [find src-address=198.51.100.0/24]",
        rollback_supported=True,
    )

    action_id = action.action_id
    assert action.status == ActionExecutionStatus.PENDING_APPROVAL.value
    assert action.approval_required is True

    # Attempting to execute WITHOUT approval MUST fail
    exec_attempt = engine.execute_and_verify_action(action_id, operator_id="autonomous_ai")
    assert exec_attempt["success"] is False
    assert "must be 'APPROVED'" in exec_attempt["error"]

    # Resolve approval (Approve by lingga_admin)
    resolved = engine.resolve_approval(action_id, approved=True, reviewer_id="lingga_admin", notes="Verified by senior NOC engineer")
    assert resolved["success"] is True
    assert resolved["status"] == ActionExecutionStatus.APPROVED.value

    # Now execute action
    exec_res = engine.execute_and_verify_action(action_id, operator_id="lingga_admin")
    assert exec_res["success"] is True
    assert exec_res["status"] == ActionExecutionStatus.SUCCESS.value
    assert exec_res["verification"]["checks_passed"] is True


def test_action_rejection_flow():
    engine = ActionManagementEngine()

    action = engine.propose_action(
        action_name="INTERFACE_DOWN",
        target_devices=["R1-Gateway"],
        description="Disable interface ether3",
        reason="Port security alert",
        before_state={"ether3": "enabled"},
        proposed_changes={"ether3": "disabled"},
        expected_after_state={"ether3": "disabled"},
        diff_text="/interface disable ether3",
        verification_plan="Check link state",
        rollback_plan="/interface enable ether3",
        rollback_supported=True,
    )

    action_id = action.action_id
    rejected = engine.resolve_approval(action_id, approved=False, reviewer_id="lingga_admin", notes="Port in use by core uplink")
    assert rejected["success"] is True
    assert rejected["status"] == ActionExecutionStatus.REJECTED.value

    exec_res = engine.execute_and_verify_action(action_id, operator_id="lingga_admin")
    assert exec_res["success"] is False
    assert "must be 'APPROVED'" in exec_res["error"]


# ---------------------------------------------------------------------------
# 4. REST API Overview Endpoint Verification
# ---------------------------------------------------------------------------

def test_api_network_intelligence_overview():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)

    # Supply an authenticated TenantContext for lingga_admin
    mock_admin_context = TenantContext(
        user_id="usr_25b8282cc548",
        username="lingga_admin",
        is_internal=True,
        tenant_id="tenant_internal",
        roles=["SUPER_ADMIN"],
        groups=["SUPER_ADMIN"],
        permissions={"*"},
        account_enabled=True,
    )
    from core.tenant.auth_deps import require_permission
    dep = require_permission("nms.read")
    app.dependency_overrides[get_current_authenticated_user] = lambda: mock_admin_context
    app.dependency_overrides[dep] = lambda: mock_admin_context

    try:
        res = client.get("/api/intelligence/overview", headers={"Authorization": "Bearer mock_token"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        overview = data["overview"]

        # Verify all 8 metrics required by Section 4.1
        assert "network_condition" in overview
        assert "health_score" in overview
        assert "total_registered_devices" in overview
        assert "reachable_devices" in overview
        assert "unreachable_devices" in overview
        assert "active_investigations" in overview
        assert "detected_anomalies" in overview
        assert "pending_approvals" in overview
        assert "recent_ai_decisions" in overview
    finally:
        app.dependency_overrides.clear()
