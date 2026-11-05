"""
Tests for Networking VII Phase E (WP 7.4) — Operational Scheduler Engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
import zoneinfo

from core.operations.models import (
    JobRunStatus,
    JobScheduleType,
    MissedJobStrategy,
    OperationalJobRecord,
)
from core.operations.scheduler import OperationalSchedulerEngine


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_scheduler.db"


@pytest.fixture
def scheduler(temp_db_path: Path) -> OperationalSchedulerEngine:
    return OperationalSchedulerEngine(db_path=temp_db_path)


def test_job_registration_and_persistence(scheduler: OperationalSchedulerEngine) -> None:
    """Verifies that an operational job is persisted to SQLite and can survive reloads."""
    job = OperationalJobRecord(
        job_id="job_daily_audit",
        name="Daily Health Audit",
        job_type="HEALTH_AUDIT",
        description="Daily operational review of all devices",
        schedule_type=JobScheduleType.INTERVAL.value,
        schedule_expression="3600",
        timezone="Asia/Jakarta",
    )

    registered = scheduler.register_job(job)
    assert registered.next_due_at is not None

    fetched = scheduler.get_job("job_daily_audit")
    assert fetched is not None
    assert fetched.name == "Daily Health Audit"
    assert fetched.schedule_type == JobScheduleType.INTERVAL.value
    assert fetched.is_enabled is True

    jobs = scheduler.list_jobs()
    assert len(jobs) == 1


def test_timezone_aware_daily_schedule(scheduler: OperationalSchedulerEngine) -> None:
    """Verifies that 08:00 Asia/Jakarta (WIB) correctly translates to 01:00 UTC."""
    # Fixed base time: 2026-11-04 00:00:00 UTC (= 07:00:00 WIB)
    base_utc = datetime(2026, 11, 4, 0, 0, 0, tzinfo=timezone.utc)

    job = OperationalJobRecord(
        job_id="job_daily_0800",
        name="Morning Review",
        job_type="HEALTH_AUDIT",
        description="Run at 08:00 WIB",
        schedule_type=JobScheduleType.DAILY.value,
        schedule_expression="08:00",
        timezone="Asia/Jakarta",
    )

    next_due_dt = scheduler.calculate_next_due(job, from_utc=base_utc)

    # 08:00 WIB on 2026-11-04 is 01:00:00 UTC on 2026-11-04
    assert next_due_dt.year == 2026
    assert next_due_dt.month == 11
    assert next_due_dt.day == 4
    assert next_due_dt.hour == 1
    assert next_due_dt.minute == 0

    # Verify timezone conversion to WIB
    tz = zoneinfo.ZoneInfo("Asia/Jakarta")
    local_dt = next_due_dt.astimezone(tz)
    assert local_dt.hour == 8
    assert local_dt.minute == 0


def test_manual_job_execution_logs_run(scheduler: OperationalSchedulerEngine) -> None:
    """Verifies that running a job executes handler and logs a run record."""
    job = OperationalJobRecord(
        job_id="job_cap_forecast",
        name="Capacity Forecast",
        job_type="CAPACITY_FORECAST",
        description="Forecast saturation",
        schedule_type=JobScheduleType.INTERVAL.value,
        schedule_expression="86400",
        parameters_json={"horizon_days": 14},
    )
    scheduler.register_job(job)

    run_record = scheduler.execute_job_now("job_cap_forecast", trigger_type="MANUAL")

    assert run_record.status == JobRunStatus.SUCCESS.value
    assert run_record.trigger_type == "MANUAL"
    assert run_record.duration_ms is not None
    assert "saturation projections" in (run_record.result_summary or "")

    runs = scheduler.list_job_runs(job_id="job_cap_forecast")
    assert len(runs) == 1
    assert runs[0].run_id == run_record.run_id

    # Verify job record updated
    updated_job = scheduler.get_job("job_cap_forecast")
    assert updated_job is not None
    assert updated_job.last_status == JobRunStatus.SUCCESS.value
    assert updated_job.last_run_at is not None


def test_due_job_execution_and_missed_recovery(scheduler: OperationalSchedulerEngine) -> None:
    """Verifies check_and_run_due_jobs() runs overdue jobs with MISSED_RECOVERY trigger."""
    # Past time (20 minutes ago)
    past_due = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()

    job = OperationalJobRecord(
        job_id="job_overdue",
        name="Overdue Audit",
        job_type="ROUTE_AUDIT",
        description="Overdue job to recover",
        schedule_type=JobScheduleType.INTERVAL.value,
        schedule_expression="3600",
        next_due_at=past_due,
        missed_strategy=MissedJobStrategy.RUN_IMMEDIATELY.value,
    )
    scheduler.register_job(job)

    runs = scheduler.check_and_run_due_jobs()
    assert len(runs) == 1
    assert runs[0].trigger_type == "MISSED_RECOVERY"
    assert runs[0].status == JobRunStatus.SUCCESS.value


def test_missed_job_skip_policy(scheduler: OperationalSchedulerEngine) -> None:
    """Verifies that an overdue job configured with SKIP advances without executing."""
    past_due = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    job = OperationalJobRecord(
        job_id="job_skip_test",
        name="Skippable Job",
        job_type="CERT_CHECK",
        description="Test skip strategy",
        schedule_type=JobScheduleType.INTERVAL.value,
        schedule_expression="3600",
        next_due_at=past_due,
        missed_strategy=MissedJobStrategy.SKIP.value,
    )
    scheduler.register_job(job)

    runs = scheduler.check_and_run_due_jobs()
    assert len(runs) == 0  # Was skipped, not run

    updated = scheduler.get_job("job_skip_test")
    assert updated is not None
    # Next due time must have advanced into the future
    assert updated.next_due_at > datetime.now(timezone.utc).isoformat()
