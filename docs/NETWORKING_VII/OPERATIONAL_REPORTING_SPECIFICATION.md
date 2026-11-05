# AIRA OS — NETWORKING VII
# OPERATIONAL REPORTING SPECIFICATION (WP 7.8)

**Module:** `AIRA_ECOSYSTEM/core/operations/reporting_engine.py`  
**Endpoint:** `GET /api/operations/reports/generate?period=DAILY|WEEKLY|MONTHLY`  
**Phase:** Phase H — Reporting, API Layer & Frontend Operations Center  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Problem

Reporting network health, capacity headroom, and maintenance execution often requires labor-intensive manual data collection across disconnected tools.

The **Operational Reporting Engine** automatically aggregates deterministic operational telemetry across:
1. Business Service availability and health percentages.
2. Proactive incidents detected, investigated, and preventatively mitigated.
3. Active and completed scheduled maintenance windows.
4. Operational scheduler job execution success rates.
5. Critical capacity saturation forecasts.

---

## 2. Supported Report Formats

- **Structured JSON (`Dict[str, Any]`):** Machine-readable contract containing raw metrics, entity records, and time intervals.
- **GitHub-Flavored Markdown (`markdown`):** Fully formatted markdown with tables and badges, ready for immediate rendering in chat conversations and web UI.
- **Printable HTML (`html`):** Standalone, styled HTML document suitable for browser printing or PDF conversion.
