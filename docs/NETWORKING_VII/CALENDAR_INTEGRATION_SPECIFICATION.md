# AIRA OS — NETWORKING VII
# CALENDAR INTEGRATION SPECIFICATION (WP 7.5)

**Module:** `AIRA_ECOSYSTEM/core/operations/calendar/`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Database Table:** `operational_maintenance_windows`  
**Phase:** Phase F — External Calendar Integration  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Problem

Network changes often trigger noisy false-positive alarms when monitoring systems are unaware of scheduled maintenance windows. Furthermore, NOC operators coordinate maintenance windows across diverse tools (Google Calendar, Microsoft Outlook, internal spreadsheets).

The **Calendar Integration Subsystem** provides a multi-provider calendar architecture with:
1. **Local Provider:** Pure SQLite storage for 100% offline environments.
2. **ICS Provider:** RFC 5545 standard compliant `.ics` import and export for Outlook, Thunderbird, and Apple Calendar.
3. **Google Calendar Provider:** Google Calendar API v3 with OAuth 2.0 and graceful offline fallback.
4. **Alert Suppression:** Real-time suppression of alarms and baseline updates for devices inside active maintenance windows.

---

## 2. Real-Time Alert Suppression Logic

When an anomaly or failure is detected on entity $E$ at timestamp $T$:
1. `CalendarManager.is_entity_in_maintenance(E, at_time=T)` is evaluated.
2. If `True` and `suppress_alerts = 1`:
   - Anomaly is tagged with `in_maintenance_window = True`.
   - Low/Medium alerts are suppressed to prevent operator alarm fatigue.
   - Telemetry samples collected during this window are tagged `MAINTENANCE_EXCLUDED` in `BaselineEngine` to prevent baseline contamination.

---

## 3. RFC 5545 iCalendar Interoperability

- **Export:** Serializes maintenance windows into standard `VCALENDAR` and `VEVENT` records with `DTSTART`, `DTEND`, `SUMMARY`, and `DESCRIPTION`.
- **Import:** Parses imported `.ics` files, extracts timestamps and target scopes, and persists records into `operational_maintenance_windows`.
