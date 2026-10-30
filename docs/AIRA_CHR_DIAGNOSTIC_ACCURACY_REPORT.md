# AIRA OS — Phase 8.4 Diagnostic Scenario Accuracy Report
## Controlled Diagnostic Scenarios, Deterministic Reasoning, and Hypothesis Ranking

**Project:** AIRA OS — Network Intelligence & Diagnostic Platform  
**Workspace:** `D:\data\agent_ai`  
**Execution Timestamp:** 2026-10-30T12:15:00+07:00  
**Target Architecture:** MikroTik RouterOS v6 / v7  
**Status Determination:** `VERIFIED_OFFLINE (7 SCENARIOS VALIDATED)`  

---

## 1. Executive Summary

AIRA OS implements a deterministic, evidence-driven diagnostic engine (`NetworkInvestigator` and `PlaybookEngine`) that evaluates collected evidence bundles against structured network engineering rules.

In accordance with Rule 1.4:
- Never guess a diagnosis when evidence is incomplete (`INSUFFICIENT_EVIDENCE`).
- Produce explainable diagnostic hypotheses ranked by confidence (`HIGH`, `MEDIUM`, `LOW`).
- Provide falsification criteria, recommended tests, and remediation plans for each hypothesis.
- Clearly disclose operational boundaries and limitations.

Seven core ISP and enterprise networking incident scenarios were evaluated against verified offline test fixtures and structural topologies.

---

## 2. Seven Diagnostic Scenarios Evaluation

| Scenario ID | Incident Type | Injected Root Cause Condition | AIRA OS Diagnostic Inference | Ranked Hypothesis & Recommendation | Verification Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SCN-001** | `LAN_NO_INTERNET` | Gateway interface active, but default route `0.0.0.0/0` is missing from routing table. | `DefaultRouteMissingChecker` detects absence of `0.0.0.0/0`. | **Hypothesis 1 (HIGH):** Rute default hilang.<br/>**Recommendation:** Konfigurasikan rute default statis atau periksa DHCP Client di ether1. | **PASSED (100%)** |
| **SCN-002** | `DEFAULT_ROUTE_FAILS` | Default route present (`0.0.0.0/0 via 192.168.1.1`), but interface is down or gateway unreachable. | `evaluate_longest_prefix_match` identifies inactive default route (`active=False`). | **Hypothesis 1 (HIGH):** Gateway default tidak dapat dijangkau (link down atau gateway drop). | **PASSED (100%)** |
| **SCN-003** | `NAT_MISMATCH` | Outbound traffic routed through WAN, but `/ip firewall nat` has no `action=masquerade` rule. | `NATCoverageChecker` detects missing masquerade for LAN subnet `192.168.1.0/24`. | **Hypothesis 1 (HIGH):** Rule NAT Masquerade tidak ditemukan untuk interface WAN. | **PASSED (100%)** |
| **SCN-004** | `FIREWALL_FORWARD_BLOCKED` | Explicit `action=drop` in forward chain preceding accept rules without FastTrack or stateful match. | `FirewallFilterEvaluator` simulates packet traversal and flags early unconditional drop rule. | **Hypothesis 1 (HIGH):** Firewall filter forward chain memblokir paket LAN ke WAN pada rule index 2. | **PASSED (100%)** |
| **SCN-005** | `OSPF_ADJACENCY_FAILURE` | OSPF neighbor configured, but neighbor state stuck in `ExStart` or `Init` due to MTU mismatch. | `OSPFAdjacencyChecker` detects non-Full state and flags MTU / area mismatch. | **Hypothesis 1 (MEDIUM):** Adjacency OSPF gagal mencapai status Full (status saat ini: ExStart). | **PASSED (100%)** |
| **SCN-006** | `BGP_PREFIXES_MISSING` | BGP session established (`state=established`), but prefix count is 0 due to missing routing filter. | `BGPPeeringChecker` flags `prefix-count=0` on active peer. | **Hypothesis 1 (MEDIUM):** Peering BGP aktif namun tidak menerima rute (periksa routing filter in/out). | **PASSED (100%)** |
| **SCN-007** | `VLAN_TRUNK_FAILURE` | Bridge VLAN filtering enabled (`vlan-filtering=yes`), but trunk port missing tagged VLAN ID membership. | `BridgeVLANChecker` flags trunk port missing from tagged port list for VLAN 100. | **Hypothesis 1 (HIGH):** VLAN ID 100 tidak diizinkan pada trunk port bridge. | **PASSED (100%)** |

---

## 3. Truthful Uncertainty & Insufficient Evidence Enforcement

When evidence collection fails or target connectivity is absent:
1. **Zero Guesswork**: The investigator does not attempt to deduce routing or firewall failures when the device is unreachable.
2. **Explicit Blocked State**:
   - `investigation_status`: `"BLOCKED"`
   - `confidence`: `"INSUFFICIENT_EVIDENCE"`
   - `missing_evidence`: Lists the exact uncollected observations.
   - `limitations_disclosure`: Explains that diagnostic conclusions cannot be made without device telemetry.

---

## 4. Phase 8.4 Diagnostic Accuracy Determination

```
================================================================================
                    DIAGNOSTIC ACCURACY DETERMINATION
================================================================================
 Status: VERIFIED_OFFLINE (7 SCENARIOS VALIDATED)
 
 Summary:
 - Deterministic rule checkers for all 7 core scenarios pass 100% of tests.
 - Longest Prefix Match (LPM) simulator correctly evaluates route priorities.
 - Truthful uncertainty is strictly enforced: missing telemetry results in
   INSUFFICIENT_EVIDENCE rather than synthetic guesses.
================================================================================
```
