# PHASE 13 — DEPLOYMENT, CI/CD & CONFIGURATION AUDIT (`13_DEPLOYMENT_AND_CONFIGURATION_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Workspace**: `/home/Lingga/Documents/project/Network_AI_Agent`  
**Scope**: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `.env.example`, `requirements.txt`, `requirements-web.txt`, `pytest.ini`, `.github/workflows/ci.yml`, `deploy/nginx/aira_customer_portal.conf`, `AIRA_ECOSYSTEM/scripts/*.py`, and `AIRA_ECOSYSTEM/core/config.py`.

---

## 1. Executive Summary of Deployment Readiness

**Deployment Readiness Status**: **BROKEN IN DOCKER & CI/CD (`CONFIRMED`)**

Both the production Docker container (`Dockerfile`) and the GitHub Actions CI pipeline (`.github/workflows/ci.yml`) **fail to build/run out of the box** due to split Python dependency manifests (`requirements.txt` vs `requirements-web.txt`), an invalid Node.js test flag (`npm test -- --run`), and missing `.dockerignore` rules that bake local developer SQLite databases into the container image.

---

## 2. Detailed Deployment & Configuration Findings

### 2.1 Split Dependency Manifests Break Docker & CI (`CONFIRMED — CRITICAL`)
- **Evidence**:
  - [`requirements.txt:1-16`](file:///home/Lingga/Documents/project/Network_AI_Agent/requirements.txt#L1-L16): Contains `ollama`, `mcp`, `paramiko`, `pysnmp`, `faster-whisper`, `kokoro-onnx`, `sounddevice`, `numpy`, `requests`, `beautifulsoup4`, `python-dotenv`, `pytest`, `httpx`. **Does NOT contain `fastapi`, `uvicorn`, `pydantic`, `PyYAML`, or `websockets`!**
  - [`requirements-web.txt:1-3`](file:///home/Lingga/Documents/project/Network_AI_Agent/requirements-web.txt#L1-L3): Contains `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0` (which pulls in `pydantic`, `PyYAML`, `websockets`).
  - [`Dockerfile:29-30`](file:///home/Lingga/Documents/project/Network_AI_Agent/Dockerfile#L29-L30):
    ```dockerfile
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    ```
  - [`.github/workflows/ci.yml:26`](file:///home/Lingga/Documents/project/Network_AI_Agent/.github/workflows/ci.yml#L26):
    ```yaml
    run: |
      python -m pip install --upgrade pip
      pip install -r requirements.txt
    ```
- **Impact**:
  1. **Docker Container Fails on Startup**: `Dockerfile:48` runs `CMD ["python", "run_web.py"]`, which immediately crashes with `ModuleNotFoundError: No module named 'uvicorn'` / `'fastapi'` because `requirements-web.txt` was never copied or installed in the `Dockerfile`!
  2. **GitHub Actions CI Backend Job Fails**: `.github/workflows/ci.yml:26` never installs `requirements-web.txt`, so every test that imports `fastapi` or `pydantic` or `yaml` fails during `pytest` collection!
  3. **Local `.venv` Parity Mismatch**: Conversely, the local `.venv` only installed `requirements-web.txt` and never installed `requirements.txt` (`pytest`, `paramiko`, `pysnmp`, `mcp`).

---

### 2.2 GitHub Actions CI Frontend Test Breaker (`CONFIRMED — HIGH`)
- **Evidence**:
  - [`.github/workflows/ci.yml:64`](file:///home/Lingga/Documents/project/Network_AI_Agent/.github/workflows/ci.yml#L64) executes: `run: npm test -- --run`.
  - [`AIRA_ECOSYSTEM/app/frontend/package.json:10`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/package.json#L10) defines: `"test": "node --test"`.
- **Verification**: Running `npm test -- --run` in `AIRA_ECOSYSTEM/app/frontend/` passes `--run` to `node --test`, which is not a valid Node.js CLI flag (it is a Vitest flag) and exits with **exit code `9` (`bad option: --run`)** (`CONFIRMED` in Phase 11).

---

### 2.3 Docker & `.dockerignore` Database Leakage & Single-Container Gap (`CONFIRMED — HIGH`)
1. **Local SQLite Databases Baked Into Docker Image (`.dockerignore:1-35` & `Dockerfile:33`)**:
   - [`Dockerfile:33`](file:///home/Lingga/Documents/project/Network_AI_Agent/Dockerfile#L33) executes `COPY AIRA_ECOSYSTEM/ ./AIRA_ECOSYSTEM/`.
   - [`.dockerignore:1-35`](file:///home/Lingga/Documents/project/Network_AI_Agent/.dockerignore#L1-L35) excludes `.venv/`, `node_modules/`, and `AIRA_ECOSYSTEM/logs/`, **but does NOT exclude `AIRA_ECOSYSTEM/database/*.db` or `*.db.old` or `AIRA_ECOSYSTEM/workspace/`**!
   - **Impact**: Building the Docker image on a developer machine copies live `topology.db`, `chat_sessions.db`, `long_term_memory.db`, and `.db.old` files (including session tokens, user accounts, and chat transcripts) directly into the immutable Docker image layers!
2. **Frontend Static Build Omitted from `Dockerfile` & `docker-compose.yml`**:
   - [`Dockerfile`](file:///home/Lingga/Documents/project/Network_AI_Agent/Dockerfile#L1-L48) only builds a Python backend container (`python:3.11-slim`) and does not include a multi-stage Node/Vite build for `AIRA_ECOSYSTEM/app/frontend`, nor does `api/main.py` mount `app/frontend/dist` via `StaticFiles`.
   - [`docker-compose.yml:1-46`](file:///home/Lingga/Documents/project/Network_AI_Agent/docker-compose.yml#L1-L46) only defines a single service (`aira-core` on port `8000`) and has **no frontend or Nginx service**, even though [`deploy/nginx/aira_customer_portal.conf`](file:///home/Lingga/Documents/project/Network_AI_Agent/deploy/nginx/aira_customer_portal.conf#L1-L82) exists!
3. **System Audio Library Missing in `Dockerfile` (`libportaudio2`)**:
   - `Dockerfile:16-22` installs `iputils-ping`, `traceroute`, `dnsutils`, `openssh-client`, `curl`, `sqlite3`, but omits `libportaudio2` (required by `sounddevice` in `requirements.txt` / `agents/yuki/voice_io.py`).

---

### 2.4 Reverse Proxy / Nginx Configuration Audit (`CONFIRMED — MEDIUM`)
- **File**: [`deploy/nginx/aira_customer_portal.conf:1-82`](file:///home/Lingga/Documents/project/Network_AI_Agent/deploy/nginx/aira_customer_portal.conf#L1-L82).
- **Findings**:
  1. **Hardcoded Placeholder TLS Paths & Domains (`L7, 17-19`)**: Uses `portal.aira-network.example.com` and `/etc/letsencrypt/live/portal.aira-network.example.com/fullchain.pem`.
  2. **Missing Proxy Routes for Non-`/api/` Endpoints (`L36-74`)**:
     - Proxies `/api/` (`L36`) and `/ws/` (`L51`) to `http://127.0.0.1:8000`, **but does NOT proxy `/health` (`L70` returns static `"OK\n"` from Nginx without checking backend health!) or `/files/*` / `/host/info`** (which `src/api.js:93-128` falls back to).
  3. **Dangerous Interaction with `require_topology_admin` (`api/routers/topology.py:76`)**:
     - Because Nginx proxies from `127.0.0.1` to `http://127.0.0.1:8000`, `request.client.host` in FastAPI is always `"127.0.0.1"`. When `AIRA_TOPOLOGY_ADMIN_TOKEN` is unset in `.env`, `require_topology_admin` (`topology.py:76`) sees `client_host == "127.0.0.1"` and **grants admin write access to every remote Internet user behind Nginx**!
  4. **Dangerous Interaction with `auth.py` `X-Forwarded-For` (`api/routers/auth.py:76-78`)**:
     - If FastAPI is exposed directly without Nginx stripping/overwriting `X-Forwarded-For`, clients can spoof `X-Forwarded-For` to bypass login rate limiting.

---

### 2.5 Environment Variable Audit (`.env.example` vs Codebase `os.getenv`)
Comparison between [`.env.example`](file:///home/Lingga/Documents/project/Network_AI_Agent/.env.example#L1-L67) and all `os.getenv()` calls across `AIRA_ECOSYSTEM/` reveals **14 undocumented environment variables** used in code but missing from `.env.example`:

| Undocumented Environment Variable | Where Used in Code | Purpose & Impact When Unset |
|---|---|---|
| `AIRA_CORS_ORIGINS` | `api/main.py:67` | Comma-separated allowed CORS origins (defaults to `localhost:5173,localhost:3000`, blocking production domains!). |
| `AIRA_TOPOLOGY_ADMIN_TOKEN` / `AIRA_ADMIN_TOKEN` | `api/routers/topology.py:69-70` | Static token for `require_topology_admin` (when unset, `127.0.0.1` bypasses admin checks!). |
| `AIRA_BILLING_WEBHOOK_SECRET` | `core/billing/service.py:34` | HMAC secret for payment webhooks (falls back to hardcoded source string when unset!). |
| `AIRA_SUPERADMIN_INITIAL_PASSWORD` | `core/tenant/seed_admin.py:29` | Initial password for `lingga_admin` on first bootstrap. |
| `AIRA_VOICE_AUTOSTART` | `api/main.py:251` | Auto-starts YUKI background microphone listener on server boot if `"true"`. |
| `AIRA_MEMORY_COMPACTOR_INTERVAL_HOURS` | `api/main.py:224` | Background memory compaction interval (defaults to `6`). |
| `AIRA_WORKSPACE_ROOT` | `core/config.py:134` | Overrides workspace sandbox root directory. |
| `AIRA_UPLOADS_DIR` | `core/config.py:137` | Overrides attachment uploads directory. |
| `AIRA_HOST` / `AIRA_PORT` / `AIRA_RELOAD` | `run_web.py:22-24` | Uvicorn bind host, port, and hot-reload toggle. |
| `GOOGLE_CALENDAR_CLIENT_ID` / `SECRET` / `CALENDAR_ID` | `core/operations/calendar/google_provider.py:24-26` | Google Calendar maintenance window provider config (stubbed). |

---

### 2.6 Backup, Restore & Operational Scripts Audit (`AIRA_ECOSYSTEM/scripts/`)
- **Files**: `scripts/backup_restore.py`, `scripts/production_readiness_check.py`, `scripts/soak_test.py`.
- **Findings (`CONFIRMED — MEDIUM`)**:
  1. **Incomplete Backup Coverage in `scripts/backup_restore.py:28-35`**:
     - `BackupManager` only backs up `topology.db` (and optional `inventory.json` / `.env` metadata), **completely omitting the other 16 SQLite databases** (`inventory.db`, `chat_sessions.db`, `model_router.db`, `logs.db`, `global_settings.db`, `attachments.db`, `artifacts.db`, etc.)!
  2. **Unsafe Live File Copy (`shutil.copy2`) During WAL Transactions (`scripts/backup_restore.py:55`)**:
     - Uses `shutil.copy2(self.db_path, target_db)` instead of SQLite's online backup API (`sqlite3.Connection.backup()`), which can produce a corrupted backup if `topology.db-wal` has uncommitted/uncheckpointed frames during a write transaction!
