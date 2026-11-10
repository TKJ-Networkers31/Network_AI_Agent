# VERA Interactive Experience Platform Migration Report

**Subsystem:** VERA Adaptive Experience (VAE) & Core Interaction Platform  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P0 Architecture & Experience Platform Transformation  
**Status:** MIGRATION COMPLETE & VERIFIED  

---

## 1. Executive Summary & Migration Scope

The objective of this migration was to upgrade VERA from a conventional chat interface rendering static Markdown into a high-reliability, interactive, persistent, and visually adaptive enterprise network operations platform.

The migration addresses ten critical engineering goals:
1. **Broken Interaction Resolution:** Eliminating `Tipe aksi "tidak diketahui" belum didukung di UI ini` and establishing a typed action contract across frontend and backend.
2. **Interactive SVG DOM:** Upgrading from non-interactive `<img>` wrappers to a React-managed SVG canvas with per-node selection, edge inspection, and a contextual device drawer.
3. **Deterministic SVG Layout Engine:** Resolving unmeasured coordinate overlaps and line collisions in VRRP failover diagrams.
4. **Adaptive Visual Asset Resolution:** Establishing strict intent classification preventing hallucinated live topologies using stock photography while cataloging authentic physical hardware.
5. **Ergonomic SVG Animations:** Network flow and VRRP pulses with user controls and full compliance with `prefers-reduced-motion`.
6. **Smart Reading Auto-Scroll Physics:** Replacing blind `scrollIntoView()` with threshold-based reading anchoring and a floating "Lihat respons terbaru" pill.
7. **Context-Preserving Selection Intelligence:** Connecting text highlights across markdown, code, and tables directly to the parent turn context.
8. **Durable Background Job Execution:** Implementing a SQLite-backed state machine (`jobs.db`) with automatic interruption recovery on reboot.
9. **Zero-Amnesia Reconnection:** Replaying active run state and partial streaming text over WebSockets upon browser refresh without reset to 0%.
10. **Native Desktop Notifications:** Providing background alerts and tab-focusing click handlers via the Service Worker and Notification API.

---

## 2. Architectural Evolution Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LEGACY (AIRA OS)                               │
│  - Static <img> SVG rendering (no click/keyboard handlers)                  │
│  - Unmapped action types thrown directly to generic capabilities            │
│  - Unmeasured coordinates causing overlapping VRRP boxes & text             │
│  - Blind scrollIntoView() pulling viewport away from reading position       │
│  - Ephemeral _ACTIVE_RUNS: F5 refresh causes lost state and stuck busy lock │
│  - Zero system desktop notifications                                        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ (TRANSFORMATION)
┌─────────────────────────────────────────────────────────────────────────────┐
│                            VERA ENTERPRISE VAE                              │
│  - InteractiveSvgCanvas (React DOM, zoom/pan, detail drawer, accessibility) │
│  - ActionRegistry + ActionGateway (/api/v1/actions/execute & approval)      │
│  - Deterministic layoutEngine (text metrics, collision pills, auto viewBox) │
│  - Smart reading auto-follow (110px threshold, unread pill, motion safe)    │
│  - Persistent JobStore (jobs.db, 10 states, active_run_resumed WS replay)   │
│  - Native NotificationService + ServiceWorker push & tab focusing           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Modifications & Implementations

### 3.1 Universal Action & Interaction Gateway
- **Frontend Registry (`ActionRegistry.js`):** Defines typed action contracts (`ACTION_TYPES`), input normalization (`normalizeAction`), and fallback execution (`executeTypedAction`).
- **Workflow Recovery Integration (`WorkflowRecoveryBlock.jsx`):** Emits structured action objects instead of passing raw tool names as capability strings.
- **Backend Action Gateway (`api/routers/actions.py`):** REST endpoints for `POST /api/v1/actions/execute`, `POST /api/v1/actions/approval`, and `GET /api/v1/actions/registry`.

### 3.2 High-Fidelity Interactive SVG
- **Declarative Scene Graph (`sceneGraph.js`):** Canonical node, edge, and cluster definitions with blank-node fallbacks and a dedicated VRRP failover builder (`buildVrrpFailoverSceneGraph`).
- **Deterministic Layout Engine (`layoutEngine.js`):** Heuristic character measurement, minimum 16px padding, anti-collision background pill rects behind labels, and bounding-box auto-viewBox calculation.
- **Interactive Canvas (`InteractiveSvgCanvas.jsx`):** Pan, zoom, motion pause/play toggle, keyboard navigation (`tabIndex={0}`, `role="button"`), and ARIA compliance.
- **Contextual Device Detail Drawer (`DeviceDetailDrawer.jsx`):** Displays device specs, operational status, VRRP parameters, and quick actions (Ping, AKANE Terminal, WebFig).

### 3.3 Visual Asset Resolution Pipeline
- **Intent Discriminator (`adaptiveAssetResolver.js`):** Classifies visual intents into `RETRIEVED_IMAGE`, `STRUCTURED_SVG`, `NATIVE_CHART`, `INTERACTIVE_GRAPH`, and `NARRATIVE_ONLY`. Enforces that live topology never uses stock photography.
- **Hardware Catalog:** MikroTik CCR, CRS, and hEX series specifications with licensing metadata and SSRF validation.

### 3.4 Interaction & Ergonomics
- **Smart Reading Auto-Scroll (`ChatPage.jsx`):** Disables auto-follow when scrolled $>110\text{px}$ from bottom. Surfaces floating "Lihat respons terbaru" pill with unread count.
- **Selection Intelligence (`SelectionToolbar.jsx`):** Floating toolbar near highlighted text with "Jelaskan" and "Salin" actions bound to parent turn metadata.

### 3.5 Durability, Stream Replay & Notifications
- **Persistent Job Store (`core/job_store.py`):** 10-state machine persisted in `database/jobs.db` with auto-recovery of interrupted jobs on startup.
- **WebSocket Reconnect (`api/routers/ws.py`):** Emits `active_run_resumed` immediately on reconnect, restoring live tools and partial text without 0% reset.
- **Desktop Notifications (`notificationService.js` & `public/service-worker.js`):** Emits native desktop notifications on job completion when tab is hidden; clicking focuses the VERA tab.

---

## 4. Verification & Validation Summary

- **Pytest:** 6/6 tests passed (`test_durable_jobs.py`, `test_actions_gateway_api.py`).
- **Frontend Test Suite:** 296/296 tests passed (`node --test`).
- **Vite Build:** 2367 modules transformed, zero errors, production bundle generated.
- **Runtime Stability:** Zero regressions introduced to existing chat history, DIO forms, or network monitoring tools.
