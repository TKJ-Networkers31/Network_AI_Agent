# VERA Accessibility, Visual Quality & Content Normalization Report

**Subsystem:** User Interface / Accessibility & Visual Presentation  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Classification:** P0 Usability & Visual Correctness Transformation  
**Status:** IMPLEMENTED & VERIFIED  

---

## 1. Executive Summary

This engineering effort resolved visual regressions and accessibility deficiencies across the VERA interface. The primary focuses included:
1. Transforming static SVG images into interactive, accessible vector documents.
2. Eliminating text collisions and unmeasured coordinate overlap in topology and VRRP diagrams.
3. Implementing WCAG 2.1 AA keyboard accessibility and motion controls (`prefers-reduced-motion`).
4. Eliminating token leakage (such as unclosed streaming suggestion comments `<!-- suggestions:` and bookkeeping strings like `1 tool digunakan svg`).
5. Establishing smart reading auto-follow behavior without disruptive scroll physics.

---

## 2. Accessibility Engineering (WCAG 2.1 AA Compliance)

### 2.1 Interactive SVG Keyboard Navigation & ARIA Semantics

In `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/svg/InteractiveSvgCanvas.jsx`:
- **Keyboard Focusable Nodes:** Each node in the SVG scene graph has `tabIndex={0}` and `role="button"`.
- **Screen Reader Announcements:** Dynamic `aria-label` providing full device context:
  `aria-label="Router: Master Router (CCR2004) - Active Master. Status: healthy. Tekan Enter untuk membuka detail."`
- **Keydown Listeners:** Supports both `Enter` and `Space` to open the contextual `DeviceDetailDrawer`.
- **Focus Rings:** Distinct 2px cyan focus indicators (`focus:outline-none focus:stroke-cyan-400 focus:stroke-2`) that respect high-contrast viewing modes.

### 2.2 Respect for Reduced Motion & User Animation Control

- **System Preference Detection:** Automatically detects `window.matchMedia("(prefers-reduced-motion: reduce)")`.
- **Interactive Motion Toggle:** A persistent button in the canvas controls enables operators to pause or play SVG animations (e.g., VRRP heartbeat pulses, network flow dashes) at will.
- **Scroll Animation Disabling:** In `ChatPage.jsx`, if reduced motion is preferred, scrolling behavior immediately switches from `"smooth"` to `"auto"` (instant jump).

---

## 3. Visual Quality & Collision Prevention

### 3.1 Deterministic SVG Layout Engine (`layoutEngine.js`)

Previously, VRRP failover diagrams suffered from severe overlapping text, labels clipping node borders, and dashed multicast lines crossing through device boxes.
The new layout engine enforces:
1. **Measured Text Dimensions:** Text is measured based on character heuristics with dynamic padding (minimum 16px horizontal, 12px vertical).
2. **Deterministic Tier Assignment:**
   - **Tier 0 ($y=40$):** Virtual Router Master VIP with dedicated IP badge.
   - **Tier 1 ($y=200$):** Master and Backup routers separated by an 80px horizontal gap with an isolated multicast heartbeat lane ($y=155$).
   - **Tier 2 ($y=360$):** Distribution switch / LAN endpoints.
3. **Collision-Free Connector Routing:** Edges calculate center-to-edge intersections and render background pill rects (`#0D1527` with 1px border) behind edge labels, guaranteeing 100% legibility over dashed and solid lines.
4. **Auto-ViewBox Calculation:** ViewBox is dynamically computed from bounding boxes with 40px safety margins to prevent viewport truncation.

---

## 4. Content Normalization & Token Leakage Sanitization

### 4.1 Root Cause of Leaked Metadata

During LLM generation, assistants often output tool tracking metadata or append suggestions in HTML comments. Two distinct leakage vectors were identified:
1. **Streaming HTML Comments:** The model outputs `<!-- suggestions: ["Reroute traffic"` token by token. Because the closing `-->` tag has not yet arrived, markdown renderers could not treat it as an HTML comment, causing raw code to flicker on the screen.
2. **Bookkeeping Tokens:** Backend or assistant output containing `1 tool digunakan svg` or `2 tools digunakan network_intelligence` occasionally leaked into prose paragraphs.

### 4.2 Multi-Stage Sanitization Solution

1. **Incremental Stream Parser (`streamParser.js`):**
   ```javascript
   export function stripIncompleteInline(text) {
     const openComment = text.lastIndexOf("<!--");
     if (openComment !== -1 && text.indexOf("-->", openComment) === -1) {
       text = text.slice(0, openComment);
     }
     ...
   }
   ```
   During streaming, any trailing unclosed comment is hidden before it reaches the markdown parser.

2. **Unified Message Bubble Sanitizer (`MessageBubble.jsx`):**
   - Parses and extracts valid suggestions from `<!-- suggestions: [...] -->` or `[SUGGESTIONS: ...]`.
   - Strips all HTML comments from prose.
   - Applies regex filter: `/\b\d+\s+tool(?:s)?\s+digunakan\s+[a-z0-9_-]+\b/gi` to clean leaked tool bookkeeping tokens from narrative responses.

---

## 5. Visual Regression & Accessibility Matrix

| Requirement | Audit Status | Mechanism |
| :--- | :---: | :--- |
| **SVG Node Overlap** | **RESOLVED** | Deterministic tier coordinate routing + measured bounding boxes. |
| **Edge Label Clipping** | **RESOLVED** | Background pill rects behind text labels. |
| **Keyboard Accessibility** | **COMPLIANT** | `tabIndex={0}`, `role="button"`, `Enter`/`Space` listeners. |
| **Screen Reader Context** | **COMPLIANT** | Descriptive `aria-label` with device role and operational health. |
| **Reduced Motion** | **COMPLIANT** | Auto-detects `prefers-reduced-motion` + interactive toggle button. |
| **Streaming Comment Leak** | **RESOLVED** | `stripIncompleteInline` in `streamParser.js`. |
| **Tool Token Leak** | **RESOLVED** | Regex sanitization filter in `MessageBubble.jsx`. |
| **Auto-Scroll Disruption** | **RESOLVED** | Smart reading auto-follow with threshold detection & floating pill. |
