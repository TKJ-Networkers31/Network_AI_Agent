# VERA WebSocket Stream Resume & Event Replay Report

**Subsystem:** Realtime Communication Fabric / WebSocket Transport  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P0 User Experience Continuity & Reconnection Reliability  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Problem Statement & Root Cause

Previously, when a user submitted a complex network query (e.g., evaluating multi-hop traceroute latency and RouterOS BGP table stability) and refreshed the browser tab, the following breakdown occurred:
1. React's context unmounted, resetting `runsRef.current` in `ChatRuntimeContext.jsx` to an empty object `{}`.
2. A new WebSocket connected to `/ws/chat/{session_id}`.
3. The server accepted the connection, but did not announce that a background task was actively running.
4. The user's UI appeared completely idle with the prompt input enabled.
5. If the user attempted to submit a query, the backend replied with:
   `"Chat ini masih memproses permintaan sebelumnya. Tekan Stop dulu atau tunggu selesai."`
6. The user was stranded with no progress bar, no tool status, no stream text, and an input lock they could not easily explain.

---

## 2. Architecture & Technical Solution

```
┌────────────────────────────────┐            ┌────────────────────────────────┐
│         Client Browser         │            │          VERA Backend          │
│ (React + ChatRuntimeContext)   │            │   (FastAPI + ws.py + bridge)   │
└──────────────┬─────────────────┘            └──────────────┬─────────────────┘
               │                                             │
               │─────── Browser Reload / Reconnect ─────────►│
               │        ws://.../ws/chat/{session_id}        │
               │                                             │
               │◄────── active_run_resumed Event ────────────│
               │   - run_id: "r123..."                       │
               │   - phase: "streaming" | "tool_execution"   │
               │   - accumulated_text: "Checking BGP..."     │
               │   - live_tools: [{tool, status}]            │
               │                                             │
               │ (Reconstitutes active run & bubble)         │
               │ (Continues streaming without 0% reset)      │
               │                                             │
               │◄────── stream_delta / tool_finish ──────────│
               │                                             │
               │◄────── response (Final VAE Payload) ────────│
               ▼                                             ▼
```

### 2.1 Server-Side Event Synchronization (`api/routers/ws.py` & `api/ws_bridge.py`)

1. **Active Run Cache Accumulation:**
   In `ws_bridge.py`, as events pass through the internal `EventBus`, `_on_event` translates and passes events to `update_active_run_event(session_id, event_type, data)`.
   - Incoming `stream_delta` chunks are appended to `run["accumulated_text"]`.
   - Tool execution (`tool_start`, `tool_finish`) updates `run["live_tools"]`.
   - `phase` dynamically updates (`thinking` $\rightarrow$ `tool_execution` $\rightarrow$ `streaming`).
   - Every event is recorded in `jobs.db` via `JobStore.record_event`.

2. **Immediate Connection Hydration:**
   When a client opens or reconnects to `/ws/chat/{session_id}`, `chat_ws` immediately checks `_ACTIVE_RUNS.get(session_id)`. If an active task is running, it transmits:
   ```json
   {
     "type": "active_run_resumed",
     "data": {
       "session_id": "session_uuid",
       "run_id": "run_uuid",
       "job_id": "job_uuid",
       "phase": "streaming",
       "accumulated_text": "Analyse prefix distribution on R1-Core...",
       "live_tools": [
         {"tool": "fetch_bgp_summary", "status": "success", "output": "..."}
       ],
       "ts": 1773179500.12
     }
   }
   ```

3. **Deterministic Event Replay:**
   If a client requires historical event verification, it can send `{"type": "request_replay", "since_id": 0}` over the WebSocket. The server retrieves persisted `JobEvent` records and returns a `replay_events` payload.

### 2.2 Frontend Hydration & Non-Destructive Update (`ChatRuntimeContext.jsx`)

Upon receiving `active_run_resumed`:
1. `setRun(sid, restoredRun)` restores the active run status, phase, and tool list in `runsRef.current` and state.
2. If `accumulated_text` is non-empty, `setMessagesForSession` ensures that an active assistant bubble with `streaming: true` is placed in the message stack with the already received text.
3. The conversation history is never wiped or re-requested prematurely.
4. When subsequent `stream_delta` chunks or the terminal `response` arrive, they smoothly update or replace the existing bubble.

---

## 3. Verification & Observability

- **Zero Amnesia on Refresh:** Verified by initiating long-running turns and issuing browser reloads. The active run resumes immediately with live tool execution cards and partial response text.
- **Truthful Progress:** Progress indicators do not reset to 0% upon reconnection; the active phase (`tool_execution` or `streaming`) and all completed sub-steps are rendered accurately.
- **Graceful Termination:** When the turn finishes, `response` fires, clearing the run and finalizing the message bubble into immutable conversation history.
