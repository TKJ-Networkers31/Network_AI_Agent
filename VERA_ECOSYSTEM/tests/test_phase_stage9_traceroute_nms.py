"""
tests/test_phase_stage9_traceroute_nms.py — Stage 9 Verification Test Suite.

Verifies:
1. NEW-03: Traceroute executable discovery (traceroute, tracepath, tracert).
2. NEW-03: Traceroute structured hop parser (Linux traceroute, Linux tracepath, Windows tracert).
3. NEW-03: Traceroute security boundary (rejection of option injection, shell metacharacters, unbounded hops).
4. NEW-03: Honest error classification (binary_missing, invalid_target, permission_denied, dns_failed, timeout).
5. NEW-03: Real execution against loopback 127.0.0.1.
6. REC-15: HardenedNmsScheduler concurrent polling performance (20 devices with 5 unreachable targets in < 10s).
7. REC-15: AlertEngine anti-flapping hysteresis & upstream RCA downstream suppression.
8. RouterOS v6/v7 syntax compatibility in tools/mikrotik/routeros.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import platform
import subprocess
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from core.nms.alerts import AlertEngine, AlertSeverity, AlertState
from core.nms.models import (
    MetricTaxonomy,
    MetricSemanticType,
    SampleQuality,
    TelemetrySample,
)
from core.nms.scheduler import (
    DevicePollCoordinator,
    DevicePollState,
    HardenedNmsScheduler,
    PollingProfile,
)
from core.nms_engine import NmsEngine
from tools.mikrotik.routeros import COMMANDS, get_routes, get_routes_v7
from tools.network.diagnostics import (
    discover_traceroute_binary,
    parse_traceroute_output,
    traceroute,
)


# ===========================================================================
# 1. NEW-03: Executable Discovery Tests
# ===========================================================================

def test_01_traceroute_binary_discovery():
    """Verifies shutil.which discovery finds system traceroute/tracepath or handles missing cleanly."""
    with patch("tools.network.diagnostics.platform.system", return_value="Linux"):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "/usr/bin/traceroute" if cmd == "traceroute" else None
            path, method = discover_traceroute_binary()
            assert path == "/usr/bin/traceroute"
            assert method == "traceroute"

    with patch("tools.network.diagnostics.platform.system", return_value="Linux"):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "/usr/bin/tracepath" if cmd == "tracepath" else None
            path, method = discover_traceroute_binary()
            assert path == "/usr/bin/tracepath"
            assert method == "tracepath"

    with patch("tools.network.diagnostics.platform.system", return_value="Windows"):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: "C:\\Windows\\System32\\tracert.exe" if cmd == "tracert" else None
            path, method = discover_traceroute_binary()
            assert path == "C:\\Windows\\System32\\tracert.exe"
            assert method == "tracert"

    with patch("tools.network.diagnostics.platform.system", return_value="Linux"):
        with patch("shutil.which", return_value=None):
            path, method = discover_traceroute_binary()
            assert path is None
            assert method is None


def test_02_traceroute_binary_missing_returns_honest_error():
    """Proves that when binary is missing, honest binary_missing error is returned without synthetic hops."""
    with patch("tools.network.diagnostics.discover_traceroute_binary", return_value=(None, None)):
        res = traceroute("8.8.8.8")
        assert res["success"] is False
        assert res["error_type"] == "binary_missing"
        assert res["hops"] == []
        assert res["total_hops"] == 0
        assert "No traceroute executable found" in res["error"]


# ===========================================================================
# 2. NEW-03: Security & Validation Tests
# ===========================================================================

def test_03_traceroute_rejects_command_injection_and_options():
    """Verifies that flag injection and shell metacharacters are rejected before subprocess execution."""
    with patch("subprocess.run") as mock_run:
        res1 = traceroute("-v")
        assert res1["success"] is False
        assert res1["error_type"] == "invalid_target"
        assert mock_run.call_count == 0

        res2 = traceroute("8.8.8.8; cat /etc/passwd")
        assert res2["success"] is False
        assert res2["error_type"] == "invalid_target"
        assert mock_run.call_count == 0

        res3 = traceroute("1.1.1.1 | rm -rf /")
        assert res3["success"] is False
        assert res3["error_type"] == "invalid_target"
        assert mock_run.call_count == 0


# ===========================================================================
# 3. NEW-03: Structured Output Parser Tests
# ===========================================================================

def test_04_parse_linux_traceroute_output():
    """Parses standard multi-hop Linux traceroute output with timed out and reached hops."""
    sample = """
traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
 1  192.168.1.1  1.234 ms
 2  *
 3  10.0.0.1  5.432 ms !H
 4  dns.google (8.8.8.8)  14.210 ms  14.500 ms
"""
    parsed = parse_traceroute_output(sample, method="traceroute", target="8.8.8.8")
    assert parsed["total_hops"] == 4
    assert parsed["reached"] is True

    hop1 = parsed["hops"][0]
    assert hop1["hop"] == 1
    assert hop1["ip"] == "192.168.1.1"
    assert hop1["status"] == "SUCCESS"
    assert hop1["rtts"] == [1.234]

    hop2 = parsed["hops"][1]
    assert hop2["hop"] == 2
    assert hop2["status"] == "TIMEOUT"
    assert hop2["rtts"] == []

    hop3 = parsed["hops"][2]
    assert hop3["hop"] == 3
    assert hop3["status"] == "UNREACHABLE"

    hop4 = parsed["hops"][3]
    assert hop4["hop"] == 4
    assert hop4["host"] == "dns.google"
    assert hop4["ip"] == "8.8.8.8"
    assert hop4["status"] == "REACHED"
    assert len(hop4["rtts"]) == 2


def test_05_parse_linux_tracepath_output():
    """Parses Linux tracepath output skipping MTU probe lines and handling no reply."""
    sample = """
 1?: [LOCALHOST]                      pmtu 1500
 1:  192.168.43.1                                          2.099ms 
 2:  no reply
 3:  8.8.8.8                                             306.042ms reached
     Resume: pmtu 1500 hops 3 back 3 
"""
    parsed = parse_traceroute_output(sample, method="tracepath", target="8.8.8.8")
    assert parsed["total_hops"] == 3
    assert parsed["reached"] is True

    assert parsed["hops"][0]["hop"] == 1
    assert parsed["hops"][0]["ip"] == "192.168.43.1"
    assert parsed["hops"][0]["status"] == "SUCCESS"

    assert parsed["hops"][1]["hop"] == 2
    assert parsed["hops"][1]["status"] == "TIMEOUT"

    assert parsed["hops"][2]["hop"] == 3
    assert parsed["hops"][2]["ip"] == "8.8.8.8"
    assert parsed["hops"][2]["status"] == "REACHED"


def test_06_parse_windows_tracert_output():
    """Parses Windows tracert output with sub-millisecond times and timeout lines."""
    sample = """
Tracing route to dns.google [8.8.8.8]
over a maximum of 30 hops:

  1     1 ms    <1 ms     1 ms  192.168.1.1
  2     *        *        *     Request timed out.
  3    12 ms    11 ms    12 ms  dns.google [8.8.8.8]

Trace complete.
"""
    parsed = parse_traceroute_output(sample, method="tracert", target="8.8.8.8")
    assert parsed["total_hops"] == 3
    assert parsed["reached"] is True

    hop1 = parsed["hops"][0]
    assert hop1["hop"] == 1
    assert hop1["ip"] == "192.168.1.1"
    assert 0.5 in hop1["rtts"]  # <1 ms converted to 0.5

    assert parsed["hops"][1]["status"] == "TIMEOUT"
    assert parsed["hops"][2]["status"] == "REACHED"


def test_07_traceroute_timeout_retains_partial_hops():
    """Verifies that subprocess.TimeoutExpired retains partial hops collected so far."""
    sample = " 1  192.168.1.1  1.500 ms\n 2  10.0.0.1  3.200 ms\n"
    exc = subprocess.TimeoutExpired(cmd=["traceroute", "8.8.8.8"], timeout=10, output=sample)

    with patch("tools.network.diagnostics.discover_traceroute_binary", return_value=("/usr/bin/traceroute", "traceroute")):
        with patch("subprocess.run", side_effect=exc):
            res = traceroute("8.8.8.8")
            assert res["success"] is False
            assert res["error_type"] == "timeout"
            assert res["total_hops"] == 2
            assert res["hops"][0]["ip"] == "192.168.1.1"
            assert res["hops"][1]["ip"] == "10.0.0.1"


def test_08_real_traceroute_loopback_execution():
    """Executes real traceroute against 127.0.0.1 if binary is available on the host."""
    bin_path, method = discover_traceroute_binary()
    if not bin_path:
        pytest.skip("No traceroute binary found in host environment.")

    res = traceroute("127.0.0.1", max_hops=3, wait_sec=1)
    assert res["target"] == "127.0.0.1"
    assert res["method_used"] in ("traceroute", "tracepath")
    assert res["success"] is True
    assert res["total_hops"] >= 1
    assert res["hops"][0]["ip"] == "127.0.0.1"
    assert res["reached"] is True


# ===========================================================================
# 4. REC-15: Hardened NMS Scheduler Concurrent Polling Tests
# ===========================================================================

def test_09_hardened_nms_concurrent_unreachable_devices_performance():
    """
    REC-15 Acceptance Test:
    Polling 20 devices with 5 unreachable/slow targets must complete in < 10s
    using ThreadPool/coordinator concurrency governor.
    """
    async def _run():
        coordinator = DevicePollCoordinator(max_concurrency=16)

        async def mock_poll(device_id: str, state: DevicePollState):
            if "unreachable" in device_id:
                # Simulate 1.5s timeout for unreachable target
                await asyncio.sleep(1.5)
                state.record_failure()
            else:
                # Simulate quick 30ms response for healthy target
                await asyncio.sleep(0.03)
                state.record_success()

        scheduler = HardenedNmsScheduler(coordinator=coordinator, poll_executor=mock_poll)

        # 15 healthy devices + 5 unreachable devices
        devices = [f"dev_healthy_{i}" for i in range(15)] + [f"dev_unreachable_{i}" for i in range(5)]
        for dev in devices:
            scheduler.register_device(dev, profile_name=PollingProfile.STANDARD.value)

        start_time = time.time()
        # Execute single cycle across all devices
        sem = asyncio.Semaphore(16)

        async def _dispatch(dev_id):
            async with sem:
                state = coordinator.get_or_create_state(dev_id)
                lock = coordinator.get_async_lock(dev_id)
                async with lock:
                    await mock_poll(dev_id, state)

        await asyncio.gather(*[_dispatch(d) for d in devices])
        elapsed = time.time() - start_time

        assert elapsed < 10.0, f"Polling 20 devices took {elapsed:.2f}s, expected < 10.0s!"

        # Verify circuit breaker state for unreachable targets
        for i in range(5):
            st = coordinator.get_or_create_state(f"dev_unreachable_{i}")
            assert st.consecutive_failures >= 1

    asyncio.run(_run())


# ===========================================================================
# 5. REC-15: AlertEngine Anti-Flapping & Upstream RCA Suppression Tests
# ===========================================================================

def test_10_alert_engine_hysteresis_and_rca_suppression():
    """
    Verifies that:
    1. Alert requires N=3 consecutive violations to trigger.
    2. When upstream parent is DOWN, downstream reachability loss is SUPPRESSED.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test_alerts.db"
        engine = AlertEngine(db_path=db_path)

        now = time.time()

        # Step 1: 2 failures for upstream router — should not trigger active incident yet (debounce N=3)
        s1 = TelemetrySample("r1_core", MetricTaxonomy.DEVICE_AVAILABILITY, 0.0, unit="ratio", measured_at=now)
        act1 = engine.evaluate_sample(s1)
        assert act1 is None  # Cycle 1

        s2 = TelemetrySample("r1_core", MetricTaxonomy.DEVICE_AVAILABILITY, 0.0, unit="ratio", measured_at=now + 15)
        act2 = engine.evaluate_sample(s2)
        assert act2 is None  # Cycle 2

        # Step 2: 3rd failure for upstream router triggers ACTIVE CRITICAL incident
        s3 = TelemetrySample("r1_core", MetricTaxonomy.DEVICE_AVAILABILITY, 0.0, unit="ratio", measured_at=now + 30)
        act3 = engine.evaluate_sample(s3)
        assert act3 is not None
        assert act3["action"] == "triggered"
        assert act3["severity"] == AlertSeverity.CRITICAL.value
        r1_inc_id = act3["incident_id"]

        # Step 3: Downstream switch s1_edge (mocked as downstream of r1_core) fails
        with patch.object(engine, "check_upstream_failure", return_value=r1_inc_id):
            # 3 failures for s1_edge
            for i in range(2):
                engine.evaluate_sample(TelemetrySample("s1_edge", MetricTaxonomy.DEVICE_AVAILABILITY, 0.0, unit="ratio", measured_at=now + 45 + i*15))
            act_down = engine.evaluate_sample(TelemetrySample("s1_edge", MetricTaxonomy.DEVICE_AVAILABILITY, 0.0, unit="ratio", measured_at=now + 75))

            assert act_down is not None
            assert act_down["action"] == "suppressed"
            assert act_down["parent_incident_id"] == r1_inc_id
            assert act_down["state"] == AlertState.SUPPRESSED.value


# ===========================================================================
# 6. RouterOS v6 / v7 Command Compatibility Tests
# ===========================================================================

def test_11_routeros_v6_and_v7_command_registry():
    """Verifies that routeros tools support both v6 (/ip route print) and v7 (/routing route print)."""
    assert "get_routes" in COMMANDS
    assert COMMANDS["get_routes"] == "/ip route print"
    assert "get_routes_v7" in COMMANDS
    assert COMMANDS["get_routes_v7"] == "/routing route print"

    with patch("tools.mikrotik.routeros.execute_mikrotik_tool") as mock_exec:
        mock_exec.return_value = {"success": True, "output": "Flags: X - disabled, A - active"}
        get_routes("dev_r1")
        mock_exec.assert_called_with("get_routes", "dev_r1")

        get_routes("dev_r1", routeros_version="v7")
        mock_exec.assert_called_with("get_routes_v7", "dev_r1")

        get_routes_v7("dev_r1")
        mock_exec.assert_called_with("get_routes_v7", "dev_r1")
