# AIRA OS — Phase Networking III
# NMS Historical Data & Telemetry Foundation

## 1. Executive Summary

This document specifies the multi-device NMS historical metrics architecture implemented in `core/network_intelligence/metrics_service.py` under Work Package N3.8 of Phase Networking III.

The service extends single-node polling into fleet-wide telemetry ingestion, historical time-series querying, downsampling, automated retention management, and cross-device anomaly correlation.

---

## 2. Telemetry Models & Storage

### 2.1 Domain Models

- `NormalizedDeviceMetric`: Records CPU load, memory utilization, storage utilization, temperature, uptime seconds, and ICMP ping latency.
- `NormalizedInterfaceMetric`: Records tx/rx throughput rates (bps), packet counters, CRC/in/out errors, drops, admin status, and operational status.
- `MetricAnomaly`: Records detected health anomalies with threshold values, severity ("INFO", "WARNING", "CRITICAL"), and descriptions.

### 2.2 SQLite Schema (`topology.db`)

Stored in `topology.db` with WAL mode and compound indexing:
- `nms_device_metrics (device_id, timestamp)`
- `nms_interface_metrics (device_id, interface_name, timestamp)`

---

## 3. Querying, Downsampling & Retention

### 3.1 Downsampling Algorithm

When querying extensive time windows (e.g. 7 days with thousands of samples), `_downsample_records()` compresses the data to a client-specified number of points (e.g. 100 points) using an even stride algorithm while preserving the initial and latest data points, preventing UI chart lag on modest client devices.

### 3.2 Automated Retention Pruning

`prune_expired_metrics(retention_days=7)` enforces a rolling 7-day data retention window, purging stale records and preventing SQLite database bloat on the host machine.

---

## 4. Cross-Device Metric Anomaly Correlation

`correlate_metric_anomalies()` correlates performance degradation events across distinct devices occurring within a configurable temporal window (default: $\pm 60$ seconds):
- Example: Core Router A experiences a CPU load spike to 98% at $T = 100$; simultaneously at $T = 105$, Edge Router B experiences a ping latency spike to 350ms.
- The service flags this as a `CROSS_DEVICE_METRIC_CORRELATION`, feeding temporal evidence into the diagnostic engine.

---

## 5. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/core/network_intelligence/metrics_service.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_metrics.py` (4 tests passed).
- API Integration: `GET /api/intelligence/metrics/history`.
