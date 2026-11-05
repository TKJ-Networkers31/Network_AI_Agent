"""
AIRA OS — Networking V WP 5.4 Test Suite
Time-Series Metrics Pipeline, Batch Writer & Multi-Tier Retention Verification.
"""

import asyncio
import sqlite3
import time
from pathlib import Path
import pytest

from core.nms.models import (
    MetricSemanticType,
    MetricTaxonomy,
    SampleQuality,
    TelemetrySample,
    TelemetrySource,
)
from core.nms.metrics_store import (
    MetricsBatchWriter,
    RollupEngine,
    init_metrics_tables,
    query_metrics,
)


@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test_topology.db"
    init_metrics_tables(db_file)
    return db_file


def test_01_schema_initialization_and_indexes(test_db_path):
    """Verify that tables and performance indexes are created idempotently."""
    conn = sqlite3.connect(test_db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "nms_raw_metrics" in tables
    assert "nms_5m_rollups" in tables
    assert "nms_1h_rollups" in tables

    indexes = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
    assert "idx_nms_raw_query" in indexes
    assert "idx_nms_5m_unique" in indexes
    assert "idx_nms_1h_unique" in indexes
    conn.close()


@pytest.mark.anyio
async def test_02_metrics_batch_writer_lifecycle_and_drain(test_db_path):
    """Verify in-memory queue buffering, atomic flush, and operational metrics."""
    writer = MetricsBatchWriter(db_path=test_db_path, flush_interval_sec=0.1, max_batch_size=100)
    now = time.time()

    samples = [
        TelemetrySample(
            device_id="dev_batch_1",
            metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
            metric_value=float(10 + i),
            unit="percent",
            semantic_type=MetricSemanticType.GAUGE.value,
            measured_at=now + i,
            collected_at=now + i,
            source_protocol=TelemetrySource.ROUTEROS_SSH.value,
            quality=SampleQuality.GOOD.value,
        )
        for i in range(25)
    ]

    enqueued = await writer.enqueue_samples(samples)
    assert enqueued == 25
    assert writer.queue_depth == 25

    flushed = await writer.flush_now()
    assert flushed == 25
    assert writer.queue_depth == 0
    assert writer.total_samples_written == 25
    assert writer.total_batches_flushed == 1
    assert writer.last_flush_latency_ms > 0.0

    conn = sqlite3.connect(test_db_path)
    count = conn.execute("SELECT count(*) FROM nms_raw_metrics WHERE device_id='dev_batch_1'").fetchone()[0]
    conn.close()
    assert count == 25


def test_03_bounded_queue_saturation_protection(test_db_path):
    """Verify non-blocking sample dropping when queue capacity is reached."""
    writer = MetricsBatchWriter(db_path=test_db_path, queue_maxsize=5)
    now = time.time()

    for i in range(5):
        sample = TelemetrySample(
            device_id="dev_drop",
            metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
            metric_value=float(i),
            unit="percent",
            semantic_type=MetricSemanticType.GAUGE.value,
            measured_at=now,
            collected_at=now,
        )
        assert writer.enqueue_sample_nowait(sample) is True

    # 6th sample exceeds bounded capacity
    overflow_sample = TelemetrySample(
        device_id="dev_drop",
        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
        metric_value=99.0,
        unit="percent",
        semantic_type=MetricSemanticType.GAUGE.value,
        measured_at=now,
        collected_at=now,
    )
    assert writer.enqueue_sample_nowait(overflow_sample) is False
    assert writer.queue_depth == 5


def test_04_rollup_engine_5m_aggregation(test_db_path):
    """Verify mathematical aggregation of raw samples into 5-minute buckets."""
    conn = sqlite3.connect(test_db_path)
    # Bucket 1: timestamp 0 to 240 (5 samples: 10, 20, 30, 40, 50)
    for i, val in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
        conn.execute(
            """
            INSERT INTO nms_raw_metrics (
                device_id, interface_name, metric_name, metric_value,
                unit, semantic_type, source_protocol, quality, measured_at, collected_at
            ) VALUES ('dev_1', 'ether1', 'aira.nms.interface.rx.bps', ?, 'bps', 'rate', 'snmp', 'good', ?, ?);
            """,
            (val, 60.0 * i, 60.0 * i),
        )
    conn.commit()
    conn.close()

    engine = RollupEngine(db_path=test_db_path)
    engine.aggregate_5m_rollups(cutoff_time=500.0)

    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nms_5m_rollups WHERE device_id='dev_1'").fetchone()
    conn.close()

    assert row is not None
    assert row["bucket_start"] == 0.0
    assert row["avg_value"] == 30.0  # (10+20+30+40+50)/5
    assert row["min_value"] == 10.0
    assert row["max_value"] == 50.0
    assert row["sample_count"] == 5


def test_05_rollup_engine_1h_aggregation(test_db_path):
    """Verify mathematical rollup of 5-minute buckets into 1-hour buckets."""
    conn = sqlite3.connect(test_db_path)
    # Insert twelve 5-minute buckets covering 3600 seconds (0 to 3300s)
    for b in range(12):
        b_time = float(b * 300)
        conn.execute(
            """
            INSERT INTO nms_5m_rollups (
                device_id, interface_name, metric_name, bucket_start,
                avg_value, min_value, max_value, sample_count, created_at
            ) VALUES ('dev_1', 'ether1', 'aira.nms.interface.rx.bps', ?, 100.0, 80.0, 120.0, 20, ?);
            """,
            (b_time, b_time + 300),
        )
    conn.commit()
    conn.close()

    engine = RollupEngine(db_path=test_db_path)
    engine.aggregate_1h_rollups(cutoff_time=4000.0)

    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nms_1h_rollups WHERE device_id='dev_1'").fetchone()
    conn.close()

    assert row is not None
    assert row["bucket_start"] == 0.0
    assert row["avg_value"] == 100.0
    assert row["min_value"] == 80.0
    assert row["max_value"] == 120.0
    assert row["sample_count"] == 240  # 12 * 20


def test_06_chunked_retention_pruning(test_db_path):
    """Verify non-blocking chunked deletion across all 3 retention tiers."""
    now = 10_000_000.0
    conn = sqlite3.connect(test_db_path)

    # 1. Raw samples: 5 expired (> 48h = 172,800s ago), 2 fresh
    for i in range(5):
        conn.execute(
            """
            INSERT INTO nms_raw_metrics (device_id, metric_name, metric_value, unit, semantic_type, source_protocol, quality, measured_at, collected_at)
            VALUES ('dev_p', 'm1', 1.0, 'u', 'g', 'p', 'good', ?, ?);
            """,
            (now - 200_000.0 + i, now - 200_000.0 + i),
        )
    for i in range(2):
        conn.execute(
            """
            INSERT INTO nms_raw_metrics (device_id, metric_name, metric_value, unit, semantic_type, source_protocol, quality, measured_at, collected_at)
            VALUES ('dev_p', 'm1', 1.0, 'u', 'g', 'p', 'good', ?, ?);
            """,
            (now - 1000.0 + i, now - 1000.0 + i),
        )

    # 2. 5m rollups: 4 expired (> 30d = 2,592,000s ago), 1 fresh
    for i in range(4):
        conn.execute(
            """
            INSERT INTO nms_5m_rollups (device_id, metric_name, bucket_start, avg_value, min_value, max_value, sample_count, created_at)
            VALUES ('dev_p', 'm1', ?, 1.0, 1.0, 1.0, 10, ?);
            """,
            (now - 3_000_000.0 + i * 300, now),
        )
    conn.execute(
        """
        INSERT INTO nms_5m_rollups (device_id, metric_name, bucket_start, avg_value, min_value, max_value, sample_count, created_at)
        VALUES ('dev_p', 'm1', ?, 1.0, 1.0, 1.0, 10, ?);
        """,
        (now - 5000.0, now),
    )

    conn.commit()
    conn.close()

    engine = RollupEngine(db_path=test_db_path)
    # Prune with chunk_size = 2 to verify multi-chunk loop
    stats = engine.prune_expired_metrics(now=now, chunk_size=2)

    assert stats["raw_pruned"] == 5
    assert stats["rollups_5m_pruned"] == 4

    conn = sqlite3.connect(test_db_path)
    raw_left = conn.execute("SELECT count(*) FROM nms_raw_metrics WHERE device_id='dev_p'").fetchone()[0]
    r5m_left = conn.execute("SELECT count(*) FROM nms_5m_rollups WHERE device_id='dev_p'").fetchone()[0]
    conn.close()

    assert raw_left == 2  # Only the 2 fresh remain
    assert r5m_left == 1  # Only the 1 fresh remains


def test_07_downsampled_query_resolution_selector(test_db_path):
    """Verify auto-resolution selection and explicit step overrides."""
    now = time.time()

    # 1. Window <= 6 hours -> raw tier
    res_raw = query_metrics("dev_q", "m1", start_time=now - 3600, end_time=now, db_path=test_db_path)
    assert res_raw["resolution"] == "raw"

    # 2. 6 hours < Window <= 7 days -> 5m tier
    res_5m = query_metrics("dev_q", "m1", start_time=now - 86400 * 2, end_time=now, db_path=test_db_path)
    assert res_5m["resolution"] == "5m"

    # 3. Window > 7 days -> 1h tier
    res_1h = query_metrics("dev_q", "m1", start_time=now - 86400 * 14, end_time=now, db_path=test_db_path)
    assert res_1h["resolution"] == "1h"

    # 4. Explicit override step="raw"
    res_override = query_metrics("dev_q", "m1", start_time=now - 86400 * 14, end_time=now, step="raw", db_path=test_db_path)
    assert res_override["resolution"] == "raw"


def test_08_api_query_endpoint():
    """Verify FastAPI /api/nms/metrics/query endpoint execution."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get(
        "/api/nms/metrics/query",
        params={
            "device_id": "dev_test",
            "metric_name": "aira.nms.device.cpu.utilization",
            "step": "raw",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["device_id"] == "dev_test"
    assert data["metric_name"] == "aira.nms.device.cpu.utilization"
    assert "resolution" in data
    assert "points" in data
