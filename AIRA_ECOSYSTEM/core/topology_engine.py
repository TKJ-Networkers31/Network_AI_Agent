"""
core/topology_engine.py — Evidence-Based Enterprise Topology & Monitoring Engine (V2) for AIRA OS.

Supports:
- Non-destructive SQLite schema migrations preserving existing nodes, links, positions & overrides
- Separation of discovery_status, ownership_status, topology_scope, trust_zone, reachability,
  management_status, and observation_freshness
- Evidence tracking for every discovered or manually confirmed node and link
- ISP / external boundary policies & bounded recursive discovery (seed_only, enterprise_managed, authorized_expansion)
- Deterministic port-to-port wiring verification & conflict preservation
- Rate-limited, timeout-bounded ICMP probing and lightweight freshness refresh
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.nms_models import is_check_stale
from core.topology_discovery import TopologyDiscoveryMixin
from core.topology_models import (
    DEFAULT_TOPOLOGY_POLICY,
    DISCOVERY_MODE_VALUES,
    LINK_TYPE_VALUES,
    OWNERSHIP_VALUES,
    TOPOLOGY_SCOPE_VALUES,
    TRUST_ZONE_VALUES,
    VERIFICATION_STATUS_VALUES,
    VIEW_MODE_VALUES,
    bounded_icmp_ping,
    calculate_deterministic_node_status,
    compute_observation_freshness,
    ip_in_subnets,
    normalize_ip,
    normalize_mac,
    sanitize_cli_excerpt,
    sanitize_untrusted_text,
    validate_subnet_list,
)
from core.topology_parsers import parse_mikrotik_arp, parse_mikrotik_neighbors

logger = logging.getLogger("aira.topology")

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DATABASE_DIR / "topology.db"

_NODE_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("discovery_status", "TEXT DEFAULT 'discovered'"),
    ("ownership_status", "TEXT DEFAULT 'unknown'"),
    ("topology_scope", "TEXT DEFAULT 'unclassified'"),
    ("trust_zone", "TEXT DEFAULT 'unknown'"),
    ("device_role", "TEXT DEFAULT 'unspecified'"),
    ("confidence", "TEXT DEFAULT 'unknown'"),
    ("confidence_reason", "TEXT DEFAULT ''"),
    ("provenance", "TEXT DEFAULT 'discovery_managed'"),
    ("user_overrides_json", "TEXT DEFAULT '{}'"),
    ("reachability_status", "TEXT DEFAULT 'unknown'"),
    ("management_status", "TEXT DEFAULT 'not_attempted'"),
    ("link_status", "TEXT DEFAULT 'unknown'"),
    ("observation_freshness", "TEXT DEFAULT 'unknown'"),
    ("availability_reason", "TEXT DEFAULT ''"),
    ("last_probe_at", "REAL"),
    ("last_ping_alive", "INTEGER"),
    ("last_verified", "REAL"),
    ("first_seen", "REAL"),
    ("source_device_id", "TEXT DEFAULT ''"),
    ("serial_number", "TEXT DEFAULT ''"),
    ("observability", "TEXT DEFAULT 'not_attempted'"),
    ("observability_reason", "TEXT DEFAULT ''"),
    ("all_ips_json", "TEXT DEFAULT '[]'"),
    ("all_macs_json", "TEXT DEFAULT '[]'"),
    ("vlans_json", "TEXT DEFAULT '[]'"),
]

_LINK_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("verification_status", "TEXT DEFAULT 'unknown'"),
    ("local_interface_id", "TEXT DEFAULT ''"),
    ("remote_interface_id", "TEXT DEFAULT ''"),
    ("evidence_sources_json", "TEXT DEFAULT '[]'"),
    ("confidence", "TEXT DEFAULT 'unknown'"),
    ("confidence_reason", "TEXT DEFAULT ''"),
    ("provenance", "TEXT DEFAULT 'discovery_managed'"),
    ("user_overrides_json", "TEXT DEFAULT '{}'"),
    ("first_seen", "REAL"),
    ("last_seen", "REAL"),
    ("last_verified", "REAL"),
    ("bandwidth_bps", "INTEGER DEFAULT 0"),
    ("admin_status", "TEXT DEFAULT 'unknown'"),
    ("oper_status", "TEXT DEFAULT 'unknown'"),
    ("notes", "TEXT DEFAULT ''"),
]


def _json_loads_safe(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


class TopologyEngine(TopologyDiscoveryMixin):
    parse_mikrotik_neighbors = staticmethod(parse_mikrotik_neighbors)
    parse_mikrotik_arp = staticmethod(parse_mikrotik_arp)

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self._lock = threading.RLock()
        self._discovery_lock = threading.Lock()
        self._active_job_id: Optional[str] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Creates base tables and runs non-destructive column migrations preserving existing user data."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._get_connection()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS topology_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    identity TEXT,
                    ip TEXT,
                    mac TEXT,
                    device_type TEXT DEFAULT 'router',
                    status TEXT DEFAULT 'online',
                    latency_ms REAL DEFAULT 0.0,
                    pos_x REAL DEFAULT 0.0,
                    pos_y REAL DEFAULT 0.0,
                    last_seen REAL,
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS topology_links (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    source_port TEXT DEFAULT '',
                    target_port TEXT DEFAULT '',
                    link_type TEXT DEFAULT 'ethernet',
                    status TEXT DEFAULT 'up',
                    bandwidth TEXT DEFAULT '',
                    last_checked REAL,
                    FOREIGN KEY (source_id) REFERENCES topology_nodes (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES topology_nodes (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS topology_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    protocol TEXT DEFAULT '',
                    observing_device_id TEXT DEFAULT '',
                    observed_endpoint TEXT DEFAULT '',
                    local_interface TEXT DEFAULT '',
                    remote_interface TEXT DEFAULT '',
                    directness TEXT DEFAULT 'direct',
                    confidence TEXT DEFAULT 'medium',
                    explanation TEXT DEFAULT '',
                    raw_excerpt TEXT DEFAULT '',
                    observed_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS topology_policy (
                    key TEXT PRIMARY KEY,
                    policy_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS topology_discovery_jobs (
                    job_id TEXT PRIMARY KEY,
                    seed_device TEXT DEFAULT '',
                    mode TEXT DEFAULT 'seed_only',
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    duration_ms REAL DEFAULT 0.0,
                    hops_scanned INTEGER DEFAULT 0,
                    nodes_observed INTEGER DEFAULT 0,
                    links_observed INTEGER DEFAULT 0,
                    errors_json TEXT DEFAULT '[]',
                    limitations_json TEXT DEFAULT '[]',
                    summary TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS topology_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conflict_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    candidate_data_json TEXT DEFAULT '{}',
                    reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'open',
                    created_at REAL NOT NULL,
                    resolved_at REAL
                );

                CREATE TABLE IF NOT EXISTS topology_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT DEFAULT 'admin',
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    before_json TEXT DEFAULT '{}',
                    after_json TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_status ON topology_nodes(status);
                CREATE INDEX IF NOT EXISTS idx_links_nodes ON topology_links(source_id, target_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_subj ON topology_evidence(subject_type, subject_id);
                CREATE INDEX IF NOT EXISTS idx_conflicts_status ON topology_conflicts(status);
                """
            )

            existing_node_cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(topology_nodes)").fetchall()
            }
            for col_name, col_def in _NODE_MIGRATION_COLUMNS:
                if col_name not in existing_node_cols:
                    conn.execute(f"ALTER TABLE topology_nodes ADD COLUMN {col_name} {col_def}")

            existing_link_cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(topology_links)").fetchall()
            }
            for col_name, col_def in _LINK_MIGRATION_COLUMNS:
                if col_name not in existing_link_cols:
                    conn.execute(f"ALTER TABLE topology_links ADD COLUMN {col_name} {col_def}")

            # Ensure default policy row exists without overwriting existing saved policy
            row = conn.execute("SELECT key FROM topology_policy WHERE key = 'default'").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO topology_policy (key, policy_json, updated_at) VALUES (?, ?, ?)",
                    ("default", json.dumps(DEFAULT_TOPOLOGY_POLICY), time.time()),
                )

            conn.commit()

    # ------------------------------------------------------------------
    # Policy & Governance Configuration
    # ------------------------------------------------------------------

    def get_policy(self) -> Dict[str, Any]:
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT policy_json FROM topology_policy WHERE key = 'default'").fetchone()
            stored = _json_loads_safe(row["policy_json"] if row else None, {})
        merged = dict(DEFAULT_TOPOLOGY_POLICY)
        merged.update(stored)
        return merged

    def update_policy(self, updates: Dict[str, Any], actor: str = "admin") -> Dict[str, Any]:
        current = self.get_policy()
        new_pol = dict(current)

        if "discovery_mode" in updates and updates["discovery_mode"] is not None:
            mode = str(updates["discovery_mode"]).strip()
            if mode not in DISCOVERY_MODE_VALUES:
                raise ValueError(f"Invalid discovery_mode '{mode}'. Must be one of {DISCOVERY_MODE_VALUES}.")
            new_pol["discovery_mode"] = mode

        if "view_mode" in updates and updates["view_mode"] is not None:
            vm = str(updates["view_mode"]).strip()
            if vm not in VIEW_MODE_VALUES:
                raise ValueError(f"Invalid view_mode '{vm}'. Must be one of {VIEW_MODE_VALUES}.")
            new_pol["view_mode"] = vm

        for subnet_key in ("management_subnets", "enterprise_subnets", "approved_discovery_scopes", "excluded_subnets"):
            if subnet_key in updates and updates[subnet_key] is not None:
                new_pol[subnet_key] = validate_subnet_list(updates[subnet_key])

        for list_key in ("isp_boundary_interfaces", "known_isp_devices", "known_external_devices", "approved_discovery_protocols"):
            if list_key in updates and updates[list_key] is not None:
                new_pol[list_key] = [
                    sanitize_untrusted_text(x, 128) for x in updates[list_key] if str(x or "").strip()
                ]

        for str_key in ("enterprise_id", "seed_device_id"):
            if str_key in updates and updates[str_key] is not None:
                new_pol[str_key] = sanitize_untrusted_text(updates[str_key], 64)

        for bool_key in ("allow_routed_expansion", "auto_include_unknown_neighbors", "require_review_for_unknown_devices"):
            if bool_key in updates and updates[bool_key] is not None:
                new_pol[bool_key] = bool(updates[bool_key])

        if "discovery_depth" in updates and updates["discovery_depth"] is not None:
            new_pol["discovery_depth"] = max(1, min(int(updates["discovery_depth"]), 5))

        for int_key, bounds in (
            ("freshness_threshold_sec", (10, 86400)),
            ("expire_threshold_sec", (60, 604800)),
            ("probe_cooldown_sec", (1, 3600)),
            ("probe_timeout_sec", (1, 10)),
            ("probe_retries", (0, 3)),
            ("max_concurrency", (1, 8)),
            ("max_scan_duration_sec", (5, 180)),
        ):
            if int_key in updates and updates[int_key] is not None:
                lo, hi = bounds
                new_pol[int_key] = max(lo, min(int(updates[int_key]), hi))

        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                "INSERT INTO topology_policy (key, policy_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET policy_json = excluded.policy_json, updated_at = excluded.updated_at",
                ("default", json.dumps(new_pol), now),
            )
            conn.execute(
                "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, before_json, after_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (actor, "update_policy", "policy", "default", "Policy updated", json.dumps(current), json.dumps(new_pol), now),
            )
            conn.commit()
        return new_pol

    # ------------------------------------------------------------------
    # Evidence, Conflicts & Audit Helpers
    # ------------------------------------------------------------------

    def record_evidence(
        self,
        *,
        subject_type: str,
        subject_id: str,
        evidence_type: str,
        protocol: str = "",
        observing_device_id: str = "",
        observed_endpoint: str = "",
        local_interface: str = "",
        remote_interface: str = "",
        directness: str = "direct",
        confidence: str = "medium",
        explanation: str = "",
        raw_excerpt: str = "",
        observed_at: Optional[float] = None,
    ) -> None:
        ts = observed_at if observed_at is not None else time.time()
        clean_raw = sanitize_cli_excerpt(raw_excerpt, 600)
        clean_exp = sanitize_untrusted_text(explanation, 300)
        with self._lock, closing(self._get_connection()) as conn:
            # Deduplicate identical evidence source per subject so repeated scans refresh timestamp cleanly
            existing = conn.execute(
                """
                SELECT id FROM topology_evidence
                WHERE subject_type = ? AND subject_id = ? AND evidence_type = ?
                  AND observing_device_id = ? AND local_interface = ? AND remote_interface = ?
                """,
                (subject_type, subject_id, evidence_type, observing_device_id, local_interface, remote_interface),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE topology_evidence
                    SET protocol = ?, observed_endpoint = ?, directness = ?, confidence = ?,
                        explanation = ?, raw_excerpt = ?, observed_at = ?
                    WHERE id = ?
                    """,
                    (protocol, observed_endpoint, directness, confidence, clean_exp, clean_raw, ts, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO topology_evidence (
                        subject_type, subject_id, evidence_type, protocol, observing_device_id,
                        observed_endpoint, local_interface, remote_interface, directness,
                        confidence, explanation, raw_excerpt, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subject_type,
                        subject_id,
                        evidence_type,
                        protocol,
                        observing_device_id,
                        observed_endpoint,
                        local_interface,
                        remote_interface,
                        directness,
                        confidence,
                        clean_exp,
                        clean_raw,
                        ts,
                    ),
                )
            conn.commit()

    def record_conflict(
        self,
        *,
        conflict_type: str,
        subject_id: str,
        candidate_data: Dict[str, Any],
        reason: str,
        now: Optional[float] = None,
    ) -> int:
        ts = now if now is not None else time.time()
        clean_reason = sanitize_untrusted_text(reason, 400)
        payload = json.dumps(candidate_data or {})
        with self._lock, closing(self._get_connection()) as conn:
            existing = conn.execute(
                "SELECT id FROM topology_conflicts WHERE conflict_type = ? AND subject_id = ? AND status = 'open'",
                (conflict_type, subject_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE topology_conflicts SET candidate_data_json = ?, reason = ?, created_at = ? WHERE id = ?",
                    (payload, clean_reason, ts, existing["id"]),
                )
                conn.commit()
                return int(existing["id"])
            cur = conn.execute(
                "INSERT INTO topology_conflicts (conflict_type, subject_id, candidate_data_json, reason, status, created_at) "
                "VALUES (?, ?, ?, ?, 'open', ?)",
                (conflict_type, subject_id, payload, clean_reason, ts),
            )
            conn.commit()
            return int(cur.lastrowid)

    def resolve_conflict(self, conflict_id: int, status: str = "resolved", actor: str = "admin") -> bool:
        if status not in ("resolved", "ignored", "open"):
            raise ValueError("Conflict status must be 'resolved', 'ignored', or 'open'.")
        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            cur = conn.execute(
                "UPDATE topology_conflicts SET status = ?, resolved_at = ? WHERE id = ?",
                (status, now if status != "open" else None, int(conflict_id)),
            )
            if cur.rowcount > 0:
                conn.execute(
                    "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, created_at) "
                    "VALUES (?, ?, 'conflict', ?, ?, ?)",
                    (actor, f"conflict_{status}", str(conflict_id), f"Marked conflict {status}", now),
                )
            conn.commit()
            return cur.rowcount > 0

    def get_node_evidence(self, node_id: str) -> List[Dict[str, Any]]:
        pol = self.get_policy()
        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT * FROM topology_evidence WHERE subject_type = 'node' AND subject_id = ? ORDER BY observed_at DESC",
                (node_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "evidence_type": r["evidence_type"],
                "protocol": r["protocol"],
                "observing_device_id": r["observing_device_id"],
                "observed_endpoint": r["observed_endpoint"],
                "local_interface": r["local_interface"],
                "remote_interface": r["remote_interface"],
                "directness": r["directness"],
                "confidence": r["confidence"],
                "explanation": r["explanation"],
                "raw_excerpt": r["raw_excerpt"],
                "observed_at": r["observed_at"],
                "freshness": compute_observation_freshness(
                    r["observed_at"],
                    now=now,
                    fresh_sec=pol["freshness_threshold_sec"],
                    expire_sec=pol["expire_threshold_sec"],
                ),
            }
            for r in rows
        ]

    def get_link_evidence(self, link_id: str) -> List[Dict[str, Any]]:
        pol = self.get_policy()
        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT * FROM topology_evidence WHERE subject_type = 'link' AND subject_id = ? ORDER BY observed_at DESC",
                (link_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "evidence_type": r["evidence_type"],
                "protocol": r["protocol"],
                "observing_device_id": r["observing_device_id"],
                "observed_endpoint": r["observed_endpoint"],
                "local_interface": r["local_interface"],
                "remote_interface": r["remote_interface"],
                "directness": r["directness"],
                "confidence": r["confidence"],
                "explanation": r["explanation"],
                "raw_excerpt": r["raw_excerpt"],
                "observed_at": r["observed_at"],
                "freshness": compute_observation_freshness(
                    r["observed_at"],
                    now=now,
                    fresh_sec=pol["freshness_threshold_sec"],
                    expire_sec=pol["expire_threshold_sec"],
                ),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Identity Resolution & Reconciliation Internals
    # ------------------------------------------------------------------

    def _safe_list_inventory_devices(self) -> List[Dict[str, Any]]:
        try:
            from core.inventory_store import get_inventory_store
            return get_inventory_store().list_devices().get("devices", [])
        except Exception:
            return []

    def _get_existing_position(self, node_id: str) -> Tuple[Optional[float], Optional[float]]:
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT pos_x, pos_y FROM topology_nodes WHERE id = ?", (node_id,)).fetchone()
            if row and (row["pos_x"] != 0.0 or row["pos_y"] != 0.0):
                return float(row["pos_x"]), float(row["pos_y"])
        return None, None

    def _resolve_or_select_node_id(
        self,
        *,
        preferred_id: str,
        serial_number: str,
        mac: str,
        ip: str,
        identity: str,
        board: str,
        all_macs: Optional[List[str]] = None,
        is_interrogated_device: bool = False,
    ) -> str:
        with self._lock, closing(self._get_connection()) as conn:
            if serial_number:
                r_sn = conn.execute(
                    "SELECT id FROM topology_nodes WHERE serial_number = ? AND serial_number != ''",
                    (serial_number,),
                ).fetchone()
                if r_sn:
                    return str(r_sn["id"])

            r_pref = conn.execute("SELECT id FROM topology_nodes WHERE id = ?", (preferred_id,)).fetchone()
            if r_pref:
                return preferred_id

            mac_candidates = [normalize_mac(m) for m in ([mac] + list(all_macs or [])) if normalize_mac(m)]
            if mac_candidates:
                placeholders = ",".join("?" for _ in mac_candidates)
                r_mac = conn.execute(
                    f"SELECT id, serial_number FROM topology_nodes WHERE UPPER(mac) IN ({placeholders}) LIMIT 1",
                    mac_candidates,
                ).fetchone()
                if r_mac and (not serial_number or not r_mac["serial_number"] or r_mac["serial_number"] == serial_number):
                    return str(r_mac["id"])

            if is_interrogated_device and ip:
                r_ip = conn.execute(
                    "SELECT id, serial_number FROM topology_nodes WHERE ip = ?",
                    (ip,),
                ).fetchone()
                if r_ip and (not serial_number or not r_ip["serial_number"] or r_ip["serial_number"] == serial_number):
                    return str(r_ip["id"])
        return preferred_id

    def _resolve_neighbor_node_id(
        self,
        *,
        preferred_id: str,
        mac: str,
        ip: str,
        identity: str,
        board: str,
        now: float,
    ) -> Tuple[str, bool]:
        """
        Stage C: Resolves stable node_id for a candidate neighbor.
        Handles IP renewals cleanly via MAC matching while refusing to silently merge
        conflicting hardware/identities sharing an IP or spoofed MAC.
        """
        norm_mac = normalize_mac(mac)
        norm_ip = normalize_ip(ip)
        conflict = False

        with self._lock, closing(self._get_connection()) as conn:
            # 1. Exact ID check
            by_id = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (preferred_id,)).fetchone()
            if by_id:
                existing_meta = _json_loads_safe(by_id["metadata_json"], {})
                ex_board = (existing_meta.get("board") or "").strip().lower()
                if board and ex_board and board.lower() != ex_board:
                    conflict = True
                    alt_id = f"{preferred_id}_conflict_{re.sub(r'[^a-z0-9]', '_', board.lower())}"
                    self.record_conflict(
                        conflict_type="identity_conflict",
                        subject_id=preferred_id,
                        candidate_data={"existing_board": ex_board, "new_board": board, "mac": norm_mac, "ip": norm_ip, "identity": identity},
                        reason=f"Conflicting hardware board '{board}' vs '{ex_board}' observed on same identifier '{preferred_id}'.",
                        now=now,
                    )
                    return alt_id, conflict
                return preferred_id, False

            # 2. Match by non-empty MAC (supports DHCP IP changes without creating duplicates!)
            if norm_mac:
                by_mac = conn.execute("SELECT * FROM topology_nodes WHERE UPPER(mac) = ?", (norm_mac,)).fetchall()
                if by_mac:
                    r0 = by_mac[0]
                    ex_meta = _json_loads_safe(r0["metadata_json"], {})
                    ex_board = (ex_meta.get("board") or "").strip().lower()
                    if board and ex_board and board.lower() != ex_board:
                        conflict = True
                        self.record_conflict(
                            conflict_type="identity_conflict",
                            subject_id=r0["id"],
                            candidate_data={"mac": norm_mac, "existing_board": ex_board, "new_board": board, "ip": norm_ip},
                            reason=f"MAC {norm_mac} seen with conflicting hardware model '{board}' vs '{ex_board}'.",
                            now=now,
                        )
                        return preferred_id, True
                    return str(r0["id"]), False

            # 3. Check IP collision with an unrelated hardware MAC/identity
            if norm_ip:
                by_ip = conn.execute("SELECT * FROM topology_nodes WHERE ip = ?", (norm_ip,)).fetchall()
                for row in by_ip:
                    ex_mac = normalize_mac(row["mac"])
                    ex_ident = (row["identity"] or "").strip().lower()
                    # Safe merge ONLY if existing node had no MAC yet and compatible identity
                    if not ex_mac and (not identity or not ex_ident or identity.lower() == ex_ident or "arp host" in ex_ident):
                        return str(row["id"]), False
                    if ex_mac and norm_mac and ex_mac != norm_mac:
                        # Different MAC claiming same IP: could be multi-interface router OR IP conflict!
                        ex_all_macs = _json_loads_safe(row["all_macs_json"], [])
                        if norm_mac in ex_all_macs:
                            return str(row["id"]), False
                        conflict = True
                        self.record_conflict(
                            conflict_type="ip_conflict",
                            subject_id=row["id"],
                            candidate_data={
                                "ip": norm_ip,
                                "existing_node": row["id"],
                                "existing_mac": ex_mac,
                                "existing_identity": row["identity"],
                                "candidate_mac": norm_mac,
                                "candidate_identity": identity,
                            },
                            reason=f"IP {norm_ip} observed with different MAC ({norm_mac}, '{identity}') vs existing node '{row['name']}' ({ex_mac}); kept separate.",
                            now=now,
                        )

        return preferred_id, conflict

    def _reconcile_discovered_node(
        self,
        *,
        node_id: str,
        name: str,
        identity: str,
        ip: str,
        mac: str,
        device_type: str,
        device_role: str,
        discovery_status: str,
        ownership_status: str,
        topology_scope: str,
        trust_zone: str,
        confidence: str,
        confidence_reason: str,
        ssh_ok: Optional[bool],
        management_authorized: bool,
        observability: str,
        observability_reason: str,
        source_device_id: str,
        serial_number: str = "",
        all_ips: Optional[List[str]] = None,
        all_macs: Optional[List[str]] = None,
        vlans: Optional[List[Dict[str, Any]]] = None,
        pos_x: Optional[float] = None,
        pos_y: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
        evidence_batch: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        ts = now if now is not None else time.time()
        pol = self.get_policy()

        for ev in evidence_batch or []:
            self.record_evidence(
                subject_type="node",
                subject_id=node_id,
                evidence_type=ev["evidence_type"],
                protocol=ev.get("protocol", ""),
                observing_device_id=source_device_id,
                observed_endpoint=ip or mac or identity,
                local_interface=ev.get("local_interface", ""),
                remote_interface=ev.get("remote_interface", ""),
                directness=ev.get("directness", "direct"),
                confidence=ev.get("confidence", "medium"),
                explanation=ev.get("explanation", ""),
                raw_excerpt=ev.get("raw_excerpt", ""),
                observed_at=ts,
            )

        ev_list = self.get_node_evidence(node_id)

        with self._lock, closing(self._get_connection()) as conn:
            existing = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (node_id,)).fetchone()
            overrides: Dict[str, Any] = _json_loads_safe(existing["user_overrides_json"] if existing else None, {})
            cur_meta: Dict[str, Any] = _json_loads_safe(existing["metadata_json"] if existing else None, {})
            if metadata:
                # Preserve user-locked metadata keys such as role / is_isp_boundary
                for k, v in metadata.items():
                    if k == "role" and "device_role" in overrides:
                        continue
                    cur_meta[k] = v

            prev_prov = existing["provenance"] if existing else "discovery_managed"
            new_prov = "hybrid" if prev_prov in ("user_managed", "hybrid") or overrides else "discovery_managed"

            final_name = overrides.get("name") or (existing["name"] if prev_prov == "user_managed" and existing else name)
            final_ident = overrides.get("identity") or identity or final_name
            final_type = overrides.get("device_type") or device_type
            final_role = overrides.get("device_role") or device_role
            final_own = overrides.get("ownership_status") or ownership_status
            final_scope = overrides.get("topology_scope") or topology_scope
            final_zone = overrides.get("trust_zone") or trust_zone

            if overrides.get("is_isp_boundary"):
                cur_meta["is_isp_boundary"] = True
                if "topology_scope" not in overrides:
                    final_scope = "isp_upstream"
                if "trust_zone" not in overrides:
                    final_zone = "isp"

            if overrides.get("excluded_from_discovery"):
                cur_meta["excluded_from_discovery"] = True
                discovery_status = "excluded"

            final_ip = overrides.get("ip") or normalize_ip(ip) or (existing["ip"] if existing else "")
            final_mac = overrides.get("mac") or normalize_mac(mac) or (existing["mac"] if existing else "")
            final_sn = serial_number or (existing["serial_number"] if existing else "")

            merged_ips = sorted(
                set(_json_loads_safe(existing["all_ips_json"] if existing else None, []))
                | set(all_ips or [])
                | ({final_ip} if final_ip else set())
            )
            merged_macs = sorted(
                set(_json_loads_safe(existing["all_macs_json"] if existing else None, []))
                | set(all_macs or [])
                | ({final_mac} if final_mac else set())
            )
            final_vlans = vlans if vlans is not None else _json_loads_safe(existing["vlans_json"] if existing else None, [])

            last_probe_at = existing["last_probe_at"] if existing else None
            last_ping_int = existing["last_ping_alive"] if existing else None
            last_ping_alive = None if last_ping_int is None else bool(last_ping_int)

            calc = calculate_deterministic_node_status(
                evidence_list=ev_list,
                last_seen=ts,
                last_probe_at=last_probe_at,
                last_ping_alive=last_ping_alive,
                ssh_ok=ssh_ok,
                management_authorized=management_authorized or (final_own == "owned" and existing and existing["management_status"] == "managed"),
                provenance=new_prov,
                current_legacy_status=existing["status"] if existing else "online",
                now=ts,
                fresh_sec=pol["freshness_threshold_sec"],
                expire_sec=pol["expire_threshold_sec"],
            )

            first_seen = (existing["first_seen"] if existing and existing["first_seen"] else ts)
            last_verified = ts if (ssh_ok is True or final_own == "owned" and overrides) else (existing["last_verified"] if existing else None)
            fx = pos_x if pos_x is not None else (existing["pos_x"] if existing else 0.0)
            fy = pos_y if pos_y is not None else (existing["pos_y"] if existing else 0.0)
            lat_ms = existing["latency_ms"] if existing else 0.0

            conn.execute(
                """
                INSERT INTO topology_nodes (
                    id, name, identity, ip, mac, device_type, status, latency_ms, pos_x, pos_y,
                    last_seen, metadata_json, discovery_status, ownership_status, topology_scope,
                    trust_zone, device_role, confidence, confidence_reason, provenance,
                    user_overrides_json, reachability_status, management_status, link_status,
                    observation_freshness, availability_reason, last_probe_at, last_ping_alive,
                    last_verified, first_seen, source_device_id, serial_number,
                    observability, observability_reason, all_ips_json, all_macs_json, vlans_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    identity = excluded.identity,
                    ip = excluded.ip,
                    mac = excluded.mac,
                    device_type = excluded.device_type,
                    status = excluded.status,
                    pos_x = excluded.pos_x,
                    pos_y = excluded.pos_y,
                    last_seen = excluded.last_seen,
                    metadata_json = excluded.metadata_json,
                    discovery_status = excluded.discovery_status,
                    ownership_status = excluded.ownership_status,
                    topology_scope = excluded.topology_scope,
                    trust_zone = excluded.trust_zone,
                    device_role = excluded.device_role,
                    confidence = excluded.confidence,
                    confidence_reason = excluded.confidence_reason,
                    provenance = excluded.provenance,
                    user_overrides_json = excluded.user_overrides_json,
                    reachability_status = excluded.reachability_status,
                    management_status = excluded.management_status,
                    observation_freshness = excluded.observation_freshness,
                    availability_reason = excluded.availability_reason,
                    last_verified = excluded.last_verified,
                    source_device_id = excluded.source_device_id,
                    serial_number = excluded.serial_number,
                    observability = excluded.observability,
                    observability_reason = excluded.observability_reason,
                    all_ips_json = excluded.all_ips_json,
                    all_macs_json = excluded.all_macs_json,
                    vlans_json = excluded.vlans_json
                """,
                (
                    node_id,
                    final_name,
                    final_ident,
                    final_ip,
                    final_mac,
                    final_type,
                    calc["legacy_status"],
                    lat_ms,
                    fx,
                    fy,
                    ts,
                    json.dumps(cur_meta),
                    discovery_status,
                    final_own,
                    final_scope,
                    final_zone,
                    final_role,
                    overrides.get("confidence") or confidence,
                    overrides.get("confidence_reason") or confidence_reason,
                    new_prov,
                    json.dumps(overrides),
                    calc["reachability_status"],
                    calc["management_status"],
                    "up",
                    calc["observation_freshness"],
                    calc["availability_reason"],
                    last_probe_at,
                    last_ping_int,
                    last_verified,
                    first_seen,
                    source_device_id,
                    final_sn,
                    observability if not (existing and existing["observability"] == "fully_observable" and observability != "fully_observable") else "fully_observable",
                    observability_reason if not (existing and existing["observability"] == "fully_observable" and observability != "fully_observable") else existing["observability_reason"],
                    json.dumps(merged_ips),
                    json.dumps(merged_macs),
                    json.dumps(final_vlans),
                ),
            )
            conn.commit()

    def _reconcile_discovered_link(
        self,
        *,
        source_id: str,
        target_id: str,
        local_port: str,
        remote_port: str,
        link_type: str,
        verification_status: str,
        confidence: str,
        confidence_reason: str,
        oper_status: str,
        bandwidth: str,
        evidence_item: Dict[str, Any],
        now: Optional[float] = None,
    ) -> str:
        """
        Stages 7-9: Reconciles discovered links idempotently without duplicating links,
        preserving manual confirmations, correlating bidirectional observations into 'confirmed',
        and flagging conflicting port claims as 'conflicting'.
        """
        ts = now if now is not None else time.time()
        lp = sanitize_untrusted_text(local_port, 64)
        rp = sanitize_untrusted_text(remote_port, 64)

        with self._lock, closing(self._get_connection()) as conn:
            # Find any existing link between (source_id, target_id) in either direction
            pair_rows = conn.execute(
                """
                SELECT * FROM topology_links
                WHERE (source_id = ? AND target_id = ?)
                   OR (source_id = ? AND target_id = ?)
                """,
                (source_id, target_id, target_id, source_id),
            ).fetchall()

            matched_row = None
            reverse_match = False

            for r in pair_rows:
                is_rev = r["source_id"] == target_id and r["target_id"] == source_id
                r_lp = r["target_port"] if is_rev else r["source_port"]
                r_rp = r["source_port"] if is_rev else r["target_port"]

                # Match same port pair, or upgrade an incomplete port pair, or check conflict on same local port
                if (r_lp == lp and r_rp == rp) or (r_lp == lp) or (not r_lp and not lp) or is_rev:
                    matched_row = r
                    reverse_match = is_rev
                    break

            if matched_row is not None:
                link_id = str(matched_row["id"])
                overrides = _json_loads_safe(matched_row["user_overrides_json"], {})
                ev_sources = set(_json_loads_safe(matched_row["evidence_sources_json"], []))
                ev_sources.add(f"{source_id}:{evidence_item['evidence_type']}")

                # Preserve user_managed or manually confirmed links!
                if matched_row["provenance"] == "user_managed" or overrides.get("locked") or matched_row["verification_status"] == "manual":
                    ex_lp = matched_row["target_port"] if reverse_match else matched_row["source_port"]
                    ex_rp = matched_row["source_port"] if reverse_match else matched_row["target_port"]
                    if (lp and ex_lp and lp != ex_lp) or (rp and ex_rp and rp != ex_rp):
                        self.record_conflict(
                            conflict_type="manual_vs_discovered_port_conflict",
                            subject_id=link_id,
                            candidate_data={"manual_ports": [ex_lp, ex_rp], "discovered_ports": [lp, rp], "observer": source_id},
                            reason=f"Discovered ports ({lp} <-> {rp}) differ from user-confirmed link ({ex_lp} <-> {ex_rp}); manual link preserved.",
                            now=ts,
                        )
                    conn.execute(
                        "UPDATE topology_links SET last_seen = ?, last_checked = ?, evidence_sources_json = ? WHERE id = ?",
                        (ts, ts, json.dumps(sorted(ev_sources)), link_id),
                    )
                    conn.commit()
                    self.record_evidence(
                        subject_type="link",
                        subject_id=link_id,
                        observing_device_id=source_id,
                        observed_endpoint=target_id,
                        observed_at=ts,
                        **evidence_item,
                    )
                    return link_id

                # Evaluate bidirectional correlation vs port conflict
                ex_lp = matched_row["target_port"] if reverse_match else matched_row["source_port"]
                ex_rp = matched_row["source_port"] if reverse_match else matched_row["target_port"]

                final_src = matched_row["source_id"]
                final_dst = matched_row["target_id"]
                final_sp = matched_row["source_port"]
                final_tp = matched_row["target_port"]
                final_vstatus = verification_status
                final_ltype = link_type
                final_conf = confidence
                final_reason = confidence_reason
                last_ver = matched_row["last_verified"]

                if reverse_match:
                    # Peer device B is reporting its view of link to A!
                    ports_conflict = (lp and ex_lp and lp != ex_lp) or (rp and ex_rp and rp != ex_rp)
                    if ports_conflict:
                        final_vstatus = "conflicting"
                        final_conf = "low"
                        final_reason = (
                            f"Conflicting port observations between endpoints: {final_src} reported "
                            f"({final_sp} <-> {final_tp}) while {source_id} reported ({lp} <-> {rp})."
                        )
                        self.record_conflict(
                            conflict_type="link_port_conflict",
                            subject_id=link_id,
                            candidate_data={
                                "endpoint_a": {"node": final_src, "source_port": final_sp, "target_port": final_tp},
                                "endpoint_b": {"node": source_id, "local_port": lp, "remote_port": rp},
                            },
                            reason=final_reason,
                            now=ts,
                        )
                    elif lp and (rp or ex_rp) and link_type in ("layer2_adjacency", "physical"):
                        # Bidirectional agreement! Upgrade to confirmed physical link!
                        final_sp = final_sp or rp
                        final_tp = final_tp or lp
                        if final_sp and final_tp:
                            final_ltype = "physical"
                            final_vstatus = "confirmed"
                            final_conf = "high"
                            final_reason = (
                                f"Verified physical adjacency: both {final_src} ({final_sp}) and "
                                f"{final_dst} ({final_tp}) independently confirmed identities and port mapping."
                            )
                            last_ver = ts
                else:
                    # Same-direction update: check if a different non-empty remote port was claimed on the same scan/window
                    if rp and ex_rp and rp != ex_rp and link_type in ("layer2_adjacency", "physical"):
                        final_vstatus = "conflicting"
                        final_conf = "low"
                        final_reason = (
                            f"Conflicting remote port claims on {source_id}:{lp} -> '{ex_rp}' vs '{rp}'."
                        )
                        self.record_conflict(
                            conflict_type="link_port_conflict",
                            subject_id=link_id,
                            candidate_data={"local_port": lp, "remote_port_1": ex_rp, "remote_port_2": rp},
                            reason=final_reason,
                            now=ts,
                        )
                    else:
                        final_sp = lp or ex_lp
                        final_tp = rp or ex_rp
                        # Do not downgrade an already bidirectionally confirmed link on a single-sided refresh
                        if matched_row["verification_status"] == "confirmed" and final_sp == matched_row["source_port"] and final_tp == matched_row["target_port"]:
                            final_vstatus = "confirmed"
                            final_ltype = matched_row["link_type"]
                            final_conf = "high"
                            final_reason = matched_row["confidence_reason"]

                conn.execute(
                    """
                    UPDATE topology_links
                    SET source_port = ?, target_port = ?, link_type = ?, status = ?, bandwidth = ?,
                        last_checked = ?, last_seen = ?, last_verified = ?, verification_status = ?,
                        evidence_sources_json = ?, confidence = ?, confidence_reason = ?, oper_status = ?
                    WHERE id = ?
                    """,
                    (
                        final_sp,
                        final_tp,
                        final_ltype,
                        oper_status,
                        bandwidth or matched_row["bandwidth"],
                        ts,
                        ts,
                        last_ver,
                        final_vstatus,
                        json.dumps(sorted(ev_sources)),
                        final_conf,
                        final_reason,
                        oper_status,
                        link_id,
                    ),
                )
                conn.commit()
            else:
                # Canonicalize deterministic link_id without volatile empty port suffixes causing duplicates
                link_id = f"{source_id}->{target_id}:{lp or 'any'}"
                ev_sources_list = [f"{source_id}:{evidence_item['evidence_type']}"]
                conn.execute(
                    """
                    INSERT INTO topology_links (
                        id, source_id, target_id, source_port, target_port, link_type, status,
                        bandwidth, last_checked, verification_status, evidence_sources_json,
                        confidence, confidence_reason, provenance, first_seen, last_seen,
                        last_verified, admin_status, oper_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovery_managed', ?, ?, ?, 'up', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        target_port = excluded.target_port,
                        link_type = excluded.link_type,
                        status = excluded.status,
                        last_checked = excluded.last_checked,
                        last_seen = excluded.last_seen,
                        verification_status = excluded.verification_status,
                        confidence = excluded.confidence,
                        confidence_reason = excluded.confidence_reason
                    """,
                    (
                        link_id,
                        source_id,
                        target_id,
                        lp,
                        rp,
                        link_type,
                        oper_status,
                        bandwidth,
                        ts,
                        verification_status,
                        json.dumps(ev_sources_list),
                        confidence,
                        confidence_reason,
                        ts,
                        ts,
                        ts if verification_status == "confirmed" else None,
                        oper_status,
                    ),
                )
                conn.commit()

        self.record_evidence(
            subject_type="link",
            subject_id=link_id,
            observing_device_id=source_id,
            observed_endpoint=target_id,
            observed_at=ts,
            **evidence_item,
        )
        return link_id

    # ------------------------------------------------------------------
    # Manual Node & Link CRUD + Administrative Overrides
    # ------------------------------------------------------------------

    def upsert_node(
        self,
        node_id: str,
        name: str,
        identity: Optional[str] = None,
        ip: Optional[str] = None,
        mac: Optional[str] = None,
        device_type: str = "router",
        status: str = "online",
        latency_ms: float = 0.0,
        pos_x: Optional[float] = None,
        pos_y: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        ownership_status: Optional[str] = None,
        topology_scope: Optional[str] = None,
        trust_zone: Optional[str] = None,
        device_role: Optional[str] = None,
        provenance: str = "user_managed",
    ) -> Dict[str, Any]:
        clean_id = sanitize_untrusted_text(node_id, 96)
        clean_name = sanitize_untrusted_text(name, 80)
        clean_ip = normalize_ip(ip) if ip else ""
        clean_mac = normalize_mac(mac) if mac else ""
        now = time.time()

        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (clean_id,)).fetchone()
            final_pos_x = pos_x if pos_x is not None else (row["pos_x"] if row else 0.0)
            final_pos_y = pos_y if pos_y is not None else (row["pos_y"] if row else 0.0)

            cur_meta = _json_loads_safe(row["metadata_json"] if row else None, {})
            if metadata:
                cur_meta.update(metadata)

            overrides = _json_loads_safe(row["user_overrides_json"] if row else None, {})
            if provenance == "user_managed":
                overrides["name"] = clean_name
                overrides["device_type"] = device_type
                if ownership_status:
                    overrides["ownership_status"] = ownership_status
                if topology_scope:
                    overrides["topology_scope"] = topology_scope
                if trust_zone:
                    overrides["trust_zone"] = trust_zone
                if device_role:
                    overrides["device_role"] = device_role

            final_prov = (
                "hybrid"
                if (row and row["provenance"] == "discovery_managed" and provenance == "user_managed")
                else (row["provenance"] if row and provenance != "user_managed" else provenance)
            )
            final_own = ownership_status or (row["ownership_status"] if row else ("owned" if provenance == "user_managed" and device_type != "wan" else "unknown"))
            final_scope = topology_scope or (row["topology_scope"] if row else ("isp_upstream" if device_type == "wan" else ("enterprise_internal" if final_own == "owned" else "unclassified")))
            final_zone = trust_zone or (row["trust_zone"] if row else ("isp" if device_type == "wan" else ("internal" if final_own == "owned" else "unknown")))
            final_role = device_role or cur_meta.get("role") or (row["device_role"] if row else "unspecified")

            reach = "unreachable" if status == "offline" else (row["reachability_status"] if row and row["reachability_status"] != "unknown" else "unknown")
            mgmt = row["management_status"] if row else "not_attempted"
            fresh = row["observation_freshness"] if row else "fresh"
            first_seen = row["first_seen"] if (row and row["first_seen"]) else now

            conn.execute(
                """
                INSERT INTO topology_nodes (
                    id, name, identity, ip, mac, device_type, status, latency_ms, pos_x, pos_y,
                    last_seen, metadata_json, discovery_status, ownership_status, topology_scope,
                    trust_zone, device_role, confidence, confidence_reason, provenance,
                    user_overrides_json, reachability_status, management_status, observation_freshness,
                    availability_reason, first_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    identity = COALESCE(excluded.identity, topology_nodes.identity),
                    ip = CASE WHEN excluded.ip != '' THEN excluded.ip ELSE topology_nodes.ip END,
                    mac = CASE WHEN excluded.mac != '' THEN excluded.mac ELSE topology_nodes.mac END,
                    device_type = excluded.device_type,
                    status = excluded.status,
                    latency_ms = excluded.latency_ms,
                    pos_x = excluded.pos_x,
                    pos_y = excluded.pos_y,
                    last_seen = excluded.last_seen,
                    metadata_json = excluded.metadata_json,
                    ownership_status = excluded.ownership_status,
                    topology_scope = excluded.topology_scope,
                    trust_zone = excluded.trust_zone,
                    device_role = excluded.device_role,
                    provenance = excluded.provenance,
                    user_overrides_json = excluded.user_overrides_json,
                    reachability_status = excluded.reachability_status
                """,
                (
                    clean_id,
                    clean_name,
                    sanitize_untrusted_text(identity or clean_name, 80),
                    clean_ip,
                    clean_mac,
                    device_type,
                    status,
                    latency_ms,
                    final_pos_x,
                    final_pos_y,
                    now,
                    json.dumps(cur_meta),
                    "manual" if final_prov == "user_managed" else (row["discovery_status"] if row else "discovered"),
                    final_own,
                    final_scope,
                    final_zone,
                    final_role,
                    "high" if final_prov in ("user_managed", "hybrid") else "unknown",
                    "Administrator defined or edited node." if final_prov in ("user_managed", "hybrid") else "",
                    final_prov,
                    json.dumps(overrides),
                    reach,
                    mgmt,
                    fresh,
                    row["availability_reason"] if row else "Manually registered node.",
                    first_seen,
                ),
            )
            conn.commit()

        if provenance == "user_managed":
            self.record_evidence(
                subject_type="node",
                subject_id=clean_id,
                evidence_type="user_confirmed",
                protocol="manual",
                directness="manual",
                confidence="high",
                explanation=f"Node '{clean_name}' manually created or updated by administrator.",
                observed_at=now,
            )

        return {"success": True, "id": clean_id}

    def classify_node_override(
        self,
        node_id: str,
        *,
        name: Optional[str] = None,
        identity: Optional[str] = None,
        ownership_status: Optional[str] = None,
        topology_scope: Optional[str] = None,
        trust_zone: Optional[str] = None,
        device_role: Optional[str] = None,
        is_isp_boundary: Optional[bool] = None,
        excluded_from_discovery: Optional[bool] = None,
        reason: str = "",
        actor: str = "admin",
    ) -> Dict[str, Any]:
        """Persists auditable administrator overrides that survive all future discovery scans."""
        if ownership_status and ownership_status not in OWNERSHIP_VALUES:
            raise ValueError(f"Invalid ownership_status '{ownership_status}'.")
        if topology_scope and topology_scope not in TOPOLOGY_SCOPE_VALUES:
            raise ValueError(f"Invalid topology_scope '{topology_scope}'.")
        if trust_zone and trust_zone not in TRUST_ZONE_VALUES:
            raise ValueError(f"Invalid trust_zone '{trust_zone}'.")

        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return {"success": False, "not_found": True, "error": f"Node '{node_id}' not found."}

            before = dict(row)
            overrides = _json_loads_safe(row["user_overrides_json"], {})
            meta = _json_loads_safe(row["metadata_json"], {})

            new_name = sanitize_untrusted_text(name, 80) if name else row["name"]
            new_ident = sanitize_untrusted_text(identity, 80) if identity else row["identity"]
            new_own = ownership_status or row["ownership_status"]
            new_scope = topology_scope or row["topology_scope"]
            new_zone = trust_zone or row["trust_zone"]
            new_role = sanitize_untrusted_text(device_role, 64) if device_role else row["device_role"]
            new_disc = row["discovery_status"]

            if name:
                overrides["name"] = new_name
            if identity:
                overrides["identity"] = new_ident
            if ownership_status:
                overrides["ownership_status"] = new_own
                if new_own in ("owned", "third_party", "managed_external") and new_disc == "pending_review":
                    new_disc = "discovered"
            if topology_scope:
                overrides["topology_scope"] = new_scope
            if trust_zone:
                overrides["trust_zone"] = new_zone
            if device_role:
                overrides["device_role"] = new_role
                meta["role"] = new_role
            if is_isp_boundary is not None:
                overrides["is_isp_boundary"] = bool(is_isp_boundary)
                meta["is_isp_boundary"] = bool(is_isp_boundary)
                if is_isp_boundary and not topology_scope:
                    new_scope = "isp_upstream"
                    overrides["topology_scope"] = "isp_upstream"
                if is_isp_boundary and not trust_zone:
                    new_zone = "isp"
                    overrides["trust_zone"] = "isp"
            if excluded_from_discovery is not None:
                overrides["excluded_from_discovery"] = bool(excluded_from_discovery)
                meta["excluded_from_discovery"] = bool(excluded_from_discovery)
                if excluded_from_discovery:
                    new_disc = "excluded"

            new_prov = "user_managed" if row["provenance"] == "user_managed" else "hybrid"
            clean_reason = sanitize_untrusted_text(reason or "Administrator classification override", 300)

            conn.execute(
                """
                UPDATE topology_nodes
                SET name = ?, identity = ?, ownership_status = ?, topology_scope = ?, trust_zone = ?,
                    device_role = ?, discovery_status = ?, provenance = ?, confidence = 'high',
                    confidence_reason = ?, last_verified = ?, user_overrides_json = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    new_name,
                    new_ident,
                    new_own,
                    new_scope,
                    new_zone,
                    new_role,
                    new_disc,
                    new_prov,
                    clean_reason,
                    now,
                    json.dumps(overrides),
                    json.dumps(meta),
                    node_id,
                ),
            )
            conn.execute(
                "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, before_json, after_json, created_at) "
                "VALUES (?, 'classify_node', 'node', ?, ?, ?, ?, ?)",
                (
                    actor,
                    node_id,
                    clean_reason,
                    json.dumps({"ownership": before["ownership_status"], "scope": before["topology_scope"], "zone": before["trust_zone"]}),
                    json.dumps({"ownership": new_own, "scope": new_scope, "zone": new_zone, "overrides": overrides}),
                    now,
                ),
            )
            conn.commit()

        self.record_evidence(
            subject_type="node",
            subject_id=node_id,
            evidence_type="user_confirmed",
            protocol="admin_override",
            directness="manual",
            confidence="high",
            explanation=clean_reason,
            observed_at=now,
        )
        return {"success": True, "node_id": node_id, "ownership_status": new_own, "topology_scope": new_scope, "trust_zone": new_zone}

    def upsert_link(
        self,
        source_id: str,
        target_id: str,
        source_port: str = "",
        target_port: str = "",
        link_type: str = "ethernet",
        status: str = "up",
        bandwidth: str = "",
        *,
        verification_status: str = "manual",
        provenance: str = "user_managed",
        notes: str = "",
    ) -> Dict[str, Any]:
        sp = sanitize_untrusted_text(source_port, 64)
        tp = sanitize_untrusted_text(target_port, 64)
        norm_type = "physical" if link_type in ("ethernet", "fiber") else link_type
        if norm_type not in LINK_TYPE_VALUES:
            norm_type = "physical"

        link_id = f"{source_id}->{target_id}:{sp}:{tp}"
        now = time.time()
        overrides = {"locked": True} if provenance == "user_managed" else {}
        ev_sources = [f"admin:manual_link"] if provenance == "user_managed" else []

        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                """
                INSERT INTO topology_links (
                    id, source_id, target_id, source_port, target_port, link_type, status, bandwidth,
                    last_checked, verification_status, evidence_sources_json, confidence,
                    confidence_reason, provenance, user_overrides_json, first_seen, last_seen,
                    last_verified, admin_status, oper_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'up', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_port = excluded.source_port,
                    target_port = excluded.target_port,
                    link_type = excluded.link_type,
                    status = excluded.status,
                    bandwidth = excluded.bandwidth,
                    last_checked = excluded.last_checked,
                    last_seen = excluded.last_seen,
                    verification_status = excluded.verification_status,
                    provenance = excluded.provenance,
                    user_overrides_json = excluded.user_overrides_json,
                    notes = excluded.notes
                """,
                (
                    link_id,
                    source_id,
                    target_id,
                    sp,
                    tp,
                    norm_type,
                    status,
                    bandwidth,
                    now,
                    verification_status,
                    json.dumps(ev_sources),
                    "high" if verification_status in ("manual", "confirmed") else "unknown",
                    "Manually wired or confirmed by administrator.",
                    provenance,
                    json.dumps(overrides),
                    now,
                    now,
                    now if verification_status in ("manual", "confirmed") else None,
                    status,
                    sanitize_untrusted_text(notes, 300),
                ),
            )
            conn.commit()

        if provenance == "user_managed":
            self.record_evidence(
                subject_type="link",
                subject_id=link_id,
                evidence_type="manual_link",
                protocol="manual",
                local_interface=sp,
                remote_interface=tp,
                directness="manual",
                confidence="high",
                explanation=f"Manual wiring {source_id}:{sp} <-> {target_id}:{tp} created by administrator.",
                observed_at=now,
            )
        return {"success": True, "id": link_id}

    def verify_or_override_link(
        self,
        link_id: str,
        *,
        verification_status: str = "confirmed",
        source_port: Optional[str] = None,
        target_port: Optional[str] = None,
        link_type: Optional[str] = None,
        notes: Optional[str] = None,
        reason: str = "",
        actor: str = "admin",
    ) -> Dict[str, Any]:
        if verification_status not in VERIFICATION_STATUS_VALUES:
            raise ValueError(f"Invalid verification_status '{verification_status}'.")
        now = time.time()
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM topology_links WHERE id = ?", (link_id,)).fetchone()
            if not row:
                return {"success": False, "not_found": True, "error": f"Link '{link_id}' not found."}

            sp = sanitize_untrusted_text(source_port, 64) if source_port is not None else row["source_port"]
            tp = sanitize_untrusted_text(target_port, 64) if target_port is not None else row["target_port"]
            lt = link_type or ("physical" if verification_status == "confirmed" and row["link_type"] == "layer2_adjacency" else row["link_type"])
            nt = sanitize_untrusted_text(notes, 300) if notes is not None else (row["notes"] or "")
            clean_reason = sanitize_untrusted_text(reason or f"Administrator marked link '{verification_status}'.", 300)
            overrides = _json_loads_safe(row["user_overrides_json"], {})
            overrides["locked"] = verification_status in ("confirmed", "manual")
            new_prov = "user_managed" if row["provenance"] == "user_managed" else "hybrid"

            conn.execute(
                """
                UPDATE topology_links
                SET source_port = ?, target_port = ?, link_type = ?, verification_status = ?,
                    confidence = ?, confidence_reason = ?, provenance = ?, user_overrides_json = ?,
                    last_verified = ?, notes = ?
                WHERE id = ?
                """,
                (
                    sp,
                    tp,
                    lt,
                    verification_status,
                    "high" if verification_status in ("confirmed", "manual") else "low",
                    clean_reason,
                    new_prov,
                    json.dumps(overrides),
                    now if verification_status in ("confirmed", "manual") else row["last_verified"],
                    nt,
                    link_id,
                ),
            )
            conn.execute(
                "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, before_json, after_json, created_at) "
                "VALUES (?, 'verify_link', 'link', ?, ?, ?, ?, ?)",
                (
                    actor,
                    link_id,
                    clean_reason,
                    json.dumps({"verification_status": row["verification_status"], "ports": [row["source_port"], row["target_port"]]}),
                    json.dumps({"verification_status": verification_status, "ports": [sp, tp], "link_type": lt}),
                    now,
                ),
            )
            conn.commit()

        self.record_evidence(
            subject_type="link",
            subject_id=link_id,
            evidence_type="user_confirmed",
            protocol="admin_override",
            local_interface=sp,
            remote_interface=tp,
            directness="manual",
            confidence="high",
            explanation=clean_reason,
            observed_at=now,
        )
        return {"success": True, "link_id": link_id, "verification_status": verification_status}

    def update_node_position(self, node_id: str, pos_x: float, pos_y: float) -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            cur = conn.execute("UPDATE topology_nodes SET pos_x = ?, pos_y = ? WHERE id = ?", (pos_x, pos_y, node_id))
            conn.commit()
            return cur.rowcount > 0

    def delete_node(self, node_id: str) -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("DELETE FROM topology_evidence WHERE subject_type = 'node' AND subject_id = ?", (node_id,))
            link_ids = [r[0] for r in conn.execute("SELECT id FROM topology_links WHERE source_id = ? OR target_id = ?", (node_id, node_id)).fetchall()]
            for lid in link_ids:
                conn.execute("DELETE FROM topology_evidence WHERE subject_type = 'link' AND subject_id = ?", (lid,))
            conn.execute("DELETE FROM topology_links WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            
            for tbl in ("nms_device_profiles", "nms_device_metrics", "nms_interface_metrics", "nms_incidents"):
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone():
                    conn.execute(f"DELETE FROM {tbl} WHERE device_id = ?", (node_id,))
            
            cur = conn.execute("DELETE FROM topology_nodes WHERE id = ?", (node_id,))
            conn.commit()
            return cur.rowcount > 0

    def delete_link(self, link_id: str) -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("DELETE FROM topology_evidence WHERE subject_type = 'link' AND subject_id = ?", (link_id,))
            cur = conn.execute("DELETE FROM topology_links WHERE id = ?", (link_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_topology(self) -> Dict[str, Any]:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("DELETE FROM topology_evidence")
            conn.execute("DELETE FROM topology_conflicts")
            conn.execute("DELETE FROM topology_links")
            conn.execute("DELETE FROM topology_nodes")
            
            for tbl in ("nms_device_profiles", "nms_device_metrics", "nms_interface_metrics", "nms_incidents"):
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone():
                    conn.execute(f"DELETE FROM {tbl}")
                    
            conn.execute("DELETE FROM topology_discovery_jobs")
            conn.execute("DELETE FROM topology_audit_log")
            conn.commit()
        return {"success": True, "message": "Seluruh data topologi dan NMS telah dikosongkan."}

    # ------------------------------------------------------------------
    # Active Probing & Lightweight Status / Freshness Refresh
    # ------------------------------------------------------------------

    def probe_node_icmp(
        self,
        node_id: str,
        *,
        force: bool = False,
        now: Optional[float] = None,
        ping_fn: Any = None,
    ) -> Dict[str, Any]:
        """
        Executes a rate-limited, timeout-bounded ICMP reachability probe.
        CRITICAL:
        - Never alters ownership_status or topology_scope (ping != ownership!).
        - Never deletes a node on failed ping.
        - Never creates or upgrades physical links.
        """
        ts = now if now is not None else time.time()
        pol = self.get_policy()
        cooldown = float(pol.get("probe_cooldown_sec", 15))

        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return {"success": False, "not_found": True, "error": "Node tidak ditemukan."}
            ip = normalize_ip(row["ip"])
            if not ip:
                return {"success": False, "error": "Node tidak memiliki alamat IP."}
            last_probe = row["last_probe_at"]
            if not force and last_probe and (ts - float(last_probe)) < cooldown:
                wait_s = round(cooldown - (ts - float(last_probe)), 1)
                return {
                    "success": False,
                    "rate_limited": True,
                    "retry_after_sec": wait_s,
                    "error": f"Probe rate-limited; coba lagi dalam {wait_s} detik.",
                }

        runner = ping_fn or bounded_icmp_ping
        probe_res = runner(
            ip,
            count=1,
            timeout_sec=int(pol.get("probe_timeout_sec", 4)),
            retries=int(pol.get("probe_retries", 1)),
        )
        alive = bool(probe_res.get("alive", False))
        rtt = float(probe_res.get("avg_rtt_ms") or 0.0)

        self.record_evidence(
            subject_type="node",
            subject_id=node_id,
            evidence_type="icmp_ping",
            protocol="icmp",
            observed_endpoint=ip,
            directness="direct",
            confidence="medium" if alive else "low",
            explanation=f"ICMP ping {'replied (' + str(rtt) + ' ms)' if alive else 'timed out / no reply'}.",
            raw_excerpt=probe_res.get("raw_excerpt", ""),
            observed_at=ts,
        )

        ev_list = self.get_node_evidence(node_id)
        with self._lock, closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM topology_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return {"success": False, "error": "Node hilang saat update."}
            new_last_seen = ts if alive else row["last_seen"]
            ssh_ok = True if row["management_status"] == "managed" else (False if row["management_status"] == "management_unavailable" else None)

            calc = calculate_deterministic_node_status(
                evidence_list=ev_list,
                last_seen=new_last_seen,
                last_probe_at=ts,
                last_ping_alive=alive,
                ssh_ok=ssh_ok,
                management_authorized=(row["management_status"] != "not_authorized"),
                provenance=row["provenance"] or "discovery_managed",
                current_legacy_status=row["status"] or "online",
                now=ts,
                fresh_sec=pol["freshness_threshold_sec"],
                expire_sec=pol["expire_threshold_sec"],
            )
            conn.execute(
                """
                UPDATE topology_nodes
                SET last_probe_at = ?, last_ping_alive = ?, last_seen = ?, latency_ms = ?,
                    reachability_status = ?, observation_freshness = ?, availability_reason = ?, status = ?
                WHERE id = ?
                """,
                (
                    ts,
                    1 if alive else 0,
                    new_last_seen,
                    rtt if alive else row["latency_ms"],
                    calc["reachability_status"],
                    calc["observation_freshness"],
                    calc["availability_reason"],
                    calc["legacy_status"],
                    node_id,
                ),
            )
            conn.commit()

        return {
            "success": True,
            "node_id": node_id,
            "alive": alive,
            "latency_ms": rtt,
            "reachability_status": calc["reachability_status"],
            "observation_freshness": calc["observation_freshness"],
            "availability_reason": calc["availability_reason"],
            "status": calc["legacy_status"],
        }

    def refresh_statuses(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Lightweight status & freshness evaluation without opening any SSH sessions."""
        ts = now if now is not None else time.time()
        pol = self.get_policy()
        updated = 0

        with self._lock, closing(self._get_connection()) as conn:
            table_names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            has_nms = "nms_device_profiles" in table_names

            rows = conn.execute("SELECT * FROM topology_nodes").fetchall()
            for r in rows:
                if has_nms:
                    prof = conn.execute(
                        "SELECT status, consecutive_failures, last_error FROM nms_device_profiles WHERE device_id = ?",
                        (r["id"],),
                    ).fetchone()
                    if prof and prof["status"] in ("DOWN", "SUSPECTED_DOWN"):
                        target_reach = "unreachable" if prof["status"] == "DOWN" else "suspected_down"
                        target_leg = "offline" if prof["status"] == "DOWN" else "warning"
                        err_msg = prof["last_error"] or ("Consecutive check failures" if prof["status"] == "DOWN" else "Health check failing")
                        target_reason = f"NMS Alert: {prof['status']}. {err_msg}".strip()
                        if r["reachability_status"] != target_reach or r["status"] != target_leg:
                            conn.execute(
                                """
                                UPDATE topology_nodes
                                SET reachability_status = ?, observation_freshness = 'fresh', availability_reason = ?, status = ?
                                WHERE id = ?
                                """,
                                (target_reach, target_reason, target_leg, r["id"]),
                            )
                            updated += 1
                        continue
                ev_rows = conn.execute(
                    "SELECT evidence_type, observed_at FROM topology_evidence WHERE subject_type = 'node' AND subject_id = ?",
                    (r["id"],),
                ).fetchall()
                ev_list = [{"evidence_type": er["evidence_type"], "observed_at": er["observed_at"]} for er in ev_rows]
                ssh_ok = True if r["management_status"] == "managed" else (False if r["management_status"] == "management_unavailable" else None)
                last_ping = None if r["last_ping_alive"] is None else bool(r["last_ping_alive"])

                calc = calculate_deterministic_node_status(
                    evidence_list=ev_list,
                    last_seen=r["last_seen"],
                    last_probe_at=r["last_probe_at"],
                    last_ping_alive=last_ping,
                    ssh_ok=ssh_ok,
                    management_authorized=(r["management_status"] != "not_authorized"),
                    provenance=r["provenance"] or "discovery_managed",
                    current_legacy_status=r["status"] or "online",
                    now=ts,
                    fresh_sec=pol["freshness_threshold_sec"],
                    expire_sec=pol["expire_threshold_sec"],
                )
                if (
                    calc["observation_freshness"] != r["observation_freshness"]
                    or calc["reachability_status"] != r["reachability_status"]
                    or calc["legacy_status"] != r["status"]
                ):
                    conn.execute(
                        """
                        UPDATE topology_nodes
                        SET reachability_status = ?, observation_freshness = ?, availability_reason = ?, status = ?
                        WHERE id = ?
                        """,
                        (
                            calc["reachability_status"],
                            calc["observation_freshness"],
                            calc["availability_reason"],
                            calc["legacy_status"],
                            r["id"],
                        ),
                    )
                    updated += 1
            conn.commit()
        return {"success": True, "updated_nodes": updated, "evaluated_at": ts}

    # ------------------------------------------------------------------
    # Bounded Discovery Execution (Stages 1-11)
    # ------------------------------------------------------------------

    def sync_from_seed_router(
        self,
        device_name: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        *,
        mode: Optional[str] = None,
        conn_mgr_override: Any = None,
        inv_store_override: Any = None,
    ) -> Dict[str, Any]:
        """
        Bounded, single-flight discovery job starting from an authorized Inventory seed router.
        Never wipes confirmed topology on transient errors and never interrogates unknown neighbors.
        """
        if not self._discovery_lock.acquire(blocking=False):
            return {
                "success": False,
                "already_running": True,
                "active_job_id": self._active_job_id,
                "error": "Proses discovery lain sedang berjalan; tunggu hingga selesai.",
            }

        job_id = f"disc_{uuid.uuid4().hex[:10]}"
        self._active_job_id = job_id
        started_at = time.time()

        try:
            from agents.akane.connection_manager import get_connection_manager
            from core.inventory_store import get_inventory_store

            conn_mgr = conn_mgr_override or get_connection_manager()
            inv = inv_store_override or get_inventory_store()
            base_pol = self.get_policy()
            effective_mode = mode if (mode in DISCOVERY_MODE_VALUES) else base_pol.get("discovery_mode", "seed_only")
            pol = {**base_pol, "discovery_mode": effective_mode}
            max_depth = 1 if effective_mode == "seed_only" else max(1, int(pol.get("discovery_depth", 1)))
            max_duration = float(pol.get("max_scan_duration_sec", 45))

            inv_devices = inv.list_devices().get("devices", [])
            enabled_devs = [d for d in inv_devices if d.get("enabled", True)]

            # Stage A: Validate Authorized Seed Device from Inventory!
            seed_dev: Optional[Dict[str, Any]] = None
            req_name = (device_name or pol.get("seed_device_id") or "").strip()

            if req_name:
                seed_dev = next((d for d in enabled_devs if d["name"].lower() == req_name.lower()), None)
                if not seed_dev:
                    return {
                        "success": False,
                        "error": f"Seed device '{sanitize_untrusted_text(req_name, 64)}' tidak terdaftar atau tidak aktif di Inventory.",
                    }
            elif host:
                norm_h = normalize_ip(host) or host.strip()
                seed_dev = next((d for d in enabled_devs if (normalize_ip(d["host"]) or d["host"]) == norm_h), None)
                if not seed_dev:
                    return {
                        "success": False,
                        "error": "Host target tidak terdaftar di Inventory; discovery ke jaringan acak tanpa otorisasi ditolak.",
                    }
            else:
                sessions = [s for s in conn_mgr.list_sessions() if s.get("status") != "closed" and s.get("device_name")]
                if sessions:
                    sname = sessions[0]["device_name"].lower()
                    seed_dev = next((d for d in enabled_devs if d["name"].lower() == sname), None)
                if not seed_dev and enabled_devs:
                    seed_dev = enabled_devs[0]

            if not seed_dev:
                return {"success": False, "error": "Belum ada router resmi yang terdaftar di Inventory."}

            with self._lock, closing(self._get_connection()) as conn:
                conn.execute(
                    "INSERT INTO topology_discovery_jobs (job_id, seed_device, mode, status, started_at) VALUES (?, ?, ?, 'running', ?)",
                    (job_id, seed_dev["name"], effective_mode, started_at),
                )
                conn.commit()

            errors: List[str] = []
            limitations: List[str] = []
            visited_names: Set[str] = set()
            queue: List[Tuple[str, str, int]] = [(seed_dev["name"], seed_dev["host"], 0)]

            hops_scanned = 0
            total_nodes_obs = 0
            total_links_obs = 0
            first_details: Optional[Dict[str, Any]] = None

            while queue:
                if (time.time() - started_at) > max_duration:
                    limitations.append(f"Batas durasi scan ({max_duration}s) tercapai; ekspansi dihentikan dengan aman.")
                    break

                cur_name, cur_host, depth = queue.pop(0)
                if cur_name.lower() in visited_names:
                    continue
                visited_names.add(cur_name.lower())

                cur_ip = normalize_ip(cur_host)
                if depth > 0 and cur_ip and ip_in_subnets(cur_ip, pol.get("excluded_subnets", [])):
                    limitations.append(f"Melewati {cur_name} ({cur_ip}): berada di excluded_subnets.")
                    continue

                # Check if node was marked excluded_from_discovery by administrator
                cand_nid = f"node_{re.sub(r'[^a-zA-Z0-9_]', '_', cur_name.lower())}"
                with self._lock, closing(self._get_connection()) as conn:
                    ex_row = conn.execute("SELECT user_overrides_json FROM topology_nodes WHERE id = ?", (cand_nid,)).fetchone()
                    if ex_row and _json_loads_safe(ex_row["user_overrides_json"], {}).get("excluded_from_discovery"):
                        limitations.append(f"Melewati {cur_name}: dikecualikan dari recursive discovery oleh admin.")
                        continue

                interrogated = self.interrogate_routeros_readonly(
                    conn_mgr, device_name=cur_name, host=cur_host, timeout=15.0
                )
                if not interrogated.get("success"):
                    err_msg = sanitize_untrusted_text(interrogated.get("error", "Interrogation failed"), 200)
                    errors.append(f"{cur_name}: {err_msg}")
                    # Update management_status on existing node WITHOUT deleting confirmed topology!
                    with self._lock, closing(self._get_connection()) as conn:
                        row = conn.execute(
                            "SELECT * FROM topology_nodes WHERE id = ? OR (ip != '' AND ip = ?) ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END LIMIT 1",
                            (cand_nid, cur_ip, cand_nid),
                        ).fetchone()
                        if row:
                            conn.execute(
                                "UPDATE topology_nodes SET management_status = 'management_unavailable', "
                                "availability_reason = ? WHERE id = ?",
                                (f"SSH management unavailable: {err_msg}", row["id"]),
                            )
                            conn.commit()
                    self.refresh_statuses()
                    if depth == 0:
                        self._finish_job(
                            job_id, "failed", started_at, hops_scanned, total_nodes_obs, total_links_obs,
                            errors, limitations, f"Gagal menginterogasi seed router {cur_name}."
                        )
                        return {"success": False, "job_id": job_id, "error": f"Gagal menginterogasi {cur_name}: {err_msg}"}
                    continue

                outs = interrogated["outputs"]
                limitations.extend(interrogated.get("limitations", []))

                parsed = self.discover_from_device_output(
                    source_name=cur_name,
                    source_ip=cur_ip or cur_host,
                    identity_output=outs.get("identity", ""),
                    resource_output=outs.get("resource", ""),
                    neighbor_output=outs.get("neighbor", ""),
                    interface_output=outs.get("interface", ""),
                    route_output=outs.get("route", ""),
                    nat_output=outs.get("nat", ""),
                    arp_output=outs.get("arp", ""),
                    dhcp_client_output=outs.get("dhcp_client", ""),
                    wireless_output=outs.get("wireless", ""),
                    routerboard_output=outs.get("routerboard", ""),
                    ip_address_output=outs.get("ip_address", ""),
                    bridge_port_output=outs.get("bridge_port", ""),
                    bridge_host_output=outs.get("bridge_host", ""),
                    dhcp_lease_output=outs.get("dhcp_lease", ""),
                    vlan_output=outs.get("vlan", ""),
                    bridge_vlan_output=outs.get("bridge_vlan", ""),
                    policy=pol,
                    inventory_devices=enabled_devs,
                    hop_depth=depth,
                )
                hops_scanned += 1
                total_nodes_obs += 1 + int(parsed.get("new_nodes_added", 0))
                total_links_obs += int(parsed.get("links_added", 0))
                if first_details is None:
                    first_details = parsed

                # Recursive expansion ONLY in enterprise_managed / authorized_expansion within max_depth
                if effective_mode in ("enterprise_managed", "authorized_expansion") and (depth + 1) < max_depth:
                    for cand in parsed.get("downstream_candidates", []):
                        cname = cand["device_name"]
                        chost = cand["host"]
                        cip = normalize_ip(chost)
                        if cname.lower() in visited_names:
                            continue
                        if cip and pol.get("enterprise_subnets") and effective_mode == "enterprise_managed":
                            if not ip_in_subnets(cip, pol["enterprise_subnets"]) and not ip_in_subnets(cip, pol.get("management_subnets", [])):
                                limitations.append(f"Melewati ekspansi ke {cname} ({cip}): di luar enterprise_subnets.")
                                continue
                        queue.append((cname, chost, depth + 1))
                elif parsed.get("downstream_candidates") and effective_mode == "seed_only":
                    limitations.append(
                        f"Mode 'seed_only' aktif: {len(parsed['downstream_candidates'])} perangkat terkelola downstream tidak diinterogasi rekursif."
                    )

            summary = (
                f"Discovery ({effective_mode}) selesai dari {seed_dev['name']}: "
                f"{hops_scanned} router diinterogasi, {total_nodes_obs} perangkat diamati."
            )
            self._finish_job(
                job_id, "completed", started_at, hops_scanned, total_nodes_obs, total_links_obs,
                errors, limitations, summary
            )
            return {
                "success": True,
                "job_id": job_id,
                "mode": effective_mode,
                "message": summary,
                "errors": errors,
                "limitations": limitations,
                "details": first_details or {},
            }

        finally:
            self._active_job_id = None
            self._discovery_lock.release()

    def _finish_job(
        self,
        job_id: str,
        status: str,
        started_at: float,
        hops: int,
        nodes_obs: int,
        links_obs: int,
        errors: List[str],
        limitations: List[str],
        summary: str,
    ) -> None:
        fin = time.time()
        dur_ms = round((fin - started_at) * 1000.0, 1)
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute(
                """
                UPDATE topology_discovery_jobs
                SET status = ?, finished_at = ?, duration_ms = ?, hops_scanned = ?,
                    nodes_observed = ?, links_observed = ?, errors_json = ?, limitations_json = ?, summary = ?
                WHERE job_id = ?
                """,
                (status, fin, dur_ms, hops, nodes_obs, links_obs, json.dumps(errors), json.dumps(limitations), summary, job_id),
            )
            conn.commit()

    def sync_from_router_async(
        self,
        device_name: Optional[str] = None,
        host: Optional[str] = None,
    ) -> None:
        """Runs non-blocking background discovery only if no scan is currently active."""
        if self._active_job_id is not None:
            return

        def _worker():
            try:
                self.sync_from_seed_router(device_name=device_name, host=host)
            except Exception as exc:
                logger.debug("Background topology sync skipped: %s", exc)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Graph Query, View Scope Filtering, Review Queue & Jobs
    # ------------------------------------------------------------------

    def get_topology(self, view_mode: Optional[str] = None, now: Optional[float] = None) -> Dict[str, Any]:
        """Returns topology graph, V2 governance metadata, and comprehensive statistics."""
        self.refresh_statuses(now=now)
        pol = self.get_policy()

        with self._lock, closing(self._get_connection()) as conn:
            table_names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "nms_device_profiles" in table_names:
                node_rows = conn.execute(
                    """
                    SELECT n.*,
                           p.status as nms_status,
                           p.last_check_at as nms_last_check_at,
                           p.last_success_at as nms_last_success_at,
                           p.consecutive_failures as nms_consecutive_failures,
                           p.last_error as nms_last_error,
                           p.monitoring_method as nms_monitoring_method,
                           p.name_source as nms_name_source,
                           p.device_identity as nms_device_identity,
                           p.routeros_version as nms_routeros_version,
                           p.routeros_model as nms_routeros_model,
                           p.monitoring_enabled as nms_monitoring_enabled,
                           p.is_paused as nms_is_paused,
                           p.maintenance_mode as nms_maintenance_mode
                    FROM topology_nodes n
                    LEFT JOIN nms_device_profiles p ON n.id = p.device_id
                    ORDER BY n.name ASC
                    """
                ).fetchall()
            else:
                node_rows = conn.execute("SELECT * FROM topology_nodes ORDER BY name ASC").fetchall()

            link_rows = conn.execute("SELECT * FROM topology_links").fetchall()
            open_conflicts = conn.execute(
                "SELECT * FROM topology_conflicts WHERE status = 'open' ORDER BY created_at DESC"
            ).fetchall()
            last_job_row = conn.execute(
                "SELECT * FROM topology_discovery_jobs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

        all_nodes: List[Dict[str, Any]] = []
        status_counts = {"online": 0, "warning": 0, "offline": 0}
        ownership_counts = {"owned": 0, "managed_external": 0, "third_party": 0, "unknown": 0}
        scope_counts: Dict[str, int] = {}
        freshness_counts = {"fresh": 0, "stale": 0, "expired": 0, "unknown": 0}
        type_counts: Dict[str, int] = {}

        for row in node_rows:
            r = dict(row)
            meta = _json_loads_safe(r["metadata_json"], {})
            overrides = _json_loads_safe(r["user_overrides_json"], {})

            nms_st = r["nms_status"] if "nms_status" in r.keys() else None
            last_chk = r["nms_last_check_at"] if "nms_last_check_at" in r.keys() else None
            stale = is_check_stale(last_chk, interval_sec=pol.get("freshness_threshold_sec", 45)) if last_chk else False

            st = r["status"] or "online"
            reachability = r["reachability_status"] or "unknown"
            reason = r["availability_reason"] or ""

            if nms_st:
                if nms_st == "DOWN":
                    st = "offline"
                    reachability = "unreachable"
                    if r.get("nms_last_error"):
                        reason = f"Down: {r['nms_last_error']}"
                elif nms_st == "SUSPECTED_DOWN":
                    st = "warning"
                    reachability = "suspected_down"
                    if r.get("nms_last_error"):
                        reason = f"Suspected Down ({r.get('nms_consecutive_failures', 1)}x): {r['nms_last_error']}"
                elif nms_st == "UP":
                    st = "online"
                    reachability = "reachable"
                elif nms_st == "MONITORING_UNAVAILABLE":
                    st = "warning"
                    reachability = "reachable"
                    reason = f"Monitoring Unavailable: {r.get('nms_last_error', 'Management unreachable')}"
                elif nms_st == "MAINTENANCE":
                    st = "warning"
                    reachability = "maintenance"
                    reason = "Device in maintenance mode"
                elif nms_st == "UNKNOWN":
                    if not r["status"] or r["status"] == "unknown":
                        st = "warning"
                        reachability = "unknown"

            dt = r["device_type"] or "router"
            own = r["ownership_status"] or "unknown"
            scp = r["topology_scope"] or "unclassified"
            fr = r["observation_freshness"] or "unknown"

            status_counts[st] = status_counts.get(st, 0) + 1
            ownership_counts[own] = ownership_counts.get(own, 0) + 1
            scope_counts[scp] = scope_counts.get(scp, 0) + 1
            freshness_counts[fr] = freshness_counts.get(fr, 0) + 1
            type_counts[dt] = type_counts.get(dt, 0) + 1

            all_nodes.append({
                "id": r["id"],
                "name": r["name"],
                "identity": r["identity"] or r["name"],
                "ip": r["ip"],
                "mac": r["mac"],
                "all_ips": _json_loads_safe(r["all_ips_json"], []),
                "all_macs": _json_loads_safe(r["all_macs_json"], []),
                "serial_number": r["serial_number"] or "",
                "device_type": dt,
                "device_role": r["device_role"] or "unspecified",
                "status": st,
                "reachability_status": reachability,
                "management_status": r["management_status"] or "not_attempted",
                "observation_freshness": fr,
                "availability_reason": reason,
                "discovery_status": r["discovery_status"] or "discovered",
                "ownership_status": own,
                "topology_scope": scp,
                "trust_zone": r["trust_zone"] or "unknown",
                "confidence": r["confidence"] or "unknown",
                "confidence_reason": r["confidence_reason"] or "",
                "provenance": r["provenance"] or "discovery_managed",
                "observability": r["observability"] or "not_attempted",
                "observability_reason": r["observability_reason"] or "",
                "source_device_id": r["source_device_id"] or "",
                "vlans": _json_loads_safe(r["vlans_json"], []),
                "user_overrides": overrides,
                "latency_ms": r["latency_ms"],
                "pos_x": r["pos_x"],
                "pos_y": r["pos_y"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "last_probe_at": r["last_probe_at"],
                "last_verified": r["last_verified"],
                "metadata": meta,
                "nms_status": nms_st or "UNKNOWN",
                "last_check_at": last_chk,
                "last_success_at": r["nms_last_success_at"] if "nms_last_success_at" in r.keys() else None,
                "consecutive_failures": (r["nms_consecutive_failures"] or 0) if "nms_consecutive_failures" in r.keys() else 0,
                "last_error": (r["nms_last_error"] or "") if "nms_last_error" in r.keys() else "",
                "monitoring_method": (r["nms_monitoring_method"] or "icmp_ping") if "nms_monitoring_method" in r.keys() else "icmp_ping",
                "name_source": (r["nms_name_source"] or "unknown") if "nms_name_source" in r.keys() else "unknown",
                "is_stale": stale,
                "routeros_version": (r["nms_routeros_version"] or "") if "nms_routeros_version" in r.keys() else "",
                "routeros_model": (r["nms_routeros_model"] or "") if "nms_routeros_model" in r.keys() else "",
            })

        # Apply optional visualization filter (Section 4.3)
        if view_mode == "internal_only":
            visible_nodes = [
                n for n in all_nodes
                if n["discovery_status"] != "excluded"
                and n["topology_scope"] not in ("isp_upstream", "external")
                and (
                    n["topology_scope"] in ("enterprise_internal", "enterprise_edge")
                    or n["ownership_status"] == "owned"
                )
            ]
        elif view_mode == "internal_and_edge":
            visible_nodes = [
                n for n in all_nodes
                if n["discovery_status"] != "excluded"
                and n["topology_scope"] in ("enterprise_internal", "enterprise_edge", "isp_upstream", "vpn_remote", "unclassified")
            ]
        else:
            visible_nodes = all_nodes

        visible_ids = {n["id"] for n in visible_nodes}

        links: List[Dict[str, Any]] = []
        link_ver_counts = {"confirmed": 0, "observed": 0, "inferred": 0, "manual": 0, "conflicting": 0, "unknown": 0}
        for l in link_rows:
            vs = l["verification_status"] or "unknown"
            link_ver_counts[vs] = link_ver_counts.get(vs, 0) + 1
            if l["source_id"] not in visible_ids or l["target_id"] not in visible_ids:
                continue
            links.append({
                "id": l["id"],
                "source": l["source_id"],
                "target": l["target_id"],
                "local_node_id": l["source_id"],
                "remote_node_id": l["target_id"],
                "source_port": l["source_port"],
                "target_port": l["target_port"],
                "local_interface_name": l["source_port"],
                "remote_interface_name": l["target_port"],
                "link_type": l["link_type"],
                "verification_status": vs,
                "confidence": l["confidence"] or "unknown",
                "confidence_reason": l["confidence_reason"] or "",
                "provenance": l["provenance"] or "discovery_managed",
                "evidence_sources": _json_loads_safe(l["evidence_sources_json"], []),
                "status": l["status"],
                "oper_status": l["oper_status"] or l["status"],
                "admin_status": l["admin_status"] or "up",
                "bandwidth": l["bandwidth"],
                "bandwidth_bps": l["bandwidth_bps"] or 0,
                "first_seen": l["first_seen"],
                "last_seen": l["last_seen"] or l["last_checked"],
                "last_verified": l["last_verified"],
                "last_checked": l["last_checked"],
                "notes": l["notes"] or "",
            })

        last_job = None
        if last_job_row:
            last_job = {
                "job_id": last_job_row["job_id"],
                "seed_device": last_job_row["seed_device"],
                "mode": last_job_row["mode"],
                "status": last_job_row["status"],
                "started_at": last_job_row["started_at"],
                "finished_at": last_job_row["finished_at"],
                "duration_ms": last_job_row["duration_ms"],
                "hops_scanned": last_job_row["hops_scanned"],
                "errors": _json_loads_safe(last_job_row["errors_json"], []),
                "limitations": _json_loads_safe(last_job_row["limitations_json"], []),
                "summary": last_job_row["summary"],
            }

        pending_review_count = sum(
            1 for n in all_nodes if n["ownership_status"] == "unknown" or n["discovery_status"] == "pending_review"
        )

        return {
            "success": True,
            "view_mode": view_mode or "all_observed",
            "nodes": visible_nodes,
            "links": links,
            "policy": pol,
            "last_job": last_job,
            "active_job_id": self._active_job_id,
            "stats": {
                "total_nodes": len(visible_nodes),
                "total_observed_nodes": len(all_nodes),
                "total_links": len(links),
                "online": status_counts.get("online", 0),
                "warning": status_counts.get("warning", 0),
                "offline": status_counts.get("offline", 0),
                "types": type_counts,
                "ownership": ownership_counts,
                "scopes": scope_counts,
                "freshness": freshness_counts,
                "link_verification": link_ver_counts,
                "pending_review_nodes": pending_review_count,
                "open_conflicts": len(open_conflicts),
            },
        }

    def get_review_queue(self) -> Dict[str, Any]:
        topo = self.get_topology()
        pending_nodes = [
            n for n in topo["nodes"]
            if n["ownership_status"] == "unknown" or n["discovery_status"] in ("pending_review", "excluded")
        ]
        unverified_links = [
            l for l in topo["links"]
            if l["verification_status"] in ("conflicting", "inferred", "observed")
        ]
        with self._lock, closing(self._get_connection()) as conn:
            c_rows = conn.execute("SELECT * FROM topology_conflicts WHERE status = 'open' ORDER BY created_at DESC").fetchall()
        conflicts = [
            {
                "id": r["id"],
                "conflict_type": r["conflict_type"],
                "subject_id": r["subject_id"],
                "candidate_data": _json_loads_safe(r["candidate_data_json"], {}),
                "reason": r["reason"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in c_rows
        ]
        return {
            "success": True,
            "pending_nodes": pending_nodes,
            "unverified_links": unverified_links,
            "conflicts": conflicts,
        }

    def get_discovery_jobs(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT * FROM topology_discovery_jobs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [
            {
                "job_id": r["job_id"],
                "seed_device": r["seed_device"],
                "mode": r["mode"],
                "status": r["status"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "duration_ms": r["duration_ms"],
                "hops_scanned": r["hops_scanned"],
                "nodes_observed": r["nodes_observed"],
                "links_observed": r["links_observed"],
                "errors": _json_loads_safe(r["errors_json"], []),
                "limitations": _json_loads_safe(r["limitations_json"], []),
                "summary": r["summary"],
            }
            for r in rows
        ]

    def get_audit_log(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock, closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT * FROM topology_audit_log ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "actor": r["actor"],
                "action": r["action"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "reason": r["reason"],
                "before": _json_loads_safe(r["before_json"], {}),
                "after": _json_loads_safe(r["after_json"], {}),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Autonomous Troubleshooting & Root Cause Analysis (RCA)
    # ------------------------------------------------------------------

    def troubleshoot_node(self, target_node_id: str) -> Dict[str, Any]:
        topo = self.get_topology()
        nodes_by_id = {n["id"]: n for n in topo["nodes"]}
        links = topo["links"]

        if target_node_id not in nodes_by_id:
            return {"success": False, "error": f"Node '{target_node_id}' tidak ditemukan di database topologi."}

        target = nodes_by_id[target_node_id]

        adj: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {n["id"]: [] for n in topo["nodes"]}
        for link in links:
            src = link["source"]
            dst = link["target"]
            if src in adj and dst in adj:
                adj[src].append((dst, link))
                adj[dst].append((src, link))

        gateway_candidates = [
            n for n in topo["nodes"]
            if n["device_type"] == "router"
            and n.get("topology_scope") != "isp_upstream"
            and (
                n.get("ownership_status") == "owned"
                or any(k in n["name"].lower() for k in ["core", "gateway", "main", "router"])
            )
        ]
        gateway_node = gateway_candidates[0] if gateway_candidates else (topo["nodes"][0] if topo["nodes"] else None)

        if not gateway_node or gateway_node["id"] == target_node_id:
            return {
                "success": True,
                "target_node": target,
                "is_gateway": True,
                "diagnosis": (
                    f"Perangkat {target['name']} adalah Gateway/Core Node utama "
                    f"(Ownership: {target.get('ownership_status', 'unknown')}, Reachability: {target.get('reachability_status', target['status'])}). "
                    f"Status saat ini: {target['status'].upper()} (Latency: {target['latency_ms']}ms)."
                ),
                "path": [target],
                "root_cause_found": target["status"] != "online",
            }

        start_id = gateway_node["id"]
        queue: List[List[str]] = [[start_id]]
        visited = {start_id}
        found_path: Optional[List[str]] = None

        while queue:
            current_path = queue.pop(0)
            curr = current_path[-1]
            if curr == target_node_id:
                found_path = current_path
                break
            for neighbor, _ in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(current_path + [neighbor])

        if not found_path:
            return {
                "success": True,
                "target_node": target,
                "is_isolated": True,
                "diagnosis": (
                    f"Perangkat {target['name']} terisolasi (Islands). Tidak ditemukan jalur terpetakan yang "
                    f"menghubungkannya ke Core Gateway ({gateway_node['name']}). Periksa uplink fisik atau cakupan VLAN."
                ),
                "path": [target],
                "root_cause_found": True,
            }

        path_nodes = [nodes_by_id[nid] for nid in found_path]
        hop_issues = []
        root_cause_node = None

        for idx, node in enumerate(path_nodes):
            if node["status"] != "online":
                hop_issues.append(
                    f"Hop {idx + 1}: {node['name']} [{node.get('ownership_status', 'unknown')}] "
                    f"status={node['status'].upper()} ({node.get('availability_reason', '')})"
                )
                if root_cause_node is None:
                    root_cause_node = node

        if root_cause_node and root_cause_node["id"] != target_node_id:
            boundary_note = (
                " (Catatan: hop ini berada di luar kendali internal / batas ISP)"
                if root_cause_node.get("topology_scope") in ("isp_upstream", "external")
                else ""
            )
            diagnosis = (
                f"🚨 ROOT CAUSE TERDETEKSI: Perangkat {target['name']} terganggu KARENA perangkat perantara "
                f"'{root_cause_node['name']}' ({root_cause_node['ip']}) mengalami status {root_cause_node['status'].upper()}{boundary_note}. "
                f"Selesaikan masalah pada {root_cause_node['name']} terlebih dahulu agar jalur kembali normal."
            )
        elif target["status"] != "online":
            diagnosis = (
                f"⚠️ PERANGKAT TARGET {target['status'].upper()}: Jalur interkoneksi dari Gateway ke hop sebelum {target['name']} "
                f"berjalan normal. Detail ketersediaan: {target.get('availability_reason') or 'Periksa power, firewall ICMP, atau kabel.'}"
            )
        else:
            diagnosis = (
                f"✅ KONDISI SEHAT: Seluruh {len(path_nodes)} hop dari {gateway_node['name']} ke {target['name']} "
                f"berstatus ONLINE. Latency target: {target['latency_ms']}ms."
            )

        return {
            "success": True,
            "gateway_node": gateway_node,
            "target_node": target,
            "path": path_nodes,
            "hop_issues": hop_issues,
            "root_cause_node": root_cause_node,
            "diagnosis": diagnosis,
        }

    # ------------------------------------------------------------------
    # Path Explorer & Change Impact Analysis (Master Engineering Upgrade)
    # ------------------------------------------------------------------

    def _resolve_topology_node(self, query: str, nodes_by_id: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        clean = str(query or "").strip().lower()
        if not clean:
            return None
        if clean in nodes_by_id:
            return nodes_by_id[clean]
        for node in nodes_by_id.values():
            if node.get("name") and node["name"].lower() == clean:
                return node
            if node.get("identity") and node["identity"].lower() == clean:
                return node
            if node.get("ip") and node["ip"] == clean:
                return node
        return None

    def find_path(
        self,
        source: str,
        target: str,
        layer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Traces topology path between source and target nodes with L2/L3 separation,
        interface mapping, bottleneck identification, and health scoring.
        """
        topo = self.get_topology(view_mode="all_observed")
        nodes_by_id = {n["id"]: n for n in topo["nodes"]}
        links = topo["links"]

        src_node = self._resolve_topology_node(source, nodes_by_id)
        tgt_node = self._resolve_topology_node(target, nodes_by_id)

        if not src_node:
            return {"success": False, "error": f"Source endpoint '{source}' tidak ditemukan di topologi."}
        if not tgt_node:
            return {"success": False, "error": f"Target endpoint '{target}' tidak ditemukan di topologi."}

        src_id = src_node["id"]
        tgt_id = tgt_node["id"]

        if src_id == tgt_id:
            return {
                "success": True,
                "source_node": src_node,
                "target_node": tgt_node,
                "layer_filter": layer,
                "path_found": True,
                "hop_count": 0,
                "nodes": [src_node],
                "hops": [],
                "bottlenecks": [],
                "estimated_latency_ms": 0.0,
                "path_health": "healthy",
            }

        # Build adjacency graph with layer classification
        adj: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {n["id"]: [] for n in topo["nodes"]}
        for link in links:
            l_src = link["source"]
            l_dst = link["target"]
            l_type = str(link.get("link_type") or "physical").lower()
            edge_layer = "L3" if l_type in ("routed", "vpn") else "L2"

            if layer:
                if layer.upper() == "L2" and edge_layer != "L2":
                    continue
                if layer.upper() == "L3" and edge_layer != "L3":
                    continue

            annotated_link = dict(link)
            annotated_link["layer"] = edge_layer

            if l_src in adj and l_dst in adj:
                adj[l_src].append((l_dst, annotated_link))
                adj[l_dst].append((l_src, annotated_link))

        queue: List[Tuple[List[str], List[Dict[str, Any]]]] = [([src_id], [])]
        visited = {src_id}
        found_nodes: Optional[List[str]] = None
        found_links: Optional[List[Dict[str, Any]]] = None

        while queue:
            cur_path, cur_links = queue.pop(0)
            cur_node = cur_path[-1]
            if cur_node == tgt_id:
                found_nodes = cur_path
                found_links = cur_links
                break
            for nxt, edge in adj.get(cur_node, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((cur_path + [nxt], cur_links + [edge]))

        if not found_nodes or found_links is None:
            return {
                "success": True,
                "source_node": src_node,
                "target_node": tgt_node,
                "layer_filter": layer,
                "path_found": False,
                "hop_count": 0,
                "nodes": [],
                "hops": [],
                "bottlenecks": ["Tidak ada jalur fisik/logis terhubung antara kedua perangkat."],
                "estimated_latency_ms": 0.0,
                "path_health": "broken",
            }

        hops_detail = []
        bottlenecks = []
        total_latency = 0.0

        for i, edge in enumerate(found_links):
            u_id = found_nodes[i]
            v_id = found_nodes[i + 1]
            u_node = nodes_by_id[u_id]
            v_node = nodes_by_id[v_id]

            total_latency += float(v_node.get("latency_ms") or 0.0)

            if edge.get("verification_status") in ("stale", "unknown"):
                bottlenecks.append(f"Hop {i+1} ({u_node['name']} -> {v_node['name']}): Link status '{edge.get('verification_status')}'")
            if v_node.get("status") != "online":
                bottlenecks.append(f"Hop {i+1}: Node '{v_node['name']}' status {v_node.get('status', 'unknown').upper()}")

            hops_detail.append({
                "hop_index": i + 1,
                "from_node_id": u_id,
                "from_node_name": u_node.get("name"),
                "to_node_id": v_id,
                "to_node_name": v_node.get("name"),
                "layer": edge.get("layer", "L2"),
                "link_type": edge.get("link_type", "physical"),
                "verification_status": edge.get("verification_status", "unknown"),
                "local_interface": edge.get("local_interface_id") or edge.get("local_port") or "",
                "remote_interface": edge.get("remote_interface_id") or edge.get("remote_port") or "",
                "bandwidth_bps": edge.get("bandwidth_bps", 0),
            })

        health = "broken" if any("status" in b.lower() and "offline" in b.lower() for b in bottlenecks) else (
            "degraded" if bottlenecks else "healthy"
        )

        # Audit C: Determine path certainty based on link evidence
        link_verifs = [h.get("verification_status") for h in hops_detail]
        if all(v == "confirmed" for v in link_verifs):
            path_certainty = "confirmed"
        elif all(v in ("confirmed", "observed") for v in link_verifs):
            path_certainty = "partially_observed"
        else:
            path_certainty = "inferred_incomplete"

        return {
            "success": True,
            "source_node": src_node,
            "target_node": tgt_node,
            "layer_filter": layer,
            "path_found": True,
            "path_certainty": path_certainty,
            "hop_count": len(found_links),
            "nodes": [nodes_by_id[nid] for nid in found_nodes],
            "hops": hops_detail,
            "bottlenecks": bottlenecks,
            "assumptions": [
                "Jalur didasarkan pada graf topologi yang terpetakan saat ini.",
                "Forwarding layer 3 aktual bergantung pada evaluasi routing table RouterOS (LPM), routing mark, dan status gateway.",
                "Forwarding layer 2 dapat dipengaruhi oleh STP/RSTP blocking state pada switch/bridge port.",
            ],
            "estimated_latency_ms": round(total_latency, 2),
            "path_health": health,
        }

    def analyze_change_impact(
        self,
        target_node_id: str,
        change_type: str = "node_offline",
        affected_interface: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulates network failure/maintenance on a node or link, predicting
        isolated devices, rerouted paths, and blast radius.
        """
        topo = self.get_topology(view_mode="all_observed")
        nodes_by_id = {n["id"]: n for n in topo["nodes"]}
        target_node = self._resolve_topology_node(target_node_id, nodes_by_id)

        if not target_node:
            return {"success": False, "error": f"Node target '{target_node_id}' tidak ditemukan di topologi."}

        tid = target_node["id"]
        links = topo["links"]

        gateways = [
            n["id"] for n in topo["nodes"]
            if n["device_type"] == "router"
            and n.get("topology_scope") != "isp_upstream"
            and (
                n.get("ownership_status") == "owned"
                or any(k in n["name"].lower() for k in ["core", "gateway", "main", "r1"])
            )
        ]
        if not gateways and topo["nodes"]:
            gateways = [topo["nodes"][0]["id"]]

        def build_adj(excluded_node_id: Optional[str] = None, excluded_iface: Optional[str] = None):
            adj: Dict[str, Set[str]] = {n["id"]: set() for n in topo["nodes"]}
            for link in links:
                s = link["source"]
                t = link["target"]
                if excluded_node_id and (s == excluded_node_id or t == excluded_node_id):
                    continue
                if excluded_iface:
                    local_p = str(link.get("local_interface_id") or link.get("local_port") or "")
                    remote_p = str(link.get("remote_interface_id") or link.get("remote_port") or "")
                    if (s == tid and local_p == excluded_iface) or (t == tid and remote_p == excluded_iface):
                        continue
                if s in adj and t in adj:
                    adj[s].add(t)
                    adj[t].add(s)
            return adj

        def get_reachable_from_gateways(adj_map: Dict[str, Set[str]], gws: List[str]) -> Set[str]:
            reachable = set()
            for gw in gws:
                if gw not in adj_map:
                    continue
                q = [gw]
                visited = {gw}
                while q:
                    cur = q.pop(0)
                    reachable.add(cur)
                    for nxt in adj_map.get(cur, []):
                        if nxt not in visited:
                            visited.add(nxt)
                            q.append(nxt)
            return reachable

        baseline_adj = build_adj()
        baseline_reachable = get_reachable_from_gateways(baseline_adj, gateways)

        sim_adj = build_adj(
            excluded_node_id=tid if change_type in ("node_offline", "node_maintenance") else None,
            excluded_iface=affected_interface if change_type == "interface_down" else None,
        )
        sim_gateways = [g for g in gateways if g != tid]
        sim_reachable = get_reachable_from_gateways(sim_adj, sim_gateways)

        isolated_ids = [
            nid for nid in baseline_reachable
            if nid != tid and nid not in sim_reachable
        ]
        isolated_nodes = [nodes_by_id[nid] for nid in isolated_ids if nid in nodes_by_id]

        is_core_gateway = tid in gateways
        if is_core_gateway or len(isolated_nodes) >= 3:
            severity = "CRITICAL"
        elif len(isolated_nodes) > 0:
            severity = "HIGH"
        elif any(tid == link["source"] or tid == link["target"] for link in links):
            severity = "MEDIUM"
        else:
            severity = "LOW"

        if is_core_gateway:
            mitigation = "Perangkat adalah Core Gateway utama. Rencanakan maintenance window dengan failover VRRP/OSPF aktif sebelum eksekusi."
        elif isolated_nodes:
            mitigation = f"Perubahan akan mengisolasi {len(isolated_nodes)} perangkat: {', '.join(n['name'] for n in isolated_nodes[:4])}. Siapkan redundant uplink atau jalur alternatif."
        else:
            mitigation = "Tidak ada perangkat downstream yang terisolasi. Operasi relatif aman."

        return {
            "success": True,
            "target_node_id": tid,
            "target_name": target_node.get("name"),
            "change_type": change_type,
            "affected_interface": affected_interface,
            "severity": severity,
            "is_core_gateway": is_core_gateway,
            "isolated_nodes_count": len(isolated_nodes),
            "isolated_nodes": [
                {
                    "id": n["id"],
                    "name": n.get("name"),
                    "ip": n.get("ip"),
                    "device_type": n.get("device_type"),
                    "status": n.get("status"),
                }
                for n in isolated_nodes
            ],
            "downstream_impact": f"{len(isolated_nodes)} perangkat downstream terisolasi dari core gateway.",
            "recommended_mitigation": mitigation,
            "simulation_assumptions": [
                "Simulasi pohon graf statis mengasumsikan topologi yang terdaftar sudah lengkap.",
                "Protokol routing dinamis (OSPF/BGP) atau STP failover dapat mengalihkan trafik secara otomatis jika ada jalur redundan yang belum terpetakan.",
            ],
            "disclaimer": "Hasil analisis adalah estimasi simulasi graf topologi, bukan jaminan mutlak perilaku runtime paket pada jaringan fisik.",
        }

    # ------------------------------------------------------------------
    # Sanitized Context Injection for LLM
    # ------------------------------------------------------------------

    def get_llm_topology_context(self) -> str:
        topo = self.get_topology(view_mode="internal_and_edge")
        nodes = topo["nodes"]
        stats = topo["stats"]

        if not nodes:
            return (
                "[TOPOLOGI JARINGAN]: Belum ada perangkat terpetakan di graf topologi. "
                "Gunakan Auto-Discover dari seed router terdaftar di tab Devices."
            )

        own_stats = stats.get("ownership", {})
        lv_stats = stats.get("link_verification", {})

        lines = [
            "[TOPOLOGI JARINGAN AIRA - EVIDENCE-BASED FABRIC V2]",
            (
                f"Perangkat Terlihat: {stats['total_nodes']} "
                f"(Owned={own_stats.get('owned', 0)}, External/ISP={own_stats.get('third_party', 0)}, Unknown={own_stats.get('unknown', 0)}) | "
                f"Links: {stats['total_links']} "
                f"(Confirmed={lv_stats.get('confirmed', 0)}, Observed={lv_stats.get('observed', 0)}, Inferred={lv_stats.get('inferred', 0)})"
            ),
        ]

        unreachable_internal = [
            f"{sanitize_untrusted_text(n['name'], 40)} ({n['ip'] or 'no-ip'})"
            for n in nodes
            if n.get("reachability_status") == "unreachable" and n.get("ownership_status") == "owned"
        ]
        if unreachable_internal:
            lines.append(f"🚨 INTERNAL UNREACHABLE ({len(unreachable_internal)}): " + ", ".join(unreachable_internal[:5]))

        main_devices = [
            (
                f"- {sanitize_untrusted_text(n['name'], 40)} [{n['device_type'].upper()}] "
                f"Scope={n.get('topology_scope')} Ownership={n.get('ownership_status')} "
                f"Reachability={n.get('reachability_status')} Freshness={n.get('observation_freshness')} IP={n['ip']}"
            )
            for n in nodes
            if n["device_type"] in ("router", "switch", "server", "wan")
        ][:10]

        if main_devices:
            lines.append("Ringkasan Node Utama:")
            lines.extend(main_devices)

        lines.append(
            "PENTING: Bedakan perangkat 'owned' internal dari 'isp_upstream'/'unknown', serta bedakan "
            "kabel fisik 'confirmed'/'observed' dari relasi logis 'inferred'/'routed'."
        )
        return "\n".join(lines)


# Singleton accessor
_engine_instance: Optional[TopologyEngine] = None
_engine_lock = threading.Lock()


def get_topology_engine() -> TopologyEngine:
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = TopologyEngine()
    return _engine_instance
