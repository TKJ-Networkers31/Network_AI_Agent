# AIRA OS — NETWORKING VII
# CONTROLLED NOTIFICATION ENGINE SPECIFICATION (WP 7.7)

**Module:** `AIRA_ECOSYSTEM/core/operations/notification_hub.py`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Database Table:** `operational_notifications`  
**Phase:** Phase G — Proactive Incident & Notification Intelligence  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Problem

Uncontrolled network alerts cause operator desensitization and alert fatigue ("alert storms"). 

The **Controlled Notification Engine** enforces three layers of alert discipline:
1. **Deduplication:** Hash-based `dedup_key` suppresses repeated alarms within a sliding cooldown window (default 15 minutes).
2. **Quiet Hours in Asia/Jakarta:** Non-critical alerts (`INFO`, `LOW`, `MEDIUM`) arriving between 22:00 and 06:00 WIB are held in queue (`QUEUED_QUIET_HOURS`).
3. **Emergency Priority Override:** Critical and High severity alerts (`HIGH`, `CRITICAL`) immediately bypass quiet hours and are dispatched in real-time.

---

## 2. Notification Pipeline

```mermaid
flowchart TD
    In[Incoming Alert / Predictive Risk] --> DedupCheck{Within Cooldown?}
    DedupCheck -- Yes --> Suppress[Status: SUPPRESSED_COOLDOWN\nLogged to DB, Suppressed from UI/WS]
    DedupCheck -- No --> QuietCheck{In Quiet Hours?\n(22:00 - 06:00 WIB)}
    QuietCheck -- Yes --> SevCheck{Severity HIGH or CRITICAL?}
    SevCheck -- No --> QueueQuiet[Status: QUEUED_QUIET_HOURS\nHeld until 06:00 WIB]
    SevCheck -- Yes --> Send[Status: SENT\nImmediate Delivery]
    QuietCheck -- No --> Send
    Send --> EventBus[Publish to EventBus\n'operational.notification'\nWebSocket Bridge]
```
