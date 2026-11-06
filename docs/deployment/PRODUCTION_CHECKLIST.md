# AIRA OS — Production Readiness Checklist

Before promoting AIRA OS to production on any host or VPS, verify each item in this checklist:

---

## 1. Security & Credentials
- [ ] **Default Passwords Changed:** Superadmin (`lingga_admin`) default bootstrap password changed to a strong unique secret.
- [ ] **Secret Key Set:** `SECRET_KEY` in `.env` is populated with a cryptographically secure random value (`openssl rand -hex 32`).
- [ ] **CORS Origins Scoped:** `CORS_ORIGINS` in `.env` restricted to official production domain names, not wildcard `*`.
- [ ] **Non-Root Execution:** Verified the application container runs as non-root user (`aira`, UID 10001).
- [ ] **SSL/TLS Configured:** HTTPS enabled with valid certificate (Let's Encrypt / Certbot); HTTP automatically redirects to HTTPS.
- [ ] **WebSocket WSS:** WebSockets connect over secure `wss://`.

---

## 2. Resource Management & Optimization
- [ ] **Memory Limit Enforced:** Container memory limit set to 1.5 GB in `docker-compose.yml`.
- [ ] **System Swap Enabled:** 2 GB swapfile configured on VPS host.
- [ ] **Vision/YOLO Decommissioned:** Verified zero YOLO/ultralytics dependencies loaded in memory.
- [ ] **Single Worker Process:** Uvicorn set to 1 worker to keep RAM footprint low on single-node VPS.

---

## 3. Data Integrity & Persistence
- [ ] **Persistent Volume Mounts:** Volumes `aira_data`, `aira_workspace`, and `aira_logs` verified mounted.
- [ ] **Database WAL Mode:** SQLite database `topology.db` verified running in WAL mode with busy timeout.
- [ ] **Automated Backup Job:** Daily backup cron configured for SQLite database snapshots.
- [ ] **Audit Logs Active:** Audit logging writing to `/app/AIRA_ECOSYSTEM/logs/audit.log`.

---

## 4. Operational Features
- [ ] **Global Long-Term Memory:** Account-level memories persistent across sessions for the same user.
- [ ] **Persona Hierarchy:** System Safety -> Base Personality -> User Preferences -> Account Memory -> Session Context.
- [ ] **Dynamic Input Orchestrator (DIO):** Parameter validation active before configuration generation.
- [ ] **Modal Dialogs:** Zero browser-native alerts (`alert()`, `confirm()`, `prompt()`) used in UI.
- [ ] **Interactive Suggestions:** Assistant response suggests contextual follow-ups.

---

## 5. Verification Commands
```bash
# Backend test suite
pytest AIRA_ECOSYSTEM/tests/

# Frontend test suite
npm --prefix AIRA_ECOSYSTEM/app/frontend test

# Frontend production build
npm --prefix AIRA_ECOSYSTEM/app/frontend run build

# Docker container health
curl -f http://localhost:8000/api/health
```
