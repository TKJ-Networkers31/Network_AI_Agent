# VERA DISCOVERY ENGINE AUDIT
## Seed Interrogation, Neighbor Parsing, MNDP/CDP/LLDP & ARP Host Identification

**Document Version:** 1.0.0  
**Audit Target:** VERA Network Discovery Engine  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Network Topology Discovery & Device Identification Audit  
**Status:** VALIDATED WITH CRITICAL IMPORT FIX DOCUMENTED  

---

## 1. DISCOVERY ENGINE ARCHITECTURE

The discovery engine ([core/topology_discovery.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_discovery.py) and [core/topology_engine.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_engine.py)) employs a bounded, seed-based interrogation strategy designed for high-integrity network mapping:

```
  +--------------------+
  | Authorized Seed    |
  | Router (Inventory) |
  +---------+----------+
            |
            v
  +-------------------------------------------------------------+
  |              Read-Only CLI Interrogation Suite              |
  |  - /system identity print                                   |
  |  - /system resource print & /system routerboard print       |
  |  - /interface print detail                                  |
  |  - /ip address print detail                                 |
  |  - /ip neighbor print detail (MNDP / CDP / LLDP)            |
  |  - /ip arp print detail                                     |
  |  - /ip route print detail                                   |
  +-----------------------------+-------------------------------+
                                |
        +-----------------------+-----------------------+
        |                                               |
        v                                               v
  +--------------------------+             +--------------------------+
  |    Neighbor Discovery    |             |       ARP Host Scan      |
  | (L2 Adjacency Discovery) |             |  (End-Device Discovery)  |
  +-------------+------------+             +------------+-------------+
                |                                       |
                +-------------------+-------------------+
                                    |
                                    v
                     +-----------------------------+
                     | Deterministic Deduplication |
                     | & Node Classification Model |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Topology Graph Persistence  |
                     |       (topology.db)         |
                     +-----------------------------+
```

---

## 2. DISCOVERY MODES & POLICIES

The discovery engine operates under three deterministic policy modes:
1. `seed_only`: Interrogates only the explicitly specified seed device. Discovers neighbors and connected endpoints via ARP/MNDP without cascading interrogation to those neighbors.
2. `inventory_only`: Discovers connections exclusively between routers already present in `inventory.db`.
3. `deep_scan`: Recursively traverses discovered neighbors up to `discovery_depth` (default: 1 hop) within authorized subnet boundaries.

*Safety Enforcer:* The engine **never** attempts SSH/Telnet connections to discovered neighbor IPs unless those devices are explicitly enrolled in `inventory.db` with authorized credentials.

---

## 3. LIVE HARDWARE DISCOVERY EXECUTION & VERIFICATION

Seed discovery was initiated against **MikroTik-hAP-ac-lite** (`192.168.0.1`):

```python
engine = get_topology_engine()
result = engine.sync_from_seed_router(device_name="MikroTik-hAP-ac-lite", mode="seed_only")
```

### 3.1 Execution Metrics:
- **Job ID:** `disc_6e887b19a4`
- **Elapsed Duration:** 2.81 seconds.
- **Interrogated Seed:** `MikroTik-hAP-ac-lite`
- **Observed Entities:** 2 entities.
- **L2 Neighbors Found:** 0 (no MNDP/CDP neighbors active on lab switch port).
- **ARP Hosts Found:** 1 (`192.168.0.254`, MAC `54:E1:AD:93:31:AF`).
- **Nodes Created:**
  1. `node_mikrotik-hap-ac-lite` (Management IP: 192.168.0.1, status: online).
  2. `node_mac_54_e1_ad_93_31_af` (Observed IP: 192.168.0.254, status: online).
- **Edges Created:** 1 edge connecting `node_mikrotik-hap-ac-lite` (port `ether1`) to `node_mac_54_e1_ad_93_31_af`.
- **Snapshot ID:** `snap_1794217115830_eeec3e52`.

---

## 4. CRITICAL ANOMALY: CIRCULAR IMPORT RESOLUTION (BUG-NET-01)

During initial standalone execution of `sync_from_seed_router`, the process crashed with:
```python
ImportError: cannot import name 'MultiDeviceRouteCollector' from partially initialized module 'core.routing.route_collector'
```
*Root Cause:* [topology_discovery.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_discovery.py) calls `parse_mikrotik_routes()` in [core/topology_parsers.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_parsers.py), which imports `UnifiedRouteParser`. This triggers `core.routing.__init__.py`, which attempts to load `MultiDeviceRouteCollector` before `core.network_intelligence` is completely initialized.

*Pre-Import Mitigation:* Pre-importing `core.network_intelligence` prior to invoking topology discovery completely mitigates the exception. A permanent refactoring is logged in [VERA_NETWORKING_BUG_REGISTER.md](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_NETWORKING_AUDIT/VERA_NETWORKING_BUG_REGISTER.md).
