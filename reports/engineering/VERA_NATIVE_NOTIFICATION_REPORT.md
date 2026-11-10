# VERA Native Desktop Notifications Architecture & Specification Report

**Subsystem:** Operating System Integration / User Experience  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P1/P0 System Interaction & Operator Ergonomics  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Overview & Operational Need

Network engineering diagnostics and automated remediation workflows (such as topology-wide discovery scans, route convergence verification, and firmware audits) often execute for minutes. Requiring operators to continuously stare at a browser tab reduces operational productivity.

The VERA Native Desktop Notification engine provides background alerts when operations complete, require authorization, or encounter high-severity network incidents, allowing engineers to multitask across terminal windows and operational dashboards safely.

---

## 2. Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Browser Context                       │
│                                                             │
│   ┌───────────────────────────┐                             │
│   │   ChatRuntimeContext      │                             │
│   │ (receives "response" /    │                             │
│   │  "approval_required")     │                             │
│   └─────────────┬─────────────┘                             │
│                 │                                           │
│                 ▼                                           │
│   ┌───────────────────────────┐                             │
│   │   notificationService.js  │                             │
│   │  - permission check       │                             │
│   │  - document visibility    │                             │
│   │  - deduplication tag      │                             │
│   └─────────────┬─────────────┘                             │
│                 │                                           │
│        ┌────────┴──────────────────┐                        │
│        ▼                           ▼                        │
│ ┌───────────────┐         ┌───────────────────┐             │
│ │ Service Worker│         │window.Notification│             │
│ │ (background)  │         │  (tab fallback)   │             │
│ └──────┬────────┘         └────────┬──────────┘             │
└────────┼───────────────────────────┼────────────────────────┘
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Operating System Notification            │
│           [ VERA — Analisis Jaringan Selesai ]              │
│       "Tanggapan pada 'RouterOS VRRP Failover' siap."       │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Component Specifications

#### A. `VERA_ECOSYSTEM/app/frontend/src/services/notificationService.js`
- **Permission Lifecycle:** Encapsulates `isNotificationSupported()`, `getNotificationPermission()`, and `requestNotificationPermission()`.
- **Preference Persistence:** Manages user preference in `localStorage` under `vera_desktop_notifications_enabled`.
- **Visibility-Aware Throttling:** `onlyWhenHidden: true` checks `document.visibilityState === "hidden"`. If the engineer is actively viewing the VERA tab, desktop notifications are suppressed to prevent redundancy.
- **Deduplication:** Stable tags (`tag: run-done-${sid}-${runId}`) prevent duplicate alerts for the same operation.

#### B. `VERA_ECOSYSTEM/app/frontend/public/service-worker.js`
- **`push` Listener:** Receives push payloads and invokes `self.registration.showNotification(title, options)`.
- **`notificationclick` Listener:** Closes notification, searches active browser windows matching origin, focuses the existing tab, and navigates to the target deep link (e.g. `/chat/{session_id}`). If no window is open, calls `clients.openWindow(url)`.

#### C. Integration in `ChatRuntimeContext.jsx`
- In `case "response":`:
  ```javascript
  showDesktopNotification({
    title: "VERA — Analisis Selesai",
    body: data.session_title
      ? `Tanggapan pada "${data.session_title}" telah siap.`
      : "Operasi dan tanggapan jaringan telah selesai.",
    tag: `run-done-${sid}-${runId || "latest"}`,
  });
  ```

---

## 3. Privacy, Security & User Agency

1. **Explicit Opt-In:** Notifications are never triggered without explicit user permission.
2. **Local Processing:** In-app notification triggers are evaluated entirely client-side without sending sensitive payload data to external push endpoints unless configured for enterprise web push.
3. **Sensitive Data Redaction:** Notification bodies include operational summaries (e.g. "Tanggapan telah selesai") rather than full routing tables or credential information.

---

## 4. Verification

- Tested notification dispatch across backgrounded browser tabs and window minimizations.
- Verified click handler focuses the existing VERA tab without triggering unnecessary reloads.
- Verified deduplication tags suppress duplicate alerts.
