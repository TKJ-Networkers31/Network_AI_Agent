"""
Unit tests for AKANE Safe Configuration Engine in agents/akane/config_engine.py
"""

from unittest.mock import MagicMock, patch
import pytest

from agents.akane.config_engine import (
    SafeConfigEngine,
    generate_rollback_for_command,
)


def test_rollback_generators():
    # 1. IP address
    rb_ip = generate_rollback_for_command('/ip address add address=192.168.100.1/24 interface=ether2')
    assert rb_ip == '/ip address remove [find address="192.168.100.1/24"]'

    # 2. IP route
    rb_rt = generate_rollback_for_command('/ip route add dst-address=10.50.0.0/16 gateway=192.168.1.254')
    assert rb_rt == '/ip route remove [find dst-address="10.50.0.0/16"]'

    # 3. Interface enable / disable
    rb_en = generate_rollback_for_command('/interface enable ether3')
    assert rb_en == '/interface disable ether3'
    rb_dis = generate_rollback_for_command('/interface disable ether3')
    assert rb_dis == '/interface enable ether3'


def test_plan_change_safety_checks():
    engine = SafeConfigEngine()

    # Safe commands
    safe_cmds = [
        "/ip address add address=192.168.10.1/24 interface=ether2",
        "/ip route add dst-address=10.0.0.0/8 gateway=192.168.1.1",
    ]
    plan_safe = engine.plan_change("R1", safe_cmds)
    assert plan_safe["success"] is True
    assert plan_safe["safety_status"] == "APPROVED_FOR_VALIDATION"
    assert len(plan_safe["rollback_plan"]) == 2

    # Dangerous command rejection
    dangerous_cmds = [
        "/ip address add address=10.0.0.1/24 interface=ether2",
        "/system reset-configuration no-defaults=yes",
    ]
    plan_danger = engine.plan_change("R1", dangerous_cmds)
    assert plan_danger["success"] is False
    assert plan_danger["safety_status"] == "REJECTED_DANGEROUS"
    assert any("dangerous operation" in iss for iss in plan_danger["flagged_issues"])


def test_preview_change_diff_generation():
    engine = SafeConfigEngine()
    validation_res = {
        "change_plan": {
            "proposed_commands": ["/ip address add address=10.1.1.1/24 interface=ether3"],
            "rollback_plan": ['/ip address remove [find address="10.1.1.1/24"]'],
        }
    }
    prev = engine.preview_change("R1", validation_res)
    assert prev["success"] is True
    assert prev["requires_approval"] is True
    assert "+ /ip address add address=10.1.1.1/24 interface=ether3" in prev["diff_preview"]
    assert "- [Rollback plan]: /ip address remove [find address=\"10.1.1.1/24\"]" in prev["diff_preview"]


def test_apply_change_approval_enforcement():
    engine = SafeConfigEngine()
    cmds = ["/ip address add address=10.1.1.1/24 interface=ether3"]

    # 1. Unapproved call -> MUST BE REJECTED
    unapproved = engine.apply_change("R1", cmds, approved=False)
    assert unapproved["success"] is False
    assert unapproved["status"] == "APPROVAL_REQUIRED"
    assert unapproved["requires_approval"] is True

    # 2. Approved call with mock connection manager -> ALLOWED
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": True, "output": "", "latency_ms": 15.0}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        approved_res = engine.apply_change("R1", cmds, approved=True)
        assert approved_res["success"] is True
        assert approved_res["status"] == "APPLIED_SUCCESSFULLY"
        assert approved_res["applied_count"] == 1
        assert mock_mgr.execute_for_device.called


def test_verify_and_recover_lifecycle():
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.get_ip_addresses.return_value = {"success": True, "raw_output": "10.1.1.1/24 ether3"}
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "R1-Core"}
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        # Verification stage
        ver = engine.verify_change("R1", ["/ip address add address=10.1.1.1/24 interface=ether3"])
        assert ver["success"] is True
        assert ver["status"] == "VERIFIED_OPERATIONAL"

        # Recovery stage
        rec = engine.recover("R1", ['/ip address remove [find address="10.1.1.1/24"]'])
        assert rec["success"] is True
        assert rec["status"] == "ROLLBACK_SUCCESSFUL"
