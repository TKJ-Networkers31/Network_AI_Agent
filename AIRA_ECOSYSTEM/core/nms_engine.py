"""
core/nms_engine.py — Centralized Network Management System (NMS) Engine for AIRA OS.
Provides continuous device availability monitoring, RouterOS & SNMP resource metrics,
interface bandwidth tracking with delta rate calculations, incident management,
and an interactive SNMP setup wizard.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core.events import EventNames, event_bus
from core.nms_models import (
    DEFAULT_NMS_SETTINGS,
    NMS_STATUS_VALUES,
    calculate_traffic_rate,
    determine_device_availability,
    is_check_stale,
    resolve_device_display_name,
    parse_uptime_to_seconds,
)
from core.nms_snmp import poll_device_snmp_full, snmp_get_multi
from core.topology_models import bounded_icmp_ping
from core.topology_parsers import (
    parse_mikrotik_ethernet,
    parse_mikrotik_identity,
    parse_mikrotik_interfaces,
    parse_mikrotik_resource,
    parse_mikrotik_routerboard,
)

logger = logging.getLogger("aira.nms.engine")

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "database" / "topology.db"

_PROFILE_MIGRATION_COLUMNS = [
    ("last_check_at", "REAL"),
    ("last_success_at", "REAL"),
    ("status_changed_at", "REAL"),
    ("monitoring_method", "TEXT DEFAULT 'icmp_ping'"),
    ("name_source", "TEXT DEFAULT 'unknown'"),
    ("device_identity", "TEXT DEFAULT ''"),
    ("routeros_version", "TEXT DEFAULT ''"),
    ("routeros_model", "TEXT DEFAULT ''"),
]

_IFACE_MIGRATION_COLUMNS = [
    ("admin_status", "TEXT DEFAULT 'enabled'"),
    ("interface_type", "TEXT DEFAULT 'unknown'"),
    ("mac_address", "TEXT DEFAULT ''"),
    ("negotiated_speed_bps", "INTEGER"),
    ("maximum_capability_bps", "INTEGER"),
    ("reported_speed_bps", "INTEGER"),
    ("speed_source", "TEXT DEFAULT 'unknown'"),
    ("speed_updated_at", "REAL"),
    ("duplex", "TEXT DEFAULT 'unknown'"),
    ("in_drops", "INTEGER DEFAULT 0"),
    ("out_drops", "INTEGER DEFAULT 0"),
]


class NmsEngine:
    """Centralized NMS Engine maintaining persistent monitoring profiles, metrics, and incident lifecycle."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        self._is_polling = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self.last_poll_timestamp: Optional[float] = None
        self.next_poll_timestamp: Optional[float] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        """Initializes NMS tables and ensures schema migrations are non-destructive."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._get_connection()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nms_settings (
                    key TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nms_device_profiles (
                    device_id TEXT PRIMARY KEY,
                    management_mode TEXT DEFAULT 'unmanaged',
                    monitoring_enabled INTEGER DEFAULT 1,
                    is_paused INTEGER DEFAULT 0,
                    maintenance_mode INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'UNKNOWN',
                    consecutive_failures INTEGER DEFAULT 0,
                    consecutive_successes INTEGER DEFAULT 0,
                    snmp_enabled INTEGER DEFAULT 0,
                    snmp_version TEXT DEFAULT 'v2c',
                    snmp_community TEXT DEFAULT '',
                    snmp_port INTEGER DEFAULT 161,
                    snmp_v3_user TEXT DEFAULT '',
                    snmp_v3_auth_proto TEXT DEFAULT '',
                    snmp_v3_auth_key TEXT DEFAULT '',
                    snmp_v3_priv_proto TEXT DEFAULT '',
                    snmp_v3_priv_key TEXT DEFAULT '',
                    routeros_api_enabled INTEGER DEFAULT 0,
                    routeros_api_port INTEGER DEFAULT 8728,
                    ssh_monitoring_enabled INTEGER DEFAULT 0,
                    last_polled_at REAL,
                    last_successful_poll_at REAL,
                    last_status_change REAL,
                    outage_started_at REAL,
                    last_error TEXT DEFAULT '',
                    latency_ms REAL DEFAULT 0.0,
                    metrics_summary_json TEXT DEFAULT '{}',
                    updated_at REAL NOT NULL
                );

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
                );

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
                    out_errors INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS nms_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    incident_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    status TEXT DEFAULT 'open',
                    started_at REAL NOT NULL,
                    resolved_at REAL,
                    acknowledged_at REAL,
                    acknowledged_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_nms_prof_status ON nms_device_profiles(status);
                CREATE INDEX IF NOT EXISTS idx_nms_dev_metrics_ts ON nms_device_metrics(device_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_nms_if_metrics_ts ON nms_interface_metrics(device_id, interface_name, timestamp);
                CREATE INDEX IF NOT EXISTS idx_nms_inc_status ON nms_incidents(status, started_at);
                """
            )

            # Insert default settings if absent
            row = conn.execute("SELECT key FROM nms_settings WHERE key = 'default'").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO nms_settings (key, settings_json, updated_at) VALUES (?, ?, ?)",
                    ("default", json.dumps(DEFAULT_NMS_SETTINGS), time.time()),
                )

            # Non-destructive migrations for nms_device_profiles
            prof_cols = {r["name"] for r in conn.execute("PRAGMA table_info(nms_device_profiles)").fetchall()}
            for col_name, col_def in _PROFILE_MIGRATION_COLUMNS:
                if col_name not in prof_cols:
                    conn.execute(f"ALTER TABLE nms_device_profiles ADD COLUMN {col_name} {col_def}")

            # Non-destructive migrations for nms_interface_metrics
            if_cols = {r["name"] for r in conn.execute("PRAGMA table_info(nms_interface_metrics)").fetchall()}
            for col_name, col_def in _IFACE_MIGRATION_COLUMNS:
                if col_name not in if_cols:
                    conn.execute(f"ALTER TABLE nms_interface_metrics ADD COLUMN {col_name} {col_def}")

            # Non-destructive migrations for topology_nodes if table exists
            table_names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "topology_nodes" in table_names:
                topo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(topology_nodes)").fetchall()}
                for col_name, col_def in [
                    ("status", "TEXT DEFAULT 'online'"),
                    ("latency_ms", "REAL DEFAULT 0.0"),
                    ("reachability_status", "TEXT DEFAULT 'unknown'"),
                    ("management_status", "TEXT DEFAULT 'not_attempted'"),
                    ("observation_freshness", "TEXT DEFAULT 'unknown'"),
                    ("availability_reason", "TEXT DEFAULT ''"),
                    ("last_probe_at", "REAL"),
                    ("last_ping_alive", "INTEGER"),
                    ("user_overrides_json", "TEXT DEFAULT '{}'"),
                    ("metadata_json", "TEXT DEFAULT '{}'"),
                ]:
                    if col_name not in topo_cols:
                        conn.execute(f"ALTER TABLE topology_nodes ADD COLUMN {col_name} {col_def}")

            # Populate last_check_at, last_success_at, status_changed_at from legacy columns if null
            conn.execute("UPDATE nms_device_profiles SET last_check_at = last_polled_at WHERE last_check_at IS NULL AND last_polled_at IS NOT NULL")
            conn.execute("UPDATE nms_device_profiles SET last_success_at = last_successful_poll_at WHERE last_success_at IS NULL AND last_successful_poll_at IS NOT NULL")
            conn.execute("UPDATE nms_device_profiles SET status_changed_at = last_status_change WHERE status_changed_at IS NULL AND last_status_change IS NOT NULL")

            # Sync any existing topology_nodes into nms_device_profiles
            conn.execute(
                """
                INSERT OR IGNORE INTO nms_device_profiles (device_id, status, updated_at)
                SELECT id, 'UNKNOWN', ? FROM topology_nodes
                """,
                (time.time(),),
            )
            conn.commit()

    # -----------------------------------------------------------------------
    # Settings Management
    # -----------------------------------------------------------------------
    def get_settings(self) -> Dict[str, Any]:
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT settings_json FROM nms_settings WHERE key = 'default'").fetchone()
            if row:
                try:
                    loaded = json.loads(row["settings_json"])
                    merged = dict(DEFAULT_NMS_SETTINGS)
                    merged.update(loaded)
                    return merged
                except Exception:
                    pass
            return dict(DEFAULT_NMS_SETTINGS)

    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        curr = self.get_settings()
        for k, v in new_settings.items():
            if k in curr:
                curr[k] = v
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                "UPDATE nms_settings SET settings_json = ?, updated_at = ? WHERE key = 'default'",
                (json.dumps(curr), time.time()),
            )
            conn.commit()
        return curr

    # -----------------------------------------------------------------------
    # Overview KPI Metrics
    # -----------------------------------------------------------------------
    def get_overview(self) -> Dict[str, Any]:
        with self._lock, closing(self._get_connection()) as conn:
            # Sync any new nodes from topology_nodes
            conn.execute(
                """
                INSERT OR IGNORE INTO nms_device_profiles (device_id, status, updated_at)
                SELECT id, 'UNKNOWN', ? FROM topology_nodes
                """,
                (time.time(),),
            )
            conn.commit()

            rows = conn.execute("SELECT status, management_mode, monitoring_enabled FROM nms_device_profiles").fetchall()
            open_incidents = conn.execute("SELECT COUNT(*) as c FROM nms_incidents WHERE status = 'open'").fetchone()["c"]

            total = len(rows)
            up_count = sum(1 for r in rows if r["status"] == "UP")
            down_count = sum(1 for r in rows if r["status"] == "DOWN")
            suspected_count = sum(1 for r in rows if r["status"] == "SUSPECTED_DOWN")
            degraded_count = sum(1 for r in rows if r["status"] == "DEGRADED")
            unavailable_count = sum(1 for r in rows if r["status"] == "MONITORING_UNAVAILABLE")
            unknown_count = sum(1 for r in rows if r["status"] == "UNKNOWN")
            managed_count = sum(1 for r in rows if r["management_mode"] == "managed")
            unmanaged_count = sum(1 for r in rows if r["management_mode"] != "managed")

            settings = self.get_settings()

            return {
                "total_devices": total,
                "up": up_count,
                "down": down_count,
                "suspected_down": suspected_count,
                "degraded": degraded_count,
                "monitoring_unavailable": unavailable_count,
                "unknown": unknown_count,
                "managed": managed_count,
                "unmanaged": unmanaged_count,
                "active_incidents": open_incidents,
                "auto_monitoring_enabled": bool(settings.get("auto_monitoring_enabled", True)),
                "polling_interval_sec": settings.get("default_interval_sec", 15),
                "is_running": self.is_running(),
                "last_poll_timestamp": self.last_poll_timestamp,
                "next_poll_timestamp": self.next_poll_timestamp,
            }

    # -----------------------------------------------------------------------
    # Device Inventory & Profile Queries
    # -----------------------------------------------------------------------
    def list_devices(
        self,
        status: Optional[str] = None,
        management_mode: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        settings = self.get_settings()
        interval = int(settings.get("default_interval_sec", 15))

        with self._lock, closing(self._get_connection()) as conn:
            query = """
                SELECT 
                    n.id, n.name, n.identity, n.ip, n.mac, n.device_type, n.ownership_status,
                    p.management_mode, p.monitoring_enabled, p.is_paused, p.maintenance_mode,
                    p.status as nms_status, p.latency_ms, p.last_check_at, p.last_polled_at,
                    p.last_success_at, p.last_successful_poll_at, p.status_changed_at,
                    p.last_status_change, p.consecutive_failures, p.consecutive_successes,
                    p.outage_started_at, p.last_error, p.monitoring_method, p.name_source,
                    p.device_identity, p.routeros_version, p.routeros_model,
                    p.metrics_summary_json, p.snmp_enabled
                FROM topology_nodes n
                LEFT JOIN nms_device_profiles p ON n.id = p.device_id
                WHERE 1=1
            """
            params: List[Any] = []
            if status and status != "all":
                query += " AND p.status = ?"
                params.append(status.upper())
            if management_mode and management_mode != "all":
                query += " AND p.management_mode = ?"
                params.append(management_mode)
            if search:
                query += " AND (n.name LIKE ? OR n.ip LIKE ? OR n.identity LIKE ? OR p.device_identity LIKE ?)"
                kw = f"%{search.strip()}%"
                params.extend([kw, kw, kw, kw])

            query += " ORDER BY CASE p.status WHEN 'DOWN' THEN 1 WHEN 'SUSPECTED_DOWN' THEN 2 WHEN 'DEGRADED' THEN 3 WHEN 'UP' THEN 4 ELSE 5 END, n.name"
            rows = conn.execute(query, params).fetchall()

            result = []
            for r in rows:
                metrics_summary = {}
                try:
                    metrics_summary = json.loads(r["metrics_summary_json"] or "{}")
                except Exception:
                    pass

                last_chk = r["last_check_at"] or r["last_polled_at"]
                last_succ = r["last_success_at"] or r["last_successful_poll_at"]
                st_changed = r["status_changed_at"] or r["last_status_change"]
                stale = is_check_stale(last_chk, interval_sec=interval)

                result.append({
                    "id": r["id"],
                    "name": r["name"],
                    "identity": r["device_identity"] or r["identity"] or "",
                    "name_source": r["name_source"] or "unknown",
                    "ip": r["ip"] or "",
                    "mac": r["mac"] or "",
                    "device_type": r["device_type"] or "router",
                    "ownership_status": r["ownership_status"] or "unknown",
                    "management_mode": r["management_mode"] or "unmanaged",
                    "monitoring_enabled": bool(r["monitoring_enabled"] if r["monitoring_enabled"] is not None else 1),
                    "is_paused": bool(r["is_paused"]),
                    "maintenance_mode": bool(r["maintenance_mode"]),
                    "status": r["nms_status"] or "UNKNOWN",
                    "latency_ms": r["latency_ms"] or 0.0,
                    "last_check_at": last_chk,
                    "last_polled_at": last_chk,
                    "last_success_at": last_succ,
                    "last_successful_poll_at": last_succ,
                    "status_changed_at": st_changed,
                    "last_status_change": st_changed,
                    "consecutive_failures": r["consecutive_failures"] or 0,
                    "consecutive_successes": r["consecutive_successes"] or 0,
                    "monitoring_method": r["monitoring_method"] or "icmp_ping",
                    "outage_started_at": r["outage_started_at"],
                    "last_error": r["last_error"] or "",
                    "is_stale": stale,
                    "routeros_version": r["routeros_version"] or "",
                    "routeros_model": r["routeros_model"] or "",
                    "metrics_summary": metrics_summary,
                    "snmp_enabled": bool(r["snmp_enabled"]),
                })
            return result

    def get_device_detail(self, device_id: str) -> Optional[Dict[str, Any]]:
        settings = self.get_settings()
        interval = int(settings.get("default_interval_sec", 15))

        with self._lock, closing(self._get_connection()) as conn:
            node = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (device_id,)).fetchone()
            if not node:
                return None

            profile = conn.execute("SELECT * FROM nms_device_profiles WHERE device_id = ?", (device_id,)).fetchone()
            if not profile:
                conn.execute("INSERT OR IGNORE INTO nms_device_profiles (device_id, updated_at) VALUES (?, ?)", (device_id, time.time()))
                conn.commit()
                profile = conn.execute("SELECT * FROM nms_device_profiles WHERE device_id = ?", (device_id,)).fetchone()

            # Latest device metrics
            latest_m = conn.execute(
                "SELECT * FROM nms_device_metrics WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1",
                (device_id,),
            ).fetchone()

            # Current interfaces
            ifaces = conn.execute(
                """
                SELECT m1.*
                FROM nms_interface_metrics m1
                INNER JOIN (
                    SELECT interface_name, MAX(timestamp) as max_ts
                    FROM nms_interface_metrics
                    WHERE device_id = ?
                    GROUP BY interface_name
                ) m2 ON m1.interface_name = m2.interface_name AND m1.timestamp = m2.max_ts
                WHERE m1.device_id = ?
                ORDER BY m1.interface_name
                """,
                (device_id, device_id),
            ).fetchall()

            # Active incidents
            incidents = conn.execute(
                "SELECT * FROM nms_incidents WHERE device_id = ? ORDER BY started_at DESC LIMIT 10",
                (device_id,),
            ).fetchall()

            metrics_summary = {}
            try:
                metrics_summary = json.loads(profile["metrics_summary_json"] or "{}")
            except Exception:
                pass

            last_chk = profile["last_check_at"] or profile["last_polled_at"]
            last_succ = profile["last_success_at"] or profile["last_successful_poll_at"]
            st_changed = profile["status_changed_at"] or profile["last_status_change"]
            stale = is_check_stale(last_chk, interval_sec=interval)

            formatted_interfaces = []
            for i in ifaces:
                formatted_interfaces.append({
                    "interface_name": i["interface_name"],
                    "interface_type": i["interface_type"] if "interface_type" in i.keys() and i["interface_type"] else "unknown",
                    "admin_status": i["admin_status"] if "admin_status" in i.keys() and i["admin_status"] else "enabled",
                    "oper_status": i["oper_status"] or "unknown",
                    "mac_address": i["mac_address"] if "mac_address" in i.keys() else "",
                    "negotiated_speed_bps": i["negotiated_speed_bps"] if "negotiated_speed_bps" in i.keys() else None,
                    "maximum_capability_bps": i["maximum_capability_bps"] if "maximum_capability_bps" in i.keys() else None,
                    "reported_speed_bps": i["reported_speed_bps"] if "reported_speed_bps" in i.keys() else i["speed_bps"],
                    "speed_bps": (i["negotiated_speed_bps"] if "negotiated_speed_bps" in i.keys() and i["negotiated_speed_bps"] else (i["speed_bps"] or 0)),
                    "speed_source": i["speed_source"] if "speed_source" in i.keys() else "unknown",
                    "speed_updated_at": i["speed_updated_at"] if "speed_updated_at" in i.keys() else None,
                    "duplex": i["duplex"] if "duplex" in i.keys() else "unknown",
                    "rx_rate_bps": i["rx_rate_bps"] or 0.0,
                    "tx_rate_bps": i["tx_rate_bps"] or 0.0,
                    "rx_utilization_percent": i["rx_utilization_percent"],
                    "tx_utilization_percent": i["tx_utilization_percent"],
                    "in_octets": i["in_octets"],
                    "out_octets": i["out_octets"],
                    "in_errors": i["in_errors"] or 0,
                    "out_errors": i["out_errors"] or 0,
                    "in_drops": i["in_drops"] if "in_drops" in i.keys() else 0,
                    "out_drops": i["out_drops"] if "out_drops" in i.keys() else 0,
                    "timestamp": i["timestamp"],
                })

            return {
                "id": node["id"],
                "name": node["name"],
                "identity": profile["device_identity"] or node["identity"] or "",
                "name_source": profile["name_source"] or "unknown",
                "ip": node["ip"] or "",
                "mac": node["mac"] or "",
                "device_type": node["device_type"] or "router",
                "ownership_status": node["ownership_status"] or "unknown",
                "profile": {
                    "management_mode": profile["management_mode"] or "unmanaged",
                    "monitoring_enabled": bool(profile["monitoring_enabled"]),
                    "is_paused": bool(profile["is_paused"]),
                    "maintenance_mode": bool(profile["maintenance_mode"]),
                    "snmp_enabled": bool(profile["snmp_enabled"]),
                    "snmp_version": profile["snmp_version"] or "v2c",
                    "snmp_port": profile["snmp_port"] or 161,
                    "has_community": bool(profile["snmp_community"]),
                    "status": profile["status"] or "UNKNOWN",
                    "consecutive_failures": profile["consecutive_failures"] or 0,
                    "consecutive_successes": profile["consecutive_successes"] or 0,
                    "latency_ms": profile["latency_ms"] or 0.0,
                    "last_check_at": last_chk,
                    "last_polled_at": last_chk,
                    "last_success_at": last_succ,
                    "last_successful_poll_at": last_succ,
                    "status_changed_at": st_changed,
                    "last_status_change": st_changed,
                    "monitoring_method": profile["monitoring_method"] or "icmp_ping",
                    "name_source": profile["name_source"] or "unknown",
                    "device_identity": profile["device_identity"] or "",
                    "routeros_version": profile["routeros_version"] or "",
                    "routeros_model": profile["routeros_model"] or "",
                    "outage_started_at": profile["outage_started_at"],
                    "last_error": profile["last_error"] or "",
                    "is_stale": stale,
                    "metrics_summary": metrics_summary,
                },
                "latest_metrics": dict(latest_m) if latest_m else None,
                "interfaces": formatted_interfaces,
                "incidents": [dict(inc) for inc in incidents],
            }

    def upsert_device_profile(
        self,
        device_id: str,
        display_name: Optional[str] = None,
        host: Optional[str] = None,
        management_method: Optional[str] = None,
        management_mode: str = "managed",
        snmp_community: Optional[str] = None,
        snmp_port: int = 161,
        snmp_enabled: bool = False,
        **kwargs,
    ) -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            now = time.time()
            conn.execute(
                """
                INSERT INTO nms_device_profiles (
                    device_id, management_mode, monitoring_enabled,
                    snmp_enabled, snmp_community, snmp_port,
                    status, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?, 'UNKNOWN', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    management_mode = excluded.management_mode,
                    snmp_enabled = excluded.snmp_enabled,
                    snmp_community = coalesce(excluded.snmp_community, nms_device_profiles.snmp_community),
                    snmp_port = excluded.snmp_port,
                    updated_at = excluded.updated_at
                """,
                (
                    device_id,
                    management_mode,
                    1 if (snmp_enabled or snmp_community) else 0,
                    snmp_community,
                    snmp_port,
                    now,
                ),
            )
            conn.commit()
            return True

    def update_device_profile(self, device_id: str, updates: Dict[str, Any]) -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            fields = []
            values = []
            allowed = {
                "management_mode", "monitoring_enabled", "is_paused", "maintenance_mode",
                "snmp_enabled", "snmp_version", "snmp_community", "snmp_port",
                "snmp_v3_user", "snmp_v3_auth_proto", "snmp_v3_auth_key",
                "snmp_v3_priv_proto", "snmp_v3_priv_key", "routeros_api_enabled",
            }
            for k, v in updates.items():
                if k in allowed:
                    fields.append(f"{k} = ?")
                    values.append(v)
            if not fields:
                return False

            fields.append("updated_at = ?")
            values.append(time.time())
            values.append(device_id)

            conn.execute(f"UPDATE nms_device_profiles SET {', '.join(fields)} WHERE device_id = ?", values)
            conn.commit()
            return True

    # -----------------------------------------------------------------------
    # Historical Metrics Queries
    # -----------------------------------------------------------------------
    def get_resource_history(self, device_id: str, time_range: str = "1h") -> List[Dict[str, Any]]:
        seconds = 3600
        if time_range == "15m":
            seconds = 900
        elif time_range == "24h":
            seconds = 86400
        elif time_range == "7d":
            seconds = 604800

        cutoff = time.time() - seconds
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, cpu_load_percent, memory_used_percent, latency_ms, temperature_celsius
                FROM nms_device_metrics
                WHERE device_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (device_id, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_interface_history(
        self, device_id: str, interface_name: str, time_range: str = "1h"
    ) -> List[Dict[str, Any]]:
        seconds = 3600
        if time_range == "15m":
            seconds = 900
        elif time_range == "24h":
            seconds = 86400
        elif time_range == "7d":
            seconds = 604800

        cutoff = time.time() - seconds
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, rx_rate_bps, tx_rate_bps, rx_utilization_percent, tx_utilization_percent, oper_status
                FROM nms_interface_metrics
                WHERE device_id = ? AND interface_name = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (device_id, interface_name, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Incidents Management
    # -----------------------------------------------------------------------
    def list_incidents(
        self, status: Optional[str] = "open", limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self._lock, closing(self._get_connection()) as conn:
            query = """
                SELECT i.*, n.name as device_name, n.ip as device_ip
                FROM nms_incidents i
                LEFT JOIN topology_nodes n ON i.device_id = n.id
                WHERE 1=1
            """
            params: List[Any] = []
            if status and status != "all":
                query += " AND i.status = ?"
                params.append(status)
            query += " ORDER BY i.started_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def acknowledge_incident(self, incident_id: int, user: str = "admin") -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                "UPDATE nms_incidents SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by = ? WHERE id = ?",
                (time.time(), user, incident_id),
            )
            conn.commit()
            return True

    def _open_incident_if_not_exists(
        self, conn: sqlite3.Connection, device_id: str, inc_type: str, severity: str, title: str, details: str
    ) -> None:
        existing = conn.execute(
            "SELECT id FROM nms_incidents WHERE device_id = ? AND incident_type = ? AND status = 'open'",
            (device_id, inc_type),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO nms_incidents (device_id, incident_type, severity, title, details, status, started_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (device_id, inc_type, severity, title, details, time.time()),
            )

    def _resolve_incident_if_open(
        self, conn: sqlite3.Connection, device_id: str, inc_type: str, recovery_details: str
    ) -> None:
        open_incs = conn.execute(
            "SELECT id FROM nms_incidents WHERE device_id = ? AND incident_type = ? AND status IN ('open', 'acknowledged')",
            (device_id, inc_type),
        ).fetchall()
        now = time.time()
        for inc in open_incs:
            conn.execute(
                "UPDATE nms_incidents SET status = 'resolved', resolved_at = ?, details = details || '\n[RECOVERED]: ' || ? WHERE id = ?",
                (now, recovery_details, inc["id"]),
            )

    # -----------------------------------------------------------------------
    # SNMP Setup Wizard
    # -----------------------------------------------------------------------
    async def wizard_detect_snmp(
        self, host: str, port: int = 161, community: str = "public", version: str = "v2c"
    ) -> Dict[str, Any]:
        """Langkah 1 Wizard: Deteksi ketersediaan port UDP 161 dan SNMP handshake."""
        # 1. Cek ping dulu
        ping_res = bounded_icmp_ping(host, count=1, timeout_sec=1.5)
        if not ping_res["alive"]:
            return {
                "reachable": False,
                "snmp_responding": False,
                "message": f"Host {host} tidak merespons ICMP ping.",
            }

        # 2. Cek SNMP GET OID_SYS_DESCR
        data, err = await snmp_get_multi(
            host=host, port=port, community=community, version=version, oids={"sys_descr": "1.3.6.1.2.1.1.1.0"}, timeout=2.0
        )
        if data and "sys_descr" in data and data["sys_descr"]:
            return {
                "reachable": True,
                "snmp_responding": True,
                "sys_descr": data["sys_descr"],
                "message": "SNMP aktif dan merespons dengan benar.",
            }

        return {
            "reachable": True,
            "snmp_responding": False,
            "error": err or "Timeout menunggu respons SNMP.",
            "message": "Host terjangkau via ping, tetapi SNMP belum merespons.",
        }

    def wizard_generate_commands(
        self,
        community_name: str = "aira-ro",
        allowed_collector_ip: str = "192.168.0.0/24",
        use_v3: bool = False,
        v3_user: str = "aira-mgr",
        v3_auth_key: str = "AiraAuthPass123",
        v3_priv_key: str = "AiraPrivPass123",
    ) -> List[str]:
        """Langkah 3 Wizard: Menghasilkan perintah konfigurasi aman RouterOS (hanya read-only)."""
        cmds = []
        if use_v3:
            cmds.extend([
                "# 1. Aktifkan SNMP Service di MikroTik",
                "/snmp set enabled=yes",
                "# 2. Tambah SNMPv3 Read-Only Community Profile dengan Auth SHA & Priv AES",
                f'/snmp community add name="{community_name}" security=private read-access=yes write-access=no authentication-protocol=SHA authentication-password="{v3_auth_key}" encryption-protocol=AES encryption-password="{v3_priv_key}" addresses="{allowed_collector_ip}"',
            ])
        else:
            cmds.extend([
                "# 1. Aktifkan SNMP Service di MikroTik",
                "/snmp set enabled=yes",
                "# 2. Matikan community bawaan 'public' yang rentan",
                '/snmp community set [find default=yes] disabled=yes',
                "# 3. Buat read-only community khusus terisolasi ke IP kolektor AIRA",
                f'/snmp community add name="{community_name}" read-access=yes write-access=no addresses="{allowed_collector_ip}"',
            ])
        return cmds

    async def wizard_verify_and_save(
        self,
        device_id: str,
        host: str,
        port: int = 161,
        community: str = "aira-ro",
        version: str = "v2c",
    ) -> Dict[str, Any]:
        """Langkah 4 & 5 Wizard: Verifikasi metrik dan simpan profile termonitor."""
        poll_res = await poll_device_snmp_full(host=host, port=port, community=community, version=version, timeout=3.5)
        if not poll_res["success"]:
            return {
                "success": False,
                "error": poll_res["error"] or "Gagal memverifikasi metrik SNMP.",
            }

        # Simpan profil termonitor
        self.update_device_profile(
            device_id,
            {
                "management_mode": "managed",
                "snmp_enabled": 1,
                "snmp_version": version,
                "snmp_community": community,
                "snmp_port": port,
                "monitoring_enabled": 1,
                "is_paused": 0,
            },
        )
        return {
            "success": True,
            "identity": poll_res.get("identity"),
            "cpu_load_percent": poll_res.get("cpu_load_percent"),
            "memory_used_percent": poll_res.get("memory_used_percent"),
            "interfaces_count": len(poll_res.get("interfaces", [])),
            "message": "Monitoring SNMP berhasil diverifikasi dan diaktifkan!",
        }

    # -----------------------------------------------------------------------
    # RouterOS Dynamic Interrogation
    # -----------------------------------------------------------------------
    def _poll_device_routeros_sync(
        self,
        host: str,
        device_name: Optional[str] = None,
        conn_mgr: Any = None,
        inv_store: Any = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Interrogates an authorized RouterOS device via SSH / ConnectionManager.
        Fetches real dynamic identity, resources, hardware model, dynamic interfaces,
        and ethernet link speed & duplex without modifying state.
        """
        try:
            from agents.akane.connection_manager import get_connection_manager
            from core.inventory_store import get_inventory_store
        except ImportError as e:
            return {"success": False, "error": f"Failed to import connection modules: {e}"}

        inv = inv_store or get_inventory_store()
        target_name = (device_name or host or "").strip()

        # Try resolving device in inventory
        ssh_target = {"success": False}
        try:
            ssh_target = inv.resolve_ssh(target_name)
        except Exception:
            pass

        if not ssh_target.get("success") and host and host != target_name:
            try:
                ssh_target = inv.resolve_ssh(host)
            except Exception:
                pass

        if not ssh_target.get("success"):
            return {"success": False, "error": f"Device '{target_name}' not found in inventory with SSH credentials"}

        mgr = conn_mgr or get_connection_manager()
        resolved_dev_name = ssh_target.get("name") or target_name

        def _exec(cmd: str) -> Tuple[bool, str, str]:
            try:
                res = mgr.execute_command(cmd, device_name=resolved_dev_name, host=host, timeout=timeout)
                if not res.get("success"):
                    return False, "", res.get("error", "Execution failed")
                return True, res.get("output", ""), ""
            except Exception as ex:
                return False, "", str(ex)

        ok_id, raw_id, err_id = _exec("/system identity print")
        if not ok_id:
            return {"success": False, "error": err_id or f"Identity query failed on {resolved_dev_name}"}

        identity = parse_mikrotik_identity(raw_id)

        _, raw_res, _ = _exec("/system resource print")
        resource_info = parse_mikrotik_resource(raw_res)

        _, raw_rb, _ = _exec("/system routerboard print")
        rb_info = parse_mikrotik_routerboard(raw_rb)

        _, raw_if, _ = _exec("/interface print detail")
        parsed_ifaces = parse_mikrotik_interfaces(raw_if)

        _, raw_eth, _ = _exec("/interface ethernet print detail")
        parsed_eth = parse_mikrotik_ethernet(raw_eth)

        formatted_interfaces: List[Dict[str, Any]] = []
        now = time.time()
        for if_name, if_data in parsed_ifaces.items():
            eth = parsed_eth.get(if_name, {})
            running = bool(if_data.get("running"))
            disabled = bool(if_data.get("disabled"))

            admin_st = "disabled" if disabled else "enabled"
            if disabled:
                oper_st = "disabled"
            elif running:
                oper_st = "up"
            else:
                oper_st = "down"

            neg_speed = eth.get("negotiated_speed_bps") if (running and not disabled) else None
            speed_src = eth.get("speed_source", "unknown") if neg_speed is not None else "unknown"
            duplex = eth.get("duplex", "unknown") if (running and not disabled) else "unknown"

            formatted_interfaces.append({
                "name": if_name,
                "interface_type": if_data.get("type", "ether"),
                "admin_status": admin_st,
                "oper_status": oper_st,
                "mac_address": eth.get("mac") or if_data.get("mac", ""),
                "negotiated_speed_bps": neg_speed,
                "maximum_capability_bps": None,
                "reported_speed_bps": neg_speed,
                "speed_bps": neg_speed or 0,
                "speed_source": speed_src,
                "speed_updated_at": now if neg_speed is not None else None,
                "duplex": duplex,
                "in_octets": if_data.get("rx_byte") or 0,
                "out_octets": if_data.get("tx_byte") or 0,
                "in_errors": if_data.get("rx_error", 0),
                "out_errors": if_data.get("tx_error", 0),
                "in_drops": if_data.get("rx_drop", 0),
                "out_drops": if_data.get("tx_drop", 0),
            })

        model = rb_info.get("model") or resource_info.get("board_name") or ""
        version = resource_info.get("version") or ""

        return {
            "success": True,
            "identity": identity,
            "version": version,
            "model": model,
            "resource": resource_info,
            "routerboard": rb_info,
            "interfaces": formatted_interfaces,
            "cpu_load_percent": resource_info.get("cpu_load_percent"),
            "memory_used_percent": resource_info.get("memory_used_percent"),
            "total_memory_bytes": resource_info.get("total_memory_bytes"),
            "used_memory_bytes": resource_info.get("used_memory_bytes"),
            "uptime": resource_info.get("uptime"),
        }

    async def poll_device_routeros(
        self, host: str, device_name: Optional[str] = None, timeout: float = 5.0
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._poll_device_routeros_sync,
            host=host,
            device_name=device_name,
            timeout=timeout,
        )

    # -----------------------------------------------------------------------
    # Device Polling Execution Cycle
    # -----------------------------------------------------------------------
    async def poll_single_device(
        self, device_id: str, host: str, profile: Dict[str, Any], settings: Dict[str, Any]
    ) -> None:
        """Melakukan pemeriksaan health check (ICMP + RouterOS SSH / SNMP) untuk 1 perangkat dan mencatat hasilnya."""
        ping_timeout = float(settings.get("ping_timeout_sec", 2.0))
        snmp_timeout = float(settings.get("snmp_timeout_sec", 3.0))
        fail_thresh = int(settings.get("failure_threshold", 3))
        recov_thresh = int(settings.get("recovery_threshold", 2))

        # 1. ICMP Ping Check
        ping_res = await asyncio.to_thread(bounded_icmp_ping, host, 1, ping_timeout)
        ping_ok = ping_res["alive"]
        latency_ms = ping_res.get("avg_rtt_ms") or ping_res.get("rtt_ms") or 0.0

        # 2. Management / Telemetry Interrogation
        is_managed = profile.get("management_mode") == "managed"
        snmp_enabled = bool(profile.get("snmp_enabled"))
        routeros_enabled = bool(profile.get("routeros_api_enabled", True))
        snmp_comm = profile.get("snmp_community") or "public"
        snmp_port = int(profile.get("snmp_port") or 161)
        snmp_ver = profile.get("snmp_version") or "v2c"

        routeros_res: Optional[Dict[str, Any]] = None
        snmp_res: Optional[Dict[str, Any]] = None
        mgmt_ok: Optional[bool] = None

        verified_identity: Optional[str] = None
        snmp_sys_name: Optional[str] = None
        routeros_version: str = ""
        routeros_model: str = ""
        interfaces_to_save: List[Dict[str, Any]] = []
        monitoring_method: str = "icmp_ping"
        last_error: str = ""

        if ping_ok:
            # Query RouterOS SSH if managed or routeros enabled
            if is_managed or routeros_enabled:
                try:
                    routeros_res = await self.poll_device_routeros(
                        host=host,
                        device_name=profile.get("name"),
                        timeout=min(ping_timeout + 3.0, 5.0),
                    )
                except Exception as ex:
                    routeros_res = {"success": False, "error": str(ex)}

            # Query SNMP if enabled
            if snmp_enabled:
                try:
                    snmp_res = await poll_device_snmp_full(
                        host=host, port=snmp_port, community=snmp_comm, version=snmp_ver, timeout=snmp_timeout
                    )
                except Exception as ex:
                    snmp_res = {"success": False, "error": str(ex)}

            # Evaluate management availability and collect telemetry
            if routeros_res and routeros_res.get("success"):
                mgmt_ok = True
                monitoring_method = "routeros_ssh"
                verified_identity = routeros_res.get("identity")
                routeros_version = routeros_res.get("version", "")
                routeros_model = routeros_res.get("model", "")
                interfaces_to_save = routeros_res.get("interfaces", [])
            elif snmp_res and snmp_res.get("success"):
                mgmt_ok = True
                monitoring_method = f"snmp_{snmp_ver}"
                snmp_sys_name = snmp_res.get("identity")
                interfaces_to_save = snmp_res.get("interfaces", [])
            elif is_managed:
                mgmt_ok = False
                errs = []
                if routeros_res and not routeros_res.get("success"):
                    errs.append(routeros_res.get("error", "RouterOS interrogation error"))
                if snmp_res and not snmp_res.get("success"):
                    errs.append(snmp_res.get("error", "SNMP request error"))
                last_error = "; ".join(errs) or "Management services unreachable"
        else:
            last_error = f"ICMP ping timeout ({ping_timeout}s)"

        # 3. Read current status & counters atomically from database
        with self._lock, closing(self._get_connection()) as conn:
            db_row = conn.execute(
                """
                SELECT status, consecutive_failures, consecutive_successes, is_paused,
                       maintenance_mode, outage_started_at, last_status_change, last_successful_poll_at,
                       last_success_at
                FROM nms_device_profiles WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()

            node_row = conn.execute(
                "SELECT name, identity, user_overrides_json, metadata_json FROM topology_nodes WHERE id = ?",
                (device_id,),
            ).fetchone()

        if db_row:
            curr_status = db_row["status"] or "UNKNOWN"
            consec_fails = db_row["consecutive_failures"] or 0
            consec_succs = db_row["consecutive_successes"] or 0
            is_paused = bool(db_row["is_paused"])
            is_maintenance = bool(db_row["maintenance_mode"])
            outage_started = db_row["outage_started_at"]
            last_change = db_row["last_status_change"]
            last_succ_poll = db_row["last_success_at"] or db_row["last_successful_poll_at"]
        else:
            curr_status = profile.get("status", "UNKNOWN")
            consec_fails = profile.get("consecutive_failures", 0)
            consec_succs = profile.get("consecutive_successes", 0)
            is_paused = bool(profile.get("is_paused"))
            is_maintenance = bool(profile.get("maintenance_mode"))
            outage_started = profile.get("outage_started_at")
            last_change = profile.get("last_status_change")
            last_succ_poll = profile.get("last_success_at") or profile.get("last_successful_poll_at")

        # 4. Determine display name according to strict precedence rules
        user_override: Optional[str] = None
        current_node_name: str = profile.get("name", "")
        if node_row:
            try:
                overrides = json.loads(node_row["user_overrides_json"] or "{}")
                user_override = overrides.get("name")
            except Exception:
                pass
            if not current_node_name:
                current_node_name = node_row["name"]

        resolved_name, name_source = resolve_device_display_name(
            user_override=user_override,
            verified_identity=verified_identity,
            snmp_sys_name=snmp_sys_name,
            inventory_name=profile.get("name") or current_node_name,
            ip=host,
        )

        # 5. Availability State Machine Transition
        new_status, new_fails, new_succs = determine_device_availability(
            current_status=curr_status,
            consecutive_failures=consec_fails,
            consecutive_successes=consec_succs,
            ping_ok=ping_ok,
            management_ok=mgmt_ok,
            is_managed=is_managed,
            failure_threshold=fail_thresh,
            recovery_threshold=recov_thresh,
            is_paused=is_paused,
            is_maintenance=is_maintenance,
        )

        now = time.time()
        if new_status != curr_status:
            last_change = now
            if new_status in ("DOWN", "SUSPECTED_DOWN") and not outage_started:
                outage_started = now
            elif new_status == "UP":
                outage_started = None

        if ping_ok:
            last_succ_poll = now

        metrics_summary: Dict[str, Any] = {}
        if routeros_res and routeros_res.get("success"):
            metrics_summary = {
                "cpu_load_percent": routeros_res.get("cpu_load_percent"),
                "memory_used_percent": routeros_res.get("memory_used_percent"),
                "uptime": routeros_res.get("uptime"),
                "interfaces_count": len(interfaces_to_save),
                "model": routeros_model,
                "version": routeros_version,
            }
        elif snmp_res and snmp_res.get("success"):
            metrics_summary = {
                "cpu_load_percent": snmp_res.get("cpu_load_percent"),
                "memory_used_percent": snmp_res.get("memory_used_percent"),
                "uptime_seconds": snmp_res.get("uptime_seconds"),
                "temperature_celsius": snmp_res.get("temperature_celsius"),
                "interfaces_count": len(interfaces_to_save),
            }

        # 6. Update Database: nms_device_profiles AND topology_nodes
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                """
                UPDATE nms_device_profiles SET
                    status = ?,
                    consecutive_failures = ?,
                    consecutive_successes = ?,
                    latency_ms = ?,
                    last_polled_at = ?,
                    last_check_at = ?,
                    last_successful_poll_at = ?,
                    last_success_at = ?,
                    last_status_change = ?,
                    status_changed_at = ?,
                    outage_started_at = ?,
                    last_error = ?,
                    monitoring_method = ?,
                    name_source = ?,
                    device_identity = CASE WHEN ? != '' THEN ? ELSE device_identity END,
                    routeros_version = CASE WHEN ? != '' THEN ? ELSE routeros_version END,
                    routeros_model = CASE WHEN ? != '' THEN ? ELSE routeros_model END,
                    metrics_summary_json = ?,
                    updated_at = ?
                WHERE device_id = ?
                """,
                (
                    new_status,
                    new_fails,
                    new_succs,
                    latency_ms,
                    now,
                    now,
                    last_succ_poll,
                    last_succ_poll,
                    last_change,
                    last_change,
                    outage_started,
                    last_error,
                    monitoring_method,
                    name_source,
                    verified_identity or "",
                    verified_identity or "",
                    routeros_version,
                    routeros_version,
                    routeros_model,
                    routeros_model,
                    json.dumps(metrics_summary),
                    now,
                    device_id,
                ),
            )

            # Synchronize real-time state into topology_nodes
            topo_status = "offline" if new_status == "DOWN" else ("online" if new_status == "UP" else "warning")
            topo_reach = "unreachable" if new_status == "DOWN" else ("suspected_down" if new_status == "SUSPECTED_DOWN" else ("reachable" if ping_ok else "unknown"))
            topo_mgmt = "managed" if mgmt_ok is True else ("management_unavailable" if mgmt_ok is False else "not_attempted")
            avail_reason = f"NMS Health: {new_status}. {last_error}".strip()

            topo_meta: Dict[str, Any] = {}
            if node_row:
                try:
                    topo_meta = json.loads(node_row["metadata_json"] or "{}")
                except Exception:
                    topo_meta = {}
            topo_meta["nms_status"] = new_status
            topo_meta["name_source"] = name_source
            if routeros_version:
                topo_meta["routeros_version"] = routeros_version
            if routeros_model:
                topo_meta["routeros_model"] = routeros_model

            # Determine whether node name in topology_nodes should be updated
            # Never overwrite manual user overrides!
            new_node_name = user_override or (resolved_name if name_source != "fallback" else (node_row["name"] if node_row else resolved_name))
            new_node_ident = verified_identity or (node_row["identity"] if node_row and node_row["identity"] else "")

            conn.execute(
                """
                UPDATE topology_nodes SET
                    name = ?,
                    identity = ?,
                    status = ?,
                    reachability_status = ?,
                    management_status = ?,
                    observation_freshness = 'fresh',
                    availability_reason = ?,
                    latency_ms = ?,
                    last_probe_at = ?,
                    last_ping_alive = ?,
                    last_seen = CASE WHEN ? = 1 THEN ? ELSE last_seen END,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    new_node_name,
                    new_node_ident,
                    topo_status,
                    topo_reach,
                    topo_mgmt,
                    avail_reason,
                    latency_ms,
                    now,
                    1 if ping_ok else 0,
                    1 if ping_ok else 0,
                    now,
                    json.dumps(topo_meta),
                    device_id,
                ),
            )

            # Record device metrics history if ping succeeded
            if ping_ok:
                conn.execute(
                    """
                    INSERT INTO nms_device_metrics (
                        device_id, timestamp, cpu_load_percent, memory_used_bytes, memory_total_bytes,
                        memory_used_percent, storage_used_bytes, storage_total_bytes, temperature_celsius,
                        uptime_seconds, latency_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        now,
                        metrics_summary.get("cpu_load_percent"),
                        routeros_res.get("used_memory_bytes") if routeros_res else (snmp_res.get("memory_used_bytes") if snmp_res else None),
                        routeros_res.get("total_memory_bytes") if routeros_res else (snmp_res.get("memory_total_bytes") if snmp_res else None),
                        metrics_summary.get("memory_used_percent"),
                        snmp_res.get("storage_used_bytes") if snmp_res else None,
                        snmp_res.get("storage_total_bytes") if snmp_res else None,
                        snmp_res.get("temperature_celsius") if snmp_res else None,
                        (
                            snmp_res.get("uptime_seconds")
                            if (snmp_res and snmp_res.get("uptime_seconds") is not None)
                            else (
                                routeros_res.get("uptime_seconds")
                                if (routeros_res and routeros_res.get("uptime_seconds") is not None)
                                else (
                                    parse_uptime_to_seconds(routeros_res.get("uptime"))
                                    if routeros_res
                                    else None
                                )
                            )
                        ),
                        latency_ms,
                    ),
                )

            # Save dynamic interfaces & calculate delta rates
            if interfaces_to_save:
                for iface in interfaces_to_save:
                    iname = iface.get("name") or iface.get("interface_name")
                    if not iname:
                        continue

                    prev_s = conn.execute(
                        """
                        SELECT timestamp, in_octets, out_octets, speed_bps, negotiated_speed_bps
                        FROM nms_interface_metrics
                        WHERE device_id = ? AND interface_name = ?
                        ORDER BY timestamp DESC LIMIT 1
                        """,
                        (device_id, iname),
                    ).fetchone()

                    neg_speed = iface.get("negotiated_speed_bps")
                    speed = iface.get("speed_bps", 0)
                    effective_speed = neg_speed if neg_speed is not None else speed

                    rx_rate = 0.0
                    tx_rate = 0.0
                    rx_util = None
                    tx_util = None

                    curr_in = iface.get("in_octets", 0)
                    curr_out = iface.get("out_octets", 0)

                    if prev_s:
                        prev_speed = prev_s["negotiated_speed_bps"] if prev_s["negotiated_speed_bps"] is not None else prev_s["speed_bps"]
                        calc_speed = effective_speed or prev_speed
                        rx_rate, rx_util = calculate_traffic_rate(
                            curr_octets=curr_in,
                            prev_octets=prev_s["in_octets"],
                            curr_time=now,
                            prev_time=prev_s["timestamp"],
                            speed_bps=calc_speed,
                        )
                        tx_rate, tx_util = calculate_traffic_rate(
                            curr_octets=curr_out,
                            prev_octets=prev_s["out_octets"],
                            curr_time=now,
                            prev_time=prev_s["timestamp"],
                            speed_bps=calc_speed,
                        )

                    conn.execute(
                        """
                        INSERT INTO nms_interface_metrics (
                            device_id, interface_name, timestamp, oper_status, speed_bps,
                            in_octets, out_octets, rx_rate_bps, tx_rate_bps, rx_utilization_percent,
                            tx_utilization_percent, in_errors, out_errors,
                            admin_status, interface_type, mac_address, negotiated_speed_bps,
                            maximum_capability_bps, reported_speed_bps, speed_source,
                            speed_updated_at, duplex, in_drops, out_drops
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            device_id,
                            iname,
                            now,
                            iface.get("oper_status", "unknown"),
                            effective_speed or 0,
                            curr_in,
                            curr_out,
                            rx_rate,
                            tx_rate,
                            rx_util,
                            tx_util,
                            iface.get("in_errors", 0),
                            iface.get("out_errors", 0),
                            iface.get("admin_status", "enabled"),
                            iface.get("interface_type", "ether"),
                            iface.get("mac_address", ""),
                            neg_speed,
                            iface.get("maximum_capability_bps"),
                            iface.get("reported_speed_bps") or effective_speed,
                            iface.get("speed_source", "unknown"),
                            iface.get("speed_updated_at") or (now if neg_speed is not None else None),
                            iface.get("duplex", "unknown"),
                            iface.get("in_drops", 0),
                            iface.get("out_drops", 0),
                        ),
                    )

            # 7. Incident Handling (Down & Recovery)
            dev_name = resolved_name or profile.get("name") or host
            if new_status == "DOWN" and curr_status != "DOWN":
                self._open_incident_if_not_exists(
                    conn,
                    device_id,
                    inc_type="device_down",
                    severity="critical",
                    title=f"Perangkat {dev_name} Tidak Terjangkau (DOWN)",
                    details=f"Gagal merespons {new_fails}x check berturut-turut. Error terakhir: {last_error}",
                )
            elif new_status == "UP" and curr_status in ("DOWN", "SUSPECTED_DOWN"):
                self._resolve_incident_if_open(
                    conn,
                    device_id,
                    inc_type="device_down",
                    recovery_details=f"Koneksi pulih normal. Latency: {latency_ms:.1f}ms",
                )

            conn.commit()

            # Publish real-time NMS device status event
            try:
                event_bus.publish(
                    EventNames.NMS_DEVICE_STATUS,
                    data={
                        "device_id": device_id,
                        "name": resolved_name or dev_name,
                        "ip": host,
                        "status": new_status,
                        "previous_status": curr_status,
                        "latency_ms": latency_ms,
                        "metrics": metrics_summary,
                        "timestamp": now,
                        "monitoring_method": monitoring_method,
                    },
                )
            except Exception as exc:
                logger.debug("Failed to publish NMS_DEVICE_STATUS: %s", exc)

            if new_status == "DOWN" and curr_status != "DOWN":
                try:
                    event_bus.publish(
                        EventNames.NMS_INCIDENT,
                        data={
                            "device_id": device_id,
                            "device_name": dev_name,
                            "type": "device_down",
                            "status": "open",
                            "severity": "critical",
                            "timestamp": now,
                        },
                    )
                except Exception:
                    pass
            elif new_status == "UP" and curr_status in ("DOWN", "SUSPECTED_DOWN"):
                try:
                    event_bus.publish(
                        EventNames.NMS_INCIDENT,
                        data={
                            "device_id": device_id,
                            "device_name": dev_name,
                            "type": "device_down",
                            "status": "resolved",
                            "timestamp": now,
                        },
                    )
                except Exception:
                    pass

    async def poll_all_devices_cycle(self) -> None:
        """Menjalankan 1 siklus polling penuh untuk seluruh perangkat yang aktif."""
        async with self._async_lock:
            if self._is_polling:
                logger.warning("Polling cycle sebelumnya masih berjalan — melewati siklus ini (single-flight lock).")
                return
            self._is_polling = True

        try:
            settings = self.get_settings()
            max_concurrency = int(settings.get("max_concurrent_polls", 10))
            sem = asyncio.Semaphore(max_concurrency)

            # Auto-sync any discovered nodes with IP into nms_device_profiles
            with self._lock, closing(self._get_connection()) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO nms_device_profiles (device_id, status, updated_at)
                    SELECT id, 'UNKNOWN', ? FROM topology_nodes WHERE ip IS NOT NULL AND TRIM(ip) != ''
                    """,
                    (time.time(),),
                )
                conn.commit()

                rows = conn.execute(
                    """
                    SELECT n.id, n.name, n.ip, p.*
                    FROM topology_nodes n
                    JOIN nms_device_profiles p ON n.id = p.device_id
                    WHERE p.monitoring_enabled = 1 AND p.is_paused = 0 AND n.ip IS NOT NULL AND TRIM(n.ip) != ''
                    """
                ).fetchall()
                devices = [dict(r) for r in rows]

            async def _bounded_poll(dev: Dict[str, Any]):
                async with sem:
                    try:
                        await self.poll_single_device(
                            device_id=dev["id"], host=dev["ip"], profile=dev, settings=settings
                        )
                    except Exception as exc:
                        logger.error(f"Error saat polling {dev.get('name')}: {exc}")

            if devices:
                await asyncio.gather(*[_bounded_poll(d) for d in devices])

            self.last_poll_timestamp = time.time()
            interval = int(settings.get("default_interval_sec", 15))
            self.next_poll_timestamp = self.last_poll_timestamp + interval

            # Bersihkan metrik lama
            retention_days = int(settings.get("history_retention_days", 7))
            self.prune_expired_metrics(retention_days)

            try:
                event_bus.publish(
                    EventNames.NMS_CYCLE_COMPLETED,
                    data={
                        "overview": self.get_overview(),
                        "timestamp": self.last_poll_timestamp,
                        "next_poll": self.next_poll_timestamp,
                        "device_count": len(devices),
                    },
                )
            except Exception as exc:
                logger.debug("Failed to publish NMS_CYCLE_COMPLETED: %s", exc)
        finally:
            async with self._async_lock:
                self._is_polling = False

    def prune_expired_metrics(self, retention_days: int = 7) -> None:
        """Membersihkan sampel metrik yang lebih tua dari batas retensi."""
        cutoff = time.time() - (retention_days * 86400)
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("DELETE FROM nms_device_metrics WHERE timestamp < ?", (cutoff,))
            conn.execute("DELETE FROM nms_interface_metrics WHERE timestamp < ?", (cutoff,))
            conn.commit()

    # -----------------------------------------------------------------------
    # Background Scheduler Lifecycle
    # -----------------------------------------------------------------------
    def is_running(self) -> bool:
        return self._scheduler_task is not None and not self._scheduler_task.done()

    async def _scheduler_loop(self) -> None:
        logger.info("NMS background scheduler loop started.")
        while not self._stop_event.is_set():
            try:
                settings = self.get_settings()
                if settings.get("auto_monitoring_enabled", True):
                    await self.poll_all_devices_cycle()
                interval = max(5, int(settings.get("default_interval_sec", 15)))
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in NMS scheduler loop: {exc}")
                await asyncio.sleep(5)
        logger.info("NMS background scheduler loop stopped.")

    def start_monitoring(self) -> bool:
        """Memulai background scheduler jika belum berjalan."""
        if self.is_running():
            return True
        self._stop_event.clear()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        self._scheduler_task = loop.create_task(self._scheduler_loop())
        return True

    def stop_monitoring(self) -> bool:
        """Menghentikan background scheduler."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._stop_event.set()
            self._scheduler_task.cancel()
            self._scheduler_task = None
            return True
        return False


_GLOBAL_NMS_ENGINE: Optional[NmsEngine] = None


def get_nms_engine(db_path: Path = DEFAULT_DB_PATH) -> NmsEngine:
    global _GLOBAL_NMS_ENGINE
    if _GLOBAL_NMS_ENGINE is None:
        _GLOBAL_NMS_ENGINE = NmsEngine(db_path)
    return _GLOBAL_NMS_ENGINE
