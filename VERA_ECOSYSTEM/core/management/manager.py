"""
core/management/manager.py — MultiPathManager Singleton for Unified Device Management.

Provides:
- SQLite persistence of DeviceManagementProfile and administrative path overrides
- Testing connectivity across candidate paths (SSH, API, MAC Telnet, RoMON)
- RoMON neighbor aggregation across discovered gateways
- Integration with AKANE connection manager and NMS engine
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.management.models import (
    DeviceManagementProfile,
    ManagementMethod,
    ManagementPath,
    PathStatus,
    RomonNeighbor,
)
from core.management.selection_engine import SelectionEngine
from core.management.mac_manager import MacManager
from core.management.romon_manager import RomonManager

logger = logging.getLogger("vera.management.manager")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "database" / "management.db"


class MultiPathManager:
    """Central manager for multi-path device management (IP, MAC, RoMON)."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._lock = threading.RLock()
        self._cached_romon_neighbors: Dict[str, RomonNeighbor] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_management_profiles (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    vendor TEXT DEFAULT 'MikroTik',
                    model TEXT DEFAULT '',
                    routeros_version TEXT DEFAULT '',
                    ip TEXT,
                    mac TEXT,
                    preferred_method TEXT,
                    manual_selection INTEGER DEFAULT 0,
                    active_method TEXT,
                    paths_json TEXT,
                    selection_rationale TEXT,
                    romon_enabled INTEGER DEFAULT 0,
                    romon_id TEXT,
                    layer2_adjacent INTEGER DEFAULT 0,
                    adjacent_interface TEXT,
                    updated_at REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS romon_neighbors_cache (
                    romon_id TEXT PRIMARY KEY,
                    mac TEXT NOT NULL,
                    identity TEXT,
                    version TEXT,
                    board TEXT,
                    hop_count INTEGER DEFAULT 1,
                    path_json TEXT,
                    via_device_id TEXT,
                    via_device_name TEXT,
                    discovered_at REAL NOT NULL
                );
            """)
            conn.commit()

    # -----------------------------------------------------------------------
    # Profile & Path Resolution
    # -----------------------------------------------------------------------
    def get_profile(self, device_id: str) -> Optional[DeviceManagementProfile]:
        """Loads device management profile from database."""
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT * FROM device_management_profiles WHERE device_id = ?",
                (device_id,)
            ).fetchone()
            if not row:
                return None

            try:
                paths_data = json.loads(row["paths_json"] or "[]")
                paths = [ManagementPath.from_dict(p) for p in paths_data]
            except Exception:
                paths = []

            active_p = next((p for p in paths if p.method == row["active_method"]), None)

            return DeviceManagementProfile(
                device_id=row["device_id"],
                device_name=row["device_name"],
                vendor=row["vendor"] or "MikroTik",
                model=row["model"] or "",
                routeros_version=row["routeros_version"] or "",
                ip=row["ip"],
                mac=row["mac"],
                paths=paths,
                active_path=active_p,
                manual_selection=bool(row["manual_selection"]),
                selection_rationale=row["selection_rationale"] or "",
                romon_enabled=bool(row["romon_enabled"]),
                romon_id=row["romon_id"],
                layer2_adjacent=bool(row["layer2_adjacent"]),
                adjacent_interface=row["adjacent_interface"],
                last_updated_at=row["updated_at"],
            )

    def evaluate_and_save_profile(
        self,
        device_id: str,
        device_name: str = "",
        host: Optional[str] = None,
        mac: Optional[str] = None,
        mac_address: Optional[str] = None,
        vendor: str = "MikroTik",
        model: str = "",
        routeros_model: Optional[str] = None,
        routeros_version: Optional[str] = None,
        preferred_method: Optional[str] = None,
        manual_override: bool = False,
    ) -> DeviceManagementProfile:
        """Evaluates all candidate paths and persists the profile."""
        target_mac = mac or mac_address
        target_model = model or routeros_model or ""
        target_name = device_name or device_id
        target_ros = routeros_version or ""
        neighbors = self.list_romon_neighbors()

        profile = SelectionEngine.evaluate_paths(
            device_id=device_id,
            device_name=target_name,
            host=host,
            mac=target_mac,
            vendor=vendor,
            model=target_model,
            routeros_version=target_ros,
            preferred_method=preferred_method,
            manual_override=manual_override,
            romon_neighbors=neighbors,
        )

        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("""
                INSERT INTO device_management_profiles (
                    device_id, device_name, vendor, model, routeros_version,
                    ip, mac, preferred_method, manual_selection, active_method,
                    paths_json, selection_rationale, romon_enabled, romon_id,
                    layer2_adjacent, adjacent_interface, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    device_name = excluded.device_name,
                    vendor = excluded.vendor,
                    model = excluded.model,
                    routeros_version = excluded.routeros_version,
                    ip = excluded.ip,
                    mac = excluded.mac,
                    preferred_method = excluded.preferred_method,
                    manual_selection = excluded.manual_selection,
                    active_method = excluded.active_method,
                    paths_json = excluded.paths_json,
                    selection_rationale = excluded.selection_rationale,
                    romon_enabled = excluded.romon_enabled,
                    romon_id = excluded.romon_id,
                    layer2_adjacent = excluded.layer2_adjacent,
                    adjacent_interface = excluded.adjacent_interface,
                    updated_at = excluded.updated_at
            """, (
                profile.device_id,
                profile.device_name,
                profile.vendor,
                profile.model,
                profile.routeros_version,
                profile.ip,
                profile.mac,
                preferred_method,
                1 if manual_override else 0,
                profile.active_path.method if profile.active_path else None,
                json.dumps([p.to_dict() for p in profile.paths]),
                profile.selection_rationale,
                1 if profile.romon_enabled else 0,
                profile.romon_id,
                1 if profile.layer2_adjacent else 0,
                profile.adjacent_interface,
                time.time(),
            ))
            conn.commit()

        return profile

    def set_manual_override(
        self,
        device_id: str,
        preferred_method: Optional[str] = None,
    ) -> DeviceManagementProfile:
        """Sets administrative manual path override for a device."""
        existing = self.get_profile(device_id)
        if not existing:
            existing = self.evaluate_and_save_profile(device_id=device_id, host=None)

        is_manual = bool(preferred_method and preferred_method.lower() not in ("", "auto", "none"))
        chosen = preferred_method if is_manual else None

        return self.evaluate_and_save_profile(
            device_id=existing.device_id,
            device_name=existing.device_name,
            host=existing.ip,
            mac=existing.mac,
            vendor=existing.vendor,
            model=existing.model,
            routeros_version=existing.routeros_version,
            preferred_method=chosen,
            manual_override=is_manual,
        )

    # -----------------------------------------------------------------------
    # Path Testing
    # -----------------------------------------------------------------------
    def test_path(
        self,
        device_id: str,
        method: str,
    ) -> Dict[str, Any]:
        """Tests connectivity for a specific management path on a device."""
        profile = self.get_profile(device_id)
        if not profile:
            return {"success": False, "error": f"Profil perangkat '{device_id}' tidak ditemukan."}

        m_enum = ManagementMethod.coerce(method)

        if m_enum == ManagementMethod.SSH_IP:
            if not profile.ip:
                return {"success": False, "method": method, "error": "Perangkat tidak memiliki IP address."}
            from core.management.capability_detector import check_tcp_port
            ok, lat, err = check_tcp_port(profile.ip, 22, timeout=3.0)
            return {
                "success": ok,
                "method": method,
                "target": profile.ip,
                "port": 22,
                "latency_ms": lat,
                "message": f"Port SSH 22 terhubung dalam {lat} ms." if ok else f"Gagal terhubung: {err}",
                "error": err,
            }

        elif m_enum == ManagementMethod.API_IP:
            if not profile.ip:
                return {"success": False, "method": method, "error": "Perangkat tidak memiliki IP address."}
            from core.management.capability_detector import check_tcp_port
            ok, lat, err = check_tcp_port(profile.ip, 8728, timeout=3.0)
            return {
                "success": ok,
                "method": method,
                "target": profile.ip,
                "port": 8728,
                "latency_ms": lat,
                "message": f"RouterOS API port 8728 terhubung dalam {lat} ms." if ok else f"Gagal terhubung: {err}",
                "error": err,
            }

        elif m_enum == ManagementMethod.MAC_TELNET:
            if not profile.mac:
                return {"success": False, "method": method, "error": "MAC address perangkat belum diketahui."}
            return MacManager.test_mac_reachability(profile.mac, profile.adjacent_interface)

        elif m_enum == ManagementMethod.ROMON:
            neighbors = self.list_romon_neighbors()
            matched = next((n for n in neighbors if n.mac == profile.mac or n.identity == profile.device_name), None)
            if matched:
                return {
                    "success": True,
                    "method": method,
                    "romon_id": matched.romon_id,
                    "hop_count": matched.hop_count,
                    "intermediary": matched.via_device_name,
                    "message": f"RoMON neighbor terdeteksi via {matched.via_device_name} ({matched.hop_count} hop).",
                }
            return {
                "success": False,
                "method": method,
                "error": "Perangkat tidak ditemukan di tabel RoMON tetangga manapun.",
            }

        return {"success": False, "method": method, "error": f"Metode '{method}' tidak didukung untuk tes langsung."}

    # -----------------------------------------------------------------------
    # RoMON Neighbor Cache
    # -----------------------------------------------------------------------
    def list_romon_neighbors(self) -> List[RomonNeighbor]:
        """Lists cached RoMON neighbors discovered across network."""
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute("SELECT * FROM romon_neighbors_cache").fetchall()
            out: List[RomonNeighbor] = []
            for r in rows:
                try:
                    path_l = json.loads(r["path_json"] or "[]")
                except Exception:
                    path_l = []
                out.append(RomonNeighbor(
                    romon_id=r["romon_id"],
                    mac=r["mac"],
                    identity=r["identity"] or "",
                    version=r["version"] or "",
                    board=r["board"] or "",
                    hop_count=r["hop_count"] or 1,
                    path=path_l,
                    via_device_id=r["via_device_id"] or "",
                    via_device_name=r["via_device_name"] or "",
                    discovered_at=r["discovered_at"],
                ))
            return out

    def update_romon_neighbors(self, neighbors: List[RomonNeighbor]) -> None:
        """Stores fresh RoMON neighbor records in cache."""
        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            for n in neighbors:
                conn.execute("""
                    INSERT INTO romon_neighbors_cache (
                        romon_id, mac, identity, version, board, hop_count,
                        path_json, via_device_id, via_device_name, discovered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(romon_id) DO UPDATE SET
                        mac = excluded.mac,
                        identity = excluded.identity,
                        version = excluded.version,
                        board = excluded.board,
                        hop_count = excluded.hop_count,
                        path_json = excluded.path_json,
                        via_device_id = excluded.via_device_id,
                        via_device_name = excluded.via_device_name,
                        discovered_at = excluded.discovered_at
                """, (
                    n.romon_id,
                    n.mac,
                    n.identity,
                    n.version,
                    n.board,
                    n.hop_count,
                    json.dumps(n.path),
                    n.via_device_id,
                    n.via_device_name,
                    now,
                ))
            conn.commit()


_manager_singleton: Optional[MultiPathManager] = None
_manager_lock = threading.Lock()


def get_multi_path_manager() -> MultiPathManager:
    global _manager_singleton
    if _manager_singleton is None:
        with _manager_lock:
            if _manager_singleton is None:
                _manager_singleton = MultiPathManager()
    return _manager_singleton
