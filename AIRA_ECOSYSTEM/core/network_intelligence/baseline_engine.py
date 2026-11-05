"""
AIRA OS — Adaptive Network Behavior Baseline Engine (Networking VI / WP 6.6).

Learns per-device and per-interface normal behavior using pure-Python, outlier-resistant
Rolling Median, Median Absolute Deviation (MAD), and EWMA over bounded windows.

Enforces strict epistemic hygiene:
- Never constructs baselines from insufficient samples (`sample_count < min_samples`).
- Never treats `None` (missing telemetry) as `0.0`.
- Excludes maintenance-window samples and `DISCONTINUOUS` counter resets.
- Detects device reboots (`uptime_seconds` regression) and material topology changes,
  incrementing baseline `version` and invalidating contaminated history cleanly.
"""

from __future__ import annotations

from collections import deque
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import statistics
import time
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple
import uuid

from core.network_intelligence.intelligence_models import (
    MetricBaselineRecord,
    NetworkEvidenceBundle,
)
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, get_topology_connection

DEFAULT_MIN_SAMPLES = 5
DEFAULT_MAX_SAMPLES = 120
DEFAULT_EWMA_ALPHA = 0.25


class _SeriesWindow:
    """Internal bounded state for a single `(device_id, entity_key, metric_name)` baseline."""

    __slots__ = (
        "baseline_id",
        "device_id",
        "entity_key",
        "metric_name",
        "version",
        "samples",
        "ewma",
        "last_uptime_sec",
        "last_raw_counter",
        "topology_ref",
        "status",
        "invalidation_reason",
        "updated_at",
    )

    def __init__(
        self,
        device_id: str,
        entity_key: str,
        metric_name: str,
        max_samples: int = DEFAULT_MAX_SAMPLES,
        topology_ref: str = "",
    ) -> None:
        self.baseline_id = f"base_{device_id}_{uuid.uuid4().hex[:8]}"
        self.device_id = device_id
        self.entity_key = entity_key
        self.metric_name = metric_name
        self.version = 1
        self.samples: Deque[Tuple[float, float]] = deque(maxlen=max(10, max_samples))
        self.ewma: Optional[float] = None
        self.last_uptime_sec: Optional[int] = None
        self.last_raw_counter: Optional[float] = None
        self.topology_ref = topology_ref
        self.status = "INSUFFICIENT_SAMPLES"
        self.invalidation_reason = ""
        self.updated_at = time.time()


class BaselineEngine:
    """
    Resource-efficient per-device and per-interface baseline manager supporting
    reboot invalidation, counter-reset protection, maintenance exclusion, and versioning.
    """

    def __init__(
        self,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        max_samples: int = DEFAULT_MAX_SAMPLES,
        ewma_alpha: float = DEFAULT_EWMA_ALPHA,
        max_tracked_series: int = 4000,
    ) -> None:
        self.min_samples = max(3, int(min_samples))
        self.max_samples = max(self.min_samples, int(max_samples))
        self.ewma_alpha = max(0.05, min(0.95, float(ewma_alpha)))
        self.max_tracked_series = max(100, int(max_tracked_series))
        self._series: Dict[Tuple[str, str, str], _SeriesWindow] = {}

    def ingest_sample(
        self,
        device_id: str,
        entity_key: str,
        metric_name: str,
        value: Optional[float],
        timestamp: Optional[float] = None,
        uptime_seconds: Optional[int] = None,
        is_monotonic_counter: bool = False,
        in_maintenance: bool = False,
        topology_ref: str = "",
        invalidate_on_topology_change: bool = False,
    ) -> Tuple[Optional[MetricBaselineRecord], str]:
        """
        Ingests a single observation into the baseline engine.
        Returns `(baseline_record_or_None, ingestion_note)` where `ingestion_note` is one of:
        - `INGESTED`
        - `SKIPPED_MISSING_VALUE`
        - `SKIPPED_MAINTENANCE`
        - `INVALIDATED_REBOOT`
        - `SKIPPED_COUNTER_RESET_DISCONTINUOUS`
        - `INVALIDATED_TOPOLOGY_CHANGE`
        """
        ts = float(timestamp) if timestamp is not None else time.time()
        key = (device_id, entity_key, metric_name)

        if value is None:
            return self.get_baseline(device_id, entity_key, metric_name), "SKIPPED_MISSING_VALUE"
        try:
            fval = float(value)
        except (TypeError, ValueError):
            return self.get_baseline(device_id, entity_key, metric_name), "SKIPPED_MISSING_VALUE"
        if math.isnan(fval) or math.isinf(fval):
            return self.get_baseline(device_id, entity_key, metric_name), "SKIPPED_MISSING_VALUE"

        if in_maintenance:
            return self.get_baseline(device_id, entity_key, metric_name), "SKIPPED_MAINTENANCE"

        win = self._series.get(key)
        if win is None:
            if len(self._series) >= self.max_tracked_series:
                # Evict oldest series to enforce strict memory ceiling
                oldest_k = min(self._series.keys(), key=lambda k: self._series[k].updated_at)
                self._series.pop(oldest_k, None)
            win = _SeriesWindow(
                device_id=device_id,
                entity_key=entity_key,
                metric_name=metric_name,
                max_samples=self.max_samples,
                topology_ref=topology_ref,
            )
            self._series[key] = win

        note = "INGESTED"

        # 1. Device Reboot Check (uptime regression)
        if uptime_seconds is not None:
            up_int = int(uptime_seconds)
            if win.last_uptime_sec is not None and up_int + 5 < win.last_uptime_sec:
                win.version += 1
                win.samples.clear()
                win.ewma = None
                win.last_raw_counter = None
                win.status = "INVALIDATED"
                win.invalidation_reason = f"DEVICE_REBOOT_DETECTED (uptime {win.last_uptime_sec}s -> {up_int}s)"
                note = "INVALIDATED_REBOOT"
            win.last_uptime_sec = up_int

        # 2. Material Topology Change Check
        if (
            invalidate_on_topology_change
            and topology_ref
            and win.topology_ref
            and topology_ref != win.topology_ref
            and note != "INVALIDATED_REBOOT"
        ):
            win.version += 1
            win.samples.clear()
            win.ewma = None
            win.last_raw_counter = None
            win.status = "INVALIDATED"
            win.invalidation_reason = f"TOPOLOGY_CHANGE ({win.topology_ref} -> {topology_ref})"
            note = "INVALIDATED_TOPOLOGY_CHANGE"
        if topology_ref:
            win.topology_ref = topology_ref

        # 3. Monotonic Counter Reset Check (DISCONTINUOUS)
        sample_to_store = fval
        if is_monotonic_counter:
            prev_cnt = win.last_raw_counter
            win.last_raw_counter = fval
            if prev_cnt is None:
                win.updated_at = ts
                return self._to_record(win), note if note.startswith("INVALIDATED") else "COUNTER_ANCHOR_ESTABLISHED"
            if fval < prev_cnt:
                # Counter reset without reboot -> DISCONTINUOUS, never treat as negative delta!
                win.updated_at = ts
                return self._to_record(win), "SKIPPED_COUNTER_RESET_DISCONTINUOUS"
            sample_to_store = fval - prev_cnt

        win.samples.append((ts, sample_to_store))
        if win.ewma is None:
            win.ewma = sample_to_store
        else:
            win.ewma = self.ewma_alpha * sample_to_store + (1.0 - self.ewma_alpha) * win.ewma
        win.updated_at = ts

        if len(win.samples) >= self.min_samples:
            win.status = "ACTIVE"
            win.invalidation_reason = ""
        elif win.status != "INVALIDATED":
            win.status = "INSUFFICIENT_SAMPLES"

        return self._to_record(win), note

    def invalidate_device_baselines(self, device_id: str, reason: str = "DEVICE_REPLACEMENT_OR_MANUAL") -> int:
        """Explicitly invalidates and versions all baselines belonging to `device_id`."""
        count = 0
        now = time.time()
        for (did, _, _), win in self._series.items():
            if did == device_id:
                win.version += 1
                win.samples.clear()
                win.ewma = None
                win.last_raw_counter = None
                win.status = "INVALIDATED"
                win.invalidation_reason = reason
                win.updated_at = now
                count += 1
        return count

    def get_baseline(
        self,
        device_id: str,
        entity_key: str,
        metric_name: str,
    ) -> Optional[MetricBaselineRecord]:
        win = self._series.get((device_id, entity_key, metric_name))
        if win is None:
            return None
        return self._to_record(win)

    def list_baselines(
        self,
        device_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[MetricBaselineRecord]:
        out: List[MetricBaselineRecord] = []
        for (did, _, _), win in self._series.items():
            if device_id and did != device_id:
                continue
            rec = self._to_record(win)
            if active_only and rec.status != "ACTIVE":
                continue
            out.append(rec)
        return out

    def update_from_bundle(
        self,
        bundle: NetworkEvidenceBundle,
        in_maintenance_devices: Optional[Sequence[str]] = None,
        invalidate_on_topology_change: bool = False,
    ) -> List[MetricBaselineRecord]:
        """Ingests non-null observations from a `NetworkEvidenceBundle` into per-entity baselines."""
        maint_set = set(in_maintenance_devices or [])
        topo_ref = bundle.topology_snapshot_ref or ""
        updated: List[MetricBaselineRecord] = []

        for dev_id, dinfo in bundle.device_evidence.items():
            is_maint = dev_id in maint_set
            obs_ts = float(dinfo.get("last_check_at") or bundle.assembled_at)
            uptime = dinfo.get("uptime_seconds")
            dev_key = f"device:{dev_id}"

            for mname in ("cpu_load_percent", "memory_used_percent", "latency_ms", "packet_loss_percent"):
                rec, _ = self.ingest_sample(
                    device_id=dev_id,
                    entity_key=dev_key,
                    metric_name=mname,
                    value=dinfo.get(mname),
                    timestamp=obs_ts,
                    uptime_seconds=uptime,
                    in_maintenance=is_maint,
                    topology_ref=topo_ref,
                    invalidate_on_topology_change=invalidate_on_topology_change,
                )
                if rec:
                    updated.append(rec)

            # Route count stability baseline
            routes = bundle.routing_evidence.get(dev_id)
            if routes is not None and len(routes) > 0:
                active_cnt = sum(1 for r in routes if r.active and not r.disabled)
                rec, _ = self.ingest_sample(
                    device_id=dev_id,
                    entity_key=dev_key,
                    metric_name="active_route_count",
                    value=float(active_cnt),
                    timestamp=obs_ts,
                    uptime_seconds=uptime,
                    in_maintenance=is_maint,
                    topology_ref=topo_ref,
                    invalidate_on_topology_change=invalidate_on_topology_change,
                )
                if rec:
                    updated.append(rec)

            # Interface baselines
            for iface in bundle.interface_evidence.get(dev_id, []):
                iname = str(iface.get("interface_name") or "")
                if not iname:
                    continue
                if_key = f"iface:{dev_id}:{iname}"
                if_ts = float(iface.get("last_counter_update") or obs_ts)
                for mname in (
                    "rx_rate_bps",
                    "tx_rate_bps",
                    "rx_utilization_percent",
                    "tx_utilization_percent",
                ):
                    rec, _ = self.ingest_sample(
                        device_id=dev_id,
                        entity_key=if_key,
                        metric_name=mname,
                        value=iface.get(mname),
                        timestamp=if_ts,
                        uptime_seconds=uptime,
                        in_maintenance=is_maint,
                    )
                    if rec:
                        updated.append(rec)

                # Cumulative error+drop delta baseline (counter-reset protected)
                err_vals = [iface.get(k) for k in ("in_errors", "out_errors", "in_drops", "out_drops")]
                non_null_errs = [float(v) for v in err_vals if v is not None]
                if non_null_errs:
                    rec, _ = self.ingest_sample(
                        device_id=dev_id,
                        entity_key=if_key,
                        metric_name="error_drop_delta",
                        value=sum(non_null_errs),
                        timestamp=if_ts,
                        uptime_seconds=uptime,
                        is_monotonic_counter=True,
                        in_maintenance=is_maint,
                    )
                    if rec:
                        updated.append(rec)

        return updated

    def bootstrap_from_topology_db(
        self,
        db_path: Optional[Path | str] = None,
        device_ids: Optional[Sequence[str]] = None,
        max_rows_per_device: int = 60,
    ) -> int:
        """
        Loads bounded recent historical NMS metric observations from `topology.db`
        in chronological order to warm per-device and per-interface baselines.
        """
        target_db = (Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
        if not target_db.exists():
            return 0
        dev_filter = set(device_ids) if device_ids else None
        ingested_count = 0

        try:
            with closing(get_topology_connection(target_db, timeout=10.0)) as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "nms_device_metrics" in tables:
                    rows = conn.execute(
                        "SELECT * FROM nms_device_metrics ORDER BY timestamp DESC LIMIT ?",
                        (max_rows_per_device * max(1, len(dev_filter) if dev_filter else 10),),
                    ).fetchall()
                    for r in reversed(rows):
                        did = r["device_id"]
                        if dev_filter and did not in dev_filter:
                            continue
                        ts = float(r["timestamp"] or 0.0)
                        up = r["uptime_seconds"]
                        dkey = f"device:{did}"
                        for col in ("cpu_load_percent", "memory_used_percent", "latency_ms", "packet_loss_percent"):
                            if col in r.keys() and r[col] is not None:
                                self.ingest_sample(did, dkey, col, r[col], timestamp=ts, uptime_seconds=up)
                                ingested_count += 1

                if "nms_interface_metrics" in tables:
                    rows = conn.execute(
                        "SELECT * FROM nms_interface_metrics ORDER BY timestamp DESC LIMIT ?",
                        (max_rows_per_device * max(1, len(dev_filter) if dev_filter else 20),),
                    ).fetchall()
                    for r in reversed(rows):
                        did = r["device_id"]
                        if dev_filter and did not in dev_filter:
                            continue
                        iname = r["interface_name"]
                        ikey = f"iface:{did}:{iname}"
                        ts = float(r["timestamp"] or 0.0)
                        for col in ("rx_rate_bps", "tx_rate_bps", "rx_utilization_percent", "tx_utilization_percent"):
                            if col in r.keys() and r[col] is not None:
                                self.ingest_sample(did, ikey, col, r[col], timestamp=ts)
                                ingested_count += 1
        except sqlite3.Error:
            return ingested_count

        return ingested_count

    @staticmethod
    def _to_record(win: _SeriesWindow) -> MetricBaselineRecord:
        vals = [v for _, v in win.samples]
        if not vals:
            return MetricBaselineRecord(
                baseline_id=win.baseline_id,
                entity_key=win.entity_key,
                device_id=win.device_id,
                metric_name=win.metric_name,
                version=win.version,
                sample_count=0,
                median_value=0.0,
                mad_value=0.0,
                ewma_value=0.0,
                min_value=0.0,
                max_value=0.0,
                status=win.status,
                invalidation_reason=win.invalidation_reason,
                last_uptime_sec=win.last_uptime_sec,
                topology_ref=win.topology_ref,
                updated_at=win.updated_at,
            )

        med = float(statistics.median(vals))
        abs_devs = [abs(v - med) for v in vals]
        mad = float(statistics.median(abs_devs))
        ewma = float(win.ewma if win.ewma is not None else med)

        return MetricBaselineRecord(
            baseline_id=win.baseline_id,
            entity_key=win.entity_key,
            device_id=win.device_id,
            metric_name=win.metric_name,
            version=win.version,
            sample_count=len(vals),
            median_value=med,
            mad_value=mad,
            ewma_value=ewma,
            min_value=min(vals),
            max_value=max(vals),
            status=win.status,
            invalidation_reason=win.invalidation_reason,
            last_uptime_sec=win.last_uptime_sec,
            topology_ref=win.topology_ref,
            updated_at=win.updated_at,
        )
