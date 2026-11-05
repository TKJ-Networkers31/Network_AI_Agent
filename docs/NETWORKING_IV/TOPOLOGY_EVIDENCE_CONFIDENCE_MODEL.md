# AIRA OS — TOPOLOGY EVIDENCE CONFIDENCE MODEL
## Mathematical Confidence Scoring, Evidentiary Decay, Explainability & Contradiction Resolution

**Document ID:** `AIRA-NET-IV-CONFIDENCE-001`  
**Date:** 2026-10-31 (Revised)  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_CONFIDENCE_SPECIFICATION  

---

## 1. Objective & Mathematical Philosophy

In enterprise network management, visual topology diagrams often fail because they treat all connections as equally true. A static line drawn between two routers might represent a certified Cat6 cable, a multi-hop wireless link, or merely an unverified ARP entry from three months ago.

AIRA OS implements an **Explicit Epistemic Confidence Model**. Every node and edge in the graph carries:
1. A deterministic numerical confidence score $S \in [0.0, 1.0]$.
2. A formal confidence tier (`CONFIRMED`, `HIGH`, `MEDIUM`, `LOW`).
3. An explicit **Qualitative Confidence Rationale** explaining *why* the relationship is classified as such in plain technical terms.

### Core Directive: Confidence Score Is NOT the Sole Classification Basis
> [!IMPORTANT]
> A numerical float (e.g. `0.85`) alone is insufficient for engineering decisions. AIRA requires an auditable **Confidence Explanation Bundle** containing:
> - The primary evidence protocol and observing device.
> - The relationship class (`physical`, `layer2`, `layer3`, `logical`).
> - The qualitative rationale (e.g. *"Bidirectional LLDP frame received on ether1 matching remote chassis MAC 08:00:27:CC:21:02 on ether2"*).
> - Contradiction status (whether negative evidence or port overlaps exist).
> - Expiration status (freshness half-life decay).

---

## 2. Mathematical Scoring Formulation

The composite confidence score $S(e)$ for any topology edge $e$ is calculated using a multi-factor formula:

$$S(e) = \min\left(1.0, \max(0.0, \left( \sum_{k=1}^N W_k \cdot D_k(\Delta t) \right) \cdot C_{dir} \cdot (1 - P_{contra}) \right))$$

Where:
- $W_k$: Base weight of evidence source $k$ ($0.0 \le W_k \le 1.0$).
- $D_k(\Delta t)$: Temporal decay factor as a function of elapsed time since observation $\Delta t$.
- $C_{dir}$: Directionality factor ($1.0$ for bidirectional corroboration, $0.75$ for single-sided observation).
- $P_{contra}$: Contradiction penalty ($0.0 \le P_{contra} \le 1.0$).

### 2.1 Base Protocol Weights & Permitted Relationship Classes

| Evidence Protocol / Source | Base Weight ($W_k$) | Permitted Relationship Class | Qualitative Explanation Rationale |
|---|---|---|---|
| **Operator Manual Confirmation** | $1.00$ | Any (`physical`, `layer2`, `layer3`) | Verified by authorized network administrator |
| **Bidirectional LLDP / MNDP** | $0.95$ | `physical` (if physical ports) | Mutual Layer 2 neighbor discovery on both physical endpoints |
| **Single-Sided LLDP / MNDP** | $0.80$ | `layer2` (or candidate `physical`) | Valid neighbor packet received from known chassis MAC |
| **Dedicated Point-to-Point (/30, /31)** | $0.75$ | Strictly `layer3` (`routed_p2p`) | Mutual ARP on exclusive point-to-point IP subnet |
| **Mutual ARP (Multi-Access Subnet)** | $0.55$ | Strictly `layer3` (`routed_multiaccess`)| Both devices have each other in ARP table on a `/24` |
| **Single-Sided ARP Entry** | $0.35$ | Strictly `layer3` (Candidate endpoint) | Only one router has an ARP entry for target IP |
| **Routing Table Next-Hop** | $0.30$ | Strictly `layer3` (`default_gateway`) | Destination route points to next-hop gateway IP |
| **Bridge Host MAC Forwarding Entry** | $0.25$ | Strictly `layer2` (`bridge_port_member`)| MAC address learned on a multi-port software bridge |
| **DHCP Server Lease Record** | $0.20$ | Strictly `layer3` (End-client lease) | Active IP lease granted to client MAC address |
| **Randomized MAC Address** | $0.05$ | Strictly `layer3` (Ephemeral client) | Locally administered MAC (IEEE bit 1 set) |

---

## 3. Temporal Decay Function ($D_k(\Delta t)$)

Evidence loses validity as time elapses without re-observation. AIRA applies a half-life exponential decay function:

$$D(\Delta t) = 2^{-\frac{\Delta t}{\tau_{half}}}$$

Where:
- $\Delta t$: Elapsed time in seconds since the observation was recorded ($t_{now} - t_{observed}$).
- $\tau_{half}$: Half-life parameter defined per protocol type.

### Half-Life Parameters ($\tau_{half}$):
1. **L2 Neighbor Advertisements (MNDP / LLDP):** $\tau_{half} = 180 \text{ seconds}$ (3 minutes).  
   *Neighbor advertisements are sent every 30–60s; missing 3 consecutive cycles degrades confidence rapidly.*
2. **ARP & DHCP Leases:** $\tau_{half} = 900 \text{ seconds}$ (15 minutes).  
   *ARP caches typically expire in 10–20 minutes in RouterOS.*
3. **Routing Next-Hops:** $\tau_{half} = 1800 \text{ seconds}$ (30 minutes).  
4. **Administrator Manual Confirmations:** $\tau_{half} = \infty$ ($D = 1.0$).  
   *Manual wiring is permanent until explicitly modified or physically disproven.*

---

## 4. Confidence Tier Thresholds & Rationale Mapping

The composite numerical score maps directly to operational tiers, accompanied by mandatory textual rationales:

```
Score S(e)    Tier        Class Permitted           Mandatory Qualitative Rationale
────────────────────────────────────────────────────────────────────────────────────────────────────
0.90 – 1.00   CONFIRMED   physical, layer2, layer3  "Bidirectional protocol verification or verified operator manual wiring."
0.70 – 0.89   HIGH        layer2, layer3            "Single-sided neighbor protocol or exclusive /30 point-to-point mutual ARP."
0.40 – 0.69   MEDIUM      layer3, logical           "Inferred from shared multi-access subnet, routing next-hop, or tunnel configuration."
0.00 – 0.39   LOW         candidate / unverified    "Single ARP cache entry or randomized MAC address; physical connection unverified."
```

---

## 5. Contradiction Resolution & Anomaly Penalization

When multiple sources of evidence conflict, the engine applies penalty $P_{contra}$ and creates a `topology_conflicts` record:

1. **Port Overlap Contradiction ($P_{contra} = 0.50$):**
   - *Symptom:* Device A interface `ether1` has an active LLDP neighbor pointing to Device B, but the ARP table on `ether1` shows a completely different gateway MAC for Device C.
   - *Resolution:* Edge confidence is penalized by 50%, flagged as `conflicting`, and an operator review issue is generated.
2. **Interface Oper-Down Contradiction ($P_{contra} = 1.00$):**
   - *Symptom:* An edge claims a physical link between `ether2` and Device B, but `/interface print detail` reports `ether2` has `oper_status = "down"` (carrier lost).
   - *Resolution:* The edge operational status is immediately updated to `oper_status = "down"`, and confidence is zeroed ($S = 0.0$).
3. **MAC Flapping / Multi-Port Learning ($P_{contra} = 0.40$):**
   - *Symptom:* Device B's MAC address appears simultaneously on `ether3` and `ether4` of the same bridge.
   - *Resolution:* Indicates a potential Layer 2 switching loop or duplicate MAC. The edge is marked `conflicting`.

---

## 6. Epistemic Guardrails: What AIRA Will NEVER Claim

To uphold the integrity of the diagnostic platform, the discovery engine enforces the following negative assertions:

> [!CAUTION]
> **EPISTEMIC GUARDRAIL 1:** A shared IP subnet (e.g. `/24`) between two devices shall **NEVER** be classified as Tier 1 (`CONFIRMED`) or Tier 2 (`HIGH`) physical adjacency without corroborating L2 neighbor packets or mutual switch port FDB records.

> [!WARNING]
> **EPISTEMIC GUARDRAIL 2:** An ARP cache entry shall **NEVER** be used as evidence that a remote host is currently online. ARP caches persist after devices disconnect. Active availability requires a fresh ICMP ping or live L2 beacon.

> [!IMPORTANT]
> **EPISTEMIC GUARDRAIL 3:** Locally administered or randomized MAC addresses (identifiable by bit 1 of the first octet) shall **NEVER** be assumed to represent permanent infrastructure hardware. They are always classified as `client` or `candidate` endpoints.
