"""
AIRA OS — Calendar Manager & Maintenance Window Coordinator (Networking VII / WP 7.5).

Coordinates calendar providers and evaluates real-time alert suppression during
scheduled network maintenance windows.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set

from core.operations.calendar.base import CalendarProvider
from core.operations.calendar.google_provider import GoogleCalendarProvider
from core.operations.calendar.ics_provider import IcsCalendarProvider
from core.operations.calendar.local_provider import LocalCalendarProvider
from core.operations.models import MaintenanceStatus, MaintenanceWindowRecord

logger = logging.getLogger("aira.operations.calendar.manager")


class CalendarManager:
    """Unified manager for maintenance windows, provider coordination, and alert suppression."""

    def __init__(
        self,
        local_provider: Optional[LocalCalendarProvider] = None,
        google_provider: Optional[GoogleCalendarProvider] = None,
        ics_provider: Optional[IcsCalendarProvider] = None,
    ) -> None:
        self.local = local_provider or LocalCalendarProvider()
        self.google = google_provider or GoogleCalendarProvider(local_fallback=self.local)
        self.ics = ics_provider or IcsCalendarProvider(fallback_provider=self.local)

    def get_active_provider(self) -> CalendarProvider:
        """Returns the primary active provider (Google if configured, otherwise Local)."""
        if self.google.is_configured:
            return self.google
        return self.local

    def list_windows(
        self,
        start_utc: Optional[datetime] = None,
        end_utc: Optional[datetime] = None,
    ) -> List[MaintenanceWindowRecord]:
        return self.get_active_provider().list_windows(start_utc, end_utc)

    def create_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        return self.get_active_provider().create_window(window)

    def get_window(self, window_id: str) -> Optional[MaintenanceWindowRecord]:
        return self.get_active_provider().get_window(window_id)

    def update_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        return self.get_active_provider().update_window(window)

    def delete_window(self, window_id: str) -> bool:
        return self.get_active_provider().delete_window(window_id)

    # -----------------------------------------------------------------------
    # Real-Time Maintenance Window & Alert Suppression Evaluation
    # -----------------------------------------------------------------------

    def get_currently_active_windows(
        self,
        now_dt: Optional[datetime] = None,
    ) -> List[MaintenanceWindowRecord]:
        """Returns all maintenance windows active at the current moment."""
        current_dt = now_dt or datetime.now(timezone.utc)
        all_windows = self.local.list_windows()
        active: List[MaintenanceWindowRecord] = []

        for w in all_windows:
            try:
                s_dt = datetime.fromisoformat(w.start_time_utc)
                e_dt = datetime.fromisoformat(w.end_time_utc)
                if s_dt <= current_dt <= e_dt and w.status in (MaintenanceStatus.SCHEDULED.value, MaintenanceStatus.ACTIVE.value):
                    active.append(w)
            except Exception:
                continue

        return active

    def is_entity_in_maintenance(
        self,
        entity_id: str,
        now_dt: Optional[datetime] = None,
    ) -> bool:
        """
        Evaluates whether a specific device, interface, or service is currently in
        an active maintenance window where alert suppression is enabled.
        """
        active_windows = self.get_currently_active_windows(now_dt)
        clean_target = entity_id.strip()

        for w in active_windows:
            if not w.suppress_alerts:
                continue
            if w.scope_type == "GLOBAL":
                return True
            if clean_target in w.target_entities:
                return True
            # Check prefix matches (e.g. 'device:Core-1' matching 'Core-1')
            for target in w.target_entities:
                if clean_target.endswith(target) or target.endswith(clean_target):
                    return True

        return False

    # -----------------------------------------------------------------------
    # ICS Export / Import
    # -----------------------------------------------------------------------

    def export_ics(self) -> str:
        """Exports all local maintenance windows to RFC 5545 iCalendar string."""
        windows = self.local.list_windows()
        return self.ics.export_to_ics(windows)

    def import_ics(self, ics_content: str) -> List[MaintenanceWindowRecord]:
        """Imports events from RFC 5545 iCalendar string into local database."""
        imported_windows = self.ics.import_from_ics(ics_content)
        saved: List[MaintenanceWindowRecord] = []
        for w in imported_windows:
            saved.append(self.local.create_window(w))
        return saved
