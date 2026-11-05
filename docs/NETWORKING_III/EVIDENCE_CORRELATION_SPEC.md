# AIRA OS — Phase Networking III
# Cross-Device Evidence Correlation Specification

## 1. Executive Summary

This document specifies the rules, scoring models, and contradiction detection logic of the **Cross-Device Evidence Correlator** (`core/network_intelligence/correlation.py`), delivered under Work Package N3.6 of Phase Networking III.

The correlator ingests evidence bundles from multiple network devices and infers physical, Layer 2, Layer 3, and upstream dependency relationships without fabricating certainty.

---

## 2. Correlation Rules & Confidence Assignment

The correlator evaluates multiple deterministic correlation rules:

| Rule Name | Confidence Level | Link Type | Conditions Required |
|---|---|---|---|
| `MUTUAL_ARP_AND_SUBNET_MATCH` | `HIGH` (0.90) | `layer2_adjacency` | Device A has IP $IP_A$ on subnet $S$ and an ARP entry for $IP_B$ with MAC $M_B$; Device B has IP $IP_B$ with MAC $M_B$ on the same subnet $S$. |
| `ROUTED_NEXT_HOP` | `HIGH` (0.85) | `routed` | Device A has a route with gateway $GW$; Device B owns IP address matching $GW$. |
| `SUBNET_OVERLAP_ONLY` | `MEDIUM` (0.50) | `inferred` | Device A and Device B have interfaces in the same CIDR subnet, but neither mutual ARP nor neighbor discovery confirms direct Layer 2 adjacency. |
| `NEIGHBOR_DISCOVERY_MATCH` | `HIGH` (0.95) | `physical` | MNDP/LLDP/CDP advertisement from Device A matches MAC/identity on Device B. |

### 2.1 Principle of Truthful Uncertainty

- Subnet overlap alone is **never** promoted to `confirmed` or `HIGH` confidence. It is strictly classified as `inferred` with `MEDIUM` (0.50) confidence.
- Inferred relationships carry explicit disclosures noting that intermediate switches, bridges, or VLAN filters may be present between the endpoints.

---

## 3. Contradiction & IP Collision Detection

The multi-device orchestrator and correlator track IP assignments across all observed devices:
- If two distinct devices report the exact same IP address (e.g. `192.168.1.1/24` on Router-A and `192.168.1.1/24` on Router-B) without being tagged as VRRP or Anycast:
  - An entry is added to `cross_device_contradictions`.
  - An anomaly is surfaced highlighting possible IP collision, misconfiguration, or split-brain behavior.

---

## 4. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/core/network_intelligence/correlation.py`.
- Automated Unit Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_correlation.py` (3 tests passed).
- Integration: Used directly by `NetworkInvestigator.run_multi_device_investigation()` and `POST /api/intelligence/correlation`.
