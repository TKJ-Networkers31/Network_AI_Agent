# AIRA OS — TOPOLOGY NMS INTEGRATION
## Decoupled Responsibilities, Event-Driven Synchronization & Physical Adjacency Invariance

**Document ID:** `AIRA-NET-IV-NMS-001`  
**Date:** 2026-10-31 (Revised)  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_NMS_INTEGRATION_SPECIFICATION  

---

## 1. Architectural Separation of Responsibilities

A foundational architectural principle of Networking IV is the **Tripartite Separation of Responsibilities**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TRIPARTITE ARCHITECTURE                         │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Subsystem            │ Authoritative Responsibility                    │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **Discovery Engine** │ Discovers network STRUCTURE and adjacency       │
│                      │ classes (Physical, L2, L3, Logical).            │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **NMS Engine**       │ Observes live OPERATIONAL CONDITIONS            │
│                      │ (oper_status, reachability, latency, traffic).  │
├──────────────────────┼─────────────────────────────────────────────────┤
│ **Topology Engine**  │ STORES graph relationships, evidence records,   │
│                      │ historical snapshots, and delta changes.        │
└──────────────────────┴─────────────────────────────────────────────────┘
```

### The Invariance Principle:
> [!IMPORTANT]
> **PHYSICAL ADJACENCY INVARIANCE:** An event originating from the NMS Engine (e.g. an interface down alert or an ICMP timeout) can update the **`oper_status`** of an existing edge or the **`reachability_status`** of a node.
> 
> However, an NMS event can **NEVER**:
> 1. Mutate the `relationship_class` of an edge (e.g. converting a physical edge to logical).
> 2. Delete or prune an edge from the graph.
> 3. Create a new physical adjacency.
> 4. Disprove physical cabling (an unplugged cable or powered-down switch port is an *operational link down*, not an absent relationship).

---

## 2. Event-Driven Architecture & Event Bus Topics

The integration leverages the internal `core.events.event_bus` without external brokers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NMS ENGINE (core/nms_engine.py)                 │
│  - Background scheduler (30s poll interval)                            │
│  - ICMP ping reachability check                                        │
│  - RouterOS / SNMP interface traffic delta rate calculation            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Publishes events
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                             EVENT BUS                                  │
│  Topics:                                                               │
│    - nms.device.status_changed    (device_id, old_status, new_status)  │
│    - nms.interface.status_changed (device_id, iface, oper_status)     │
│    - nms.incident.created         (device_id, incident_type, severity)│
│    - nms.incident.resolved        (device_id, incident_type)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Consumes events
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     TOPOLOGY NMS EVENT LISTENER                        │
│  (core/topology_engine.py :: handle_nms_event)                         │
│  - Updates topology_nodes.reachability_status                          │
│  - Updates topology_edges.oper_status & link_status                    │
│  - Logs delta change to topology_changes                               │
│  - Emits WebSocket payload 'topology.delta' to frontend canvas         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Real-Time State Synchronization Workflows

### 3.1 Interface State Synchronization
1. **Detection:** During an NMS polling cycle, `poll_device()` interrogates interface operational states. An interface (e.g. `ether2` on `node_chr`) changes from `running` to `inactive`.
2. **Event Emission:** NMS engine publishes `nms.interface.status_changed`:
   ```json
   {
     "device_id": "node_chr",
     "interface_name": "ether2",
     "oper_status": "down",
     "timestamp": 1793410500.0
   }
   ```
3. **Graph Reconciliation:**
   - The Topology Engine listener queries all edges in `topology_edges` where `source_node_id = 'node_chr' AND source_interface = 'ether2'` or `target_node_id = 'node_chr' AND target_interface = 'ether2'`.
   - The matching edge's `oper_status` transitions from `up` to `down`.
   - **Crucial:** `relationship_class` remains strictly `"physical"`. The edge is **preserved** in the topology graph.
   - A `topology_changes` delta record is logged (`change_type = 'STATUS_CHANGED'`, `change_reason = 'OPERATIONAL_DOWN'`).
4. **Instant UI Push:** A lightweight delta frame is broadcast over WebSocket (`/ws/{session_id}`). The frontend canvas immediately renders the link as broken/red without requiring a page refresh.

### 3.2 Device Reachability Synchronization (Anti-Flap Guard)
1. **Detection:** If `node_chr` fails 3 consecutive ICMP ping checks, NMS updates its profile to `DOWN` and creates a critical incident.
2. **Graph Reconciliation:**
   - `topology_nodes.reachability_status` transitions to `unreachable`.
   - `topology_nodes.status` transitions to `offline`.
   - All connecting edges are marked `oper_status = "degraded"` or `"unknown"`.
   - **Crucial:** The node and its edges are **NOT** deleted. They are preserved as known topology awaiting recovery.
3. **Recovery:** When ICMP ping recovers, NMS publishes recovery; the node immediately returns to `reachable` and `online`.

---

## 4. Continuous Stale Observation Decayer

To prevent stale edges from lingering indefinitely without imposing polling overhead, the engine runs an in-memory **Decay Ticker**:

- **Execution Frequency:** Every 60 seconds (piggybacked on the NMS scheduler loop).
- **Network Overhead:** Zero. The decayer performs **no network calls, no pings, and no SSH sessions**.
- **Operation:**
  ```python
  now = time.time()
  # Update freshness in SQLite
  conn.execute("""
      UPDATE topology_edges 
      SET observation_freshness = 'expired'
      WHERE observation_freshness != 'expired'
        AND verification_status != 'manual'
        AND (? - last_seen) > 3600.0
  """, (now,))
  ```
- Any edge older than 1 hour without active observation is marked `observation_freshness = "expired"`. It is NOT deleted; it is rendered as an expired candidate requiring re-scan.

---

## 5. Discovery Scheduling & Polling Storm Prevention

To maintain network stability and protect router CPU utilization, full discovery operations are strictly rate-limited:

1. **Lightweight NMS Polling (Frequent):**
   - Interval: Every 30–60 seconds.
   - Operations: ICMP ping + interface counters (SNMP / `/interface print stats`).
   - Impact: $< 1\%$ router CPU.
2. **Full Topology Discovery (Infrequent):**
   - Interval: Operator-triggered or scheduled once every 24 hours (off-peak).
   - Operations: Full Layer 2/3 table dumps (`/ip neighbor`, `/ip arp`, `/ip route`, bridge hosts).
   - Rate-Limit Guard: Discovery cannot be triggered more than once every 60 seconds per seed router.
3. **Session Reuse:**
   - If NMS and Topology both require SSH interrogation on the same device, they reuse the active transport in `ConnectionManager` via single-flight locks, preventing duplicate concurrent connections.
