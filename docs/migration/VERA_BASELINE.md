# VERA Migration Baseline Report

**Document Version:** 1.0.0  
**Baseline Date:** 2026-11-08  
**Author:** VERA System Architecture & Quality Assurance Team  
**Initial Git Branch:** `main`  
**Initial Git Commit (HEAD):** `a6eb27f3306d041bbea66a03086e407ecd905ccc`  
**Working Tree Status:** Clean (no unstaged or untracked modifications prior to migration)  

---

## 1. Executive Summary

This document captures the baseline state of the repository prior to executing the complete brand and product migration from **AIRA** to **VERA** (Enterprise Network Intelligence Platform). All architectural entrypoints, filesystem structures, test suites, builds, and existing limitations have been inventoried to guarantee zero regression and ensure safe migration.

---

## 2. Repository & Architecture Overview

### 2.1 Repository Structure
- **Root Directory:** `/home/Lingga/Documents/project/Network_AI_Agent`
- **Main Backend Package & Source:** `AIRA_ECOSYSTEM/`
  - `agents/`: AI agents (e.g., `akane` - network reasoning, `hikari`, `rei`, `yuki`).
  - `api/`: FastAPI application (`api/main.py`), route handlers (`api/routers/`), WebSockets (`api/ws_bridge.py`, `api/ws_manager.py`).
  - `core/`: Core business logic including NMS poller, topology engine, database managers, security/RBAC, session management, and capability registry.
  - `database/`: SQLite database files (`topology.db`, `inventory.db`, `chat_sessions.db`, `logs.db`, `network_intelligence.db`, etc.).
  - `scripts/`: Operational scripts, backup/restore, benchmarks.
  - `tests/`: Extensive pytest suite with >2,000 tests.
- **Frontend Source:** `AIRA_ECOSYSTEM/app/frontend/`
  - React 18.3, Vite 8.3, Tailwind CSS v4, Lucide icons, Leaflet.
  - Single-page application with lazy code-splitting across 17+ pages.

### 2.2 Application Entrypoints
- **Backend Entrypoint:** `AIRA_ECOSYSTEM/api/main.py`
  - Run command: `uvicorn api.main:app --reload --port 8000` (from `AIRA_ECOSYSTEM/`)
  - Title: `"AIRA Ecosystem API"` -> Target: `"VERA Enterprise Network Intelligence API"`
- **Frontend Entrypoint:** `AIRA_ECOSYSTEM/app/frontend/index.html` & `src/main.jsx`
  - Build command: `npm run build` (Vite)
  - Unit test command: `npm test` (`node --test`)
- **Docker / Deployment Entrypoints:**
  - `Dockerfile` at root referencing `AIRA_ECOSYSTEM`
  - `docker-compose.yml`
  - `deploy/nginx/aira_customer_portal.conf`

---

## 3. Baseline Build and Test Status

### 3.1 Frontend Test & Build Baseline
- **Build Status:** **PASS**
  - Command: `npm run build` in `AIRA_ECOSYSTEM/app/frontend`
  - Output: Clean production bundle in `dist/`, total size ~1.5 MB uncompressed assets, zero syntax errors.
- **Node Test Suite:** **PASS**
  - Command: `npm test` (`node --test`)
  - Results: **275 passed**, **0 failed**, **0 skipped** (Execution time ~1.37s).

### 3.2 Backend Pytest Baseline
- **Pytest Version:** 9.2.0 (Python 3.15.0 virtual environment at `.venv/`)
- **Execution Command:** `./.venv/bin/pytest -q`
- **Results:**
  - **Passed:** 2,074
  - **Subtests Passed:** 176
  - **Failed:** 54 (Documented pre-existing baseline failures)
  - **Skipped:** 1
  - **Warnings:** 33
  - **Total execution time:** 200.96s (03:20)

### 3.3 Root-Cause Analysis of Pre-Existing Baseline Failures (54 Tests)
The 54 test failures in the unmodified repository stem from two distinct known technical characteristics:
1. **Missing Optional Document Generators (4 tests)**:
   - `core/artifacts/tests/test_engine.py`: `test_docx`, `test_pdf`, `test_pptx`, `test_generates_valid_pptx`.
   - Reason: Python packages `python-docx`, `reportlab`, and `python-pptx` are optional dependencies not present in the runtime virtual environment.
2. **Auth Header Enforcement on Legacy Route Tests (48 tests)**:
   - Several older tests in `tests/test_networking_iii_api.py`, `tests/test_networking_vii_api.py`, `tests/test_topology_history_api.py`, and `tests/test_voice_service.py` send requests via TestClient without authenticating as an active user or superadmin session, following the strict removal of the Guest Mode bypass in the security baseline.
3. **Live Lab Offline Condition (2 tests)**:
   - `test_phase6_lab_preflight.py` and `test_phase7_live_verification.py`: Fail expectedly when live RouterOS CHR lab simulator instances (`192.168.x.x`) are not reachable on the local network.

> **CRITICAL QA DIRECTIVE:** These 54 baseline failures are verified pre-existing conditions and are not regressions caused by the brand migration. All other 2,074 tests must remain passing.

---

## 4. Invariant System Behavior & Policies to Preserve
1. **Authentication & Authorization**: Strict RBAC, session management, organization isolation.
2. **No Guest Mode**: `?guest=1`, `aira_guest_session`, and anonymous bypasses remain strictly forbidden.
3. **No Per-User AI Token Quotas or Billing**: Operational and intelligence capabilities are enterprise-entitled, not metered per token.
4. **M2M Machine-to-Machine Gateway Boundaries**: Machine gateway credentials and enrollment tokens remain isolated from interactive human web sessions.
5. **Data Preservation**: All existing SQLite databases, network device inventory, topology snapshots, and diagnostic playbooks must remain intact.
