# PHASE 8 — DUPLICATION, DEAD CODE & LEGACY AUDIT (`08_DUPLICATION_AND_UNUSED_CODE_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent`  
**Audit Mode**: Read-Only AST & Import-Graph Reachability Analysis

---

## 1. Duplicate Code & Parallel Subsystems Audit (Section A)

### 1.1 Backend Subsystem & Module Duplications (`CONFIRMED`)

| # | Duplicated Domain | File / Module A | File / Module B (and C/D) | Nature of Duplication & Runtime Impact |
|---:|---|---|---|---|
| 1 | **FastAPI Application Entrypoint** | [`api/main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/main.py) (345 lines — Active) | [`core/attachment/main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachment/main.py) (153 lines — Dead copy) | `core/attachment/main.py` is an older copy of `api/main.py` accidentally left inside `core/attachment/`. |
| 2 | **YUKI Kokoro TTS Engine** | [`agents/yuki/tts.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/yuki/tts.py) (182 lines — Active) | [`agents/yuki/tts_engine.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/yuki/tts_engine.py) (160 lines — Dead copy) | `tts.py` duplicates the entire Kokoro ONNX implementation (`_get_kokoro`, `speak`, `synthesize_bytes`) of `tts_engine.py`, leaving `tts_engine.py` 100% unused. |
| 3 | **Persona Module vs Package** | [`core/persona/`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/persona/__init__.py) (6-file package — Active) | [`core/persona.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/persona.py) (Shadowed single file) AND [`core/tenant/persona_service.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/persona_service.py) | Python resolves `import core.persona` to the directory package `core/persona/__init__.py`, making `core/persona.py` 100% unreachable. Meanwhile `core/persona/` (`persona.db`) and `core/tenant/persona_service.py` (`topology.db:user_personas`) duplicate persona management. |
| 4 | **SSH Connection Pooling & MikroTik Wrappers** | [`agents/akane/connection_manager.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/akane/connection_manager.py) (`ConnectionManager`) + [`agents/akane/network_tools.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/akane/network_tools.py) | [`tools/ssh/client.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/tools/ssh/client.py) (`_connections`) + [`tools/mikrotik/routeros.py:45-157`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/tools/mikrotik/routeros.py#L45-L157) | Two uncoordinated SSH pools. All 12 `get_*` functions in `tools/mikrotik/routeros.py:45-157` are dead because callers only import `COMMANDS` (`L4-42`) and execute via `ConnectionManager`. |
| 5 | **NMS v1 vs NMS v2 Package** | [`core/nms_engine.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/nms_engine.py), `nms_models.py`, `nms_snmp.py` (Active) | [`core/nms/`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/nms/__init__.py) (`scheduler.py`, `monitoring.py`, `capability.py`, `alerts.py`, `metrics_store.py`) | `HardenedNmsScheduler`, `PollingSelfMonitor`, `CapabilityDiscoveryService`, and `AlertEngine` in `core/nms/` are unused in production (only tested in `tests/`). |
| 6 | **Network Intelligence Generational Triplication** | Gen 1: `models.py`, `evidence.py`, `store.py` (`network_intelligence.db`) | Gen 2: `network_models.py`, `correlation.py`, `auto_orchestrator.py`<br>Gen 3: `intelligence_models.py`, `evidence_service.py`, `correlation_engine.py`, `investigator.py` | Three generations of models, evidence collectors, correlators, and NL diagnostic orchestrators coexist in `core/network_intelligence/`. |
| 7 | **Security Posture Auditors** | [`core/network_intelligence/security.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/security.py) (`SecurityAuditor`) | [`core/network_intelligence/security_baseline.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/security_baseline.py) (`SecurityBaselineEngine`) | Two separate RouterOS security auditors exposed on adjacent routes (`/api/intelligence/security/audit` vs `/api/intelligence/security/scan`). |
| 8 | **Operational Incident Engines** | [`core/operations/incident_engine.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/operations/incident_engine.py) (`ProactiveIncidentEngine`, tenant-unaware) | [`core/operations/multi_tenant_incident_engine.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/operations/multi_tenant_incident_engine.py) (`MultiTenantIncidentEngine`, tenant-scoped) | Both read/write `operational_incidents` in `topology.db` with conflicting `tenant_id` behavior (`NULL` vs required `tenant_id`). |
| 9 | **Health Scoring Engines (4 Implementations)** | `TopologyEngine.calculate_health_score()` (`topology_engine.py:4717`) | `NetworkHealthEngine` (`health_engine.py:40`), `DynamicHealthScoringEngine` (`health_scoring_engine.py:46`), `ServiceIntelligenceEngine.evaluate_service_health()` (`service_intelligence.py:290`) | Four separate health score calculators across Topology, Intelligence, Operations, and Services. |
| 10 | **Blast-Radius & Failure Simulators (5 Implementations)** | `TopologyEngine.analyze_change_impact()` (`topology_engine.py:4567`) | `FailurePropagationAnalyzer` (`route_dependency.py:968`), `ImpactAnalyzer` + `FailureSimulator` (`impact_analyzer.py`, `failure_simulator.py`), `ChangeImpactEngine` (`change_impact_engine.py`), `RiskAssessmentEngine` (`risk_engine.py`) | Five overlapping failure/impact simulators across 4 packages. |
| 11 | **Scheduler Engines (2 Implementations)** | [`core/scheduler.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/scheduler.py) (`AutomationScheduler` -> `automation_jobs`) | [`core/operations/scheduler.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/operations/scheduler.py) (`OperationalSchedulerEngine` -> `operational_jobs`) | Two separate scheduler engines and tables in `topology.db`, both filled with dummy 1-line lambda actions. |
| 12 | **Playbook Engines (2 Implementations)** | [`core/network_intelligence/playbooks.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/playbooks.py) (`PlaybookEngine`) | [`core/playbooks/runner.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/playbooks/runner.py) (`PlaybookRunner`) | Two separate playbook engines (`/api/intelligence/playbooks` vs `/api/v1/playbooks`). |

### 1.2 Frontend Duplications (`CONFIRMED`)
1. **Byte-for-Byte Duplicate Location Service**: [`src/service.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/service.js) (128 lines) is an exact copy of [`src/services/location.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/services/location.js) (128 lines).
2. **Duplicate `request()` Fetch Wrappers**: Duplicated across `src/api.js:35-91`, `src/inventoryApi.js:8-35`, `src/modelRouterApi.js:8-32`, `src/services/location.js:12-28`, `src/services/settingsApi.js:5-19`, `src/components/topology/topologyHistoryApi.js:6-18`, and `src/components/topology/routeHistoryApi.js:6-18`.
3. **Duplicate UI Components**: Detailed in `05_FRONTEND_AUDIT.md` Section 2 (`BootScreen.jsx` x2, `CapabilityHeroRow` x2, `WorkspacePage.jsx` x2, `Hero.jsx` vs `DynamicHero.jsx`, `WorkspaceCockpit.jsx` vs `ComposerCockpit.jsx`, 5 Login modals/pages, 3 Voice subsystems).

---

## 2. Unused Files Inventory (Section B — With Confidence Levels)

### 2.1 Backend Unused Python Files (22 Files)

| # | File Path | Category | Imported in Prod? | Imported in Tests? | Confidence | Evidence & Explanation |
|---:|---|---|---|---|---|---|
| 1 | `AIRA_ECOSYSTEM/core/persona.py` | Shadowed Module | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Shadowed by package directory `AIRA_ECOSYSTEM/core/persona/__init__.py`. |
| 2 | `AIRA_ECOSYSTEM/core/attachment/main.py` | Misplaced File | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Obsolete copy of `api/main.py` inside `core/attachment/`. |
| 3 | `AIRA_ECOSYSTEM/agents/yuki/tts_engine.py` | Duplicate Engine | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Superseded by `agents/yuki/tts.py`; zero imports anywhere in repo. |
| 4 | `AIRA_ECOSYSTEM/agents/rei/settings_tools.py` | Unregistered Tools | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Docstring (`L14-19`) notes tools were intentionally excluded from `agents/rei/registry.py`. |
| 5 | `AIRA_ECOSYSTEM/core/bootstrap_superadmin.py` | Standalone Script | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Superseded by `core/tenant/seed_admin.py` (`api/main.py:165`); contains hardcoded fallback password. |
| 6 | `AIRA_ECOSYSTEM/core/tenant/context.py` | Unused Module | **NO** | **NO** | **HIGH (`CONFIRMED`)** | `ContextVar` tenant context never imported by any router or service. |
| 7 | `AIRA_ECOSYSTEM/core/tenant/entitlement_service.py` | Duplicate Service | **NO** | **NO** | **HIGH (`CONFIRMED`)** | Superseded by `core/tenant/entitlements.py` (`EntitlementManager`). |
| 8 | `AIRA_ECOSYSTEM/core/tenant/workspace_service.py` | Unwired Service | **NO** | `test_phase_f_enterprise_hardening.py` | **HIGH (`CONFIRMED`)** | Per-tenant workspace isolation service never wired into `api/routers/files.py` or `core/filesystem/manager.py`. |
| 9 | `AIRA_ECOSYSTEM/core/security/ssrf_validator.py` | Unwired Security | **NO** | `test_phase_h_security_and_governance.py` | **HIGH (`CONFIRMED`)** | SSRF validator never imported by any production module (`tools/web/search.py` or `provider_client.py`). |
| 10 | `AIRA_ECOSYSTEM/core/nms/scheduler.py` | Unwired Engine | **NO** | `test_phase_4_3_nms_telemetry.py` | **HIGH (`CONFIRMED`)** | `HardenedNmsScheduler` is only used in unit tests; production uses `core/nms_engine.py`. |
| 11 | `AIRA_ECOSYSTEM/core/nms/alerts.py` | Unwired Engine | **NO** | `test_phase_4_3_nms_telemetry.py` | **HIGH (`CONFIRMED`)** | `AlertEngine` is only used in unit tests; production uses `core/nms_engine.py`. |
| 12 | `AIRA_ECOSYSTEM/core/nms/capability.py` | Unwired Engine | **NO** | `test_phase_4_3_nms_telemetry.py` | **HIGH (`CONFIRMED`)** | `CapabilityDiscoveryService` is only used in unit tests. |
| 13 | `AIRA_ECOSYSTEM/core/edge_gateway/buffer.py` | Edge Agent Lib | **NO** | `test_phase_8_edge_gateway.py` | **HIGH (`CONFIRMED`)** | Edge-side SQLite buffer class (`edge_buffer.db`), not used by central server runtime. |
| 14 | `AIRA_ECOSYSTEM/core/edge_gateway/collector.py` | Edge Agent Lib | **NO** | `test_phase_8_edge_gateway.py` | **HIGH (`CONFIRMED`)** | Edge-side diagnostic collector (with broken Windows `ping -n` flags), not used by central server runtime. |
| 15 | `AIRA_ECOSYSTEM/core/network_intelligence/change_detector.py` | Unwired Engine | **NO** | `test_phase_5_network_intelligence.py` | **HIGH (`CONFIRMED`)** | `NetworkChangeDetector` is only imported in `core/network_intelligence/__init__.py` and tests. |
| 16 | `AIRA_ECOSYSTEM/core/plugins/loader.py` & `validator.py` | Unwired Subsystem | **NO** | `test_phase_g_productization.py` | **HIGH (`CONFIRMED`)** | Plugin loader/validator never called in `api/main.py` or `core/orchestrator.py`. |
| 17–23 | `scratch/*.py` (7 root scripts: `audit_System.py`, `fix_indent.py`, `patch_orch.py`, `patch_routes.py`, `test_imports.py`, `test_phase_f1_e2e.py`, `verify_phase_f1.py`) | Developer Scratch | **NO** | **NO** | **HIGH (`CONFIRMED`)** | One-off developer regex patchers and manual verification scripts in root `scratch/`. |

### 2.2 Frontend Unused Files in `app/frontend/src/` (20 Files)

All 20 files below have **zero incoming imports** from `src/main.jsx` or any reachable component (`Confidence: HIGH (CONFIRMED)`):
1. `src/benchmark_svg_performance.js`
2. `src/service.js`
3. `src/capabilities/CapabilityHeroRow (1).jsx`
4. `src/components/ThinkingIndicator.jsx`
5. `src/components/auth/LoginRequiredModal.jsx`
6. `src/components/auth/RegisterModal.jsx`
7. `src/components/capabilities/FileCapabilityActions.jsx`
8. `src/components/cockpit/WorkspaceCockpit.jsx`
9. `src/components/cockpit/index.js`
10. `src/components/cockpit/mockData.js`
11. `src/components/workspace/WorkspacePage.jsx`
12. `src/hooks/useAiraSocket.js`
13. `src/pages/dio/DioPreviewPage.jsx`
14. `src/theme/index.js`
15. `src/theme/colors.js`
16. `src/theme/radius.js`
17. `src/theme/shadow.js`
18. `src/theme/spacing.js`
19. `src/theme/typography.js`
20. `src/types/modelRouter.d.ts`

---

## 3. Unused Functions, Variables, Props, State & Unreachable Code (Section C)

1. **Unreachable Dead Conditional Branches in `api/routers/gateways.py:72-89` & `api/routers/decisions.py:83-98` (`CONFIRMED`)**:
   ```python
   if not authorization or not authorization.startswith("Bearer "):
       if authorization and authorization.startswith("Bearer aira_tok_"):
           # 100% UNREACHABLE: cannot start with "Bearer aira_tok_" if not startswith("Bearer ")!
   ```
2. **Shadowed FastAPI Route Handlers (`CONFIRMED`)**:
   - `api/routers/user_management.py:368-382` (`simulate_permissions`) — shadowed by `api/routers/admin_platform.py:385`.
   - `api/routers/network_intelligence.py:1586-1591` (`get_action_policy`) — shadowed by `api/routers/network_intelligence.py:1556` (`get_action`).
3. **Unused Functions in `tools/` (`CONFIRMED`)**:
   - `tools/mikrotik/routeros.py:45-157`: `execute_mikrotik_tool` and all 12 `get_*` functions (`get_interfaces`, `get_ip_addresses`, `get_routes`, `get_firewall_filter`, etc.) have zero callers.
   - `tools/snmp/client.py:235-262`: `snmp_get()` and `snmp_walk()` have zero callers.
   - `tools/ssh/shell.py:292-306`: `PersistentShell._read_until_idle()` has zero callers.
4. **Unused Instantiated Services & Variables (`CONFIRMED`)**:
   - `api/routers/chat.py:28`: `_quota_service = TokenQuotaService()` is instantiated at module level and never referenced anywhere in `chat.py`.
   - `api/routers/auth.py:26-29`: `_tenant_mgr`, `_entitlement_mgr`, `_sub_service`, `_quota_service` are instantiated at module level and never used in `auth.py`.
   - `api/routers/logs.py:48`: `logs = log_store.query_logs(limit=1, offset=0)` is executed and immediately overwritten/ignored on line 50 (`all_logs = log_store.query_logs(limit=500)`).
   - `agents/akane/config_engine.py:135`: `masked_data = _mask_sensitive(data)` is computed and never written to disk (`data` is written twice at `L142` and `L147`).
5. **Unused Frontend State, Hooks & JSX (`CONFIRMED`)**:
   - `src/pages/ChatPage.jsx:73, 77, 85, 239, 247, 536`: Imports `DynamicHero`, computes `heroModel` via `useCockpitData()`, and mounts `<VoiceOverlay>` / `useVoiceCall()`, none of which are ever triggered or rendered in active UI flows.
   - `src/context/ChatRuntimeContext.jsx:43, 203-209`: Imports `createStreamBatcher` and `isStreamEvent` and initializes `batcherRef.current`, but never calls `batcherRef.current.push()` or `isStreamEvent()`.
   - `src/pages/SettingsPage.jsx:83-110, 288-380, 961-1093, 1262-1415`: ~400 lines of unreachable JSX and state for `"subscription"` tab, `"token_usage"` tab, and legacy Persona modals.

---

## 4. Legacy Code & Backup Artifacts Audit (Section D)

1. **`_legacy_backup_20260910_143345/` (27 Files in Repository Root — `CONFIRMED`)**:
   - Contains pre-consolidation root scripts (`run_web.py`, `run_chat.py`, `verify_phase1_to_4.py`), duplicate tests (`tests/test_capabilities.py`, `tests/test_dio_pipeline.py`), old database copies (`database/chat_sessions.db`, `database/long_term_memory.db`), and PowerShell migration scripts (`migrate_phase2_merge.ps1`–`migrate_phase7_cleanup.ps1`).
2. **Tracked SQLite `.db.old` Backup Files (`CONFIRMED`)**:
   - `AIRA_ECOSYSTEM/database/chat_sessions.db.old` and `AIRA_ECOSYSTEM/database/long_term_memory.db.old` are tracked in Git.
3. **Decommissioned Vision Agent (`AIRA_ECOSYSTEM/agents/hikari/` — `CONFIRMED`)**:
   - `agents/hikari/__init__.py` and `agents/hikari/registry.py` contain only empty dictionaries (`HIKARI_TOOLS = {}`) after camera/YOLO vision modules were removed, yet are still imported by `core/orchestrator.py:44`.
4. **Root Windows Consolidation Script (`consolidate_to_aira.ps1` — `CONFIRMED`)**:
   - One-time PowerShell migration script in repository root from the September 2026 directory restructuring.
