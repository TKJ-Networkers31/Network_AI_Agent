"""
Tests for Networking VII Phase F (WP 7.5) — External Calendar Integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from core.operations.calendar.manager import CalendarManager
from core.operations.calendar.local_provider import LocalCalendarProvider
from core.operations.calendar.google_provider import GoogleCalendarProvider
from core.operations.calendar.ics_provider import IcsCalendarProvider
from core.operations.models import MaintenanceWindowRecord


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_calendar.db"


@pytest.fixture
def local_prov(temp_db_path: Path) -> LocalCalendarProvider:
    return LocalCalendarProvider(db_path=temp_db_path)


@pytest.fixture
def cal_manager(local_prov: LocalCalendarProvider) -> CalendarManager:
    return CalendarManager(local_provider=local_prov)


def test_local_calendar_crud(cal_manager: CalendarManager) -> None:
    """Verifies complete CRUD operations for maintenance windows."""
    now_utc = datetime.now(timezone.utc)
    start_utc = (now_utc + timedelta(hours=2)).isoformat()
    end_utc = (now_utc + timedelta(hours=4)).isoformat()

    win = MaintenanceWindowRecord(
        window_id="win_maint_001",
        title="Core Router Firmware Upgrade",
        description="Upgrading RouterOS v7.14 to v7.15",
        source_provider="LOCAL",
        external_event_id=None,
        scope_type="DEVICE",
        target_entities=["Core-1"],
        start_time_utc=start_utc,
        end_time_utc=end_utc,
        start_time_local="",
        end_time_local="",
        status="SCHEDULED",
        suppress_alerts=True,
    )

    created = cal_manager.create_window(win)
    assert created.window_id == "win_maint_001"
    assert created.start_time_local != ""

    fetched = cal_manager.get_window("win_maint_001")
    assert fetched is not None
    assert fetched.title == "Core Router Firmware Upgrade"
    assert "Core-1" in fetched.target_entities

    all_wins = cal_manager.list_windows()
    assert len(all_wins) == 1

    deleted = cal_manager.delete_window("win_maint_001")
    assert deleted is True
    assert cal_manager.get_window("win_maint_001") is None


def test_realtime_alert_suppression(cal_manager: CalendarManager) -> None:
    """Verifies that an entity active in an ongoing maintenance window suppresses alerts."""
    now_utc = datetime.now(timezone.utc)
    # Active window spanning -1 hour to +1 hour
    active_start = (now_utc - timedelta(hours=1)).isoformat()
    active_end = (now_utc + timedelta(hours=1)).isoformat()

    win = MaintenanceWindowRecord(
        window_id="win_active_now",
        title="Active Emergency Fiber Splicing",
        description="Link down expected on ether1",
        source_provider="LOCAL",
        external_event_id=None,
        scope_type="DEVICE",
        target_entities=["CHR", "R-1"],
        start_time_utc=active_start,
        end_time_utc=active_end,
        start_time_local="",
        end_time_local="",
        status="ACTIVE",
        suppress_alerts=True,
    )
    cal_manager.create_window(win)

    # Test targeted devices
    assert cal_manager.is_entity_in_maintenance("CHR", now_dt=now_utc) is True
    assert cal_manager.is_entity_in_maintenance("R-1", now_dt=now_utc) is True

    # Test unaffected device
    assert cal_manager.is_entity_in_maintenance("Dist-Switch-1", now_dt=now_utc) is False


def test_rfc5545_ics_export_and_import(cal_manager: CalendarManager) -> None:
    """Verifies round-trip RFC 5545 iCalendar generation and parsing."""
    now_utc = datetime.now(timezone.utc)
    start_str = (now_utc + timedelta(days=1)).isoformat()
    end_str = (now_utc + timedelta(days=1, hours=2)).isoformat()

    win = MaintenanceWindowRecord(
        window_id="win_ics_test",
        title="Scheduled Core Maintenance",
        description="BGP peering reconfiguration",
        source_provider="LOCAL",
        external_event_id=None,
        scope_type="DEVICE",
        target_entities=["Core-1"],
        start_time_utc=start_str,
        end_time_utc=end_str,
        start_time_local="",
        end_time_local="",
        status="SCHEDULED",
        suppress_alerts=True,
    )
    cal_manager.create_window(win)

    # Export to .ics
    ics_text = cal_manager.export_ics()
    assert "BEGIN:VCALENDAR" in ics_text
    assert "BEGIN:VEVENT" in ics_text
    assert "SUMMARY:Scheduled Core Maintenance" in ics_text
    assert "UID:win_ics_test@aira-os" in ics_text
    assert "END:VCALENDAR" in ics_text

    # Import into another manager instance
    imported = cal_manager.import_ics(ics_text)
    assert len(imported) >= 1
    assert any(w.title == "Scheduled Core Maintenance" for w in imported)


def test_google_provider_offline_fallback(local_prov: LocalCalendarProvider) -> None:
    """Verifies Google provider gracefully falls back to local SQLite when unconfigured."""
    google_prov = GoogleCalendarProvider(local_fallback=local_prov)
    assert google_prov.is_configured is False

    windows = google_prov.list_windows()
    assert isinstance(windows, list)
