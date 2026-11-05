"""
tests/test_networking_iii_connection_manager.py — Unit tests for Phase Networking III Multi-Device Connection Manager.
"""

import pytest
from agents.akane.connection_manager import ConnectionManager
from agents.akane.session_state import ConnectionState, ManagementProtocol


def test_connection_states_and_protocols():
    assert ConnectionState.DISCONNECTED.value == "disconnected"
    assert ConnectionState.CONNECTING.value == "connecting"
    assert ConnectionState.CONNECTED.value == "connected"
    assert ConnectionState.AUTHENTICATION_FAILED.value == "authentication_failed"
    assert ConnectionState.CONNECTION_TIMEOUT.value == "connection_timeout"
    assert ConnectionState.CONNECTION_ERROR.value == "connection_error"
    assert ConnectionState.SESSION_EXPIRED.value == "session_expired"
    assert ConnectionState.CLOSING.value == "closing"

    assert ManagementProtocol.SSH.value == "ssh"
    assert ManagementProtocol.REST.value == "rest"
    assert ManagementProtocol.SNMP.value == "snmp"


def test_execute_batch_empty():
    cm = ConnectionManager()
    res = cm.execute_batch([])
    assert res == []
    cm.shutdown()


def test_execute_batch_unresolvable_targets():
    cm = ConnectionManager()
    requests = [
        {"device_name": "phantom_device_1", "command": "/system identity print"},
        {"device_name": "phantom_device_2", "command": "/system identity print"},
    ]
    results = cm.execute_batch(requests, max_concurrency=2)
    assert len(results) == 2
    for r in results:
        assert r["success"] is False
        assert "tidak ditemukan" in r["error"].lower()
    cm.shutdown()
