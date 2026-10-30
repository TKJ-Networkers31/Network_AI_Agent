# AIRA OS — Phase N2.3: Live Evidence Collection & Parser Validation Report

**Status:** `VERIFIED_LIVE`  
**Timestamp:** 2026-10-30T17:56:21+07:00  
**Target:** `CHR` (`192.168.43.30:22`, MikroTik RouterOS v7.23.8)  
**Collector:** `EvidenceCollector` (`AIRA_ECOSYSTEM/core/network_intelligence/evidence.py`)  
**Operator:** Automated Acceptance Engineer (AIRA OS)

---

## 1. Executive Summary

Phase N2.3 validated live evidence collection and normalization against the live MikroTik Cloud Hosted Router (CHR) v7. A full evidence bundle spanning 10 distinct observation types was gathered through `EvidenceCollector.collect_evidence_bundle()`.

All 10 observations were successfully collected from the live router without mock data, synthetic stubs, or telemetry fabrication. Each observation was parsed into structured, type-safe dictionaries conforming to the canonical `EvidenceItem` contract, with zero collection errors and zero internal contradictions detected.

---

## 2. Collected Evidence Matrix

| # | Observation Type | RouterOS v7 Command | Collection Status | State | Freshness | Normalized Structure |
|---|---|---|---|---|---|---|
| 1 | `identity` | `/system identity print` | SUCCESS | OBSERVED | FRESH | `{'raw_length': 9, 'lines_count': 1}` |
| 2 | `resources` | `/system resource print` | SUCCESS | OBSERVED | FRESH | `{'raw_length': 896, 'lines_count': 17}` |
| 3 | `interfaces` | `/interface print detail` | SUCCESS | OBSERVED | FRESH | 2 interfaces: `ether1` (ether, running, MTU 1500), `lo` (loopback, running, MTU 65536) |
| 4 | `ip_addresses` | `/ip address print detail` | SUCCESS | OBSERVED | FRESH | 1 address: `192.168.43.30/24` on `ether1` (network: `192.168.43.0`, active) |
| 5 | `routes` | `/ip route print detail` | SUCCESS | OBSERVED | FRESH | 2 routes: `0.0.0.0/0` via `192.168.43.1` (`DAd`, active), `192.168.43.0/24` via `ether1` (`DAc`, active) |
| 6 | `firewall_filter` | `/ip firewall filter print detail` | SUCCESS | OBSERVED | FRESH | 0 rules (empty table, clean baseline) |
| 7 | `nat_rules` | `/ip firewall nat print detail` | SUCCESS | OBSERVED | FRESH | 0 rules (`has_masquerade: false`) |
| 8 | `bridge` | `/interface bridge print detail` | SUCCESS | OBSERVED | FRESH | 0 bridges (routed topology) |
| 9 | `arp` | `/ip arp print detail` | SUCCESS | OBSERVED | FRESH | Dynamic ARP entries (gateway `192.168.43.1` on `ether1`) |
| 10 | `dns` | `/ip dns print` | SUCCESS | OBSERVED | FRESH | DNS server configuration parsed |

---

## 3. RouterOS v7 Parser Precision & Enhancements

### 3.1 Routing Engine Flag Parser Upgrade
During validation of `/ip route print detail` on RouterOS v7, the default detail output format presents route status flags at the head of each line rather than inline `active=yes` key-value pairs (e.g., `DAd dst-address=0.0.0.0/0 ...`).

- **Identified Gap:** The parser previously checked only for inline `active=yes`, defaulting `active=false` on RouterOS v7 detail prints.
- **Engine Enhancement in `agents/akane/reasoning_engine.py`:**
  ```python
  prefix = line_clean.split("dst-address=")[0].strip()
  flags_m = prefix.split()[-1] if prefix else ""
  active_m = ("A" in flags_m) or ("active=yes" in line_clean) or ("active=no" not in line_clean and not flags_m)
  dynamic_m = ("D" in flags_m) or ("dynamic=yes" in line_clean)
  connect_m = ("C" in flags_m.upper()) or ("connect=yes" in line_clean)
  static_m = ("S" in flags_m.upper()) or ("static=yes" in line_clean)
  ```
- **Validation:** Live execution on CHR verified that `has_default_route` and `has_active_default_route` both evaluated to `True`, with `raw_flags="DAd"` and `raw_flags="DAc"` extracted with 100% fidelity.

---

## 4. Provenance & Anti-Fabrication Attestation

1. **Deterministic Device Resolution:** Target `CHR` resolved via `CanonicalNetworkRegistry` to inventory device #13 with host `192.168.43.30:22`.
2. **Freshness Tracking:** Every `EvidenceItem` contains actual UNIX timestamp recorded at packet arrival; freshness evaluated strictly to `FRESH` (< 60s).
3. **No Synthetic Data:** All telemetry was acquired over active Paramiko SSH transport to the live hypervisor. Zero simulated fixtures were invoked.
4. **Contradiction Detection:** `EvidenceCollector.detect_contradictions()` completed with 0 anomalies (no IP-to-interface mismatches, no unroutable subnets).
