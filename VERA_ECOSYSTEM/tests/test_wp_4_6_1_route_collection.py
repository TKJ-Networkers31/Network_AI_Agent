"""
WP 4.6.1 Acceptance Test Suite — Multi-Device Route Collection Integration.

Verifies:
1. Single-device collection with CanonicalDevice provenance
2. Multi-device concurrent collection
3. RouterOS v6 and v7 real-device fixture compatibility
4. Single device unavailable (partial fleet preservation)
5. Multiple devices unavailable
6. Partial / truncated route collection handling
7. Duplicate overlapping collection prevention & duplicate route deduplication
8. Per-device timeout & transient retry backoff
9. Cancellation via threading.Event and job_id
10. Parser failure & RouterOS CLI error handling
11. Routing table / VRF preservation
12. Device identity & management IP collision detection
13. Bounded concurrency limit enforcement
14. Read-only command boundary, unauthorized target rejection, and REST API contracts
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from core.canonical_network import CanonicalDevice, CanonicalNetworkRegistry
from core.network_intelligence.command_execution import (
    CommandExecutionRequest,
    CommandExecutionResult,
    ExecutionStatus,
    UnifiedCommandExecutor,
)
from core.routing.route_collector import (
    MultiDeviceRouteCollector,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.unified_route_parser import UnifiedRouteParser

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "routes"


def _load_fixture(rel_path: str) -> str:
    return (FIXTURE_ROOT / rel_path).read_text(encoding="utf-8")


class FakeRegistry(CanonicalNetworkRegistry):
    def __init__(self, devices: List[CanonicalDevice]):
        super().__init__()
        self._devices = {d.device_id: d for d in devices}

    def list_devices(self, force_refresh: bool = False) -> List[CanonicalDevice]:
        return list(self._devices.values())

    def resolve_device(self, query: str) -> Optional[CanonicalDevice]:
        q = (query or "").strip().lower()
        if not q:
            return None
        for dev in self._devices.values():
            if q in (
                dev.device_id.lower(),
                dev.inventory_name.lower(),
                dev.observed_identity.lower(),
                dev.management_ip.lower(),
            ):
                return dev
        return None


def _make_devices() -> List[CanonicalDevice]:
    return [
        CanonicalDevice(
            device_id="dev_chr",
            inventory_name="CHR",
            observed_identity="CHR-Core",
            management_ip="10.66.38.30",
            device_type="mikrotik",
            platform="CHR x86_64",
            os_version="7.23.8",
            ros_major_version=7,
            is_managed=True,
        ),
        CanonicalDevice(
            device_id="dev_r-1",
            inventory_name="R-1",
            observed_identity="R1-Branch",
            management_ip="192.168.0.1",
            device_type="mikrotik",
            platform="hAP ac lite",
            os_version="6.49.18",
            ros_major_version=6,
            is_managed=True,
        ),
        CanonicalDevice(
            device_id="dev_edge",
            inventory_name="Edge-1",
            observed_identity="Edge-GW",
            management_ip="10.0.0.254",
            device_type="mikrotik",
            platform="CCR2004",
            os_version="7.16.2",
            ros_major_version=7,
            is_managed=True,
        ),
    ]


def test_01_single_device_collection_canonical_provenance():
    v7_detail = _load_fixture("routeros_v7/raw/ip_route_detail.txt")
    registry = FakeRegistry(_make_devices())
    cm = MagicMock()
    cm.execute_command.return_value = {"success": True, "output": v7_detail}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    res = collector.collect_device_routes("CHR")

    assert res.status == RouteCollectionStatus.SUCCESS.value
    assert res.completeness == RouteCompleteness.COMPLETE.value
    assert res.device_id == "dev_chr"
    assert res.device_identity == "CHR-Core"
    assert res.router_os_version == "7.23.8"
    assert res.ros_major_version == 7
    assert res.parser_version == "4.6.0"
    assert res.source_command == "/ip route print detail"
    assert res.route_count > 0
    assert all(r.device_id == "dev_chr" for r in res.routes)
    assert all(r.evidence_provenance.get("evidence_id") == res.evidence_id for r in res.routes)


def test_02_multi_device_and_v6_v7_compatibility():
    v7_detail = _load_fixture("routeros_v7/raw/ip_route_detail.txt")
    v6_detail = _load_fixture("routeros_v6/raw/ip_route_detail.txt")
    registry = FakeRegistry(_make_devices()[:2])

    def _exec_side_effect(command: str, device_name: str, timeout: float = 15.0):
        if device_name == "CHR":
            return {"success": True, "output": v7_detail}
        if device_name == "R-1":
            return {"success": True, "output": v6_detail}
        return {"success": False, "error": "Unknown device"}

    cm = MagicMock()
    cm.execute_command.side_effect = _exec_side_effect
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(targets=["CHR", "R-1"], max_concurrency=2)

    assert report.status == RouteCollectionStatus.SUCCESS.value
    assert report.successful_devices == 2
    assert report.failed_devices == 0
    assert report.results["dev_chr"].ros_major_version == 7
    assert report.results["dev_r-1"].ros_major_version == 6
    assert report.results["dev_chr"].route_count > 0
    assert report.results["dev_r-1"].route_count > 0


def test_03_one_device_unavailable_preserves_healthy_results():
    v7_detail = _load_fixture("routeros_v7/raw/ip_route_detail.txt")
    registry = FakeRegistry(_make_devices()[:2])

    def _exec_side_effect(command: str, device_name: str, timeout: float = 15.0):
        if device_name == "CHR":
            return {"success": True, "output": v7_detail}
        return {"success": False, "error": "SSH connection refused: host unreachable"}

    cm = MagicMock()
    cm.execute_command.side_effect = _exec_side_effect
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(targets=["CHR", "R-1"], max_retries=0)

    assert report.status == RouteCollectionStatus.PARTIAL.value
    assert report.successful_devices == 1
    assert report.failed_devices == 1
    assert report.results["dev_chr"].status == RouteCollectionStatus.SUCCESS.value
    assert report.results["dev_r-1"].status == RouteCollectionStatus.UNREACHABLE.value
    assert report.results["dev_r-1"].completeness == RouteCompleteness.UNREACHABLE.value


def test_04_multiple_devices_unavailable():
    registry = FakeRegistry(_make_devices())
    cm = MagicMock()
    cm.execute_command.return_value = {"success": False, "error": "No route to host"}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(max_retries=0)

    assert report.status == RouteCollectionStatus.FAILED.value
    assert report.successful_devices == 0
    assert report.failed_devices == 3
    for res in report.results.values():
        assert res.status == RouteCollectionStatus.UNREACHABLE.value
        assert res.route_count == 0


def test_05_partial_truncated_collection():
    raw_truncated = (
        "Flags: D - dynamic; A - active; c - connect, s - static\n"
        " 0  As   dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n"
        "[truncated]\n"
    )
    registry = FakeRegistry(_make_devices()[:1])
    cm = MagicMock()
    cm.execute_command.return_value = {"success": True, "output": raw_truncated}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    res = collector.collect_device_routes("CHR")

    assert res.status == RouteCollectionStatus.PARTIAL.value
    assert res.completeness == RouteCompleteness.PARTIAL.value
    assert res.route_count == 1
    assert any("truncated" in w.lower() for w in res.warnings)


def test_06_duplicate_overlapping_collection_prevention_and_route_dedup():
    raw_with_dup = (
        "Flags: D - dynamic; A - active; s - static\n"
        " 0  As   dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n"
        " 1  As   dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n"
        " 2  As   dst-address=10.20.0.0/24 gateway=10.0.0.2 distance=1\n"
    )
    registry = FakeRegistry(_make_devices()[:1])
    entered = threading.Event()
    proceed = threading.Event()
    ssh_calls = 0
    ssh_lock = threading.Lock()

    def _slow_exec(command: str, device_name: str, timeout: float = 15.0):
        nonlocal ssh_calls
        with ssh_lock:
            ssh_calls += 1
        entered.set()
        proceed.wait(timeout=3.0)
        return {"success": True, "output": raw_with_dup}

    cm = MagicMock()
    cm.execute_command.side_effect = _slow_exec
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    first_holder: Dict[str, object] = {}

    def _run_first():
        first_holder["res"] = collector.collect_device_routes("CHR")

    t1 = threading.Thread(target=_run_first)
    t1.start()
    assert entered.wait(timeout=2.0)

    # Concurrent second call for the SAME device while first is active
    second_res = collector.collect_device_routes("CHR")
    proceed.set()
    t1.join(timeout=3.0)

    first_res = first_holder["res"]
    assert ssh_calls == 1, "Overlapping SSH collection for same device must be prevented!"
    assert second_res.duplicate_prevented is True
    assert second_res.status == RouteCollectionStatus.SKIPPED_DUPLICATE.value
    assert first_res.route_count == 2  # duplicate 0.0.0.0/0 entry deduplicated


def test_07_timeout_and_transient_retry_backoff():
    registry = FakeRegistry(_make_devices()[:1])
    attempts = 0

    def _flaky_exec(command: str, device_name: str, timeout: float = 15.0):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {"success": False, "error": "SSH socket timed out"}
        return {
            "success": True,
            "output": "Flags: A - active, s - static\n 0  As dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n",
        }

    cm = MagicMock()
    cm.execute_command.side_effect = _flaky_exec
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    res = collector.collect_device_routes("CHR", max_retries=1, backoff_base_sec=0.05)
    assert attempts == 2
    assert res.retries_used == 1
    assert res.status == RouteCollectionStatus.SUCCESS.value

    # Persistent timeout
    cm.execute_command.side_effect = None
    cm.execute_command.return_value = {"success": False, "error": "Command timed out after 5s"}
    res_to = collector.collect_device_routes("CHR", timeout_sec=1.0, max_retries=0)
    assert res_to.status == RouteCollectionStatus.TIMEOUT.value
    assert res_to.completeness == RouteCompleteness.UNREACHABLE.value


def test_08_cancellation_via_event_and_job_id():
    registry = FakeRegistry(_make_devices())
    cancel_evt = threading.Event()
    cancel_evt.set()

    cm = MagicMock()
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(
        targets=["CHR", "R-1"],
        cancel_event=cancel_evt,
    )
    assert report.cancelled is True
    assert report.status == RouteCollectionStatus.CANCELLED.value
    assert cm.execute_command.call_count == 0


def test_09_parser_failure_and_cli_error_handling():
    registry = FakeRegistry(_make_devices()[:1])
    cm = MagicMock()
    cm.execute_command.return_value = {"success": True, "output": "bad command name route (line 1 column 5)"}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    res_cli_err = collector.collect_device_routes("CHR")
    assert res_cli_err.status == RouteCollectionStatus.FAILED.value
    assert res_cli_err.completeness == RouteCompleteness.FAILED.value

    # Force parser runtime exception
    broken_parser = MagicMock(spec=UnifiedRouteParser)
    broken_parser.parse_with_report.side_effect = RuntimeError("corrupt frame")
    cm.execute_command.return_value = {"success": True, "output": "0 As dst-address=0.0.0.0/0 gateway=1.1.1.1"}
    collector_broken = MultiDeviceRouteCollector(
        registry=registry, command_executor=executor, parser=broken_parser
    )
    res_exc = collector_broken.collect_device_routes("CHR")
    assert res_exc.status == RouteCollectionStatus.FAILED.value
    assert any("corrupt frame" in e for e in res_exc.errors)


def test_10_routing_table_vrf_preservation():
    raw_vrf = (
        "Flags: D - dynamic; A - active; c - connect, s - static\n"
        " 0  As   dst-address=0.0.0.0/0 routing-table=main gateway=10.0.0.1 distance=1\n"
        " 1  As   dst-address=0.0.0.0/0 routing-table=vrf_customer_a gateway=172.16.10.1 distance=1\n"
        " 2  DAC  dst-address=192.168.50.0/24 routing-table=vrf_mgmt gateway=ether5 distance=0\n"
    )
    registry = FakeRegistry(_make_devices()[:1])
    cm = MagicMock()
    cm.execute_command.return_value = {"success": True, "output": raw_vrf}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    res = collector.collect_device_routes("CHR")
    assert res.status == RouteCollectionStatus.SUCCESS.value
    assert res.routing_tables == ["main", "vrf_customer_a", "vrf_mgmt"]

    vrf_filtered = res.to_dict(routing_table="vrf_customer_a")
    assert vrf_filtered["filtered_route_count"] == 1
    assert vrf_filtered["routes"][0]["gateway"] == "172.16.10.1"


def test_11_device_identity_and_ip_collision_detection():
    colliding_devs = [
        CanonicalDevice(
            device_id="dev_a",
            inventory_name="RouterA",
            observed_identity="Dup-Identity",
            management_ip="10.0.0.10",
            is_managed=True,
            ros_major_version=7,
        ),
        CanonicalDevice(
            device_id="dev_b",
            inventory_name="RouterB",
            observed_identity="Dup-Identity",
            management_ip="10.0.0.10",
            is_managed=True,
            ros_major_version=7,
        ),
    ]
    registry = FakeRegistry(colliding_devs)
    cm = MagicMock()
    cm.execute_command.return_value = {
        "success": True,
        "output": "Flags: A - active, s - static\n 0  As dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n",
    }
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(targets=["dev_a", "dev_b"])
    assert len(report.identity_collisions) >= 2
    assert report.results["dev_a"].identity_collision is True
    assert report.results["dev_a"].status == RouteCollectionStatus.PARTIAL.value


def test_12_bounded_concurrency_limit_enforced():
    devs = [
        CanonicalDevice(
            device_id=f"dev_r{i}",
            inventory_name=f"R{i}",
            observed_identity=f"R{i}",
            management_ip=f"10.99.0.{i}",
            is_managed=True,
            ros_major_version=7,
        )
        for i in range(1, 7)
    ]
    registry = FakeRegistry(devs)
    active_workers = 0
    peak_workers = 0
    w_lock = threading.Lock()

    def _measured_exec(command: str, device_name: str, timeout: float = 15.0):
        nonlocal active_workers, peak_workers
        with w_lock:
            active_workers += 1
            peak_workers = max(peak_workers, active_workers)
        time.sleep(0.06)
        with w_lock:
            active_workers -= 1
        return {
            "success": True,
            "output": "Flags: A - active, s - static\n 0  As dst-address=0.0.0.0/0 gateway=10.99.0.254 distance=1\n",
        }

    cm = MagicMock()
    cm.execute_command.side_effect = _measured_exec
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    report = collector.collect_multi_device_routes(max_concurrency=2)
    assert report.successful_devices == 6
    assert peak_workers <= 2, f"Concurrency exceeded limit 2 (observed peak={peak_workers})"


def test_13_readonly_boundary_and_unauthorized_scope_enforcement():
    devs = _make_devices()
    # Add an unmanaged third-party ISP node — must NEVER be interrogated via SSH
    devs.append(
        CanonicalDevice(
            device_id="topo_isp_pe",
            inventory_name="",
            observed_identity="ISP-PE",
            management_ip="203.0.113.1",
            is_managed=False,
        )
    )
    registry = FakeRegistry(devs)
    cm = MagicMock()
    cm.execute_command.return_value = {
        "success": True,
        "output": "Flags: A - active, s - static\n 0  As dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1\n",
    }
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)

    # Attempt to collect from unmanaged ISP device & arbitrary external IP
    report = collector.collect_multi_device_routes(targets=["topo_isp_pe", "8.8.8.8", "CHR"])
    assert "topo_isp_pe" in report.unresolved_targets
    assert "8.8.8.8" in report.unresolved_targets
    assert list(report.results.keys()) == ["dev_chr"]

    # Verify UnifiedCommandExecutor blocks any write command
    bad_req = CommandExecutionRequest(device_id="CHR", command_str="/ip route add dst-address=0.0.0.0/0 gateway=1.1.1.1")
    bad_res = executor.execute(bad_req)
    assert bad_res.execution_status == ExecutionStatus.SECURITY_REJECTED


def test_14_route_collection_api_endpoints_and_secret_redaction(monkeypatch):
    from api.main import app
    import core.routing.route_collector as rc_mod

    v7_detail = _load_fixture("routeros_v7/raw/ip_route_detail.txt")
    registry = FakeRegistry(_make_devices()[:1])
    cm = MagicMock()
    cm.execute_command.return_value = {"success": True, "output": v7_detail}
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    test_collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)
    monkeypatch.setattr(rc_mod, "_route_collector_singleton", test_collector)

    from tests.auth_helper import get_test_auth_headers
    client = TestClient(app, headers=get_test_auth_headers())

    # Trigger collection
    resp = client.post("/api/intelligence/routes/collect", json={"targets": ["CHR"], "max_concurrency": 2})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["report"]["summary"]["successful_devices"] == 1
    assert "password" not in str(payload).lower()

    # Check status endpoint
    st_resp = client.get("/api/intelligence/routes/status")
    assert st_resp.status_code == 200
    assert st_resp.json()["status"]["cached_devices_count"] == 1

    # Check per-device route retrieval
    dev_resp = client.get("/api/intelligence/routes/dev_chr?active_only=true&limit=10")
    assert dev_resp.status_code == 200
    assert dev_resp.json()["device_routes"]["device_id"] == "dev_chr"
    assert len(dev_resp.json()["device_routes"]["routes"]) <= 10
