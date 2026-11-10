# VERA INTERACTION ACTION REGISTRY REPORT
## Universal Typed Action Contracts, Execution Mappings, Safety Fallbacks & Gateway Architecture

**Project:** VERA Enterprise Network Intelligence Platform  
**Subsystem:** VERA Adaptive Experience (VAE) Action Gateway  
**Classification:** P0 Technical Architecture Report  
**Date:** November 2026  
**Architect:** Principal Generative UI Architect & Backend Platform Engineer  
**Frontend Registry:** `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/interactions/ActionRegistry.js`  
**Backend Endpoints:** `VERA_ECOSYSTEM/api/routers/actions.py`

---

## 1. Executive Summary

Prior to this implementation, the interaction between user-facing visual components (such as `WorkflowRecoveryBlock`, `UnifiedActionCard`, and capability buttons) and the backend execution pipeline suffered from fatal contract mismatches. Specifically, actions invoked with parameter lists or recovery tokens caused client-side crashes:
```text
Error: Tipe aksi "tidak diketahui" belum didukung di UI ini.
```

To resolve this defect at its architectural root, VERA established the **Universal Action & Interaction Registry** (`ActionRegistry.js` & `api/routers/actions.py`). This subsystem introduces strongly typed action contracts, robust normalization of raw tool calls and recovery tokens, guaranteed safe fallbacks for unmapped actions, and full REST/WS execution mappings across the entire platform.

---

## 2. Typed Action Contract Specification

Every action presented in the VERA UI conforms to the Discriminated Action Contract:

| Action Type | Operational Role | Parameter Schema | Backend Mapping | Permissions Required |
| :--- | :--- | :--- | :--- | :--- |
| **`retry_operation`** | Re-runs a failed operation with identical inputs | `{ target_tool, payload }` | `/api/v1/actions/execute` or Chat `/tool` | `actions.execute` |
| **`edit_parameters`** | Re-opens interactive form for parameter adjustments | `{ schema, prefilled_data, target_tool }` | Frontend Form Renderer | `actions.execute` |
| **`cancel_workflow`** | Aborts an interactive workflow cleanly | `{ workflow_id, reason }` | Lifecycle State Machine `CANCELLED` | None |
| **`open_resource`** | Opens an existing inventory or topology entity | `{ resource_id, device_name, type }` | Client Drawer / `/api/inventory` | `devices.read` |
| **`view_details`** | Opens comprehensive diagnostic or RCA view | `{ entity_id, incident_id }` | Investigation Panel | `nms.read` |
| **`request_permission`** | Simulates or requests role elevation | `{ resource, action }` | `POST /api/v1/admin/permissions/simulate` | None |
| **`approve_action`** | Confirms high-risk change execution | `{ action_id, reason }` | `POST /api/v1/actions/approval` (APPROVE) | `actions.approve` |
| **`reject_action`** | Denies and cancels proposed change | `{ action_id, reason }` | `POST /api/v1/actions/approval` (REJECT) | `actions.approve` |
| **`resume_workflow`** | Re-attaches to background task after reload | `{ job_id, session_id }` | WebSocket / Stream Replay | `actions.execute` |
| **`navigate_to_resource`** | Deep-links client to page/panel | `{ page, target }` | `window.dispatchEvent('vera:navigate')` | None |
| **`tool`** | Executes registered platform tool | `{ tool, args }` | Chat Turn Runner / Action Engine | `tools.execute` |
| **`workspace`** | Workspace file management | `{ workspace_op, file_path, ... }` | `api.workspace.*` | `files.write` |

---

## 3. Action Normalization & Unknown Action Fallback

### 3.1 Normalization Pipeline (`normalizeAction`)
The dispatcher accepts arbitrary incoming triggers and coerces them into validated envelopes:
- **String Tool Names:** `("update_device", { name: "CHR" })` $\rightarrow$ typed tool envelope `{ type: "tool", targetTool: "update_device", payload: { ... } }`.
- **Recovery Action Objects:** `{ action_id, action_type: "UPDATE_EXISTING", ... }` $\rightarrow$ typed recovery envelope preserving prefilled schemas and original input.
- **Legacy Capabilities:** `{ action: { type: "prompt", prompt: "..." } }` $\rightarrow$ normalized prompt execution.

### 3.2 Safe Fallback for Unsupported Actions
If an unmapped or corrupt action arrives at runtime:
1. It is intercepted before execution.
2. An internal diagnostic warning is recorded (`console.warn("[ActionRegistry] Rejected unsupported action", action)`).
3. Arbitrary execution is blocked.
4. A safe, localized warning toast is shown to the operator (*"Aksi ini tidak memiliki eksekusi yang valid atau belum didaftarkan"*), rather than throwing an unhandled exception or breaking the UI.

---

## 4. Verification Evidence

The action architecture was verified across both unit and end-to-end integration tests:
- `test_actions_gateway_api.py::TestActionsGatewayApi::test_get_action_registry`: **PASSED**.
- `test_actions_gateway_api.py::TestActionsGatewayApi::test_execute_generic_action`: **PASSED**.
- `test_actions_gateway_api.py::TestActionsGatewayApi::test_submit_action_approval`: **PASSED**.
- `test_vae_recovery_engine.py`: 12/12 **PASSED**.
- Zero `"Tipe aksi tidak diketahui"` exceptions reproduced across all recovery flows.
