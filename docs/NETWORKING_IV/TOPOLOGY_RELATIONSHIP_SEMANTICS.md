# AIRA OS — TOPOLOGY RELATIONSHIP SEMANTICS
## Formal Taxonomy, Epistemic Boundaries & Multi-Layer Graph Semantics

**Document ID:** `AIRA-NET-IV-SEMANTICS-001`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_DESIGN_SPECIFICATION  

---

## 1. Architectural Motivation & Problem Definition

In traditional network monitoring tools, topology diagrams frequently suffer from **Semantic Conflation**:
- A green line between Router A and Router B might represent a direct physical 10GbE fiber link, an intermediate unmanaged switch, an untagged VLAN trunk, a static route, or simply an ephemeral ARP entry observed five days ago.
- When an engineer sees a link in the UI, they assume physical adjacency. If that "link" was actually inferred from a shared `/24` subnet, troubleshooting instructions will be catastrophically wrong (e.g., instructing an operator to inspect a non-existent patch cable).

**Networking IV enforces strict Semantic Separation**. Network relationships are classified into four mutually distinct relationship classes, each governed by specific evidentiary requirements and operational boundaries.

---

## 2. Four-Class Relationship Taxonomy

```
┌────────────────────────────────────────────────────────────────────────┐
│                   AIRA TOPOLOGY RELATIONSHIP TAXONOMY                  │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Relationship Class   │ Concrete Subtypes                               │
├──────────────────────┼─────────────────────────────────────────────────┤
│ PHYSICAL_ADJACENCY   │ direct_copper, direct_fiber, patch_cable,       │
│                      │ verified_manual_cable                           │
├──────────────────────┼─────────────────────────────────────────────────┤
│ LAYER2_ADJACENCY     │ vlan_trunk, vlan_access, bridge_port_member,    │
│                      │ lacp_bundle_member, shared_switch_domain        │
├──────────────────────┼─────────────────────────────────────────────────┤
│ LAYER3_REACHABILITY  │ routed_point_to_point, routed_multiaccess,      │
│                      │ default_gateway_transit, bgp_peer, ospf_adj     │
├──────────────────────┼─────────────────────────────────────────────────┤
│ LOGICAL_RELATIONSHIP │ overlay_tunnel (WireGuard, GRE, IPIP, EoIP),    │
│                      │ parent_child_interface, vpn_session             │
└──────────────────────┴─────────────────────────────────────────────────┘
```

---

### 2.1 Class 1: PHYSICAL_ADJACENCY (`physical`)
- **Semantic Meaning:** A dedicated, unswitched, physical transmission medium (copper RJ45, direct fiber patch, DAC cable) connecting two specific physical ports.
- **Evidentiary Standard (Zero Tolerance for Speculation):**
  - Requires **bidirectional Layer 2 neighbor discovery** (MNDP, LLDP, or CDP) where:
    1. Device A receives a neighbor frame on physical port $P_A$ advertising Device B's chassis MAC on physical port $P_B$.
    2. Device B receives a neighbor frame on physical port $P_B$ advertising Device A's chassis MAC on physical port $P_A$.
  - OR an explicit **administrator manual wiring declaration** (`provenance = "user_managed"` with `verification_status = "manual"`).
- **Prohibitions:**
  - An edge shall **NEVER** be classified as `PHYSICAL_ADJACENCY` if either endpoint is a logical interface (e.g., `bridge1`, `vlan10`, `lo`, `wireguard1`).
  - An edge shall **NEVER** be classified as `PHYSICAL_ADJACENCY` based solely on IP subnets, routing tables, ARP entries, or DHCP leases.

---

### 2.2 Class 2: LAYER2_ADJACENCY (`layer2`)
- **Semantic Meaning:** Direct data-link layer frame forwarding within the same broadcast domain, bridging domain, or link-aggregation group.
- **Concrete Subtypes:**
  - `vlan_trunk`: 802.1Q tagged frame forwarding carrying multiple VLAN IDs.
  - `vlan_access`: Untagged port membership in a specific VLAN domain.
  - `bridge_port_member`: Association between a physical port and a software bridge.
  - `lacp_bundle_member`: Physical link participating in an 802.3ad bonding/LAG bundle.
  - `shared_switch_domain`: Inferred presence of an intermediate Layer 2 switch forwarding frames between devices where port-to-port cable adjacency is unobservable.
- **Evidentiary Standard:**
  - RouterOS `/interface bridge port print detail`, `/interface bridge vlan print detail`, and `/interface bridge host print detail`.
  - Single-sided LLDP/MNDP neighbor advertisements reporting a bridge wrapper interface.

---

### 2.3 Class 3: LAYER3_REACHABILITY (`layer3`)
- **Semantic Meaning:** Network-layer packet routing and next-hop forwarding reachability.
- **Concrete Subtypes:**
  - `routed_point_to_point`: Point-to-point IP subnet (strictly `/30` or `/31`) with mutual ARP resolution.
  - `routed_multiaccess`: Common broadcast IP subnet (e.g. `/24`, `/23`) connecting multiple IP endpoints.
  - `default_gateway_transit`: Egress routing relationship defined by default route `0.0.0.0/0`.
  - `bgp_peer`: Active BGP peering relationship.
  - `ospf_adjacency`: Active OSPF neighbor state (`Full`, `2-Way`).
- **Evidentiary Standard:**
  - RouterOS `/ip route print detail`, `/ip address print detail`, and `/ip arp print detail`.
  - Mutual ping reachability and next-hop gateway resolution.
- **Epistemic Note:**
  - Layer 3 reachability asserts that packets can be forwarded between endpoints. It makes **zero claims** about physical cable topology.

---

### 2.4 Class 4: LOGICAL_RELATIONSHIP (`logical`)
- **Semantic Meaning:** Encapsulated overlays, virtual tunnels, or structural software parent-child hierarchies.
- **Concrete Subtypes:**
  - `overlay_tunnel`: Virtual point-to-point or mesh tunnels (WireGuard, GRE, IPIP, EoIP, VXLAN, SSTP, OpenVPN).
  - `parent_child_interface`: Structural encapsulation (e.g. VLAN interface `vlan10` running on physical interface `ether1`).
- **Evidentiary Standard:**
  - RouterOS `/interface print detail` identifying tunnel types, `/interface wireguard peers print detail`, or tunnel endpoint IPs.
- **Operational Independence:**
  - A logical tunnel may traverse multiple physical and Layer 3 hops across the public internet, yet represents a direct single-hop overlay edge.

---

## 3. Explicit Epistemic Prohibitions (Anti-Patterns Guardrails)

The engine code must strictly enforce the following negative rules:

```
[OBSERVED TELEMETRY]                    [PERMITTED INFERENCE]          [FORBIDDEN INFERENCE]
─────────────────────────────────────────────────────────────────────────────────────────────
Shared /24 IP Subnet             ───►   Layer 3 Multi-Access Edge   ─X─► Physical Adjacency
Single ARP Cache Entry           ───►   Candidate L3 Endpoint       ─X─► Live Physical Link
Shared Default Gateway IP        ───►   Common Transit Dependency   ─X─► Router-to-Router Cable
MAC in Bridge Host Table         ───►   Layer 2 Learned MAC         ─X─► Direct Port Connection
WireGuard Endpoint Handshake     ───►   Logical Overlay Edge        ─X─► L2 Broadcast Adjacency
```

> [!CAUTION]
> **RULE 1 (Subnet Non-Physicality):** Subnet overlap proves only Layer 3 network configuration. It shall never generate an edge of class `PHYSICAL_ADJACENCY`.

> [!WARNING]
> **RULE 2 (ARP Cache Ephemerality):** An ARP table entry proves that an IP-to-MAC resolution was placed in cache at some point before the ARP timeout. It does not prove that a cable is directly plugged into the observing router's port.

> [!IMPORTANT]
> **RULE 3 (Separation of Multi-Layer Edges):** If Router A and Router B are connected via a physical cable on `ether1`, share a point-to-point routed subnet on `ether1`, and also maintain a WireGuard tunnel `wg0`, these **MUST be represented as three distinct edges**:
> 1. Physical Edge: `A:ether1` $\leftrightarrow$ `B:ether1` (`relationship_class = "physical"`)
> 2. Routed Edge: `A:10.0.0.1/30` $\rightarrow$ `B:10.0.0.2/30` (`relationship_class = "layer3"`)
> 3. Overlay Edge: `A:wg0` $\leftrightarrow$ `B:wg0` (`relationship_class = "logical"`)

---

## 4. Multi-Layer Graph Filtering & Canvas Projections

In the user interface, operators must be able to filter and project the graph by relationship class without corrupting data integrity:

```typescript
// View Projections supported by Topology Engine & Canvas:
export type TopologyViewProjection = 
  | "all_layers"          // Full comprehensive multi-layer graph
  | "physical_only"       // Only physical cables and direct port connections
  | "layer2_fabric"       // Physical + VLAN trunks + Bridge domains
  | "layer3_routing"      // IP routed subnets + Default gateways + Dynamic routing
  | "logical_overlays";   // VPNs, WireGuard, and Virtual Tunnels
```

1. **Physical View:** Hides all routed, subnet, and logical tunnel edges. Renders only confirmed physical cables and switch port links. If no physical evidence exists, the canvas cleanly shows disconnected nodes rather than inventing false links.
2. **Layer 3 Routing View:** Hides physical port details and visualizes traffic flow, IP prefixes, gateway transit, and routing boundaries.
3. **Overlay View:** Visualizes encrypted tunnel meshes and overlay topologies independently of underlying transit networks.
