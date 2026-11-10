# VERA INTERACTIVE SVG SPECIFICATION
## React-Managed SVG DOM, Dynamic Navigation, Device Detail Drawers, Motion Controls & WCAG 2.2 Accessibility

**Project:** VERA Enterprise Network Intelligence Platform  
**Subsystem:** VERA Adaptive Experience (VAE) Interactive Visuals  
**Classification:** P0 Technical Specification  
**Date:** November 2026  
**Architect:** Principal Generative UI Architect & SVG Systems Engineer  
**Component Reference:** `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/svg/InteractiveSvgCanvas.jsx`  
**Drawer Reference:** `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/svg/DeviceDetailDrawer.jsx`

---

## 1. Executive Summary

Static SVG images rendered via `<img src="data:image/svg+xml,...">` lack the interactive fidelity required for enterprise network operations. Operators cannot inspect device interfaces, trigger ping probes, trace link telemetry, or navigate large topologies from a static picture.

The **VERA Interactive SVG Engine** replaces static image tags with a **React-Managed SVG DOM**, transforming diagrams into usable operational control surfaces.

---

## 2. Interactive SVG Canvas Capabilities

### 2.1 Viewport Pan & Zoom Controls
- **Drag-to-Pan:** Smooth pointer panning with cursor state synchronization (`cursor-grab` to `cursor-grabbing`).
- **Granular Zoom:** Precision zoom-in ($1.25\times$), zoom-out ($0.8\times$), and 1-click view reset (`RotateCcw`).
- **Bounding Box Fit:** Auto-scales diagrams to fit client viewports without horizontal scrollbars.

### 2.2 Contextual Node Interaction & Device Detail Drawer
- **Pointer & Focus Activation:** Clicking or pressing `Enter` / `Space` on any node card highlights the node with a high-contrast Cyan halo (`#00E5FF`) and slides open the **Device Detail Drawer**:
  - Device Identity, Vendor, Model, and OS Version.
  - Active Management IP & Port.
  - Real-time Operational Status (Online, Backup, Offline).
  - Protocol Details (VRID, Virtual IP ownership for VRRP).
  - Instant Operational Actions:
    - **Ping Probe:** Dispatches `/network_ping` with 4 ICMP packets.
    - **Terminal Access:** Navigates directly to AKANE Web SSH console.
    - **WebFig Launch:** Opens authorized RouterOS management GUI in a secure tab.

### 2.3 Link Inspection & Broken Link Visualization
- Clicking any connector displays an inline **Link Inspection Card** detailing link status, speed/duplex, and protocol.
- **Broken / Degraded Links:** Visualized with high-visibility Rose-red dashed lines (`strokeDasharray="6 4"`) and explicit status badges, preventing confusion between active and failed routes.

### 2.4 Cluster Visualization
- Grouped devices (e.g. core router clusters) render a **Stacked-Card Visual Effect** (multiple offset backdrop borders).
- Displays total cluster count badge (e.g. `Cluster: 5 Units`).
- Clicking the cluster card opens member inventory in the detail drawer.

---

## 3. Motion Controls & WCAG 2.2 Section 2.2.2 Compliance

Animations must convey real operational meaning, not decorative distraction:
1. **Directional Flow Animation:** Active links feature pulsating stroke dash offsets representing packet movement. Inactive or broken links remain static.
2. **User Pause/Resume Toggle:** A visible Play/Pause control in the canvas toolbar allows operators to halt all moving elements at will.
3. **Respect for Reduced Motion (`prefers-reduced-motion`):**
   ```javascript
   const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
   if (mediaQuery.matches) {
     setIsMotionPaused(true);
   }
   ```
   If the operating system has reduced-motion enabled, animations are paused by default.

---

## 4. Accessibility & Keyboard Navigation (W3C SVG Access)

- **Semantic Tags:** Every SVG root includes `<title>` and `<desc>`.
- **Keyboard Tab-Stops:** All interactive node cards carry `tabIndex={0}`, `role="button"`, and descriptive `aria-label` tags (`"R1-Master, online, router"`).
- **Keyboard Triggers:** Full keyboard support (`Enter` and `Space` keydown events open detail drawers).
- **Non-Color-Only Status Communication:** Statuses are never conveyed solely by red/green colors; every status includes explicit text labels (`ONLINE`, `MASTER`, `BACKUP`, `FAILOVER`) and icons.
