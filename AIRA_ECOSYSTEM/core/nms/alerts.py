"""
AIRA OS — Networking V Topology-Aware Event, Alert & Health Engine (WP 5.5).

Implements:
1. Alert Lifecycle FSM: DETECTED -> ACTIVE / SUPPRESSED -> ACKNOWLEDGED -> RESOLVED.
2. Anti-flapping hysteresis with debouncing (N=3 consecutive violations to trigger, M=2 healthy to clear).
3. Upstream root-cause analysis (RCA): suppresses downstream cascade alarms when upstream parent is DOWN.
4. Automatic forensic route snapshot pinning during CRITICAL incidents.
5. Strict separation between network faults and agent collection failures.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.nms.models import (
    MetricSemanticType,
    MetricTaxonomy,
    SampleQuality,
    TelemetrySample,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    get_topology_connection,
    topology_transaction,
)

logger = logging.getLogger("aira.nms.alerts")


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # Red: Complete outage, unreachable device, core link down
    MAJOR = "MAJOR"        # Orange: CPU > 90%, utilization > 90%, packet loss > 15%
    WARNING = "WARNING"    # Yellow: High CPU/RAM/temperature, link utilization > 75%
    INFO = "INFO"          # Blue/Slate: Admin changes, reboot, recovery confirmations


class AlertState(str, Enum):
    DETECTED = "DETECTED"
    ACTIVE = "ACTIVE"
    SUPPRESSED = "SUPPRESSED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


@dataclass
class AlertRule:
    """Threshold rule definition with hysteresis deadband and debouncing."""
    metric_name: str
    threshold_trigger: float
    threshold_clear: float
    severity: AlertSeverity
    consecutive_trigger_required: int = 3   # N = 3
    consecutive_clear_required: int = 2     # M = 2
    comparison_op: str = ">="              # ">=", "<=", "=="
    title_template: str = ""
    description_template: str = ""

    def is_violation(self, value: float) -> bool:
        if self.comparison_op == ">=":
            return value >= self.threshold_trigger
        elif self.comparison_op == "<=":
            return value <= self.threshold_trigger
        elif self.comparison_op == "==":
            return value == self.threshold_trigger
        return False

    def is_clear(self, value: float) -> bool:
        if self.comparison_op == ">=":
            return value <= self.threshold_clear
        elif self.comparison_op == "<=":
            return value >= self.threshold_clear
        elif self.comparison_op == "==":
            return value != self.threshold_trigger
        return False


# Default canonical alert rules for AIRA OS NMS
DEFAULT_ALERT_RULES: List[AlertRule] = [
    # Device Availability (0 = Down)
    AlertRule(
        metric_name=MetricTaxonomy.DEVICE_AVAILABILITY,
        threshold_trigger=0.0,
        threshold_clear=1.0,
        severity=AlertSeverity.CRITICAL,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op="==",
        title_template="Device {device_id} Unreachable",
        description_template="Device {device_id} failed ICMP availability probe across 3 consecutive cycles.",
    ),
    # High Packet Loss (>= 15% trigger, <= 5% clear)
    AlertRule(
        metric_name=MetricTaxonomy.DEVICE_PACKET_LOSS_PCT,
        threshold_trigger=15.0,
        threshold_clear=5.0,
        severity=AlertSeverity.MAJOR,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op=">=",
        title_template="High Packet Loss on {device_id}",
        description_template="Packet loss elevated to {value}% on {device_id}.",
    ),
    # High CPU Utilization (>= 85% trigger, <= 75% clear: 10% deadband margin)
    AlertRule(
        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
        threshold_trigger=85.0,
        threshold_clear=75.0,
        severity=AlertSeverity.WARNING,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op=">=",
        title_template="High CPU Utilization on {device_id}",
        description_template="Processor load reached {value}% on {device_id}.",
    ),
    # Critical CPU Utilization (>= 95% trigger, <= 85% clear)
    AlertRule(
        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
        threshold_trigger=95.0,
        threshold_clear=85.0,
        severity=AlertSeverity.MAJOR,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op=">=",
        title_template="Critical CPU Saturation on {device_id}",
        description_template="Processor load reached {value}% on {device_id}.",
    ),
    # Interface Link Saturation (>= 90% trigger, <= 80% clear)
    AlertRule(
        metric_name=MetricTaxonomy.INTERFACE_RX_UTILIZATION,
        threshold_trigger=90.0,
        threshold_clear=80.0,
        severity=AlertSeverity.MAJOR,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op=">=",
        title_template="Interface {interface_name} Inbound Saturated on {device_id}",
        description_template="Inbound link saturation reached {value}% on interface {interface_name}.",
    ),
    AlertRule(
        metric_name=MetricTaxonomy.INTERFACE_TX_UTILIZATION,
        threshold_trigger=90.0,
        threshold_clear=80.0,
        severity=AlertSeverity.MAJOR,
        consecutive_trigger_required=3,
        consecutive_clear_required=2,
        comparison_op=">=",
        title_template="Interface {interface_name} Outbound Saturated on {device_id}",
        description_template="Outbound link saturation reached {value}% on interface {interface_name}.",
    ),
]


@dataclass
class DebounceTracker:
    """State tracking for a single (device_id, metric_name, interface_name) evaluation key."""
    consecutive_violations: int = 0
    consecutive_normal: int = 0
    current_state: AlertState = AlertState.RESOLVED
    active_incident_id: Optional[int] = None
    parent_incident_id: Optional[int] = None
    suppression_reason: Optional[str] = None
    last_evaluated_at: float = 0.0
    last_value: Optional[float] = None


class AlertEngine:
    """
    Topology-aware alert evaluator managing debounce counters, root-cause
    correlation, and incident life cycle updates.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        rules: Optional[Sequence[AlertRule]] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH
        self.rules: List[AlertRule] = list(rules) if rules is not None else list(DEFAULT_ALERT_RULES)
        self._trackers: Dict[Tuple[str, str, Optional[str]], DebounceTracker] = {}
        self._ensure_incident_schema()

    def _ensure_incident_schema(self) -> None:
        """Migrates nms_incidents table non-destructively to support RCA and forensic snapshot links."""
        try:
            with topology_transaction(self.db_path, write=True) as conn:
                conn.execute(
                    """
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
                    """
                )
                # Check for WP 5.5 extended columns
                existing_cols = [
                    r["name"] for r in conn.execute("PRAGMA table_info(nms_incidents)").fetchall()
                ]
                if "parent_incident_id" not in existing_cols:
                    conn.execute("ALTER TABLE nms_incidents ADD COLUMN parent_incident_id INTEGER DEFAULT NULL;")
                if "suppression_reason" not in existing_cols:
                    conn.execute("ALTER TABLE nms_incidents ADD COLUMN suppression_reason TEXT DEFAULT NULL;")
                if "route_snapshot_id" not in existing_cols:
                    conn.execute("ALTER TABLE nms_incidents ADD COLUMN route_snapshot_id TEXT DEFAULT NULL;")
                if "affected_downstream_count" not in existing_cols:
                    conn.execute("ALTER TABLE nms_incidents ADD COLUMN affected_downstream_count INTEGER DEFAULT 0;")
        except Exception as exc:
            logger.warning("Could not migrate nms_incidents schema: %s", exc)

    def get_tracker(
        self, device_id: str, metric_name: str, interface_name: Optional[str] = None, severity: Optional[AlertSeverity] = None
    ) -> DebounceTracker:
        if severity is not None:
            key = (device_id, metric_name, interface_name, severity.value)
            if key not in self._trackers:
                self._trackers[key] = DebounceTracker()
            return self._trackers[key]

        # If severity is None, look for any existing tracker with matching prefix
        for (d, m, i, s), tr in self._trackers.items():
            if d == device_id and m == metric_name and i == interface_name:
                return tr

        # Fallback to default
        key = (device_id, metric_name, interface_name, "default")
        if key not in self._trackers:
            self._trackers[key] = DebounceTracker()
        return self._trackers[key]

    def evaluate_sample(self, sample: TelemetrySample) -> Optional[Dict[str, Any]]:
        """
        Evaluates a single TelemetrySample against registered alert rules.
        Handles threshold breaches, debouncing, upstream RCA, and resolution.
        """
        if sample.metric_value is None:
            return None

        val = float(sample.metric_value)
        action_taken: Optional[Dict[str, Any]] = None

        for rule in self.rules:
            if rule.metric_name != sample.metric_name:
                continue

            tracker = self.get_tracker(sample.device_id, sample.metric_name, sample.interface_name, rule.severity)
            tracker.last_evaluated_at = sample.measured_at
            tracker.last_value = val

            # Check for violation
            if rule.is_violation(val):
                tracker.consecutive_violations += 1
                tracker.consecutive_normal = 0

                if tracker.consecutive_violations >= rule.consecutive_trigger_required:
                    # Threshold debounced and confirmed!
                    if tracker.current_state in (AlertState.RESOLVED, AlertState.DETECTED):
                        # Perform Upstream Root-Cause Analysis (RCA)
                        parent_id = None
                        suppressed = False
                        if sample.metric_name == MetricTaxonomy.DEVICE_AVAILABILITY and val == 0.0:
                            parent_id = self.check_upstream_failure(sample.device_id)
                            if parent_id is not None:
                                suppressed = True

                        if suppressed:
                            tracker.current_state = AlertState.SUPPRESSED
                            tracker.parent_incident_id = parent_id
                            tracker.suppression_reason = "SUPPRESSED_DOWNSTREAM_UNREACHABLE"
                            inc_id = self._record_incident(
                                device_id=sample.device_id,
                                incident_type="device_unreachable_downstream",
                                severity=AlertSeverity.INFO.value,
                                title=f"Downstream Reachability Loss: {sample.device_id}",
                                details=f"Suppressed due to upstream root cause incident #{parent_id}.",
                                status="suppressed",
                                parent_incident_id=parent_id,
                                suppression_reason="SUPPRESSED_DOWNSTREAM_UNREACHABLE",
                            )
                            tracker.active_incident_id = inc_id
                            action_taken = {
                                "action": "suppressed",
                                "incident_id": inc_id,
                                "parent_incident_id": parent_id,
                                "state": tracker.current_state.value,
                            }
                        else:
                            # Declare ACTIVE incident
                            tracker.current_state = AlertState.ACTIVE
                            title = rule.title_template.format(
                                device_id=sample.device_id,
                                interface_name=sample.interface_name or "",
                                value=val,
                            )
                            details = rule.description_template.format(
                                device_id=sample.device_id,
                                interface_name=sample.interface_name or "",
                                value=val,
                            )
                            inc_id = self._record_incident(
                                device_id=sample.device_id,
                                incident_type=rule.metric_name,
                                severity=rule.severity.value,
                                title=title,
                                details=details,
                                status="open",
                            )
                            tracker.active_incident_id = inc_id

                            # Forensic Route Snapshot Pinning for CRITICAL incidents
                            snapshot_id = None
                            if rule.severity == AlertSeverity.CRITICAL:
                                snapshot_id = self._pin_forensic_route_snapshot(sample.device_id, inc_id)

                            action_taken = {
                                "action": "triggered",
                                "incident_id": inc_id,
                                "severity": rule.severity.value,
                                "state": tracker.current_state.value,
                                "route_snapshot_id": snapshot_id,
                            }
                elif tracker.current_state == AlertState.RESOLVED:
                    tracker.current_state = AlertState.DETECTED

            # Check for recovery / clear
            elif rule.is_clear(val):
                tracker.consecutive_normal += 1
                tracker.consecutive_violations = 0

                if tracker.consecutive_normal >= rule.consecutive_clear_required:
                    if tracker.current_state in (AlertState.ACTIVE, AlertState.SUPPRESSED, AlertState.ACKNOWLEDGED):
                        inc_id = tracker.active_incident_id
                        if inc_id:
                            self._resolve_incident(
                                inc_id,
                                recovery_details=f"Metric {sample.metric_name} returned within hysteresis threshold ({val}).",
                            )
                        tracker.current_state = AlertState.RESOLVED
                        tracker.active_incident_id = None
                        tracker.parent_incident_id = None
                        action_taken = {
                            "action": "resolved",
                            "incident_id": inc_id,
                            "state": AlertState.RESOLVED.value,
                        }

        return action_taken

    def check_upstream_failure(self, device_id: str) -> Optional[int]:
        """
        Inspects topology links/edges to identify whether an upstream parent
        router or switch is currently DOWN with an open incident.
        """
        conn = get_topology_connection(self.db_path, read_only=True)
        try:
            # Query edges where device is connected
            edges = conn.execute(
                """
                SELECT source, target FROM topology_edges 
                WHERE source = ? OR target = ?;
                """,
                (device_id, device_id),
            ).fetchall()

            for edge in edges:
                peer_id = edge["target"] if edge["source"] == device_id else edge["source"]
                # Check if peer has an open or acknowledged critical incident
                inc = conn.execute(
                    """
                    SELECT id FROM nms_incidents 
                    WHERE device_id = ? AND status IN ('open', 'acknowledged') AND severity = 'CRITICAL'
                    ORDER BY started_at DESC LIMIT 1;
                    """,
                    (peer_id,),
                ).fetchone()
                if inc:
                    return inc["id"]
            return None
        except Exception as exc:
            logger.debug("Upstream RCA lookup failed: %s", exc)
            return None
        finally:
            conn.close()

    def _record_incident(
        self,
        device_id: str,
        incident_type: str,
        severity: str,
        title: str,
        details: str,
        status: str = "open",
        parent_incident_id: Optional[int] = None,
        suppression_reason: Optional[str] = None,
    ) -> int:
        """Atomically inserts or updates an incident in nms_incidents."""
        now = time.time()
        with topology_transaction(self.db_path, write=True) as conn:
            # Check if matching open incident already exists
            existing = conn.execute(
                """
                SELECT id FROM nms_incidents 
                WHERE device_id = ? AND incident_type = ? AND status IN ('open', 'suppressed', 'acknowledged');
                """,
                (device_id, incident_type),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE nms_incidents 
                    SET details = ?, severity = ?, status = ?
                    WHERE id = ?;
                    """,
                    (details, severity, status, existing["id"]),
                )
                return existing["id"]

            cur = conn.execute(
                """
                INSERT INTO nms_incidents (
                    device_id, incident_type, severity, title, details,
                    status, started_at, parent_incident_id, suppression_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    device_id,
                    incident_type,
                    severity,
                    title,
                    details,
                    status,
                    now,
                    parent_incident_id,
                    suppression_reason,
                ),
            )
            inc_id = cur.lastrowid

            # If this is a child suppressed incident, increment parent's downstream count
            if parent_incident_id:
                conn.execute(
                    """
                    UPDATE nms_incidents 
                    SET affected_downstream_count = coalesce(affected_downstream_count, 0) + 1
                    WHERE id = ?;
                    """,
                    (parent_incident_id,),
                )
            return inc_id

    def _resolve_incident(self, incident_id: int, recovery_details: str) -> bool:
        """Marks an active incident as resolved."""
        now = time.time()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE nms_incidents 
                SET status = 'resolved', resolved_at = ?, details = details || '\n[RECOVERED]: ' || ?
                WHERE id = ?;
                """,
                (now, recovery_details, incident_id),
            )
            return True

    def acknowledge_incident(self, incident_id: int, user: str = "operator") -> bool:
        """Operator acknowledgment transition."""
        now = time.time()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE nms_incidents 
                SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?;
                """,
                (now, user, incident_id),
            )
            return True

    def _pin_forensic_route_snapshot(self, device_id: str, incident_id: int) -> Optional[str]:
        """
        Pins forensic route snapshot evidence when a CRITICAL incident is raised.
        Attaches the snapshot_id to the incident record.
        """
        try:
            from core.routing.route_history import get_route_history_store
            store = get_route_history_store(self.db_path)
            # Find most recent snapshot or record reference
            snaps = store.list_snapshots(device_id=device_id, limit=1)
            if snaps:
                snap_id = snaps[0].snapshot_id
                with topology_transaction(self.db_path, write=True) as conn:
                    conn.execute(
                        "UPDATE nms_incidents SET route_snapshot_id = ? WHERE id = ?;",
                        (snap_id, incident_id),
                    )
                return snap_id
        except Exception as exc:
            logger.debug("Could not pin forensic route snapshot: %s", exc)
        return None
