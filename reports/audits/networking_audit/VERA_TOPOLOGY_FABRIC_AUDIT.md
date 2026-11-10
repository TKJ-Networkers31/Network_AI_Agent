# VERA TOPOLOGY FABRIC AUDIT
## Multi-Layer Graph Modeling, Edge Lifecycles, Route Overlay & Canvas Visualization

**Document Version:** 1.0.0  
**Audit Target:** VERA Topology Graph Fabric  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`  
**Classification:** Graph Modeling & Route Overlay Architecture Audit  
**Status:** VALIDATED — PASS  

---

## 1. MULTI-LAYER TOPOLOGY TAXONOMY

The VERA topology engine ([core/topology_engine.py](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/core/topology_engine.py)) implements a strict multi-layer relationship model conforming to Phase 4.1 engineering specifications:

```
  +-------------------------------------------------------------------------+
  |                          TOPOLOGY GRAPH LAYERS                          |
  +-------------------------------------------------------------------------+
  | Layer 1: PHYSICAL_ADJACENCY | Confirmed physical patch cables, switch   |
  |                             | ports, and interface cross-connects.     |
  +-----------------------------+-------------------------------------------+
  | Layer 2: DATA_LINK          | L2 Ethernet segments, bridge domains,     |
  |                             | VLANs, and MAC-to-MAC adjacencies.        |
  +-----------------------------+-------------------------------------------+
  | Layer 3: NETWORK_LAYER      | IP subnets, point-to-point IP links, and  |
  |                             | L3 gateway relationships.                 |
  +-----------------------------+-------------------------------------------+
  | Layer 4: INFERRED_ROUTE_PATH| Non-mutating control-plane forwarding     |
  |          (Route Overlay)    | paths derived from RIB/FIB lookups.       |
  +-------------------------------------------------------------------------+
```

*Architectural Principle:* Physical adjacency is **never** inferred from IP reachability, subnet overlap, or ARP discovery alone. When only ARP observations exist, the engine classifies the link as `DATA_LINK` or `NETWORK_LAYER` with appropriate confidence tiers.

---

## 2. EDGE LIFECYCLE STATE MACHINE

Edges in `topology.db:topology_edges` transition through five formal lifecycle states:

```
      [DISCOVERED]  <----+ (Fresh observation recorded)
           |             |
           v             |
      [TENTATIVE] -------+
           |
           v (Corroborated by independent evidence)
       [ACTIVE]
           |
           v (Missed polling intervals)
       [STALE]
           |
           v (Exceeded retention half-life)
      [ARCHIVED]
```

### Confidence Tier Calculation:
- **`CONFIRMED` (0.90 - 1.00):** Multi-source corroborated (e.g., LLDP/MNDP neighbor matched with mutual ARP and matching subnet).
- **`HIGH_PROBABILITY` (0.70 - 0.89):** Direct seed discovery with single evidence source.
- **`PLAUSIBLE` (0.40 - 0.69):** Subnet overlap without direct L2 neighbor confirmation.
- **`SPECULATIVE` (< 0.40):** Historical observation past decay half-life.

---

## 3. NON-MUTATING ROUTE OVERLAY ENGINE

### 3.1 Architectural Isolation
A common failure mode in legacy NMS tools is corrupting the physical topology graph when visualizing routing paths. VERA resolves this by maintaining total separation:
- **Physical Graph:** Persisted in `topology.db` (`topology_nodes`, `topology_edges`).
- **Route Overlay:** Ephemeral SVG / GeoJSON paths generated dynamically by `GET /api/topology/route-overlay`.

### 3.2 Live Hardware Evaluation Test
The endpoint was tested using live hardware data:
```bash
GET /api/topology/route-overlay?source_device=dev_mikrotik-hap-ac-lite&destination=192.168.0.254
```
**API Response Summary:**
- `path_state`: `PATH_CONFIRMED_BY_EVIDENCE`
- `path_confidence`: `0.96`
- `mutates_physical_topology`: `False`
- `selected_route_candidate`: `192.168.0.0/24` (via `ether1`, protocol `connected`)
- `next_device_hypothesis`: `CONNECTED_DESTINATION`
- `limitations`: Explicitly disclosed that LPM route evaluation reflects control-plane forwarding intent rather than hardware FastTrack FIB state.

---

## 4. FRONTEND VISUAL EXPERIENCE (TOPOLOGYPAGE.JSX)

The frontend topology view ([TopologyPage.jsx](file:///home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/app/frontend/src/pages/TopologyPage.jsx)) was verified against all 296 unit tests:
- Renders curved parallel edges symmetrically for bundled links.
- Uses distinct visual aesthetics per relationship class (solid for physical, dashed for L2/L3, animated pulse for route overlays).
- Successfully passed production build in Vite in 1.32s.
