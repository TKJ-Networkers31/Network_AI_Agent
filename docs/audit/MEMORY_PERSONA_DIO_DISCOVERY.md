# AIRA OS — MEMORY, PERSONA & DIO REPOSITORY DISCOVERY REPORT
**Date:** 2026-11-05  
**Workspace:** `D:\data\agent_ai`  
**Branch:** `feature/aira-phase-f1-rbac-redesign`  
**Status:** COMPLETE (Phase 1)

---

## 1. Executive Overview

This discovery audit investigates the actual implementation of:
1. **Memory Subsystem** (long-term facts, preferences, user data isolation)
2. **Persona Subsystem** (behavior profiles, system prompt builders, custom personas, presets)
3. **Dynamic Interaction Orchestrator (DIO)** (interactive UI form generation, clarification engine, tool execution, parameter resolution)
4. **Identity & Session Management** (user account state, session accumulation, single-session lifecycle)

All components were analyzed via physical codebase inspection, SQLite schema verification, API router mappings, and execution flow tracing.

---

## 2. Component Inventory & Audit Map

### 2.1 Memory Subsystem
| Component | Physical Location | Status & Role |
|---|---|---|
| User Memory Service | `core/tenant/memory_service.py` | **Authoritative**. Multi-tenant isolated service. Enforces logical isolation per `user_id`. Tables: `user_memories`, `user_preferences`. |
| Personalization API Router | `api/routers/personalization.py` | **Authoritative**. Full CRUD (`/api/v1/personalization/memories`), summary, category filters, importance scoring. Requires Bearer token. |
| Legacy Memory Router | `api/routers/memory.py` | **Legacy (Phase A/B)**. Global unisolated facts (`/api/memory/facts`) storing to `database/long_term_memory.db`. |
| Frontend Memory Page | `app/frontend/src/pages/MemoryPage.jsx` | Standalone UI for legacy memory facts. |
| Settings Memory Tab | `app/frontend/src/pages/SettingsPage.jsx` | Embedded in Settings. Interfaced with `api.personalization.*`. |

### 2.2 Persona Subsystem
| Component | Physical Location | Status & Role |
|---|---|---|
| User Persona Service | `core/tenant/persona_service.py` | **Authoritative**. Manages 5 built-in presets (`user_id IS NULL`) + user custom personas (`user_id = ?`). Table: `user_personas`. |
| Personalization Router | `api/routers/personalization.py` | **Authoritative**. Endpoints: `/api/v1/personalization/personas`, `/active`, `/duplicate`, `/preview`. |
| Legacy Persona Page | `app/frontend/src/pages/PersonaPage.jsx` | Standalone page with behavior sliders and preset cards. |
| Settings Persona Tab | `app/frontend/src/pages/SettingsPage.jsx` | Embedded in Settings. Features active persona card, preset activation, custom persona creation, prompt preview, custom instructions. |

### 2.3 Dynamic Interaction Orchestrator (DIO)
| Component | Physical Location | Status & Role |
|---|---|---|
| Core DIO Models | `core/dio/models.py` | Data structures: `InteractionSchema`, `InteractionPlan`, `MissingField`, `ChoiceOption`, `InteractionState`. |
| Core DIO Builder | `core/dio/builder.py` | Converts `InteractionPlan` into concrete UI schemas (`MODE_FORM`, `MODE_CHOICE`, `MODE_LOCATION_PERMISSION`). |
| Core DIO Validator | `core/dio/validator.py` | Structural validation of generated interaction schemas. |
| Core DIO Analyzer | `core/dio/analyzer.py` | Analyzes missing fields and known data from planner output. |
| Core DIO Reasoning | `core/dio/reasoning.py` | Mode selection heuristics (`select_mode`). |
| Interaction Memory | `core/dio/interaction_memory.py` | Key-value state storage for active interaction forms (`database/interaction_memory.db`). |
| REI DIO Tools | `agents/rei/dio_tools.py` | `request_structured_input()`, `submit_structured_input()`, `request_device_choice()`, `resolve_submission()`. |
| Planner Integration | `agents/rei/planner.py` | Detects `result.get("interaction_schema")`, stops execution loop, yields interactive UI form to client. |
| Orchestrator Integration | `core/orchestrator.py` | `_execute_tool()` and `_prepare_device_args()`. Currently limited to `device_name` check rather than universal parameter resolution. |

---

## 3. Critical Defects Identified

### DEFECT-01 (CRITICAL — Fixed): Account Disable/Enable Toggle Failure
* **Location:** `AIRA_ECOSYSTEM/api/routers/admin_platform.py` line 287 vs `api/routers/user_management.py` line 81.
* **Evidence:** Both routers registered `GET /users` under prefix `/api/v1/admin`. Because `admin_platform.router` was included first in `main.py`, its legacy endpoint shadowed `user_management.py`.
* **Impact:** The legacy endpoint omitted `account_enabled`, `is_online`, and `groups` from the response. The frontend evaluated `!u.account_enabled` as `true`, marking all users as Disabled and rendering status toggles unresponsive.
* **Resolution:** Removed the shadowing endpoint in `admin_platform.py`. `GET /api/v1/admin/users` now routes directly to `user_management.py`, returning complete user status.

### DEFECT-02 (HIGH — Fixed): Active Session Accumulation (Missing Single-Session Displacement)
* **Location:** `AIRA_ECOSYSTEM/core/tenant/manager.py` in `create_session()`.
* **Evidence:** `create_session()` inserted a new `ACTIVE` session without revoking existing active sessions for that user, causing sessions to pile up (18 duplicate active sessions observed).
* **Impact:** Multiple unrevoked sessions per user, confusing administrators and violating the single-active-session policy.
* **Resolution:** Added atomic revocation of prior active sessions (`UPDATE operational_user_sessions SET status = 'REVOKED' WHERE user_id = ? AND status = 'ACTIVE'`) prior to inserting a new session.

### DEFECT-03 (MEDIUM — Fixed): Memory and Persona Consolidated into a Shared Tab
* **Location:** `AIRA_ECOSYSTEM/app/frontend/src/pages/SettingsPage.jsx`.
* **Evidence:** Memory and Persona were crammed inside a single tab (`personalization`), leading to clutter and poor discoverability.
* **Impact:** Violates the requirement that Memory and Persona exist as dedicated, distinct tabs within Settings.
* **Resolution:** Restructured `SettingsPage.jsx` with distinct `memory` and `persona` tabs, along with `general`, `security`, `account`, and `privacy`.

### DEFECT-04 (HIGH — In Progress): Incomplete Parameter Resolution Barrier in Orchestrator
* **Location:** `AIRA_ECOSYSTEM/core/orchestrator.py` in `_execute_tool()`.
* **Evidence:** Only `device_name` was resolved via `_prepare_device_args()`. Missing required parameters on other tools threw Python exceptions (`TypeError`), while unrecognized arguments caused keyword argument crashes.
* **Impact:** Risk of tool failures, parameter hallucinations, and unhandled missing parameter errors instead of clean DIO interactive form presentations.
* **Resolution:** Design and implement `DIOParameterResolver` to enforce strict 7-state classification, parameter provenance tracking, and automatic DIO interactive schema generation for missing/ambiguous inputs.

---

## 4. Discovery Conclusion

The architecture has solid foundational building blocks in `core/dio/`, `core/tenant/memory_service.py`, and `core/tenant/persona_service.py`. The primary missing bridge is an authoritative, universal **Parameter Resolution & Provenance Engine** integrated into `core/orchestrator.py` that enforces strict schema validation and interactive DIO prompts across all 60+ agent tools.
