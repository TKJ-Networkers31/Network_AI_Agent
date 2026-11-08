# VERA Complete Brand Inventory & Rename Manifest

**Document Version:** 1.0.0  
**Manifest Date:** 2026-11-08  
**Scope:** Full repository scan of file paths, directory paths, environment variables, frontend components, and static assets.  
**Classification Standard:** Section 6.1 of VERA Migration Specification.  

---

## 1. Classification Taxonomy

Each occurrence and path has been mapped into one of the designated categories:
1. **Active Product Branding**: Active user-facing strings, headers, titles, slogans, and metadata -> **Migrated to VERA**.
2. **Visible UI Identity**: Nav bars, sidebars, page headers, modal titles, breadcrumbs -> **Migrated to VERA**.
3. **Branding Assets**: Logos, emblems, favicons, splash graphics -> **Replaced with VERA vector network core assets**.
4. **Project-Owned Directory / File Paths**: Tracked source directories and filenames -> **Safely renamed via Git with backward compatibility symlink/adapters**.
5. **Source Imports & Path References**: Imports, references, and loaders -> **Updated in sync with renames**.
6. **API / Internal Identifiers**: Routes, tokens, env vars -> **Dual-support / backward compatibility fallback enabled (`VERA_*` primary, fallback to `AIRA_*`)**.
7. **Database Schema & Tables**: SQLite tables, columns, indexes -> **Preserved intact (zero schema disruption, verified data integrity)**.
8. **Historical Migrations & Audits**: Sprint logs, Phase reports (`docs/AIRA_PHASE*.md`, `AUDIT_REPORT/`) -> **Preserved as historical provenance**.
9. **Third-Party Dependencies & System Caches**: `node_modules`, `.venv`, `.pytest_cache`, `graphify-out` -> **Preserved untouched**.
10. **Logs & Runtime User Data**: SQLite `.db` log tables, historical text logs -> **Preserved without destructive rewrites**.

---

## 2. Comprehensive Rename & Migration Manifest Table

| Original Path / Identifier | Proposed New Path / Target | Category | Dependency Impact | Risk Level | Migration Method | Validation Method | Status |
|---|---|---|---|---|---|---|---|
| `AIRA_ECOSYSTEM/` | `VERA_ECOSYSTEM/` | Project Directory | High (Build configs, Docker, CI) | Medium | Git rename + symlink `AIRA_ECOSYSTEM -> VERA_ECOSYSTEM` | `pytest` and `npm run build` | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/src/components/voice/AiraVoiceEmblem.jsx` | `.../components/voice/VeraVoiceEmblem.jsx` | Component Rename | Low (Voice companion host) | Low | Git mv + update import in `VoiceCompanionHost.jsx` | `npm test` & Vite build | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/src/hooks/useAiraSocketPool.js` | `.../hooks/useVeraSocketPool.js` | Hook / Utility | Low (WebSocket consumers) | Low | Git mv + re-export alias in old path for safety | Vite build & test suite | Scheduled |
| `deploy/nginx/aira_customer_portal.conf` | `deploy/nginx/vera_customer_portal.conf` | Deployment Config | Medium (Nginx reverse proxy) | Low | Git mv + update server name / upstream comments | Syntax check & file review | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/src/components/BrandEmblem.jsx` | `.../components/BrandEmblem.jsx` (contents) | Visual Brand Asset | High (Rendered across all pages) | Low | Replace sakura flower with VERA Geometric Network Core SVG | Visual inspection & component tests | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/index.html` (Title & Meta) | `.../index.html` | Visible UI Identity | Medium (Browser tab, PWA metadata) | Low | Update title to "VERA — Enterprise Network Intelligence", theme color to `#071426` | Build verification | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/public/manifest.json` | `.../manifest.json` | PWA Manifest | Low (PWA install identity) | Low | Update name to "VERA", short_name to "VERA", theme_color to `#071426` | JSON validation | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/src/components/navConfig.js` | `.../navConfig.js` | Visible UI Identity | Medium (Sidebar menu labels) | Low | Change `"AIRA Control Plane"` to `"VERA Control Plane"` | React UI test | Scheduled |
| `AIRA_ECOSYSTEM/app/frontend/src/theme/colors.js` & `index.css` | `.../theme/` & CSS vars | Design System | High (Theme across all UI) | Low | Centralize VERA design tokens (Electric Blue, Cyan, Deep Navy, Steel Gray) | Visual inspection | Scheduled |
| `AIRA_ECOSYSTEM/api/main.py` (FastAPI metadata) | `.../api/main.py` | API Identification | Low (OpenAPI schema title) | Low | Update title to `"VERA Enterprise Network Intelligence API"` | FastAPI startup check | Scheduled |
| `AIRA_ECOSYSTEM/core/logger.py` (`aira.api` logger) | `.../core/logger.py` | Internal Logging | Low (Log streams) | Low | Support `vera.*` with backward-compatible fallback | Logger tests | Scheduled |
| Environment variables (`AIRA_SECRET_KEY`, `AIRA_ADMIN_TOKEN`, etc.) | Dual-lookup (`VERA_*` or `AIRA_*`) | Internal Identifiers | High (Config loading) | Low | Non-breaking fallback in `os.getenv` calls | Pytest regression suite | Scheduled |
| `pytest.ini` (`pythonpath = AIRA_ECOSYSTEM`) | Update to `VERA_ECOSYSTEM` | Build Config | High (Pytest test runner) | Low | Update `pytest.ini` with `VERA_ECOSYSTEM` + keep symlink | Run pytest suite | Scheduled |
| `Dockerfile` & `docker-compose.yml` | Update paths to `VERA_ECOSYSTEM` | Deployment | Medium (Docker builds) | Low | Update Dockerfile COPY & working dir paths | Config syntax verification | Scheduled |
| `.github/workflows/ci.yml` | Update CI paths to `VERA_ECOSYSTEM` | CI / CD | Medium (GitHub Actions) | Low | Update workflow paths | Syntax check | Scheduled |
| Historical files (`docs/AIRA_PHASE*.md`, `AUDIT_REPORT/`) | Unchanged | Historical Record | None | None | Preserve without modification | Preserved | Preserved |

---

## 3. Risk Mitigation & Integrity Rules
1. **Zero Downtime Renaming**: A filesystem symlink `AIRA_ECOSYSTEM -> VERA_ECOSYSTEM` ensures any external script or hardcoded legacy path retains immediate 100% path resolution.
2. **Environment Variable Fallback**:
   ```python
   secret = os.getenv("VERA_SECRET_KEY") or os.getenv("AIRA_SECRET_KEY", default)
   ```
   Ensures existing deployment secrets continue to authenticate seamlessly.
3. **Database Files**: Filenames `topology.db`, `inventory.db`, `network_intelligence.db`, `chat_sessions.db` do not contain "AIRA" in their base filenames and remain untouched. SQLite integrity checks (`PRAGMA integrity_check`) will be performed prior to and following directory migration.
