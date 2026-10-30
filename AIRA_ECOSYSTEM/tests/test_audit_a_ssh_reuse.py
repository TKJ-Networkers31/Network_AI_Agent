"""
tests/test_audit_a_ssh_reuse.py — Isolated Evidence Tests for Audit A (SSH Connection Reuse).
"""

import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from agents.akane.connection_manager import (
    ConnectionManager,
    MAX_SESSION_LIFETIME_SECONDS,
    IDLE_TIMEOUT_SECONDS,
)
from agents.akane.session_state import STATUS_CONNECTED, STATUS_CLOSED, STATUS_ERROR


class CountingMockShell:
    """Mock PersistentShell that records connection lifecycle events."""
    transport_creations = 0
    transport_closes = 0
    executions = []

    def __init__(self):
        self._alive = True

    def open(self, host, port, username, password=None, key_data=None):
        CountingMockShell.transport_creations += 1
        time.sleep(0.02)  # Simulate network handshake delay
        self._alive = True

    def execute(self, command, timeout=25.0):
        CountingMockShell.executions.append(command)
        time.sleep(0.01)  # Simulate command execution
        return {"output": f"ACK:{command}", "prompt_matched": True}

    def is_alive(self):
        return self._alive

    def close(self):
        CountingMockShell.transport_closes += 1
        self._alive = False


@pytest.fixture(autouse=True)
def reset_counts():
    CountingMockShell.transport_creations = 0
    CountingMockShell.transport_closes = 0
    CountingMockShell.executions.clear()


@pytest.fixture
def isolated_manager():
    mgr = ConnectionManager()
    mgr._monitor_stop.set()  # Stop background thread
    return mgr


@patch("agents.akane.connection_manager.PersistentShell", side_effect=CountingMockShell)
def test_audit_a_concurrent_single_flight(mock_shell, isolated_manager):
    """
    Test condition: 10 concurrent threads call open_connection for the same device at the exact same moment.
    Expected:
    - Exactly 1 transport creation.
    - Exactly 1 session created in session pool.
    - Exactly 9 reuses.
    """
    results = []
    threads = []

    def worker():
        res = isolated_manager.open_connection("192.168.10.1", "admin", "secret")
        results.append(res)

    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 10
    assert all(r["success"] is True for r in results)

    # Verify session IDs are all identical
    first_session_id = results[0]["session"]["session_id"]
    assert all(r["session"]["session_id"] == first_session_id for r in results)

    # Count creations vs reuses
    reused_count = sum(1 for r in results if r["reused"] is True)
    created_count = sum(1 for r in results if r["reused"] is False)

    assert created_count == 1
    assert reused_count == 9
    assert CountingMockShell.transport_creations == 1

    stats = isolated_manager.get_stats()
    assert stats["active_sessions_count"] == 1
    assert stats["total_sessions_opened"] == 1
    assert stats["total_sessions_reused"] == 9


@patch("agents.akane.connection_manager.PersistentShell", side_effect=CountingMockShell)
def test_audit_a_concurrent_command_execution_integrity(mock_shell, isolated_manager):
    """
    Test condition: 5 concurrent threads execute different commands on the same session.
    Expected:
    - Commands serialize cleanly via session lock.
    - No output mixing occurs.
    - Latency and stats reflect all 5 commands.
    """
    opened = isolated_manager.open_connection("192.168.10.2", "admin", "secret")
    session_id = opened["session"]["session_id"]

    results = {}
    threads = []

    def cmd_worker(cmd_id):
        cmd = f"/system identity print --tag={cmd_id}"
        res = isolated_manager.execute(session_id, cmd)
        results[cmd_id] = res

    for i in range(5):
        t = threading.Thread(target=cmd_worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 5
    for i in range(5):
        res = results[i]
        assert res["success"] is True
        # Output must match the exact command sent, never mixed with other threads
        assert res["output"] == f"ACK:/system identity print --tag={i}"
        assert res["latency_ms"] >= 0.0

    stats = isolated_manager.get_stats()
    assert stats["total_commands_executed"] == 5


@patch("agents.akane.connection_manager.PersistentShell", side_effect=CountingMockShell)
def test_audit_a_broken_transport_auto_recovery(mock_shell, isolated_manager):
    """
    Test condition: Active session experiences unexpected transport drop (is_alive=False).
    Next command should automatically detect the dropped transport and recover.
    """
    opened = isolated_manager.open_connection("192.168.10.3", "admin", "secret")
    session_id = opened["session"]["session_id"]
    session = isolated_manager._sessions[session_id]

    assert CountingMockShell.transport_creations == 1

    # Simulate transport failure
    session.shell._alive = False
    assert session.shell.is_alive() is False

    # Execute should auto-reconnect
    res = isolated_manager.execute(session_id, "/interface print")
    assert res["success"] is True
    assert CountingMockShell.transport_creations == 2  # Reconnected!
    assert session.shell.is_alive() is True


@patch("agents.akane.connection_manager.PersistentShell", side_effect=CountingMockShell)
def test_audit_a_lifecycle_expiry_and_shutdown(mock_shell, isolated_manager):
    """
    Test condition: Verify idle cleanup, max lifetime expiry, and shutdown cleanup.
    """
    opened1 = isolated_manager.open_connection("192.168.10.4", "admin", "secret")
    sid1 = opened1["session"]["session_id"]
    sess1 = isolated_manager._sessions[sid1]

    opened2 = isolated_manager.open_connection("192.168.10.5", "admin", "secret")
    sid2 = opened2["session"]["session_id"]
    sess2 = isolated_manager._sessions[sid2]

    # Force sess1 to be idle expired
    sess1.last_activity = time.time() - (IDLE_TIMEOUT_SECONDS + 5)
    # Force sess2 to be lifetime expired
    sess2.connected_at = time.time() - (MAX_SESSION_LIFETIME_SECONDS + 5)

    isolated_manager._check_idle_sessions()

    assert sess1.status == STATUS_CLOSED
    assert sess2.status == STATUS_CLOSED

    # Test clean shutdown
    opened3 = isolated_manager.open_connection("192.168.10.6", "admin", "secret")
    sid3 = opened3["session"]["session_id"]
    assert isolated_manager._sessions[sid3].status == STATUS_CONNECTED

    isolated_manager.shutdown()
    assert isolated_manager._sessions[sid3].status == STATUS_CLOSED
