# AIRA OS — TOPOLOGY INTELLIGENCE INTEGRATION
## Topology-Aware Automated Diagnostics, Upstream Traversal & Causal Reasoning

**Document ID:** `AIRA-NET-IV-INTEL-001`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_INTELLIGENCE_INTEGRATION  

---

## 1. Problem Statement: Isolated vs. Graph-Aware Diagnosis

In traditional diagnostic tools, when a user asks *"Kenapa internet di router R1 lambat atau putus?"*, the tool connects solely to $R_1$, reads its routing table, sees a default gateway, runs a local ping, and concludes either "Gateway is unreachable" or "Router has an issue".

This approach suffers from **Locality Blindness**:
- It cannot distinguish between a failure on the router's local outbound interface, an outage on the intermediate distribution switch, or an upstream ISP gateway breakdown.
- It treats symptoms on downstream devices as root causes.
- It cannot recommend targeted testing across adjacent network nodes.

**Networking IV transforms AIRA's diagnostic pipeline into a Graph-Aware Intelligence Engine.** By combining `TopologyEngine` with `AutomaticNetworkOrchestrator`, AIRA treats the network as an interconnected causal system.

---

## 2. The TopologyGraphContext Provider

During an automated diagnostic run (invoked via `auto_diagnose_network` or `/api/intelligence/auto-diagnose`), the `AutomaticNetworkOrchestrator` constructs a **`TopologyGraphContext`**:

```python
@dataclass
class TopologyGraphContext:
    primary_node_id: str
    adjacent_nodes: List[Dict[str, Any]]        # Direct L2/L3 neighbors
    upstream_nodes: List[Dict[str, Any]]        # Default gateway and transit hops
    downstream_nodes: List[Dict[str, Any]]      # Subordinate routers and access points
    incident_edges: List[Dict[str, Any]]        # Edges connected to primary node
    edge_confidences: Dict[str, float]          # Confidence scores for incident edges
    unverified_relationships: List[str]         # Relationships with confidence < 0.70
```

---

## 3. Upstream Dependency Traversal Algorithm

When an incident involves transit failure (e.g. `LAN_NO_INTERNET` or `DEFAULT_ROUTE_FAILS`), the engine executes the **Upstream Dependency Traversal Algorithm**:

```
[Target Router: CHR]
       │
       │ Reads /ip route print: DAd 0.0.0.0/0 gateway=10.66.38.99%ether1
       ▼
[Resolve Next-Hop in TopologyEngine]
       │
       ├─► Next-Hop 10.66.38.99 matches known node 'node_isp_gateway'
       │     │
       │     ▼
       │   Check Edge (CHR -> node_isp_gateway):
       │     - Local Interface: ether1 (oper_status: UP)
       │     - Edge Verification: STRONGLY_INFERRED (Point-to-point / mutual ARP)
       │     - Confidence: 0.85
       │
       └─► Query Device Authority:
             │
             ├─► If node_isp_gateway is MANAGED (in inventory):
             │     Interrogate upstream router's egress WAN interface
             │
             └─► If node_isp_gateway is UNMANAGED / ISP BOUNDARY:
                   Mark as external boundary; recommend localized ICMP probe
```

### Traversal Steps:
1. **Routing Ingress Identification:** The engine extracts all active default routes (`0.0.0.0/0`) and specific corporate CIDR routes from the target device.
2. **Hop Resolution:** The gateway IP and interface are queried against `TopologyEngine.get_node_by_ip()` and `TopologyEngine.get_edges_for_node()`.
3. **Link Health Verification:** The physical operational status of the connecting edge (`oper_status`) is verified. If the interface is DOWN, the investigation halts upstream traversal and flags local physical link failure.
4. **Authorized Multi-Hop Interrogation:** If the upstream device is registered in `inventory.db` and authorized, the `MultiDeviceCollector` gathers read-only evidence from both devices concurrently.

---

## 4. Root Cause vs. Downstream Symptom Disambiguation

By projecting observations onto the topology graph, the investigator applies **Topological Causal Ordering**:

```
Case A: Upstream WAN Outage
[Core Router R1] ────── ether1 (UP) ──────► [Edge Router R2] ────── ether1 (DOWN) ──────► [ISP]
       │                                           │
  Reported Symptom: "No Internet"            Root Cause Identified:
  Status: DOWNSTREAM SYMPTOM                 "R2 outbound interface ether1 link down"
```

### Disambiguation Rules:
- **Rule 1 (Upstream Dominance):** If Node $B$ is upstream of Node $A$, and Node $B$ has confirmed failure on its transit egress, Node $A$'s connectivity loss is classified as a *downstream consequence* with `MEDIUM` severity, while Node $B$'s fault is ranked as the *primary root cause* with `HIGH/CRITICAL` severity.
- **Rule 2 (Boundary Isolation):** If Node $A$ has confirmed physical reachability to its upstream gateway $G$, but $G$ drops public packets, the issue is isolated to the ISP boundary rather than internal enterprise LAN cabling.

---

## 5. Structured Hypothesis Generation with Evidentiary Disclosure

The final output generated by `auto_diagnose_network` transparently explains the topological basis of its conclusions:

```json
{
  "incident_type": "LAN_NO_INTERNET",
  "primary_device": "CHR",
  "topological_context": {
    "primary_node": "CHR",
    "upstream_gateway": "10.66.38.99",
    "egress_interface": "ether1",
    "edge_verification": "OBSERVED (Confidence: 85%)",
    "transit_nodes_analyzed": ["CHR", "node_isp_gateway"]
  },
  "observed_facts": [
    "Primary device CHR default gateway 10.66.38.99 is reachable with 0% packet loss (latency: 21.9ms).",
    "Egress interface ether1 is Running (1000Mbps full duplex).",
    "Edge between CHR and upstream gateway is verified via mutual ARP and Layer 3 subnet correlation."
  ],
  "ranked_hypotheses": [
    {
      "rank": 1,
      "title": "Konektivitas transit upstream nominal; anomali terbatas pada klien lokal",
      "confidence": "HIGH",
      "supporting_evidence": [
        "Jalur topologi CHR -> Gateway 10.66.38.99 terkonfirmasi aktif.",
        "Ping internet publik ke 8.8.8.8 berhasil dengan rtt rata-rata 54.2ms."
      ],
      "topological_path": "Client -> CHR [ether1] -> Gateway [10.66.38.99] -> Internet"
    }
  ],
  "limitations_disclosure": "Pemeriksaan multi-hop ini bergantung pada status topologi terbaca. Perangkat upstream di luar 10.66.38.99 berada di bawah kewenangan ISP dan tidak dapat diinterogasi langsung."
}
```
