# VERA NETWORKING BUG REGISTER
## Formal Defect Catalog, Severity Classifications, Root Causes & Steps to Reproduce

**Document Version:** 1.0.0  
**Audit Target:** VERA Networking Subsystem  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** P0 Software Quality & Engineering Defect Register  
**Status:** FORENSIC RECORD  

---

## 1. DEFECT CLASSIFICATION MATRIX

| Bug ID | Severity | Subsystem | Title / Summary | Status |
| :--- | :---: | :---: | :--- | :---: |
| **BUG-NET-01** | **P1 (High)** | Routing / NI | Circular dependency between `core.routing` & `core.network_intelligence` | Confirmed |
| **BUG-NET-02** | **P2 (Med)** | Test Suites | Legacy API unit test fixtures lack `Authorization` bearer token | Confirmed |
| **BUG-NET-03** | **P2 (Med)** | NMS WebSocket | Asynchronous telemetry event race condition in WebSocket test | Confirmed |
| **BUG-NET-04** | **P3 (Low)** | SSH Transport | Paramiko default banner timeout too aggressive on low-power MIPS | Workaround Active |
| **BUG-NET-05** | **P3 (Low)** | MCP Server | Residual legacy strings ("AIRA") in Network MCP tool descriptions | Confirmed |

---

## 2. DETAILED DEFECT SPECIFICATIONS

### 2.1 BUG-NET-01: Circular Dependency in Routing & Intelligence
- **Severity:** P1 — High
- **Components:** [core/routing/__init__.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/routing/__init__.py), [core/routing/route_collector.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/routing/route_collector.py), and [core/network_intelligence/evidence_service.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/network_intelligence/evidence_service.py).
- **Steps to Reproduce:**
  ```python
  import sys
  sys.path.insert(0, "VERA_ECOSYSTEM")
  from core.routing.unified_route_parser import UnifiedRouteParser
  ```
- **Error Encountered:**
  ```
  ImportError: cannot import name 'MultiDeviceRouteCollector' from partially initialized 
  module 'core.routing.route_collector' (most likely due to a circular import)
  ```
- **Root Cause:** `core/routing/__init__.py` imports `route_collector.py`. `route_collector.py` imports `core.network_intelligence.command_execution`. `core.network_intelligence/__init__.py` loads `evidence_service.py`, which imports `MultiDeviceRouteCollector` from `core.routing.route_collector` before the module has completed its definition.
- **Impact:** Crashed `sync_from_seed_router` in [topology_discovery.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_discovery.py) unless `core.network_intelligence` was imported earlier in the process lifecycle.
- **Remediation Recommendation:** Move the import of `MultiDeviceRouteCollector` in `core/network_intelligence/evidence_service.py` inside the specific method where it is consumed (lazy import) or factor the protocol contracts into an independent `core/routing/interfaces.py`.

---

### 2.2 BUG-NET-02: Missing Authorization Headers in Older API Test Fixtures
- **Severity:** P2 — Medium
- **Components:** `test_wp_4_6_1_route_collection.py`, `test_wp_4_6_2_route_analytics.py`, `test_wp_4_6_3_route_dependency.py`, `test_wp_4_6_4_route_history.py`, `test_networking_iii_api.py`, `test_networking_vii_api.py`.
- **Steps to Reproduce:**
  ```bash
  .venv/bin/pytest VERA_ECOSYSTEM/tests/test_networking_iii_api.py
  ```
- **Error Encountered:**
  ```
  AssertionError: assert 401 == 200
  +  where 401 = <Response [401 Unauthorized]>.status_code
  ```
- **Root Cause:** When Phase F.1 introduced mandatory RBAC and session token verification across all endpoints, existing unit test fixtures that instantiated `TestClient(app)` without supplying an `Authorization: Bearer <token>` header were not refactored.
- **Impact:** 20 unit tests fail in automated test runs, masking actual regressions.
- **Remediation Recommendation:** Update the `client` pytest fixture across these test files to automatically create an ephemeral test admin user and attach `Authorization: Bearer <token>` to request headers.

---

### 2.3 BUG-NET-03: Asynchronous Telemetry Race in WebSocket Test
- **Severity:** P2 — Medium
- **Components:** [tests/test_nms.py:836](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tests/test_nms.py)
- **Steps to Reproduce:**
  ```bash
  .venv/bin/pytest VERA_ECOSYSTEM/tests/test_nms.py -k test_nms_websocket_endpoint_and_snapshot
  ```
- **Error Encountered:**
  ```
  AssertionError: 'nms_device_status' != 'pong'
  - nms_device_status
  + pong
  ```
- **Root Cause:** The test client sends `{"type": "ping"}` and immediately awaits `ws.receive_json()`. If the background scheduler pushes an unsolicited `nms_device_status` broadcast at that exact moment, the test assertion fails.
- **Remediation Recommendation:** Update the test loop to consume frames until a `pong` frame is received, ignoring interleaved background status broadcasts.

---

### 2.4 BUG-NET-04: Paramiko Default Banner Timeout on Low-Power Hardware
- **Severity:** P3 — Low
- **Components:** [agents/akane/connection_manager.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/agents/akane/connection_manager.py)
- **Steps to Reproduce:** Rapidly establish 5 successive SSH connections to a physical MikroTik router with MIPS CPU under RouterOS v6 without setting `banner_timeout`.
- **Error Encountered:** `paramiko.ssh_exception.SSHException: No existing session`
- **Root Cause:** Paramiko defaults to a short banner negotiation timeout (1.0s). Under RouterOS v6 on low-power MIPS hardware (650MHz), the SSH server may require 2.0-5.0s to complete banner transmission during bursts.
- **Remediation Implemented:** Configured `banner_timeout=15.0s` in `PersistentShell.open()`.

---

### 2.5 BUG-NET-05: Residual Legacy Strings in Network MCP Server
- **Severity:** P3 — Low
- **Components:** [mcp_servers/network/server.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/mcp_servers/network/server.py)
- **Defect Description:** The tool docstrings for `network_list_devices`, `network_nslookup`, and `network_ping` explicitly mention `"AIRA inventory"` and `"AIRA host"`.
- **Remediation Recommendation:** Update string literals to reference `"VERA"`.
