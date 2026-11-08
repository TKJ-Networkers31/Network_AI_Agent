"""
core/network_intelligence/metrics_service.py — Multi-Device NMS Historical Metrics & Telemetry Service.
Provides normalized device & interface metric models, time-series querying, downsampling,
retention pruning, and cross-device metric anomaly correlation.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    get_topology_connection,
    init_topology_database,
    get_write_coordinator,
)

logger = logging.getLogger("aira.network_intelligence.metrics")


@dataclass
class NormalizedDeviceMetric:
    device_id: str
    timestamp: float
    cpu_load_percent: Optional[float] = None
    memory_used_percent: Optional[float] = None
    memory_used_bytes: Optional[int] = None
    memory_total_bytes: Optional[int] = None
    uptime_seconds: Optional[int] = None
    latency_ms: Optional[float] = None
    temperature_celsius: Optional[float] = None
    metrics_json: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedInterfaceMetric:
    device_id: str
    interface_name: str
    timestamp: float
    oper_status: str = "unknown"
    admin_status: str = "enabled"
    speed_bps: int = 0
    rx_rate_bps: float = 0.0
    tx_rate_bps: float = 0.0
    rx_utilization_percent: Optional[float] = None
    tx_utilization_percent: Optional[float] = None
    in_errors: int = 0
    out_errors: int = 0
    in_drops: int = 0
    out_drops: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetricAnomaly:
    device_id: str
    metric_type: str  # "cpu", "memory", "latency", "interface_errors", "interface_drops"
    severity: str    # "INFO", "WARNING", "CRITICAL"
    timestamp: float
    current_value: float
    threshold_value: float
    description: str
    interface_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NmsHistoricalMetricsService:
    """
    Historical metrics engine supporting multi-device telemetry ingestion,
    time-range retrieval, downsampling, retention cleanup, and anomaly correlation.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = (Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self._lock = get_write_coordinator(self.db_path)._lock
        init_topology_database(self.db_path)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return get_topology_connection(self.db_path, timeout=30.0)

    def _ensure_tables(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nms_device_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    cpu_load_percent REAL,
                    memory_used_bytes INTEGER,
                    memory_total_bytes INTEGER,
                    memory_used_percent REAL,
                    storage_used_bytes INTEGER,
                    storage_total_bytes INTEGER,
                    temperature_celsius REAL,
                    uptime_seconds INTEGER,
                    latency_ms REAL,
                    metrics_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nms_dev_metrics_dev_ts ON nms_device_metrics(device_id, timestamp)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS nms_interface_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    interface_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    oper_status TEXT DEFAULT 'unknown',
                    speed_bps INTEGER DEFAULT 0,
                    in_octets INTEGER DEFAULT 0,
                    out_octets INTEGER DEFAULT 0,
                    rx_rate_bps REAL DEFAULT 0.0,
                    tx_rate_bps REAL DEFAULT 0.0,
                    rx_utilization_percent REAL,
                    tx_utilization_percent REAL,
                    in_errors INTEGER DEFAULT 0,
                    out_errors INTEGER DEFAULT 0,
                    admin_status TEXT DEFAULT 'enabled',
                    interface_type TEXT DEFAULT 'unknown',
                    mac_address TEXT DEFAULT '',
                    negotiated_speed_bps INTEGER,
                    maximum_capability_bps INTEGER,
                    reported_speed_bps INTEGER,
                    speed_source TEXT DEFAULT 'unknown',
                    speed_updated_at REAL,
                    duplex TEXT DEFAULT 'unknown',
                    in_drops INTEGER DEFAULT 0,
                    out_drops INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nms_if_metrics_dev_if_ts ON nms_interface_metrics(device_id, interface_name, timestamp)")
            conn.commit()

    def ingest_device_metric(self, m: NormalizedDeviceMetric) -> int:
        """Stores a single device telemetry snapshot."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO nms_device_metrics (
                    device_id, timestamp, cpu_load_percent, memory_used_bytes,
                    memory_total_bytes, memory_used_percent, uptime_seconds,
                    latency_ms, temperature_celsius, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m.device_id,
                    m.timestamp,
                    m.cpu_load_percent,
                    m.memory_used_bytes,
                    m.memory_total_bytes,
                    m.memory_used_percent,
                    m.uptime_seconds,
                    m.latency_ms,
                    m.temperature_celsius,
                    json.dumps(m.metrics_json),
                ),
            )
            conn.commit()
            return cur.lastrowid or 0

    def ingest_interface_metric(self, m: NormalizedInterfaceMetric) -> int:
        """Stores a single interface metric snapshot."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO nms_interface_metrics (
                    device_id, interface_name, timestamp, oper_status,
                    speed_bps, rx_rate_bps, tx_rate_bps, rx_utilization_percent,
                    tx_utilization_percent, in_errors, out_errors, admin_status,
                    in_drops, out_drops
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m.device_id,
                    m.interface_name,
                    m.timestamp,
                    m.oper_status,
                    m.speed_bps,
                    m.rx_rate_bps,
                    m.tx_rate_bps,
                    m.rx_utilization_percent,
                    m.tx_utilization_percent,
                    m.in_errors,
                    m.out_errors,
                    m.admin_status,
                    m.in_drops,
                    m.out_drops,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0

    def query_device_metrics_history(
        self,
        device_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 500,
        downsample_points: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Queries historical device metrics with optional time bounding and downsampling."""
        query = "SELECT * FROM nms_device_metrics WHERE device_id = ?"
        params: List[Any] = [device_id]

        if start_time is not None:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time is not None:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        if downsample_points and len(rows) > downsample_points:
            rows = self._downsample_records(rows, downsample_points)

        return rows

    def query_interface_metrics_history(
        self,
        device_id: str,
        interface_name: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 500,
        downsample_points: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Queries historical interface metrics with optional time bounding and downsampling."""
        query = "SELECT * FROM nms_interface_metrics WHERE device_id = ? AND interface_name = ?"
        params: List[Any] = [device_id, interface_name]

        if start_time is not None:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time is not None:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        if downsample_points and len(rows) > downsample_points:
            rows = self._downsample_records(rows, downsample_points)

        return rows

    def prune_expired_metrics(self, retention_days: int = 7) -> int:
        """Deletes metrics older than retention_days. Default is 7 days."""
        cutoff = time.time() - (retention_days * 86400)
        with self._get_connection() as conn:
            cur1 = conn.execute("DELETE FROM nms_device_metrics WHERE timestamp < ?", (cutoff,))
            cur2 = conn.execute("DELETE FROM nms_interface_metrics WHERE timestamp < ?", (cutoff,))
            deleted = cur1.rowcount + cur2.rowcount
            conn.commit()
            return deleted

    def detect_anomalies(
        self,
        device_ids: List[str],
        window_seconds: int = 3600,
        cpu_warning_pct: float = 85.0,
        cpu_critical_pct: float = 95.0,
        latency_warning_ms: float = 100.0,
        latency_critical_ms: float = 300.0,
    ) -> List[MetricAnomaly]:
        """Scans metrics within window_seconds for performance and health anomalies."""
        cutoff = time.time() - window_seconds
        anomalies: List[MetricAnomaly] = []

        with self._get_connection() as conn:
            for dev_id in device_ids:
                dev_rows = conn.execute(
                    """
                    SELECT timestamp, cpu_load_percent, memory_used_percent, latency_ms
                    FROM nms_device_metrics
                    WHERE device_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    """,
                    (dev_id, cutoff),
                ).fetchall()

                for r in dev_rows:
                    cpu = r["cpu_load_percent"]
                    if cpu is not None:
                        if cpu >= cpu_critical_pct:
                            anomalies.append(MetricAnomaly(
                                device_id=dev_id,
                                metric_type="cpu",
                                severity="CRITICAL",
                                timestamp=r["timestamp"],
                                current_value=cpu,
                                threshold_value=cpu_critical_pct,
                                description=f"Beban CPU kritis pada {dev_id}: {cpu:.1f}% >= {cpu_critical_pct}%",
                            ))
                        elif cpu >= cpu_warning_pct:
                            anomalies.append(MetricAnomaly(
                                device_id=dev_id,
                                metric_type="cpu",
                                severity="WARNING",
                                timestamp=r["timestamp"],
                                current_value=cpu,
                                threshold_value=cpu_warning_pct,
                                description=f"Beban CPU tinggi pada {dev_id}: {cpu:.1f}% >= {cpu_warning_pct}%",
                            ))

                    lat = r["latency_ms"]
                    if lat is not None:
                        if lat >= latency_critical_ms:
                            anomalies.append(MetricAnomaly(
                                device_id=dev_id,
                                metric_type="latency",
                                severity="CRITICAL",
                                timestamp=r["timestamp"],
                                current_value=lat,
                                threshold_value=latency_critical_ms,
                                description=f"Latensi ping sangat tinggi pada {dev_id}: {lat:.1f}ms >= {latency_critical_ms}ms",
                            ))
                        elif lat >= latency_warning_ms:
                            anomalies.append(MetricAnomaly(
                                device_id=dev_id,
                                metric_type="latency",
                                severity="WARNING",
                                timestamp=r["timestamp"],
                                current_value=lat,
                                threshold_value=latency_warning_ms,
                                description=f"Latensi ping meningkat pada {dev_id}: {lat:.1f}ms >= {latency_warning_ms}ms",
                            ))

                # Check interface errors / drops
                if_rows = conn.execute(
                    """
                    SELECT timestamp, interface_name, in_errors, out_errors, in_drops, out_drops
                    FROM nms_interface_metrics
                    WHERE device_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    """,
                    (dev_id, cutoff),
                ).fetchall()

                for ir in if_rows:
                    err_sum = (ir["in_errors"] or 0) + (ir["out_errors"] or 0)
                    if err_sum > 0:
                        anomalies.append(MetricAnomaly(
                            device_id=dev_id,
                            metric_type="interface_errors",
                            severity="WARNING",
                            timestamp=ir["timestamp"],
                            current_value=float(err_sum),
                            threshold_value=0.0,
                            description=f"Error antarmuka terdeteksi pada {dev_id}:{ir['interface_name']} ({err_sum} errors)",
                            interface_name=ir["interface_name"],
                        ))

                    drop_sum = (ir["in_drops"] or 0) + (ir["out_drops"] or 0)
                    if drop_sum > 0:
                        anomalies.append(MetricAnomaly(
                            device_id=dev_id,
                            metric_type="interface_drops",
                            severity="WARNING",
                            timestamp=ir["timestamp"],
                            current_value=float(drop_sum),
                            threshold_value=0.0,
                            description=f"Paket drop terdeteksi pada {dev_id}:{ir['interface_name']} ({drop_sum} drops)",
                            interface_name=ir["interface_name"],
                        ))

        return anomalies

    def correlate_metric_anomalies(
        self,
        anomalies: List[MetricAnomaly],
        temporal_window_sec: float = 60.0,
    ) -> List[Dict[str, Any]]:
        """
        Correlates anomalies across distinct devices occurring within temporal_window_sec.
        E.g. latency spike on Router-A coinciding with CPU exhaustion on Core-1.
        """
        correlated_events: List[Dict[str, Any]] = []
        n = len(anomalies)

        for i in range(n):
            a1 = anomalies[i]
            for j in range(i + 1, n):
                a2 = anomalies[j]
                if a1.device_id == a2.device_id:
                    continue  # We seek cross-device correlation

                time_diff = abs(a1.timestamp - a2.timestamp)
                if time_diff <= temporal_window_sec:
                    correlated_events.append({
                        "event_type": "CROSS_DEVICE_METRIC_CORRELATION",
                        "time_difference_sec": round(time_diff, 2),
                        "device_1": a1.device_id,
                        "anomaly_1": a1.to_dict(),
                        "device_2": a2.device_id,
                        "anomaly_2": a2.to_dict(),
                        "correlation_summary": (
                            f"Anomali {a1.metric_type} pada {a1.device_id} berkorelasi temporal "
                            f"(selisih {time_diff:.1f}s) dengan anomali {a2.metric_type} pada {a2.device_id}."
                        ),
                    })

        return correlated_events

    def _downsample_records(self, records: List[Dict[str, Any]], target_points: int) -> List[Dict[str, Any]]:
        """Simple stride-based downsampling preserving first and last records."""
        if len(records) <= target_points:
            return records

        stride = len(records) / (target_points - 1)
        sampled = []
        for i in range(target_points - 1):
            idx = int(math.floor(i * stride))
            sampled.append(records[idx])
        sampled.append(records[-1])
        return sampled
