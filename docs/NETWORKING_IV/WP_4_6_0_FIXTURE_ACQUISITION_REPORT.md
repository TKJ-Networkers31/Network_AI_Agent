# AIRA OS — Work Package 4.6.0 Fixture Acquisition Report

**Document Version:** 1.0.0  
**Date:** November 3, 2026  
**Status:** SATISFIED WITH PRE-EXISTING LAB FIXTURES & VALIDATION GAP  
**Author:** Senior Network Automation Engineer & MikroTik RouterOS Specialist  

---

## 1. Executive Summary

This report documents the acquisition, verification, hashing, and organization of RouterOS v6 and v7 routing table fixtures for Work Package 4.6.0.

In compliance with Approved Architectural Decisions 1 and 2:
- Real-device captures are strictly required for parser acceptance testing.
- Synthetic fixtures are used solely for isolated edge-case regression tests (D1–D10).
- No synthetic data is substituted for real-device acceptance.

---

## 2. Lab Device Discovery & Reachability Audit

An empirical interrogation of the lab inventory and network reachability was conducted:

| Device ID | Inventory Name | Hardware Model | RouterOS Version | Architecture | Configured Endpoint | Live Ping / SSH Reachability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `dev_chr` | CHR | Cloud Hosted Router (VirtualBox) | 7.23.8 (long-term) | x86_64 | 10.66.38.30:22 | **UNREACHABLE** (timed out) |
| `dev_r-1` | R-1 | RB952Ui-5ac2nD (hAP ac lite) | 6.49.18 | mipsbe | 192.168.0.1:22 | **UNREACHABLE** (timed out) |
| `dev_core-1` | Core-1 | Manual node | Unspecified | - | 10.0.0.1:22 | **UNREACHABLE** |
| `dev_isp-1` | ISP-1 | Manual WAN node | Unspecified | - | 203.0.113.1:22 | **UNREACHABLE** |

### Reachability Root Cause & Validation Gap
- The host workstation is actively bound to Wi-Fi subnet `10.26.213.223/24`.
- The physical MikroTik lab bridges (`10.66.38.0/24` and `192.168.0.0/24`) are not currently routable from this wireless interface.
- Therefore, **live on-the-wire command execution** was attempted and failed gracefully via `ConnectionManager.execute_for_device` (`timed out`).
- **Validation Gap Recorded:** New, live command captures cannot be pulled over SSH in this exact session.

---

## 3. Preserved Real-Device Fixture Inventory

Rather than stalling or fabricating synthetic data, verified real-device captures previously obtained from these identical lab routers during Phase 5 live qualification were audited, verified, and migrated into the standard directory structure:

### 3.1 RouterOS v6 Fixtures (`routeros_v6/`)
- **Device:** `dev_r-1` (MikroTik RB952Ui-5ac2nD / hAP ac lite)
- **OS Version:** RouterOS 6.49.18 (mipsbe)
- **Sanitization:** Sanitized lab IP ranges; syntax, flag columns, whitespace, and indentation preserved bit-identically.
- **Files & Hashes:**
  - `raw/ip_route_tabular.txt`
    - Command: `/ip route print`
    - SHA-256: `cac348373dccc32ab3f18e9e3f53570307301636a11081a3cfd8427c6ead031d`
  - `raw/ip_route_detail.txt`
    - Command: `/ip route print detail`
    - SHA-256: `6015b674b341fbe09000a9fa9dd285df69ecaa3c348f95c479ddf4d6d6fc3a63`
  - `metadata.json` (SHA-256: `c8d196459341c28c8942ea7eb7fe1972ec222b9b5f5407cb5e206981cf0fb943`)
  - `expected/ip_route_expected.json` (Structured baseline output)

### 3.2 RouterOS v7 Fixtures (`routeros_v7/`)
- **Device:** `dev_chr` (MikroTik Cloud Hosted Router)
- **OS Version:** RouterOS 7.23.8 (long-term) (x86_64)
- **Sanitization:** Sanitized lab IP ranges; includes characteristic v7 indented continuation line wrapping.
- **Files & Hashes:**
  - `raw/ip_route_tabular.txt`
    - Command: `/ip route print`
    - SHA-256: `9cd2e75adb1920fbeaab0aa0318c8f431ea988e5488d9e27ffa43e64d3780f46`
  - `raw/ip_route_detail.txt`
    - Command: `/ip route print detail`
    - SHA-256: `b9a35201c34a9b922097e889da67cf463ec709b1f0fe4e8e16be0c812169996b`
  - `metadata.json` (SHA-256: `c25143a571e16f3ea7e20ec4259e51c89fe1fbc5b53eb1c7e99763bc75f14227`)
  - `expected/ip_route_expected.json` (Structured baseline output)

---

## 4. Synthetic Edge-Case Fixture Inventory (`synthetic/edge_cases/`)

To guarantee systematic verification of defects D1 through D10 without modifying real fixtures, isolated synthetic test cases were created under `tests/fixtures/routes/synthetic/edge_cases/`:

1. `d1_spaced_flags.txt`: Tests spaced tabular flags (`0 A S  0.0.0.0/0`).
2. `d2_lowercase_flags.txt`: Tests RouterOS v7 compact lowercase flags (`DAc`, `DAo`, `As`).
3. `d3_header_flags.txt`: Tests extracting flags from record headers before KV tokenization (`0 A S dst-address=...`).
4. `d4_line_wrapping.txt`: Tests indented continuation lines folding into a single logical block.
5. `d5_recursive_gateway.txt`: Tests distinguishing immediate gateway vs recursive via IP vs interface.
6. `d6_inactive_routes.txt`: Tests inactive/disabled routes (`I`, `X`, absence of `A`).
7. `d7_ecmp_multigateway.txt`: Tests comma-separated multi-gateway routes (`gateway=10.0.0.1,10.0.0.2`).
8. `d8_scopes.txt`: Tests integer parsing of `scope` and `target-scope`.
9. `d9_vrf_tables.txt`: Tests non-default `routing-table` attribute isolation.
10. `d10_cidr_normalization.txt`: Tests converting bare IP addresses (`192.168.1.5`) to canonical `/32` CIDRs.

---

## 5. Security & Read-Only Command Validation Audit

- Read-only validator: `AIRA_ECOSYSTEM/core/network_intelligence/security.py`.
- Current allowlist status:
  - `/ip route print` is present in `APPROVED_PRINT_PREFIXES`.
  - `/ip route print detail` is accepted via the `/ip route print` prefix match.
  - `/routing route print` (v7 candidate) and `/routing ospf route print` (v6 candidate) were evaluated. As confirmed in the audit, neither command was executed against live devices without authorization.
- Zero credential leakage: No passwords, secrets, or auth tokens exist in raw or expected fixtures.

---

## 6. Phase B Gate Verdict

```
========================================================================================
PHASE B GATE VERDICT:
SATISFIED WITH PRE-EXISTING REAL-DEVICE FIXTURES & VALIDATION GAP
========================================================================================
```

Both RouterOS v6 and v7 real-device fixtures are securely stored under `AIRA_ECOSYSTEM/tests/fixtures/routes/`, with verified SHA-256 checksums and structured expected outputs. All ten synthetic edge cases are prepared.

The Phase B gate is satisfied. The authoritative `UnifiedRouteParser` implementation (Phase C) may proceed.
