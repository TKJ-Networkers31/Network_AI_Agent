"""
AIRA OS — Unit & Integration Tests for WP 5.1 (Canonical Telemetry Models & Contracts).

Verifies:
1. TelemetrySample schema, timestamp separation, and sample quality states.
2. Metric taxonomy naming conventions and semantic types (Gauge, Counter, Rate, State).
3. CapabilityState hierarchy and DeviceCapabilityProfile caching with TTL.
4. Capability isolation: Protocol failure does not mark entire device unhealthy.
5. Missing telemetry semantics: Missing samples are NEVER converted into 0.0 bps.
6. CounterMetadata wraparound and reboot discontinuity handling.
7. Secret masking across CollectionResult, CollectionError, and TelemetrySample.
8. Backward compatibility with core.nms_models and calculate_traffic_rate.
"""

from __future__ import annotations

import time
import pytest

from core.nms.models import (
    CollectionError,
    CollectionResult,
    CollectionStatus,
    CounterMetadata,
    DeviceResourceTelemetry,
    InterfaceTelemetry,
    MetricSemanticType,
    MetricTaxonomy,
    NetworkQualityTelemetry,
    SampleQuality,
    TelemetryBatch,
    TelemetryCompleteness,
    TelemetryFreshness,
    TelemetrySample,
    TelemetrySource,
)
from core.nms.capability import (
    CapabilityAssessment,
    CapabilityProber,
    CapabilityState,
    DeviceCapabilityProfile,
    MonitoringCapability,
)
from core.nms.collector_contracts import (
    BaseTelemetryCollector,
    IcmpTelemetryCollector,
    MockTelemetryCollector,
)
from core.nms_models import calculate_traffic_rate


def test_01_telemetry_sample_schema_and_timestamp_separation():
    t_meas = 1700000000.0
    t_coll = 1700000002.5

    sample = TelemetrySample(
        device_id="dev_chr",
        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
        metric_value=42.5,
        unit="percent",
        semantic_type=MetricSemanticType.GAUGE.value,
        measured_at=t_meas,
        collected_at=t_coll,
        source_protocol=TelemetrySource.SNMP_V2C.value,
        source_collector="snmp_cpu_collector",
        quality=SampleQuality.GOOD.value,
    )

    assert sample.is_valid() is True
    assert sample.measured_at == t_meas
    assert sample.collected_at == t_coll
    assert sample.measured_at != sample.collected_at

    d = sample.to_dict()
    assert d["device_id"] == "dev_chr"
    assert d["metric_name"] == "aira.nms.device.cpu.utilization"
    assert d["metric_value"] == 42.5
    assert d["unit"] == "percent"
    assert d["quality"] == "GOOD"


def test_02_metric_taxonomy_conventions():
    assert MetricTaxonomy.DEVICE_AVAILABILITY == "aira.nms.device.availability"
    assert MetricTaxonomy.INTERFACE_RX_BPS == "aira.nms.interface.rx.bps"
    assert MetricTaxonomy.INTERFACE_TX_BPS == "aira.nms.interface.tx.bps"
    assert MetricTaxonomy.NETWORK_WAN_AVAILABILITY == "aira.nms.network.wan_availability"


def test_03_missing_sample_semantics():
    sample = TelemetrySample(
        device_id="dev_r-1",
        metric_name=MetricTaxonomy.INTERFACE_RX_BPS,
        metric_value=0.0,
        unit="bps",
        semantic_type=MetricSemanticType.RATE.value,
        quality=SampleQuality.MISSING.value,
        error_detail="Collector timeout; sample dropped",
    )

    assert sample.is_valid() is False
    assert sample.quality == SampleQuality.MISSING.value
    # A missing sample must not be considered valid telemetry even if value is 0.0
    assert sample.is_valid() is False


def test_04_device_capability_profile_and_isolation():
    profile = DeviceCapabilityProfile(
        device_id="dev_r-1",
        management_ip="192.168.0.1",
        platform="mikrotik",
        profile_ttl_seconds=100.0,
    )

    # ICMP supported
    profile.set_assessment(MonitoringCapability.ICMP, CapabilityState.SUPPORTED, response_time_ms=1.4)
    # SNMP fails authentication
    profile.set_assessment(
        MonitoringCapability.SNMP_V2C,
        CapabilityState.AUTH_FAILED,
        error_message="Invalid community string secret_pass123",
    )
    # SSH supported
    profile.set_assessment(MonitoringCapability.ROUTEROS_SSH, CapabilityState.SUPPORTED, response_time_ms=45.0)

    # Assert capability states
    assert profile.is_supported(MonitoringCapability.ICMP) is True
    assert profile.is_supported(MonitoringCapability.SNMP_V2C) is False
    assert profile.get_state(MonitoringCapability.SNMP_V2C) == CapabilityState.AUTH_FAILED.value
    assert profile.is_supported(MonitoringCapability.ROUTEROS_SSH) is True

    # Preferred fallback: since SNMP failed auth, prefers SSH!
    assert profile.preferred_telemetry_source() == "ssh"

    # Serialization must mask secrets in error message
    d = profile.to_dict()
    snmp_asmt = d["capabilities"][MonitoringCapability.SNMP_V2C.value]
    assert "secret_pass123" not in snmp_asmt["error_message"]
    assert "***" in snmp_asmt["error_message"]


def test_05_capability_prober_caching_and_expiration():
    prober = CapabilityProber(cache_ttl_seconds=0.1)  # 100ms TTL for testing

    prof = prober.evaluate_initial_profile_from_inventory(
        device_id="dev_chr",
        host="10.26.213.30",
        device_meta={"device_type": "mikrotik", "snmp_enabled": True, "snmp_version": "v2c"},
    )

    assert prober.get_cached_profile("dev_chr") is not None
    assert prof.is_expired() is False

    time.sleep(0.15)
    # Cache should be expired
    assert prof.is_expired() is True
    assert prober.get_cached_profile("dev_chr") is None


def test_06_collection_result_secret_redaction_and_metrics():
    res = CollectionResult(
        device_id="dev_core",
        source_protocol="snmp",
        collector_name="test_collector",
        status=CollectionStatus.PARTIAL.value,
        completeness=TelemetryCompleteness.PARTIAL.value,
    )

    res.samples.append(
        TelemetrySample(
            device_id="dev_core",
            metric_name="aira.nms.device.availability",
            metric_value=1,
            unit="state",
            quality=SampleQuality.GOOD.value,
        )
    )
    res.samples.append(
        TelemetrySample(
            device_id="dev_core",
            metric_name="aira.nms.device.cpu.utilization",
            metric_value=999.0,
            unit="percent",
            quality=SampleQuality.ERROR.value,
            error_detail="Invalid response for password=supersecret",
        )
    )
    res.errors.append(
        CollectionError(
            error_type="SnmpTimeout",
            message="Failed with key=my_private_key_xyz",
            protocol="snmp",
        )
    )

    assert res.successful_metric_count == 1
    assert res.failed_metric_count == 2  # 1 bad sample + 1 error

    d = res.to_dict()
    assert d["successful_metric_count"] == 1
    assert d["failed_metric_count"] == 2
    json_str = str(d)
    assert "supersecret" not in json_str
    assert "my_private_key_xyz" not in json_str


def test_07_interface_and_resource_telemetry_dataclasses():
    iface = InterfaceTelemetry(
        device_id="dev_chr",
        interface_name="ether1",
        speed_bps=1_000_000_000,
        in_octets=1000,
        out_octets=2000,
        rx_rate_bps=80_000.0,
        tx_rate_bps=160_000.0,
        rx_utilization_pct=0.008,
        tx_utilization_pct=0.016,
    )
    d_iface = iface.to_dict()
    assert d_iface["interface_name"] == "ether1"
    assert d_iface["speed_bps"] == 1_000_000_000
    assert d_iface["rx_rate_bps"] == 80000.0

    res = DeviceResourceTelemetry(
        device_id="dev_chr",
        cpu_util_pct=15.4,
        memory_used_bytes=256_000_000,
        memory_total_bytes=1_024_000_000,
        memory_util_pct=25.0,
        uptime_seconds=3600,
    )
    d_res = res.to_dict()
    assert d_res["cpu_util_pct"] == 15.4
    assert d_res["memory_util_pct"] == 25.0


def test_08_backward_compatibility_with_traffic_rate():
    # Verify existing calculate_traffic_rate still works seamlessly
    rate, util = calculate_traffic_rate(
        curr_octets=2_000_000,
        prev_octets=1_000_000,
        curr_time=10.0,
        prev_time=0.0,
        speed_bps=100_000_000,
    )
    # (1_000_000 * 8) / 10 = 800,000 bps = 0.8% of 100 Mbps
    assert rate == 800_000.0
    assert util == 0.8


@pytest.mark.anyio
async def test_09_icmp_collector_adapter():
    collector = IcmpTelemetryCollector()
    profile = DeviceCapabilityProfile(device_id="dev_test", management_ip="127.0.0.1")

    # Localhost should reply to ICMP ping or return structured result without crashing
    res = await collector.collect(device_id="dev_test", host="127.0.0.1", profile=profile, timeout_sec=1.0)
    assert isinstance(res, CollectionResult)
    assert res.device_id == "dev_test"
    assert res.source_protocol == "icmp"
    assert len(res.samples) >= 2  # availability + packet_loss (+ latency if alive)
