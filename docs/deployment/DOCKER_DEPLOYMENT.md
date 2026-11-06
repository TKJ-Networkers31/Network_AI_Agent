# AIRA OS — Docker Deployment Guide (Low-Resource VPS)

This guide documents how to build, deploy, and operate AIRA OS using Docker and Docker Compose on a low-resource Virtual Private Server (VPS) with 1 GB - 2 GB RAM.

---

## 1. System Requirements

- **CPU:** 1-2 vCPU cores
- **RAM:** Minimum 1.5 GB available RAM (2 GB recommended; swap recommended)
- **Disk:** 10 GB SSD / NVMe
- **OS:** Ubuntu 22.04 LTS / Debian 12 / Rocky Linux 9
- **Container Engine:** Docker Engine 24+ and Docker Compose v2+

### Swap Configuration (Recommended for 1-2GB RAM VPS)
If your VPS has only 1-2GB physical RAM, configure a 2GB swap file to prevent out-of-memory (OOM) kernel kills during peak operations:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 2. Fast-Track Deployment

### Step 1: Clone Repository
```bash
git clone https://github.com/your-org/aira-os.git /opt/aira-os
cd /opt/aira-os
```

### Step 2: Configure Environment
```bash
cp .env.example .env
nano .env
```
Fill in your `SECRET_KEY` and any necessary LLM API keys (`OPENROUTER_API_KEY`, etc.).

### Step 3: Build & Start Container
```bash
docker compose up -d --build
```

### Step 4: Verify Container Health
```bash
docker compose ps
docker compose logs -f app
```
Verify the health check endpoint:
```bash
curl http://localhost:8000/api/health
```

---

## 3. Container Architecture & Resource Budget

The deployment utilizes a multi-stage Dockerfile:
1. **Stage 1 (`frontend-builder`):** `node:20-alpine` builds the Vite/React single-page application into optimized static assets.
2. **Stage 2 (`runner`):** `python:3.12-slim` runs the Uvicorn ASGI server as a non-privileged `aira` user (`uid=10001`).

### Memory Budgeting:
- **Container Limit:** `1536M` (1.5 GB)
- **Memory Reservation:** `256M`
- **Uvicorn Workers:** `1` (Single worker process ensures memory footprint remains under 350MB idle / 750MB peak).
- **Vision/YOLO:** Completely decommissioned, saving ~1.2 GB RAM.

---

## 4. Persistent Volumes & Data Safety

The `docker-compose.yml` mounts 3 persistent volumes:
- `aira_data`: Stores `topology.db` SQLite database (users, credentials, inventory, topology, persona, memories).
- `aira_workspace`: Stores user scripts, generated configurations, and backup artifacts.
- `aira_logs`: Stores application and audit logs.

### Database Backup
To back up the live SQLite database safely using online SQLite backup:
```bash
docker compose exec app sqlite3 /app/AIRA_ECOSYSTEM/database/topology.db ".backup '/app/workspace/backup_$(date +%Y%m%d_%H%M%S).db'"
```

---

## 5. Reverse Proxy Setup (Nginx + SSL)

We recommend putting Nginx in front of port 8000 for TLS termination and WebSocket proxying:

```nginx
server {
    listen 80;
    server_name aira.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aira.example.com;

    ssl_certificate /etc/letsencrypt/live/aira.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aira.example.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```
