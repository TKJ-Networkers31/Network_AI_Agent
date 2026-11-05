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

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.events import Event, EventBus, EventNames, event_bus
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
    ConfidenceTier,
    EdgeEvidence,
    EdgeLifecycleState,
    GraphDiffReport,
    RelationshipClass,
    TopologyChange,
    TopologyChangeType,
    TopologyEdge,
    TopologySnapshot,
    compute_edge_canonical_key,
    normalize_confidence_tier,
    normalize_edge_lifecycle_state,
    normalize_interface_name,
    normalize_relationship_class,
    normalize_topology_change_type,
    calculate_edge_confidence,
    EVIDENCE_HALF_LIVES,
    DEFAULT_HALF_LIFE,
)
from core.topology_parsers import parse_mikrotik_arp, parse_mikrotik_neighbors
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    get_topology_connection,
    init_topology_database,
    get_write_coordinator,
    execute_with_retry,
    topology_transaction,
)

logger = logging.getLogger("aira.topology")

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DEFAULT_TOPOLOGY_DB_PATH

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

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = (Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self._coordinator = get_write_coordinator(self.db_path)
        self._lock = self._coordinator._lock
        self._discovery_lock = threading.Lock()
        self._active_job_id: Optional[str] = None
        # Phase 4.3 Stale Decayer & NMS synchronization attributes
        self._stale_threshold_sec: float = 60.0
        self._decayer_interval_sec: float = 60.0
        self._decayer_stop_event = asyncio.Event()
        self._decayer_task: Optional[asyncio.Task] = None
        self._decayer_lock = threading.Lock()
        self._subscriber_token: Optional[str] = None
        self._dev_subscriber_token: Optional[str] = None
        self._obs_subscriber_token: Optional[str] = None
        self._subscriber_lock = threading.Lock()
        self._target_bus: Optional[EventBus] = None
        init_topology_database(self.db_path)
        self._init_db()

    def _get_connection(self, read_only: bool = False) -> sqlite3.Connection:
        return get_topology_connection(self.db_path, read_only=read_only, timeout=30.0)

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

            # ------------------------------------------------------------------
            # Phase 4.1: Normalized Graph Data Model & SQLite Foundation
            # ------------------------------------------------------------------
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS topology_edges (
                    id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    source_interface TEXT DEFAULT '',
                    target_interface TEXT DEFAULT '',
                    relationship_class TEXT DEFAULT 'physical',
                    relationship_subtype TEXT DEFAULT 'direct_copper',
                    direction TEXT DEFAULT 'bidirectional',
                    oper_status TEXT DEFAULT 'up',
                    admin_status TEXT DEFAULT 'enabled',
                    verification_status TEXT DEFAULT 'unknown',
                    confidence_tier TEXT DEFAULT 'MEDIUM',
                    confidence_score REAL DEFAULT 0.5,
                    confidence_rationale TEXT DEFAULT '',
                    bandwidth_bps INTEGER DEFAULT 1000000000,
                    vlan_id INTEGER,
                    is_lag_member INTEGER DEFAULT 0,
                    lag_parent_edge_id TEXT,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    last_verified REAL,
                    observation_freshness TEXT DEFAULT 'fresh',
                    lifecycle_state TEXT DEFAULT 'active',
                    provenance TEXT DEFAULT 'discovery_managed',
                    user_overrides_json TEXT DEFAULT '{}',
                    metadata_json TEXT DEFAULT '{}',
                    FOREIGN KEY (source_node_id) REFERENCES topology_nodes (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_node_id) REFERENCES topology_nodes (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS topology_edge_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    edge_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    protocol TEXT DEFAULT '',
                    observing_device_id TEXT NOT NULL,
                    local_interface TEXT DEFAULT '',
                    remote_interface TEXT DEFAULT '',
                    remote_chassis_mac TEXT DEFAULT '',
                    raw_excerpt TEXT DEFAULT '',
                    confidence_contribution TEXT DEFAULT 'medium',
                    explanation TEXT DEFAULT '',
                    observed_at REAL NOT NULL,
                    expires_at REAL,
                    is_active INTEGER DEFAULT 1,
                    metadata_json TEXT DEFAULT '{}',
                    FOREIGN KEY (edge_id) REFERENCES topology_edges (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS topology_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    schema_version TEXT DEFAULT '4.1',
                    discovery_run_id TEXT,
                    created_at REAL NOT NULL,
                    node_count INTEGER DEFAULT 0,
                    edge_count INTEGER DEFAULT 0,
                    graph_json TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    trigger_type TEXT DEFAULT 'discovery_run',
                    description TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_update
                BEFORE UPDATE ON topology_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'Topology snapshots are mathematically immutable and cannot be updated.');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_delete
                BEFORE DELETE ON topology_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'Topology snapshots are mathematically immutable and cannot be deleted.');
                END;

                CREATE TABLE IF NOT EXISTS topology_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT,
                    change_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    change_reason TEXT DEFAULT '',
                    attribute_name TEXT DEFAULT '',
                    before_value_json TEXT DEFAULT '',
                    after_value_json TEXT DEFAULT '',
                    detected_at REAL NOT NULL,
                    FOREIGN KEY (snapshot_id) REFERENCES topology_snapshots (snapshot_id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS topology_schema_version (
                    version TEXT PRIMARY KEY,
                    applied_at REAL NOT NULL,
                    description TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_edges_nodes ON topology_edges(source_node_id, target_node_id);
                CREATE INDEX IF NOT EXISTS idx_edges_rel ON topology_edges(relationship_class, relationship_subtype);
                CREATE INDEX IF NOT EXISTS idx_edges_lifecycle ON topology_edges(lifecycle_state);
                CREATE INDEX IF NOT EXISTS idx_edges_freshness ON topology_edges(observation_freshness);
                CREATE INDEX IF NOT EXISTS idx_edge_ev_edge ON topology_edge_evidence(edge_id);
                CREATE INDEX IF NOT EXISTS idx_edge_ev_device ON topology_edge_evidence(observing_device_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_created ON topology_snapshots(created_at);
                CREATE INDEX IF NOT EXISTS idx_changes_snap ON topology_changes(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_changes_entity ON topology_changes(entity_id);
                CREATE INDEX IF NOT EXISTS idx_changes_type ON topology_changes(change_type);
                """
            )

            conn.execute(
                "INSERT OR IGNORE INTO topology_schema_version (version, applied_at, description) VALUES (?, ?, ?)",
                ("4.1", time.time(), "Networking IV Phase 4.1 Normalized Graph Data Model & SQLite Foundation"),
            )

            conn.commit()

    # ------------------------------------------------------------------
    # Phase 4.1 Repository & Data-Access Layer
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self, write: bool = True):
        """Provides an atomic transaction block for TopologyEngine operations."""
        with topology_transaction(self.db_path, write=write) as conn:
            yield conn

    def get_schema_version(self, conn: Optional[sqlite3.Connection] = None) -> str:
        """Returns the latest applied topology schema version."""
        def _execute(c: sqlite3.Connection) -> str:
            row = c.execute("SELECT version FROM topology_schema_version ORDER BY applied_at DESC LIMIT 1").fetchone()
            return str(row["version"]) if row else "1.0"

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            return _execute(auto_conn)

    def insert_edge(self, edge: TopologyEdge, conn: Optional[sqlite3.Connection] = None) -> str:
        """Inserts a new TopologyEdge. Validates edge constraints and node existence."""
        if not isinstance(edge, TopologyEdge):
            raise TypeError("edge must be an instance of TopologyEdge.")

        def _execute(c: sqlite3.Connection) -> str:
            s_node = c.execute("SELECT id FROM topology_nodes WHERE id = ?", (edge.source_node_id,)).fetchone()
            if not s_node:
                raise ValueError(f"source_node_id '{edge.source_node_id}' does not exist in topology_nodes.")
            t_node = c.execute("SELECT id FROM topology_nodes WHERE id = ?", (edge.target_node_id,)).fetchone()
            if not t_node:
                raise ValueError(f"target_node_id '{edge.target_node_id}' does not exist in topology_nodes.")

            c.execute(
                """
                INSERT INTO topology_edges (
                    id, source_node_id, target_node_id, source_interface, target_interface,
                    relationship_class, relationship_subtype, direction, oper_status, admin_status,
                    verification_status, confidence_tier, confidence_score, confidence_rationale,
                    bandwidth_bps, vlan_id, is_lag_member, lag_parent_edge_id,
                    first_seen, last_seen, last_verified, observation_freshness,
                    lifecycle_state, provenance, user_overrides_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.source_interface,
                    edge.target_interface,
                    edge.relationship_class,
                    edge.relationship_subtype,
                    edge.direction,
                    edge.oper_status,
                    edge.admin_status,
                    edge.verification_status,
                    edge.confidence_tier,
                    edge.confidence_score,
                    edge.confidence_rationale,
                    edge.bandwidth_bps,
                    edge.vlan_id,
                    1 if edge.is_lag_member else 0,
                    edge.lag_parent_edge_id,
                    edge.first_seen,
                    edge.last_seen,
                    edge.last_verified,
                    edge.observation_freshness,
                    edge.lifecycle_state,
                    edge.provenance,
                    json.dumps(edge.user_overrides or {}),
                    json.dumps(edge.metadata or {}),
                ),
            )
            return edge.id

        if conn is not None:
            return _execute(conn)

        def _do_write() -> str:
            with self._lock, closing(self._get_connection()) as auto_conn:
                res = _execute(auto_conn)
                auto_conn.commit()
                return res

        return execute_with_retry(_do_write, operation_name="insert_edge")

    def get_edge(self, edge_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[TopologyEdge]:
        """Retrieves a single TopologyEdge by ID."""
        def _execute(c: sqlite3.Connection) -> Optional[TopologyEdge]:
            row = c.execute("SELECT * FROM topology_edges WHERE id = ?", (edge_id,)).fetchone()
            if not row:
                return None
            return TopologyEdge.from_dict(dict(row))

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def list_edges(
        self,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        relationship_class: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        include_tombstoned: bool = False,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[TopologyEdge]:
        """Lists topology edges with optional filtering. Hides tombstoned edges unless specified."""
        query = "SELECT * FROM topology_edges WHERE 1=1"
        params: List[Any] = []

        if source_node_id:
            query += " AND source_node_id = ?"
            params.append(source_node_id)
        if target_node_id:
            query += " AND target_node_id = ?"
            params.append(target_node_id)
        if relationship_class:
            norm_rc = normalize_relationship_class(relationship_class)
            query += " AND relationship_class = ?"
            params.append(norm_rc)
        if lifecycle_state:
            norm_ls = normalize_edge_lifecycle_state(lifecycle_state)
            query += " AND lifecycle_state = ?"
            params.append(norm_ls)
        elif not include_tombstoned:
            query += " AND lifecycle_state != 'tombstoned'"

        query += " ORDER BY first_seen ASC"

        def _execute(c: sqlite3.Connection) -> List[TopologyEdge]:
            rows = c.execute(query, params).fetchall()
            return [TopologyEdge.from_dict(dict(r)) for r in rows]

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def find_existing_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        relationship_class: str,
        source_interface: str = "",
        target_interface: str = "",
        relationship_subtype: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[TopologyEdge]:
        """Locates an edge matching endpoint, interface, and semantic class."""
        norm_rc = normalize_relationship_class(relationship_class)
        query = (
            "SELECT * FROM topology_edges "
            "WHERE source_node_id = ? AND target_node_id = ? "
            "  AND relationship_class = ? AND source_interface = ? AND target_interface = ?"
        )
        params: List[Any] = [source_node_id, target_node_id, norm_rc, source_interface, target_interface]
        if relationship_subtype is not None:
            query += " AND relationship_subtype = ?"
            params.append(relationship_subtype)

        def _execute(c: sqlite3.Connection) -> Optional[TopologyEdge]:
            row = c.execute(query, params).fetchone()
            if not row:
                return None
            return TopologyEdge.from_dict(dict(row))

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            return _execute(auto_conn)

    def update_edge(
        self,
        edge_id: str,
        updates: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[TopologyEdge]:
        """Updates attributes of an existing edge. Validates field constraints."""
        if not updates:
            return self.get_edge(edge_id, conn=conn)

        def _execute(c: sqlite3.Connection) -> Optional[TopologyEdge]:
            existing = c.execute("SELECT * FROM topology_edges WHERE id = ?", (edge_id,)).fetchone()
            if not existing:
                return None
            edge_data = dict(existing)
            edge_data["user_overrides"] = json.loads(edge_data.pop("user_overrides_json") or "{}")
            edge_data["metadata"] = json.loads(edge_data.pop("metadata_json") or "{}")
            edge_data["is_lag_member"] = bool(edge_data.get("is_lag_member", 0))

            for k, v in updates.items():
                if k in ("user_overrides_json", "metadata_json"):
                    continue
                if k == "relationship_class":
                    v = normalize_relationship_class(v)
                elif k == "lifecycle_state":
                    v = normalize_edge_lifecycle_state(v)
                elif k == "confidence_tier":
                    v = normalize_confidence_tier(v)
                elif k == "confidence_score":
                    v = float(v)
                    if not (0.0 <= v <= 1.0):
                        raise ValueError(f"confidence_score must be between 0.0 and 1.0, got {v}")
                elif k == "confidence_rationale":
                    if not v or not str(v).strip():
                        raise ValueError("confidence_rationale must be provided and non-empty.")
                edge_data[k] = v

            updated_edge = TopologyEdge.from_dict(edge_data)

            c.execute(
                """
                UPDATE topology_edges
                SET source_interface = ?, target_interface = ?, relationship_class = ?,
                    relationship_subtype = ?, direction = ?, oper_status = ?, admin_status = ?,
                    verification_status = ?, confidence_tier = ?, confidence_score = ?,
                    confidence_rationale = ?, bandwidth_bps = ?, vlan_id = ?, is_lag_member = ?,
                    lag_parent_edge_id = ?, first_seen = ?, last_seen = ?, last_verified = ?,
                    observation_freshness = ?, lifecycle_state = ?, provenance = ?,
                    user_overrides_json = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    updated_edge.source_interface,
                    updated_edge.target_interface,
                    updated_edge.relationship_class,
                    updated_edge.relationship_subtype,
                    updated_edge.direction,
                    updated_edge.oper_status,
                    updated_edge.admin_status,
                    updated_edge.verification_status,
                    updated_edge.confidence_tier,
                    updated_edge.confidence_score,
                    updated_edge.confidence_rationale,
                    updated_edge.bandwidth_bps,
                    updated_edge.vlan_id,
                    1 if updated_edge.is_lag_member else 0,
                    updated_edge.lag_parent_edge_id,
                    updated_edge.first_seen,
                    updated_edge.last_seen,
                    updated_edge.last_verified,
                    updated_edge.observation_freshness,
                    updated_edge.lifecycle_state,
                    updated_edge.provenance,
                    json.dumps(updated_edge.user_overrides or {}),
                    json.dumps(updated_edge.metadata or {}),
                    edge_id,
                ),
            )
            return updated_edge

        if conn is not None:
            return _execute(conn)

        def _do_decay() -> int:
            with self._lock, closing(self._get_connection()) as auto_conn:
                res = _execute(auto_conn)
                auto_conn.commit()
                return res

        return execute_with_retry(_do_decay, operation_name="decay_stale_observations")

    def delete_edge(
        self,
        edge_id: str,
        soft_delete: bool = True,
        actor: str = "admin",
        reason: str = "Administrative deletion",
        conn: Optional[sqlite3.Connection] = None,
    ) -> bool:
        """
        Deletes an edge. If soft_delete is True (default), marks as 'tombstoned'
        and preserves empirical evidence for audit/historical continuity.
        If soft_delete is False, hard deletes edge and cascades to edge evidence.
        Records an auditable TopologyChange (EDGE_REMOVED) and audit log record.
        """
        def _execute(c: sqlite3.Connection) -> bool:
            row = c.execute("SELECT * FROM topology_edges WHERE id = ?", (edge_id,)).fetchone()
            if not row:
                return False
            if soft_delete and row["lifecycle_state"] == "tombstoned":
                return False  # Already tombstoned/deleted

            now_ts = time.time()
            if soft_delete:
                cur = c.execute(
                    "UPDATE topology_edges SET lifecycle_state = 'tombstoned', last_seen = ? WHERE id = ?",
                    (now_ts, edge_id),
                )
            else:
                c.execute("DELETE FROM topology_edge_evidence WHERE edge_id = ?", (edge_id,))
                cur = c.execute("DELETE FROM topology_edges WHERE id = ?", (edge_id,))

            if cur.rowcount > 0:
                table_names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "topology_changes" in table_names:
                    self.record_change(
                        TopologyChange(
                            change_type=TopologyChangeType.EDGE_REMOVED.value,
                            entity_id=edge_id,
                            change_reason=reason,
                            detected_at=now_ts,
                        ),
                        conn=c,
                    )
                if "topology_audit_log" in table_names:
                    c.execute(
                        "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, created_at) "
                        "VALUES (?, 'delete_edge', 'edge', ?, ?, ?)",
                        (actor, edge_id, reason, now_ts),
                    )
                return True
            return False

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

    def insert_edge_evidence(
        self,
        evidence: EdgeEvidence,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Inserts a new EdgeEvidence row. Enforces foreign key constraint to topology_edges."""
        if not isinstance(evidence, EdgeEvidence):
            raise TypeError("evidence must be an instance of EdgeEvidence.")

        def _execute(c: sqlite3.Connection) -> int:
            edge = c.execute("SELECT id FROM topology_edges WHERE id = ?", (evidence.edge_id,)).fetchone()
            if not edge:
                raise ValueError(f"edge_id '{evidence.edge_id}' does not exist in topology_edges.")

            cur = c.execute(
                """
                INSERT INTO topology_edge_evidence (
                    edge_id, evidence_type, protocol, observing_device_id,
                    local_interface, remote_interface, remote_chassis_mac,
                    raw_excerpt, confidence_contribution, explanation,
                    observed_at, expires_at, is_active, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.edge_id,
                    evidence.evidence_type,
                    evidence.protocol,
                    evidence.observing_device_id,
                    evidence.local_interface,
                    evidence.remote_interface,
                    evidence.remote_chassis_mac,
                    evidence.raw_excerpt,
                    evidence.confidence_contribution,
                    evidence.explanation,
                    evidence.observed_at,
                    evidence.expires_at,
                    1 if evidence.is_active else 0,
                    json.dumps(evidence.metadata or {}),
                ),
            )
            return int(cur.lastrowid)

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

    def get_edge_evidence(
        self,
        edge_id: str,
        active_only: bool = True,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[EdgeEvidence]:
        """Retrieves all evidence associated with an edge, ordered newest first."""
        query = "SELECT * FROM topology_edge_evidence WHERE edge_id = ?"
        params: List[Any] = [edge_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY observed_at DESC"

        def _execute(c: sqlite3.Connection) -> List[EdgeEvidence]:
            rows = c.execute(query, params).fetchall()
            return [EdgeEvidence.from_dict(dict(r)) for r in rows]

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            return _execute(auto_conn)

    def deactivate_expired_evidence(
        self,
        now: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Marks evidence rows as is_active = 0 when expires_at <= now."""
        current_time = now if now is not None else time.time()

        def _execute(c: sqlite3.Connection) -> int:
            cur = c.execute(
                "UPDATE topology_edge_evidence SET is_active = 0 WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at <= ?",
                (current_time,),
            )
            return cur.rowcount

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

    def create_snapshot(
        self,
        trigger_type: str = "manual",
        description: str = "",
        discovery_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        completeness: Optional[Dict[str, Any]] = None,
        schema_version: str = "4.4",
        conn: Optional[sqlite3.Connection] = None,
    ) -> TopologySnapshot:
        """
        Phase 4.4A Complete Immutable Topology Snapshot Model.
        Creates an immutable, SHA-256 hashed point-in-time snapshot of the topology graph.
        Pulls current nodes, active edges, and edge evidence in a single consistent read transaction,
        embeds sanitized discovery completeness metadata, and records in database.
        Concurrency-hardened: Read phase operates without holding the single-writer lock;
        graph serialization and hashing occurs in memory; insert commits in a fast atomic transaction.
        """
        ts = time.time()
        snap_id = f"snap_{int(ts * 1000)}_{uuid.uuid4().hex[:8]}"

        MAX_SNAPSHOT_NODES = 10000
        MAX_SNAPSHOT_EDGES = 50000

        def _read_graph_state(c: sqlite3.Connection):
            # 1. Nodes (sorted by id)
            node_rows = c.execute("SELECT * FROM topology_nodes ORDER BY id ASC").fetchall()
            nodes_list = [dict(r) for r in node_rows]
            if len(nodes_list) > MAX_SNAPSHOT_NODES:
                raise ValueError(
                    f"Snapshot exceeds maximum allowable node limit ({MAX_SNAPSHOT_NODES}): got {len(nodes_list)}"
                )
            for n in nodes_list:
                if "metadata_json" in n:
                    raw_m = n.pop("metadata_json")
                    n["metadata"] = json.loads(raw_m) if isinstance(raw_m, str) and raw_m else {}
                if "user_overrides_json" in n:
                    raw_u = n.pop("user_overrides_json")
                    n["user_overrides"] = json.loads(raw_u) if isinstance(raw_u, str) and raw_u else {}

            # 2. Edges (sorted by id, non-tombstoned)
            edge_rows = c.execute(
                "SELECT * FROM topology_edges WHERE lifecycle_state != 'tombstoned' ORDER BY id ASC"
            ).fetchall()
            edges_list = [dict(r) for r in edge_rows]
            if len(edges_list) > MAX_SNAPSHOT_EDGES:
                raise ValueError(
                    f"Snapshot exceeds maximum allowable edge limit ({MAX_SNAPSHOT_EDGES}): got {len(edges_list)}"
                )
            for e in edges_list:
                if "metadata_json" in e:
                    raw_m = e.pop("metadata_json")
                    e["metadata"] = json.loads(raw_m) if isinstance(raw_m, str) and raw_m else {}
                if "user_overrides_json" in e:
                    raw_u = e.pop("user_overrides_json")
                    e["user_overrides"] = json.loads(raw_u) if isinstance(raw_u, str) and raw_u else {}
                e["is_lag_member"] = bool(e.get("is_lag_member", 0))

            # 3. Evidence (sorted by edge_id, id)
            edge_ids = [e["id"] for e in edges_list]
            evidence_list: List[Dict[str, Any]] = []
            if edge_ids:
                placeholders = ",".join("?" for _ in edge_ids)
                ev_rows = c.execute(
                    f"SELECT * FROM topology_edge_evidence WHERE edge_id IN ({placeholders}) ORDER BY edge_id ASC, id ASC",
                    edge_ids,
                ).fetchall()
                for row in ev_rows:
                    ev = dict(row)
                    clean_excerpt = sanitize_cli_excerpt(sanitize_untrusted_text(ev.get("raw_excerpt") or ""))
                    clean_explanation = sanitize_untrusted_text(ev.get("explanation") or "")
                    ev_meta = json.loads(ev.get("metadata_json") or "{}") if isinstance(ev.get("metadata_json"), str) else (ev.get("metadata") or {})
                    clean_item = {
                        "id": ev.get("id"),
                        "edge_id": ev.get("edge_id"),
                        "evidence_type": ev.get("evidence_type", ""),
                        "protocol": ev.get("protocol", ""),
                        "observing_device_id": ev.get("observing_device_id", ""),
                        "source_device": ev.get("observing_device_id", ""),
                        "local_interface": ev.get("local_interface", ""),
                        "remote_interface": ev.get("remote_interface", ""),
                        "remote_chassis_mac": ev.get("remote_chassis_mac", ""),
                        "raw_excerpt": clean_excerpt,
                        "confidence_contribution": ev.get("confidence_contribution", "medium"),
                        "confidence_score": ev.get("confidence_contribution", "medium"),
                        "explanation": clean_explanation,
                        "observed_at": ev.get("observed_at"),
                        "discovered_at": ev.get("observed_at"),
                        "expires_at": ev.get("expires_at"),
                        "is_active": bool(ev.get("is_active", 1)),
                        "metadata": ev_meta,
                    }
                    evidence_list.append(clean_item)

            ev_by_edge: Dict[str, List[Dict[str, Any]]] = {}
            for ev in evidence_list:
                ev_by_edge.setdefault(ev["edge_id"], []).append(ev)
            for e in edges_list:
                e["evidence"] = ev_by_edge.get(e["id"], [])

            return nodes_list, edges_list, evidence_list

        # Execute read phase
        if conn is not None:
            nodes_list, edges_list, evidence_list = _read_graph_state(conn)
        else:
            with closing(self._get_connection(read_only=True)) as read_conn:
                nodes_list, edges_list, evidence_list = _read_graph_state(read_conn)

        # 4. Completeness metadata (Pure CPU in memory)
        snapshot_metadata = dict(metadata or {})
        comp_raw = completeness if completeness is not None else snapshot_metadata.get("completeness", {})
        node_ids = [n["id"] for n in nodes_list]

        if "is_complete" in comp_raw:
            is_comp = bool(comp_raw["is_complete"])
        else:
            disc_status = comp_raw.get("discovery_status", "unknown")
            if disc_status == "complete":
                is_comp = True
            elif disc_status in ("failed", "partial"):
                is_comp = False
            else:
                is_comp = True if (not comp_raw.get("failed_devices") and not comp_raw.get("timed_out_devices") and len(nodes_list) > 0) else False

        completeness_dict = {
            "discovery_status": str(comp_raw.get("discovery_status", "unknown")),
            "expected_devices": list(comp_raw.get("expected_devices", [])),
            "successful_devices": list(comp_raw.get("successful_devices", node_ids)),
            "failed_devices": list(comp_raw.get("failed_devices", [])),
            "timed_out_devices": list(comp_raw.get("timed_out_devices", [])),
            "collection_scope": comp_raw.get("collection_scope", ""),
            "started_at": float(comp_raw.get("started_at", ts)),
            "completed_at": float(comp_raw.get("completed_at", ts)),
            "is_complete": is_comp,
        }
        snapshot_metadata["completeness"] = completeness_dict

        # 5. Canonical JSON & SHA-256 Checksum (Pure CPU in memory)
        graph_state = {
            "snapshot_id": snap_id,
            "created_at": ts,
            "schema_version": schema_version,
            "nodes": nodes_list,
            "edges": edges_list,
            "evidence": evidence_list,
            "completeness": completeness_dict,
            "metadata": snapshot_metadata,
        }
        graph_json = json.dumps(graph_state, sort_keys=True, separators=(',', ':'))
        sha256_hash = hashlib.sha256(graph_json.encode("utf-8")).hexdigest()

        snapshot = TopologySnapshot(
            snapshot_id=snap_id,
            schema_version=schema_version,
            discovery_run_id=discovery_run_id,
            created_at=ts,
            node_count=len(nodes_list),
            edge_count=len(edges_list),
            graph_json=graph_json,
            sha256_hash=sha256_hash,
            trigger_type=trigger_type,
            description=description,
            metadata=snapshot_metadata,
        )

        def _insert(c: sqlite3.Connection) -> None:
            c.execute(
                """
                INSERT INTO topology_snapshots (
                    snapshot_id, schema_version, discovery_run_id, created_at,
                    node_count, edge_count, graph_json, sha256_hash,
                    trigger_type, description, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.schema_version,
                    snapshot.discovery_run_id,
                    snapshot.created_at,
                    snapshot.node_count,
                    snapshot.edge_count,
                    snapshot.graph_json,
                    snapshot.sha256_hash,
                    snapshot.trigger_type,
                    snapshot.description,
                    json.dumps(snapshot.metadata or {}),
                ),
            )

        if conn is not None:
            _insert(conn)
            return snapshot

        def _do_write() -> None:
            with self._lock, closing(self._get_connection()) as auto_conn:
                _insert(auto_conn)
                auto_conn.commit()

        execute_with_retry(_do_write, operation_name="create_snapshot")
        return snapshot

    def get_snapshot(
        self,
        snapshot_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[TopologySnapshot]:
        """Retrieves an immutable TopologySnapshot by ID."""
        def _execute(c: sqlite3.Connection) -> Optional[TopologySnapshot]:
            row = c.execute("SELECT * FROM topology_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
            if not row:
                return None
            return TopologySnapshot.from_dict(dict(row))

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def list_snapshots(
        self,
        limit: int = 50,
        offset: int = 0,
        trigger_type: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[TopologySnapshot]:
        """Lists snapshots ordered newest first with optional pagination and trigger filter."""
        query = "SELECT * FROM topology_snapshots WHERE 1=1"
        params: List[Any] = []
        if trigger_type:
            query += " AND trigger_type = ?"
            params.append(trigger_type)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        def _execute(c: sqlite3.Connection) -> List[TopologySnapshot]:
            rows = c.execute(query, params).fetchall()
            return [TopologySnapshot.from_dict(dict(r)) for r in rows]

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def count_snapshots(
        self,
        trigger_type: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Returns total snapshot count matching criteria."""
        query = "SELECT count(*) FROM topology_snapshots WHERE 1=1"
        params: List[Any] = []
        if trigger_type:
            query += " AND trigger_type = ?"
            params.append(trigger_type)

        def _execute(c: sqlite3.Connection) -> int:
            return int(c.execute(query, params).fetchone()[0])

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def compare_snapshots(
        self,
        base_id: Any,
        target_id: Any,
    ) -> GraphDiffReport:
        """
        Phase 4.4A Semantic Snapshot Comparison Engine.
        Executes read-only comparison between two point-in-time snapshots with:
        - DB query isolation inside lock (<5ms)
        - Memory deserialization and CPU comparison outside DB lock
        - Canonical multi-edge identity resolution preserving (T_A, T_B)
        - Ambiguity detection (INDETERMINATE_AMBIGUOUS_MATCH)
        - Epistemically safe node/edge removal checks
        - Operational status, freshness, and evidence change classification
        """
        if hasattr(base_id, "snapshot_id"):
            base_id = base_id.snapshot_id
        if hasattr(target_id, "snapshot_id"):
            target_id = target_id.snapshot_id

        base_id_str = str(base_id or "").strip()
        target_id_str = str(target_id or "").strip()
        if not base_id_str:
            raise ValueError("base_id cannot be empty.")
        if not target_id_str:
            raise ValueError("target_id cannot be empty.")

        t0 = time.perf_counter()

        # Database read boundary outside writer lock (WAL read-only):
        with closing(self._get_connection(read_only=True)) as conn:
            row_base = conn.execute(
                "SELECT snapshot_id, schema_version, graph_json, metadata_json, created_at FROM topology_snapshots WHERE snapshot_id = ?",
                (base_id_str,),
            ).fetchone()
            row_target = conn.execute(
                "SELECT snapshot_id, schema_version, graph_json, metadata_json, created_at FROM topology_snapshots WHERE snapshot_id = ?",
                (target_id_str,),
            ).fetchone()
        t1 = time.perf_counter()
        db_query_ms = round((t1 - t0) * 1000.0, 3)

        if not row_base:
            raise ValueError(f"Base snapshot '{base_id_str}' not found.")
        if not row_target:
            raise ValueError(f"Target snapshot '{target_id_str}' not found.")

        # Deserialization phase outside DB lock:
        t2 = time.perf_counter()
        base_graph = json.loads(row_base["graph_json"])
        target_graph = json.loads(row_target["graph_json"])
        base_meta = json.loads(row_base["metadata_json"] or "{}") if isinstance(row_base["metadata_json"], str) else (row_base["metadata_json"] or {})
        target_meta = json.loads(row_target["metadata_json"] or "{}") if isinstance(row_target["metadata_json"], str) else (row_target["metadata_json"] or {})
        t3 = time.perf_counter()
        deserialization_ms = round((t3 - t2) * 1000.0, 3)

        # Graph size safeguard bounds
        MAX_NODES = 10000
        MAX_EDGES = 50000
        base_nodes: List[Dict[str, Any]] = base_graph.get("nodes", [])
        target_nodes: List[Dict[str, Any]] = target_graph.get("nodes", [])
        base_edges: List[Dict[str, Any]] = base_graph.get("edges", [])
        target_edges: List[Dict[str, Any]] = target_graph.get("edges", [])

        if len(base_nodes) > MAX_NODES or len(target_nodes) > MAX_NODES:
            raise ValueError(f"Snapshot exceeds maximum allowable node limit ({MAX_NODES}).")
        if len(base_edges) > MAX_EDGES or len(target_edges) > MAX_EDGES:
            raise ValueError(f"Snapshot exceeds maximum allowable edge limit ({MAX_EDGES}).")

        # Diff computation phase:
        t4 = time.perf_counter()

        structural_changes: List[Dict[str, Any]] = []
        operational_changes: List[Dict[str, Any]] = []
        evidence_changes: List[Dict[str, Any]] = []
        freshness_changes: List[Dict[str, Any]] = []
        indeterminate_items: List[Dict[str, Any]] = []

        # Target discovery completeness metadata
        target_comp = target_meta.get("completeness") or target_graph.get("completeness") or {}
        target_status = str(target_comp.get("discovery_status", "unknown")).lower()
        if "is_complete" in target_comp:
            target_is_complete = bool(target_comp["is_complete"])
        else:
            if target_status == "complete":
                target_is_complete = True
            elif target_status in ("failed", "partial"):
                target_is_complete = False
            else:
                target_is_complete = True if (not target_comp.get("failed_devices") and not target_comp.get("timed_out_devices") and len(target_nodes) > 0) else False

        successful_devices = set(target_comp.get("successful_devices", [n.get("id") for n in target_nodes]))
        failed_devices = set(target_comp.get("failed_devices", []))
        timed_out_devices = set(target_comp.get("timed_out_devices", []))

        # ---------------------------------------------------------------------
        # 1. NODE COMPARISON
        # ---------------------------------------------------------------------
        base_nodes_map = {n["id"]: n for n in base_nodes if "id" in n}
        target_nodes_map = {n["id"]: n for n in target_nodes if "id" in n}

        # Node Added:
        for nid, tn in target_nodes_map.items():
            if nid not in base_nodes_map:
                structural_changes.append({
                    "change_type": "NODE_ADDED",
                    "entity_type": "node",
                    "entity_id": nid,
                    "change_reason": "Device observed in target snapshot but absent in base",
                    "attribute_name": "",
                    "before_value": None,
                    "after_value": tn,
                })

        # Node Removed (Epistemic safeguard):
        for nid, bn in base_nodes_map.items():
            if nid not in target_nodes_map:
                is_safe_removal = (
                    target_is_complete
                    and target_status in ("complete", "unknown")
                    and (nid not in failed_devices)
                    and (nid not in timed_out_devices)
                )
                if is_safe_removal:
                    structural_changes.append({
                        "change_type": "NODE_REMOVED",
                        "entity_type": "node",
                        "entity_id": nid,
                        "change_reason": "Device present in base snapshot was confirmed absent during complete discovery",
                        "attribute_name": "",
                        "before_value": bn,
                        "after_value": None,
                    })
                else:
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_UNREACHABLE_NODE",
                        "entity_type": "node",
                        "entity_id": nid,
                        "reason": f"Device missing from target snapshot but target discovery was incomplete (status={target_status}, is_complete={target_is_complete}) or device was unreachable",
                        "details": {
                            "node_id": nid,
                            "target_is_complete": target_is_complete,
                            "target_discovery_status": target_status,
                            "failed": nid in failed_devices,
                            "timed_out": nid in timed_out_devices,
                        },
                    })

        # Node Modified:
        node_fields_to_check = [
            "name", "identity", "hostname", "ip", "ip_address",
            "device_type", "device_role", "role", "model", "status",
            "reachability_status", "management_status"
        ]
        for nid in set(base_nodes_map.keys()) & set(target_nodes_map.keys()):
            bn = base_nodes_map[nid]
            tn = target_nodes_map[nid]
            for fld in node_fields_to_check:
                bv = bn.get(fld)
                tv = tn.get(fld)
                if bv is not None and tv is not None and bv != tv:
                    structural_changes.append({
                        "change_type": "NODE_MODIFIED",
                        "entity_type": "node",
                        "entity_id": nid,
                        "attribute_name": fld,
                        "change_reason": f"Node attribute '{fld}' changed from '{bv}' to '{tv}'",
                        "before_value": bv,
                        "after_value": tv,
                    })

        # ---------------------------------------------------------------------
        # 2. MULTI-EDGE IDENTITY RESOLUTION & COMPARISON
        # ---------------------------------------------------------------------
        base_edges_by_id = {e["id"]: e for e in base_edges if "id" in e}
        target_edges_by_id = {e["id"]: e for e in target_edges if "id" in e}

        matched_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        matched_base_ids: Set[str] = set()
        matched_target_ids: Set[str] = set()

        for eid in set(base_edges_by_id.keys()) & set(target_edges_by_id.keys()):
            matched_pairs.append((base_edges_by_id[eid], target_edges_by_id[eid]))
            matched_base_ids.add(eid)
            matched_target_ids.add(eid)

        unmatched_base = [e for e in base_edges if e.get("id") not in matched_base_ids]
        unmatched_target = [e for e in target_edges if e.get("id") not in matched_target_ids]

        base_grouped_by_key: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        for be in unmatched_base:
            k = compute_edge_canonical_key(be)
            base_grouped_by_key.setdefault(k, []).append(be)

        target_grouped_by_key: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        for te in unmatched_target:
            k = compute_edge_canonical_key(te)
            target_grouped_by_key.setdefault(k, []).append(te)

        def _get_pair(e: Dict[str, Any]) -> Tuple[str, str]:
            u = str(e.get("source_node_id") or "")
            v = str(e.get("target_node_id") or "")
            return (u, v) if u <= v else (v, u)

        base_pair_counts: Dict[Tuple[str, str], int] = {}
        for e in base_edges:
            pair = _get_pair(e)
            base_pair_counts[pair] = base_pair_counts.get(pair, 0) + 1

        target_pair_counts: Dict[Tuple[str, str], int] = {}
        for e in target_edges:
            pair = _get_pair(e)
            target_pair_counts[pair] = target_pair_counts.get(pair, 0) + 1

        all_candidate_keys = set(base_grouped_by_key.keys()) | set(target_grouped_by_key.keys())
        ambiguous_base_edges: Set[str] = set()
        ambiguous_target_edges: Set[str] = set()

        for k in all_candidate_keys:
            b_list = base_grouped_by_key.get(k, [])
            t_list = target_grouped_by_key.get(k, [])

            if len(b_list) > 1 or len(t_list) > 1:
                for e in b_list:
                    ambiguous_base_edges.add(e["id"])
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": e["id"],
                        "reason": f"Multiple edges share identical canonical identity tuple {k} (collision count: base={len(b_list)}, target={len(t_list)})",
                        "details": {"key": str(k), "edge": e},
                    })
                for e in t_list:
                    ambiguous_target_edges.add(e["id"])
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": e["id"],
                        "reason": f"Multiple edges share identical canonical identity tuple {k} (collision count: base={len(b_list)}, target={len(t_list)})",
                        "details": {"key": str(k), "edge": e},
                    })
                continue

            if len(b_list) == 1 and len(t_list) == 1:
                be = b_list[0]
                te = t_list[0]
                b_iface_missing = not (be.get("source_interface") and be.get("target_interface"))
                t_iface_missing = not (te.get("source_interface") and te.get("target_interface"))
                b_pair = _get_pair(be)
                t_pair = _get_pair(te)

                has_parallel_base = base_pair_counts.get(b_pair, 0) > 1
                has_parallel_target = target_pair_counts.get(t_pair, 0) > 1

                if (b_iface_missing or t_iface_missing) and (has_parallel_base or has_parallel_target):
                    ambiguous_base_edges.add(be["id"])
                    ambiguous_target_edges.add(te["id"])
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": be["id"],
                        "reason": "Missing interface on link with parallel edges between same endpoint pair",
                        "details": {"key": str(k), "edge": be},
                    })
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": te["id"],
                        "reason": "Missing interface on link with parallel edges between same endpoint pair",
                        "details": {"key": str(k), "edge": te},
                    })
                else:
                    matched_pairs.append((be, te))
                    matched_base_ids.add(be["id"])
                    matched_target_ids.add(te["id"])

        # Check remaining unmatched edges for missing interface on parallel link
        for be in unmatched_base:
            if be["id"] not in matched_base_ids and be["id"] not in ambiguous_base_edges:
                b_pair = _get_pair(be)
                b_iface_missing = not (be.get("source_interface") and be.get("target_interface"))
                if b_iface_missing and base_pair_counts.get(b_pair, 0) > 1:
                    ambiguous_base_edges.add(be["id"])
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": be["id"],
                        "reason": "Missing interface on link with parallel edges between same endpoint pair",
                        "details": {"edge": be},
                    })

        for te in unmatched_target:
            if te["id"] not in matched_target_ids and te["id"] not in ambiguous_target_edges:
                t_pair = _get_pair(te)
                t_iface_missing = not (te.get("source_interface") and te.get("target_interface"))
                if t_iface_missing and target_pair_counts.get(t_pair, 0) > 1:
                    ambiguous_target_edges.add(te["id"])
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_AMBIGUOUS_MATCH",
                        "entity_type": "edge",
                        "entity_id": te["id"],
                        "reason": "Missing interface on link with parallel edges between same endpoint pair",
                        "details": {"edge": te},
                    })

        # Remaining unmatched target edges (not ambiguous) -> EDGE_ADDED
        for te in unmatched_target:
            if te["id"] not in matched_target_ids and te["id"] not in ambiguous_target_edges:
                structural_changes.append({
                    "change_type": "EDGE_ADDED",
                    "entity_type": "edge",
                    "entity_id": te["id"],
                    "change_reason": "Edge observed in target snapshot but absent in base",
                    "attribute_name": "",
                    "before_value": None,
                    "after_value": te,
                })

        # Remaining unmatched base edges (not ambiguous) -> EDGE_REMOVED (Epistemic safeguard)
        for be in unmatched_base:
            if be["id"] not in matched_base_ids and be["id"] not in ambiguous_base_edges:
                u = be.get("source_node_id")
                v = be.get("target_node_id")
                is_safe_edge_removal = (
                    target_is_complete
                    and target_status in ("complete", "unknown")
                    and (u in successful_devices and v in successful_devices)
                    and (u not in failed_devices and u not in timed_out_devices)
                    and (v not in failed_devices and v not in timed_out_devices)
                )
                if is_safe_edge_removal:
                    structural_changes.append({
                        "change_type": "EDGE_REMOVED",
                        "entity_type": "edge",
                        "entity_id": be["id"],
                        "change_reason": "Edge confirmed removed between verified endpoints",
                        "attribute_name": "",
                        "before_value": be,
                        "after_value": None,
                    })
                else:
                    indeterminate_items.append({
                        "indeterminate_type": "INDETERMINATE_UNVERIFIED_EDGE",
                        "entity_type": "edge",
                        "entity_id": be["id"],
                        "reason": f"Edge missing from target snapshot but endpoint verification incomplete (source={u}, target={v}, target_complete={target_is_complete})",
                        "details": {
                            "edge_id": be["id"],
                            "source_node_id": u,
                            "target_node_id": v,
                            "target_is_complete": target_is_complete,
                            "target_discovery_status": target_status,
                            "source_successful": u in successful_devices,
                            "target_successful": v in successful_devices,
                        },
                    })

        # ---------------------------------------------------------------------
        # 3. MATCHED EDGES: OPERATIONAL, FRESHNESS, EVIDENCE, MODIFICATIONS
        # ---------------------------------------------------------------------
        base_evidence_list: List[Dict[str, Any]] = base_graph.get("evidence", [])
        target_evidence_list: List[Dict[str, Any]] = target_graph.get("evidence", [])
        base_ev_by_edge: Dict[str, List[Dict[str, Any]]] = {}
        for ev in base_evidence_list:
            base_ev_by_edge.setdefault(ev.get("edge_id", ""), []).append(ev)
        target_ev_by_edge: Dict[str, List[Dict[str, Any]]] = {}
        for ev in target_evidence_list:
            target_ev_by_edge.setdefault(ev.get("edge_id", ""), []).append(ev)

        for be, te in matched_pairs:
            eid = be["id"]

            # Operational Status Change:
            b_op = be.get("oper_status") or "unknown"
            t_op = te.get("oper_status") or "unknown"
            if b_op != t_op:
                operational_changes.append({
                    "change_type": "STATUS_CHANGED",
                    "entity_type": "edge",
                    "entity_id": eid,
                    "attribute_name": "oper_status",
                    "before_value": b_op,
                    "after_value": t_op,
                    "change_reason": f"Operational status transitioned from '{b_op}' to '{t_op}'",
                })

            # Observation Freshness Change:
            b_fresh = be.get("observation_freshness")
            t_fresh = te.get("observation_freshness")
            if b_fresh is not None and t_fresh is not None:
                try:
                    if round(float(b_fresh), 4) != round(float(t_fresh), 4):
                        freshness_changes.append({
                            "change_type": "FRESHNESS_CHANGED",
                            "entity_type": "edge",
                            "entity_id": eid,
                            "attribute_name": "observation_freshness",
                            "before_value": b_fresh,
                            "after_value": t_fresh,
                            "change_reason": f"Observation freshness updated from {b_fresh} to {t_fresh}",
                        })
                except (ValueError, TypeError):
                    pass

            # Evidence Differences:
            b_evs = be.get("evidence") or base_ev_by_edge.get(eid, [])
            t_evs = te.get("evidence") or target_ev_by_edge.get(te["id"], [])

            b_active_count = sum(1 for ev in b_evs if ev.get("is_active", True))
            t_active_count = sum(1 for ev in t_evs if ev.get("is_active", True))

            b_ev_ids = {ev.get("id") for ev in b_evs if ev.get("id") is not None}
            t_ev_ids = {ev.get("id") for ev in t_evs if ev.get("id") is not None}
            new_evs = [ev for ev in t_evs if ev.get("id") not in b_ev_ids and ev.get("id") is not None]
            if new_evs or len(t_evs) > len(b_evs):
                evidence_changes.append({
                    "change_type": "EVIDENCE_CHANGED",
                    "entity_type": "edge",
                    "entity_id": eid,
                    "attribute_name": "evidence_added",
                    "before_value": len(b_evs),
                    "after_value": len(t_evs),
                    "change_reason": f"{len(new_evs) or (len(t_evs) - len(b_evs))} new evidence item(s) attached to edge",
                })

            expired_evs = [
                ev for ev in t_evs
                if not ev.get("is_active", True)
                and any(old.get("id") == ev.get("id") and old.get("is_active", True) for old in b_evs)
            ]
            if expired_evs or (t_active_count < b_active_count and len(t_evs) <= len(b_evs)):
                evidence_changes.append({
                    "change_type": "EVIDENCE_EXPIRED",
                    "entity_type": "edge",
                    "entity_id": eid,
                    "attribute_name": "evidence_expired",
                    "before_value": b_active_count,
                    "after_value": t_active_count,
                    "change_reason": "Evidence item on edge transitioned to expired/inactive state",
                })

            b_conf = be.get("confidence_tier") or be.get("confidence") or be.get("confidence_score")
            t_conf = te.get("confidence_tier") or te.get("confidence") or te.get("confidence_score")
            if b_conf is not None and t_conf is not None and str(b_conf).upper() != str(t_conf).upper():
                evidence_changes.append({
                    "change_type": "CONFIDENCE_CHANGED",
                    "entity_type": "edge",
                    "entity_id": eid,
                    "attribute_name": "confidence_score",
                    "before_value": b_conf,
                    "after_value": t_conf,
                    "change_reason": f"Confidence score changed from {b_conf} to {t_conf}",
                })

            edge_attrs_to_check = ["confidence_rationale", "link_speed", "mtu", "is_lag_member", "lag_master_id"]
            for attr in edge_attrs_to_check:
                bv = be.get(attr)
                tv = te.get(attr)
                if bv is not None and tv is not None and bv != tv:
                    structural_changes.append({
                        "change_type": "EDGE_MODIFIED",
                        "entity_type": "edge",
                        "entity_id": eid,
                        "attribute_name": attr,
                        "before_value": bv,
                        "after_value": tv,
                        "change_reason": f"Edge attribute '{attr}' modified from '{bv}' to '{tv}'",
                    })

        t5 = time.perf_counter()
        diff_compute_ms = round((t5 - t4) * 1000.0, 3)
        total_duration_ms = round((t5 - t0) * 1000.0, 3)

        summary = {
            "nodes_added": sum(1 for c in structural_changes if c["change_type"] == "NODE_ADDED"),
            "nodes_removed": sum(1 for c in structural_changes if c["change_type"] == "NODE_REMOVED"),
            "nodes_modified": sum(1 for c in structural_changes if c["change_type"] == "NODE_MODIFIED"),
            "edges_added": sum(1 for c in structural_changes if c["change_type"] == "EDGE_ADDED"),
            "edges_removed": sum(1 for c in structural_changes if c["change_type"] == "EDGE_REMOVED"),
            "edges_modified": sum(1 for c in structural_changes if c["change_type"] == "EDGE_MODIFIED"),
            "operational_changes": len(operational_changes),
            "freshness_changes": len(freshness_changes),
            "evidence_changes": len(evidence_changes),
            "indeterminate_count": len(indeterminate_items),
        }

        telemetry = {
            "db_query_ms": db_query_ms,
            "deserialization_ms": deserialization_ms,
            "diff_compute_ms": diff_compute_ms,
            "total_duration_ms": total_duration_ms,
            "base_graph_size": {"nodes": len(base_nodes), "edges": len(base_edges)},
            "target_graph_size": {"nodes": len(target_nodes), "edges": len(target_edges)},
        }

        return GraphDiffReport(
            base_snapshot_id=base_id_str,
            target_snapshot_id=target_id_str,
            generated_at=time.time(),
            summary=summary,
            structural_changes=structural_changes,
            operational_changes=operational_changes,
            evidence_changes=evidence_changes,
            freshness_changes=freshness_changes,
            indeterminate_items=indeterminate_items,
            telemetry=telemetry,
        )

    def record_change(
        self,
        change: TopologyChange,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Records a topology graph delta change."""
        if not isinstance(change, TopologyChange):
            raise TypeError("change must be an instance of TopologyChange.")

        def _execute(c: sqlite3.Connection) -> int:
            cur = c.execute(
                """
                INSERT INTO topology_changes (
                    snapshot_id, change_type, entity_id, change_reason,
                    attribute_name, before_value_json, after_value_json, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change.snapshot_id,
                    change.change_type,
                    change.entity_id,
                    change.change_reason,
                    change.attribute_name,
                    change.before_value_json,
                    change.after_value_json,
                    change.detected_at,
                ),
            )
            return int(cur.lastrowid)

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

    def get_change(
        self,
        change_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[TopologyChange]:
        """Retrieves a single TopologyChange record by its primary key ID."""
        def _execute(c: sqlite3.Connection) -> Optional[TopologyChange]:
            row = c.execute("SELECT * FROM topology_changes WHERE id = ?", (change_id,)).fetchone()
            if not row:
                return None
            return TopologyChange.from_dict(dict(row))

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def count_changes(
        self,
        snapshot_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        change_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """Counts recorded topology delta changes with optional filters."""
        query = "SELECT count(*) FROM topology_changes WHERE 1=1"
        params: List[Any] = []
        if snapshot_id:
            query += " AND snapshot_id = ?"
            params.append(snapshot_id)
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        if change_type:
            norm_type = normalize_topology_change_type(change_type)
            query += " AND change_type = ?"
            params.append(norm_type)
        if start_time is not None:
            query += " AND detected_at >= ?"
            params.append(start_time)
        if end_time is not None:
            query += " AND detected_at <= ?"
            params.append(end_time)

        def _execute(c: sqlite3.Connection) -> int:
            return int(c.execute(query, params).fetchone()[0])

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    def list_changes(
        self,
        snapshot_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        change_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[TopologyChange]:
        """Lists recorded topology delta changes with optional filters and pagination."""
        query = "SELECT * FROM topology_changes WHERE 1=1"
        params: List[Any] = []
        if snapshot_id:
            query += " AND snapshot_id = ?"
            params.append(snapshot_id)
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        if change_type:
            norm_type = normalize_topology_change_type(change_type)
            query += " AND change_type = ?"
            params.append(norm_type)
        if start_time is not None:
            query += " AND detected_at >= ?"
            params.append(start_time)
        if end_time is not None:
            query += " AND detected_at <= ?"
            params.append(end_time)
        query += " ORDER BY detected_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])

        def _execute(c: sqlite3.Connection) -> List[TopologyChange]:
            rows = c.execute(query, params).fetchall()
            return [TopologyChange.from_dict(dict(r)) for r in rows]

        if conn is not None:
            return _execute(conn)
        with closing(self._get_connection(read_only=True)) as auto_conn:
            return _execute(auto_conn)

    # ------------------------------------------------------------------
    # Policy & Governance Configuration
    # ------------------------------------------------------------------

    def get_policy(self) -> Dict[str, Any]:
        with closing(self._get_connection(read_only=True)) as conn:
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

    def _reconcile_discovered_edge(
        self,
        *,
        source_id: str,
        target_id: str,
        relationship_class: str,
        source_interface: str = "",
        target_interface: str = "",
        relationship_subtype: str = "",
        direction: str = "bidirectional",
        oper_status: str = "up",
        admin_status: str = "enabled",
        verification_status: str = "observed",
        confidence_tier: str = "MEDIUM",
        confidence_score: float = 0.5,
        confidence_rationale: str = "",
        bandwidth_bps: int = 1000000000,
        vlan_id: Optional[int] = None,
        is_lag_member: bool = False,
        lag_parent_edge_id: Optional[str] = None,
        evidence_item: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        """
        Reconciles discovered multi-layer topology edges idempotently in topology_edges
        and records evidence in topology_edge_evidence.

        Supports:
        - Strict relationship class separation (physical, layer2, layer3, logical).
        - Multi-edge support: does NOT overwrite parallel edges of different classes or interfaces.
        - Bidirectional corroboration upgrade to 'physical' / 'CONFIRMED' when both endpoints match on physical ports.
        - Epistemic guardrail: subnets and ARP entries are NEVER promoted to physical adjacency.
        - First-class evidence tracking in topology_edge_evidence.
        """
        ts = now if now is not None else time.time()
        norm_rc = normalize_relationship_class(relationship_class)
        norm_ct = normalize_confidence_tier(confidence_tier)
        s_if = sanitize_untrusted_text(source_interface, 64)
        t_if = sanitize_untrusted_text(target_interface, 64)

        def _execute(c: sqlite3.Connection) -> str:
            # 1. Validate both endpoints exist in topology_nodes
            s_node = c.execute("SELECT id FROM topology_nodes WHERE id = ?", (source_id,)).fetchone()
            t_node = c.execute("SELECT id FROM topology_nodes WHERE id = ?", (target_id,)).fetchone()
            if not s_node or not t_node:
                logger.debug(
                    "Cannot reconcile edge %s -> %s: endpoint(s) missing in topology_nodes.",
                    source_id,
                    target_id,
                )
                return ""

            # 2. Check for existing edge in forward or reverse direction
            pair_rows = c.execute(
                """
                SELECT * FROM topology_edges
                WHERE (source_node_id = ? AND target_node_id = ? AND relationship_class = ?)
                   OR (direction = 'bidirectional' AND source_node_id = ? AND target_node_id = ? AND relationship_class = ?)
                """,
                (source_id, target_id, norm_rc, target_id, source_id, norm_rc),
            ).fetchall()

            matched_row = None
            is_reverse = False

            for r in pair_rows:
                rev = r["source_node_id"] == target_id and r["target_node_id"] == source_id
                ex_s_if = r["target_interface"] if rev else r["source_interface"]
                ex_t_if = r["source_interface"] if rev else r["target_interface"]
                ex_sub = r["relationship_subtype"]

                # Exact port pair match
                if (ex_s_if == s_if and ex_t_if == t_if) or (ex_s_if == s_if and not ex_t_if and not t_if):
                    if not relationship_subtype or not ex_sub or relationship_subtype == ex_sub:
                        matched_row = r
                        is_reverse = rev
                        break
                # Port refinement (remote port previously missing, now observed)
                elif ex_s_if == s_if and not ex_t_if and t_if:
                    matched_row = r
                    is_reverse = rev
                    break
                # Generic match when both interfaces empty (e.g. subnet-level edges)
                elif not ex_s_if and not ex_t_if and not s_if and not t_if:
                    if not relationship_subtype or not ex_sub or relationship_subtype == ex_sub:
                        matched_row = r
                        is_reverse = rev
                        break

            if matched_row is not None:
                edge_id = str(matched_row["id"])
                ex_s_if = matched_row["target_interface"] if is_reverse else matched_row["source_interface"]
                ex_t_if = matched_row["source_interface"] if is_reverse else matched_row["target_interface"]

                final_rc = matched_row["relationship_class"]
                final_sub = matched_row["relationship_subtype"] or relationship_subtype
                final_vstatus = matched_row["verification_status"]
                final_tier = matched_row["confidence_tier"]
                final_score = float(matched_row["confidence_score"] or 0.5)
                final_rationale = matched_row["confidence_rationale"]
                last_ver = matched_row["last_verified"]

                # Bidirectional corroboration upgrade
                if is_reverse:
                    ports_physical = any(p in (s_if or "").lower() for p in ("ether", "sfp")) and any(p in (t_if or "").lower() for p in ("ether", "sfp"))
                    if s_if and (t_if or ex_t_if) and (norm_rc in ("layer2", "physical")):
                        if ports_physical:
                            final_rc = "physical"
                            final_sub = "direct_copper" if "ether" in s_if.lower() else "direct_fiber"
                            final_vstatus = "confirmed"
                            final_tier = "CONFIRMED"
                            final_score = 1.0
                            final_rationale = (
                                f"Verified physical adjacency: both {matched_row['source_node_id']} ({ex_s_if}) and "
                                f"{matched_row['target_node_id']} ({s_if}) independently confirmed identities and port mapping."
                            )
                            last_ver = ts
                else:
                    if confidence_score > final_score:
                        final_score = confidence_score
                        final_tier = norm_ct
                        final_rationale = confidence_rationale or final_rationale
                    final_vstatus = verification_status or final_vstatus

                if matched_row["provenance"] == "user_managed" or matched_row["verification_status"] == "manual":
                    c.execute(
                        "UPDATE topology_edges SET last_seen = ?, observation_freshness = 'fresh' WHERE id = ?",
                        (ts, edge_id),
                    )
                else:
                    c.execute(
                        """
                        UPDATE topology_edges
                        SET last_seen = ?, last_verified = ?, oper_status = ?, verification_status = ?,
                            confidence_tier = ?, confidence_score = ?, confidence_rationale = ?,
                            relationship_class = ?, relationship_subtype = ?, target_interface = ?,
                            observation_freshness = 'fresh', lifecycle_state = 'active'
                        WHERE id = ?
                        """,
                        (
                            ts,
                            last_ver,
                            oper_status,
                            final_vstatus,
                            final_tier,
                            final_score,
                            final_rationale,
                            final_rc,
                            final_sub,
                            t_if or matched_row["target_interface"],
                            edge_id,
                        ),
                    )
            else:
                clean_src = re.sub(r"[^a-zA-Z0-9_]", "_", source_id.lower())
                clean_tgt = re.sub(r"[^a-zA-Z0-9_]", "_", target_id.lower())
                clean_s_if = re.sub(r"[^a-zA-Z0-9_]", "_", s_if.lower()) if s_if else "any"
                clean_t_if = re.sub(r"[^a-zA-Z0-9_]", "_", t_if.lower()) if t_if else "any"
                sub_suffix = f"_{relationship_subtype}" if relationship_subtype else ""
                vlan_suffix = f"_vlan{vlan_id}" if vlan_id is not None else ""

                edge_id = f"edge_{norm_rc}_{clean_src}_{clean_s_if}__{clean_tgt}_{clean_t_if}{sub_suffix}{vlan_suffix}"

                existing_by_id = c.execute("SELECT id FROM topology_edges WHERE id = ?", (edge_id,)).fetchone()
                if existing_by_id:
                    edge_id = f"{edge_id}_{int(ts * 1000) % 100000}"

                edge_obj = TopologyEdge(
                    id=edge_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                    source_interface=s_if,
                    target_interface=t_if,
                    relationship_class=norm_rc,
                    relationship_subtype=relationship_subtype or ("direct_copper" if norm_rc == "physical" else ("bridge_port_member" if norm_rc == "layer2" else "routed_multiaccess")),
                    direction=direction,
                    oper_status=oper_status,
                    admin_status=admin_status,
                    verification_status=verification_status,
                    confidence_tier=norm_ct,
                    confidence_score=confidence_score,
                    confidence_rationale=confidence_rationale or f"Discovered via {evidence_item.get('protocol', 'empirical evidence') if evidence_item else 'telemetry'}.",
                    bandwidth_bps=bandwidth_bps,
                    vlan_id=vlan_id,
                    is_lag_member=is_lag_member,
                    lag_parent_edge_id=lag_parent_edge_id,
                    first_seen=ts,
                    last_seen=ts,
                    last_verified=ts if verification_status == "confirmed" else None,
                    observation_freshness="fresh",
                    lifecycle_state="active",
                    provenance="discovery_managed",
                )
                self.insert_edge(edge_obj, conn=c)

                self.record_change(
                    TopologyChange(
                        change_type="EDGE_ADDED",
                        entity_id=edge_id,
                        change_reason="Discovered via telemetry reconciliation",
                        detected_at=ts,
                    ),
                    conn=c,
                )

            # 4. Attach EdgeEvidence if provided
            if evidence_item:
                ev_type = evidence_item.get("evidence_type", "neighbor_discovery")
                proto = evidence_item.get("protocol", "")
                raw_ex = sanitize_cli_excerpt(evidence_item.get("raw_excerpt", ""), max_len=16000)
                exp = evidence_item.get("explanation", confidence_rationale)
                conf_contrib = evidence_item.get("confidence", "medium")

                half_life = EVIDENCE_HALF_LIVES.get(proto, EVIDENCE_HALF_LIVES.get(ev_type, DEFAULT_HALF_LIFE))
                expires_at = None if half_life == float("inf") else (ts + 2.0 * half_life)

                ev_obj = EdgeEvidence(
                    edge_id=edge_id,
                    evidence_type=ev_type,
                    protocol=proto,
                    observing_device_id=source_id,
                    local_interface=s_if,
                    remote_interface=t_if,
                    remote_chassis_mac=evidence_item.get("remote_chassis_mac", ""),
                    raw_excerpt=raw_ex,
                    confidence_contribution=conf_contrib,
                    explanation=exp,
                    observed_at=ts,
                    expires_at=expires_at,
                    is_active=1,
                    metadata=evidence_item.get("metadata", {}),
                )
                self.insert_edge_evidence(ev_obj, conn=c)

                self.record_change(
                    TopologyChange(
                        change_type="EVIDENCE_CHANGED",
                        entity_id=edge_id,
                        change_reason=f"Evidence {ev_type} ({proto}) recorded",
                        detected_at=ts,
                    ),
                    conn=c,
                )

            return edge_id

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

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
    def correlate_and_reconcile_device_bundles(
        self,
        device_bundles: Dict[str, Dict[str, Any]],
        now: Optional[float] = None,
    ) -> List[str]:
        """
        Integrates CrossDeviceEvidenceCorrelator into the discovery reconciliation loop.
        Correlates multi-device evidence and reconciles resulting relationships into
        topology_edges and topology_edge_evidence.
        """
        from core.network_intelligence.correlation import CrossDeviceEvidenceCorrelator
        correlator = CrossDeviceEvidenceCorrelator()
        relationships = correlator.correlate_bundles(device_bundles)
        return correlator.reconcile_correlated_relationships_to_engine(
            relationships, self, now=now
        )

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

    def delete_link(self, link_id: str, actor: str = "admin", reason: str = "Administrative link deletion") -> bool:
        with self._lock, closing(self._get_connection()) as conn:
            conn.execute("DELETE FROM topology_evidence WHERE subject_type = 'link' AND subject_id = ?", (link_id,))
            cur = conn.execute("DELETE FROM topology_links WHERE id = ?", (link_id,))
            rowcount = cur.rowcount
            table_names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "topology_edges" in table_names:
                # Soft-delete matching edge to preserve empirical evidence for audit continuity
                cur_edge = conn.execute(
                    "UPDATE topology_edges SET lifecycle_state = 'tombstoned', last_seen = ? WHERE id = ? AND lifecycle_state != 'tombstoned'",
                    (time.time(), link_id),
                )
                rowcount += cur_edge.rowcount

            if rowcount > 0:
                now_ts = time.time()
                if "topology_changes" in table_names:
                    self.record_change(
                        TopologyChange(
                            change_type=TopologyChangeType.EDGE_REMOVED.value,
                            entity_id=link_id,
                            change_reason=reason,
                            detected_at=now_ts,
                        ),
                        conn=conn,
                    )
                if "topology_audit_log" in table_names:
                    conn.execute(
                        "INSERT INTO topology_audit_log (actor, action, target_type, target_id, reason, created_at) "
                        "VALUES (?, 'delete_link', 'link', ?, ?, ?)",
                        (actor, link_id, reason, now_ts),
                    )
            conn.commit()
            return rowcount > 0

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
            successful_dev_list: List[str] = []
            failed_dev_list: List[str] = []
            timed_out_dev_list: List[str] = []

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
                    failed_dev_list.append(cur_name)
                    if "timeout" in err_msg.lower():
                        timed_out_dev_list.append(cur_name)
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
                        failed_comp = {
                            "discovery_status": "failed",
                            "expected_devices": [cur_name],
                            "successful_devices": [],
                            "failed_devices": [cur_name],
                            "timed_out_devices": [cur_name] if "timeout" in err_msg.lower() else [],
                            "collection_scope": effective_mode,
                            "started_at": started_at,
                            "completed_at": time.time(),
                            "is_complete": False,
                        }
                        try:
                            self.create_snapshot(
                                trigger_type="discovery_run",
                                description=f"Failed discovery: {cur_name}",
                                discovery_run_id=job_id,
                                completeness=failed_comp,
                            )
                        except Exception as e_snap:
                            logger.warning(f"Could not create failed discovery snapshot: {e_snap}")
                        return {"success": False, "job_id": job_id, "error": f"Gagal menginterogasi {cur_name}: {err_msg}"}
                    continue

                successful_dev_list.append(cur_name)
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

            # Phase 4.4A Snapshot & Semantic Diff Integration
            expected_devs = [d["name"] for d in enabled_devs] if effective_mode == "enterprise_managed" else list(visited_names)
            is_comp = (len(failed_dev_list) == 0 and len(timed_out_dev_list) == 0 and len(successful_dev_list) > 0 and len(errors) == 0)
            disc_status = "complete" if is_comp else ("failed" if not successful_dev_list else "partial")

            comp_meta = {
                "discovery_status": disc_status,
                "expected_devices": expected_devs,
                "successful_devices": successful_dev_list,
                "failed_devices": failed_dev_list,
                "timed_out_devices": timed_out_dev_list,
                "collection_scope": effective_mode,
                "started_at": started_at,
                "completed_at": time.time(),
                "is_complete": is_comp,
            }

            new_snap = None
            diff_report = None
            try:
                prior_snaps = self.list_snapshots(limit=2)
                prior_snap = prior_snaps[0] if prior_snaps else None

                new_snap = self.create_snapshot(
                    trigger_type="discovery_run",
                    description=summary,
                    discovery_run_id=job_id,
                    completeness=comp_meta,
                )

                if prior_snap and prior_snap.snapshot_id != new_snap.snapshot_id:
                    diff_report = self.compare_snapshots(prior_snap.snapshot_id, new_snap.snapshot_id)

                    for ch in diff_report.structural_changes:
                        self.record_change(
                            TopologyChange(
                                snapshot_id=new_snap.snapshot_id,
                                change_type=ch["change_type"],
                                entity_id=ch["entity_id"],
                                change_reason=ch.get("change_reason", ""),
                                attribute_name=ch.get("attribute_name", ""),
                                before_value_json=json.dumps(ch.get("before_value")) if ch.get("before_value") is not None else "",
                                after_value_json=json.dumps(ch.get("after_value")) if ch.get("after_value") is not None else "",
                            )
                        )
                    for ch in diff_report.operational_changes:
                        self.record_change(
                            TopologyChange(
                                snapshot_id=new_snap.snapshot_id,
                                change_type="STATUS_CHANGED",
                                entity_id=ch["entity_id"],
                                change_reason=ch.get("change_reason", ""),
                                attribute_name=ch.get("attribute_name", "oper_status"),
                                before_value_json=json.dumps(ch.get("before_value")) if ch.get("before_value") is not None else "",
                                after_value_json=json.dumps(ch.get("after_value")) if ch.get("after_value") is not None else "",
                            )
                        )
                    for ch in diff_report.evidence_changes:
                        self.record_change(
                            TopologyChange(
                                snapshot_id=new_snap.snapshot_id,
                                change_type=ch["change_type"],
                                entity_id=ch["entity_id"],
                                change_reason=ch.get("change_reason", ""),
                                attribute_name=ch.get("attribute_name", "evidence"),
                                before_value_json=json.dumps(ch.get("before_value")) if ch.get("before_value") is not None else "",
                                after_value_json=json.dumps(ch.get("after_value")) if ch.get("after_value") is not None else "",
                            )
                        )
                    for ch in diff_report.freshness_changes:
                        self.record_change(
                            TopologyChange(
                                snapshot_id=new_snap.snapshot_id,
                                change_type=ch["change_type"],
                                entity_id=ch["entity_id"],
                                change_reason=ch.get("change_reason", ""),
                                attribute_name=ch.get("attribute_name", "observation_freshness"),
                                before_value_json=json.dumps(ch.get("before_value")) if ch.get("before_value") is not None else "",
                                after_value_json=json.dumps(ch.get("after_value")) if ch.get("after_value") is not None else "",
                            )
                        )
            except Exception as e_snap:
                logger.warning(f"Error creating/comparing discovery snapshot: {e_snap}")

            return {
                "success": True,
                "job_id": job_id,
                "mode": effective_mode,
                "message": summary,
                "errors": errors,
                "limitations": limitations,
                "details": first_details or {},
                "snapshot_id": new_snap.snapshot_id if new_snap else None,
                "diff_summary": diff_report.summary if diff_report else {},
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
            "edges": [e.to_dict() for e in self.list_edges()],
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


    # =======================================================================
    # Phase 4.3: Real-Time NMS Operational Event Synchronization & Decayer
    # =======================================================================

    @staticmethod
    def _normalize_nms_oper_status(raw_status: Any) -> str:
        s = str(raw_status).strip().lower()
        if s in ("up", "running", "active", "online", "ok", "true", "1"):
            return "up"
        if s in ("down", "inactive", "offline", "failed", "error", "false", "0", "disabled"):
            return "down"
        if s in ("degraded", "warning", "suspected_down"):
            return "degraded"
        return "unknown"

    def _resolve_canonical_node_id(
        self,
        query: str,
        conn: sqlite3.Connection,
    ) -> Optional[str]:
        """
        Resolves query to a topology_nodes primary key using CanonicalDevice registry first,
        falling back to direct topology_nodes lookup.
        """
        if not query:
            return None

        # 1. Check CanonicalNetworkRegistry
        try:
            from core.canonical_network import get_canonical_registry
            registry = get_canonical_registry()
            c_dev = registry.resolve_device(query)
            if c_dev:
                candidates = [c_dev.device_id, c_dev.inventory_name, c_dev.observed_identity, c_dev.hostname]
                candidates = [c for c in candidates if c]
                for cand in candidates:
                    row = conn.execute(
                        "SELECT id FROM topology_nodes WHERE id = ? OR LOWER(name) = LOWER(?) OR LOWER(identity) = LOWER(?)",
                        (cand, cand, cand),
                    ).fetchone()
                    if row:
                        return str(row["id"])

                if c_dev.management_ip:
                    row = conn.execute("SELECT id FROM topology_nodes WHERE ip = ?", (c_dev.management_ip,)).fetchone()
                    if row:
                        return str(row["id"])
                for ip_str in (c_dev.all_ips or []):
                    row = conn.execute("SELECT id FROM topology_nodes WHERE ip = ?", (ip_str,)).fetchone()
                    if row:
                        return str(row["id"])

                if c_dev.primary_mac:
                    norm_m = normalize_mac(c_dev.primary_mac)
                    row = conn.execute("SELECT id FROM topology_nodes WHERE UPPER(mac) = UPPER(?)", (norm_m,)).fetchone()
                    if row:
                        return str(row["id"])
        except Exception as exc:
            logger.debug("Canonical registry resolution fallback: %s", exc)

        # 2. Fallback to direct topology_nodes matching
        clean_q = str(query).strip()
        row = conn.execute(
            "SELECT id FROM topology_nodes WHERE id = ? OR LOWER(name) = LOWER(?) OR LOWER(identity) = LOWER(?) OR ip = ?",
            (clean_q, clean_q, clean_q, clean_q),
        ).fetchone()
        if row:
            return str(row["id"])

        norm_m = normalize_mac(clean_q)
        if norm_m:
            row = conn.execute("SELECT id FROM topology_nodes WHERE UPPER(mac) = UPPER(?)", (norm_m,)).fetchone()
            if row:
                return str(row["id"])

        return None

    def handle_nms_event(
        self,
        event: Any,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        """
        Processes real-time NMS operational events (interface and device status changes).
        Strictly preserves topology invariance:
        - NEVER creates topology edges or nodes from NMS events alone.
        - NEVER modifies relationship_class, relationship_subtype, endpoint devices/interfaces,
          physical adjacency classification, or confidence tier/score.
        - NEVER tombstones or deletes edges on link down.
        - Handles duplicate, delayed, out-of-order, or missing-reference events idempotently.
        """
        if event is None:
            return {"success": False, "error": "empty_event", "edges_updated": 0}

        event_name = ""
        payload: Dict[str, Any] = {}
        event_id = None
        event_timestamp_raw = None

        if hasattr(event, "event") and hasattr(event, "data"):
            event_name = str(event.event)
            payload = event.data if isinstance(event.data, dict) else {}
            event_id = getattr(event, "event_id", None)
            event_timestamp_raw = getattr(event, "timestamp", None)
        elif isinstance(event, dict):
            event_name = str(event.get("event") or event.get("event_name") or EventNames.NMS_INTERFACE_STATUS_CHANGED)
            payload = event.get("data") if isinstance(event.get("data"), dict) else event
            event_id = payload.get("event_id") or event.get("event_id")
            event_timestamp_raw = payload.get("timestamp") or event.get("timestamp")
        else:
            return {"success": False, "error": "invalid_event_format", "edges_updated": 0}

        if not isinstance(payload, dict):
            return {"success": False, "error": "payload_not_dict", "edges_updated": 0}

        # Normalize timestamp to float epoch
        event_time: float
        if "timestamp" in payload and isinstance(payload["timestamp"], (int, float)):
            event_time = float(payload["timestamp"])
        elif event_timestamp_raw is not None:
            if isinstance(event_timestamp_raw, (int, float)):
                event_time = float(event_timestamp_raw)
            else:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(event_timestamp_raw).replace("Z", "+00:00"))
                    event_time = dt.timestamp()
                except Exception:
                    event_time = time.time()
        else:
            event_time = time.time()

        is_status_transition_event = (
            event_name in (
                EventNames.NMS_INTERFACE_STATUS_CHANGED,
                "nms.interface.status_changed",
            )
        )
        is_interface_observed = (
            event_name in (
                getattr(EventNames, "NMS_INTERFACE_OBSERVED", "nms.interface.observed"),
                "nms.interface.observed",
            )
        )
        is_interface_event = is_status_transition_event or is_interface_observed
        is_device_event = (
            event_name in (
                EventNames.NMS_DEVICE_STATUS,
                "nms.device.status_changed",
                "nms.device_status",
            )
        )

        if not is_interface_event and not is_device_event:
            return {
                "success": False,
                "reason": "unknown_event_type",
                "event_type": event_name,
                "edges_updated": 0,
            }

        def _execute(c: sqlite3.Connection) -> Dict[str, Any]:
            if is_interface_event:
                return self._process_interface_status_event(
                    payload=payload,
                    event_id=event_id,
                    event_time=event_time,
                    conn=c,
                    is_status_transition_event=is_status_transition_event,
                )
            else:
                return self._process_device_status_event(
                    payload=payload,
                    event_id=event_id,
                    event_time=event_time,
                    conn=c,
                )

        if conn is not None:
            return _execute(conn)

        def _do_write() -> Dict[str, Any]:
            with self._lock, closing(self._get_connection()) as auto_conn:
                res = _execute(auto_conn)
                auto_conn.commit()
                return res

        result = execute_with_retry(_do_write, operation_name="handle_nms_event")
        pending = result.pop("_pending_events", [])
        if pending:
            try:
                event_bus = self._target_bus or get_event_bus()
                for p_data in pending:
                    try:
                        event_bus.publish("topology.delta", data=p_data)
                    except Exception as emit_err:
                        logger.warning("Error publishing topology.delta outside transaction: %s", emit_err)
            except Exception:
                pass
        return result

    def _process_interface_status_event(
        self,
        payload: Dict[str, Any],
        event_id: Optional[str],
        event_time: float,
        conn: sqlite3.Connection,
        is_status_transition_event: bool = True,
    ) -> Dict[str, Any]:
        device_ref = (
            payload.get("device_id")
            or payload.get("device")
            or payload.get("device_name")
            or payload.get("host")
            or payload.get("ip")
        )
        if not device_ref or not str(device_ref).strip():
            return {"success": False, "error": "missing_device_reference", "edges_updated": 0}

        iface_ref = (
            payload.get("interface_name")
            or payload.get("interface")
            or payload.get("iface")
            or payload.get("iname")
            or payload.get("port")
        )
        if iface_ref is None or not str(iface_ref).strip():
            return {"success": False, "error": "missing_interface_reference", "edges_updated": 0}
        clean_iface = str(iface_ref).strip()

        oper_raw = payload.get("oper_status") or payload.get("status")
        if not oper_raw or not str(oper_raw).strip():
            return {"success": False, "error": "missing_oper_status", "edges_updated": 0}

        norm_status = self._normalize_nms_oper_status(oper_raw)

        pending_events: List[Dict[str, Any]] = []
        resolved_node_id = self._resolve_canonical_node_id(str(device_ref).strip(), conn)
        if not resolved_node_id:
            logger.debug("NMS sync: device '%s' not recognized in topology.", device_ref)
            return {"success": False, "reason": "unknown_device", "edges_updated": 0}

        matching_edges = conn.execute(
            """
            SELECT * FROM topology_edges
            WHERE lifecycle_state != 'tombstoned'
              AND (
                (source_node_id = ? AND LOWER(source_interface) = LOWER(?))
                OR
                (target_node_id = ? AND LOWER(target_interface) = LOWER(?))
              )
            """,
            (resolved_node_id, clean_iface, resolved_node_id, clean_iface),
        ).fetchall()

        if not matching_edges:
            logger.debug(
                "NMS sync: no matching topology edge for device '%s' interface '%s'. Invariance preserved (no edge created).",
                resolved_node_id, clean_iface,
            )
            return {
                "success": True,
                "reason": "interface_not_mapped",
                "device_id": resolved_node_id,
                "interface": clean_iface,
                "edges_updated": 0,
            }

        updated_count = 0
        now_ts = event_time

        for edge in matching_edges:
            edge_id = edge["id"]
            current_status = edge["oper_status"]
            current_last_seen = float(edge["last_seen"]) if edge["last_seen"] else 0.0

            try:
                meta = json.loads(edge["metadata_json"] or "{}")
            except Exception:
                meta = {}

            last_nms_ts = float(meta.get("last_nms_timestamp") or current_last_seen)

            # Ordering check: older event must not overwrite newer observation
            if now_ts < last_nms_ts:
                logger.debug(
                    "NMS sync: out-of-order event dropped for edge %s (event_ts=%.2f < last_ts=%.2f)",
                    edge_id, now_ts, last_nms_ts,
                )
                continue

            # Idempotency check: duplicate delivery
            if now_ts == last_nms_ts and current_status == norm_status:
                logger.debug("NMS sync: duplicate event ignored for edge %s", edge_id)
                continue

            meta["last_nms_timestamp"] = now_ts
            meta["last_nms_oper_status"] = norm_status
            meta["last_nms_interface"] = clean_iface
            meta["last_nms_device"] = resolved_node_id
            if event_id:
                meta["last_nms_event_id"] = event_id
            if "admin_status" in payload:
                meta["last_nms_admin_status"] = payload["admin_status"]
            if "speed_bps" in payload:
                meta["last_nms_speed_bps"] = payload["speed_bps"]

            # Check if this represents a genuine status transition:
            # Only transition status if it is a status transition event and status actually changed.
            # If it is an observation event (NMS_INTERFACE_OBSERVED), oper_status is preserved
            # (unless it was 'unknown' and we now know a concrete operational status).
            has_status_transition = is_status_transition_event and (current_status != norm_status)
            new_status = norm_status if has_status_transition or current_status == "unknown" else current_status

            # CRITICAL TOPOLOGY INVARIANCE:
            # ONLY update oper_status (on genuine transition/unknown initialization), last_seen, observation_freshness, metadata_json.
            # relationship_class, relationship_subtype, confidence_score, tier, endpoints,
            # and lifecycle_state remain strictly invariant.
            conn.execute(
                """
                UPDATE topology_edges
                SET oper_status = ?,
                    last_seen = ?,
                    observation_freshness = 'fresh',
                    metadata_json = ?
                WHERE id = ?
                """,
                (new_status, now_ts, json.dumps(meta), edge_id),
            )
            updated_count += 1

            # Only record delta in topology_changes and emit WebSocket event if genuine status transition occurred!
            if has_status_transition:
                self.record_change(
                    TopologyChange(
                        change_type=TopologyChangeType.STATUS_CHANGED.value,
                        entity_id=edge_id,
                        change_reason=f"OPERATIONAL_{norm_status.upper()}",
                        attribute_name="oper_status",
                        before_value_json=json.dumps(current_status),
                        after_value_json=json.dumps(norm_status),
                        detected_at=now_ts,
                    ),
                    conn=conn,
                )

                # Update legacy topology_links for backward compatibility
                conn.execute(
                    """
                    UPDATE topology_links
                    SET status = ?,
                        last_checked = ?
                    WHERE (source_id = ? AND LOWER(source_port) = LOWER(?))
                       OR (target_id = ? AND LOWER(target_port) = LOWER(?))
                    """,
                    (norm_status, now_ts, resolved_node_id, clean_iface, resolved_node_id, clean_iface),
                )

                # Emit delta event on EventBus for WebSocket push ONLY on genuine transition
                pending_events.append({
                    "edge_id": edge_id,
                    "oper_status": norm_status,
                    "previous_status": current_status,
                    "source_node_id": edge["source_node_id"],
                    "target_node_id": edge["target_node_id"],
                    "source_interface": edge["source_interface"],
                    "target_interface": edge["target_interface"],
                    "timestamp": now_ts,
                })
            else:
                # Unchanged observation: refresh last_checked in legacy links without status change or ws broadcast
                conn.execute(
                    """
                    UPDATE topology_links
                    SET last_checked = ?
                    WHERE (source_id = ? AND LOWER(source_port) = LOWER(?))
                       OR (target_id = ? AND LOWER(target_port) = LOWER(?))
                    """,
                    (now_ts, resolved_node_id, clean_iface, resolved_node_id, clean_iface),
                )

        return {
            "success": True,
            "device_id": resolved_node_id,
            "interface": clean_iface,
            "oper_status": norm_status,
            "edges_updated": updated_count,
            "_pending_events": pending_events,
        }

    def _process_device_status_event(
        self,
        payload: Dict[str, Any],
        event_id: Optional[str],
        event_time: float,
        conn: sqlite3.Connection,
    ) -> Dict[str, Any]:
        device_ref = payload.get("device_id") or payload.get("device") or payload.get("name") or payload.get("ip")
        if not device_ref:
            return {"success": False, "error": "missing_device_reference", "edges_updated": 0}

        status_raw = payload.get("status") or payload.get("state")
        if not status_raw:
            return {"success": False, "error": "missing_device_status", "edges_updated": 0}

        resolved_node_id = self._resolve_canonical_node_id(str(device_ref).strip(), conn)
        if not resolved_node_id:
            return {"success": False, "reason": "unknown_device", "edges_updated": 0}

        dev_status = str(status_raw).strip().upper()
        now_ts = event_time

        if dev_status == "DOWN":
            node_reach = "unreachable"
            node_status = "offline"
            edge_oper = "degraded"
        elif dev_status == "UP":
            node_reach = "reachable"
            node_status = "online"
            edge_oper = "up"
        elif dev_status == "SUSPECTED_DOWN":
            node_reach = "suspected_down"
            node_status = "warning"
            edge_oper = "degraded"
        elif dev_status == "DEGRADED":
            node_reach = "reachable"
            node_status = "warning"
            edge_oper = "degraded"
        else:
            node_reach = "unknown"
            node_status = "warning"
            edge_oper = "unknown"

        conn.execute(
            """
            UPDATE topology_nodes
            SET reachability_status = ?,
                status = ?,
                last_seen = ?
            WHERE id = ?
            """,
            (node_reach, node_status, now_ts, resolved_node_id),
        )

        edges_updated = 0
        if dev_status in ("DOWN", "UP"):
            edges = conn.execute(
                """
                SELECT * FROM topology_edges
                WHERE lifecycle_state != 'tombstoned'
                  AND (source_node_id = ? OR target_node_id = ?)
                """,
                (resolved_node_id, resolved_node_id),
            ).fetchall()

            for edge in edges:
                conn.execute(
                    """
                    UPDATE topology_edges
                    SET oper_status = ?,
                        last_seen = ?,
                        observation_freshness = 'fresh'
                    WHERE id = ?
                    """,
                    (edge_oper, now_ts, edge["id"]),
                )
                edges_updated += 1

        return {
            "success": True,
            "device_id": resolved_node_id,
            "device_status": dev_status,
            "node_reachability": node_reach,
            "edges_updated": edges_updated,
        }

    # -----------------------------------------------------------------------
    # In-Memory 60-Second Stale Observation Decayer
    # -----------------------------------------------------------------------

    def decay_stale_observations(
        self,
        now: Optional[float] = None,
        stale_threshold_sec: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """
        Marks operational edge observations as 'stale' when observation freshness threshold expires.
        Pure in-memory/DB scan:
        - NEVER tombstones or deletes an edge.
        - NEVER downgrades physical adjacency.
        - NEVER invents a link failure (oper_status is untouched).
        - Avoids unnecessary database writes (only touches fresh edges exceeding threshold).
        - Accepts injected deterministic 'now' and 'stale_threshold_sec' for testing.
        """
        threshold = (
            float(stale_threshold_sec)
            if stale_threshold_sec is not None
            else float(self._stale_threshold_sec)
        )
        current_ts = float(now) if now is not None else time.time()

        def _execute(c: sqlite3.Connection) -> int:
            cur = c.execute(
                """
                UPDATE topology_edges
                SET observation_freshness = 'stale'
                WHERE lifecycle_state != 'tombstoned'
                  AND observation_freshness = 'fresh'
                  AND verification_status != 'manual'
                  AND (? - last_seen) > ?
                """,
                (current_ts, threshold),
            )
            count = cur.rowcount
            if count > 0:
                logger.info(
                    "Topology Stale Decayer: marked %d edge(s) as 'stale' (age > %.1fs).",
                    count, threshold,
                )
            return count

        if conn is not None:
            return _execute(conn)
        with self._lock, closing(self._get_connection()) as auto_conn:
            res = _execute(auto_conn)
            auto_conn.commit()
            return res

    async def _decayer_loop(self) -> None:
        logger.info(
            "Topology Stale Decayer ticker started (interval=%.1fs, threshold=%.1fs).",
            self._decayer_interval_sec,
            self._stale_threshold_sec,
        )
        try:
            while not self._decayer_stop_event.is_set():
                start_mono = time.monotonic()
                try:
                    self.decay_stale_observations()
                except Exception as exc:
                    logger.error("Error during stale observation decay cycle: %s", exc)

                elapsed_mono = time.monotonic() - start_mono
                sleep_time = max(0.5, self._decayer_interval_sec - elapsed_mono)
                try:
                    await asyncio.wait_for(
                        self._decayer_stop_event.wait(),
                        timeout=sleep_time,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            with self._decayer_lock:
                self._decayer_task = None
            logger.info("Topology Stale Decayer ticker stopped.")

    def start_decayer(
        self,
        interval_sec: float = 60.0,
        stale_threshold_sec: float = 60.0,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> bool:
        """Starts the in-memory Stale Observation Decayer ticker. Idempotent."""
        with self._decayer_lock:
            if self._decayer_task is not None and not self._decayer_task.done():
                return True

            self._decayer_interval_sec = float(interval_sec)
            self._stale_threshold_sec = float(stale_threshold_sec)
            self._decayer_stop_event.clear()

            try:
                target_loop = loop
                if target_loop is None:
                    try:
                        target_loop = asyncio.get_running_loop()
                    except RuntimeError:
                        target_loop = asyncio.get_event_loop()
                self._decayer_task = target_loop.create_task(self._decayer_loop())
                return True
            except Exception as exc:
                logger.error("Failed to start Topology Stale Decayer task: %s", exc)
                return False

    def stop_decayer(self) -> bool:
        """Stops the in-memory Stale Observation Decayer ticker cleanly. Idempotent."""
        with self._decayer_lock:
            if self._decayer_task is None and self._decayer_stop_event.is_set():
                return False
            self._decayer_stop_event.set()
            task = self._decayer_task
            self._decayer_task = None

        if task and not task.done():
            task.cancel()
        return True

    def is_decayer_running(self) -> bool:
        with self._decayer_lock:
            return self._decayer_task is not None and not self._decayer_task.done()

    # -----------------------------------------------------------------------
    # EventBus Subscriber Registration Lifecycle
    # -----------------------------------------------------------------------

    def register_nms_subscriber(self, bus: Optional[EventBus] = None) -> bool:
        """
        Registers handle_nms_event as subscriber on the EventBus.
        Idempotent: guarantees handle_nms_event is registered exactly once per process.
        """
        with self._subscriber_lock:
            if self._subscriber_token is not None:
                return True

            target_bus = bus or event_bus
            self._target_bus = target_bus

            def _nms_callback(event: Event) -> None:
                try:
                    self.handle_nms_event(event)
                except Exception as exc:
                    logger.error("TopologyEngine handle_nms_event unhandled error: %s", exc, exc_info=True)

            token = target_bus.subscribe(
                EventNames.NMS_INTERFACE_STATUS_CHANGED,
                _nms_callback,
            )
            dev_token = target_bus.subscribe(
                EventNames.NMS_DEVICE_STATUS,
                _nms_callback,
            )
            obs_token = target_bus.subscribe(
                EventNames.NMS_INTERFACE_OBSERVED,
                _nms_callback,
            )
            self._subscriber_token = token
            self._dev_subscriber_token = dev_token
            self._obs_subscriber_token = obs_token
            logger.info("TopologyEngine registered NMS subscriber (tokens: %s, %s, %s)", token, dev_token, obs_token)
            return True

    def unregister_nms_subscriber(self) -> bool:
        """Unregisters the NMS event subscriber from EventBus. Idempotent."""
        with self._subscriber_lock:
            if self._subscriber_token is None and self._dev_subscriber_token is None and self._obs_subscriber_token is None:
                return False

            bus = self._target_bus or event_bus
            if self._subscriber_token:
                bus.unsubscribe(EventNames.NMS_INTERFACE_STATUS_CHANGED, self._subscriber_token)
                self._subscriber_token = None
            if self._dev_subscriber_token:
                bus.unsubscribe(EventNames.NMS_DEVICE_STATUS, self._dev_subscriber_token)
                self._dev_subscriber_token = None
            if self._obs_subscriber_token:
                bus.unsubscribe(EventNames.NMS_INTERFACE_OBSERVED, self._obs_subscriber_token)
                self._obs_subscriber_token = None
            logger.info("TopologyEngine unregistered NMS subscribers.")
            return True

    def is_subscriber_registered(self) -> bool:
        with self._subscriber_lock:
            return self._subscriber_token is not None

    def start_nms_sync(
        self,
        interval_sec: float = 60.0,
        stale_threshold_sec: float = 60.0,
        bus: Optional[EventBus] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> bool:
        """Starts both EventBus subscription and Stale Decayer. Idempotent."""
        sub_ok = self.register_nms_subscriber(bus=bus)
        dec_ok = self.start_decayer(interval_sec=interval_sec, stale_threshold_sec=stale_threshold_sec, loop=loop)
        return sub_ok and dec_ok

    def stop_nms_sync(self) -> bool:
        """Stops both EventBus subscription and Stale Decayer. Idempotent."""
        sub_ok = self.unregister_nms_subscriber()
        dec_ok = self.stop_decayer()
        return sub_ok or dec_ok

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
