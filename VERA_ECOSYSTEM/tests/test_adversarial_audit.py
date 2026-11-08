"""
AIRA_ECOSYSTEM/tests/test_adversarial_audit.py

Adversarial acceptance tests validating:
- Section A: Snapshot integrity, raw vs presentation separation, write failure guards, metadata binding & tampering detection.
- Section B: Recovery status semantics, semantic verification, state mismatch detection, unverified reachability disclosure.
- Section C: Credential probe correctness, active session preservation, rejection of invalid supplied credentials despite active sessions, error classification, credential masking.
"""

import concurrent.futures
import json
import os
import socket
import pytest
from unittest.mock import MagicMock, patch

from agents.akane.config_engine import SafeConfigEngine
from agents.akane.connection_manager import ConnectionManager
from agents.akane.session_state import ConnectionSession, STATUS_CONNECTED


# =====================================================================
# SECTION A: SNAPSHOT INTEGRITY TESTS
# =====================================================================

def test_audit_a_raw_snapshot_preserves_secrets_while_presentation_is_masked(tmp_path):
    """Confirm protected snapshot preserves raw data for restore, while presentation is redacted."""
    with patch("agents.akane.config_engine.SNAPSHOT_DIR", tmp_path):
        engine = SafeConfigEngine()

        sample_config = {
            "identity": "Core-Router",
            "admin_user": "admin",
            "password": "CleartextSuperSecretPassword123!",
            "bgp_secret": "BgpNeighborKey999",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            "interface_ip": "192.168.1.1/24",
            "routes": "dst-address=0.0.0.0/0 gateway=192.168.1.254",
        }

        raw_path = engine._persist_snapshot("op_audit_001", {
            "device_name": "core-gw",
            "commands": ["/ip route add dst-address=10.0.0.0/8 gateway=192.168.1.254"],
            "snapshot": sample_config,
        })

        assert os.path.exists(raw_path)
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_record = json.load(f)

        # 1. Protected raw copy MUST retain the exact secret values
        assert raw_record["snapshot"]["password"] == "CleartextSuperSecretPassword123!"
        assert raw_record["snapshot"]["bgp_secret"] == "BgpNeighborKey999"
        assert "-----BEGIN RSA PRIVATE KEY-----" in raw_record["snapshot"]["private_key"]
        assert raw_record["snapshot"]["interface_ip"] == "192.168.1.1/24"
        assert "sha256" in raw_record

        # 2. Presentation snapshot MUST redact all sensitive values for UI and external logging
        presentation = engine.get_presentation_snapshot("op_audit_001")
        assert presentation is not None
        assert presentation["snapshot"]["password"] == "***"
        assert presentation["snapshot"]["bgp_secret"] == "***"
        assert presentation["snapshot"]["private_key"] == "***"
        # Non-sensitive values remain intact
        assert presentation["snapshot"]["interface_ip"] == "192.168.1.1/24"
        assert presentation["snapshot"]["identity"] == "Core-Router"


def test_audit_a_snapshot_write_failure_aborts_apply():
    """Simulate snapshot write failure and verify NO configuration command is applied."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.get_configuration_snapshot.return_value = {"success": True, "snapshot": {"identity": "R1"}}

    # Simulate filesystem write error (e.g. PermissionDenied or DiskFull)
    with patch.object(engine, "_persist_snapshot", side_effect=IOError("Disk full or permission denied")), \
         patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):

        res = engine.apply_change(
            device_name="R1",
            commands=["/ip address add address=10.50.0.1/24 interface=ether2"],
            approved=True,
            operation_id="op_fail_write",
        )

        assert res["success"] is False
        assert res["status"] == "SNAPSHOT_PERSISTENCE_FAILED"
        assert "Gagal menyimpan snapshot ke storage" in res["error"]
        assert res["recovery_needed"] is False
        # Commands must NEVER be executed
        mock_mgr.execute_for_device.assert_not_called()


def test_audit_a_snapshot_integrity_and_tampering_detection(tmp_path):
    """Verify metadata binding and integrity detection on missing, corrupted, or tampered snapshots."""
    with patch("agents.akane.config_engine.SNAPSHOT_DIR", tmp_path):
        engine = SafeConfigEngine()

        op_id = "op_tamper_test"
        raw_path = engine._persist_snapshot(op_id, {
            "device_name": "R1-Border",
            "snapshot": {"routes": "0.0.0.0/0", "identity": "R1-Border"},
        })

        # 1. Valid snapshot passes validation
        val_ok = engine.validate_snapshot_integrity(op_id, expected_device="R1-Border")
        assert val_ok["valid"] is True
        assert val_ok["error"] is None

        # 2. Device mismatch detection
        val_mismatch = engine.validate_snapshot_integrity(op_id, expected_device="R2-Different")
        assert val_mismatch["valid"] is False
        assert val_mismatch["error"] == "DEVICE_MISMATCH"

        # 3. Tampering / Checksum modification detection
        with open(raw_path, "r", encoding="utf-8") as f:
            tampered_data = json.load(f)
        tampered_data["snapshot"]["routes"] = "192.168.0.0/16"  # Modified without updating sha256
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(tampered_data, f)

        val_tampered = engine.validate_snapshot_integrity(op_id)
        assert val_tampered["valid"] is False
        assert val_tampered["error"] == "INTEGRITY_MISMATCH"

        # 4. Truncated / Corrupted file
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write("{ truncated json ...")
        val_corrupt = engine.validate_snapshot_integrity(op_id)
        assert val_corrupt["valid"] is False
        assert val_corrupt["error"] == "CORRUPTED_SNAPSHOT"

        # 5. Missing snapshot file
        val_missing = engine.validate_snapshot_integrity("op_non_existent")
        assert val_missing["valid"] is False
        assert val_missing["error"] == "MISSING_SNAPSHOT"


# =====================================================================
# SECTION B: RECOVERY STATUS SEMANTICS TESTS
# =====================================================================

def test_audit_b_failure_before_any_command():
    """Failure before any command is applied (unapproved or preflight fail)."""
    engine = SafeConfigEngine()

    res_unapproved = engine.apply_change("R1", ["/ip route add dst-address=10.0.0.0/8"], approved=False)
    assert res_unapproved["status"] == "APPROVAL_REQUIRED"
    assert res_unapproved["success"] is False

    mock_mgr = MagicMock()
    mock_mgr.get_configuration_snapshot.return_value = {"success": False, "errors": ["Timeout"]}
    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        res_preflight = engine.apply_change("R1", ["/cmd1", "/cmd2"], approved=True)
        assert res_preflight["status"] == "SNAPSHOT_FAILED"
        assert res_preflight["recovery_needed"] is False


def test_audit_b_failure_mid_operation_and_connection_loss():
    """Failure mid-operation or connection loss during apply triggers APPLY_FAILED with recovery_needed."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.get_configuration_snapshot.return_value = {"success": True, "sections": {}}

    mock_mgr.execute_for_device.side_effect = [
        {"success": True, "output": ""},
        {"success": False, "error": "SSH transport disconnected: connection reset by peer"},
    ]

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        res = engine.apply_change(
            device_name="core-gw",
            commands=["/interface bridge add name=br-lan", "/interface bridge port add bridge=br-lan interface=ether2"],
            approved=True,
        )
        assert res["success"] is False
        assert res["status"] == "APPLY_FAILED"
        assert res["partial_application"] is True
        assert res["applied_count"] == 1
        assert res["recovery_needed"] is True


def test_audit_b_inverse_command_execution_failure():
    """Rollback command execution failure transitions to RECOVERY_REQUIRED with manual_intervention_required."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": False, "error": "item not found"}
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "core-gw"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec = engine.recover("core-gw", ['/ip address remove [find address="10.0.0.1/24"]'])
        assert rec["success"] is False
        assert rec["status"] == "ROLLBACK_PARTIAL_ERROR"
        assert rec["recovery_status"] == "RECOVERY_REQUIRED"
        assert rec["manual_intervention_required"] is True
        assert rec["device_responsive"] is True


def test_audit_b_router_reachable_but_configuration_differs_from_expected():
    """Router reachable after recovery but semantic check shows configuration still differs."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    # Rollback command reports syntax success
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    # Router is reachable
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "core-gw"}
    # BUT live IP addresses STILL contain 192.168.99.1/24 (semantic removal failed silently!)
    mock_mgr.get_ip_addresses.return_value = {
        "success": True,
        "raw_output": "# ADDRESS            NETWORK        INTERFACE\n0 192.168.99.1/24    192.168.99.0   ether2",
    }

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec = engine.recover(
            "core-gw",
            ['/ip address remove [find address="192.168.99.1/24"]'],
            semantic_checks=[{"target": "ip_addresses", "absent": "192.168.99.1"}],
        )

        # MUST NOT declare RECOVERY_VERIFIED
        assert rec["success"] is False
        assert rec["status"] == "ROLLBACK_STATE_MISMATCH"
        assert rec["recovery_status"] == "RECOVERY_STATE_MISMATCH"
        assert rec["lifecycle_status"] == "RECOVERY_REQUIRED"
        assert rec["semantic_verification_passed"] is False
        assert rec["manual_intervention_required"] is True
        assert "differs from expected baseline state" in rec["error"]


def test_audit_b_router_unreachable_after_recovery():
    """Router unreachable after recovery commands were sent."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    mock_mgr.get_identity.return_value = {"success": False, "error": "Connection timed out"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec = engine.recover("core-gw", ["/interface disable ether1"])
        assert rec["success"] is False
        assert rec["status"] == "ROLLBACK_PARTIAL_ERROR"
        assert rec["recovery_status"] == "RECOVERY_REQUIRED"
        assert rec["device_responsive"] is False
        assert rec["manual_intervention_required"] is True


def test_audit_b_successful_recovery_with_semantic_verification():
    """Successful recovery with verified semantic removal of altered entity."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "core-gw"}
    mock_mgr.get_ip_addresses.return_value = {"success": True, "raw_output": "192.168.1.1/24 ether1"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec = engine.recover(
            "core-gw",
            ['/ip address remove [find address="192.168.99.1/24"]'],
            semantic_checks=[{"target": "ip_addresses", "absent": "192.168.99.1"}],
        )
        assert rec["success"] is True
        assert rec["status"] == "ROLLBACK_SUCCESSFUL"
        assert rec["recovery_status"] == "RECOVERY_VERIFIED"
        assert rec["lifecycle_status"] == "RECOVERY_VERIFIED"
        assert rec["semantic_verification_passed"] is True
        assert rec["manual_intervention_required"] is False
        assert rec["atomic_hardware_transaction"] is False


def test_audit_b_reachability_without_semantic_checks_returns_narrow_status():
    """When only reachability is established without semantic checks, return narrower status disclosing uncertainty."""
    engine = SafeConfigEngine()
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "core-gw"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec = engine.recover("core-gw", ["/some custom raw inverse command"])
        assert rec["success"] is True
        assert rec["recovery_status"] == "RECOVERY_ATTEMPTED_REACHABLE"
        assert rec["lifecycle_status"] == "RECOVERY_ATTEMPTED_REACHABLE"
        assert rec["semantic_verification_passed"] is None
        assert "semantic configuration restoration was not verified" in rec["disclaimer"]


# =====================================================================
# SECTION C: CREDENTIAL PROBE CORRECTNESS TESTS
# =====================================================================

def test_audit_c_correct_credentials_no_session():
    """Probe with valid credentials and no prior session succeeds."""
    import paramiko
    mgr = ConnectionManager()
    mock_client = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"name: Lab-GW\n"
    mock_client.exec_command.return_value = (None, mock_stdout, None)

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials("10.0.0.1", "admin", "correct_pwd")
        assert res["authenticated"] is True
        assert res["identity"] == "Lab-GW"
        assert res["reused_session"] is False
        mock_client.connect.assert_called_once()


def test_audit_c_incorrect_credentials_no_session():
    """Probe with invalid credentials fails with auth_failure."""
    import paramiko
    mgr = ConnectionManager()
    mock_client = MagicMock()
    mock_client.connect.side_effect = paramiko.AuthenticationException("Authentication failed")

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials("10.0.0.1", "admin", "wrong_pwd")
        assert res["authenticated"] is False
        assert res["error_type"] == "auth_failure"


def test_audit_c_incorrect_supplied_credentials_with_active_session_is_rejected():
    """CRITICAL: Explicit invalid credentials must NOT be falsely authenticated because an active session exists."""
    import paramiko
    mgr = ConnectionManager()
    key = mgr._host_key("10.0.0.5", 22, "admin")

    # An active authenticated session is currently alive
    mock_session = ConnectionSession(
        session_id="active_sess_gw5",
        device_name="GW5",
        host="10.0.0.5",
        port=22,
        username="admin",
        shell=MagicMock(),
        status=STATUS_CONNECTED,
    )
    mgr._sessions["active_sess_gw5"] = mock_session
    mgr._host_index[key] = "active_sess_gw5"

    mock_client = MagicMock()
    mock_client.connect.side_effect = paramiko.AuthenticationException("Bad password")

    with patch("paramiko.SSHClient", return_value=mock_client):
        # Caller supplies an incorrect password
        res = mgr.test_target_credentials("10.0.0.5", "admin", "attacker_or_wrong_password")

        # MUST reject the probe
        assert res["authenticated"] is False
        assert res["error_type"] == "auth_failure"
        assert res["reused_session"] is False

        # Active session must remain unharmed and connected
        assert "active_sess_gw5" in mgr._sessions
        assert mgr._sessions["active_sess_gw5"].status == STATUS_CONNECTED


def test_audit_c_different_identity_probed_preserves_active_session():
    """Probing credentials for user 'operator' while 'admin' is active uses a separate probe and preserves both."""
    import paramiko
    mgr = ConnectionManager()
    admin_key = mgr._host_key("10.0.0.6", 22, "admin")

    mock_admin_session = ConnectionSession(
        session_id="active_sess_admin",
        device_name="GW6",
        host="10.0.0.6",
        port=22,
        username="admin",
        shell=MagicMock(),
        status=STATUS_CONNECTED,
    )
    mgr._sessions["active_sess_admin"] = mock_admin_session
    mgr._host_index[admin_key] = "active_sess_admin"

    mock_client = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"name: GW6\n"
    mock_client.exec_command.return_value = (None, mock_stdout, None)

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials("10.0.0.6", "operator", "operator_pwd")
        assert res["authenticated"] is True
        assert res["identity"] == "GW6"
        assert res["reused_session"] is False

        # Admin session remains untouched
        assert mgr._sessions["active_sess_admin"].status == STATUS_CONNECTED


def test_audit_c_concurrent_probes_to_same_target():
    """Verify concurrent probes to the same target execute cleanly without race conditions."""
    import paramiko
    mgr = ConnectionManager()

    def run_probe(idx):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = f"name: Router-{idx}\n".encode()
        mock_client.exec_command.return_value = (None, mock_stdout, None)

        with patch("paramiko.SSHClient", return_value=mock_client):
            return mgr.test_target_credentials("192.168.100.1", "admin", f"pass_{idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(run_probe, i) for i in range(5)]
        results = [f.result() for f in futures]

    for res in results:
        assert res["authenticated"] is True
        assert "Router-" in res["identity"]


def test_audit_c_host_key_mismatch():
    """Host key mismatch triggers host_key_failure error_type."""
    import paramiko
    mgr = ConnectionManager()
    mock_client = MagicMock()
    mock_client.connect.side_effect = paramiko.BadHostKeyException("10.0.0.7", None, None)

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials("10.0.0.7", "admin", "pwd")
        assert res["authenticated"] is False
        assert res["error_type"] == "host_key_failure"


def test_audit_c_timeout_and_unreachable():
    """Timeouts and network refusal are categorized as timeout and unreachable."""
    import paramiko
    mgr = ConnectionManager()

    mock_client_to = MagicMock()
    mock_client_to.connect.side_effect = socket.timeout("Timed out")
    with patch("paramiko.SSHClient", return_value=mock_client_to):
        res_to = mgr.test_target_credentials("10.0.0.8", "admin", "pwd")
        assert res_to["authenticated"] is False
        assert res_to["error_type"] == "timeout"

    mock_client_un = MagicMock()
    mock_client_un.connect.side_effect = ConnectionRefusedError("Connection refused")
    with patch("paramiko.SSHClient", return_value=mock_client_un):
        res_un = mgr.test_target_credentials("10.0.0.9", "admin", "pwd")
        assert res_un["authenticated"] is False
        assert res_un["error_type"] == "unreachable"


def test_audit_c_credentials_never_exposed_in_error_or_logs():
    """Passwords and private keys must never appear in response messages or error strings."""
    import paramiko
    mgr = ConnectionManager()
    mock_client = MagicMock()
    secret_pass = "SuperSecret_Sensitive_Password_999!"
    mock_client.connect.side_effect = paramiko.AuthenticationException(f"Failed for user admin with password {secret_pass}")

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials("10.0.0.10", "admin", secret_pass)
        assert res["authenticated"] is False
        assert secret_pass not in str(res)
        assert secret_pass not in res["message"]
