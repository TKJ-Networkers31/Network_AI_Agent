"""
tests/test_audit_b_nms_ws_polling.py — Controlled Evidence Tests for Audit B (NMS, WebSocket, and Polling).
"""

import asyncio
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.nms_engine import NmsEngine
from core.nms_models import determine_device_availability, NMS_STATUS_VALUES


@pytest.fixture
def isolated_nms():
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(temp_dir.name) / "test_nms.db"

    # Pre-create topology_nodes schema in test database
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE topology_nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            identity TEXT,
            ip TEXT,
            mac TEXT,
            device_type TEXT DEFAULT 'router',
            ownership_status TEXT DEFAULT 'verified_owned',
            reachability_status TEXT DEFAULT 'online',
            pos_x REAL DEFAULT 0.0,
            pos_y REAL DEFAULT 0.0,
            last_seen REAL
        );
        INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type)
        VALUES ('router_test', 'MikroTik R1', 'R1-Core', '192.168.1.1', '48:8F:5A:11:22:33', 'router');
        """
    )
    conn.commit()
    conn.close()

    engine = NmsEngine(db_path=db_path)
    yield engine
    engine.stop_monitoring()
    temp_dir.cleanup()


def test_audit_b_single_flight_poll_cycle_concurrency(isolated_nms):
    """
    Test condition: Trigger poll_all_devices_cycle twice simultaneously.
    Expected:
    - Single-flight lock (_is_polling) prevents overlapping execution.
    - Exactly 1 cycle executes; the second call is skipped safely.
    """
    async def run_test():
        execution_count = 0

        async def slow_poll(*args, **kwargs):
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)

        with patch.object(isolated_nms, "poll_single_device", side_effect=slow_poll):
            task1 = asyncio.create_task(isolated_nms.poll_all_devices_cycle())
            task2 = asyncio.create_task(isolated_nms.poll_all_devices_cycle())

            await asyncio.gather(task1, task2)
            assert execution_count == 1

    asyncio.run(run_test())


def test_audit_b_monitoring_failure_distinguishable_from_device_failure():
    """
    Test condition: Verify state machine cleanly separates:
    - ping unreachable -> DOWN
    - ping reachable but management unavailable -> MONITORING_UNAVAILABLE
    """
    # 1. Device is reachable (ping_ok=True) but management check failed (management_ok=False) on managed device
    st1, fail1, succ1 = determine_device_availability(
        current_status="UP",
        consecutive_failures=0,
        consecutive_successes=5,
        ping_ok=True,
        management_ok=False,
        is_managed=True,
        failure_threshold=3,
    )
    assert st1 == "MONITORING_UNAVAILABLE"

    # 2. Device ping fails (ping_ok=False) >= failure_threshold (3)
    st2, fail2, succ2 = determine_device_availability(
        current_status="UP",
        consecutive_failures=2,
        consecutive_successes=0,
        ping_ok=False,
        management_ok=None,
        is_managed=True,
        failure_threshold=3,
    )
    assert st2 == "DOWN"
    assert fail2 == 3


def test_audit_b_websocket_bridge_integration():
    """
    Test condition: Connect to /ws/nms WebSocket endpoint via Starlette TestClient.
    Verify snapshot message received on initial connection with overview metrics.
    """
    from starlette.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/nms") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "nms_snapshot"
            assert "overview" in data["data"]
            assert "is_running" in data["data"]
            overview = data["data"]["overview"]
            assert "total_devices" in overview
            assert "up" in overview
            assert "down" in overview
    except Exception as exc:
        pytest.fail(f"WebSocket /ws/nms connection failed: {exc}")
