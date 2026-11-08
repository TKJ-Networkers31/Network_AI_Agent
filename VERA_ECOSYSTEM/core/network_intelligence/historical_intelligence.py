"""
AIRA OS — Historical Network Intelligence Engine (Networking VI / WP 6.9).

Analyzes network evolution across immutable topology and route snapshots, historical NMS metrics,
and recurring incident patterns without mutating underlying records.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set
import uuid

from core.network_intelligence.evidence_service import UnifiedEvidenceService
from core.network_intelligence.intelligence_models import (
    CollectionGapRecord,
    ConfidenceLabel,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, get_topology_connection


class HistoricalIntelligenceEngine:
    """Read-only analytical query engine over historical network state."""

    def __init__(self, topology_db_path: Optional[Path | str] = None) -> None:
        self.db_path = (Path(topology_db_path) if topology_db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.evidence_service = UnifiedEvidenceService(topology_db_path=self.db_path)

    def compare_snapshots(
        self,
        snapshot_id_before: str,
        snapshot_id_after: str,
    ) -> Dict[str, Any]:
        """Compares two historical snapshots using `NetworkKnowledgeGraph.compare_graphs`."""
        if not self.db_path.exists():
            return {
                "error": "Topology database not found.",
                "before_snapshot_id": snapshot_id_before,
                "after_snapshot_id": snapshot_id_after,
            }

        before_data = self._load_snapshot_data(snapshot_id_before)
        after_data = self._load_snapshot_data(snapshot_id_after)

        if not before_data or not after_data:
            return {
                "error": "One or both snapshots could not be loaded.",
                "before_found": bool(before_data),
                "after_found": bool(after_data),
            }

        g_before = NetworkKnowledgeGraph.from_historical_snapshot_dicts(
            snapshot_id=snapshot_id_before,
            snapshot_ts=before_data["timestamp"],
            topology_nodes=before_data["nodes"],
            topology_edges=before_data["edges"],
        )
        g_after = NetworkKnowledgeGraph.from_historical_snapshot_dicts(
            snapshot_id=snapshot_id_after,
            snapshot_ts=after_data["timestamp"],
            topology_nodes=after_data["nodes"],
            topology_edges=after_data["edges"],
        )

        diff = NetworkKnowledgeGraph.compare_graphs(g_before, g_after)
        diff["time_delta_sec"] = max(0.0, after_data["timestamp"] - before_data["timestamp"])
        return diff

    def detect_recurring_incidents(
        self,
        device_id: Optional[str] = None,
        lookback_days: int = 14,
    ) -> List[Dict[str, Any]]:
        """Identifies repeated incident patterns and flapping devices across NMS incidents."""
        if not self.db_path.exists():
            return []

        cutoff = time.time() - (lookback_days * 86400)
        patterns: List[Dict[str, Any]] = []

        try:
            with closing(get_topology_connection(self.db_path, timeout=10.0)) as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "nms_incidents" not in tables:
                    return []
                cols = [c[1] for c in conn.execute("PRAGMA table_info(nms_incidents)").fetchall()]
                time_col = "started_at" if "started_at" in cols else ("opened_at" if "opened_at" in cols else "rowid")
                query = f"SELECT * FROM nms_incidents WHERE {time_col} >= ?"
                params: List[Any] = [cutoff]
                if device_id:
                    query += " AND device_id = ?"
                    params.append(device_id)
                query += f" ORDER BY {time_col} ASC"

                rows = conn.execute(query, params).fetchall()
                by_type_device: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
                for r in rows:
                    d_row = dict(r)
                    if "opened_at" in d_row and "started_at" not in d_row:
                        d_row["started_at"] = d_row["opened_at"]
                    elif "started_at" in d_row and "opened_at" not in d_row:
                        d_row["opened_at"] = d_row["started_at"]
                    k = (str(d_row.get("device_id")), str(d_row.get("incident_type")))
                    by_type_device.setdefault(k, []).append(d_row)

                for (did, itype), incs in by_type_device.items():
                    if len(incs) >= 2:
                        patterns.append(
                            {
                                "device_id": did,
                                "incident_type": itype,
                                "recurrence_count": len(incs),
                                "first_seen_at": float(incs[0].get("started_at") or incs[0].get("opened_at") or 0.0),
                                "last_seen_at": float(incs[-1].get("started_at") or incs[-1].get("opened_at") or 0.0),
                                "is_flapping": len(incs) >= 3,
                                "incident_ids": [str(i.get("id") or i.get("incident_id")) for i in incs],
                            }
                        )
        except sqlite3.Error:
            return []

        return sorted(patterns, key=lambda x: -x["recurrence_count"])

    def evaluate_metric_trend(
        self,
        device_id: str,
        metric_name: str,
        interface_name: Optional[str] = None,
        lookback_hours: int = 6,
    ) -> Dict[str, Any]:
        """Analyzes historical trend and counter acceleration over time."""
        if not self.db_path.exists():
            return {"error": "Topology database not found."}

        cutoff = time.time() - (lookback_hours * 3600)
        samples: List[Tuple[float, float]] = []

        try:
            with closing(get_topology_connection(self.db_path, timeout=10.0)) as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if interface_name and "nms_interface_metrics" in tables:
                    rows = conn.execute(
                        "SELECT timestamp, " + metric_name + " FROM nms_interface_metrics "
                        "WHERE device_id = ? AND interface_name = ? AND timestamp >= ? AND " + metric_name + " IS NOT NULL "
                        "ORDER BY timestamp ASC",
                        (device_id, interface_name, cutoff),
                    ).fetchall()
                    for r in rows:
                        samples.append((float(r[0]), float(r[1])))
                elif not interface_name and "nms_device_metrics" in tables:
                    rows = conn.execute(
                        "SELECT timestamp, " + metric_name + " FROM nms_device_metrics "
                        "WHERE device_id = ? AND timestamp >= ? AND " + metric_name + " IS NOT NULL "
                        "ORDER BY timestamp ASC",
                        (device_id, cutoff),
                    ).fetchall()
                    for r in rows:
                        samples.append((float(r[0]), float(r[1])))
        except sqlite3.Error:
            pass

        if not samples:
            return {
                "device_id": device_id,
                "metric_name": metric_name,
                "interface_name": interface_name,
                "sample_count": 0,
                "trend": "NO_HISTORICAL_DATA",
            }

        vals = [v for _, v in samples]
        v_start = vals[0]
        v_end = vals[-1]
        delta = v_end - v_start
        trend_label = "STABLE"
        if delta > 0.15 * max(abs(v_start), 1.0):
            trend_label = "INCREASING"
        elif delta < -0.15 * max(abs(v_start), 1.0):
            trend_label = "DECREASING"

        return {
            "device_id": device_id,
            "metric_name": metric_name,
            "interface_name": interface_name,
            "sample_count": len(samples),
            "start_value": v_start,
            "end_value": v_end,
            "min_value": min(vals),
            "max_value": max(vals),
            "delta": delta,
            "trend": trend_label,
            "has_counter_acceleration": delta > 0 and len(vals) >= 4 and (vals[-1] - vals[-2]) > (vals[1] - vals[0]),
        }

    def _load_snapshot_data(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        try:
            with closing(get_topology_connection(self.db_path, timeout=10.0)) as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "topology_snapshots" not in tables:
                    return None
                row = conn.execute("SELECT * FROM topology_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
                if not row:
                    return None
                try:
                    payload = json.loads(row["snapshot_data"] or row["payload"] or "{}")
                except Exception:
                    payload = {}
                nodes = payload.get("nodes") or []
                edges = payload.get("edges") or []
                return {
                    "snapshot_id": snapshot_id,
                    "timestamp": float(row["timestamp"] if "timestamp" in row.keys() else time.time()),
                    "nodes": nodes,
                    "edges": edges,
                }
        except Exception:
            return None
