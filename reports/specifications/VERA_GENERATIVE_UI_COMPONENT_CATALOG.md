# VERA GENERATIVE UI COMPONENT CATALOG
## Registered Adaptive Components, Visual Specs & Data Contracts

**Document Identity:** VERA-CATALOG-2026-V1  
**Classification:** Design System & Component Reference  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. COMPONENT REGISTRY OVERVIEW

The VAE Component Registry (`app/frontend/src/platform/adaptive-experience/registry/componentRegistry.jsx`) manages the catalog of registered visual blocks. Each component receives a strongly-typed `block` prop containing `id`, `type`, `data`, and `metadata`.

---

## 2. COMPONENT SPECIFICATIONS

### 2.1 `resource-gauge` (Resource Gauge Block)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/ResourceGaugeBlock.jsx`
- **Purpose:** High-impact visual gauges for CPU load, RAM usage, and Disk space on network routers.
- **Trigger Conditions:** Queries regarding router CPU, memory, uptime, health, or execution of `mikrotik_get_resources`.
- **Data Contract:**
  ```typescript
  {
    device: string;
    cpu: { value: number; unit?: string; status: "healthy" | "warning" | "critical" };
    memory: { value: number; used_mb: number; total_mb: number; status: "healthy" | "warning" | "critical" };
    disk: { value: number; used_mb: number; total_mb: number; status: "healthy" | "warning" | "critical" };
  }
  ```
- **Visual Styling:** Triple-column glassmorphism cards with gradient progress bars (cyan-to-emerald for normal, amber for warning, rose for critical). Displays live hardware tag and device model badge.

---

### 2.2 `metric-grid` (Metric Grid Block)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/MetricGridBlock.jsx`
- **Purpose:** Responsive grid (2 to 4 columns) of key numeric or status metrics.
- **Trigger Conditions:** System resource queries, interface rate comparisons, or multi-metric dashboards.
- **Data Contract:**
  ```typescript
  {
    items: Array<{
      title: string;
      value: string | number;
      unit?: string;
      trend?: "up" | "down" | "flat";
      status?: "healthy" | "warning" | "critical" | "neutral";
      subtitle?: string;
    }>;
  }
  ```
- **Visual Styling:** Modular metric tiles with uppercase title badges, mono-spaced values, and status glow borders.

---

### 2.3 `interface-status` (Interface Status Dashboard)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/InterfaceStatusBlock.jsx`
- **Purpose:** Comprehensive tabular view of physical and virtual network interfaces.
- **Trigger Conditions:** Queries regarding ports, links, ether status, or execution of `mikrotik_get_interfaces`.
- **Data Contract:**
  ```typescript
  {
    device: string;
    total_count: number;
    up_count: number;
    interfaces: Array<{
      name: string;
      type: string;
      status: "UP" | "DOWN";
      running: boolean;
      mtu?: number | string;
    }>;
  }
  ```
- **Visual Styling:** Dark-surface table with status badges (pulsing emerald dot for UP, rose for DOWN), interface type icons, and header badge showing total active links.

---

### 2.4 `hop-by-hop-traceroute` (Traceroute Hop Visualization)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/TraceroutePathBlock.jsx`
- **Purpose:** Hop-by-hop network path diagnostic breakdown.
- **Trigger Conditions:** Diagnostic traceroute queries or execution of `network_traceroute` / `mikrotik_traceroute`.
- **Data Contract:**
  ```typescript
  {
    target: string;
    reached: boolean;
    total_hops: number;
    hops: Array<{
      hop: number;
      ip: string | null;
      host?: string;
      avg_rtt_ms?: number;
      status?: "SUCCESS" | "REACHED" | "TIMEOUT";
    }>;
  }
  ```
- **Visual Styling:** Chronological hop list with hop number bubbles, DNS hostname annotations, color-coded latency pills (<20ms green, 20-80ms amber, >80ms red), and destination reached banner.

---

### 2.5 `route-table-view` (Route Table View)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/RouteTableViewBlock.jsx`
- **Purpose:** Structured routing table (RIB/FIB) representation.
- **Trigger Conditions:** Route queries, default gateway lookups, or execution of `mikrotik_get_routes`.
- **Data Contract:**
  ```typescript
  {
    device: string;
    routes: Array<{
      dst_address: string;
      gateway: string;
      flags: string;
      status: "ACTIVE" | "INACTIVE";
    }>;
  }
  ```
- **Visual Styling:** Monospace route table displaying protocol flags (`A S`, `ADC`), CIDR destination prefixes, nexthop gateways, and status tags.

---

### 2.6 `incident-summary` / `root-cause-panel` (Incident & RCA Panel)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/IncidentSummaryBlock.jsx`
- **Purpose:** Operational alert summaries, blast radius, and AI-driven Root Cause Analysis.
- **Trigger Conditions:** Outage alerts, NMS alarms, or execution of `root_cause_analysis`.
- **Data Contract:**
  ```typescript
  {
    incident_id: string;
    title: string;
    severity: "P1" | "P2" | "P3";
    root_cause: string;
    confidence: number;
    recommendations?: Array<string | { title: string }>;
  }
  ```
- **Visual Styling:** High-visibility amber/rose alert borders, severity badges, confidence percentage bar, and actionable bulleted recommendations.

---

### 2.7 `config-diff` (Configuration Diff Viewer)
- **Component File:** `app/frontend/src/platform/adaptive-experience/blocks/ConfigDiffBlock.jsx`
- **Purpose:** Side-by-side or unified diff comparison for proposed configuration changes.
- **Trigger Conditions:** Configuration change proposals, script rollbacks, or change impact planning.
- **Data Contract:**
  ```typescript
  {
    device: string;
    diff_text: string;
  }
  ```
- **Visual Styling:** Code terminal view highlighting added lines (`+`) in emerald and removed lines (`-`) in rose with line numbers and pre-flight validation tag.

---

### 2.8 `action-card` (Unified Action Card)
- **Component File:** `app/frontend/src/platform/adaptive-experience/interactions/UnifiedActionCard.jsx`
- **Purpose:** Interactive proposal card for state-changing operations requiring confirmation.
- **Trigger Conditions:** Commands with risk (e.g. firewall updates, route changes, playbook executions).
- **Data Contract:**
  ```typescript
  {
    action_id: string;
    title: string;
    description: string;
    target_device?: string;
    command?: string;
    risk_level: "low" | "medium" | "high" | "critical";
  }
  ```
- **Visual Styling:** Two-step confirmation with risk level badge, preview command block, and "Cancel" / "Confirm & Apply" buttons connected to `ActionGateway`.

---

### 2.9 `markdown` (Primary Narrative Block)
- **Component File:** `app/frontend/src/components/Markdown.jsx`
- **Purpose:** Standard rich text narrative for executive summaries, explanations, and advice.
- **Visual Styling:** Typography-optimized markdown with KaTeX math rendering, table support, and auto-linked URLs.
