"""
AIRA_ECOSYSTEM/tests/test_lifecycle_hardening.py — Pre-Networking IV Lifecycle Hardening Regression Suite.

Verifies:
1. test_reaper_vs_inflight_command_mutual_exclusion: Reaper cannot close session during command execution.
2. test_execute_for_device_recovers_if_session_closed_between_check_and_exec: 1-shot recovery on TOCTOU closure.
3. test_stale_error_session_is_not_reused_indefinitely: STATUS_ERROR sessions are evicted and fresh sessions opened.
4. test_nms_polling_cycle_quiescence_with_no_eligible_devices: Empty polling cycles incur zero network overhead.
5. test_successful_reconnect_updates_connected_at: Reconnection resets absolute lifetime clock.
6. test_failed_reconnect_does_not_reset_connected_at: Failed reconnect leaves connected_at intact and evicts stale index.
7. test_every_nms_telemetry_command_passes_through_readonly_validator: All 5 NMS commands route through validator.
8. test_rejected_nms_commands_never_reach_ssh_execution: Non-read-only commands fail closed before SSH execution.
9. test_concurrent_session_cleanup_cannot_evict_newer_valid_session: Newer session index is preserved.
10. test_existing_session_reuse_behavior_intact: Single-flight concurrency and transport reuse remain 100% operational.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest

from agents.akane.connection_manager import (
    ConnectionManager,
    IDLE_TIMEOUT_SECONDS,
    MAX_SESSION_LIFETIME_SECONDS,
)
from agents.akane.session_state import (
    STATUS_BUSY,
    STATUS_CLOSED,
    STATUS_CONNECTED,
    STATUS_ERROR,
    ConnectionSession,
)
from core.network_intelligence.security import (
    execute_safe_readonly_command,
    validate_readonly_command,
)
from core.nms_engine import NmsEngine


class MockShell:
    """Deterministic mock shell with thread synchronization."""
    transport_creations = 0
    transport_closes = 0

    def __init__(self):
        self._alive = True
        self.host = "192.168.10.1"
        self.username = "admin"
        self.port = 22

    def open(self, host, port, username, password=None, key_data=None, timeout=10.0):
        MockShell.transport_creations += 1
        self.host = host
        self.port = port
        self.username = username
        self._alive = True

    def execute(self, command, timeout=25.0):
        if not self._alive:
            raise RuntimeError("Shell is closed/disconnected.")
        return {"output": f"OUT:{command}", "prompt_matched": True}

    def is_alive(self):
        return self._alive

    def close(self):
        MockShell.transport_closes += 1
        self._alive = False


@pytest.fixture(autouse=True)
def reset_mock_shell():
    MockShell.transport_creations = 0
    MockShell.transport_closes = 0


@pytest.fixture
def isolated_manager():
    mgr = ConnectionManager()
    mgr._monitor_stop.set()  # Stop automatic background thread for deterministic control
    return mgr


def create_test_nms_db(db_path: Path):
    """Pre-creates the minimal topology_nodes schema required by NmsEngine._init_db."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS topology_nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            identity TEXT,
            ip TEXT,
            mac TEXT,
            device_type TEXT DEFAULT 'router'
        );
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Test 1: Reaper vs In-Flight Command Mutual Exclusion
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_reaper_vs_inflight_command_mutual_exclusion(mock_shell_cls, isolated_manager):
    """
    Test condition:
    1. Verify reaper ignores sessions in STATUS_BUSY.
    2. Verify direct close_connection() blocks on session lock until in-flight command finishes.
    """
    opened = isolated_manager.open_connection("192.168.10.1", "admin", "pass")
    sid = opened["session"]["session_id"]
    sess = isolated_manager._sessions[sid]

    cmd_started = threading.Event()
    cmd_can_finish = threading.Event()
    cmd_result = {}

    def slow_exec(cmd, timeout=25.0):
        cmd_started.set()
        cmd_can_finish.wait(timeout=2.0)
        return {"output": f"OK:{cmd}", "prompt_matched": True}

    def worker():
        with patch.object(sess.shell, "execute", side_effect=slow_exec):
            cmd_result["res"] = isolated_manager.execute(sid, "/system identity print")

    t_worker = threading.Thread(target=worker)
    t_worker.start()
    assert cmd_started.wait(timeout=1.0), "Command worker failed to start"

    # 1. While command is executing, status is BUSY
    time.sleep(0.02)
    assert sess.status == STATUS_BUSY

    # Force expiration timestamps
    sess.connected_at = time.time() - (MAX_SESSION_LIFETIME_SECONDS + 10)
    sess.last_activity = time.time() - (IDLE_TIMEOUT_SECONDS + 10)

    # Idle reaper loop must NOT close a BUSY session
    isolated_manager._check_idle_sessions()
    assert sess.status == STATUS_BUSY, "Reaper must not close or touch a STATUS_BUSY session"

    # 2. Concurrent explicit close must block until execute() releases session lock
    close_finished = threading.Event()

    def close_worker():
        isolated_manager.close_connection(sid, reason="concurrent_close")
        close_finished.set()

    t_close = threading.Thread(target=close_worker)
    t_close.start()

    time.sleep(0.05)
    assert not close_finished.is_set(), "close_connection should be blocked waiting for session lock"

    # Allow command to finish
    cmd_can_finish.set()
    t_worker.join(timeout=2.0)
    t_close.join(timeout=2.0)

    assert close_finished.is_set()
    assert cmd_result["res"]["success"] is True
    assert cmd_result["res"]["output"] == "OK:/system identity print"
    assert sess.status == STATUS_CLOSED


# ---------------------------------------------------------------------------
# Test 2: TOCTOU Session Closed Recovery in execute_for_device
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_execute_for_device_recovers_if_session_closed_between_check_and_exec(mock_shell_cls, isolated_manager):
    """
    Test condition: Session is closed right between session_alive check and execute().
    Expected:
    - execute_for_device detects 'Session sudah ditutup.'
    - Performs at most 1 controlled retry by opening a fresh session.
    - Operation succeeds without surfacing the intermediate closed error.
    """
    mock_target = {
        "success": True,
        "name": "R1",
        "host": "192.168.10.2",
        "port": 22,
        "username": "admin",
        "password": "secret",
    }
    with patch.object(isolated_manager, "_resolve_target", return_value=mock_target):
        # Open initial connection
        opened = isolated_manager.open_connection("192.168.10.2", "admin", "secret", device_name="R1")
        initial_sid = opened["session"]["session_id"]

        real_execute = isolated_manager.execute
        first_call = True

        def injected_execute(session_id, command, timeout=25.0):
            nonlocal first_call
            if first_call and session_id == initial_sid:
                first_call = False
                # Inject concurrent closure by reaper
                isolated_manager.close_connection(session_id, reason="simulated_toctou_reap")
            return real_execute(session_id, command, timeout=timeout)

        with patch.object(isolated_manager, "execute", side_effect=injected_execute):
            res = isolated_manager.execute_for_device("R1", "/system identity print")

        assert res["success"] is True
        assert res["output"] == "OUT:/system identity print"
        # Verify a new session was created and initial session remains closed
        new_sid = isolated_manager._host_index[isolated_manager._host_key("192.168.10.2", 22, "admin")]
        assert new_sid != initial_sid
        assert isolated_manager._sessions[initial_sid].status == STATUS_CLOSED


# ---------------------------------------------------------------------------
# Test 3: Eviction of Stale STATUS_ERROR Sessions
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_stale_error_session_is_not_reused_indefinitely(mock_shell_cls, isolated_manager):
    """
    Test condition: A session enters STATUS_ERROR due to an execution failure.
    Expected:
    - Stale reference is evicted from _host_index.
    - Subsequent calls to execute_for_device do not reuse the error session.
    - A healthy session is created and the command succeeds.
    """
    mock_target = {
        "success": True,
        "name": "R2",
        "host": "192.168.10.3",
        "port": 22,
        "username": "admin",
        "password": "secret",
    }
    with patch.object(isolated_manager, "_resolve_target", return_value=mock_target):
        opened = isolated_manager.open_connection("192.168.10.3", "admin", "secret", device_name="R2")
        sid1 = opened["session"]["session_id"]
        sess1 = isolated_manager._sessions[sid1]

        # Force command execution error on sess1
        sess1.shell._alive = False
        with patch.object(isolated_manager, "_reconnect_credentials", return_value={"success": False, "error": "Auth dead"}):
            err_res = isolated_manager.execute(sid1, "/ip address print")
            assert err_res["success"] is False

        assert sess1.status == STATUS_ERROR
        # Verify stale session was immediately evicted from _host_index
        key = isolated_manager._host_key("192.168.10.3", 22, "admin")
        assert isolated_manager._host_index.get(key) is None

        # Next execute_for_device must open a fresh session and succeed
        res = isolated_manager.execute_for_device("R2", "/system identity print")
        assert res["success"] is True
        sid2 = isolated_manager._host_index[key]
        assert sid2 != sid1
        assert isolated_manager._sessions[sid2].status == STATUS_CONNECTED


# ---------------------------------------------------------------------------
# Test 4: Quiescence When Zero Eligible Devices Exist
# ---------------------------------------------------------------------------
def test_nms_polling_cycle_quiescence_with_no_eligible_devices():
    """
    Test condition: NMS poll cycle runs with zero monitored devices in the database.
    Expected:
    - Zero network polls dispatched.
    - last_poll_timestamp and next_poll_timestamp updated properly.
    - _is_polling lock released cleanly.
    """
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(temp_dir.name) / "empty_nms.db"
    create_test_nms_db(db_path)

    engine = NmsEngine(db_path=db_path)

    async def run_test():
        with patch.object(engine, "poll_single_device") as mock_single:
            await engine.poll_all_devices_cycle()
            assert mock_single.call_count == 0
            assert engine.last_poll_timestamp is not None
            assert engine.next_poll_timestamp > engine.last_poll_timestamp
            assert not engine._is_polling

    asyncio.run(run_test())
    temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Test 5: Successful Reconnect Updates connected_at
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_successful_reconnect_updates_connected_at(mock_shell_cls, isolated_manager):
    """
    Test condition: Dropped transport is recovered via automatic reconnection in execute().
    Expected:
    - connected_at is reset to current time.
    - last_activity is updated.
    - status transitions to STATUS_CONNECTED.
    """
    opened = isolated_manager.open_connection("192.168.10.5", "admin", "pass")
    sid = opened["session"]["session_id"]
    sess = isolated_manager._sessions[sid]

    old_connected_at = 1000000.0
    sess.connected_at = old_connected_at
    sess.shell._alive = False  # Mark transport dead

    creds = {"success": True, "host": "192.168.10.5", "port": 22, "username": "admin", "password": "pass"}
    with patch.object(isolated_manager, "_reconnect_credentials", return_value=creds):
        res = isolated_manager.execute(sid, "/system identity print")

    assert res["success"] is True
    assert sess.connected_at > old_connected_at
    assert sess.status == STATUS_CONNECTED
    assert sess.last_error is None


# ---------------------------------------------------------------------------
# Test 6: Failed Reconnect Does Not Reset connected_at
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_failed_reconnect_does_not_reset_connected_at(mock_shell_cls, isolated_manager):
    """
    Test condition: Auto-reconnect fails due to invalid credentials or connection timeout.
    Expected:
    - connected_at is NOT reset.
    - status becomes STATUS_ERROR.
    - Stale reference is evicted from _host_index.
    """
    opened = isolated_manager.open_connection("192.168.10.6", "admin", "pass")
    sid = opened["session"]["session_id"]
    sess = isolated_manager._sessions[sid]

    old_connected_at = 1000000.0
    sess.connected_at = old_connected_at
    sess.shell._alive = False

    creds = {"success": False, "error": "Host unreachable"}
    with patch.object(isolated_manager, "_reconnect_credentials", return_value=creds):
        res = isolated_manager.execute(sid, "/system identity print")

    assert res["success"] is False
    assert sess.connected_at == old_connected_at  # Unchanged
    assert sess.status == STATUS_ERROR

    key = isolated_manager._host_key("192.168.10.6", 22, "admin")
    assert isolated_manager._host_index.get(key) is None


# ---------------------------------------------------------------------------
# Test 7: Every NMS Telemetry Command Passes Through Read-Only Validator
# ---------------------------------------------------------------------------
def test_every_nms_telemetry_command_passes_through_readonly_validator():
    """
    Test condition: NmsEngine._poll_device_routeros_sync interrogates a device.
    Expected:
    - All 5 telemetry commands execute via execute_safe_readonly_command().
    - All 5 commands are validated before reaching connection manager.
    """
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(temp_dir.name) / "nms.db"
    create_test_nms_db(db_path)
    engine = NmsEngine(db_path=db_path)

    mock_inv = MagicMock()
    mock_inv.resolve_ssh.return_value = {
        "success": True,
        "name": "CHR-Core",
        "host": "10.66.38.30",
        "port": 22,
        "username": "admin",
    }

    mock_cm = MagicMock()
    mock_cm.execute_for_device.return_value = {
        "success": True,
        "output": "name: CHR-Core\ncpu-load: 5%\nboard-name: CHR",
    }

    validated_commands = []

    def spy_validator(cm, device_id, command, timeout=10.0):
        validated_commands.append(command)
        return execute_safe_readonly_command(cm, device_id, command, timeout=timeout)

    with patch("core.nms_engine.execute_safe_readonly_command", side_effect=spy_validator):
        engine._poll_device_routeros_sync(
            host="10.66.38.30",
            device_name="CHR-Core",
            conn_mgr=mock_cm,
            inv_store=mock_inv,
        )

    expected_commands = [
        "/system identity print",
        "/system resource print",
        "/system routerboard print",
        "/interface print detail",
        "/interface ethernet print detail",
    ]
    assert validated_commands == expected_commands
    temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Test 8: Rejected NMS Commands Never Reach SSH Execution
# ---------------------------------------------------------------------------
def test_rejected_nms_commands_never_reach_ssh_execution():
    """
    Test condition: An unauthorized or mutating command attempts execution via the NMS validator.
    Expected:
    - Command is rejected immediately by validate_readonly_command.
    - ConnectionManager is NEVER called.
    - Result contains blocked=True.
    """
    mock_cm = MagicMock()
    dangerous_commands = [
        "/system reboot",
        "/interface ethernet set ether1 disabled=yes",
        "/ip route print file=evil.txt",
        "/system identity print where [reboot]",
    ]

    for cmd in dangerous_commands:
        res = execute_safe_readonly_command(mock_cm, "CHR-Core", cmd)
        assert res["success"] is False
        assert res["blocked"] is True
        assert "Security policy violation" in res["error"]

    assert mock_cm.execute_for_device.call_count == 0
    assert mock_cm.execute_command.call_count == 0


# ---------------------------------------------------------------------------
# Test 9: Concurrent Session Cleanup Cannot Evict Newer Valid Session
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_concurrent_session_cleanup_cannot_evict_newer_valid_session(mock_shell_cls, isolated_manager):
    """
    Test condition: Stale error cleanup for session S1 occurs after a newer valid
    session S2 has already been registered for the same host key.
    Expected:
    - S1 cleanup does NOT remove S2 from _host_index.
    - _host_index continues to point to S2.
    """
    opened1 = isolated_manager.open_connection("192.168.10.9", "admin", "pass")
    s1 = opened1["session"]["session_id"]

    # Now open session 2 for same target (force new session by removing from index)
    key = isolated_manager._host_key("192.168.10.9", 22, "admin")
    isolated_manager._host_index.pop(key, None)

    opened2 = isolated_manager.open_connection("192.168.10.9", "admin", "pass")
    s2 = opened2["session"]["session_id"]
    assert s2 != s1
    assert isolated_manager._host_index[key] == s2

    # Now invoke stale eviction on old session S1
    isolated_manager._evict_stale_session(s1)

    # _host_index must still point to s2!
    assert isolated_manager._host_index.get(key) == s2


# ---------------------------------------------------------------------------
# Test 10: Existing Session Reuse Behavior Remains Intact
# ---------------------------------------------------------------------------
@patch("agents.akane.connection_manager.PersistentShell", side_effect=MockShell)
def test_existing_session_reuse_behavior_intact(mock_shell_cls, isolated_manager):
    """
    Test condition: 10 concurrent requests to open the same connection target.
    Expected:
    - Exactly 1 transport creation.
    - Exactly 9 reuses recorded in manager statistics.
    - All return the exact same session_id.
    """
    results = []
    threads = []

    def worker():
        res = isolated_manager.open_connection("192.168.10.10", "admin", "pass")
        results.append(res)

    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 10
    first_sid = results[0]["session"]["session_id"]
    assert all(r["session"]["session_id"] == first_sid for r in results)

    reused_count = sum(1 for r in results if r["reused"] is True)
    created_count = sum(1 for r in results if r["reused"] is False)
    assert created_count == 1
    assert reused_count == 9

    stats = isolated_manager.get_stats()
    assert stats["total_sessions_opened"] == 1
    assert stats["total_sessions_reused"] == 9
