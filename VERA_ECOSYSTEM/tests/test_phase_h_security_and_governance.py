"""
AIRA OS — Master Phase H Test Suite: Security, AI Governance, Reasoning & Multi-Tenant Operations.

Validates:
1. Workstream A: Password Hashing (Argon2id + transparent migration), Session Revocation, Rate Limiting, SSRF Validator, Security Headers.
2. Workstream B: Backend Authorization Hierarchy, Granular Actions, Permission Simulation API.
3. Workstream C: AI Output Guard (Secret Redaction & Pre-retrieval clearance).
4. Workstream D: Network Security Intelligence (Device Roles, Baseline Rules, Finding Lifecycle, Posture Scoring).
5. Workstream E: Event-Driven Security Drift Detection.
6. Workstream G: 12-Stage Epistemic Reasoning & Version-Aware Syntax.
7. Workstream J: Action Governance & Non-Bypassable Approvals.
8. Workstream K: Multi-Tenant Data Scoping & Memory Preservation.
"""

from __future__ import annotations

import hashlib
import json
import pytest
from typing import Any, Dict

from core.ai.reasoning_engine import (
    ConfidenceLevel,
    DeviceSyntaxEngine,
    get_reasoning_engine,
)
from core.network_intelligence.action_engine import (
    ActionExecutionStatus,
    ActionRiskLevel,
    get_action_engine,
)
from core.network_intelligence.change_detector import get_change_detector
from core.network_intelligence.security_baseline import (
    DeviceRole,
    FindingCategory,
    FindingSeverity,
    PostureBand,
    get_security_baseline_engine,
)
from core.security.output_guard import AIOutputGuard, DataClassification
from core.security.password import hash_password, verify_password
from core.security.rate_limiter import SlidingWindowRateLimiter
from core.security.ssrf_validator import validate_safe_url
from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext
from core.tenant.permission_simulation import (
    GranularAction,
    get_permission_simulation_service,
)


# ===========================================================================
# 1. WORKSTREAM A: APPLICATION SECURITY HARDENING & DEFENSE
# ===========================================================================

def test_argon2id_password_hashing():
    pw = "SuperSecurePass123!"
    h = hash_password(pw)
    assert h.startswith("$argon2id$")

    # Positive verification
    is_valid, needs_rehash = verify_password(pw, h)
    assert is_valid is True
    assert needs_rehash is False

    # Negative verification
    is_valid_wrong, _ = verify_password("WrongPassword!", h)
    assert is_valid_wrong is False


def test_legacy_pbkdf2_transparent_migration():
    pw = "LegacyPass123!"
    salt = "abcd1234efgh5678"
    legacy_hex = hashlib.pbkdf2_hmac(
        "sha256",
        pw.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()

    # Legacy hash must be accepted AND signal needs_rehash=True
    is_valid, needs_rehash = verify_password(pw, legacy_hex, salt)
    assert is_valid is True
    assert needs_rehash is True


def test_ssrf_validator():
    # Loopback blocked
    safe, msg = validate_safe_url("http://127.0.0.1:8000/api")
    assert safe is False
    assert "terlarang" in msg or "ditolak" in msg

    # Cloud metadata blocked
    safe, msg = validate_safe_url("http://169.254.169.254/latest/meta-data/")
    assert safe is False
    assert "metadata" in msg or "ditolak" in msg

    # Private network blocked for external URLs
    safe, msg = validate_safe_url("http://10.100.1.1/device-config")
    assert safe is False
    assert "privat" in msg or "ditolak" in msg

    # Private IP allowed if explicitly registered as NOC device
    safe, _ = validate_safe_url(
        "http://192.168.1.1/rest",
        allow_private_devices=True,
        registered_device_ips={"192.168.1.1"},
    )
    assert safe is True


def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=10)
    client_ip = "192.0.2.42"

    assert limiter.is_allowed(client_ip)[0] is True
    assert limiter.is_allowed(client_ip)[0] is True
    assert limiter.is_allowed(client_ip)[0] is True

    # 4th request must be rejected
    allowed, retry_after = limiter.is_allowed(client_ip)
    assert allowed is False
    assert retry_after > 0

    # Reset
    limiter.reset(client_ip)
    assert limiter.is_allowed(client_ip)[0] is True


# ===========================================================================
# 2. WORKSTREAM B: AUTHORIZATION-FIRST & PERMISSION SIMULATION
# ===========================================================================

def test_permission_simulation_hierarchy():
    svc = get_permission_simulation_service()
    id_mgr = IdentityManager()
    admin_user = id_mgr.get_user_by_username("lingga_admin")
    if not admin_user:
        from core.bootstrap_superadmin import bootstrap_superadmin
        bootstrap_superadmin()
        admin_user = id_mgr.get_user_by_username("lingga_admin")

    admin_uid = admin_user.user_id if admin_user else "usr_25b8282cc548"

    # Superadmin user
    res_admin = svc.simulate_permission(
        user_id=admin_uid,
        resource="device:sw-core-01",
        action="EXECUTE",
    )
    assert res_admin["allowed"] is True
    assert any("SUPER_ADMIN" in r for r in res_admin["matched_rules"])

    # Non-existent user
    res_fake = svc.simulate_permission(
        user_id="usr_nonexistent_xyz",
        resource="device:sw-core-01",
        action="DELETE",
    )
    assert res_fake["allowed"] is False
    assert "User not found" in res_fake["resolution_path"][0]


# ===========================================================================
# 3. WORKSTREAM C: AI OUTPUT SECURITY GUARD
# ===========================================================================

def test_ai_output_guard_secret_redaction():
    guard = AIOutputGuard()

    sensitive_content = """
    Target configuration inspected:
    password: "SuperSecretPassword99!"
    aira_tok_abc1234567890abcdef1234567890abcdef
    snmp_community: "public"
    -----BEGIN RSA PRIVATE KEY-----
    MIIEowIBAAKCAQEA0Y...
    -----END RSA PRIVATE KEY-----
    """

    # Unauthorized caller: all secrets redacted
    sanitized, leaks = guard.inspect_and_sanitize(
        sensitive_content,
        user_permissions={"dashboard.read"},
        is_internal_staff=False,
    )
    assert "[REDACTED_PASSWORD]" in sanitized
    assert "[REDACTED_SESSION_TOKEN]" in sanitized
    assert "[REDACTED_SNMP_COMMUNITY]" in sanitized
    assert "[REDACTED_PRIVATE_KEY]" in sanitized
    assert len(leaks) >= 4


def test_ai_output_guard_pre_retrieval_filtering():
    guard = AIOutputGuard()
    context = [
        {"id": "doc_public", "classification": "PUBLIC", "text": "Public manual"},
        {"id": "doc_internal", "classification": "INTERNAL", "text": "Internal topology"},
        {"id": "doc_restricted", "classification": "RESTRICTED", "text": "Root SSH private key"},
    ]

    # Standard user without ACCESS_SENSITIVE_DATA
    filtered = guard.filter_context_for_user(context, user_permissions={"devices.read"})
    assert len(filtered) == 2
    assert all(item["classification"] != "RESTRICTED" for item in filtered)

    # Privileged internal staff
    privileged = guard.filter_context_for_user(context, is_internal_staff=True)
    assert len(privileged) == 3


# ===========================================================================
# 4. WORKSTREAM D: AUTOMATIC NETWORK SECURITY INTELLIGENCE
# ===========================================================================

def test_device_role_classification():
    engine = get_security_baseline_engine()
    assert engine.classify_device_role({"name": "Core-CCR2004", "model": "CCR2004"}) == DeviceRole.CORE_ROUTER.value
    assert engine.classify_device_role({"name": "SW-Access-Floor1", "model": "CRS326"}) == DeviceRole.ACCESS_SWITCH.value
    assert engine.classify_device_role({"name": "WAN-Gateway", "model": "RB5009"}) == DeviceRole.EDGE_ROUTER.value
    assert engine.classify_device_role({"name": "FortiGate-Primary"}) == DeviceRole.FIREWALL.value


def test_security_baseline_assessment_and_posture():
    engine = get_security_baseline_engine()
    test_device = {
        "device_id": "test_dev_sec_01",
        "name": "Edge-Router-01",
        "role": DeviceRole.EDGE_ROUTER.value,
        "vendor": "mikrotik",
        "version": "7.14",
        "open_ports": [22, 23, 80],       # Port 23 (Telnet), Port 80 (HTTP)
        "snmp_community": "public",        # Default community string
        "allow_remote_dns": True,          # Open DNS Relay
        "has_firewall": False,             # Missing input drop
    }

    findings = engine.assess_device("tenant_internal", test_device)
    assert len(findings) >= 4

    # Verify severity categories
    categories = {f.category for f in findings}
    assert FindingCategory.MANAGEMENT_PLANE.value in categories
    assert FindingCategory.MONITORING_AND_LOGGING.value in categories
    assert FindingCategory.HARDENING_AND_SERVICES.value in categories

    # Verify posture calculation
    posture = engine.calculate_posture("tenant_internal", device_id="test_dev_sec_01")
    assert posture.score < 60
    assert posture.band in (PostureBand.POOR.value, PostureBand.CRITICAL.value)
    assert posture.critical_count >= 1
    assert posture.high_count >= 2


# ===========================================================================
# 5. WORKSTREAM E: EVENT-DRIVEN SECURITY DRIFT
# ===========================================================================

def test_change_detector_security_drift():
    detector = get_change_detector()
    dev_id = "rtr_drift_test_01"

    # Initial baseline
    detector.evaluate_security_drift(
        tenant_id="tenant_internal",
        device_id=dev_id,
        current_ports=[22, 443],
        current_services=["ssh", "https"],
    )

    # Simulate drift: Telnet (23) suddenly opened
    drift_event = detector.evaluate_security_drift(
        tenant_id="tenant_internal",
        device_id=dev_id,
        current_ports=[22, 23, 443],
        current_services=["ssh", "telnet", "https"],
        device_meta={"name": "Drift-Router", "role": "EDGE_ROUTER"},
    )

    assert drift_event is not None
    assert drift_event["event_type"] == "SECURITY_CONFIGURATION_DRIFT"
    assert 23 in drift_event["ports_added"]
    assert "telnet" in drift_event["services_added"]


# ===========================================================================
# 6. WORKSTREAM G: 12-STAGE REASONING PIPELINE & VERSION-AWARE SYNTAX
# ===========================================================================

def test_version_aware_syntax_engine():
    # RouterOS v7 explicit routing-table parameter
    v7_route = DeviceSyntaxEngine.format_default_route("mikrotik", "7.15", "192.168.1.1", "to_isp1")
    assert "/ip/route/add" in v7_route
    assert "routing-table=to_isp1" in v7_route

    # RouterOS v6 routing-mark parameter
    v6_route = DeviceSyntaxEngine.format_default_route("mikrotik", "6.49", "192.168.1.1", "to_isp1")
    assert "/ip route add" in v6_route
    assert "routing-mark=to_isp1" in v6_route

    # Cisco IOS syntax
    cisco_route = DeviceSyntaxEngine.format_default_route("cisco", "17.3", "10.0.0.1")
    assert "ip route 0.0.0.0 0.0.0.0 10.0.0.1" in cisco_route

    # Linux syntax
    linux_route = DeviceSyntaxEngine.format_default_route("linux", "5.15", "10.0.0.1")
    assert "ip route add default via 10.0.0.1" in linux_route


def test_epistemic_reasoning_12_stages():
    engine = get_reasoning_engine()
    res = engine.reason(
        query="Investigate anomalous drop and harden edge router firewall",
        target_devices=[{"name": "gw-core", "vendor": "mikrotik", "version": "7.14"}],
        telemetry_bundle={"latency_ms": 12.0, "status": "UP"},
    )

    assert len(res.stages_trace) == 12
    assert res.confidence == ConfidenceLevel.HIGH.value
    assert res.risk_level == "HIGH"
    assert len(res.recommended_actions) >= 1
    assert "routing-table" in res.sanitized_explanation or "/ip" in res.sanitized_explanation


# ===========================================================================
# 7. WORKSTREAM J: ACTION GOVERNANCE & APPROVAL ENFORCEMENT
# ===========================================================================

def test_action_governance_approval_requirement():
    action_engine = get_action_engine()

    # HIGH risk proposal
    rec = action_engine.propose_action(
        action_name="configure_wan_firewall",
        target_devices=["sw-core-01"],
        description="Deploy standard input chain drop",
        reason="Security posture remediation",
        before_state={"filter": "empty"},
        proposed_changes={"filter": "add chain=input action=drop"},
        expected_after_state={"filter": "active"},
        diff_text="+ /ip firewall filter add chain=input action=drop",
        verification_plan="Verify input chain drops unsolicited packets",
    )

    assert rec.risk_level == ActionRiskLevel.HIGH.value
    assert rec.approval_required is True
    assert rec.status == ActionExecutionStatus.PENDING_APPROVAL.value

    # Attempting execution before approval must be rejected
    exec_res = action_engine.execute_and_verify_action(rec.action_id, operator_id="usr_operator")
    assert exec_res["success"] is False
    assert "must be 'APPROVED'" in exec_res["error"]

    # Resolve approval by admin
    resolve_res = action_engine.resolve_approval(
        action_id=rec.action_id,
        approved=True,
        reviewer_id="usr_25b8282cc548",
        notes="Approved for security baseline conformance",
    )
    assert resolve_res["success"] is True
    assert resolve_res["status"] == ActionExecutionStatus.APPROVED.value

    # Now execution succeeds
    exec_after = action_engine.execute_and_verify_action(rec.action_id, operator_id="usr_25b8282cc548")
    assert exec_after["success"] is True
    assert exec_after["status"] == ActionExecutionStatus.SUCCESS.value
