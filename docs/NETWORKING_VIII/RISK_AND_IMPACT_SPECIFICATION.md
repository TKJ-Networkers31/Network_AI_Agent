# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.6
# RISK AND OPERATIONAL IMPACT ASSESSMENT SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.6 — Risk and Impact Assessment  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. OBJECTIVE & RISK MODEL

The Risk and Impact Assessment engine enables NOC operators to evaluate the operational blast radius and failure consequences of network degradations or proposed changes.

### 1.1 Non-Destructive Virtual Graph Simulation
- The engine operates directly on `NetworkKnowledgeGraph` using **Virtual Exclusions**.
- When simulating an outage (e.g. failure of `Core-Switch-1` or `sfp-sfpplus1`), the original knowledge graph is **never mutated** and **never cloned into a second memory copy**.
- Graph traversals take an active set of `excluded_node_ids` and `excluded_edge_ids`, determining reachability, alternate paths, and redundancy states with zero memory overhead on the ThinkPad X270 profile.

---

## 2. DETERMINISTIC RISK SCORING FORMULA

The overall Risk Score ($R \in [0.0, 100.0]$) is computed algebraically:

$$R = 100.0 \times \left( P_{\text{failure}} \cdot S_{\text{severity}} \cdot B_{\text{blast}} \cdot C_{\text{crit}} \cdot (1.0 - 0.5 \cdot \text{Redundancy}) \right)$$

Where:
- $P_{\text{failure}} \in [0.1, 1.0]$: Probability or confidence of failure condition.
- $S_{\text{severity}} \in [0.2, 1.0]$: Failure severity class (Degraded = 0.4, Intermittent = 0.7, Total Loss = 1.0).
- $B_{\text{blast}} \in [0.1, 1.0]$: Normalized blast radius fraction $\min\left(1.0, \frac{\text{affected\_nodes}}{10}\right)$.
- $C_{\text{crit}} \in [0.2, 1.0]$: Customer Service Criticality (Tier 1 = 1.0, Tier 2 = 0.75, Tier 3 = 0.4, Tier 4 = 0.2).
- $\text{Redundancy} \in [0.0, 1.0]$: Redundant path availability ($1.0$ if full hot-standby exists, $0.5$ if degraded standby, $0.0$ if single point of failure).

---

## 3. SUPPORTED IMPACT SCENARIOS

1. **Device Failure:** Single device offline (e.g. core router, distribution switch).
2. **Interface Failure:** Uplink or trunk link disconnection.
3. **Gateway Outage:** Remote customer Edge Gateway unreachable.
4. **Site Isolation:** Complete loss of WAN backhaul to customer branch.
5. **Upstream ISP Failure:** Primary transit provider failure.
6. **Capacity Saturation:** Interface bandwidth or CPU reaching 100% capacity horizon.
7. **Redundancy Degradation:** Loss of secondary link (failover capacity exhausted).

### 3.1 Multi-Scenario In-Memory Comparison
Operators can evaluate multiple counterfactual scenarios side-by-side:
- Scenario A: Baseline current state
- Scenario B: Interface ether1 disabled for maintenance
- Scenario C: Gateway failover to cellular backup
The resulting report explicitly distinguishes **Observed Telemetry** from **Simulated Projection**.
