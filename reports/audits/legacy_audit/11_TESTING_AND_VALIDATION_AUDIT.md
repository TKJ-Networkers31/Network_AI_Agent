# PHASE 11 — TESTING & VALIDATION AUDIT (`11_TESTING_AND_VALIDATION_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent`  
**Audit Mode**: Read-Only Test Suite Inspection & Safe Non-Destructive Validation Execution

---

## 1. Existing Test Suite Inventory & Quality Audit (Section A)

### 1.1 Test File Inventory (`201` Total Test Files)
From `01_REPOSITORY_INVENTORY.md`, the repository contains **201 test-related files**:
1. **Python Backend Tests (`138` files)**:
   - `AIRA_ECOSYSTEM/tests/`: 130 test files (`test_*.py`, `conftest.py`, `fixtures/routeros/loader.py`).
   - `AIRA_ECOSYSTEM/test_events_manual.py`: 1 manual root test script.
   - `conftest.py` (workspace root): 1 path bootstrapper adding `AIRA_ECOSYSTEM/` to `sys.path`.
   - `scratch/test_*.py` & `scratch/verify_phase_f1.py`: 3 developer scratch scripts.
   - `_legacy_backup_20260910_143345/`: 3 legacy test files.
2. **Frontend JavaScript Tests (`15` files)**:
   - `AIRA_ECOSYSTEM/app/frontend/src/components/cockpit/cockpit.test.js`
   - `AIRA_ECOSYSTEM/app/frontend/src/components/topology/{multiDeviceRouteOverlay,multiLayerTopology,routeHistory,topologyHistory}.test.js` (4 files)
   - `AIRA_ECOSYSTEM/app/frontend/src/hooks/{useVoice,useVoiceCompanion}.test.js` (2 files)
   - `AIRA_ECOSYSTEM/app/frontend/src/store/bootSequence.test.js`
   - `AIRA_ECOSYSTEM/app/frontend/src/utils/{dioParser,greetingResolver,streamBatcher,streamMarkdownParser,thinkingClassifier,voiceCommandRouter,wsEventRouter}.test.js` (7 files)
3. **RouterOS CLI Output Test Fixtures (`48` files)**:
   - `AIRA_ECOSYSTEM/tests/fixtures/routeros/v6/` & `v7/` (`*.txt` CLI output snapshots + `manifest.json`).

### 1.2 Test Suite Quality & Coverage Gap Analysis (`CONFIRMED`)

1. **Why Existing Tests Missed 45 Functional Bugs & 28 Security Vulnerabilities**:
   - **Direct Service Instantiation Bypassing FastAPI Routers**:
     - Most phase tests (`test_phase_4_3_nms_telemetry.py`, `test_phase_5_network_intelligence.py`, `test_phase_6_action_onboarding.py`, `test_phase_7_autonomous_operations.py`, `test_phase_8_operational_intelligence.py`, `test_phase_8_edge_gateway.py`) instantiate individual Python service classes directly against isolated temporary SQLite databases rather than calling the FastAPI endpoints via `TestClient(app)`.
     - **Consequence**: They completely missed:
       - Router-level `Depends(require_permission("devices.read"))` in `api/routers/gateways.py:25` blocking `/enroll`, `/heartbeat`, and `/telemetry` (`BUG-15`).
       - Route shadowing of `GET /api/intelligence/actions/policy` by `GET /actions/{action_id}` in `api/routers/network_intelligence.py:1556 vs 1586` (`BUG-13`).
       - Cross-module SQLite table schema collisions when both `EdgeGatewayManager` and `metrics_store` (`BUG-06`) or `NmsEngine` and `NmsHistoricalMetricsService` (`BUG-07`) initialize against the same `topology.db`!
   - **Testing Unused Modules Instead of Production Modules**:
     - `test_phase_h_security_and_governance.py` tests `core/security/ssrf_validator.py` directly, giving a false sense of security even though `ssrf_validator.py` is **never imported anywhere in production code**!
     - `test_phase_4_3_nms_telemetry.py` tests `HardenedNmsScheduler` (`core/nms/scheduler.py`) and `AlertEngine` (`core/nms/alerts.py`), which are **never used by `api/routers/nms.py` or `core/nms_engine.py` in production**!
     - `test_phase_f_enterprise_hardening.py` tests `core/tenant/workspace_service.py`, which is **never wired into `api/routers/files.py`**!
   - **Mocked / Happy-Path-Only Assertions**:
     - `test_vision_llm.py` tests error/disabled paths or mocks `VisionResult` without triggering line `93` of `core/file_processing/vision_llm.py` (`VisionResult(..., analysis=...)`), missing `BUG-09` (`TypeError` on 100% of successful Vision LLM calls).
     - `test_phase_f2_billing_and_quota.py` always passes a valid `X-Signature` header in webhook tests, never testing an omitted `X-Signature` header (`BUG-02`), and never tests `TokenQuotaService.update_plan_policy()` (`BUG-08`).
   - **Zero Frontend Component / Page Integration Tests**:
     - All 15 frontend `.test.js` files test pure utility/helper functions using Node's built-in `node --test` runner. There are **zero** React component tests (`@testing-library/react` / Vitest / Playwright) for any of the 22 page files in `src/pages/`, which is why `NmsPage.jsx:972` (`refreshAll()` `ReferenceError`), `SettingsPage.jsx` unreachable tabs, and 9 broken API endpoint paths (`404 Not Found`) went undetected.
2. **Broken Manual Test Script (`AIRA_ECOSYSTEM/test_events_manual.py:33` — `CONFIRMED`)**:
   - Calls `loop = asyncio.get_event_loop()` outside a running event loop, which raises `RuntimeError: There is no current event loop in thread 'MainThread'` on modern Python (3.12+ / 3.15).

---

## 2. Safe Validation Execution Log (Section B)

In strict accordance with Rule 2.1 (Audit Only — Zero Mutation of Operational Databases or Dependencies), SHA-256 checksums of all files in `AIRA_ECOSYSTEM/database/*` were recorded before and verified after all validation commands.

### 2.1 Command Execution Results Table

| Command | Purpose | Result | Exit Code | Findings |
|---|---|---|---:|---|
| `sha256sum AIRA_ECOSYSTEM/database/*` (before & after) | Verify zero mutation of operational SQLite databases during audit | **PASS** (`OK` on all 9 files) | `0` | All operational databases (`topology.db`, `chat_sessions.db`, `logs.db`, `long_term_memory.db`, `model_router.db`, etc.) remained 100% byte-for-byte identical. |
| `.venv/bin/python -c "import ast..."` ( across all 557 `.py` files) | Static AST syntax & escape-sequence check across all Python files in workspace | **PASS** (`557` parsed, `0` syntax errors, `2` `SyntaxWarning`s) | `0` | Zero `SyntaxError`s across all 557 `.py` files. Identified 2 `SyntaxWarning: "\." is an invalid escape sequence` in `scratch/patch_routes.py:7, 27`. |
| `cd AIRA_ECOSYSTEM/app/frontend && npm test` (`node --test`) | Execute frontend unit test suite (`15` `.test.js` files, `246` subtests) | **PARTIAL FAIL** (`240` pass, `6` fail) | `1` | `240` pure-JS tests pass (`cockpit`, `dioParser`, `greetingResolver`, `streamBatcher`, `streamMarkdownParser`, `thinkingClassifier`, `voiceCommandRouter`, `wsEventRouter`, `bootSequence`). `6` test files (`multiDeviceRouteOverlay.test.js`, `multiLayerTopology.test.js`, `routeHistory.test.js`, `topologyHistory.test.js`, `useVoice.test.js`, `useVoiceCompanion.test.js`) fail with `ERR_MODULE_NOT_FOUND` (`lucide-react` / `react`) because `node_modules/` is not installed on disk. |
| `cd AIRA_ECOSYSTEM/app/frontend && npm test -- --run` (`node --test --run`) | Verify exact CI command configured in `.github/workflows/ci.yml:64` | **FAIL** (`bad option: --run`) | `9` | **Confirms CI Pipeline Breaker (`CONFIRMED`)**: `.github/workflows/ci.yml:64` runs `npm test -- --run` (assuming Vitest), which passes `--run` to `node --test` (`package.json:10`) and exits immediately with code `9`! |
| `.venv/bin/pip list` & `python3 -m pytest --version` | Verify Python virtual environment & test runner availability | **ENV GAP IDENTIFIED** | `1` | `.venv` (Python 3.15.0) only has `requirements-web.txt` installed (`fastapi`, `uvicorn`, `pydantic`, `PyYAML`, `websockets`, `python-dotenv`, `opentelemetry-api`). Packages from `requirements.txt` (`pytest`, `httpx`, `paramiko`, `pysnmp`, `requests`, `mcp`, `faster-whisper`, `kokoro-onnx`) are **not** installed in `.venv` or system Python. Per Rule 2.1 (no dependency modification), no packages were installed. |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c "..."` (isolated `tempfile.TemporaryDirectory()`) | Runtime verification of SQLite schema collisions, `CHECK` constraints, and `VisionResult` `TypeError` in isolated temp DB | **CONFIRMED 5 BUGS** | `0` | Executed safely in `/tmp` without touching operational DBs:<br>1. `core/nms/models.py:35` importing `mcp_servers.network.security` triggers `mcp_servers/network/__init__.py:4` -> `ModuleNotFoundError: No module named 'mcp'`.<br>2. `ensure_gateway_schema()` + `query_metrics()` raises `sqlite3.OperationalError: no such table: nms_1h_rollups` / column collision on `nms_raw_metrics` (`BUG-06`).<br>3. `pol_global_guest` row in `operational_token_policies` is `None` after `ensure_tenant_schema()`, proving silent `CHECK(tier IN ...)` failure.<br>4. `TokenQuotaService.update_plan_policy("PRO", ...)` raises `sqlite3.OperationalError: table operational_token_policies has no column named model_cost_multiplier_json` (`BUG-08`).<br>5. `VisionResult(..., analysis=...)` raises `TypeError: VisionResult.__init__() got an unexpected keyword argument 'analysis'` (`BUG-09`). |

---

## 3. Environment & Testing Limitations Documented

1. **Incomplete `.venv` Installation**: Only `requirements-web.txt` was installed into `.venv`; `requirements.txt` (including `pytest`, `paramiko`, `pysnmp`, `mcp`, `requests`) is not installed in `.venv`.
2. **Inverse Missing `requirements-web.txt` in `Dockerfile` and `.github/workflows/ci.yml`**: Conversely, `Dockerfile:29-30` and `.github/workflows/ci.yml:26` only run `pip install -r requirements.txt` and **never install `requirements-web.txt`**, meaning `fastapi` and `uvicorn` are missing in Docker builds and GitHub Actions CI!
3. **Missing `node_modules/` in `AIRA_ECOSYSTEM/app/frontend/`**: `node_modules` is not present on disk, preventing `vite build` or tests importing `react`/`lucide-react` from resolving external npm packages until `npm ci` is run.
