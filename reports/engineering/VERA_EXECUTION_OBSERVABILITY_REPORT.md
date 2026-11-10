# VERA — UNIVERSAL LIVE PROCESS OBSERVABILITY ARCHITECTURE REPORT

**Document ID:** `VERA-REP-OBSERVABILITY-01`  
**Classification:** Observability, Telemetry & UI Diagnostics  
**Status:** IMPLEMENTED & VERIFIED  
**Date:** 2026-11-10  
**Author:** Staff Observability Engineer & Frontend Platform Architect  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/`

---

## 1. EXECUTIVE SUMMARY

Real-time visibility into agent reasoning, tool invocations, and network operations is critical in mission-critical ISP environments. When an engineer executes a multi-router diagnostic or applies an automated firewall rule, opaque spinners or silent delays degrade operator trust.

This engineering initiative establishes:
1. **Typed Event Stream:** Formalizing domain lifecycle events (`job.*`, `model.request.*`, `tool.*`).
2. **Contextual Live Activity Panel (`LiveSteps.jsx`):** Shimmering phase progress indicators and running tool activity indicators.
3. **Interactive Tool Execution Inspector (`ToolStep.jsx`):** An expandable accordion for each executed tool, exposing input parameters, raw network outputs, latency metrics, and error traces.
4. **Distinction Between Idle, Waiting & Processing:** Eliminating ambiguous "stuck" states through explicit progress signals.

---

## 2. TYPED EVENT ARCHITECTURE

Events published on the internal Event Bus (`core/events.py`) flow through the WebSocket bridge (`api/ws_bridge.py`) into the frontend runtime (`ChatRuntimeContext.jsx`):

| Event Type | Producer | Consumer / Visual Representation | Payload Keys |
| :--- | :--- | :--- | :--- |
| `thinking` | `Brain.think()` | Live Thinking Bubble | `{"phase": "Menganalisis topologi..."}` |
| `stream_start` | `provider_client` | Message Bubble Streaming Indicator | `{"model": "nemotron-super"}` |
| `stream_delta` | `provider_client` | Incremental Token Appender | `{"delta": "..."}` |
| `tool_start` | `ToolRunner` | Live Activity Spinner & Step Record | `{"tool": "ping", "arguments": {...}}` |
| `tool_finish` | `ToolRunner` | Success / Error Badge & Output | `{"tool": "ping", "result": {...}, "duration": 0.4}` |
| `model.fallback` | `ModelPolicy` | Fallback Banner & Audit Log | `{"from": "nemotron", "to": "glm", "reason": "timeout"}` |
| `job_paused` | `ws.py` / `job_store` | Paused State Pill | `{"job_id": "...", "checkpoint": {...}}` |
| `job_resumed` | `ws.py` / `job_store` | Resumed Activity Notification | `{"job_id": "...", "instruction": "..."}` |

---

## 3. INTERACTIVE TOOL EXECUTION INSPECTOR

Prior to this update, `ToolStep.jsx` rendered only a static one-line summary (e.g., `✅ mikrotik -> execute_command 0.2s`). Engineers could not view the command executed or the device's reply.

`ToolStep.jsx` now provides an interactive accordion:
- **Collapsed View:** Shows status (`✅` / `❌`), category color badge (e.g., `mikrotik`, `network`, `snmp`, `inventory`), tool name, execution duration, and expandable toggle chevron.
- **Expanded Drawer:**
  - **Parameters Panel:** JSON-formatted view of parameters provided to the tool (e.g., target host, command string, query parameters).
  - **Output Panel:** Raw terminal output, structured dictionary response, or exact diagnostic failure trace.

---

## 4. TOOL-SPECIFIC ACTIVITY REPRESENTATIONS

Specific diagnostic domains feature tailored visual semantics:
1. **Ping / Reachability:** Summarizes transmitted/received packets, packet loss percentage, and min/avg/max RTT.
2. **Traceroute:** Displays sequential hop IPs, latency per hop, and AS annotations.
3. **RouterOS / SSH Command:** Monospaced terminal block showing the exact CLI syntax and RouterOS response.
4. **Database / Inventory Query:** Displays matched devices and configuration attributes.

---

## 5. VERIFICATION

- Built and validated against Vite production bundle: `dist/assets/index-D62Zp84I.js`.
- Verified in `LiveSteps.jsx` and `ToolStep.jsx` with test suites passing cleanly.
- Real-time event propagation verified with `test_events.py` and `test_ws_bridge.py`.
