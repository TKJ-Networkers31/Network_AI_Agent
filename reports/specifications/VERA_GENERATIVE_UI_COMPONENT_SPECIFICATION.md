# VERA GENERATIVE UI COMPONENT SPECIFICATION
## Comprehensive Component Families, Data Schemas, Interaction Contracts & Visual Tokens

**Project:** VERA — Enterprise Network Intelligence Platform  
**Subsystem:** VERA Adaptive Experience (VAE)  
**Classification:** P0 Technical Specification  
**Date:** November 2026  
**Architect:** Principal Generative UI Architect & Frontend Platform Architect  
**Frontend Registry:** `VERA_ECOSYSTEM/app/frontend/src/platform/adaptive-experience/componentRegistry.jsx`  
**Backend Models:** `VERA_ECOSYSTEM/core/vae/models.py`

---

## 1. Component Registry Architecture

The VERA Adaptive Experience (VAE) relies on an extensible, typed Component Registry that decouples the backend block composition pipeline from frontend React rendering implementations.

Every component conforms to the standard **VAE Block Contract**:
```typescript
interface VaeBlockProps<T = any> {
  id: string;
  type: string;
  title?: string;
  data: T;
  interactive?: boolean;
  onAction?: (actionId: string, payload?: any) => void;
  metadata?: Record<string, any>;
}
```

If an unrecognized block type reaches the frontend renderer, it safely degrades to `UnknownBlockFallback.jsx`, preventing UI crashes.

---

## 2. Component Family A: Network Status & Diagnostics

### 2.1 `resource-gauge`
Visualizes real-time hardware utilization metrics (CPU, RAM, Storage) for network appliances.
- **Component File:** `src/platform/adaptive-experience/blocks/ResourceGaugeBlock.jsx`
- **Data Contract:**
  ```json
  {
    "device": "hAP ac lite",
    "cpu": { "value": 14.0, "status": "healthy" },
    "memory": { "used_mb": 9.8, "total_mb": 64.0, "percent": 15.3, "status": "healthy" },
    "storage": { "used_mb": 8.0, "total_mb": 16.0, "percent": 50.0, "status": "healthy" },
    "uptime": "2w4d"
  }
  ```
- **Visual Design:** Circular SVG gauge for CPU load with threshold-based color coding ($<70\%$ Cyan/Emerald, $70\text{--}89\%$ Amber, $\ge 90\%$ Rose), paired with linear bar meters for RAM and disk storage.

### 2.2 `interface-status`
Presents physical and logical interface operational states, MTU, packet counters, and transceiver telemetry.
- **Component File:** `src/platform/adaptive-experience/blocks/InterfaceStatusBlock.jsx`
- **Data Contract:**
  ```json
  {
    "device": "R-Core-01",
    "total": 5,
    "running_count": 4,
    "interfaces": [
      { "name": "ether1", "type": "ether", "running": true, "disabled": false, "mtu": 1500, "status": "up" },
      { "name": "wlan1", "type": "wlan", "running": false, "disabled": true, "mtu": 1500, "status": "disabled" }
    ]
  }
  ```
- **Visual Design:** Grid of compact interface badges displaying link states with running indicators, duplex icons, and click-to-filter capability.

### 2.3 `traceroute-path`
Presents hop-by-hop packet traversal with latency measurements and packet loss indicators.
- **Component File:** `src/platform/adaptive-experience/blocks/TraceroutePathBlock.jsx`
- **Data Contract:**
  ```json
  {
    "target": "8.8.8.8",
    "reached": true,
    "total_hops": 3,
    "hops": [
      { "hop": 1, "host": "192.168.0.1", "ip": "192.168.0.1", "avg_rtt_ms": 1.2, "status": "SUCCESS" },
      { "hop": 2, "host": "isp-core.net", "ip": "10.20.30.1", "avg_rtt_ms": 8.5, "status": "SUCCESS" },
      { "hop": 3, "host": "dns.google", "ip": "8.8.8.8", "avg_rtt_ms": 14.2, "status": "REACHED" }
    ]
  }
  ```
- **Visual Design:** Connected node step-line showing chronological hops, color-coded latency pills ($<20\text{ms}$ Emerald, $20\text{--}80\text{ms}$ Amber, $>80\text{ms}$ Rose), and destination target marker.

### 2.4 `health-summary`
Provides high-level system operational score with breakdown of constituent factor ratings.
- **Component File:** `src/platform/adaptive-experience/blocks/HealthSummaryBlock.jsx`
- **Data Contract:**
  ```json
  {
    "overall_score": 94,
    "status": "healthy",
    "device_name": "R-Core-Edge",
    "factors": [
      { "name": "CPU Stability", "score": 98, "status": "healthy", "description": "Average load 12%" },
      { "name": "Memory Availability", "score": 85, "status": "healthy", "description": "54MB free of 64MB" },
      { "name": "Link Errors", "score": 100, "status": "healthy", "description": "0 frame errors detected" }
    ]
  }
  ```

---

## 3. Component Family B: Routing & Forwarding Intelligence

### 3.1 `route-table-view`
Interactive FIB/RIB routing table inspector with active/inactive filtering and next-hop status.
- **Component File:** `src/platform/adaptive-experience/blocks/RouteTableViewBlock.jsx`
- **Data Contract:**
  ```json
  {
    "device": "R-Border",
    "total_routes": 3,
    "routes": [
      { "dst": "0.0.0.0/0", "gateway": "192.168.1.1", "active": true, "distance": 1, "protocol": "static" },
      { "dst": "10.10.0.0/16", "gateway": "10.0.0.2", "active": true, "distance": 110, "protocol": "ospf" }
    ]
  }
  ```
- **Visual Design:** High-density, searchable table with protocol color pills (Static: Slate, OSPF: Purple, BGP: Blue) and distance badges.

### 3.2 `topology-detail`
Node and link inspector for multi-layer topology insights.
- **Component File:** `src/platform/adaptive-experience/blocks/TopologyDetailBlock.jsx`
- **Data Contract:**
  ```json
  {
    "device_id": "dev_r_core",
    "hostname": "R-Core",
    "hardware": "MikroTik RB4011iGS+",
    "os_version": "RouterOS v7.15",
    "ip_addresses": ["192.168.10.1", "10.255.0.1"],
    "neighbors": [
      { "neighbor_name": "SW-Dist-01", "local_interface": "ether2", "neighbor_interface": "sfp-sfpplus1", "discovery_protocol": "LLDP" }
    ]
  }
  ```

---

## 4. Component Family C: Incident & Anomaly Management

### 4.1 `incident-summary`
Visual anomaly executive summary highlighting incident severity, impacted topology, and recommended action.
- **Component File:** `src/platform/adaptive-experience/blocks/IncidentSummaryBlock.jsx`
- **Data Contract:**
  ```json
  {
    "incident_id": "INC-2026-0042",
    "title": "BGP Peer Flapping on Border-01",
    "severity": "CRITICAL",
    "affected_devices": ["Border-01"],
    "root_cause": "TCP RST packets received from peer AS64512 during link saturation",
    "recommendation": "Verify upstream MTU mismatch or queue buffer drops on ether1"
  }
  ```

### 4.2 `investigation-timeline`
Chronological investigation timeline tracing events, diagnostic actions, and state transitions.
- **Component File:** `src/platform/adaptive-experience/blocks/InvestigationTimelineBlock.jsx`
- **Data Contract:**
  ```json
  {
    "title": "Incident Investigation Progression",
    "events": [
      { "timestamp": "14:22:01", "type": "ALERT", "title": "BGP Session Down", "description": "Peer 10.1.1.2 unreachable", "status": "critical" },
      { "timestamp": "14:22:05", "type": "PROBE", "title": "Automated ICMP Check", "description": "Packet loss 0% on gateway", "status": "info" },
      { "timestamp": "14:22:15", "type": "ANALYSIS", "title": "Root Cause Isolated", "description": "Hold timer expired (90s)", "status": "warning" }
    ]
  }
  ```

---

## 5. Component Family D: Configuration & Change Management

### 5.1 `config-diff`
Side-by-side or inline syntax-highlighted difference inspector for RouterOS and network scripts.
- **Component File:** `src/platform/adaptive-experience/blocks/ConfigDiffBlock.jsx`
- **Data Contract:**
  ```json
  {
    "device": "R-Core",
    "mode": "inline",
    "changes": [
      { "type": "unchanged", "line": "/ip firewall filter" },
      { "type": "removed", "line": "add chain=forward action=accept comment=\"temp allow\"" },
      { "type": "added", "line": "add chain=forward action=drop connection-state=invalid" }
    ]
  }
  ```

### 5.2 `unified-action-card`
Enterprise change approval gate with dry-run simulation, RBAC verification, and cryptographic signing.
- **Component File:** `src/components/ActionCardBlock.jsx`
- **Data Contract:**
  ```json
  {
    "action_id": "act_cfg_apply_829",
    "title": "Apply Firewall Hardening Rules",
    "risk_level": "MEDIUM",
    "requires_approval": true,
    "simulation": { "can_execute": true, "impact_summary": "1 rule removed, 1 rule added" }
  }
  ```

---

## 6. Component Family E: Interaction & Input

### 6.1 `dio-interaction`
Dynamic Interactive Orchestration form renderer providing typed input controls (text, number, IP, select, switch).
- **Component File:** `src/components/dio/Renderer.jsx`

### 6.2 `workflow-recovery`
Universal workflow recovery interface presenting conflict diagnosis, existing entity details, and contextual recovery choices.
- **Component File:** `src/platform/adaptive-experience/blocks/WorkflowRecoveryBlock.jsx`
- **Data Contract:**
  ```json
  {
    "workflow_id": "rec_d9a8f2",
    "category": "DUPLICATE_RESOURCE",
    "user_message": "Perangkat 'CHR' sudah terdaftar dalam sistem.",
    "summary": "Konflik Pendaftaran: Perangkat dengan nama 'CHR' sudah ada di inventaris.",
    "original_tool": "add_device",
    "original_input": { "name": "CHR", "host": "192.168.0.1", "port": 22 },
    "existing_resource": { "name": "CHR", "host": "192.168.0.1", "port": 22, "device_type": "mikrotik" },
    "recovery_actions": [
      {
        "action_id": "act_update_01",
        "action_type": "UPDATE_EXISTING",
        "label": "Perbarui Data 'CHR'",
        "description": "Timpa konfigurasi perangkat yang sudah ada dengan parameter baru.",
        "target_tool": "update_device",
        "is_primary": true,
        "schema": { ... }
      },
      {
        "action_id": "act_edit_02",
        "action_type": "EDIT_FORM",
        "label": "Ubah Nama Pendaftaran",
        "description": "Gunakan nama berbeda untuk mendaftarkan sebagai router baru.",
        "target_tool": "add_device",
        "schema": { ... }
      }
    ]
  }
  ```
- **Visual Design:** High-visibility recovery banner with Amber/Red header, existing entity context card, interactive radio/button selection of recovery routes, and inline expansion of prefilled DIO forms without page reload.
