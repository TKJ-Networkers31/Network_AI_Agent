# VERA — INTERACTIVE SVG & ADAPTIVE VISUAL ASSET ARCHITECTURE REPORT

**Document ID:** `VERA-REP-SVG-ASSET-01`  
**Classification:** Advanced Data Visualization & Vector Graphics Architecture  
**Status:** IMPLEMENTED & TEST VERIFIED  
**Date:** 2026-11-10  
**Author:** Principal Generative UI Architect & Vector Graphics Specialist  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/`

---

## 1. EXECUTIVE SUMMARY

Network topology diagrams in AI platforms commonly suffer from overlapping labels, non-interactive static images, or broken aspect ratios. 

VERA addresses this with a dedicated vector rendering pipeline:
1. **Scene Graph & Topology Model (`sceneGraph.js`):** Typed representation of networking entities (`CORE_ROUTER`, `DISTRIBUTION`, `ACCESS_SWITCH`, `FIREWALL`, `SERVER`, `CLOUD`).
2. **Deterministic Layout Engine (`layoutEngine.js`):** Force-directed and tiered hierarchical positioning with collision prevention.
3. **Interactive Canvas (`InteractiveSvgCanvas.jsx`):** React-managed SVG DOM supporting smooth panning, continuous zoom (0.5x to 3.0x), and viewport reset.
4. **Animated Traffic Pulses:** Visualizing live packet transmission with operator play/pause toggles and automatic reduction for `prefers-reduced-motion`.
5. **Contextual Node Drawer (`DeviceDetailDrawer.jsx`):** Slide-out drawer displaying interfaces, IP addresses, RouterOS version, and quick-action diagnostics.
6. **Adaptive Asset Resolver (`adaptiveAssetResolver.js`):** Resolving verified manufacturer hardware references without SSRF vulnerabilities.

---

## 2. DETERMINISTIC LAYOUT & COLLISION AVOIDANCE

The SVG layout engine enforces strict clearance rules:
- **Hierarchical Tier Assignment:**
  - Tier 0: External Gateways / Cloud Providers
  - Tier 1: Core Routers (e.g., CCR2004, RB4011)
  - Tier 2: Distribution Switches
  - Tier 3: Access Switches / Endpoints
- **Collision Avoidance:** Nodes maintain a minimum horizontal distance of `160px` and vertical clearance of `120px`.
- **Curved Path Offsets:** Parallel links between the same pair of devices are curved using quadratic Bezier offsets (`calculateEdgePath`) to prevent overlapping line segments.

---

## 3. ACCESSIBILITY & MOTION CONTROL

- **Reduced Motion Compliance:** If the user’s operating system specifies `prefers-reduced-motion: reduce`, SVG path animations default to paused mode.
- **Manual Control:** A visible control pill provides instant Play/Pause toggle for all traffic flow indicators.
- **Keyboard Navigation:** All SVG nodes are focusable via `Tab` with `Enter` / `Space` opening the detail drawer.

---

## 4. AUTHORITATIVE HARDWARE CATALOG & SSRF PREVENTION

Hardware imagery is resolved through `AUTHORITATIVE_HARDWARE_CATALOG`:
- Verified vendor references for MikroTik hardware (e.g., RB4011, hAP ac lite, CCR2004).
- Safe local asset paths (`/assets/brand/...`) prevent external SSRF attacks and arbitrary remote image inclusions.
- Strict policy prohibits stock images when depicting live topology state.

---

## 5. VERIFICATION

- Validated across all SVG and VAE test cases.
- Layout correctness verified with multi-node and multi-tier topologies.
- Zero DOM hydration mismatches or layout shifts during streaming.
