# VERA NETWORKING REMEDIATION BACKLOG
## Prioritized Post-Audit Engineering Backlog & Hardening Roadmap

**Document Version:** 1.0.0  
**Audit Target:** VERA Networking Subsystem  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Post-Audit Remediation & Hardening Plan  
**Status:** BACKLOG STAGED (READ-ONLY AUDIT PRESERVED)  

---

## 1. BACKLOG PRIORITIZATION FRAMEWORK

In accordance with the executive audit directives, this assignment was strictly read-only and performed zero modifications to production application code. The remediation backlog below is organized into structured engineering sprints prioritized by architectural criticality.

```
  +-------------------------------------------------------------------------+
  |                           REMEDIATION ROADMAP                           |
  +-------------------------------------------------------------------------+
  | Sprint 1 (P1): Core Architecture & Import Stability                     |
  |   - Resolve routing/intelligence circular imports (BUG-NET-01)          |
  |   - Refactor Lazy Imports in Evidence Service                           |
  +-------------------------------------------------------------------------+
  | Sprint 2 (P2): Automated Test Suite Hardening                           |
  |   - Add Authenticated Test Fixtures to Legacy Suites (BUG-NET-02)       |
  |   - Fix Asynchronous Telemetry Race in NMS WebSocket Test (BUG-NET-03)   |
  +-------------------------------------------------------------------------+
  | Sprint 3 (P3): Transport Hardening & Legacy Identity Sanitization       |
  |   - Formalize 15s SSH Banner Timeout across all transports (BUG-NET-04) |
  |   - Sanitize Residual MCP Server Tool Docstrings (BUG-NET-05)           |
  |   - Deprecate Redundant tools/ssh/shell.py (DUP-NET-02)                 |
  +-------------------------------------------------------------------------+
  | Sprint 4 (P3): Database Schema & Subsystem Consolidation                |
  |   - Unify inventory.db and topology.db persistence layers (DUP-NET-01)  |
  |   - Standardize Multi-Vendor NormalizedRoute Consumption (DUP-NET-03)   |
  +-------------------------------------------------------------------------+
```

---

## 2. DETAILED REMEDIATION TICKETS

### Ticket NET-REM-01: Break Circular Dependency between Routing and Intelligence
- **Priority:** P1 — High
- **Estimated Effort:** 2 Hours
- **Affected Files:**
  - `VERA_ECOSYSTEM/core/routing/__init__.py`
  - `VERA_ECOSYSTEM/core/network_intelligence/evidence_service.py`
- **Specification:**
  1. In `core/network_intelligence/evidence_service.py`, remove top-level import:
     ```python
     # Remove from module header:
     from core.routing.route_collector import MultiDeviceRouteCollector, get_route_collector
     ```
  2. Move `get_route_collector` import inside `EvidenceService.collect_route_evidence()` or create an interface class `IRouteCollector` in `core/routing/contracts.py`.
  3. Verify that `python -c "from core.routing.unified_route_parser import UnifiedRouteParser"` completes successfully with exit code 0.

---

### Ticket NET-REM-02: Refactor Legacy Test Fixtures for Mandatory Authentication
- **Priority:** P2 — Medium
- **Estimated Effort:** 3 Hours
- **Affected Files:**
  - `VERA_ECOSYSTEM/tests/test_wp_4_6_1_route_collection.py`
  - `VERA_ECOSYSTEM/tests/test_wp_4_6_2_route_analytics.py`
  - `VERA_ECOSYSTEM/tests/test_wp_4_6_3_route_dependency.py`
  - `VERA_ECOSYSTEM/tests/test_wp_4_6_4_route_history.py`
  - `VERA_ECOSYSTEM/tests/test_networking_iii_api.py`
  - `VERA_ECOSYSTEM/tests/test_networking_vii_api.py`
- **Specification:**
  1. Add an authenticated fixture to `conftest.py`:
     ```python
     @pytest.fixture
     def auth_headers():
         from core.tenant.auth_deps import _identity_mgr
         user = _identity_mgr.get_user_by_username("lingga_admin")
         token = _identity_mgr.create_session(user.user_id).token
         return {"Authorization": f"Bearer {token}"}
     ```
  2. Pass `headers=auth_headers` to all `client.get()` and `client.post()` invocations.
  3. Verify that all 20 failing API assertions transition from 401 Unauthorized to 200 OK.

---

### Ticket NET-REM-03: Filter Asynchronous Broadcasts in WebSocket Test
- **Priority:** P2 — Medium
- **Estimated Effort:** 1 Hour
- **Affected Files:**
  - `VERA_ECOSYSTEM/tests/test_nms.py`
- **Specification:**
  1. In `test_nms_websocket_endpoint_and_snapshot`, replace single `ws.receive_json()` with a draining loop:
     ```python
     ws.send_json({"type": "ping"})
     pong = None
     for _ in range(5):
         msg = ws.receive_json()
         if msg.get("type") == "pong":
             pong = msg
             break
     assert pong is not None and pong["type"] == "pong"
     ```

---

### Ticket NET-REM-04: Sanitize Residual Branding in MCP Server Docstrings
- **Priority:** P3 — Low
- **Estimated Effort:** 30 Minutes
- **Affected Files:**
  - `VERA_ECOSYSTEM/mcp_servers/network/server.py`
- **Specification:**
  Replace occurrences of `"AIRA"` with `"VERA"` in docstrings for `network_list_devices`, `network_nslookup`, and `network_ping`.

---

### Ticket NET-REM-05: Transport Engine Consolidation
- **Priority:** P3 — Low
- **Estimated Effort:** 4 Hours
- **Affected Files:**
  - `VERA_ECOSYSTEM/tools/ssh/shell.py`
  - `VERA_ECOSYSTEM/agents/akane/connection_manager.py`
- **Specification:**
  1. Mark `tools/ssh/shell.py` as deprecated.
  2. Re-export `PersistentShell` from `agents.akane.connection_manager` to maintain backward compatibility while eliminating redundant PTY code.
