# VERA Reliability Baseline & Forensic Audit Report

**Date:** 2026-11-10  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P0 Forensic Investigation & System Health Baseline  
**Audit Target Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  

---

## 1. Executive Summary

This forensic baseline establishes the verified operational state of VERA based on live inspection of the codebase, SQLite databases (`chat_sessions.db`, `jobs.db`, `topology.db`), runtime logs (`logs/aira.log`), and end-to-end component interaction traces.

Independent verification confirms that multiple previous feature completions were either partially wired, lacked defensive circuit breaking, or suffered from frontend lifecycle disconnects during browser reloads.

---

## 2. Forensic Discovery & Reproduction Findings

### 2.1 Model Timeout Cascade & Unbounded Retries
- **Observed Log Signatures:**
  ```text
  2026-11-09 23:34:59 | ERROR   | aira.rei.provider_client | chat nvidia gagal (timeout): Read timed out. (read timeout=10)
  2026-11-09 23:34:59 | WARNING | aira.task_classifier     | Classifier: provider error - Read timed out.
  2026-11-09 23:39:31 | ERROR   | aira.rei.provider_client | chat nvidia gagal (timeout): Read timed out. (read timeout=45.0)
  2026-11-09 23:39:31 | INFO    | aira.rei.provider_client | Retry 1/2 ke 'Mistral Large 4' (timeout).
  2026-11-09 23:40:18 | ERROR   | aira.rei.provider_client | chat nvidia gagal (timeout): Read timed out. (read timeout=45.0)
  2026-11-09 23:40:19 | INFO    | aira.rei.provider_client | Retry 2/2 ke 'Mistral Large 4' (timeout).
  2026-11-09 23:40:26 | INFO    | aira.rei.planner         | Planner dihentikan oleh user (cancel_event).
  ```
- **Code Trace:**
  - `agents/rei/provider_client.py`: `DEFAULT_LLM_TIMEOUT = 45.0s`. `_attempt()` implements a loop retrying up to 2 times for transient errors (`timeout`, `connection`).
  - Total latency per failure: $10\text{s (classifier)} + 45\text{s} + 2\text{s} + 45\text{s} + 4\text{s} + 45\text{s} = 151\text{s}$ (> 2.5 minutes).
  - No `ProviderHealthManager` or `CircuitBreaker` exists for LLM providers. Every turn blindly attacks the failing endpoint.
  - Auxiliary tasks like `auto_extract` also hammer the dead provider, locking up background worker threads.

### 2.2 Session ID Identity Mismatch (`103ef1504de2` vs `5c854ba1534b`)
- **Forensic Evidence:**
  - In `chat_sessions.db`:
    - Session `5c854ba1534b`: Created at 13:51:16, had extensive discussions on topology, VRRP, and DHCP failover (Turns 157–162).
    - Session `103ef1504de2`: Created at 16:15:37 with title "apakah kamu bisa melanjutkan prosesnya vera?" (Turns 163–172).
- **Root Cause:**
  - `SessionsContext.jsx:15`: `const [activeId, setActiveId] = useState(null)`.
  - On page refresh (F5), `activeId` is initialized to `null`.
  - The URL does not track session ID, and `SessionsContext` never stores or restores `activeId` from `localStorage`.
  - The user refreshes, lands on an empty New Chat, types "apakah kamu bisa melanjutkan prosesnya vera?", which creates a brand new session (`103ef1504de2`), completely orphaned from `5c854ba1534b`.

### 2.3 User Prompt Disappearing on Browser Reload
- **Code Trace:**
  - `api/routers/ws.py:339`:
    `user_turn_id = store.add_turn(session_id, "user", display_message)`
    `assistant_turn_id = store.add_turn(session_id, "assistant", result.answer...)`
  - The user message is only committed to `chat_turns` in SQLite **AFTER** `brain.think()` successfully completes.
  - While `brain.think()` is waiting or streaming, the user message exists solely in frontend React memory (`messagesRef.current`).
  - When the user presses F5 or the provider times out, the database has zero record of the user prompt, causing total prompt loss.

### 2.4 "Ask VERA on Selected Text" Doing Nothing
- **Code Trace:**
  - `useSelectionContext.js:32-38`:
    ```javascript
    function handleSelectionChange() {
      const sel = window.getSelection?.();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
        setSelection(null);
        return;
      }
    ```
  - When the user clicks the "Tanya VERA" button in `SelectionToolbar.jsx`, the click event shifts browser focus, collapsing the selection (`sel.isCollapsed === true`).
  - `handleSelectionChange` immediately executes and sets `selection = null`.
  - `MessageBubble.jsx` unmounts `{selection && <SelectionToolbar ... />}`, causing the toolbar to disappear instantly before any action or question can be entered.

### 2.5 Inappropriate Generic Recovery Forms
- **Code Trace:**
  - `core/vae/composer.py:439-442`: Checked if output string contained `"failed"`.
  - `core/vae/recovery.py`: Rendered generic "Coba Lagi Operasi" and "Ubah Parameter Input" forms even when operations completed normally or had no user-editable parameters.

---

## 3. Subsystem Health Matrix

| Subsystem | Audit Finding | Severity | Target Architecture |
| :--- | :--- | :---: | :--- |
| **Provider Health** | Missing circuit breaker; 2.5m timeout loop | **CRITICAL** | `ProviderHealthManager` with 3-state CircuitBreaker |
| **Session Persistence** | `activeId` reset to null on reload; session split | **CRITICAL** | `localStorage` + URL session anchoring |
| **Prompt Durability** | User prompt committed only after success | **CRITICAL** | Commit user turn before execution begins |
| **Selection Intelligence** | Toolbar unmounts on click due to selection collapse | **HIGH** | Interaction-aware selection preservation |
| **Workflow Recovery** | Generic forms appear on benign or finished tasks | **HIGH** | Strict error-category gating |
| **Observability** | Only raw tool events; no provider wait status | **HIGH** | Typed execution timeline (`model.request.*`, `job.*`) |
| **Pause & Resume** | Only cancel supported; no checkpoint resume | **HIGH** | `PAUSED` state with instruction update |

---

## 4. Immediate Remediation Action Plan

1. **Stage 2:** Implement `core/provider_health.py` with `ProviderHealthManager`, circuit breaker, bounded backoff, intelligent timeouts, and heuristic classifier fallback.
2. **Stage 3:** Fix session persistence in `SessionsContext.jsx`, persist user prompt immediately in `ws.py`, and stream checkpoints to `job_store`.
3. **Stage 4:** Implement `PAUSED` state, checkpoint persistence, and resume with additional instructions.
4. **Stage 5:** Implement universal execution timeline and tool activity cards.
5. **Stage 6:** Ensure adaptive generative UI selection and interactive SVG DOM canvas.
6. **Stage 7:** Fix `useSelectionContext.js` toolbar focus retention and eliminate generic recovery forms.
7. **Stage 8:** Verify smart scroll, notifications, and run complete regression test suite.
