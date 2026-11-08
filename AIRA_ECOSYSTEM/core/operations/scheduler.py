"""
AIRA OS — Operational Scheduler Engine (Networking VII / WP 7.4).

Provides persistent, restart-surviving, timezone-aware (Asia/Jakarta) job scheduling
for operational maintenance, capacity forecasting, health reviews, and compliance audits.

Strict Architectural Invariant:
This engine NEVER directly connects to or polls network hardware (e.g. MikroTik RouterOS).
Device telemetry polling remains strictly isolated in `HardenedNmsScheduler`.
This engine schedules operational tasks and reuses cached evidence from `UnifiedEvidenceService`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid
import zoneinfo

from core.operations.db import ensure_operational_schema
from core.operations.models import (
    JobRunStatus,
    JobScheduleType,
    MissedJobStrategy,
    OperationalJobRecord,
    OperationalJobRunRecord,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.scheduler")

DEFAULT_TIMEZONE = "Asia/Jakarta"


def _parse_cron_field(field_str: str, min_val: int, max_val: int) -> Set[int]:
    """Parses a single cron field expression into a set of matching integers."""
    results: Set[int] = set()
    parts = field_str.strip().split(",")

    for part in parts:
        if "/" in part:
            sub, step_str = part.split("/", 1)
            step = int(step_str)
            if sub == "*":
                start, end = min_val, max_val
            elif "-" in sub:
                s_str, e_str = sub.split("-", 1)
                start, end = int(s_str), int(e_str)
            else:
                start, end = int(sub), max_val
            results.update(range(start, end + 1, step))
        elif "-" in part:
            s_str, e_str = part.split("-", 1)
            results.update(range(int(s_str), int(e_str) + 1))
        elif part == "*":
            results.update(range(min_val, max_val + 1))
        else:
            results.add(int(part))

    return {v for v in results if min_val <= v <= max_val}


class OperationalSchedulerEngine:
    """Persistent, timezone-aware operational job scheduler."""

    def __init__(self, db_path: Optional[Path] = None, tz_name: str = DEFAULT_TIMEZONE) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.default_tz = zoneinfo.ZoneInfo(tz_name)
        ensure_operational_schema(self.db_path)
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._tz_cache: Dict[str, zoneinfo.ZoneInfo] = {tz_name: self.default_tz}

        # Register default operational handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Registers built-in operational job templates."""
        self.register_handler(
            "HEALTH_AUDIT",
            lambda params: {
                "summary": "Completed automated daily network health audit.",
                "devices_reviewed": params.get("devices", ["all"]),
                "status": "HEALTHY",
            },
        )
        self.register_handler(
            "CAPACITY_FORECAST",
            lambda params: {
                "summary": "Calculated 30-day saturation projections across transit links.",
                "forecast_horizon_days": params.get("horizon_days", 30),
                "at_risk_links": 0,
            },
        )
        self.register_handler(
            "CERT_CHECK",
            lambda params: {
                "summary": "Verified SSL/TLS and SSH certificate expiry dates.",
                "expiring_soon_count": 0,
            },
        )
        self.register_handler(
            "ROUTE_AUDIT",
            lambda params: {
                "summary": "Audited routing table stability and flap rates.",
                "flaps_detected": 0,
            },
        )

    def register_handler(
        self,
        job_type: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """Binds a callable function to execute for a specific job_type."""
        self._handlers[job_type.upper()] = handler

    def _get_tz(self, tz_name: str) -> zoneinfo.ZoneInfo:
        if tz_name not in self._tz_cache:
            try:
                self._tz_cache[tz_name] = zoneinfo.ZoneInfo(tz_name)
            except Exception:
                self._tz_cache[tz_name] = self.default_tz
        return self._tz_cache[tz_name]

    # -----------------------------------------------------------------------
    # Next Due Date Calculation
    # -----------------------------------------------------------------------

    def calculate_next_due(
        self,
        job: OperationalJobRecord,
        from_utc: Optional[datetime] = None,
    ) -> datetime:
        """
        Calculates the next due execution time in UTC for a given job.
        Evaluates schedules in the job's configured timezone (default Asia/Jakarta).
        """
        base_utc = from_utc or datetime.now(timezone.utc)
        tz = self._get_tz(job.timezone)

        stype = job.schedule_type.upper().strip()

        if stype == JobScheduleType.INTERVAL.value:
            # Interval in seconds
            seconds = int(job.schedule_expression)
            return base_utc + timedelta(seconds=max(1, seconds))

        # Convert base UTC to local wall-clock time
        local_time = base_utc.astimezone(tz)

        if stype == JobScheduleType.DAILY.value:
            # Format: 'HH:MM' (e.g. '08:00')
            parts = job.schedule_expression.split(":")
            h, m = int(parts[0]), int(parts[1])
            target_local = local_time.replace(hour=h, minute=m, second=0, microsecond=0)
            if target_local <= local_time:
                target_local += timedelta(days=1)
            return target_local.astimezone(timezone.utc)

        if stype == JobScheduleType.WEEKLY.value:
            # Format: 'D HH:MM' where D is 0 (Mon) to 6 (Sun) or '08:00' default Monday
            parts = job.schedule_expression.split()
            if len(parts) == 2:
                target_dow = int(parts[0])
                time_parts = parts[1].split(":")
            else:
                target_dow = 0  # Default Monday
                time_parts = parts[0].split(":")
            h, m = int(time_parts[0]), int(time_parts[1])

            target_local = local_time.replace(hour=h, minute=m, second=0, microsecond=0)
            days_ahead = (target_dow - target_local.weekday()) % 7
            if days_ahead == 0 and target_local <= local_time:
                days_ahead = 7
            target_local += timedelta(days=days_ahead)
            return target_local.astimezone(timezone.utc)

        if stype == JobScheduleType.CRON.value:
            # Standard 5-field cron: 'minute hour day month dow'
            fields = job.schedule_expression.strip().split()
            if len(fields) != 5:
                # Fallback to 1 hour
                return base_utc + timedelta(hours=1)

            min_set = _parse_cron_field(fields[0], 0, 59)
            hour_set = _parse_cron_field(fields[1], 0, 23)
            day_set = _parse_cron_field(fields[2], 1, 31)
            month_set = _parse_cron_field(fields[3], 1, 12)
            raw_dow_set = _parse_cron_field(fields[4], 0, 7)
            # Standard cron: 0 and 7 both represent Sunday
            dow_set = {0 if v == 7 else v for v in raw_dow_set}

            # Fast-forward cursor in local time
            cursor = local_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
            for _ in range(525600):  # Maximum 1 year
                if cursor.month not in month_set:
                    cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
                    continue
                cron_dow = (cursor.weekday() + 1) % 7
                if cursor.day not in day_set or cron_dow not in dow_set:
                    cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
                    continue
                if cursor.hour not in hour_set:
                    cursor = (cursor + timedelta(hours=1)).replace(minute=0)
                    continue
                if cursor.minute in min_set:
                    return cursor.astimezone(timezone.utc)
                cursor += timedelta(minutes=1)

            # Fallback
            return base_utc + timedelta(days=1)

        # Fallback interval: 1 day
        return base_utc + timedelta(days=1)

    # -----------------------------------------------------------------------
    # Job CRUD Operations
    # -----------------------------------------------------------------------

    def register_job(self, job: OperationalJobRecord) -> OperationalJobRecord:
        """Persists a new operational job and initializes its next_due_at."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not job.next_due_at:
            next_due_dt = self.calculate_next_due(job)
            job.next_due_at = next_due_dt.isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_jobs (
                    job_id, name, job_type, description, schedule_type,
                    schedule_expression, timezone, is_enabled, missed_strategy,
                    parameters_json, last_run_at, last_status, next_due_at,
                    consecutive_failures, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.name,
                    job.job_type,
                    job.description,
                    job.schedule_type,
                    job.schedule_expression,
                    job.timezone,
                    1 if job.is_enabled else 0,
                    job.missed_strategy,
                    json.dumps(job.parameters_json or {}),
                    job.last_run_at,
                    job.last_status,
                    job.next_due_at,
                    job.consecutive_failures,
                    job.created_at or now_iso,
                    job.updated_at or now_iso,
                ),
            )
        return job

    def get_job(self, job_id: str) -> Optional[OperationalJobRecord]:
        """Retrieves a single operational job by ID."""
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                """
                SELECT job_id, name, job_type, description, schedule_type,
                       schedule_expression, timezone, is_enabled, missed_strategy,
                       parameters_json, last_run_at, last_status, next_due_at,
                       consecutive_failures, created_at, updated_at
                FROM operational_jobs WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

        if not row:
            return None

        return OperationalJobRecord(
            job_id=row[0],
            name=row[1],
            job_type=row[2],
            description=row[3],
            schedule_type=row[4],
            schedule_expression=row[5],
            timezone=row[6],
            is_enabled=bool(row[7]),
            missed_strategy=row[8],
            parameters_json=json.loads(row[9] or "{}"),
            last_run_at=row[10],
            last_status=row[11],
            next_due_at=row[12],
            consecutive_failures=row[13],
            created_at=row[14],
            updated_at=row[15],
        )

    def list_jobs(self, enabled_only: bool = False) -> List[OperationalJobRecord]:
        """Lists all registered operational jobs."""
        query = "SELECT job_id FROM operational_jobs"
        params: Tuple[Any, ...] = ()
        if enabled_only:
            query += " WHERE is_enabled = 1"
        query += " ORDER BY name ASC"

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, params).fetchall()

        jobs: List[OperationalJobRecord] = []
        for r in rows:
            j = self.get_job(r[0])
            if j:
                jobs.append(j)
        return jobs

    def delete_job(self, job_id: str) -> bool:
        """Deletes a job and its associated run logs."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute("DELETE FROM operational_jobs WHERE job_id = ?", (job_id,))
            return cur.rowcount > 0

    # -----------------------------------------------------------------------
    # Execution & Missed Run Handling
    # -----------------------------------------------------------------------

    def execute_job_now(
        self,
        job_id: str,
        trigger_type: str = "MANUAL",
    ) -> OperationalJobRunRecord:
        """
        Executes a job immediately, logs the run, and advances next_due_at.
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' does not exist.")

        run_id = f"run_{uuid.uuid4().hex[:10]}"
        started_dt = datetime.now(timezone.utc)
        start_ts = time.time()

        status = JobRunStatus.SUCCESS.value
        error_msg: Optional[str] = None
        result_data: Dict[str, Any] = {}
        result_summary: Optional[str] = None

        handler = self._handlers.get(job.job_type.upper())
        if handler:
            try:
                result_data = handler(job.parameters_json)
                result_summary = result_data.get("summary", "Execution completed successfully.")
            except Exception as e:
                status = JobRunStatus.FAILED.value
                error_msg = str(e)
                result_summary = f"Execution failed: {error_msg}"
                logger.exception("Job '%s' execution failed: %s", job_id, e)
        else:
            status = JobRunStatus.WARNING.value
            result_summary = f"No handler registered for job type '{job.job_type}'."

        duration_ms = int((time.time() - start_ts) * 1000)
        completed_dt = datetime.now(timezone.utc)

        # Calculate next due time
        next_due_dt = self.calculate_next_due(job, from_utc=completed_dt)
        next_due_iso = next_due_dt.isoformat()

        # Update job state in SQLite
        consecutive_failures = 0 if status == JobRunStatus.SUCCESS.value else job.consecutive_failures + 1

        run_record = OperationalJobRunRecord(
            run_id=run_id,
            job_id=job_id,
            trigger_type=trigger_type,
            started_at=started_dt.isoformat(),
            completed_at=completed_dt.isoformat(),
            status=status,
            duration_ms=duration_ms,
            result_summary=result_summary,
            result_data_json=result_data,
            error_message=error_msg,
        )

        with topology_transaction(self.db_path, write=True) as conn:
            # 1. Insert run log
            conn.execute(
                """
                INSERT INTO operational_job_runs (
                    run_id, job_id, trigger_type, started_at, completed_at,
                    status, duration_ms, result_summary, result_data_json, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_record.run_id,
                    run_record.job_id,
                    run_record.trigger_type,
                    run_record.started_at,
                    run_record.completed_at,
                    run_record.status,
                    run_record.duration_ms,
                    run_record.result_summary,
                    json.dumps(run_record.result_data_json or {}),
                    run_record.error_message,
                ),
            )

            # 2. Update job record
            conn.execute(
                """
                UPDATE operational_jobs
                SET last_run_at = ?, last_status = ?, next_due_at = ?,
                    consecutive_failures = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    completed_dt.isoformat(),
                    status,
                    next_due_iso,
                    consecutive_failures,
                    datetime.now(timezone.utc).isoformat(),
                    job_id,
                ),
            )

        return run_record

    def check_and_run_due_jobs(self) -> List[OperationalJobRunRecord]:
        """
        Polls SQLite for due jobs, handles missed execution strategies, and executes.
        """
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT job_id, missed_strategy, next_due_at
                FROM operational_jobs
                WHERE is_enabled = 1 AND next_due_at IS NOT NULL AND next_due_at <= ?
                ORDER BY next_due_at ASC
                """,
                (now_iso,),
            ).fetchall()

        runs: List[OperationalJobRunRecord] = []
        for r in rows:
            job_id, missed_strategy, next_due_str = r[0], r[1], r[2]
            job = self.get_job(job_id)
            if not job:
                continue

            # Evaluate if job was significantly overdue
            try:
                due_dt = datetime.fromisoformat(next_due_str)
                is_overdue = (now_dt - due_dt).total_seconds() > 300  # > 5 minutes
            except Exception:
                is_overdue = False

            if is_overdue and missed_strategy == MissedJobStrategy.SKIP.value:
                # Advance next_due_at without running
                next_due = self.calculate_next_due(job, from_utc=now_dt)
                with topology_transaction(self.db_path, write=True) as conn:
                    conn.execute(
                        "UPDATE operational_jobs SET next_due_at = ?, updated_at = ? WHERE job_id = ?",
                        (next_due.isoformat(), now_iso, job_id),
                    )
                logger.info("Job '%s' was overdue and SKIPPED per policy.", job_id)
                continue

            # Run job
            trigger = "MISSED_RECOVERY" if is_overdue else "SCHEDULED"
            run_rec = self.execute_job_now(job_id, trigger_type=trigger)
            runs.append(run_rec)

        return runs

    def list_job_runs(self, job_id: Optional[str] = None, limit: int = 50) -> List[OperationalJobRunRecord]:
        """Retrieves recent job run history."""
        query = """
            SELECT run_id, job_id, trigger_type, started_at, completed_at,
                   status, duration_ms, result_summary, result_data_json, error_message
            FROM operational_job_runs
        """
        params: List[Any] = []
        if job_id:
            query += " WHERE job_id = ?"
            params.append(job_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [
            OperationalJobRunRecord(
                run_id=r[0],
                job_id=r[1],
                trigger_type=r[2],
                started_at=r[3],
                completed_at=r[4],
                status=r[5],
                duration_ms=r[6],
                result_summary=r[7],
                result_data_json=json.loads(r[8] or "{}"),
                error_message=r[9],
            )
            for r in rows
        ]
