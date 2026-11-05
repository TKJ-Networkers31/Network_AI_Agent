"""
AIRA OS — Networking V WP 5.5 Test Suite
Topology-Aware Event, Alert & Health Engine Verification.
"""

import sqlite3
import time
from pathlib import Path
import pytest

from core.nms.alerts import (
    AlertEngine,
    AlertRule,
    AlertSeverity,
    AlertState,
    DEFAULT_ALERT_RULES,
)
from core.nms.models import (
    MetricSemanticType,
    MetricTaxonomy,
    SampleQuality,
    TelemetrySample,
)
from core.topology_db import init_topology_database


@pytest.fixture
def alert_db(tmp_path):
    db_file = tmp_path / "test_alerts.db"
    init_topology_database(db_file)
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topology_edges (
            edge_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            layer TEXT DEFAULT 'layer3',
            status TEXT DEFAULT 'active'
        );
        """
    )
    conn.commit()
    conn.close()
    return db_file


def test_01_alert_debouncing_consecutive_violations(alert_db):
    """Verify that alert requires N=3 consecutive violations before declaring ACTIVE."""
    engine = AlertEngine(db_path=alert_db)
    now = time.time()

    def make_sample(val):
        return TelemetrySample(
            device_id="dev_cpu",
            metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
            metric_value=val,
            unit="percent",
            semantic_type=MetricSemanticType.GAUGE.value,
            measured_at=now,
            collected_at=now,
        )

    # Sample 1: 90% CPU (trigger is 85%) -> DETECTED (no incident opened)
    act1 = engine.evaluate_sample(make_sample(90.0))
    tracker = engine.get_tracker("dev_cpu", MetricTaxonomy.DEVICE_CPU_UTILIZATION, severity=AlertSeverity.WARNING)
    assert tracker.consecutive_violations == 1
    assert tracker.current_state == AlertState.DETECTED
    assert act1 is None

    # Sample 2: 92% CPU -> DETECTED
    act2 = engine.evaluate_sample(make_sample(92.0))
    assert tracker.consecutive_violations == 2
    assert tracker.current_state == AlertState.DETECTED
    assert act2 is None

    # Sample 3: 88% CPU -> 3rd consecutive violation -> ACTIVE!
    act3 = engine.evaluate_sample(make_sample(88.0))
    assert tracker.consecutive_violations == 3
    assert tracker.current_state == AlertState.ACTIVE
    assert act3 is not None
    assert act3["action"] == "triggered"
    assert act3["severity"] == AlertSeverity.WARNING.value
    assert tracker.active_incident_id is not None

    # Verify incident persisted in SQLite
    conn = sqlite3.connect(alert_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nms_incidents WHERE id = ?", (tracker.active_incident_id,)).fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "open"
    assert row["device_id"] == "dev_cpu"


def test_02_hysteresis_clear_deadband(alert_db):
    """Verify that alert clears only when value drops below clear threshold with M=2 samples."""
    engine = AlertEngine(db_path=alert_db)
    now = time.time()

    def make_sample(val):
        return TelemetrySample(
            device_id="dev_hyst",
            metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
            metric_value=val,
            unit="percent",
            measured_at=now,
            collected_at=now,
        )

    # Trigger active alert (3 samples at 90%)
    for _ in range(3):
        engine.evaluate_sample(make_sample(90.0))
    tracker = engine.get_tracker("dev_hyst", MetricTaxonomy.DEVICE_CPU_UTILIZATION, severity=AlertSeverity.WARNING)
    assert tracker.current_state == AlertState.ACTIVE
    inc_id = tracker.active_incident_id

    # Value drops to 80% (between trigger 85% and clear 75% deadband): remains ACTIVE
    engine.evaluate_sample(make_sample(80.0))
    assert tracker.current_state == AlertState.ACTIVE

    # Value drops to 70% (<= 75% clear threshold): 1st recovery sample
    engine.evaluate_sample(make_sample(70.0))
    assert tracker.consecutive_normal == 1
    assert tracker.current_state == AlertState.ACTIVE

    # Value drops to 70%: 2nd recovery sample (M=2) -> RESOLVED!
    act_clear = engine.evaluate_sample(make_sample(70.0))
    assert tracker.consecutive_normal == 2
    assert tracker.current_state == AlertState.RESOLVED
    assert act_clear is not None
    assert act_clear["action"] == "resolved"

    conn = sqlite3.connect(alert_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nms_incidents WHERE id = ?", (inc_id,)).fetchone()
    conn.close()
    assert row["status"] == "resolved"
    assert row["resolved_at"] is not None


def test_03_upstream_root_cause_suppression(alert_db):
    """Verify downstream alarm suppression when upstream parent node is DOWN."""
    engine = AlertEngine(db_path=alert_db)

    conn = sqlite3.connect(alert_db)
    # Define edge: Core_Router -> Access_Switch
    conn.execute(
        "INSERT INTO topology_edges (edge_id, source, target) VALUES ('e1', 'Core_Router', 'Access_Switch');"
    )
    # Define active CRITICAL incident on Core_Router
    conn.execute(
        """
        INSERT INTO nms_incidents (id, device_id, incident_type, severity, title, status, started_at)
        VALUES (101, 'Core_Router', 'aira.nms.device.availability', 'CRITICAL', 'Core Router Down', 'open', ?);
        """,
        (time.time(),),
    )
    conn.commit()
    conn.close()

    now = time.time()

    def make_down_sample(dev):
        return TelemetrySample(
            device_id=dev,
            metric_name=MetricTaxonomy.DEVICE_AVAILABILITY,
            metric_value=0.0,
            unit="state",
            measured_at=now,
            collected_at=now,
        )

    # 3 consecutive drops on Access_Switch
    for _ in range(2):
        engine.evaluate_sample(make_down_sample("Access_Switch"))
    act = engine.evaluate_sample(make_down_sample("Access_Switch"))

    assert act is not None
    assert act["action"] == "suppressed"
    assert act["parent_incident_id"] == 101

    tracker = engine.get_tracker("Access_Switch", MetricTaxonomy.DEVICE_AVAILABILITY)
    assert tracker.current_state == AlertState.SUPPRESSED
    assert tracker.parent_incident_id == 101

    # Check child incident record in database
    conn = sqlite3.connect(alert_db)
    conn.row_factory = sqlite3.Row
    child_inc = conn.execute(
        "SELECT * FROM nms_incidents WHERE device_id = 'Access_Switch'"
    ).fetchone()
    parent_inc = conn.execute(
        "SELECT * FROM nms_incidents WHERE id = 101"
    ).fetchone()
    conn.close()

    assert child_inc is not None
    assert child_inc["status"] == "suppressed"
    assert child_inc["parent_incident_id"] == 101
    assert child_inc["suppression_reason"] == "SUPPRESSED_DOWNSTREAM_UNREACHABLE"
    assert parent_inc["affected_downstream_count"] == 1


def test_04_operator_acknowledgment(alert_db):
    """Verify operator alert acknowledgment lifecycle transition."""
    engine = AlertEngine(db_path=alert_db)
    inc_id = engine._record_incident(
        device_id="dev_ack",
        incident_type="test_alert",
        severity=AlertSeverity.MAJOR.value,
        title="Test Alert",
        details="Details",
        status="open",
    )

    ok = engine.acknowledge_incident(inc_id, user="lead_neteng")
    assert ok is True

    conn = sqlite3.connect(alert_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM nms_incidents WHERE id = ?", (inc_id,)).fetchone()
    conn.close()

    assert row["status"] == "acknowledged"
    assert row["acknowledged_by"] == "lead_neteng"
    assert row["acknowledged_at"] is not None


def test_05_interface_saturation_alert(alert_db):
    """Verify interface utilization alert with interface-specific keying."""
    engine = AlertEngine(db_path=alert_db)
    now = time.time()

    def make_iface_sample(util):
        return TelemetrySample(
            device_id="dev_sw1",
            metric_name=MetricTaxonomy.INTERFACE_RX_UTILIZATION,
            metric_value=util,
            unit="percent",
            interface_name="sfp-sfpplus1",
            measured_at=now,
            collected_at=now,
        )

    # 3 consecutive violations at 95%
    for _ in range(2):
        engine.evaluate_sample(make_iface_sample(95.0))
    act = engine.evaluate_sample(make_iface_sample(95.0))

    assert act is not None
    assert act["action"] == "triggered"
    assert act["severity"] == AlertSeverity.MAJOR.value

    tracker = engine.get_tracker("dev_sw1", MetricTaxonomy.INTERFACE_RX_UTILIZATION, "sfp-sfpplus1", severity=AlertSeverity.MAJOR)
    assert tracker.current_state == AlertState.ACTIVE
