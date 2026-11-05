# AIRA OS — FEATURE MIGRATION MATRIX

**Version:** 1.0.0  
**Classification Schema:** KEEP | REFACTOR | SIMPLIFY | MERGE | REPLACE | DEFER | REMOVE

---

## 1. Feature Classification Matrix

| Feature / Module | Current Implementation | Proposed Classification | Rationale & Transformation Target |
|---|---|---|---|
| **AI Conversational Core** | `core/brain.py`, `agents/rei/planner.py` | **KEEP** | Core reasoning, classifier, and model router are solid. Integrate into unified workspace with streaming. |
| **Dynamic Interaction Orchestrator (DIO)** | `core/dio`, `app/frontend/src/pages/dio` | **REFACTOR** | Refactor from isolated pages into seamless conversational prompt cards with schema-driven validation. |
| **Tool Registry & Categories** | `core/orchestrator.py`, `agents/*` | **REFACTOR** | Consolidate disparate tool dictionaries into a unified tool registry with Category A/B/C autonomy classifications. |
| **Approval / Confirmation System** | Ad-hoc checks in router scripts | **REFACTOR** | Build a centralized approval policy engine with user/org preferences and impact explanations. |
| **Contextual "Ask AIRA" Overlay** | `components/selection/SelectionToolbar.jsx` (8 buttons) | **SIMPLIFY** | Replace 8-button toolbar with a sleek floating prompt composer attached to selected response text. |
| **Primary Navigation & Layout** | 16-item sidebar across 4 groups | **SIMPLIFY** | Consolidate to 5 clean destinations: Workspace, Infrastructure, Automations, Files, Settings. Move admin to `/admin`. |
| **Customer Portal Page** | `pages/CustomerPortalPage.jsx` | **MERGE** | Merge portal capabilities (incidents, health overview) into unified Customer Workspace and Infrastructure. |
| **Operations Center Page** | `pages/OperationsPage.jsx` | **MERGE** | Merge operational health scoring and alerts directly into the Infrastructure & Monitoring workspace. |
| **Decision Center Page** | `pages/DecisionsPage.jsx` | **MERGE** | Fold automated decision and recommendation cards directly into AIRA's conversational feed. |
| **Edge Gateways Page** | `pages/GatewaysPage.jsx` | **MERGE** | Relocate edge gateway status and enrollment tokens into Settings > Integrations & Infrastructure. |
| **Network Intelligence Page** | `pages/NetworkIntelligencePage.jsx` | **MERGE** | Integrate route analysis and configuration simulation into conversational AIRA tools and Infrastructure tabs. |
| **Topology Engine & Graph Fabric** | `core/topology_engine.py`, `TopologyPage.jsx` | **REFACTOR** | Enforce device-centric node rendering (1 node per device) with multi-interface edge connection endpoints. |
| **Recursive Network Discovery** | `core/topology_discovery.py` | **REFACTOR** | Add single-seed capability-based discovery with progressive scoping, loop prevention, and pending device states. |
| **Automatic Inventory-Topology Sync** | `devices.py` (`sync_inventory_and_topology`) | **REPLACE** | Replace aggressive auto-population with hardcoded "admin" username with explicit pending device promotion workflow. |
| **Real-Time NMS Telemetry** | `core/nms_engine.py`, `NmsPage.jsx` | **REFACTOR** | Fix counter delta bandwidth calculations and implement live WebSocket streaming directly into UI modals and cards. |
| **Device Inventory & Secret Vault** | `core/inventory_store.py` (Fernet) | **KEEP** | Robust encrypted secret storage. Enhance with credential profiles and secret references for pending devices. |
| **Automation & Task Scheduler** | `core/scheduler.py` (33-line stub) | **REPLACE** | Replace stub with a full-featured interval and event-driven automation engine with execution history. |
| **Workspace Filesystem (FSE)** | `core/filesystem/operations.py`, `files.py` | **KEEP** | Traversal sandboxing, permission levels, and trash engine are sound. Add ZIP creation and extraction APIs. |
| **File Processing & Archive Extractor** | `core/file_processing/archive.py` | **KEEP** | Safe zip extraction and Zip-Slip protection already present. Verify and link to frontend file actions. |
| **Artifact Generation Engine** | `core/artifacts/engine.py` (7 formats) | **REFACTOR** | Connect artifact engine to downloadable output panel in chat and files destinations. |
| **Tenant Isolation & RBAC Core** | `core/tenant/manager.py`, `models.py` | **REFACTOR** | Extend existing multi-tenant models with Free, Pro, and Networking++ entitlement policies and token meters. |
| **Authentication & Session Tokens** | `core/tenant` (`aira_tok_...`) | **REFACTOR** | Add email registration/verification flow, password reset, and configurable Google OAuth 2.0 integration. |
| **Token Metering & Accounting** | Fragmented `token_usage` dicts | **REFACTOR** | Build centralized atomic token accounting engine tracking input, output, cached tokens, and tool costs. |
| **Platform Administration Site** | Non-existent (everything mixed in app) | **REFACTOR** | Create dedicated `/admin` experience for tenant onboarding, entitlement policy, token quotas, and audit logs. |
| **Background Voice Service (Yuki)** | `agents/yuki`, `VoiceControls.jsx` | **KEEP** | Voice companion works smoothly and runs in background. Retain as subtle, non-intrusive workspace tool. |
| **OCR & Vision Attachment Pipeline** | `core/file_processing/ocr.py` | **KEEP** | Tesseract OCR and multimodal attachment inspection are functional and tested. |
| **Raw Microservice Terminology in UI** | "Decision Center", "Edge Gateway", etc. | **REMOVE** | Remove internal microservice branding from customer-facing views; keep names in backend architecture. |

---

## 2. Migration Execution Sequence

1. **Stage 1 — Audit & Baseline:** Complete documentation and safety checkpoint.
2. **Stage 2 — Core Architecture:** Service interfaces and shared domain models.
3. **Stage 3 — Identity & AAA:** Authentication, verification, Google OAuth config, session tokens, audit accounting.
4. **Stage 4 — Entitlements & Metering:** Free, Pro, Networking++ tiers, token policy engine, usage tracking.
5. **Stage 5 — AI Workspace:** Minimalist UI layout, DIO integration, rich output rendering, contextual Ask AIRA overlay.
6. **Stage 6 — Infrastructure Foundation:** Single device model, pending discovery states, credential references.
7. **Stage 7 — Topology & NMS:** Device-centric multi-interface graph, counter delta fixes, live WebSocket telemetry.
8. **Stage 8 — Automation Engine:** Interval-based and event-driven scheduler, action catalog, DIO parameter hooks.
9. **Stage 9 — Files & Artifacts:** Safe ZIP archive operations, multi-format parsers, downloadable artifact panel.
10. **Stage 10 — Admin & Customer Sites:** Split `/admin` and `/app`, enforce backend RBAC boundaries.
11. **Stage 11 — Integration & Verification:** Automated test execution, security validation, completion report.
