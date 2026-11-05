"""
AIRA OS — RFC 5545 iCalendar (.ics) Provider (Networking VII / WP 7.5).

Generates and parses RFC 5545 standard compliant .ics iCalendar files for interoperability
with external calendar systems (Microsoft Outlook, Apple Calendar, Thunderbird, Google Calendar).
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List, Optional
import uuid

from core.operations.calendar.base import CalendarProvider
from core.operations.models import MaintenanceWindowRecord


def _format_ics_timestamp(iso_str: str) -> str:
    """Converts an ISO-8601 UTC timestamp to RFC 5545 format (YYYYMMDDTHHMMSSZ)."""
    clean = iso_str.replace("-", "").replace(":", "")
    if "." in clean:
        clean = clean.split(".")[0]
    if not clean.endswith("Z"):
        clean += "Z"
    return clean


def _parse_ics_timestamp(ics_ts: str) -> str:
    """Parses RFC 5545 timestamp (YYYYMMDDTHHMMSSZ) to standard ISO-8601 UTC string."""
    clean = ics_ts.strip().rstrip("Z")
    if len(clean) >= 15 and "T" in clean:
        y, m, d = clean[0:4], clean[4:6], clean[6:8]
        h, mn, s = clean[9:11], clean[11:13], clean[13:15]
        return f"{y}-{m}-{d}T{h}:{mn}:{s}+00:00"
    return datetime.now(timezone.utc).isoformat()


class IcsCalendarProvider(CalendarProvider):
    """RFC 5545 iCalendar import and export provider."""

    def __init__(self, fallback_provider: Optional[CalendarProvider] = None) -> None:
        self.fallback_provider = fallback_provider

    def export_to_ics(self, windows: List[MaintenanceWindowRecord]) -> str:
        """Serializes a list of maintenance windows into an RFC 5545 iCalendar string."""
        now_ics = _format_ics_timestamp(datetime.now(timezone.utc).isoformat())
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//AIRA OS//Network Operations Intelligence//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        for w in windows:
            dtstart = _format_ics_timestamp(w.start_time_utc)
            dtend = _format_ics_timestamp(w.end_time_utc)
            entities_str = ", ".join(w.target_entities)

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{w.window_id}@aira-os",
                f"DTSTAMP:{now_ics}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:{w.title}",
                f"DESCRIPTION:{w.description} (Scope: {w.scope_type}, Targets: {entities_str})",
                f"STATUS:{'CONFIRMED' if w.status == 'SCHEDULED' else 'CANCELLED'}",
                "CATEGORIES:NETWORK_MAINTENANCE",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR\r\n")
        return "\r\n".join(lines)

    def import_from_ics(self, ics_content: str) -> List[MaintenanceWindowRecord]:
        """Parses an RFC 5545 iCalendar string and returns extracted MaintenanceWindowRecords."""
        windows: List[MaintenanceWindowRecord] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # Split into VEVENT blocks
        events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_content, re.DOTALL | re.IGNORECASE)

        for ev_str in events:
            uid_m = re.search(r"UID:(.+)", ev_str)
            summary_m = re.search(r"SUMMARY:(.+)", ev_str)
            desc_m = re.search(r"DESCRIPTION:(.+)", ev_str)
            start_m = re.search(r"DTSTART:(.+)", ev_str)
            end_m = re.search(r"DTEND:(.+)", ev_str)

            uid = uid_m.group(1).strip() if uid_m else f"win_ics_{uuid.uuid4().hex[:8]}"
            title = summary_m.group(1).strip() if summary_m else "Imported Maintenance Window"
            desc = desc_m.group(1).strip() if desc_m else ""
            start_utc = _parse_ics_timestamp(start_m.group(1)) if start_m else now_iso
            end_utc = _parse_ics_timestamp(end_m.group(1)) if end_m else now_iso

            win = MaintenanceWindowRecord(
                window_id=uid.replace("@aira-os", ""),
                title=title,
                description=desc,
                source_provider="ICS",
                external_event_id=uid,
                scope_type="GLOBAL",
                target_entities=[],
                start_time_utc=start_utc,
                end_time_utc=end_utc,
                start_time_local=start_utc,
                end_time_local=end_utc,
                status="SCHEDULED",
                suppress_alerts=True,
            )
            windows.append(win)

        return windows

    # Fallback CalendarProvider methods delegating to local provider if set
    def list_windows(self, start_utc: Optional[datetime] = None, end_utc: Optional[datetime] = None) -> List[MaintenanceWindowRecord]:
        return self.fallback_provider.list_windows(start_utc, end_utc) if self.fallback_provider else []

    def get_window(self, window_id: str) -> Optional[MaintenanceWindowRecord]:
        return self.fallback_provider.get_window(window_id) if self.fallback_provider else None

    def create_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        return self.fallback_provider.create_window(window) if self.fallback_provider else window

    def update_window(self, window: MaintenanceWindowRecord) -> MaintenanceWindowRecord:
        return self.fallback_provider.update_window(window) if self.fallback_provider else window

    def delete_window(self, window_id: str) -> bool:
        return self.fallback_provider.delete_window(window_id) if self.fallback_provider else True
