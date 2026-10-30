import json
import os
import pytest
from unittest.mock import MagicMock, patch

from agents.akane.config_engine import SafeConfigEngine

def test_recovery_snapshot_failure_blocks_multi_command():
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    # Mock snapshot failure
    mock_mgr.get_configuration_snapshot.return_value = {
        "success": False,
        "errors": ["Connection timeout while reading /ip route"],
    }

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        res = engine.apply_change(
            device_name="core-gw",
            commands=[
                "/ip address add address=192.168.10.1/24 interface=ether2",
                "/ip route add dst-address=10.0.0.0/8 gateway=192.168.10.254",
            ],
            approved=True,
            operation_id="op_fail_snap",
        )
        assert res["success"] is False
        assert res["status"] == "SNAPSHOT_FAILED"
        assert res["recovery_needed"] is False
        # Commands must not be executed
        mock_mgr.execute_for_device.assert_not_called()

def test_recovery_elevated_risk_detection():
    engine = SafeConfigEngine()
    
    # 1. Standard risk change
    plan_std = engine.plan_change("core-gw", ["/ip address add address=192.168.50.1/24 interface=ether4"])
    assert plan_std["success"] is True
    assert plan_std["risk_level"] == "STANDARD"
    assert len(plan_std["risk_flags"]) == 0

    # 2. Elevated management risk change (default route modification)
    plan_route = engine.plan_change("core-gw", ["/ip route add dst-address=0.0.0.0/0 gateway=192.168.1.1"])
    assert plan_route["success"] is True
    assert plan_route["risk_level"] == "ELEVATED_MANAGEMENT_RISK"
    assert any("default/gateway" in f for f in plan_route["risk_flags"])

    # 3. Elevated risk change (input filter drop)
    plan_fw = engine.plan_change("core-gw", ["/ip firewall filter add chain=input action=drop comment=block_all"])
    assert plan_fw["success"] is True
    assert plan_fw["risk_level"] == "ELEVATED_MANAGEMENT_RISK"
    assert any("input chain" in f for f in plan_fw["risk_flags"])

def test_recovery_partial_apply_detection():
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.get_configuration_snapshot.return_value = {"success": True, "sections": {"identity": "core-gw"}}
    
    # First command succeeds, second command fails
    mock_mgr.execute_for_device.side_effect = [
        {"success": True, "output": ""},
        {"success": False, "error": "failure: route already exists"},
    ]

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        res = engine.apply_change(
            device_name="core-gw",
            commands=[
                "/ip address add address=192.168.10.1/24 interface=ether2",
                "/ip route add dst-address=10.0.0.0/8 gateway=192.168.10.254",
            ],
            approved=True,
            operation_id="op_partial_fail",
        )
        assert res["success"] is False
        assert res["status"] == "APPLY_FAILED"
        assert res["partial_application"] is True
        assert res["applied_count"] == 1
        assert "10.0.0.0/8" in res["failed_command"]
        assert res["recovery_needed"] is True
        assert "operation_id" in res

def test_recovery_verification_and_unresponsive_device():
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    
    # 1. Recovery succeeds with semantic verification
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "core-gw"}
    mock_mgr.get_ip_addresses.return_value = {"success": True, "raw_output": "192.168.1.1/24 ether1"} # does not contain 192.168.20.1

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec_ok = engine.recover(
            "core-gw",
            ['/ip address remove [find address="192.168.20.1/24"]'],
            semantic_checks=[{"target": "ip_addresses", "absent": "192.168.20.1/24"}],
        )
        assert rec_ok["success"] is True
        assert rec_ok["recovery_status"] == "RECOVERY_VERIFIED"
        assert rec_ok["semantic_verification_passed"] is True
        assert rec_ok["manual_intervention_required"] is False
        assert rec_ok["recovery_attempted"] is True

    # 2. Recovery commands execute but router becomes unreachable/unresponsive
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    mock_mgr.get_identity.return_value = {"success": False, "error": "Connection timed out"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec_fail = engine.recover("core-gw", ['/ip address remove [find address="192.168.20.1/24"]'])
        assert rec_fail["success"] is False
        assert rec_fail["recovery_status"] == "RECOVERY_REQUIRED"
        assert rec_fail["device_responsive"] is False
        assert rec_fail["manual_intervention_required"] is True

def test_snapshot_persistence_and_masking(tmp_path):
    with patch("agents.akane.config_engine.SNAPSHOT_DIR", tmp_path):
        engine = SafeConfigEngine()
        snap_path = engine._persist_snapshot("test_op_123", {
            "device_name": "core-gw",
            "snapshot": {
                "password": "unmasked_secret_password",
                "ssh_key": "-----BEGIN RSA PRIVATE KEY-----",
                "config": "valid_config",
            },
        })
        assert os.path.exists(snap_path)
        
        # Protected raw file retains exact secrets for recovery
        with open(snap_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["snapshot"]["password"] == "unmasked_secret_password"
        assert data["snapshot"]["ssh_key"] == "-----BEGIN RSA PRIVATE KEY-----"
        assert data["snapshot"]["config"] == "valid_config"
        assert "sha256" in data

        # Presentation snapshot masks secrets for UI and audit logs
        pres = engine.get_presentation_snapshot("test_op_123")
        assert pres is not None
        assert pres["snapshot"]["password"] == "***"
        assert pres["snapshot"]["ssh_key"] == "***"
        assert pres["snapshot"]["config"] == "valid_config"

        # Integrity validation succeeds
        val = engine.validate_snapshot_integrity("test_op_123", expected_device="core-gw")
        assert val["valid"] is True
