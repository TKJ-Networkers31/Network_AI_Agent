# PHASE 1 — REPOSITORY DISCOVERY & COMPLETE INVENTORY

- **Repository Root:** `/home/Lingga/Documents/project/Network_AI_Agent`
- **Primary Application Directory:** `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM`
- **Audit Mode:** Read-Only Static & Non-Destructive Inspection

---

## 1. Executive Summary of Repository Structure

The repository is a monorepo transitioning from an earlier root-level Python layout (`agent/`, `backend/`, `tools/`, `scripts/`) into a consolidated application tree under [`AIRA_ECOSYSTEM/`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM). While the consolidation script ([`consolidate_to_aira.ps1`](file:///home/Lingga/Documents/project/Network_AI_Agent/consolidate_to_aira.ps1)) moved active code into `AIRA_ECOSYSTEM/`, it left behind a tracked backup folder ([`_legacy_backup_20260910_143345/`](file:///home/Lingga/Documents/project/Network_AI_Agent/_legacy_backup_20260910_143345)), ad-hoc verification scripts in [`scratch/`](file:///home/Lingga/Documents/project/Network_AI_Agent/scratch), and AST analysis outputs in [`graphify-out/`](file:///home/Lingga/Documents/project/Network_AI_Agent/graphify-out).

### High-Level Directory Map

```text
/home/Lingga/Documents/project/Network_AI_Agent/
├── .claude/                              # Claude Code local IDE configuration
├── .github/workflows/                    # GitHub Actions CI/CD pipeline (ci.yml)
├── AIRA_ECOSYSTEM/                       # Main application root
│   ├── agents/                           # Internal specialist AI agents
│   │   ├── akane/                        # Network engineering, SSH/SNMP, safe config & reasoning
│   │   ├── hikari/                       # Vision/multimodal stub registry
│   │   ├── rei/                          # Executive planner, LLM provider client, tool registries
│   │   └── yuki/                         # Voice interface (Faster-Whisper STT, Kokoro ONNX TTS)
│   ├── api/                              # FastAPI application, WebSocket manager/bridge & 31 routers
│   │   └── routers/                      # REST & WebSocket API route modules (+ router test)
│   ├── app/                              # Frontend root
│   │   └── frontend/                     # React 18 + Vite 8 + Tailwind CSS v4 Single-Page Application
│   │       ├── public/                   # Brand assets, animations, favicons, PWA manifest, SW
│   │       └── src/                      # Pages, components, contexts, hooks, stores, utils, API clients
│   ├── core/                             # Core backend domain & business logic (27 subpackages + root modules)
│   │   ├── ai/                           # Core AI reasoning engine
│   │   ├── artifacts/                    # Document artifact generation (CSV, DOCX, PDF, PPTX, XLSX, TXT)
│   │   ├── attachment/                   # [LEGACY/ARTIFACT] Stray zip archive & obsolete api/main.py copy
│   │   ├── attachments/                  # Universal attachment engine, validator, store (+ stray mnt/ folder)
│   │   ├── billing/                      # Billing products, plans, invoices, webhook processing
│   │   ├── capability/                   # Dynamic capability registry, discovery & frontend contract
│   │   ├── context/                      # Prompt context builder
│   │   ├── dio/                          # Dynamic Interactive Objects (schema, builder, analyzer, memory)
│   │   ├── edge_gateway/                 # Remote Edge Gateway enrollment, telemetry ingestion & SQLite buffer
│   │   ├── external_context/             # Google Maps & OpenStreetMap (Nominatim/Overpass) providers
│   │   ├── file_processing/              # Archive extraction, OCR (Tesseract), PDF/Office & Vision LLM
│   │   ├── filesystem/                   # Workspace sandboxed file operations, permissions, history, trash
│   │   ├── host/                         # Linux/Windows host OS adapters & hardware/network detectors
│   │   ├── location/                     # Host & browser geolocation store and service
│   │   ├── mcp/                          # Model Context Protocol (MCP) client
│   │   ├── network_intelligence/         # Multi-device collector, knowledge graph, RCA, path, protocols
│   │   ├── nms/                          # Telemetry poller, scheduler, monitoring, alerts, metrics store
│   │   ├── operations/                   # NOC incident engine, approvals, SLA, risk, calendar, notifications
│   │   ├── persona/                      # YAML-driven persona engine, emotion/behavior scales, styles
│   │   ├── playbooks/                    # Built-in remediation playbooks & runner
│   │   ├── plugins/                      # Plugin manifest loader, interface & validator
│   │   ├── routing/                      # Unified RouterOS v6/v7 route parser, analytics, history, dependency
│   │   ├── runtime_state/                # Runtime state engine & models
│   │   ├── security/                     # Password hashing, MFA (TOTP), rate limiter, SSRF, output guard
│   │   ├── selection/                    # UI text/element selection context store & builder
│   │   ├── semantic_memory/              # Vector/semantic memory embedder, retriever, scorer, store
│   │   ├── tenant/                       # Multi-tenant DB, Auth, RBAC, Subscriptions, Quotas, Entitlements
│   │   ├── unified_context/              # Unified context builder combining memory, persona, location
│   │   └── workspace_links/              # External directory symlink/workspace link registry
│   ├── database/                         # SQLite database files (.db, .db.old) & baseline manifest
│   ├── docs/NETWORKING_VI/               # Benchmark result JSON inside AIRA_ECOSYSTEM
│   ├── logs/                             # Runtime application & category log files
│   ├── mcp_servers/network/              # Local MCP network server & security validator
│   ├── reports/                          # Networking VIII benchmark JSON reports
│   ├── scripts/                          # Maintenance, reset, cleanup & benchmark scripts
│   ├── tests/                            # Pytest suite (111 test scripts + RouterOS v6/v7 fixtures)
│   └── tools/                            # Low-level SSH, SNMP, MikroTik RouterOS, Network & Web Search tools
├── _legacy_backup_20260910_143345/       # Legacy pre-consolidation backup committed to Git (27 files)
├── deploy/nginx/                         # Nginx production reverse proxy configuration
├── docs/                                 # Project architecture, security, stabilization & phase reports (259 files)
├── graphify-out/                         # Generated AST code graph & community analysis artifacts
└── scratch/                              # Ad-hoc developer test, live router & monkey-patch scripts (7 files)
```

---

## 2. Quantitative Repository Inventory (Section 3.C Metrics)

### 2.1 Overall Counts

| Metric | Count | Notes |
|---|---:|---|
| **Total Files in Workspace (Including Excluded Dirs)** | **3,831** | Includes `.venv` (2,119), `graphify-out/cache` (410), `__pycache__` (94), `.git` (28) |
| **Total Project Files Inspected & Classified (Excluding Caches/Venv/Git)** | **1,180** | 100% of non-excluded files accounted for below |
| **Total Included Subdirectories** | **164** | Plus workspace root (`.`) = 165 directory nodes |
| **Backend Files (Non-Test Python, YAML, MCP, Scripts)** | **386** | Under `AIRA_ECOSYSTEM/{agents,api,core,mcp_servers,scripts,tools}` + root entrypoints |
| **Frontend Files (All Files Under `AIRA_ECOSYSTEM/app/`)** | **263** | 223 files in `src/` (208 source + 15 `.test.js`), 31 in `public/`, 9 config/lock/docs |
| **Database-Related Files** | **17** | 8 files in `AIRA_ECOSYSTEM/database/` (excluding README) + 9 DB/store layer Python modules |
| **Test Files (Test Suites + Test Fixtures)** | **201** | 153 test code files (138 Python pytest + 15 JS test files) + 48 RouterOS test fixtures |
| **Configuration Files** | **28** | Docker, Nginx, CI, Env, Pytest, Python requirements, NPM/Vite/Tailwind, Persona YAMLs |
| **Unclassified / Unknown Files** | **0** | Every file in the repository has been deterministically classified |

### 2.2 Excluded Directories & Justification

| Excluded Directory | File Count | Reason for Exclusion from Source Count |
|---|---:|---|
| `.venv/` | 2,119 | Local Python 3.12 virtual environment containing third-party PyPI packages |
| `graphify-out/cache/` | 410 | Cached AST parse objects generated by external `graphify` tool |
| `**/__pycache__/` (13 dirs) | 94 | Compiled Python bytecode (`.pyc`) generated at runtime |
| `.git/` | 28 | Git internal object store, refs, hooks, and packfiles |
| `node_modules/` | 0 | Not currently installed on disk; excluded by policy |
| `AIRA_ECOSYSTEM/app/frontend/dist/` | 0 | Not currently built on disk; excluded by policy |

---

## 3. File Classification by Audit Category (Section 3.B)

Every one of the **1,180 included project files** is classified into one of the 10 mandatory audit categories:

| # | Category | File Count | Breakdown & Evidence |
|---|---|---:|---|
| **1** | **Active Source Code** | **600** | • Backend Python modules in `AIRA_ECOSYSTEM/api/` (42), `agents/` (30), `core/` (278), `tools/` (13), `mcp_servers/` (4), `scripts/` (10), `run_chat.py` (1)<br>• Frontend active source & assets in `AIRA_ECOSYSTEM/app/frontend/src/` (203) and `public/` (29) |
| **2** | **Configuration** | **28** | • Root: [`Dockerfile`](file:///home/Lingga/Documents/project/Network_AI_Agent/Dockerfile), [`docker-compose.yml`](file:///home/Lingga/Documents/project/Network_AI_Agent/docker-compose.yml), [`.dockerignore`](file:///home/Lingga/Documents/project/Network_AI_Agent/.dockerignore), [`.gitignore`](file:///home/Lingga/Documents/project/Network_AI_Agent/.gitignore), [`.gitattributes`](file:///home/Lingga/Documents/project/Network_AI_Agent/.gitattributes), [`.env.example`](file:///home/Lingga/Documents/project/Network_AI_Agent/.env.example), [`pytest.ini`](file:///home/Lingga/Documents/project/Network_AI_Agent/pytest.ini), [`requirements.txt`](file:///home/Lingga/Documents/project/Network_AI_Agent/requirements.txt), [`requirements-web.txt`](file:///home/Lingga/Documents/project/Network_AI_Agent/requirements-web.txt)<br>• IDE & CI: [`.claude/settings.json`](file:///home/Lingga/Documents/project/Network_AI_Agent/.claude/settings.json), [`.github/workflows/ci.yml`](file:///home/Lingga/Documents/project/Network_AI_Agent/.github/workflows/ci.yml)<br>• Deployment: [`deploy/nginx/aira_customer_portal.conf`](file:///home/Lingga/Documents/project/Network_AI_Agent/deploy/nginx/aira_customer_portal.conf), [`AIRA_ECOSYSTEM/scripts/download_kokoro_model.ps1`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/scripts/download_kokoro_model.ps1)<br>• Frontend Configs: `package.json`, `package-lock.json`, `vite.config.js`, `tailwind.config.js`, `jsconfig.json`, `.npmrc`, `.gitignore`, `manifest.json`, 2× `site.webmanifest`<br>• Persona YAML Configs (6 files): `behavior.yaml`, `identity.yaml`, `tone.yaml`, `styles/{akane,companion,sensei}.yaml` |
| **3** | **Database** | **7** | • Active SQLite DB files & manifest in [`AIRA_ECOSYSTEM/database/`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/database): `topology.db` (614 KB, 38 tables), `model_router.db` (28 KB, 3 tables), `chat_sessions.db` (24 KB, 2 tables), `logs.db` (24 KB, 1 table), `long_term_memory.db` (20 KB, 2 tables), `snapshot_baseline_manifest.json`, `.gitkeep`<br>*(Note: 9 Python DB/Store access modules are counted under Active Source Code and cross-listed in Domain Counts)* |
| **4** | **Test** | **201** | • Root & API Conftest: [`conftest.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/conftest.py), [`AIRA_ECOSYSTEM/tests/conftest.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/tests/conftest.py)<br>• Main Backend Test Suite (`AIRA_ECOSYSTEM/tests/`): 95 pytest modules + 48 RouterOS v6/v7 & synthetic route fixtures<br>• Core Subpackage Unit Tests: `core/artifacts/tests/` (4), `core/attachments/tests/` (5), `core/capability/tests/` (5), `core/dio/tests/` (9), `core/external_context/tests/` (6), `core/file_processing/test_processor.py` (1), `core/filesystem/test_workspace_and_operations.py` (1), `core/host/test_host_adapters.py` (1), `core/selection/tests/` (1), `core/unified_context/tests/` (1), `core/workspace_links/tests/` (3), `api/routers/tests/test_capabilities.py` (1)<br>• Frontend Unit Tests (`app/frontend/src/**/*.test.js`): 15 test files |
| **5** | **Documentation** | **266** | • Root: [`CLAUDE.md`](file:///home/Lingga/Documents/project/Network_AI_Agent/CLAUDE.md)<br>• `AIRA_ECOSYSTEM/`: `README.md`, `MIGRATION_PLAN.md`, `api/routers/README.md`, `app/README.md`, `database/README.md`, `tools/README.md`<br>• [`docs/`](file:///home/Lingga/Documents/project/Network_AI_Agent/docs): 259 Markdown files across architecture, security, audit, deployment, stabilization, and Networking III–VIII specifications |
| **6** | **Build / Generated Artifact** | **32** | • [`graphify-out/`](file:///home/Lingga/Documents/project/Network_AI_Agent/graphify-out): 18 AST graph JSON/HTML/Markdown files<br>• [`AIRA_ECOSYSTEM/logs/`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/logs): 3 runtime log files (`aira.log`, `categories/chat_sessions.log`, `categories/system.log`)<br>• Benchmark & Phase Output Artifacts: `PHASE_E1_COMPLETION_REPORT.txt`, `PHASE_F1_COMPLETION_REPORT.txt`, `PHASE_F_COMPLETION_REPORT.txt`, `AIRA_ECOSYSTEM/reports/*.json` (2), `AIRA_ECOSYSTEM/docs/NETWORKING_VI/benchmark_results.json`, `AIRA_ECOSYSTEM/scripts/benchmark_gateway_results.json`, `docs/sprint-2.5-streaming.patch`<br>• Stray Container Archives/Paths: [`AIRA_ECOSYSTEM/core/attachment/files.zip`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachment/files.zip), [`AIRA_ECOSYSTEM/core/semantic_memory/files.zip`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/semantic_memory/files.zip), [`docs/mnt/user-data/outputs/aira_docs/docs/README.md`](file:///home/Lingga/Documents/project/Network_AI_Agent/docs/mnt/user-data/outputs/aira_docs/docs/README.md) |
| **7** | **Legacy** | **29** | • [`_legacy_backup_20260910_143345/`](file:///home/Lingga/Documents/project/Network_AI_Agent/_legacy_backup_20260910_143345): 27 pre-consolidation Python files (`agent/`, `backend/`, `scripts/`, `tools/`)<br>• Pre-migration SQLite backups in `AIRA_ECOSYSTEM/database/`: `chat_sessions.db.old`, `long_term_memory.db.old` (both tracked in Git!) |
| **8** | **Potentially Unused** | **17** | • [`scratch/`](file:///home/Lingga/Documents/project/Network_AI_Agent/scratch) (7 ad-hoc scripts: `check_db.py`, `check_inventory.py`, `patch_routes.py`, `test_live_connect.py`, `test_live_parser.py`, `verify_phase2_e2e.py`, `verify_phase5_simulation.py`)<br>• [`consolidate_to_aira.ps1`](file:///home/Lingga/Documents/project/Network_AI_Agent/consolidate_to_aira.ps1) (one-off Windows migration script)<br>• [`AIRA_ECOSYSTEM/test_events_manual.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/test_events_manual.py)<br>• [`AIRA_ECOSYSTEM/core/attachment/main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachment/main.py) (stray old copy of `api/main.py`)<br>• [`AIRA_ECOSYSTEM/core/attachments/mnt/user-data/outputs/AIRA_ECOSYSTEM/core/attachments/tests/__init__.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachments/mnt/user-data/outputs/AIRA_ECOSYSTEM/core/attachments/tests/__init__.py)<br>• [`AIRA_ECOSYSTEM/app/package-lock.json`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/package-lock.json) (orphaned lockfile outside `app/frontend/`)<br>• [`AIRA_ECOSYSTEM/app/frontend/src/capabilities/CapabilityHeroRow (1).jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/capabilities/CapabilityHeroRow%20(1).jsx) (duplicate copy with `(1)` in name)<br>• [`AIRA_ECOSYSTEM/app/frontend/src/components/BootScreen.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/BootScreen.jsx) (superseded by `components/boot/BootScreen.jsx`)<br>• [`AIRA_ECOSYSTEM/app/frontend/src/components/workspace/WorkspacePage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/workspace/WorkspacePage.jsx) (superseded by `pages/WorkspacePage.jsx`)<br>• [`AIRA_ECOSYSTEM/app/frontend/src/Hero.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/Hero.jsx)<br>• [`AIRA_ECOSYSTEM/app/frontend/src/benchmark_svg_performance.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/benchmark_svg_performance.js) *(Note: additional unreferenced frontend/backend modules are detailed in Report 08)* |
| **9** | **External Dependency** | **0** | Excluded directories (`.venv`, `node_modules`) are tracked separately in Section 2.2 |
| **10** | **Unknown / Requires Investigation** | **0** | All 1,180 files have been inspected and categorized |
| | **TOTAL** | **1,180** | |

---

## 4. Subsystem-by-Subsystem File Inventory (`AIRA_ECOSYSTEM/`)

### 4.1 Backend API & WebSockets (`AIRA_ECOSYSTEM/api/` — 44 Files)
- **Core API Files (6):** [`__init__.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/__init__.py), [`main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/main.py), [`schemas.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/schemas.py), [`state.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/state.py), [`ws_bridge.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/ws_bridge.py), [`ws_manager.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/ws_manager.py)
- **Routers (`api/routers/` — 36 Python files + 1 README + 1 Test):**
  `admin_platform.py`, `artifacts.py`, `attachments.py`, `auth.py`, `automations.py`, `billing.py`, `capabilities.py`, `capabilities_logic.py`, `chat.py`, `connections.py`, `decisions.py`, `devices.py`, `files.py`, `gateways.py`, `location.py`, `logs.py`, `memory.py`, `models.py`, `network_intelligence.py`, `nms.py`, `operations.py`, `personalization.py`, `persona.py`, `playbooks.py`, `portal.py`, `providers.py`, `selection.py`, `sessions.py`, `settings.py`, `tools.py`, `topology.py`, `user_management.py`, `voice.py`, `workspace_links.py`, `ws.py`, `__init__.py`

### 4.2 Specialist Agents (`AIRA_ECOSYSTEM/agents/` — 30 Files)
- **AKANE (`agents/akane/` — 7 files):** `config_engine.py`, `connection_manager.py`, `network_tools.py`, `reasoning_engine.py`, `registry.py`, `session_state.py`, `__init__.py`
- **HIKARI (`agents/hikari/` — 2 files):** `registry.py`, `__init__.py`
- **REI (`agents/rei/` — 13 files):** `artifact_tools.py`, `auto_extract.py`, `conversation_tools.py`, `dio_tools.py`, `fs_tools.py`, `inventory_tools.py`, `maps_tools.py`, `planner.py`, `provider_client.py`, `registry.py`, `research_tools.py`, `settings_tools.py`, `__init__.py`
- **YUKI (`agents/yuki/` — 7 files):** `service.py`, `stt.py`, `stt_engine.py`, `tts.py`, `tts_engine.py`, `voice_io.py`, `__init__.py`
- **Root (`agents/__init__.py` — 1 file)**

### 4.3 Core Domain Modules (`AIRA_ECOSYSTEM/core/` — 319 Files)
- **Core Root Modules (31 files):** `bootstrap_superadmin.py`, `brain.py`, `canonical_network.py`, `chat_sessions.py`, `conversation_context.py`, `events.py`, `global_settings.py`, `inventory_store.py`, `log_store.py`, `logger.py`, `memory.py`, `model_policy.py`, `model_registry.py`, `model_router.py`, `model_store.py`, `model_types.py`, `nms_engine.py`, `nms_models.py`, `nms_snmp.py`, `orchestrator.py`, `persona.py`, `scheduler.py`, `slash_commands.py`, `task_classifier.py`, `time_utils.py`, `topology_db.py`, `topology_discovery.py`, `topology_engine.py`, `topology_models.py`, `topology_parsers.py`, `ui.py`, `__init__.py`
- **Core Subpackages (288 files across 27 subpackages):**
  - `core/ai/` (1 file): `reasoning_engine.py`
  - `core/artifacts/` (18 files): `engine.py`, `models.py`, `specs.py`, `store.py`, `validator.py`, `generators/` (8 files), `tests/` (4 files), `__init__.py`
  - `core/attachment/` (2 files — **Stray Artifact**): `files.zip`, `main.py`
  - `core/attachments/` (13 files): `constants.py`, `context.py`, `engine.py`, `models.py`, `store.py`, `validator.py`, `tests/` (5 files), `mnt/.../__init__.py` (1 stray file), `__init__.py`
  - `core/billing/` (2 files): `service.py`, `__init__.py`
  - `core/capability/` (12 files): `constants.py`, `discovery.py`, `frontend.py`, `integration.py`, `models.py`, `registry.py`, `tests/` (5 files), `__init__.py`
  - `core/context/` (3 files): `builder.py`, `models.py`, `__init__.py`
  - `core/dio/` (19 files): `analyzer.py`, `builder.py`, `constants.py`, `interaction_memory.py`, `models.py`, `parameter_resolver.py`, `reasoning.py`, `schema.py`, `validator.py`, `tests/` (9 files), `__init__.py`
  - `core/edge_gateway/` (8 files): `buffer.py`, `collector.py`, `db.py`, `enrollment.py`, `ingestion.py`, `manager.py`, `models.py`, `__init__.py`
  - `core/external_context/` (16 files): `capability_bridge.py`, `config.py`, `constants.py`, `factory.py`, `google_maps.py`, `map_block.py`, `models.py`, `openstreetmap.py`, `provider.py`, `tests/` (6 files), `__init__.py`
  - `core/file_processing/` (9 files): `archive.py`, `context.py`, `models.py`, `ocr.py`, `processor.py`, `service.py`, `test_processor.py`, `vision_llm.py`, `__init__.py`
  - `core/filesystem/` (8 files): `history.py`, `models.py`, `operations.py`, `permissions.py`, `test_workspace_and_operations.py`, `trash.py`, `workspace.py`, `__init__.py`
  - `core/host/` (6 files): `detector.py`, `linux.py`, `models.py`, `test_host_adapters.py`, `windows.py`, `__init__.py`
  - `core/location/` (5 files): `geo.py`, `models.py`, `service.py`, `store.py`, `__init__.py`
  - `core/mcp/` (2 files): `client.py`, `__init__.py`
  - `core/network_intelligence/` (51 files): 40 root modules + `protocols/` (11 files: `base.py`, `bgp.py`, `ipv4.py`, `ipv6.py`, `layer2.py`, `nat_firewall.py`, `ospf.py`, `qos.py`, `static_routing.py`, `tunnels.py`, `__init__.py`)
  - `core/nms/` (8 files): `alerts.py`, `capability.py`, `collector_contracts.py`, `metrics_store.py`, `models.py`, `monitoring.py`, `scheduler.py`, `__init__.py`
  - `core/operations/` (22 files): 16 root modules (`approval_engine.py`, `change_impact_engine.py`, `db.py`, `decision_engine.py`, `health_scoring_engine.py`, `incident_engine.py`, `models.py`, `multi_tenant_incident_engine.py`, `notification_hub.py`, `predictive_engine.py`, `reporting_engine.py`, `risk_engine.py`, `scheduler.py`, `service_intelligence.py`, `sla_engine.py`, `__init__.py`) + `calendar/` (6 files)
  - `core/persona/` (17 files): 11 Python modules + 6 YAML definitions
  - `core/playbooks/` (3 files): `builtin_library.py`, `runner.py`, `__init__.py`
  - `core/plugins/` (6 files): `interface.py`, `loader.py`, `manifest.py`, `models.py`, `validator.py`, `__init__.py`
  - `core/routing/` (7 files): `cross_device_routing.py`, `route_analytics.py`, `route_collector.py`, `route_dependency.py`, `route_history.py`, `unified_route_parser.py`, `__init__.py`
  - `core/runtime_state/` (3 files): `engine.py`, `models.py`, `__init__.py`
  - `core/security/` (5 files): `mfa.py`, `output_guard.py`, `password.py`, `rate_limiter.py`, `ssrf_validator.py`
  - `core/selection/` (6 files): `builder.py`, `constants.py`, `models.py`, `store.py`, `tests/test_selection.py`, `__init__.py`
  - `core/semantic_memory/` (8 files): `defaults.py`, `embedder.py`, `files.zip` (stray archive), `models.py`, `retriever.py`, `scorer.py`, `store.py`, `__init__.py`
  - `core/tenant/` (16 files): `admin_authorization_service.py`, `auth_deps.py`, `context.py`, `db.py`, `entitlement_service.py`, `entitlements.py`, `manager.py`, `memory_service.py`, `models.py`, `permission_simulation.py`, `persona_service.py`, `rbac_service.py`, `token_quota_service.py`, `user_subscription.py`, `workspace_service.py`, `__init__.py`
  - `core/unified_context/` (4 files): `builder.py`, `models.py`, `tests/__init__.py`, `__init__.py`
  - `core/workspace_links/` (7 files): `models.py`, `service.py`, `store.py`, `tests/` (3 files), `__init__.py`

### 4.4 Low-Level Tools & MCP Servers (`AIRA_ECOSYSTEM/tools/` & `mcp_servers/` — 18 Files)
- `tools/inventory.py`, `tools/README.md`
- `tools/mikrotik/` (`routeros.py`, `__init__.py`)
- `tools/network/` (`diagnostics.py`, `__init__.py`)
- `tools/snmp/` (`client.py`, `monitor.py`, `oids.py`, `__init__.py`)
- `tools/ssh/` (`client.py`, `shell.py`)
- `tools/web/` (`search.py`, `__init__.py`)
- `mcp_servers/` (`__init__.py`, `network/__init__.py`, `network/security.py`, `network/server.py`)

### 4.5 Frontend Application (`AIRA_ECOSYSTEM/app/` — 263 Files)
- `app/README.md`, `app/package-lock.json` (orphaned duplicate lockfile)
- `app/frontend/` root configs (8 files): `.gitignore`, `.npmrc`, `index.html`, `jsconfig.json`, `package.json`, `package-lock.json`, `tailwind.config.js`, `vite.config.js`
- `app/frontend/public/` (31 files): animations (2 CSS), brand images (12 PNG/JPEG), favicons & icons (14), `manifest.json`, `service-worker.js`
- `app/frontend/src/` (223 files):
  - Entry & Root API clients (8 files): `main.jsx`, `App.jsx`, `Hero.jsx`, `api.js`, `service.js`, `inventoryApi.js`, `modelRouterApi.js`, `index.css`
  - Pages (`src/pages/` — 22 files): `AdminLoginPage.jsx`, `AdminPlatformPage.jsx`, `AkaneWorkspace.jsx`, `AutomationsPage.jsx`, `ChatPage.jsx`, `CustomerPortalPage.jsx`, `DecisionsPage.jsx`, `DevicesPage.jsx`, `GatewaysPage.jsx`, `InfrastructurePage.jsx`, `LoginPage.jsx`, `LogsPage.jsx`, `MemoryPage.jsx`, `ModelsPage.jsx`, `NetworkIntelligencePage.jsx`, `NmsPage.jsx`, `OperationsPage.jsx`, `PersonaPage.jsx`, `SettingsPage.jsx`, `TopologyPage.jsx`, `WorkspacePage.jsx`, `dio/DioPreviewPage.jsx`
  - Components (`src/components/` — 139 files + `src/capabilities/CapabilityHeroRow (1).jsx`)
  - Contexts (`src/context/` — 5 files): `AuthContext.jsx`, `CapabilityContext.jsx`, `ChatRuntimeContext.jsx`, `ModalDialogContext.jsx`, `SessionsContext.jsx`
  - Hooks (`src/hooks/` — 12 files): 10 hooks + 2 `.test.js` files
  - Services, Shared, Store, Theme, Types, Utils (36 files)

---

## 5. Key Structural Anomalies Identified in Phase 1

1. **Tracked Database Backups in Git (`CONFIRMED`):**
   [`AIRA_ECOSYSTEM/database/chat_sessions.db.old`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/database/chat_sessions.db.old) and [`AIRA_ECOSYSTEM/database/long_term_memory.db.old`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/database/long_term_memory.db.old) are tracked in Git (`git ls-files`) because [`.gitignore`](file:///home/Lingga/Documents/project/Network_AI_Agent/.gitignore#L55-L60) ignores `*.db` and `*.bak*`, but not `*.old`.
2. **Legacy Pre-Consolidation Code Committed in Root (`CONFIRMED`):**
   [`_legacy_backup_20260910_143345/`](file:///home/Lingga/Documents/project/Network_AI_Agent/_legacy_backup_20260910_143345) contains 27 legacy Python files generated when running [`consolidate_to_aira.ps1`](file:///home/Lingga/Documents/project/Network_AI_Agent/consolidate_to_aira.ps1), and is committed directly into Git.
3. **Container Sandbox Path Artifacts & Zip Archives Inside Source Tree (`CONFIRMED`):**
   - [`AIRA_ECOSYSTEM/core/attachment/files.zip`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachment/files.zip) and [`AIRA_ECOSYSTEM/core/attachment/main.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachment/main.py)
   - [`AIRA_ECOSYSTEM/core/attachments/mnt/user-data/outputs/AIRA_ECOSYSTEM/core/attachments/tests/__init__.py`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/attachments/mnt/user-data/outputs/AIRA_ECOSYSTEM/core/attachments/tests/__init__.py)
   - [`AIRA_ECOSYSTEM/core/semantic_memory/files.zip`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/semantic_memory/files.zip)
   - [`docs/mnt/user-data/outputs/aira_docs/docs/README.md`](file:///home/Lingga/Documents/project/Network_AI_Agent/docs/mnt/user-data/outputs/aira_docs/docs/README.md)
4. **Duplicate Filename Artifacts (`CONFIRMED`):**
   - [`AIRA_ECOSYSTEM/app/frontend/src/capabilities/CapabilityHeroRow (1).jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/capabilities/CapabilityHeroRow%20(1).jsx)
   - [`docs/roadmap (1).md`](file:///home/Lingga/Documents/project/Network_AI_Agent/docs/roadmap%20(1).md)
   - [`AIRA_ECOSYSTEM/app/package-lock.json`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/package-lock.json) vs [`AIRA_ECOSYSTEM/app/frontend/package-lock.json`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/package-lock.json)
