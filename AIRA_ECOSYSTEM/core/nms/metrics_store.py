"""
AIRA OS — Networking V Time-Series Metrics Pipeline & Multi-Tier Retention Engine (WP 5.4).

Provides high-throughput batched ingestion, downsampling rollups, and multi-tier
SQLite WAL retention for NMS telemetry:
1. MetricsBatchWriter: In-memory bounded queue with 1,000 ms micro-batch flushes.
2. Multi-tier SQLite schema:
   - Tier 1: nms_raw_metrics (10-15s resolution, 48h retention)
   - Tier 2: nms_5m_rollups (5m resolution, 30d retention)
   - Tier 3: nms_1h_rollups (1h resolution, 365d retention)
3. Non-blocking chunked retention pruner (deletions in chunks of 5,000).
4. Auto-resolving downsampled query engine.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.nms.models import TelemetrySample
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    get_topology_connection,
    init_topology_database,
    topology_transaction,
)

logger = logging.getLogger("aira.nms.metrics_store")


def init_metrics_tables(db_path: Optional[Path | str] = None) -> None:
    """
    Idempotently creates the unified NMS time-series tables and performance indexes.
    """
    resolved_path = Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH
    init_topology_database(resolved_path)

    with topology_transaction(resolved_path, write=True) as conn:
        # Tier 1: Raw Unaggregated Telemetry Samples
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nms_raw_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                interface_name TEXT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                semantic_type TEXT NOT NULL,
                source_protocol TEXT NOT NULL,
                quality TEXT NOT NULL,
                measured_at REAL NOT NULL,
                collected_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_raw_query ON nms_raw_metrics(device_id, metric_name, measured_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_raw_iface ON nms_raw_metrics(device_id, interface_name, metric_name, measured_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_raw_cleanup ON nms_raw_metrics(measured_at);"
        )

        # Tier 2: 5-Minute Rollups
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nms_5m_rollups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                interface_name TEXT,
                metric_name TEXT NOT NULL,
                bucket_start REAL NOT NULL,
                avg_value REAL NOT NULL,
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_nms_5m_unique 
            ON nms_5m_rollups(device_id, coalesce(interface_name, ''), metric_name, bucket_start);
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_5m_query ON nms_5m_rollups(device_id, metric_name, bucket_start);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_5m_cleanup ON nms_5m_rollups(bucket_start);"
        )

        # Tier 3: 1-Hour Rollups
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nms_1h_rollups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                interface_name TEXT,
                metric_name TEXT NOT NULL,
                bucket_start REAL NOT NULL,
                avg_value REAL NOT NULL,
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_nms_1h_unique 
            ON nms_1h_rollups(device_id, coalesce(interface_name, ''), metric_name, bucket_start);
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_1h_query ON nms_1h_rollups(device_id, metric_name, bucket_start);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nms_1h_cleanup ON nms_1h_rollups(bucket_start);"
        )


class MetricsBatchWriter:
    """
    High-throughput micro-batching writer that buffers TelemetrySamples in an
    in-memory queue and commits them in atomic SQLite transactions.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        flush_interval_sec: float = 1.0,
        max_batch_size: int = 250,
        queue_maxsize: int = 10_000,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH
        self.flush_interval_sec = flush_interval_sec
        self.max_batch_size = max_batch_size
        self._queue: asyncio.Queue[TelemetrySample] = asyncio.Queue(maxsize=queue_maxsize)
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Operational metrics
        self.total_samples_written: int = 0
        self.total_batches_flushed: int = 0
        self.last_flush_latency_ms: float = 0.0

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    def enqueue_sample_nowait(self, sample: TelemetrySample) -> bool:
        """Non-blocking sample enqueue. Drops sample if queue is saturated."""
        try:
            self._queue.put_nowait(sample)
            return True
        except asyncio.QueueFull:
            logger.warning("MetricsBatchWriter queue full (%d); sample dropped.", self._queue.maxsize)
            return False

    async def enqueue_sample(self, sample: TelemetrySample) -> bool:
        return self.enqueue_sample_nowait(sample)

    async def enqueue_samples(self, samples: Sequence[TelemetrySample]) -> int:
        enqueued = 0
        for s in samples:
            if self.enqueue_sample_nowait(s):
                enqueued += 1
        return enqueued

    async def start(self) -> None:
        """Starts the background batch flush loop."""
        if self.is_running:
            return
        init_metrics_tables(self.db_path)
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._flush_loop(), name="nms_metrics_batch_writer")
        logger.info("MetricsBatchWriter started (flush_interval=%.2fs, max_batch=%d)", self.flush_interval_sec, self.max_batch_size)

    async def stop(self, timeout_sec: float = 1.0) -> None:
        """Stops the worker and flushes all remaining samples in the queue."""
        if not self.is_running:
            return
        self._stop_event.set()
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout_sec)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if not self._worker_task.done():
                    self._worker_task.cancel()

        # Final drain flush
        await self.flush_now()
        logger.info("MetricsBatchWriter stopped successfully.")

    async def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.flush_interval_sec)
                await self.flush_now()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in MetricsBatchWriter flush loop: %s", exc)

    async def flush_now(self) -> int:
        """Drains buffered samples and commits them to SQLite in a single transaction."""
        items: List[TelemetrySample] = []
        while not self._queue.empty() and len(items) < self.max_batch_size:
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not items:
            return 0

        t0 = time.perf_counter()
        count = await asyncio.to_thread(self._write_batch_sync, items)
        self.last_flush_latency_ms = (time.perf_counter() - t0) * 1000.0
        self.total_samples_written += count
        self.total_batches_flushed += 1
        return count

    def _write_batch_sync(self, samples: List[TelemetrySample]) -> int:
        """Synchronous batched write using topology_transaction."""
        rows = [
            (
                s.device_id,
                s.interface_name,
                s.metric_name,
                float(s.metric_value) if s.metric_value is not None else 0.0,
                s.unit,
                s.semantic_type,
                s.source_protocol,
                s.quality,
                s.measured_at,
                s.collected_at,
            )
            for s in samples
        ]

        with topology_transaction(self.db_path, write=True) as conn:
            conn.executemany(
                """
                INSERT INTO nms_raw_metrics (
                    device_id, interface_name, metric_name, metric_value,
                    unit, semantic_type, source_protocol, quality,
                    measured_at, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
        return len(rows)


class RollupEngine:
    """
    Aggregates raw metrics into 5-minute and 1-hour rollup tiers,
    and executes chunked pruning of expired historical data.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH

    def aggregate_5m_rollups(self, cutoff_time: Optional[float] = None) -> int:
        """
        Aggregates raw samples into 300-second buckets for samples up to cutoff_time.
        Defaults cutoff_time to (now - 300s) to avoid aggregating open/incomplete intervals.
        """
        cutoff = cutoff_time if cutoff_time is not None else (time.time() - 300.0)
        now = time.time()

        with topology_transaction(self.db_path, write=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO nms_5m_rollups (
                    device_id, interface_name, metric_name, bucket_start,
                    avg_value, min_value, max_value, sample_count, created_at
                )
                SELECT 
                    device_id,
                    interface_name,
                    metric_name,
                    CAST((measured_at / 300.0) AS INTEGER) * 300.0 AS b_start,
                    AVG(metric_value),
                    MIN(metric_value),
                    MAX(metric_value),
                    COUNT(*),
                    ?
                FROM nms_raw_metrics
                WHERE measured_at <= ?
                GROUP BY device_id, coalesce(interface_name, ''), metric_name, b_start
                ON CONFLICT(device_id, coalesce(interface_name, ''), metric_name, bucket_start)
                DO UPDATE SET
                    avg_value = excluded.avg_value,
                    min_value = excluded.min_value,
                    max_value = excluded.max_value,
                    sample_count = excluded.sample_count,
                    created_at = excluded.created_at;
                """,
                (now, cutoff),
            )
            return cursor.rowcount

    def aggregate_1h_rollups(self, cutoff_time: Optional[float] = None) -> int:
        """
        Aggregates 5-minute rollups into 3600-second buckets up to cutoff_time.
        Defaults cutoff_time to (now - 3600s).
        """
        cutoff = cutoff_time if cutoff_time is not None else (time.time() - 3600.0)
        now = time.time()

        with topology_transaction(self.db_path, write=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO nms_1h_rollups (
                    device_id, interface_name, metric_name, bucket_start,
                    avg_value, min_value, max_value, sample_count, created_at
                )
                SELECT 
                    device_id,
                    interface_name,
                    metric_name,
                    CAST((bucket_start / 3600.0) AS INTEGER) * 3600.0 AS b_start_1h,
                    SUM(avg_value * sample_count) / SUM(sample_count),
                    MIN(min_value),
                    MAX(max_value),
                    SUM(sample_count),
                    ?
                FROM nms_5m_rollups
                WHERE bucket_start <= ?
                GROUP BY device_id, coalesce(interface_name, ''), metric_name, b_start_1h
                ON CONFLICT(device_id, coalesce(interface_name, ''), metric_name, bucket_start)
                DO UPDATE SET
                    avg_value = excluded.avg_value,
                    min_value = excluded.min_value,
                    max_value = excluded.max_value,
                    sample_count = excluded.sample_count,
                    created_at = excluded.created_at;
                """,
                (now, cutoff),
            )
            return cursor.rowcount

    def prune_expired_metrics(
        self,
        now: Optional[float] = None,
        raw_retention_sec: float = 48 * 3600.0,       # 48 hours
        rollup_5m_retention_sec: float = 30 * 86400.0, # 30 days
        rollup_1h_retention_sec: float = 365 * 86400.0,# 365 days
        chunk_size: int = 5000,
    ) -> Dict[str, int]:
        """
        Non-blocking chunked pruning of expired rows across all three retention tiers.
        Guarantees topology snapshots and route snapshots remain 100% untouched.
        """
        current_time = now if now is not None else time.time()
        raw_cutoff = current_time - raw_retention_sec
        r5m_cutoff = current_time - rollup_5m_retention_sec
        r1h_cutoff = current_time - rollup_1h_retention_sec

        pruned_stats = {"raw_pruned": 0, "rollups_5m_pruned": 0, "rollups_1h_pruned": 0}

        with topology_transaction(self.db_path, write=True) as conn:
            # 1. Prune Raw Metrics
            while True:
                cur = conn.execute(
                    """
                    DELETE FROM nms_raw_metrics 
                    WHERE id IN (
                        SELECT id FROM nms_raw_metrics 
                        WHERE measured_at < ? 
                        LIMIT ?
                    );
                    """,
                    (raw_cutoff, chunk_size),
                )
                deleted = cur.rowcount
                pruned_stats["raw_pruned"] += deleted
                if deleted < chunk_size:
                    break

            # 2. Prune 5m Rollups
            while True:
                cur = conn.execute(
                    """
                    DELETE FROM nms_5m_rollups 
                    WHERE id IN (
                        SELECT id FROM nms_5m_rollups 
                        WHERE bucket_start < ? 
                        LIMIT ?
                    );
                    """,
                    (r5m_cutoff, chunk_size),
                )
                deleted = cur.rowcount
                pruned_stats["rollups_5m_pruned"] += deleted
                if deleted < chunk_size:
                    break

            # 3. Prune 1h Rollups
            while True:
                cur = conn.execute(
                    """
                    DELETE FROM nms_1h_rollups 
                    WHERE id IN (
                        SELECT id FROM nms_1h_rollups 
                        WHERE bucket_start < ? 
                        LIMIT ?
                    );
                    """,
                    (r1h_cutoff, chunk_size),
                )
                deleted = cur.rowcount
                pruned_stats["rollups_1h_pruned"] += deleted
                if deleted < chunk_size:
                    break

        return pruned_stats


def query_metrics(
    device_id: str,
    metric_name: str,
    interface_name: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    step: Optional[str] = None,
    db_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Auto-resolving metrics query engine:
    - Window <= 6 hours -> nms_raw_metrics (raw samples)
    - 6 hours < Window <= 7 days -> nms_5m_rollups (5m aggregated buckets)
    - Window > 7 days -> nms_1h_rollups (1h aggregated buckets)
    """
    resolved_path = Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH
    now = time.time()
    t_end = end_time if end_time is not None else now
    t_start = start_time if start_time is not None else (t_end - 3600.0)
    window_sec = t_end - t_start

    # Determine resolution tier
    if step == "raw" or (step is None and window_sec <= 6 * 3600.0):
        target_tier = "raw"
    elif step == "5m" or (step is None and window_sec <= 7 * 86400.0):
        target_tier = "5m"
    else:
        target_tier = "1h"

    # Ensure tables exist
    try:
        conn = get_topology_connection(resolved_path, read_only=True)
        # Check if all required metric tables exist (raw + rollups)
        required_tables = {"nms_raw_metrics", "nms_5m_rollups", "nms_1h_rollups"}
        existing_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('nms_raw_metrics', 'nms_5m_rollups', 'nms_1h_rollups')"
            ).fetchall()
        }
        if not required_tables.issubset(existing_tables):
            conn.close()
            init_metrics_tables(resolved_path)
            conn = get_topology_connection(resolved_path, read_only=True)
    except Exception:
        init_metrics_tables(resolved_path)
        conn = get_topology_connection(resolved_path, read_only=True)

    try:
        points: List[Dict[str, Any]] = []

        if target_tier == "raw":
            query = """
                SELECT measured_at, metric_value, quality
                FROM nms_raw_metrics
                WHERE device_id = ? AND metric_name = ?
                  AND (? IS NULL OR interface_name = ?)
                  AND measured_at >= ? AND measured_at <= ?
                ORDER BY measured_at ASC;
            """
            rows = conn.execute(
                query, (device_id, metric_name, interface_name, interface_name, t_start, t_end)
            ).fetchall()
            for r in rows:
                points.append({
                    "timestamp": r["measured_at"],
                    "value": round(r["metric_value"], 2),
                    "quality": r["quality"],
                })

        elif target_tier == "5m":
            query = """
                SELECT bucket_start, avg_value, min_value, max_value, sample_count
                FROM nms_5m_rollups
                WHERE device_id = ? AND metric_name = ?
                  AND (? IS NULL OR interface_name = ?)
                  AND bucket_start >= ? AND bucket_start <= ?
                ORDER BY bucket_start ASC;
            """
            rows = conn.execute(
                query, (device_id, metric_name, interface_name, interface_name, t_start, t_end)
            ).fetchall()
            for r in rows:
                points.append({
                    "timestamp": r["bucket_start"],
                    "value": round(r["avg_value"], 2),
                    "min": round(r["min_value"], 2),
                    "max": round(r["max_value"], 2),
                    "sample_count": r["sample_count"],
                })

        else:  # 1h tier
            query = """
                SELECT bucket_start, avg_value, min_value, max_value, sample_count
                FROM nms_1h_rollups
                WHERE device_id = ? AND metric_name = ?
                  AND (? IS NULL OR interface_name = ?)
                  AND bucket_start >= ? AND bucket_start <= ?
                ORDER BY bucket_start ASC;
            """
            rows = conn.execute(
                query, (device_id, metric_name, interface_name, interface_name, t_start, t_end)
            ).fetchall()
            for r in rows:
                points.append({
                    "timestamp": r["bucket_start"],
                    "value": round(r["avg_value"], 2),
                    "min": round(r["min_value"], 2),
                    "max": round(r["max_value"], 2),
                    "sample_count": r["sample_count"],
                })

        return {
            "device_id": device_id,
            "metric_name": metric_name,
            "interface_name": interface_name,
            "resolution": target_tier,
            "start_time": t_start,
            "end_time": t_end,
            "points": points,
            "count": len(points),
        }
    finally:
        conn.close()
