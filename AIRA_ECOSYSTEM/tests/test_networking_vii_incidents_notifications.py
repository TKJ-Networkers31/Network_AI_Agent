"""
Tests for Networking VII Phase G (WP 7.6 & 7.7) — Proactive Incidents and Notifications.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
import pytest
import zoneinfo

from core.operations.incident_engine import ProactiveIncidentEngine
from core.operations.models import (
    IncidentSeverity,
    IncidentState,
    NotificationDeliveryStatus,
    PredictiveMetricProjection,
    PredictionStatus,
    ProactiveIncidentRecord,
    RiskLevel,
    TrendDirection,
)
from core.operations.notification_hub import NotificationHub


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_incidents.db"


@pytest.fixture
def incident_engine(temp_db_path: Path) -> ProactiveIncidentEngine:
    return ProactiveIncidentEngine(db_path=temp_db_path)


@pytest.fixture
def notif_hub(temp_db_path: Path) -> NotificationHub:
    return NotificationHub(db_path=temp_db_path, cooldown_sec=300)


def test_incident_lifecycle_state_machine(incident_engine: ProactiveIncidentEngine) -> None:
    """Verifies state machine transitions and rejects invalid state jumps."""
    inc = ProactiveIncidentRecord(
        incident_id="inc_lifecycle_001",
        title="Interface Saturation Expected",
        severity=IncidentSeverity.HIGH.value,
        state=IncidentState.DETECTED.value,
        source_engine="PREDICTIVE",
        affected_devices=["R-1"],
        summary="Utilization trend indicates breach in 12 hours.",
    )
    incident_engine.create_incident(inc)

    # 1. Valid transition: DETECTED -> ACKNOWLEDGED
    updated = incident_engine.transition_state("inc_lifecycle_001", IncidentState.ACKNOWLEDGED.value)
    assert updated.state == IncidentState.ACKNOWLEDGED.value

    # 2. Valid transition: ACKNOWLEDGED -> INVESTIGATING
    updated = incident_engine.transition_state("inc_lifecycle_001", IncidentState.INVESTIGATING.value)
    assert updated.state == IncidentState.INVESTIGATING.value

    # 3. Valid transition: INVESTIGATING -> RESOLVED
    updated = incident_engine.transition_state("inc_lifecycle_001", IncidentState.RESOLVED.value)
    assert updated.state == IncidentState.RESOLVED.value
    assert updated.resolved_at is not None

    # 4. Invalid transition: Cannot transition from RESOLVED to DETECTED
    with pytest.raises(ValueError) as exc:
        incident_engine.transition_state("inc_lifecycle_001", IncidentState.DETECTED.value)
    assert "Invalid state transition" in str(exc.value)


def test_auto_incident_creation_from_prediction(incident_engine: ProactiveIncidentEngine) -> None:
    """Verifies automatic incident creation from a critical predictive projection."""
    proj = PredictiveMetricProjection(
        metric_name="rx_utilization_percent",
        entity_type="interface",
        entity_id="sfp-sfpplus1",
        device_id="Core-1",
        current_value=91.0,
        sample_count=20,
        window="24h",
        trend_direction=TrendDirection.RAPID_INCREASE.value,
        slope_per_hour=3.5,
        slope_per_day=84.0,
        r_squared=0.92,
        p95_value=90.5,
        max_value=91.0,
        warning_threshold=80.0,
        critical_threshold=95.0,
        hours_to_warning=0.0,
        hours_to_critical=1.1,
        days_to_warning=0.0,
        days_to_critical=0.0,
        risk_level=RiskLevel.CRITICAL.value,
        status=PredictionStatus.VALID.value,
        confidence_score=0.88,
        confidence_level="HIGH",
        recommended_action="Reroute transit traffic to secondary carrier.",
    )

    inc = incident_engine.create_from_prediction(proj)
    assert inc is not None
    assert inc.severity == IncidentSeverity.CRITICAL.value
    assert inc.source_engine == "PREDICTIVE"
    assert "Core-1" in inc.affected_devices
    assert "Reroute transit traffic" in (inc.remediation_plan or "")


def test_notification_deduplication_cooldown(notif_hub: NotificationHub) -> None:
    """Verifies that duplicate alerts within cooldown window are suppressed."""
    now_utc = datetime(2026, 11, 4, 3, 0, 0, tzinfo=timezone.utc)  # 10:00 WIB (Daytime)

    # 1. First alert -> SENT
    n1 = notif_hub.dispatch_notification(
        category="CAPACITY",
        severity=IncidentSeverity.MEDIUM.value,
        title="High Bandwidth Alert",
        message="Interface ether1 > 75%",
        identifier="R-1:ether1",
        now_utc=now_utc,
    )
    assert n1.delivery_status == NotificationDeliveryStatus.SENT.value

    # 2. Second alert 1 minute later -> SUPPRESSED_COOLDOWN
    n2 = notif_hub.dispatch_notification(
        category="CAPACITY",
        severity=IncidentSeverity.MEDIUM.value,
        title="High Bandwidth Alert",
        message="Interface ether1 > 75%",
        identifier="R-1:ether1",
        now_utc=now_utc + timedelta(minutes=1),
    )
    assert n2.delivery_status == NotificationDeliveryStatus.SUPPRESSED_COOLDOWN.value

    # 3. Third alert after cooldown (10 minutes later) -> SENT
    n3 = notif_hub.dispatch_notification(
        category="CAPACITY",
        severity=IncidentSeverity.MEDIUM.value,
        title="High Bandwidth Alert",
        message="Interface ether1 > 75%",
        identifier="R-1:ether1",
        now_utc=now_utc + timedelta(minutes=10),
    )
    assert n3.delivery_status == NotificationDeliveryStatus.SENT.value


def test_quiet_hours_queueing_and_override(notif_hub: NotificationHub) -> None:
    """Verifies quiet hours (22:00 to 06:00 WIB): queues INFO/MEDIUM, overrides for CRITICAL."""
    # 23:30 WIB = 16:30 UTC
    night_utc = datetime(2026, 11, 4, 16, 30, 0, tzinfo=timezone.utc)
    assert notif_hub.is_in_quiet_hours(night_utc) is True

    # 1. INFO alert during quiet hours -> QUEUED_QUIET_HOURS
    n_info = notif_hub.dispatch_notification(
        category="ROUTING",
        severity=IncidentSeverity.INFO.value,
        title="BGP Route Table Refreshed",
        message="Prefix count updated",
        identifier="R-1:bgp",
        now_utc=night_utc,
    )
    assert n_info.delivery_status == NotificationDeliveryStatus.QUEUED_QUIET_HOURS.value

    # 2. CRITICAL alert during quiet hours -> SENT (Emergency Override)
    n_crit = notif_hub.dispatch_notification(
        category="HARDWARE",
        severity=IncidentSeverity.CRITICAL.value,
        title="Core Gateway Down",
        message="Core router unreachable across all protocols",
        identifier="Core-1:down",
        now_utc=night_utc,
    )
    assert n_crit.delivery_status == NotificationDeliveryStatus.SENT.value
