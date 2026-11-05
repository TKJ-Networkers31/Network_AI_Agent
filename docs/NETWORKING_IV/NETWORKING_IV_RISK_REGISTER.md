# AIRA OS — NETWORKING IV RISK REGISTER
## Risk Identification, Impact Analysis, Mitigation Strategies & Security Assertions

**Document ID:** `AIRA-NET-IV-RISK-001`  
**Date:** 2026-10-31  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_RISK_ASSESSMENT  

---

## 1. Overview & Risk Management Methodology

Phase Networking IV introduces multi-layer topology discovery, automated cross-device evidence correlation, and interactive visualization. In enterprise networking, automated discovery tools risk degrading network performance, overwhelming low-spec embedded routers, leaking sensitive network topology maps, or asserting false physical connectivity.

This document identifies all operational, architectural, security, and performance risks, defines concrete mitigation controls, and establishes non-negotiable **Security Boundary Assertions**.

---

## 2. Risk Matrix & Prioritized Register

```
┌────────────────────────────────────────────────────────────────────────┐
│                          RISK HEATMAP SUMMARY                          │
├───────────────────┬──────────────┬──────────────┬──────────────────────┤
│ Severity          │ Likelihood   │ Risk Score   │ Priority             │
├───────────────────┼──────────────┼──────────────┼──────────────────────┤
│ High (3)          │ High (3)     │ 9 (Critical) │ Immediate Mitigation │
│ High (3)          │ Medium (2)   │ 6 (High)     │ Active Prevention    │
│ Medium (2)        │ Medium (2)   │ 4 (Moderate) │ Continuous Monitoring│
│ Low (1)           │ Low (1)      │ 1 (Low)      │ Standard Procedure   │
└───────────────────┴──────────────┴──────────────┴──────────────────────┘
```

| Risk ID | Category | Risk Description | Imp (1-3) | Lkh (1-3) | Score | Mitigation Strategy & Safeguard |
|---|---|---|---|---|---|---|
| **RSK-01** | Security | Unsanitized CLI output or secret leak in evidence | 3 | 2 | **6 (High)** | All CLI outputs pass through `sanitize_cli_excerpt()` and `sanitize_untrusted_text()` before SQLite storage or WebSocket broadcast. Private keys, tokens, and passwords redacted. |
| **RSK-02** | Security | Accidental discovery probing of upstream ISP or public IPs | 3 | 2 | **6 (High)** | Perimeter boundary isolation: `isp_boundary_interfaces` and public IP ranges (`!RFC1918`) strictly prohibited from SSH/SNMP connection attempts. |
| **RSK-03** | Operational | Router CPU spike or memory exhaustion during table dumps | 2 | 2 | **4 (Mod)** | Rate-limited discovery (max 1 run per 60s); command timeouts capped at 15s; single-flight locks per target device. |
| **RSK-04** | Epistemic | False physical link assertion based on shared IP subnet | 3 | 2 | **6 (High)** | Epistemic confidence engine: Shared subnets strictly limited to Tier 3 (`INFERRED`), requiring mutual L2 neighbor packets for Tier 1 (`CONFIRMED`). |
| **RSK-05** | Architectural| Database lock contention between NMS and Topology | 2 | 2 | **4 (Mod)** | SQLite configured with WAL mode (`PRAGMA journal_mode = WAL`), 30s busy timeout, and separate read connections. |
| **RSK-06** | Performance | Frontend UI lag on large graphs ($> 200$ nodes) | 2 | 1 | **2 (Low)** | Hybrid SVG + DOM canvas uses viewport clipping, CSS transform hardware acceleration, and debounced dragging updates. |
| **RSK-07** | Operational | Stale or phantom edges persisting after router disconnect | 2 | 2 | **4 (Mod)** | 60-second in-memory stale observation decayer piggybacked on NMS scheduler; interface oper-status down immediately sets edge to down. |
| **RSK-08** | Compatibility| Version syntax divergence between RouterOS v6 and v7 | 2 | 1 | **2 (Low)** | Version-aware command dispatcher (`COMMAND_MAP_V6` vs `COMMAND_MAP_V7`) in APCE and `TopologyDiscoveryMixin`. |

---

## 3. Mandatory Security Boundary Assertions

To guarantee that AIRA OS remains completely safe to deploy in production enterprise networks, the following boundary assertions are enforced in code:

> [!CAUTION]
> ### ASSERTION 1: ABSOLUTE ZERO CONFIGURATION PUSH
> The Topology Discovery Engine, Cross-Device Evidence Correlator, and NMS Event Sync are strictly read-only subsystems. Under no circumstances shall these modules execute configuration commands (e.g. `/ip address add`, `/interface set`, `/system reboot`, or script execution). All commands must pass through `validate_readonly_command()`.

> [!WARNING]
> ### ASSERTION 2: BOUNDED PERIMETER DISCOVERY
> Automated recursive expansion is strictly forbidden from traversing beyond authorized enterprise subnets. Any packet received from an interface marked as WAN/ISP terminates discovery expansion at that boundary hop.

> [!IMPORTANT]
> ### ASSERTION 3: SECRETS PURGING IN EVIDENCE AND AUDIT LOGS
> All evidence records stored in `topology_edge_evidence` or rendered on the frontend canvas must have passwords, pre-shared keys, SNMP community strings, and bearer tokens replaced with `[REDACTED]` prior to persistence.
