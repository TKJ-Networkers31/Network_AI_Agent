"""
tests/test_networking_iii_metrics.py — Unit tests for Phase Networking III NMS Metrics Service.
"""

import time
import pytest
from pathlib import Path
from core.network_intelligence.metrics_service import (
    NmsHistoricalMetricsService,
    NormalizedDeviceMetric,
    NormalizedInterfaceMetric,
    MetricAnomaly,
)


@pytest.fixture
def temp_metrics_service(tmp_path: Path):
    db_file = tmp_path / "test_topology.db"
    return NmsHistoricalMetricsService(db_path=db_file)


def test_device_metric_ingestion_and_query(temp_metrics_service):
    svc = temp_metrics_service
    now = time.time()

    for i in range(10):
        svc.ingest_device_metric(NormalizedDeviceMetric(
            device_id="Router-1",
            timestamp=now - (10 - i) * 60,
            cpu_load_percent=10.0 + i * 2,
            memory_used_percent=50.0,
            uptime_seconds=3600 + i * 60,
            latency_ms=2.5 + i * 0.1,
        ))

    history = svc.query_device_metrics_history(device_id="Router-1")
    assert len(history) == 10
    assert history[0]["cpu_load_percent"] == 10.0
    assert history[-1]["cpu_load_percent"] == 28.0

    # Downsampling test
    sampled = svc.query_device_metrics_history(device_id="Router-1", downsample_points=3)
    assert len(sampled) == 3
    assert sampled[0]["timestamp"] == history[0]["timestamp"]
    assert sampled[-1]["timestamp"] == history[-1]["timestamp"]


def test_interface_metric_ingestion_and_query(temp_metrics_service):
    svc = temp_metrics_service
    now = time.time()

    svc.ingest_interface_metric(NormalizedInterfaceMetric(
        device_id="Router-1",
        interface_name="ether1",
        timestamp=now,
        rx_rate_bps=1000000.0,
        tx_rate_bps=500000.0,
        in_errors=2,
        out_errors=0,
    ))

    history = svc.query_interface_metrics_history(device_id="Router-1", interface_name="ether1")
    assert len(history) == 1
    assert history[0]["rx_rate_bps"] == 1000000.0
    assert history[0]["in_errors"] == 2


def test_prune_expired_metrics(temp_metrics_service):
    svc = temp_metrics_service
    now = time.time()
    old_time = now - (10 * 86400)  # 10 days ago

    svc.ingest_device_metric(NormalizedDeviceMetric(
        device_id="Router-Old",
        timestamp=old_time,
        cpu_load_percent=5.0,
    ))
    svc.ingest_device_metric(NormalizedDeviceMetric(
        device_id="Router-New",
        timestamp=now,
        cpu_load_percent=15.0,
    ))

    deleted = svc.prune_expired_metrics(retention_days=7)
    assert deleted == 1

    remaining = svc.query_device_metrics_history(device_id="Router-Old")
    assert len(remaining) == 0

    new_metrics = svc.query_device_metrics_history(device_id="Router-New")
    assert len(new_metrics) == 1


def test_anomaly_detection_and_cross_device_correlation(temp_metrics_service):
    svc = temp_metrics_service
    t_event = time.time() - 30

    # Device A has CPU critical
    svc.ingest_device_metric(NormalizedDeviceMetric(
        device_id="Core-1",
        timestamp=t_event,
        cpu_load_percent=98.5,
        latency_ms=3.0,
    ))

    # Device B has latency spike at t_event + 5s
    svc.ingest_device_metric(NormalizedDeviceMetric(
        device_id="Edge-2",
        timestamp=t_event + 5,
        cpu_load_percent=20.0,
        latency_ms=350.0,
    ))

    anomalies = svc.detect_anomalies(device_ids=["Core-1", "Edge-2"], window_seconds=300)
    assert len(anomalies) >= 2

    types = {a.metric_type for a in anomalies}
    assert "cpu" in types
    assert "latency" in types

    correlated = svc.correlate_metric_anomalies(anomalies, temporal_window_sec=30.0)
    assert len(correlated) >= 1
    assert correlated[0]["event_type"] == "CROSS_DEVICE_METRIC_CORRELATION"
    assert correlated[0]["device_1"] in ("Core-1", "Edge-2")
    assert correlated[0]["device_2"] in ("Core-1", "Edge-2")
