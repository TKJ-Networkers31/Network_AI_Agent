# AIRA OS — Network Security Intelligence & Baseline Engine User Guide
**Document Reference:** `docs/user-guides/NETWORK_SECURITY_INTELLIGENCE.md`  
**Version:** 1.0.0 (Phase H)  
**Target Audience:** Network Operations Center (NOC) Engineers, Security Engineers, System Administrators

---

## 1. Overview

The Network Security Intelligence Engine in AIRA OS provides continuous, capability-aware posture evaluation and security drift detection for multi-vendor network devices. It assesses configurations against security baselines, scores organizational posture (0–100), tracks findings across their lifecycle, and triggers automated alerts upon configuration drift.

---

## 2. Supported Device Roles (14 Roles)

Every onboarded or discovered device is automatically classified into one of 14 standard roles:

1. `CORE_ROUTER` (e.g., MikroTik CCR2004, Cisco ASR/Catalyst 8000)
2. `EDGE_ROUTER` (e.g., WAN Gateways, RB5009, Cisco ISR)
3. `DISTRIBUTION_SWITCH` (e.g., CRS354, Catalyst 9300)
4. `ACCESS_SWITCH` (e.g., CRS326, CSS326, Aruba CX)
5. `FIREWALL` (e.g., FortiGate, pfSense, OPNsense)
6. `WIRELESS_CONTROLLER` (e.g., CAPsMAN, Cisco WLC)
7. `VPN_GATEWAY` (e.g., WireGuard, IPsec concentrators)
8. `LOAD_BALANCER` (e.g., HAProxy, F5 BIG-IP)
9. `BORDER_GATEWAY` (e.g., BGP Autonomous System border nodes)
10. `AGGREGATION_ROUTER` (e.g., Metro-Ethernet aggregation)
11. `DATA_CENTER_GATEWAY` (e.g., Spine-Leaf leaf switches)
12. `OUT_OF_BAND_SWITCH` (e.g., Dedicated management networks)
13. `SECURE_DNS_RESOLVER` (e.g., Pi-hole, Unbound, CoreDNS)
14. `GENERIC_NETWORK_DEVICE` (Default fallback for unrecognized equipment)

---

## 3. Capability-Aware Baseline Rule Library

Security rules are partitioned into 6 operational categories:

1. **MANAGEMENT_PLANE (`SEC-MGT-xx`)**
   - Insecure Telnet (Port 23) active $\rightarrow$ Critical
   - Insecure HTTP Webfig (Port 80) active $\rightarrow$ High
   - Weak or unauthenticated SSH $\rightarrow$ High
   - Open management access on WAN interfaces $\rightarrow$ Critical

2. **FIREWALL_AND_ACL (`SEC-FWL-xx`)**
   - Missing default DROP on Input Chain $\rightarrow$ High
   - Missing FastTrack bypass or stateful filter $\rightarrow$ Medium
   - Exposed internal management services $\rightarrow$ Critical

3. **ROUTING_SECURITY (`SEC-RTE-xx`)**
   - Unauthenticated OSPF or BGP peerings $\rightarrow$ High
   - Missing routing table isolation (RouterOS v7) $\rightarrow$ Medium

4. **VLAN_AND_SEGMENTATION (`SEC-VLN-xx`)**
   - Use of Default VLAN 1 for management traffic $\rightarrow$ High
   - Unsegmented customer traffic $\rightarrow$ Critical

5. **MONITORING_AND_LOGGING (`SEC-MON-xx`)**
   - Default SNMP Community string (`public` / `private`) $\rightarrow$ High
   - Disabled remote syslog logging $\rightarrow$ Medium

6. **HARDENING_AND_SERVICES (`SEC-HRD-xx`)**
   - Open recursive DNS relay (`allow-remote-requests=yes`) on WAN $\rightarrow$ Critical
   - Unused discovery protocols active on WAN (CDP/MNDP) $\rightarrow$ Medium

---

## 4. Posture Score Calculation & Health Bands

Overall security posture is scored on a normalized 0–100 scale:

$$\text{Posture Score} = \max\left(0, 100 - \sum \text{Deductions}\right)$$

### 4.1 Finding Deductions
- **CRITICAL finding:** $-25\text{ points}$ per open issue.
- **HIGH finding:** $-10\text{ points}$ per open issue.
- **MEDIUM finding:** $-4\text{ points}$ per open issue.
- **LOW finding:** $-1\text{ point}$ per open issue.

### 4.2 Posture Bands

| Posture Band | Score Range | Operational Meaning |
|---|---|---|
| **EXCELLENT** | $90 - 100$ | Hardened against baseline; all management services isolated. |
| **GOOD** | $75 - 89$ | Baseline compliant; minor non-critical hardening opportunities. |
| **MODERATE** | $60 - 74$ | Vulnerable services active; prompt remediation recommended. |
| **POOR** | $40 - 59$ | Severe gaps; insecure protocols (HTTP/Telnet) or weak SNMP active. |
| **CRITICAL** | $0 - 39$ | Imminent breach risk; unauthenticated WAN services or missing firewall. |

---

## 5. Finding Lifecycle Management

1. **DETECTED:** The finding was identified during baseline scan or metric collection.
2. **RESOLVED:** Remediation action successfully deployed and verified.
3. **MUTED:** Temporarily acknowledged by an administrator with justification notes.

---

## 6. Continuous Security Drift Detection

The `NetworkChangeDetector` (`core/network_intelligence/change_detector.py`) evaluates periodic metric bursts:
- If a previously closed management port (e.g., Port 22, 23, or 80) opens on a network device, the system immediately records a new finding and fires a `network.security_drift` event.
- Findings are persisted in `topology.db` within the `operational_security_findings` table and broadcast to active tenant operators via WebSockets.
