import socket
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from agents.akane.connection_manager import ConnectionManager, get_connection_manager
from agents.akane.session_state import ConnectionSession, STATUS_CONNECTED
from api.main import app

def test_target_credentials_success():
    mgr = ConnectionManager()
    
    mock_client = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"name: RouterOS-Core\n"
    mock_client.exec_command.return_value = (None, mock_stdout, None)

    with patch("paramiko.SSHClient", return_value=mock_client):
        res = mgr.test_target_credentials(
            host="192.168.1.1",
            username="admin",
            password="secretpassword",
            port=22,
            timeout=3.0,
        )
        assert res["success"] is True
        assert res["authenticated"] is True
        assert res["identity"] == "RouterOS-Core"
        assert res["reused_session"] is False
        assert res["error_type"] is None
        mock_client.connect.assert_called_once()
        mock_client.close.assert_called_once()
        # Verify secret password is not in res
        assert "secretpassword" not in str(res)

def test_target_credentials_reuses_active_session_when_no_explicit_password():
    mgr = ConnectionManager()
    key = mgr._host_key("10.0.0.1", 22, "admin")
    
    # Insert an active mock session
    mock_session = ConnectionSession(
        session_id="test_sess_01",
        device_name="GW1",
        host="10.0.0.1",
        port=22,
        username="admin",
        shell=MagicMock(),
        status=STATUS_CONNECTED,
    )
    mgr._sessions["test_sess_01"] = mock_session
    mgr._host_index[key] = "test_sess_01"

    with patch.object(mgr, "execute") as mock_exec:
        mock_exec.return_value = {
            "success": True,
            "output": "Flags: X - disabled\nname: GW-Active-Session\n",
        }
        with patch("paramiko.SSHClient") as mock_paramiko_client:
            res = mgr.test_target_credentials(
                host="10.0.0.1",
                username="admin",
                password=None,
                port=22,
            )
            assert res["success"] is True
            assert res["authenticated"] is True
            assert res["identity"] == "GW-Active-Session"
            assert res["reused_session"] is True
            # Proved: Did NOT construct or open a new paramiko client!
            mock_paramiko_client.assert_not_called()
            mock_exec.assert_called_once()

def test_target_credentials_validates_supplied_credentials_even_with_active_session():
    import paramiko
    mgr = ConnectionManager()
    key = mgr._host_key("10.0.0.1", 22, "admin")
    
    # Existing active session
    mock_session = ConnectionSession(
        session_id="test_sess_active",
        device_name="GW1",
        host="10.0.0.1",
        port=22,
        username="admin",
        shell=MagicMock(),
        status=STATUS_CONNECTED,
    )
    mgr._sessions["test_sess_active"] = mock_session
    mgr._host_index[key] = "test_sess_active"

    # Caller probes with incorrect password
    with patch("paramiko.SSHClient") as mock_cls:
        client_inst = mock_cls.return_value
        client_inst.connect.side_effect = paramiko.AuthenticationException("Invalid password")
        
        res = mgr.test_target_credentials(
            host="10.0.0.1",
            username="admin",
            password="wrong_password_attempt",
            port=22,
        )
        # Probe MUST reject the invalid supplied credentials
        assert res["authenticated"] is False
        assert res["error_type"] == "auth_failure"
        assert res["reused_session"] is False
        
        # Proved: Active session was preserved and NOT closed
        assert "test_sess_active" in mgr._sessions
        assert mgr._sessions["test_sess_active"].status == STATUS_CONNECTED

def test_target_credentials_distinguishes_error_types():
    import paramiko
    mgr = ConnectionManager()

    # 1. Auth failure
    with patch("paramiko.SSHClient") as mock_cls:
        client_inst = mock_cls.return_value
        client_inst.connect.side_effect = paramiko.AuthenticationException("Auth failed")
        res = mgr.test_target_credentials("192.168.1.2", "admin", "wrong")
        assert res["authenticated"] is False
        assert res["error_type"] == "auth_failure"

    # 2. Timeout
    with patch("paramiko.SSHClient") as mock_cls:
        client_inst = mock_cls.return_value
        client_inst.connect.side_effect = socket.timeout("timed out")
        res = mgr.test_target_credentials("192.168.1.3", "admin", "any")
        assert res["authenticated"] is False
        assert res["error_type"] == "timeout"

    # 3. Host key failure
    with patch("paramiko.SSHClient") as mock_cls:
        client_inst = mock_cls.return_value
        client_inst.connect.side_effect = paramiko.BadHostKeyException("192.168.1.4", None, None)
        res = mgr.test_target_credentials("192.168.1.4", "admin", "any")
        assert res["authenticated"] is False
        assert res["error_type"] == "host_key_failure"

    # 4. Unreachable
    with patch("paramiko.SSHClient") as mock_cls:
        client_inst = mock_cls.return_value
        client_inst.connect.side_effect = ConnectionRefusedError("Connection refused")
        res = mgr.test_target_credentials("192.168.1.5", "admin", "any")
        assert res["authenticated"] is False
        assert res["error_type"] == "unreachable"

def test_topology_endpoint_delegates_to_connection_manager():
    client = TestClient(app)
    
    mock_mgr = MagicMock()
    mock_mgr.test_target_credentials.return_value = {
        "success": True,
        "authenticated": True,
        "identity": "Delegated-Router",
        "error_type": None,
        "message": "Koneksi & autentikasi berhasil!",
    }

    with patch("api.routers.topology._probe_tcp_port", return_value=(True, 15.0, "")), \
         patch("api.routers.topology.get_connection_manager", return_value=mock_mgr):

        resp = client.post(
            "/api/topology/test-reachability",
            json={
                "host": "192.168.88.1",
                "port": 22,
                "username": "admin",
                "password": "supersecretpassword123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["reachable"] is True
        assert data["port_open"] is True
        assert data["authenticated"] is True
        assert data["identity"] == "Delegated-Router"
        
        # Verify delegation occurred
        mock_mgr.test_target_credentials.assert_called_once_with(
            host="192.168.88.1",
            username="admin",
            password="supersecretpassword123",
            port=22,
            timeout=4.0,
        )
        # Ensure password is NEVER leaked in response payload
        assert "supersecretpassword123" not in resp.text
