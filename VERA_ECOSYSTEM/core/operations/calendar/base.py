"""
AIRA OS — Abstract Calendar Provider Interface (Networking VII / WP 7.5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from core.operations.models import MaintenanceWindowRecord


class CalendarProvider(ABC):
    """Abstract base class for maintenance calendar providers."""

    @abstractmethod
    def list_windows(
        self,
        start_utc: Optional[datetime] = None,
        end_utc: Optional[datetime] = None,
    ) -> List[MaintenanceWindowRecord]:
        """Retrieves maintenance windows within the specified timeframe."""
        pass

    @abstractmethod
    def get_window(self, window_id: str) -> Optional[MaintenanceWindowRecord]:
        """Retrieves a single maintenance window by ID."""
        pass

    @abstractmethod
    def create_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        """Schedules a new maintenance window."""
        pass

    @abstractmethod
    def update_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        """Updates an existing maintenance window."""
        pass

    @abstractmethod
    def delete_window(self, window_id: str) -> bool:
        """Cancels and deletes a maintenance window."""
        pass
