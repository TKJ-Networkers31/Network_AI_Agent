# VERA Migration Rollback & Disaster Recovery Plan

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-08  
**Scope:** Complete reversal and recovery procedures for the AIRA to VERA brand and product migration.  

---

## 1. Safety Principles & Invariants

1. **Non-Destructive Execution**: Under no circumstances should `git reset --hard` or `git clean -fd` be executed blindly. The workspace may contain verified operator customizations.
2. **Database First**: All SQLite databases (`topology.db`, `inventory.db`, `chat_sessions.db`, etc.) were backed up using the SQLite Online Backup API prior to migration into:
   ```text
   VERA_ECOSYSTEM/database/backups/pre_migration/
   ```
   Each backup has been verified with `PRAGMA integrity_check = ok`.
3. **Traceability**: All renames were executed using `git mv` and tracked in `docs/migration/VERA_RENAME_MANIFEST.md`.

---

## 2. Step-by-Step Rollback Procedures

### Step 1: Service Quiescence (If Running in Production)
If any local or Docker instances are running:
```bash
# Docker Compose
docker compose down

# Or local uvicorn process
pkill -f "uvicorn api.main:app" || true
```

### Step 2: Database Restoration & Verification
If any database modification or corruption occurred during testing:
```bash
python3 -c '
import sqlite3, glob, os, shutil

backup_dir = "VERA_ECOSYSTEM/database/backups/pre_migration"
db_dir = "VERA_ECOSYSTEM/database"

for bck_file in glob.glob(f"{backup_dir}/*.db"):
    base = os.path.basename(bck_file)
    target = os.path.join(db_dir, base)
    
    # Online restore
    src = sqlite3.connect(bck_file)
    dst = sqlite3.connect(target)
    src.backup(dst)
    dst.close()
    src.close()
    
    # Verify integrity
    check = sqlite3.connect(target).execute("PRAGMA integrity_check;").fetchall()
    print(f"Restored {base}: {check}")
'
```

### Step 3: Filesystem & Directory Reversal
To restore the repository filesystem structure to the pre-migration state:

```bash
# 1. Remove the backward-compatibility symlink
rm -f AIRA_ECOSYSTEM

# 2. Reverse the primary ecosystem directory
git mv VERA_ECOSYSTEM AIRA_ECOSYSTEM

# 3. Reverse internal frontend hooks and emblems
git mv AIRA_ECOSYSTEM/app/frontend/src/components/voice/VeraVoiceEmblem.jsx AIRA_ECOSYSTEM/app/frontend/src/components/voice/AiraVoiceEmblem.jsx
git mv AIRA_ECOSYSTEM/app/frontend/src/hooks/useVeraSocketPool.js AIRA_ECOSYSTEM/app/frontend/src/hooks/useAiraSocketPool.js

# 4. Reverse deployment configuration
git mv deploy/nginx/vera_customer_portal.conf deploy/nginx/aira_customer_portal.conf
```

### Step 4: Build & CI Configuration Reversal
Revert `pytest.ini`, `Dockerfile`, `docker-compose.yml`, and `.github/workflows/ci.yml`:
```bash
git checkout HEAD -- pytest.ini Dockerfile docker-compose.yml .github/workflows/ci.yml .env.example
```

### Step 5: Frontend Rebuild & Verification
```bash
cd AIRA_ECOSYSTEM/app/frontend
npm test
npm run build
```

### Step 6: Post-Rollback Validation
Execute the verification suite to ensure the baseline state is restored:
```bash
cd /home/Lingga/Documents/project/Network_AI_Agent
./.venv/bin/pytest AIRA_ECOSYSTEM/tests/test_global_settings.py -v
```

---

## 3. Rollback Manifest Verification Matrix

| Target Subsystem | Action | Verification Check |
|---|---|---|
| Primary Directory | `VERA_ECOSYSTEM` -> `AIRA_ECOSYSTEM` | `test -d AIRA_ECOSYSTEM` |
| Pytest Config | Set `pythonpath = AIRA_ECOSYSTEM` | `./.venv/bin/pytest --collect-only` |
| SQLite Databases | Restore from `pre_migration/` | `PRAGMA integrity_check == 'ok'` |
| Frontend Bundle | Recompile `dist/` | `npm run build` exits 0 |
| Nginx Config | Revert to `aira_customer_portal.conf` | `test -f deploy/nginx/aira_customer_portal.conf` |
