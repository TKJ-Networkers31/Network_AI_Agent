# VERA Adaptive Experience (VAE) — Rollback & Recovery Plan

**Plan Version:** 1.0.0  
**Target:** VERA Adaptive Experience Subsystem  
**Scope:** Reversible operational rollback to previous stable commit `d1d67490f4e1ba615bddff1fb6d78d51a8b00f05`  

---

## 1. Rollback Triggers

A rollback should be evaluated only under the following critical conditions:
1. **Severe Client Degradation:** Chat rendering fails globally, causing message bubbles not to display or throwing unhandled React root crashes.
2. **Streaming Regression:** Live token streaming breaks, hangs, or causes memory leaks in the browser.
3. **Severe Authentication Regression:** Legitimate users are denied access or permission checks fail completely across all tenants.

---

## 2. Emergency Rollback Procedures

### Step 1: Frontend Presentation Reversion
If an isolated frontend rendering defect occurs without backend impact:
1. Revert `MessageBubble.jsx` to render `Markdown` and `Renderer` directly:
   ```bash
   git checkout d1d67490f4e1ba615bddff1fb6d78d51a8b00f05 -- VERA_ECOSYSTEM/app/frontend/src/components/MessageBubble.jsx
   ```
2. Re-verify the frontend build:
   ```bash
   cd VERA_ECOSYSTEM/app/frontend && npm run build
   ```

### Step 2: Full Branch State Rollback
To restore the repository state cleanly to the exact baseline recorded before VAE implementation:
1. Verify no unstaged personal files are at risk:
   ```bash
   git status --short
   ```
2. Checkout baseline files for modified components:
   ```bash
   git checkout d1d67490f4e1ba615bddff1fb6d78d51a8b00f05 -- \
     VERA_ECOSYSTEM/api/routers/user_management.py \
     VERA_ECOSYSTEM/app/frontend/src/components/ActionCardBlock.jsx \
     VERA_ECOSYSTEM/app/frontend/src/components/Markdown.jsx \
     VERA_ECOSYSTEM/app/frontend/src/components/MermaidBlock.jsx \
     VERA_ECOSYSTEM/app/frontend/src/components/MessageBubble.jsx \
     VERA_ECOSYSTEM/app/frontend/src/components/dio/Field/SvgField.jsx
   ```
3. Archive or remove untracked VAE directories if necessary:
   ```bash
   rm -rf VERA_ECOSYSTEM/core/vae
   rm -rf VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience
   rm -f VERA_ECOSYSTEM/tests/test_vae_*.py
   ```

---

## 3. Post-Rollback Verification Checkpoints

After initiating any rollback step:

1. **Backend Test Suite Check:**
   ```bash
   ./.venv/bin/pytest VERA_ECOSYSTEM/tests/test_dio_*.py VERA_ECOSYSTEM/tests/test_streaming.py -v
   ```
   *Expected:* 86 passing tests.

2. **Frontend Test Suite Check:**
   ```bash
   cd VERA_ECOSYSTEM/app/frontend && npm test
   ```
   *Expected:* All tests passing.

3. **Frontend Production Build Check:**
   ```bash
   cd VERA_ECOSYSTEM/app/frontend && npm run build
   ```
   *Expected:* Vite build finishes with exit code 0.

4. **Database State Check:**
   VAE does not alter or migrate SQLite/PostgreSQL tables. No database restoration or data restore script is required.
