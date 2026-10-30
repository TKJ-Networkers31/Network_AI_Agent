"""
Unit tests for enhanced ConnectionManager (APCE) in agents/akane/connection_manager.py
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from agents.akane.connection_manager import (
    ConnectionManager,
    MAX_SESSION_LIFETIME_SECONDS,
)
from agents.akane.session_state import ConnectionSession, STATUS_CONNECTED, STATUS_CLOSED


class FakeShell:
    def __init__(self, output="mock_output"):
        self._output = output
        self._alive = True
        self.open_calls = 0

    def open(self, host, port, username, password=None, key_data=None):
        self.open_calls += 1
        self._alive = True

    def execute(self, command, timeout=25.0):
        time.sleep(0.01)  # small delay for latency profiling
        return {"output": f"Output for {command}: {self._output}", "prompt_matched": True}

    def is_alive(self):
        return self._alive

    def close(self):
        self._alive = False


@pytest.fixture
def manager():
    mgr = ConnectionManager()
    mgr._monitor_stop.set()  # Stop background thread during tests
    return mgr


def test_session_state_profiling():
    shell = FakeShell()
    sess = ConnectionSession(
        session_id="test1",
        device_name="R1",
        host="192.168.1.1",
        port=22,
        username="admin",
        shell=shell,
        max_lifetime_seconds=10.0,
    )
    assert sess.command_count == 0
    assert sess.avg_latency_ms == 0.0

    sess.record_command(25.5)
    sess.record_command(34.5)
    assert sess.command_count == 2
    assert sess.last_latency_ms == 34.5
    assert sess.avg_latency_ms == 30.0
    assert not sess.is_expired(time.time())
    assert sess.is_expired(time.time() + 20)


@patch("agents.akane.connection_manager.PersistentShell")
def test_open_connection_reuse_and_single_flight(mock_shell_cls, manager):
    fake = FakeShell()
    mock_shell_cls.return_value = fake

    # First open
    res1 = manager.open_connection("192.168.88.1", "admin", "admin123")
    assert res1["success"] is True
    assert res1["reused"] is False
    assert manager._total_sessions_opened == 1

    # Second open to exact same host -> reuse!
    res2 = manager.open_connection("192.168.88.1", "admin", "admin123")
    assert res2["success"] is True
    assert res2["reused"] is True
    assert res2["session"]["session_id"] == res1["session"]["session_id"]
    assert manager._total_sessions_reused == 1


@patch("agents.akane.connection_manager.PersistentShell")
def test_execute_latency_tracking(mock_shell_cls, manager):
    fake = FakeShell("uptime: 2w")
    mock_shell_cls.return_value = fake

    opened = manager.open_connection("10.0.0.1", "admin", "pass")
    sid = opened["session"]["session_id"]

    res = manager.execute(sid, "/system resource print")
    assert res["success"] is True
    assert "latency_ms" in res
    assert res["latency_ms"] >= 0.0
    assert res["avg_latency_ms"] >= 0.0

    stats = manager.get_stats()
    assert stats["active_sessions_count"] >= 1
    assert stats["total_commands_executed"] >= 1


@patch("agents.akane.connection_manager.PersistentShell")
def test_reconnect_backoff_on_failures(mock_shell_cls, manager):
    mock_shell = MagicMock()
    mock_shell.open.side_effect = Exception("Connection refused")
    mock_shell_cls.return_value = mock_shell

    key = "10.200.1.1:22:admin"
    # First failure
    res1 = manager.open_connection("10.200.1.1", "admin", "pass")
    assert res1["success"] is False
    assert "Connection refused" in res1["error"]

    # Second immediate attempt should trigger backoff
    res2 = manager.open_connection("10.200.1.1", "admin", "pass")
    assert res2["success"] is False
    assert res2.get("backoff_active") is True
    assert "Reconnect backoff aktif" in res2["error"]


@patch("agents.akane.connection_manager.PersistentShell")
def test_max_lifetime_expired_cleanup(mock_shell_cls, manager):
    fake = FakeShell()
    mock_shell_cls.return_value = fake

    opened = manager.open_connection("10.0.0.2", "admin", "pass")
    sid = opened["session"]["session_id"]
    sess = manager._sessions[sid]

    # Force session to be expired
    sess.connected_at = time.time() - (MAX_SESSION_LIFETIME_SECONDS + 10)
    assert sess.is_expired() is True

    # Idle & lifetime check cleans it up
    manager._check_idle_sessions()
    assert sess.status == STATUS_CLOSED
