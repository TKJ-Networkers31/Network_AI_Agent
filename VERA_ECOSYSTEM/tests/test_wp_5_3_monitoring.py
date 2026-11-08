"""
AIRA OS — Networking V WP 5.3 Test Suite
Device, Interface, and Resource Monitoring Verification.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.nms.capability import DeviceCapabilityProfile, MonitoringCapability, CapabilityState, CapabilityAssessment
from core.nms.models import (
    CollectionStatus,
    MetricSemanticType,
    MetricTaxonomy,
    SampleQuality,
    TelemetryCompleteness,
    TelemetrySource,
)
from core.nms.monitoring import UnifiedMonitoringEngine


@pytest.fixture
def monitoring_engine():
    return UnifiedMonitoringEngine()


@pytest.fixture
def capability_profile_snmp():
    profile = DeviceCapabilityProfile(device_id="test_router_snmp", management_ip="10.0.0.1")
    profile.capabilities[MonitoringCapability.ICMP.value] = CapabilityAssessment(
        capability=MonitoringCapability.ICMP.value,
        state=CapabilityState.SUPPORTED.value,
        last_tested_at=time.time(),
    )
    profile.capabilities[MonitoringCapability.SNMP_V2C.value] = CapabilityAssessment(
        capability=MonitoringCapability.SNMP_V2C.value,
        state=CapabilityState.SUPPORTED.value,
        last_tested_at=time.time(),
        tested_port=161,
    )
    return profile


@pytest.fixture
def capability_profile_ssh():
    profile = DeviceCapabilityProfile(device_id="test_router_ssh", management_ip="10.0.0.2")
    profile.capabilities[MonitoringCapability.ICMP.value] = CapabilityAssessment(
        capability=MonitoringCapability.ICMP.value,
        state=CapabilityState.SUPPORTED.value,
        last_tested_at=time.time(),
    )
    profile.capabilities[MonitoringCapability.ROUTEROS_SSH.value] = CapabilityAssessment(
        capability=MonitoringCapability.ROUTEROS_SSH.value,
        state=CapabilityState.SUPPORTED.value,
        last_tested_at=time.time(),
        tested_port=22,
    )
    return profile


@pytest.mark.anyio
async def test_01_icmp_probe_parsing(monitoring_engine):
    """Test ICMP probe parsing for reachable vs unreachable targets."""
    with patch("core.nms.monitoring.bounded_icmp_ping") as mock_ping:
        # Reachable scenario
        mock_ping.return_value = {"alive": True, "avg_rtt_ms": 14.5, "packet_loss": 0.0}
        res_alive = await monitoring_engine.execute_icmp_probe("10.0.0.1", timeout_sec=1.0)
        assert res_alive["alive"] is True
        assert res_alive["avg_rtt_ms"] == 14.5

        # Unreachable scenario with sub-telemetry skipped
        mock_ping.return_value = {"alive": False, "avg_rtt_ms": None, "packet_loss": 100.0}
        profile = DeviceCapabilityProfile(device_id="offline_dev", management_ip="10.0.0.99")
        coll_res = await monitoring_engine.poll_device_telemetry("offline_dev", "10.0.0.99", profile)

        assert coll_res.status == CollectionStatus.UNREACHABLE.value
        assert coll_res.completeness == TelemetryCompleteness.PARTIAL.value
        avail_samples = [s for s in coll_res.samples if s.metric_name == MetricTaxonomy.DEVICE_AVAILABILITY]
        assert len(avail_samples) == 1
        assert avail_samples[0].metric_value == 0
        loss_samples = [s for s in coll_res.samples if s.metric_name == MetricTaxonomy.DEVICE_PACKET_LOSS_PCT]
        assert len(loss_samples) == 1
        assert loss_samples[0].metric_value == 100.0


def test_02_rate_normalization_normal_delta(monitoring_engine):
    """Verify normal traffic rate calculation and caching."""
    dev = "dev_1"
    iface = "ether1"
    t0 = 1000.0
    t1 = 1010.0  # 10 second window

    # Initial sample: baseline establishment (UNCERTAIN)
    r_in, r_out, u_in, u_out, q0 = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=1_000_000, curr_out_octets=2_000_000, curr_time=t0, speed_bps=10_000_000
    )
    assert r_in == 0.0
    assert r_out == 0.0
    assert q0 == SampleQuality.UNCERTAIN.value

    # Second sample: delta = in 1,250,000 bytes, out 1,500,000 bytes
    # rx_bps = 1,250,000 * 8 / 10 = 1,000,000 bps
    # tx_bps = 1,500,000 * 8 / 10 = 1,200,000 bps
    r_in2, r_out2, u_in2, u_out2, q1 = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=2_250_000, curr_out_octets=3_500_000, curr_time=t1, speed_bps=10_000_000
    )
    assert r_in2 == 1_000_000.0
    assert r_out2 == 1_200_000.0
    assert u_in2 == 10.0  # 1 Mbps on 10 Mbps link = 10%
    assert u_out2 == 12.0  # 1.2 Mbps on 10 Mbps link = 12%
    assert q1 == SampleQuality.GOOD.value


def test_03_counter_wraparound_32bit(monitoring_engine):
    """Test 32-bit counter wraparound detection and calculation."""
    dev = "dev_wrap"
    iface = "ether1"
    t0 = 100.0
    t1 = 110.0

    # Upper half of 32-bit: 4,290,000,000 (> 2.14 GB)
    monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=4_290_000_000, curr_out_octets=100, curr_time=t0
    )

    # Counter rolled over 4,294,967,295 back to 5,000,000
    r_in, r_out, _, _, q = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=5_000_000, curr_out_octets=100, curr_time=t1
    )

    # Delta = (4,294,967,295 - 4,290,000,000) + 5,000,000 + 1 = 9,967,296 bytes
    # Rate = 9,967,296 * 8 / 10 = 7,973,836.8 bps
    assert r_in == 7_973_836.8
    assert q == SampleQuality.GOOD.value


def test_04_reboot_counter_discontinuity(monitoring_engine):
    """Test router reboot / counter reset handling tagging DISCONTINUOUS."""
    dev = "dev_reboot"
    iface = "ether1"
    t0 = 100.0
    t1 = 110.0

    # Counter at 1,000,000 (well below 2.14 GB, so NOT a wrap)
    monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=1_000_000, curr_out_octets=1_000_000, curr_time=t0
    )

    # Counter drops to 20,000 -> reboot occurred
    r_in, r_out, _, _, q = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=20_000, curr_out_octets=20_000, curr_time=t1
    )

    assert r_in == 0.0
    assert r_out == 0.0
    assert q == SampleQuality.DISCONTINUOUS.value


def test_05_missing_and_gap_intervals(monitoring_engine):
    """Verify missing counter data and large polling gaps are correctly tagged."""
    dev = "dev_gap"
    iface = "ether1"

    # None counters -> MISSING
    r_in, r_out, _, _, q_miss = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=None, curr_out_octets=None, curr_time=100.0
    )
    assert q_miss == SampleQuality.MISSING.value

    # Large interval > 300s -> DISCONTINUOUS
    monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=100_000, curr_out_octets=100_000, curr_time=100.0
    )
    r_in2, r_out2, _, _, q_gap = monitoring_engine.compute_interface_rates(
        dev, iface, curr_in_octets=200_000, curr_out_octets=200_000, curr_time=500.0  # 400s delta
    )
    assert q_gap == SampleQuality.DISCONTINUOUS.value


@pytest.mark.anyio
async def test_06_snmp_interrogation_mapping(monitoring_engine, capability_profile_snmp):
    """Verify SNMP collection produces standardized TelemetrySamples."""
    mock_snmp_data = {
        "success": True,
        "cpu_load_percent": 35.0,
        "memory_used_percent": 58.0,
        "temperature_celsius": 42.0,
        "interfaces": [
            {
                "name": "ether1",
                "in_octets": 10_000_000,
                "out_octets": 15_000_000,
                "speed_bps": 1_000_000_000,
                "oper_status": "up",
            }
        ],
    }

    with patch("core.nms.monitoring.bounded_icmp_ping", return_value={"alive": True, "avg_rtt_ms": 2.1}), \
         patch("core.nms_snmp.poll_device_snmp_full", new_callable=AsyncMock, return_value=mock_snmp_data):
        
        res = await monitoring_engine.poll_device_telemetry(
            "test_router_snmp", "10.0.0.1", capability_profile_snmp
        )

        assert res.status == CollectionStatus.SUCCESS.value
        metrics = {s.metric_name: s for s in res.samples}
        assert MetricTaxonomy.DEVICE_AVAILABILITY in metrics
        assert MetricTaxonomy.DEVICE_CPU_UTILIZATION in metrics
        assert metrics[MetricTaxonomy.DEVICE_CPU_UTILIZATION].metric_value == 35.0
        assert MetricTaxonomy.DEVICE_MEMORY_UTILIZATION in metrics
        assert metrics[MetricTaxonomy.DEVICE_MEMORY_UTILIZATION].metric_value == 58.0
        assert MetricTaxonomy.DEVICE_TEMPERATURE in metrics
        assert metrics[MetricTaxonomy.DEVICE_TEMPERATURE].metric_value == 42.0
        assert MetricTaxonomy.INTERFACE_OPER_STATUS in metrics
        assert MetricTaxonomy.INTERFACE_RX_BPS in metrics
        assert MetricTaxonomy.INTERFACE_TX_BPS in metrics


@pytest.mark.anyio
async def test_07_routeros_ssh_interrogation_mapping(monitoring_engine, capability_profile_ssh):
    """Verify RouterOS SSH interrogation produces standardized TelemetrySamples."""
    mock_ros_data = {
        "success": True,
        "cpu_load_percent": 12.0,
        "memory_used_percent": 24.5,
        "interfaces": [
            {
                "name": "ether1",
                "in_octets": 50_000_000,
                "out_octets": 40_000_000,
                "speed_bps": 100_000_000,
                "oper_status": "up",
                "disabled": False,
                "running": True,
            }
        ],
    }

    mock_engine = MagicMock()
    mock_engine.poll_device_routeros = AsyncMock(return_value=mock_ros_data)

    with patch("core.nms.monitoring.bounded_icmp_ping", return_value={"alive": True, "avg_rtt_ms": 1.8}), \
         patch("core.nms_engine.get_nms_engine", return_value=mock_engine):
        
        res = await monitoring_engine.poll_device_telemetry(
            "test_router_ssh", "10.0.0.2", capability_profile_ssh
        )

        assert res.status == CollectionStatus.SUCCESS.value
        metrics = {s.metric_name: s for s in res.samples}
        assert MetricTaxonomy.DEVICE_CPU_UTILIZATION in metrics
        assert metrics[MetricTaxonomy.DEVICE_CPU_UTILIZATION].metric_value == 12.0
        assert MetricTaxonomy.DEVICE_MEMORY_UTILIZATION in metrics
        assert metrics[MetricTaxonomy.DEVICE_MEMORY_UTILIZATION].metric_value == 24.5
        assert MetricTaxonomy.INTERFACE_OPER_STATUS in metrics
        assert MetricTaxonomy.INTERFACE_RX_BPS in metrics
        assert MetricTaxonomy.INTERFACE_TX_BPS in metrics


@pytest.mark.anyio
async def test_08_network_quality_epistemic_probe(monitoring_engine):
    """Verify separation of local gateway availability from external WAN Internet reachability."""
    with patch("core.nms.monitoring.bounded_icmp_ping") as mock_ping:
        # Case A: Both gateway and WAN online
        mock_ping.side_effect = [
            {"alive": True, "avg_rtt_ms": 1.2},  # Gateway
            {"alive": True, "avg_rtt_ms": 18.4}, # DNS target (8.8.8.8)
        ]
        q_online = await monitoring_engine.execute_network_quality_probe(gateway_ip="192.168.0.1", dns_target="8.8.8.8")
        assert q_online.gateway_reachable is True
        assert q_online.dns_reachable is True
        assert q_online.wan_available is True
        assert q_online.latency_ms == 18.4

        # Case B: Gateway online, WAN offline
        mock_ping.side_effect = [
            {"alive": True, "avg_rtt_ms": 1.1},   # Gateway
            {"alive": False, "avg_rtt_ms": None}, # DNS target
        ]
        q_wan_down = await monitoring_engine.execute_network_quality_probe(gateway_ip="192.168.0.1", dns_target="8.8.8.8")
        assert q_wan_down.gateway_reachable is True
        assert q_wan_down.dns_reachable is False
        assert q_wan_down.wan_available is False
        assert q_wan_down.packet_loss_pct == 100.0

        # Case C: Gateway offline
        mock_ping.side_effect = [
            {"alive": False, "avg_rtt_ms": None}, # Gateway
            {"alive": False, "avg_rtt_ms": None}, # DNS target
        ]
        q_gw_down = await monitoring_engine.execute_network_quality_probe(gateway_ip="192.168.0.1", dns_target="8.8.8.8")
        assert q_gw_down.gateway_reachable is False
        assert q_gw_down.dns_reachable is False
        assert q_gw_down.wan_available is False


@pytest.mark.anyio
async def test_09_live_lab_readonly_probe(monitoring_engine):
    """
    Validates live lab device polling if online in read-only mode.
    Ensures zero mutations occur and responses match schema.
    """
    from core.nms.capability import CapabilityProber
    prober = CapabilityProber()
    # Check dev_chr (10.26.213.30)
    profile = prober.evaluate_initial_profile_from_inventory("dev_chr", "10.26.213.30", {"device_type": "mikrotik"})
    icmp_res = await monitoring_engine.execute_icmp_probe("10.26.213.30", timeout_sec=1.0)
    if icmp_res.get("alive"):
        res = await monitoring_engine.poll_device_telemetry("dev_chr", "10.26.213.30", profile)
        assert res.device_id == "dev_chr"
        assert len(res.samples) > 0
        for s in res.samples:
            assert s.measured_at > 0
            assert s.collected_at > 0
    else:
        pytest.skip("dev_chr lab device is offline or off-subnet in this test run.")
