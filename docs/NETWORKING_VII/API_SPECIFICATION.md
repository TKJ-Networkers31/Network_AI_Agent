# AIRA OS — NETWORKING VII
# OPERATIONS API SPECIFICATION (WP 7.9)

**Gateway Prefix:** `/api/operations`  
**Router Module:** `AIRA_ECOSYSTEM/api/routers/operations.py`  
**Phase:** Phase H — Reporting, API Layer & Frontend Operations Center  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. REST Endpoint Catalog

| Method | Endpoint | Description | Request Body | Response Contract |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/predictive/overview` | Retrieves operational saturation forecasts across active devices/interfaces | None | `PredictiveAnalysisReport` |
| `POST` | `/predictive/forecast` | Computes a forward-looking saturation horizon on a custom time series | `ForecastRequestPayload` | `PredictiveMetricProjection` |
| `POST` | `/change-impact/simulate` | Simulates a proposed network change request against an in-memory cloned graph | `ChangeSimulatePayload` | `DetailedChangeImpactReport` |
| `GET` | `/services` | Lists all registered business services and health scores | None | `List[BusinessServiceRecord]` |
| `POST` | `/services` | Registers a new business service and its network endpoints | `ServiceCreatePayload` | `BusinessServiceRecord` |
| `GET` | `/services/{id}/health` | Calculates real-time health score and redundancy tier (HA vs SPOF) | None | `ServiceHealthReport` |
| `GET` | `/scheduler/jobs` | Lists operational scheduled jobs | None | `List[OperationalJobRecord]` |
| `POST` | `/scheduler/jobs/{id}/run` | Manually triggers immediate execution of a scheduled job | None | `OperationalJobRunRecord` |
| `GET` | `/scheduler/runs` | Retrieves recent operational job execution history | None | `List[OperationalJobRunRecord]` |
| `GET` | `/calendar/windows` | Lists scheduled network maintenance windows | None | `List[MaintenanceWindowRecord]` |
| `POST` | `/calendar/windows` | Schedules a new maintenance window | `MaintenanceWindowPayload` | `MaintenanceWindowRecord` |
| `GET` | `/calendar/export.ics` | Downloads RFC 5545 `.ics` iCalendar file | None | `text/calendar` file stream |
| `GET` | `/incidents` | Lists proactive operational incidents | None | `List[ProactiveIncidentRecord]` |
| `POST` | `/incidents/{id}/transition` | Advances an incident through its lifecycle state machine | `IncidentTransitionPayload` | `ProactiveIncidentRecord` |
| `GET` | `/notifications` | Lists recent operational notifications with quiet hours status | None | `List[OperationalNotificationRecord]` |
| `GET` | `/reports/generate` | Generates a deterministic Daily, Weekly, or Monthly operational report | None | `Dict[str, Any]` (JSON, MD, HTML) |
