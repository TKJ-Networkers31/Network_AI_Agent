"""
AIRA OS — Local SQLite Calendar Provider (Networking VII / WP 7.5).

Persists and manages maintenance windows locally in SQLite.
Guarantees 100% offline capability with zero external cloud dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, List, Optional
import zoneinfo

from core.operations.calendar.base import CalendarProvider
from core.operations.db import ensure_operational_schema
from core.operations.models import MaintenanceWindowRecord
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.calendar.local")


class LocalCalendarProvider(CalendarProvider):
    """Local SQLite-backed maintenance window calendar provider."""

    def __init__(self, db_path: Optional[Path] = None, default_tz: str = "Asia/Jakarta") -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.default_tz = zoneinfo.ZoneInfo(default_tz)
        ensure_operational_schema(self.db_path)

    def list_windows(
        self,
        start_utc: Optional[datetime] = None,
        end_utc: Optional[datetime] = None,
    ) -> List[MaintenanceWindowRecord]:
        """Lists maintenance windows, optionally filtered by UTC timeframe."""
        query = """
            SELECT window_id, title, description, source_provider, external_event_id,
                   scope_type, target_entities_json, start_time_utc, end_time_utc,
                   start_time_local, end_time_local, status, suppress_alerts,
                   created_at, updated_at
            FROM operational_maintenance_windows
        """
        conditions = []
        params = []

        if start_utc:
            conditions.append("end_time_utc >= ?")
            params.append(start_utc.isoformat())
        if end_utc:
            conditions.append("start_time_utc <= ?")
            params.append(end_utc.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY start_time_utc ASC"

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        windows: List[MaintenanceWindowRecord] = []
        for r in rows:
            windows.append(
                MaintenanceWindowRecord(
                    window_id=r[0],
                    title=r[1],
                    description=r[2],
                    source_provider=r[3],
                    external_event_id=r[4],
                    scope_type=r[5],
                    target_entities=json.loads(r[6] or "[]"),
                    start_time_utc=r[7],
                    end_time_utc=r[8],
                    start_time_local=r[9],
                    end_time_local=r[10],
                    status=r[11],
                    suppress_alerts=bool(r[12]),
                    created_at=r[13],
                    updated_at=r[14],
                )
            )
        return windows

    def get_window(self, window_id: str) -> Optional[MaintenanceWindowRecord]:
        """Retrieves a single maintenance window by ID."""
        with topology_transaction(self.db_path, write=False) as conn:
            r = conn.execute(
                """
                SELECT window_id, title, description, source_provider, external_event_id,
                       scope_type, target_entities_json, start_time_utc, end_time_utc,
                       start_time_local, end_time_local, status, suppress_alerts,
                       created_at, updated_at
                FROM operational_maintenance_windows WHERE window_id = ?
                """,
                (window_id,),
            ).fetchone()

        if not r:
            return None

        return MaintenanceWindowRecord(
            window_id=r[0],
            title=r[1],
            description=r[2],
            source_provider=r[3],
            external_event_id=r[4],
            scope_type=r[5],
            target_entities=json.loads(r[6] or "[]"),
            start_time_utc=r[7],
            end_time_utc=r[8],
            start_time_local=r[9],
            end_time_local=r[10],
            status=r[11],
            suppress_alerts=bool(r[12]),
            created_at=r[13],
            updated_at=r[14],
        )

    def create_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        """Creates a new maintenance window."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # If local times are missing, derive from UTC times in Asia/Jakarta
        if not window.start_time_local:
            start_dt = datetime.fromisoformat(window.start_time_utc)
            window.start_time_local = start_dt.astimezone(self.default_tz).isoformat()

        if not window.end_time_local:
            end_dt = datetime.fromisoformat(window.end_time_utc)
            window.end_time_local = end_dt.astimezone(self.default_tz).isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_maintenance_windows (
                    window_id, title, description, source_provider, external_event_id,
                    scope_type, target_entities_json, start_time_utc, end_time_utc,
                    start_time_local, end_time_local, status, suppress_alerts,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    window.window_id,
                    window.title,
                    window.description,
                    window.source_provider,
                    window.external_event_id,
                    window.scope_type,
                    json.dumps(window.target_entities or []),
                    window.start_time_utc,
                    window.end_time_utc,
                    window.start_time_local,
                    window.end_time_local,
                    window.status,
                    1 if window.suppress_alerts else 0,
                    window.created_at or now_iso,
                    window.updated_at or now_iso,
                ),
            )
        return window

    def update_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        """Updates an existing window."""
        window.updated_at = datetime.now(timezone.utc).isoformat()
        return self.create_window(window)

    def delete_window(self, window_id: str) -> bool:
        """Deletes a maintenance window."""
        with topology_transaction(self.db_path, write=True) as conn:
            cur = conn.execute("DELETE FROM operational_maintenance_windows WHERE window_id = ?", (window_id,))
            return cur.rowcount > 0
