# AIRA OS — Deployment and Configuration Architecture Manual
**Document Reference:** `docs/DEPLOYMENT_AND_CONFIGURATION.md`  
**Classification:** Engineering Specification & Production Runbook  
**Target Release:** AIRA OS AI-Native Transformation (v2.0)  

---

## 1. Executive Deployment Overview

AIRA OS is structured as a unified, high-performance hybrid network intelligence workspace. It combines:
1. **ASGI Backend:** FastAPI / Python 3.11+ application running asynchronous I/O with Uvicorn / Gunicorn worker pools, housing the AI Orchestrator, Dynamic Interaction Orchestrator (DIO), AutomationEngine, and Entitlement Engine.
2. **Frontend Client:** React 18 / Vite SPA with Tailwind CSS, Lucide icons, and Leaflet/SVG rendering, packaged as an engineering workspace with zero external CDN dependencies.
3. **Storage Tier:** Multi-database SQLite architecture with Write-Ahead Logging (WAL) and synchronous memory-pragmas for enterprise durability without heavyweight external database daemons.
4. **Edge Gateway Infrastructure:** Lightweight Python agents (`core/edge_gateway/`) for remote site discovery, RFC 1918 overlap isolation, and telemetry collection.

```
                    +------------------------------------------+
                    |           Reverse Proxy / TLS            |
                    |            (NGINX / Caddy / Traefik)     |
                    +--------------------+---------------------+
                                         |
                        +----------------+---------------+
                        |                                |
                        v HTTP / SSE / REST              v WebSocket (WSS)
            +---------------------------+    +---------------------------+
            |      FastAPI ASGI App     |    |   NMS & Terminal WSS      |
            |     (Uvicorn Workers)     |    |     (/ws/nms, /ws/akane)  |
            +-------------+-------------+    +-------------+-------------+
                          |                                |
        +-----------------+--------------------------------+-----------------+
        |                                                                    |
        v                                                                    v
+-----------------------+   +-----------------------+    +-----------------------+
|  AIRA Automation      |   |  Entitlement & Token  |    |  Topology & Discovery |
|  Engine (Scheduler)   |   |  Metering Engine      |    |  Fabric (Evidence-V2) |
+-----------+-----------+   +-----------+-----------+    +-----------+-----------+
            |                           |                            |
            +---------------------------+----------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | SQLite Multi-Database (WAL Enabled)   |
                    | - topology.db (Tenants, Nodes, Links) |
                    | - inventory.db (Managed Devices, SSH) |
                    | - logs.db (Audit Trails, Execution)   |
                    +---------------------------------------+
```

---

## 2. Environment Variables Reference

All runtime parameters are configurable via standard environment variables or `.env` files loaded at application startup:

| Variable Name | Default Value | Description |
|:---|:---|:---|
| `AIRA_ENV` | `production` | Deployment environment (`development`, `staging`, `production`). |
| `AIRA_HOST` | `0.0.0.0` | Bind host address for the ASGI HTTP server. |
| `AIRA_PORT` | `8000` | Bind TCP port for the ASGI HTTP server. |
| `AIRA_DATA_DIR` | `./data` | Root directory for databases, configuration snapshots, and uploads. |
| `AIRA_DATABASE_DIR` | `./database` | Storage directory for SQLite databases (`topology.db`, `inventory.db`). |
| `AIRA_STORAGE_DIR` | `./data/storage` | Root path for workspace file storage, reports, and generated ZIPs. |
| `AIRA_JWT_SECRET` | *Must be generated* | Cryptographic secret key for signing user session tokens (min 32 bytes). |
| `AIRA_DEFAULT_TENANT_ID` | `tenant_default` | Default tenant identifier for single-tenant standalone deployments. |
| `AIRA_TOKEN_METERING_ENABLED`| `true` | Toggle for enforcing token allowances across reasoning and tool runs. |
| `AIRA_ARCHIVE_MAX_ENTRIES` | `100000` | Safety limit for extraction entries to protect against zip bomb attacks. |
| `AIRA_ARCHIVE_DISK_MARGIN` | `67108864` | Minimum free disk space (64MB) required before extracting archives. |
| `AIRA_DISCOVERY_CONCURRENCY`| `5` | Maximum simultaneous SSH/SNMP discovery probes per scan job. |
| `AIRA_DISCOVERY_TIMEOUT_SEC`| `10.0` | Individual probe timeout in seconds during recursive topology scans. |
| `AIRA_LOG_LEVEL` | `INFO` | Console and structured file logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 3. SQLite Multi-Database Topology and WAL Configuration

AIRA OS utilizes three primary database stores located in `AIRA_DATABASE_DIR`:

1. **`topology.db`**: Multi-tenant organizations, user accounts, sessions, RBAC permissions, network topology nodes and edges, ISP boundaries, route overlays, token balances, and approval queues.
2. **`inventory.db`**: Managed network device credentials (SSH passwords, private keys, SNMP communities) encrypted with local secret isolation.
3. **`logs.db`**: High-throughput immutable audit trails, device telemetry samples, and automated execution histories.

### WAL Pragmas Applied at Connection:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 10000;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000; -- 64MB memory page cache
```

### Concurrency and Locking:
Write operations are wrapped in `topology_transaction(write=True)` which serializes modifications using Python file locks (`threading.Lock` / `filelock`) to prevent `SQLITE_BUSY` errors during concurrent discovery and NMS telemetry ingestion.

---

## 4. Single-Node Production Deployment (Linux / systemd)

### 4.1 Prerequisites
- Ubuntu 22.04 LTS or Debian 12
- Python 3.11 or Python 3.12 (`python3-venv`, `python3-pip`)
- Node.js 20+ (for building frontend assets)
- NGINX 1.22+

### 4.2 Installation Procedure
```bash
# 1. Clone repository
git clone https://github.com/TKJ-Networkers31/Network_AI_Agent.git /opt/aira-os
cd /opt/aira-os

# 2. Setup Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Build Production Frontend Assets
cd AIRA_ECOSYSTEM/app/frontend
npm ci
npm run build
cd ../../..

# 4. Generate Production Secrets
export AIRA_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "AIRA_JWT_SECRET=${AIRA_JWT_SECRET}" >> .env
echo "AIRA_ENV=production" >> .env
```

### 4.3 systemd Service Unit (`/etc/systemd/system/aira.service`)
```ini
[Unit]
Description=AIRA OS — AI-Native Network Operations Platform
After=network.target

[Service]
Type=simple
User=aira
Group=aira
WorkingDirectory=/opt/aira-os
EnvironmentFile=/opt/aira-os/.env
Environment=PYTHONPATH=/opt/aira-os/AIRA_ECOSYSTEM
ExecStart=/opt/aira-os/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers
Restart=always
RestartSec=5s
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

---

## 5. Reverse Proxy Configuration (NGINX)

```nginx
upstream aira_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name aira.infra.corp;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aira.infra.corp;

    ssl_certificate /etc/ssl/certs/aira.crt;
    ssl_certificate_key /etc/ssl/private/aira.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Frontend Single Page Application
    root /opt/aira-os/AIRA_ECOSYSTEM/app/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API Backend Reverse Proxy
    location /api/ {
        proxy_pass http://aira_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 100M;
    }

    # WebSocket Ingestion and Live Stream
    location /ws/ {
        proxy_pass http://aira_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

---

## 6. Backup, Snapshot, and Disaster Recovery

### Online SQLite WAL Backup Procedure
Because SQLite is run in WAL mode, database backups can be generated live without stopping the service:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/aira/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Atomic vacuum into backup files
sqlite3 /opt/aira-os/AIRA_ECOSYSTEM/database/topology.db ".backup '${BACKUP_DIR}/topology.db'"
sqlite3 /opt/aira-os/AIRA_ECOSYSTEM/database/inventory.db ".backup '${BACKUP_DIR}/inventory.db'"
sqlite3 /opt/aira-os/AIRA_ECOSYSTEM/database/logs.db ".backup '${BACKUP_DIR}/logs.db'"

# Archive configuration files safely
tar -czf "${BACKUP_DIR}/storage.tar.gz" -C /opt/aira-os/data storage/

echo "AIRA OS atomic snapshot created at ${BACKUP_DIR}"
```

### Health Check & Liveness Verification
- Endpoint: `GET /api/health` → returns `{ "status": "ok", "version": "2.0.0", "timestamp": ... }`
- NMS Telemetry Status: `GET /api/nms/status` → reports live monitoring loop status and counter delta rates.
