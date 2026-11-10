# VERA Forensic Root Cause Analysis Report

**Date:** 2026-11-10  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** Deep-Dive Forensic Architecture Diagnosis  

---

## 1. Trace Analysis of Critical Failures

### 1.1 Root Cause 1: Unbounded Provider Timeout Cascade
- **Modules Involved:**
  - `agents/rei/provider_client.py:768-786` (`_attempt`)
  - `core/task_classifier.py:160-185` (`_classify_with_llm`)
  - `core/memory.py` (`extract_and_save_facts_async`)
- **Execution Mechanism:**
  1. A user prompt is received.
  2. `task_classifier.py` calls `ProviderClient.chat` with `timeout=10`. If NVIDIA endpoint stalls, it blocks for 10 seconds.
  3. The request falls back to heuristic classification.
  4. `Brain._think` routes the prompt to the primary model (NVIDIA `mistralai/mistral-large-4-1t-a52b`).
  5. `_attempt` initiates HTTP POST to `integrate.api.nvidia.com` with `timeout=45.0`.
  6. When 45s elapses, a `requests.exceptions.Timeout` is raised.
  7. Because `timeout` is in `TRANSIENT_ERROR_TYPES`, `_attempt` sleeps 2 seconds and fires Attempt 1 (45s).
  8. Attempt 1 times out. `_attempt` sleeps 4 seconds and fires Attempt 2 (45s).
  9. Over 140 seconds are spent hammering an already unresponsive provider.
  10. `auto_extract` executes in the background, also sending requests to NVIDIA and failing.
- **Architectural Flaw:**
  The system lacks a centralized provider circuit breaker. Transient failures are treated as independent per-request events rather than systemic provider degradation.

---

### 1.2 Root Cause 2: Session Identity Amnesia & Conversation Splitting
- **Modules Involved:**
  - `app/frontend/src/context/SessionsContext.jsx:15-38`
  - `app/frontend/src/context/ChatRuntimeContext.jsx:538-558`
- **Execution Mechanism:**
  1. The user works in session `5c854ba1534b`.
  2. The user reloads the browser (F5) or reconnects.
  3. React mounts `SessionsProvider`. `activeId` is initialized as `null` by `useState(null)`.
  4. The URL does not contain `?session=5c854ba1534b`, nor does `SessionsContext` read a last-active session from `localStorage`.
  5. `activeId` remains `null`, rendering the blank "New Chat" screen.
  6. The user types "apakah kamu bisa melanjutkan prosesnya vera?".
  7. `ChatRuntimeContext.sendMessage` calls `ensureSession()`.
  8. Since `activeIdRef.current` is `null`, `ensureSession()` calls `api.sessions.create()`, generating brand new session ID `103ef1504de2`.
  9. The user is now talking in a clean-slate conversation without the routing/VRRP context of `5c854ba1534b`.
- **Architectural Flaw:**
  Session identity was purely ephemeral in frontend state, missing persistent browser-session anchoring.

---

### 1.3 Root Cause 3: Premature Prompt Loss on Interruption
- **Modules Involved:**
  - `api/routers/ws.py:339`
  - `core/chat_sessions.py:add_turn`
- **Execution Mechanism:**
  1. `_process_turn` starts upon receiving WebSocket message.
  2. The prompt is added to in-memory `memory.history`.
  3. No record is inserted into SQLite table `chat_turns`.
  4. `Brain.think()` begins and waits for LLM responses.
  5. If the user refreshes, cancels, or the server restarts during this period:
     - The turn is aborted.
     - `chat_turns` has NO record of the user prompt.
     - The prompt is permanently lost.
- **Architectural Flaw:**
  Writes to the source of truth (`chat_turns`) were delayed until terminal completion instead of persisting the user turn upon arrival.

---

### 1.4 Root Cause 4: Selection Toolbar Collapse on Interaction
- **Modules Involved:**
  - `app/frontend/src/hooks/useSelectionContext.js:32-38`
  - `app/frontend/src/components/MessageBubble.jsx:385-397`
  - `app/frontend/src/components/selection/SelectionToolbar.jsx:85-93`
- **Execution Mechanism:**
  1. User highlights text in a message.
  2. Window selection is created. `useSelectionContext` sets `selection` object.
  3. `MessageBubble` renders `<SelectionToolbar selection={selection} ... />`.
  4. User clicks "Tanya VERA" or clicks into the input field.
  5. Focusing the toolbar button or input causes the browser to collapse the window selection (`window.getSelection().isCollapsed === true`).
  6. The global `document.addEventListener("selectionchange")` listener in `useSelectionContext` fires.
  7. It evaluates `if (!sel || sel.isCollapsed) setSelection(null);`.
  8. `selection` is set to `null`.
  9. `MessageBubble` immediately unmounts the `<SelectionToolbar>`, destroying the composer before the user can type or submit.
- **Architectural Flaw:**
  The selection hook did not protect the active selection when user focus moved into the contextual toolbar.

---

### 1.5 Root Cause 5: Irrelevant Generic Recovery Blocks
- **Modules Involved:**
  - `core/vae/composer.py:430-455`
  - `core/vae/recovery.py:114-150`
- **Execution Mechanism:**
  1. A tool finishes execution.
  2. `composer.py` checks tool outputs for generic strings like `"failed"`.
  3. Even for successful commands whose output text mentioned `"0 failed"` or normal diagnostic output, `is_fail` evaluated to `True`.
  4. `UniversalRecoveryPlanner` created a generic `RecoveryPlan` with buttons "Coba Lagi Operasi" and "Ubah Parameter Input".
  5. The assistant response showed an alarming red/amber warning box with forms to edit parameters, even when the operation was completely successful.
- **Architectural Flaw:**
  Fuzzy string-matching on tool text outputs rather than strict exit code / status code validation generated false positive recovery blocks.

---

## 2. Summary of Targeted Fixes

1. **`ProviderHealthManager` (`core/provider_health.py`):** Central circuit breaker with bounded timeouts (connect: 5s, read: 25s, classifier: 4s). Fast failover when circuit is `OPEN`.
2. **Session Anchoring (`SessionsContext.jsx`):** Store active session in `localStorage.setItem("vera_active_session_id", id)` and URL search params (`?session=id`).
3. **Immediate Turn Persistence (`api/routers/ws.py`):** Commit user turn to `chat_turns` immediately upon receiving the turn.
4. **Interactive Selection Retention (`useSelectionContext.js`):** Ignore selection collapse when focus is inside `[data-selection-toolbar]`.
5. **Contextual Recovery Gating (`composer.py` & `recovery.py`):** Strictly gate recovery blocks on confirmed failures (`success is False` and error taxonomy matching).
