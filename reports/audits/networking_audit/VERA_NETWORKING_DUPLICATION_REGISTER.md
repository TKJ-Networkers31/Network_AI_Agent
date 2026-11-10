# VERA NETWORKING DUPLICATION REGISTER
## Inventory, Transport, Parser, Telemetry & Diagnostics Redundancy Catalog

**Document Version:** 1.0.0  
**Audit Target:** VERA Networking Subsystem  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Code Redundancy, Architectural Duplication & Consolidation Register  
**Status:** FORENSIC ANALYSIS COMPLETE  

---

## 1. DUPLICATION OVERVIEW

The forensic audit discovered several parallel implementations of networking capabilities across historical engineering phases (AIRA OS Phase 3 through Phase 14). While these duplicate implementations currently function without fatal collisions due to facade wrappers, they introduce cognitive overhead, maintenance risks, and unnecessary code complexity.

---

## 2. DETAILED DUPLICATION REGISTER

### 2.1 DUP-NET-01: Dual Device Registries (`inventory.db` vs `topology.db`)
- **Primary Implementation:** [core/inventory_store.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/inventory_store.py) (`inventory.db:devices`)
- **Duplicate Implementation:** [core/canonical_network.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/canonical_network.py) (`topology.db:operational_devices`)
- **Architectural Divergence:** `inventory.db` manages administrative metadata, groups, and credentials. `topology.db:operational_devices` manages operational status, serial numbers, and NMS health.
- **Current Mitigation:** Automatic event hooks keep the two stores synchronized.
- **Consolidation Target:** Merge `inventory.db` tables into `topology.db` or a single authoritative SQLite schema (`vera_platform.db`) to eliminate dual persistence synchronization overhead.

### 2.2 DUP-NET-02: Triple SSH Execution Engines
- **Implementation 1:** [agents/akane/connection_manager.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/agents/akane/connection_manager.py) (`PersistentShell`, `ConnectionManager`)
- **Implementation 2:** [tools/ssh/shell.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tools/ssh/shell.py) (`PersistentShell`)
- **Implementation 3:** [tools/ssh/client.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/tools/ssh/client.py) (`ssh_execute_command`)
- **Architectural Divergence:** `agents.akane.connection_manager` implements interactive PTY shell sessions with paging control. `tools.ssh.shell` is an exact clone residing in the tools directory. `tools.ssh.client` implements stateless single-shot `exec_command()`.
- **Consolidation Target:** Deprecate `tools/ssh/shell.py` in favor of a unified `core/transport/ssh_pool.py`.

### 2.3 DUP-NET-03: Route Parsers
- **Primary Implementation:** [core/routing/unified_route_parser.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/routing/unified_route_parser.py) (`UnifiedRouteParser`)
- **Legacy Delegate:** [core/topology_parsers.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_parsers.py) (`parse_mikrotik_routes`)
- **Protocol Sub-Parsers:** [core/network_intelligence/protocols/static_routing.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/network_intelligence/protocols/static_routing.py)
- **Architectural Divergence:** `parse_mikrotik_routes` was updated in Phase 4.6 to delegate to `UnifiedRouteParser`, but retains backward-compatibility mapping functions (`to_topology_dict()`).
- **Consolidation Target:** Standardize all consumers to accept `NormalizedRoute` directly, eliminating intermediate dict transformations.

### 2.4 DUP-NET-04: Metrics Collection Services
- **Implementation 1:** [core/nms_engine.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/nms_engine.py) (Main NMS poller)
- **Implementation 2:** [core/nms/scheduler.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/nms/scheduler.py) & [core/nms/metrics_store.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/nms/metrics_store.py)
- **Implementation 3:** [core/edge_gateway/collector.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/edge_gateway/collector.py) (Edge gateway telemetry collector)
- **Architectural Divergence:** `nms_engine.py` polls devices over SSH. `collector.py` polls edge gateways via TCP socket probes. Both write to different tables in the same database.
- **Consolidation Target:** Create a unified `CollectorInterface` with pluggable transport drivers (SSH, SNMP, Edge TCP).

---

## 3. SUMMARY OF DUPLICATION IMPACT

| Redundancy | Modules Affected | Maintenance Risk | Performance Impact | Recommended Action |
| :--- | :---: | :---: | :---: | :--- |
| **Dual Inventory** | 4 files | High | Low | Consolidate to single SQLite DB |
| **Triple SSH Clients** | 3 files | Medium | Low | Merge into `core.transport` |
| **Route Parsers** | 3 files | Medium | Low | Standardize on `UnifiedRouteParser`|
| **Telemetry Pollers** | 3 files | Medium | Low | Unified Collector Architecture |
