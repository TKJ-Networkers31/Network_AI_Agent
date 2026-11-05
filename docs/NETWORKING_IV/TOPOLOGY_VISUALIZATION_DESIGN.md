# AIRA OS — TOPOLOGY VISUALIZATION DESIGN
## Interactive Frontend Architecture, Canvas Enhancements & Evidence Inspector

**Document ID:** `AIRA-NET-IV-UI-001`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_UI_SPECIFICATION  

---

## 1. Frontend Architecture Audit & Framework Directives

The existing AIRA OS frontend is built on **React 18, Vite, Tailwind CSS, and Lucide React**. It operates with exceptional speed, rendering rich dashboards with minimal memory consumption and clean modular components.

### Core Directive: Zero Unnecessary Framework Additions
> [!IMPORTANT]
> **NO SECOND FRONTEND FRAMEWORK:** AIRA OS shall **NOT** import heavy third-party canvas engines (such as Cytoscape.js, D3-force, Vis.js, or GoJS). These monolithic libraries introduce significant bundle overhead (often $> 1.5\text{ MB}$), conflict with React state reconciliation, and bypass Tailwind styling.
> 
> Networking IV will continue utilizing the **Hybrid React-DOM + SVG Canvas Architecture** already proven in `TopologyPage.jsx`. Draggable cards are standard React DOM elements (giving full CSS backdrop-blur and responsive accessibility), while links and arrows are rendered via an optimized SVG layer.

---

## 2. Interactive Canvas Component Architecture

The topology user interface is organized into five modular components:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          TopologyPage.jsx                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ TopBar: Controls, Seed Picker, Mode, Auto-Discover, Review, Policy│  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Governance Bar: View Scopes, Ownership Counts, Confidence Tiers  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────┬──────────────────────────────┐  │
│  │                                   │ Node Inspector (Sidebar)     │  │
│  │        INTERACTIVE CANVAS         │  (TopologyNodeInspector.jsx) │  │
│  │                                   ├──────────────────────────────┤  │
│  │  - SVG Link Layer                 │ Edge Evidence Inspector      │  │
│  │  - DOM Node Cards                 │  (TopologyEdgeInspector.jsx) │  │
│  │  - Parallel Bezier Curves         │                              │  │
│  │                                   │                              │  │
│  └───────────────────────────────────┴──────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ TopologyTimeline.jsx: Snapshot Comparison & Historical Diff Bar  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Target Capabilities & Visual Specifications

### 3.1 Node & Multi-Edge Interactive Rendering
- **Draggable Node Cards:**
  - Distinct border colors and icons per device type (`router`, `switch`, `access_point`, `server`, `wan`, `client`).
  - Real-time status indicators (emerald for reachable, rose for unreachable, amber for warning/degraded).
  - Ownership badges (`Owned`, `ISP/3rd`, `Unknown`) and freshness indicators (`Fresh`, `Stale`, `Expired`).
- **Parallel Edge Rendering (Curved Bezier Paths):**
  - When two devices have multiple connections (e.g. LAG member ports `ether1` and `ether2`, or routed vs management links), lines must not overlap.
  - The SVG layer computes quadratic Bezier curves with offset control points:
    $$B(t) = (1-t)^2 P_0 + 2(1-t)t P_{ctrl} + t^2 P_1$$
    Where $P_{ctrl}$ is offset perpendicularly to the midpoint vector by index $\pm k \cdot 18\text{px}$.

### 3.2 Accessible Evidentiary Encoding
To comply with accessibility standards, confidence tiers are **never** communicated by color alone:

| Confidence Tier | Stroke Style | Line Width | Midpoint Badge Text | Interactive Meaning |
|---|---|---|---|---|
| **Tier 1: CONFIRMED** | Solid Line | 2.5px | `[Confirmed]` | Mutual L2 protocol or verified manual wiring |
| **Tier 2: HIGH** | Solid Line | 1.5px | `[Observed]` | Direct /30 subnet or single-sided LLDP |
| **Tier 3: MEDIUM** | Dashed Line (`6,4`) | 1.5px | `[Inferred]` | Shared multi-access subnet or next-hop |
| **Tier 4: LOW** | Dotted Line (`2,4`) | 1.0px | `[Candidate]` | Single-sided ARP or unverified endpoint |

### 3.3 Interactive Edge Evidence Inspector (`TopologyEdgeInspector.jsx`)
Clicking any link line or midpoint verification badge slides open the **Edge Evidence Inspector**:
1. **Edge Identity & Ports:** Source node and port (`ether1`) $\rightarrow$ Target node and port (`ether2`).
2. **Confidence Breakdown:** Composite numerical score $S(e)$ with breakdown of base weights, directionality, and decay penalties.
3. **Evidence History Table:** Chronological list of observations supporting this edge:
   - Protocol badge (`MNDP`, `LLDP`, `ARP`, `ROUTE`).
   - Observing device name and timestamp.
   - Expandable raw, sanitized CLI excerpt (e.g. exact output of `/ip neighbor print detail`).
4. **Administrative Actions:**
   - Button: `Confirm Wiring` (promotes edge to `user_confirmed`).
   - Button: `Report Conflict` (queues edge for operator review).
   - Button: `Sever Link` (deletes manual wiring).

### 3.4 Historical Topology Comparison (`TopologyTimeline.jsx`)
Allows operators to inspect past network states and perform visual diffs:
1. **Timeline Slider:** Scrub through recorded discovery runs and hourly snapshots.
2. **Visual Diff Mode:**
   - **Green Glow:** Node or edge was added since previous snapshot.
   - **Red Strikethrough:** Node or edge was removed / went offline.
   - **Yellow Pulsing:** Node or edge attributes changed (e.g., interface oper-status changed from `up` to `down`).
3. **Delta Summary Pill:** "Changes between 08:00 and 09:00: +1 Node, -0 Nodes, 1 Status Degraded".

---

## 4. Deep-Link Navigation & Ecosystem Integration

### 4.1 Device Management Integration (`DevicesPage.jsx`)
- In the Devices table or Device Detail view, clicking the **"Peta Topologi"** action stores the device ID in `sessionStorage.setItem("aira_focus_topology_node", deviceId)` and redirects to `/topology`.
- `TopologyPage.jsx` automatically centers, zooms, and highlights the target node with a glowing pulse animation.

### 4.2 Network Intelligence Integration (`NetworkIntelligencePage.jsx`)
- When viewing an active diagnostic report (e.g. from `auto_diagnose_network`), the report includes an interactive topology preview card.
- Clicking **"Investigasi Topologi"** opens the topology canvas filtered to only the primary device and its correlated upstream/downstream nodes.
