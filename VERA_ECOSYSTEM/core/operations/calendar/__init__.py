"""
AIRA OS — Calendar Integration Subsystem (Networking VII / WP 7.5).
"""

from core.operations.calendar.base import CalendarProvider
from core.operations.calendar.google_provider import GoogleCalendarProvider
from core.operations.calendar.ics_provider import IcsCalendarProvider
from core.operations.calendar.local_provider import LocalCalendarProvider
from core.operations.calendar.manager import CalendarManager

__all__ = [
    "CalendarProvider",
    "LocalCalendarProvider",
    "IcsCalendarProvider",
    "GoogleCalendarProvider",
    "CalendarManager",
]
