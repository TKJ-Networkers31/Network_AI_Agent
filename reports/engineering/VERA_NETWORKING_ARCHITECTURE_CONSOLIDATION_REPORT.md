# VERA NETWORKING ARCHITECTURE CONSOLIDATION REPORT
## Subsystem Unification, Redundancy Elimination & SSOT Cohesion

**Document Identity:** VERA-ARCH-CONSOL-2026-V1  
**Classification:** Core System Architecture Consolidation  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. ARCHITECTURAL OBJECTIVE

Prior to consolidation, the repository exhibited duplicate device stores (`inventory.db` vs `topology.db:operational_devices`), fragmented SSH session implementations, multiple ad-hoc route parsing methods across RouterOS versions, and disparate telemetry ingestion paths.

This report documents the architectural unification that establishes single sources of truth (SSOT) across all networking layers without breaking backward compatibility.

---

## 2. DEVICE REGISTRY CONSOLIDATION (SSOT ARCHITECTURE)

### 2.1 The Two Stores Problem
- **`inventory.db` (Credentials & Local Inventory):** Handled hardware credentials (AES-GCM encrypted in SecretVault), device names, management IPs, and SSH ports.
- **`topology.db:operational_devices` (Multi-Tenant Operational DB):** Handled operational device status, site mappings, topology nodes, and risk scores.

### 2.2 Unification Architecture: Bidirectional SSOT Synchronization (REC-11)
Rather than abruptly deleting `inventory.db` (which would invalidate existing encrypted SecretVault keys and local tool scripts), VERA implemented automated SSOT synchronization in `core/inventory_store.py:sync_to_operational_devices`:
1. **Creation / Update Hook:** Any write, edit, or status toggle in `InventoryStore` triggers an atomic transaction on `topology.db:operational_devices` with `ON CONFLICT(device_id) DO UPDATE`.
2. **Deletion Hook:** Deleting a device in `InventoryStore` automatically purges the corresponding record from `operational_devices`.
3. **Canonical ID Derivation:** A deterministic hashing rule (`dev_{normalized_name}`) ensures identical IDs across both databases.
4. **Verification:** Validated by `VERA_ECOSYSTEM/tests/test_phase_stage4_schema_and_ssot.py` (6 of 6 tests passing).

```
   +------------------------------------+
   |          User / API / UI           |
   +-----------------+------------------+
                     |
                     v
   +------------------------------------+
   |      core.inventory_store.py       |
   |   (Encrypted SecretVault Store)    |
   +--------+------------------+--------+
            |                  |
            | (Write/Update)   | (Sync Hook REC-11)
            v                  v
   +-----------------+  +--------------------------------+
   |  inventory.db   |  |     topology.db                |
   |  (credentials,  |  |  (operational_devices,        |
   |   devices)      |  |   topology_nodes, sites)       |
   +-----------------+  +--------------------------------+
```

---

## 3. SSH TRANSPORT CONSOLIDATION

### 3.1 Unification to `PersistentShell`
- **Legacy State:** `agents/akane/connection_manager.py` previously maintained custom Paramiko socket wrappers, while `tools/ssh/shell.py` had an independent implementation.
- **Consolidated State:** `VERA_ECOSYSTEM/tools/ssh/shell.py:PersistentShell` is now the single authoritative SSH session engine.
- **Key Transport Enhancements:**
  1. **RouterOS Terminal Modifier:** Automatic appending of `+ct200w` to username to disable terminal escape sequences (`\x1b[6n`) and ANSI colors that cause terminal hangs.
  2. **Non-RouterOS Fallback:** Graceful fallback to standard username if `+ct200w` authentication fails on generic Linux or standard network appliances.
  3. **Standardized Timeout Profiles:**
     - Connect Timeout: 15.0s (configurable)
     - Banner Timeout: `max(connect_timeout, 25.0s)`
     - Auth Timeout: `max(connect_timeout, 20.0s)`
     - Command Execution Timeout: 3.0s - 30.0s (per command profile)

---

## 4. ROUTE PARSER STANDARDIZATION

### 4.1 Canonical `UnifiedRouteParser`
- **Legacy State:** Route parsing was scattered across regex blocks in `tools/mikrotik/routeros.py`, ad-hoc string splits in `evidence_service.py`, and separate v6 vs v7 scripts.
- **Consolidated State:** `VERA_ECOSYSTEM/core/routing/unified_route_parser.py` is the single authoritative parser.
- **Capabilities:**
  - Handles RouterOS v6 (`/ip route print`) and RouterOS v7 (`/routing route print`).
  - Standardizes route flags into typed enum representations:
    - `A` = Active
    - `S` = Static
    - `D` = Dynamic
    - `C` = Connected
    - `b` = BGP
    - `o` = OSPF
  - Parses CIDR destinations, primary and secondary gateways, metrics, scopes, and route distances.
  - Zero circular import dependency (isolated protocol models in `core/routing/route_collector.py` and `unified_route_parser.py`).
  - Verified across 81 route collection and analytics tests in `test_wp_4_6_*.py`.

---

## 5. TELEMETRY & NMS CONSOLIDATION

### 5.1 Unified Collector Lifecycle
- **NMS Engine (`core/nms_engine.py`):** Authoritative poller for background health metrics, interface traffic counters, CPU load, and device reachability.
- **MCP Server (`mcp_servers/network/server.py`):** Reads directly from ConnectionManager and NMS engine state rather than launching detached ad-hoc polling processes.
- **WebSocket Streaming:** Unifies real-time event distribution over `/ws/chat` and `/api/nms/ws` using deterministic correlation IDs and user-scoped tenant isolation.

---

## 6. CONSOLIDATION RATIFICATION MATRIX

| Subsystem | Consolidated File | Deprecated / Replaced Files | Status |
| :--- | :--- | :--- | :--- |
| **Device Inventory** | `core/inventory_store.py` (REC-11 sync) | Fragmented manual sync scripts | Complete |
| **SSH Transport** | `tools/ssh/shell.py:PersistentShell` | Custom client wrappers in ad-hoc scripts | Complete |
| **Route Parser** | `core/routing/unified_route_parser.py` | Ad-hoc regex splits in diagnostic scripts | Complete |
| **Evidence Service** | `core/network_intelligence/evidence_service.py` | Standalone uncoordinated collectors | Complete |
| **Telemetry** | `core/nms_engine.py` | Duplicate polling loops | Complete |

This consolidation reduces architectural surface area, prevents stale state divergence, and guarantees reliable network automation.
