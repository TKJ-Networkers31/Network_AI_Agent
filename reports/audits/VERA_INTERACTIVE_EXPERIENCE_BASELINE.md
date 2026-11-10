# VERA INTERACTIVE EXPERIENCE BASELINE
## Forensic Audit, Baseline State, Defect Reproduction & Architectural Gaps

**Project:** VERA Enterprise Network Intelligence Platform  
**Subsystem:** VERA Adaptive Experience (VAE) & Frontend Runtime  
**Classification:** P0 Forensic Audit & Baseline Report  
**Date:** November 2026  
**Auditor:** Principal Generative UI Architect, Senior React Engineer & AI Systems Engineer  

---

## 1. Executive Summary

Prior to initiating the P0 Interactive Experience Platform transformation, an exhaustive forensic inspection was conducted across the VERA codebase. This audit evaluated the end-to-end user experience, SVG rendering architecture, chat scrolling physics, selection intelligence, background job persistence, notification infrastructure, and interaction state synchronization.

Ten critical architectural deficiencies were reproduced and isolated:
1. **Broken Action Invocation:** Visible recovery buttons trigger `Error: Tipe aksi "tidak diketahui" belum didukung di UI ini.` due to mismatched invocation signatures in `capabilityInvoke.js`.
2. **Internal Metadata Leakage:** Raw string artifacts such as `1 tool digunakan svg` and `<!-- suggestions: ["..."] -->` leak directly into rendered Markdown.
3. **Static & Fragile SVG Rendering:** SVG illustrations and network topologies are rendered as static, unclickable `<img src="data:image/svg+xml,...">` tags, suffering from text truncation, unmeasured coordinate collisions, and lack of node/edge interactivity.
4. **Disruptive Auto-Scroll:** Chat view blindly invokes `scrollIntoView()` on every streamed token, forcefully yanking the viewport away whenever an operator attempts to read previous messages.
5. **Selection Intelligence Detachment:** Text selection in complex VAE blocks fails to consistently bind to parent message IDs and surrounding context.
6. **Ephemeral Execution & Refresh Amnesia:** Active assistant thinking and tool execution states are held exclusively in transient memory (`runsRef.current` and `_ACTIVE_RUNS`); refreshing the browser tab instantly erases active task animations, and reconnection triggers `400/500` busy conflicts.
7. **Absence of Native System Notifications:** The platform has no integration with the Web Notifications API or Service Worker Push handlers for notifying operators when background network analyses conclude.
8. **Lack of Adaptive Visual Asset Resolution:** Tasks cannot intelligently arbitrate between authoritative manufacturer hardware imagery, structured SVG graphs, and native telemetry charts.
9. **Monolithic Action Execution:** Backend lacks a strongly typed, validated Action Registry for discriminating actions (`retry_operation`, `edit_parameters`, `cancel_workflow`, etc.).
10. **Unchecked Layout Collisions in Topological Flows:** Critical failover diagrams (such as VRRP master/backup transitions) rely on unmeasured coordinate assumptions that cause arrow collisions and overlapping text.

This document establishes the verified forensic baseline and technical reproduction for each defect prior to code remediation.

---

## 2. Forensic Reproduction & Root Cause Analysis

### 2.1 Defect 1: Broken Recovery Action Execution
- **Reported Error:** `Tipe aksi "tidak diketahui" belum didukung di UI ini.`
- **Reproduction Steps:**
  1. Trigger an operational conflict, e.g., register duplicate device `CHR`.
  2. VAE presents `WorkflowRecoveryBlock` with recovery routes (Route A: "Perbarui Data 'CHR'", Route B: "Ubah Nama Pendaftaran").
  3. Click Route A or Route C ("Lihat Rincian").
  4. The UI displays an error toast: `Aksi seleksi gagal: Tipe aksi "tidak diketahui" belum didukung di UI ini.`
- **Forensic Trace:**
  - `WorkflowRecoveryBlock.jsx:34` calls:
    ```javascript
    onActionInvoke(action.target_tool, action.prefilled_data)
    ```
  - In `MessageBubble.jsx:362`, `onActionInvoke` is bound to `onCapabilityInvoke`:
    ```jsx
    onActionInvoke={onCapabilityInvoke}
    ```
  - In `ChatPage.jsx:310`, `handleCapabilityInvoke(capability)` expects a capability envelope `{ action: { type, prompt, tool, ... } }`.
  - When invoked with `(action.target_tool, action.prefilled_data)`, the first argument `action.target_tool` (e.g. `"update_device"`) is treated as the `capability` object.
  - `capability.action` resolves to `undefined`, so `action.type` is `undefined`.
  - `capabilityInvoke.js:55` executes:
    ```javascript
    default:
      throw new Error(`Tipe aksi "${action.type || "tidak diketahui"}" belum didukung di UI ini.`);
    ```
  - **Root Cause:** Incompatible calling convention between VAE block actions and legacy capability invoker, combined with an unvalidated action dispatcher lacking support for operational action types (`retry_operation`, `edit_parameters`, `update_device`, etc.).

---

### 2.2 Defect 2: Raw Internal Metadata & Bookkeeping Leakage
- **Reported Symptoms:**
  - Raw strings like `1 tool digunakan svg` appearing inside assistant prose.
  - Raw HTML comments `<!-- suggestions: ["Topic 1", "Topic 2"] -->` visible during streaming or when JSON parsing fails.
- **Forensic Trace:**
  - In `core/persona/prompt_builder.py:70`, the LLM is instructed to append `<!-- suggestions: [...] -->`.
  - While streaming tokens, `rawText` contains incomplete prefixes like `<!-- suggestions: ["Topic`.
  - In `MessageBubble.jsx:226`, `extractFollowupSuggestions` uses regex:
    ```javascript
    const jsonMatch = rawText.match(/<!--\s*suggestions:\s*(\[.*?\])\s*-->/is);
    ```
  - While the comment is incomplete, `jsonMatch` is `null`. The unclosed comment passes directly into `StreamingMarkdown`, which renders it as plain text or invalid HTML.
  - Furthermore, if the LLM outputs single quotes `['Topic 1']`, `JSON.parse` throws inside `try {} catch {}` and fails to strip the comment.
  - In `MessageBubble.jsx:52`, `ProcessSteps` constructs:
    ```javascript
    const summary = toolCallCount > 0 ? `${toolCallCount} tool${toolCallCount > 1 ? "s" : ""} digunakan` : "Proses selesai";
    ```
    If tool names are concatenated or leaked into the answer narrative by the LLM (e.g. `1 tool digunakan svg`), `_sanitize_narrative` in `composer.py` only cleans non-streaming responses, leaving live-streamed text contaminated.

---

### 2.3 Defect 3: SVG Rendering Quality & Interactivity Deficits
- **Reproduction Steps:**
  1. Ask assistant: *"Gambarkan topologi failover VRRP antara Router-Master dan Router-Backup dengan Virtual IP 192.168.1.1"*.
  2. Assistant generates ````svg ... ````.
  3. UI renders an `<img>` tag via `SvgBlock` in `Markdown.jsx:155`:
     ```jsx
     <img src={built.uri} alt="Ilustrasi SVG" ... />
     ```
- **Forensic Findings:**
  1. **Non-Interactive DOM:** Rendered inside `<img>` with a `data:image/svg+xml` URI. DOM elements inside the SVG cannot receive pointer events, hover states, clicks, or keyboard focus.
  2. **Unmeasured Layout Collisions:** If the LLM generates arbitrary `<text>` tags, varying character widths cause text to overflow card boundaries and overlap connecting lines.
  3. **Blank Nodes:** If the LLM produces a node card `<rect>` without properly positioned `<text>`, an unexplained blank container is displayed.
  4. **No Device Detail Panel:** Clicking a router card does not open the device's diagnostic drawer.
  5. **Accessibility Violation:** Screen readers perceive only `alt="Ilustrasi SVG"`; internal node labels, statuses, and VRRP priorities are invisible to assistive tech.

---

### 2.4 Defect 4: Disruptive Auto-Scroll Physics
- **Reproduction Steps:**
  1. Have an ongoing conversation with multiple long messages.
  2. Ask a detailed diagnostic question.
  3. While the assistant is actively streaming tokens, scroll up 300px to review earlier traceroute data.
  4. The viewport abruptly jumps back to the bottom on every received token chunk.
- **Forensic Trace:**
  - In `ChatPage.jsx:254-256`:
    ```javascript
    useEffect(() => {
      bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
    }, [messages, loading, streaming]);
    ```
  - **Root Cause:** The `useEffect` fires on every update of `messages` without checking whether the user was already near the bottom ($<100\text{px}$). It lacks reading-state anchoring, threshold detection, and a "Jump to latest" floating button.

---

### 2.5 Defect 5: Task Execution Lost on Refresh & Busy Locks
- **Reproduction Steps:**
  1. Submit a long-running diagnostic task (e.g., multi-device BGP convergence analysis).
  2. Reload the page (press F5).
  3. Observe that all processing indicators disappear.
  4. Attempt to send another message: the server responds with HTTP/WS error:
     `"Chat ini masih memproses permintaan sebelumnya. Tekan Stop dulu atau tunggu selesai."`
- **Forensic Trace:**
  - In frontend `ChatRuntimeContext.jsx:585`:
    `runsRef.current` is an ephemeral React ref. Page refresh resets it to `{}`.
  - In backend `api/routers/ws.py:426`:
    When the new WebSocket connects, it does not send the current state of `_ACTIVE_RUNS[session_id]` to the client.
  - The client is blind to the active execution, while the backend refuses new requests because the previous task is still running.

---

### 2.6 Defect 6: Missing Native System Notifications
- **Reproduction Steps:**
  1. Start a 2-minute route convergence test.
  2. Switch to another browser tab or minimize the window.
  3. The task finishes, but no desktop notification is triggered.
- **Forensic Trace:**
  - Neither `CustomerPortalPage.jsx` nor `ChatPage.jsx` registers with `window.Notification`.
  - `public/service-worker.js` contains only cache handling; it has zero event listeners for `push` or `notificationclick`.

---

## 3. Impact Assessment Matrix

| Area | Current State | Risk Level | Target Architecture (P0) |
| :--- | :--- | :---: | :--- |
| **Action Gateway** | Unmapped action types throw uncaught exceptions | **CRITICAL (P0)** | Typed Action Registry + Universal ActionGateway Execution |
| **Content Sanitization** | Bookkeeping tags leak into assistant prose | **HIGH (P0)** | Unified multi-stage sanitizer for streaming & completed text |
| **SVG Visuals** | Static `<img>` with overlapping text & blank nodes | **CRITICAL (P0)** | Declarative Scene Graph + React SVG DOM + Collision Avoidance |
| **Chat Scroll** | Forceful scrollIntoView on every token | **HIGH (P0)** | Smart Reading Auto-Follow + Near-Bottom Threshold + Pill |
| **Selection Context** | Inconsistent message association | **HIGH (P0)** | Robust SelectionToolbar + Parent Block Context Binding |
| **Job Durability** | Task state lost on browser reload | **CRITICAL (P0)** | Persistent Job DB + WS Replay & Resume Cursor |
| **Notifications** | None | **MEDIUM (P1)** | Native Notification API + Service Worker Push & Click Handling |

---

## 4. Baseline File Audit Map

The following files require targeted engineering interventions:

- **Frontend Action & Recovery:**
  - `VERA_ECOSYSTEM/app/frontend/src/utils/capabilityInvoke.js`
  - `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/interactions/ActionGateway.js`
  - `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/blocks/WorkflowRecoveryBlock.jsx`
  - `VERA_ECOSYSTEM/app/frontend/src/pages/ChatPage.jsx`
- **SVG Scene Graph & Interactive Visuals:**
  - `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/assets/svgBuilder.js`
  - `VERA_ECOSYSTEM/app/frontend/src/components/Markdown.jsx`
  - `VERA_ECOSYSTEM/app/frontend/src/components/GraphBlock.jsx`
  - *New:* `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/svg/` (Scene Graph, Interactive SvgCanvas, Layout Engine)
- **Chat Scrolling & Selection Intelligence:**
  - `VERA_ECOSYSTEM/app/frontend/src/pages/ChatPage.jsx`
  - `VERA_ECOSYSTEM/app/frontend/src/components/selection/SelectionToolbar.jsx`
  - `VERA_ECOSYSTEM/app/frontend/src/hooks/useSelectionContext.js`
- **Durable Background Execution & Reconnection:**
  - `VERA_ECOSYSTEM/api/routers/ws.py`
  - `VERA_ECOSYSTEM/core/chat_sessions.py`
  - `VERA_ECOSYSTEM/app/frontend/src/context/ChatRuntimeContext.jsx`
- **Native Notifications & Service Worker:**
  - `VERA_ECOSYSTEM/app/frontend/public/service-worker.js`
  - *New:* `VERA_ECOSYSTEM/app/frontend/src/services/notificationService.js`
