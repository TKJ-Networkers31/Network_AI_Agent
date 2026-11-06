# AIRA OS — Phase H Security & Governance Architecture
**Document Reference:** `docs/architecture/PHASE_H_SECURITY_ARCHITECTURE.md`  
**Version:** 1.0.0 (Phase H)  
**Status:** Canonical Reference Architecture  

---

## 1. Executive Summary

Phase H upgrades AIRA OS into a zero-trust, authorization-first, mathematically-grounded autonomous network intelligence platform. Unlike conventional network tools that rely on client-side state or permissive LLM prompts, AIRA OS treats the backend as the sole security authority. AI models cannot bypass RBAC, modify configuration without deterministic verification, or inspect sensitive credentials.

```
       +--------------------------------------------------------------+
       |                  Enterprise Operator / Client UI              |
       |  (Nexvata Dark Enterprise NOC / Action Cards / KaTeX Math)    |
       +------------------------------+-------------------------------+
                                      | Session Token (aira_tok_...)
                                      v
       +--------------------------------------------------------------+
       |               FastAPI Edge & Security Gateways               |
       |   - OWASP ASVS 5.0 Security Headers Middleware               |
       |   - Sliding-Window IP Rate Limiter (10 req/min auth)         |
       |   - SSRF Safe IP Validator (Blocks cloud meta, loopback)     |
       +------------------------------+-------------------------------+
                                      |
                                      v
       +--------------------------------------------------------------+
       |             Authorization-First Simulation Engine            |
       |  Org -> UserGroup -> Site -> Subtab -> Resource -> Action     |
       +------------------------------+-------------------------------+
                                      |
         +----------------------------+----------------------------+
         |                                                         |
         v                                                         v
+-------------------------------+                         +-------------------------------+
|   Epistemic Reasoning Pipeline|                         |   Network Security Baseline   |
|   - 12 Epistemic Stages       |                         |   - 14 Device Roles           |
|   - Multi-Vendor Syntax Engine|                         |   - Capability-Aware Rules    |
|     (MikroTik v6/v7, Cisco,   |                         |   - Finding Lifecycles        |
|      Linux iptables/nftables) |                         |   - Dynamic Drift Detector    |
+---------------+---------------+                         +---------------+---------------+
                |                                                         |
                v                                                         v
+-----------------------------------------------------------------------------------------+
|                              Deterministic Action Engine                                |
|  - 5-Tier Risk Taxonomy (READ_ONLY, LOW, MEDIUM, HIGH, CRITICAL)                        |
|  - Non-Bypassable Admin Approval for HIGH & CRITICAL                                    |
|  - Pre-State Snapshot -> Dry Run -> Execution -> Post-Verification -> Rollback         |
+-----------------------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------------+
|                              Confidentiality & Output Guard                             |
|  - Pre-retrieval Context Scrubber (Strips secrets, passwords, tokens, SNMP)             |
|  - Post-generation Leak Scrubber (Redacts private keys, SSH keys, credentials)          |
|  - SVG Sanitizer & Mermaid Protection                                                   |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Authorization Hierarchy & RBAC Matrix

AIRA OS enforces a strict 6-tier authorization tree:
$$\text{Organization} \longrightarrow \text{UserGroup} \longrightarrow \text{Site} \longrightarrow \text{Subtab} \longrightarrow \text{Resource} \longrightarrow \text{Action}$$

### 2.1 The 9 Granular Actions
1. `VIEW`: Read-only inspection of topology, inventory, telemetry, and health.
2. `CREATE`: Provisioning new resources, sites, or credentials.
3. `UPDATE`: Modifying attributes, thresholds, or configuration policies.
4. `DELETE`: Decommissioning or removing entities.
5. `EXECUTE`: Running pre-approved diagnostic tests, ping, traceroute, or playbooks.
6. `APPROVE`: Authorizing proposed operational changes (Requires `SUPER_ADMIN` or `ADMIN`).
7. `EXPORT`: Downloading topology graphs, audit logs, or forensic bundles.
8. `MANAGE_PERMISSIONS`: Assigning roles, creating groups, adjusting boundaries.
9. `ACCESS_SENSITIVE_DATA`: Accessing cleartext credentials, secrets, or internal notes.

### 2.2 RBAC Role Matrix & Group Mapping

| Role / Group | Allowed Actions | Action Risk Tier Permitted | Multi-Site Scope | Sensitive Data Access |
|---|---|---|---|---|
| **SUPER_ADMIN** (`PLATFORM_OWNER`, `SUPERADMIN`) | `*` (All 9 Actions) | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `READ_ONLY` | Global (All Tenants & Sites) | Full Access |
| **ADMIN** (`NOC_ADMIN`) | `VIEW`, `CREATE`, `UPDATE`, `EXECUTE`, `APPROVE`, `EXPORT` | `HIGH`, `MEDIUM`, `LOW`, `READ_ONLY` | Organization Scope | Redacted Secrets |
| **NETWORK_ENGINEER** (`NOC_OPERATOR`) | `VIEW`, `CREATE`, `UPDATE`, `EXECUTE` | `MEDIUM`, `LOW`, `READ_ONLY` (Can propose `HIGH`) | Assigned Sites | Redacted Secrets |
| **OPERATOR** (`CUSTOMER_OPERATOR`, `NOC_ANALYST`) | `VIEW`, `EXECUTE` | `LOW`, `READ_ONLY` | Assigned Sites | No Access |
| **AUDITOR** (`CUSTOMER_VIEWER`, `READ_ONLY`) | `VIEW`, `EXPORT` | `READ_ONLY` | Assigned Sites | No Access |

### 2.3 Permission Simulation API
Administrators can preflight evaluate access controls without performing mutations via `POST /api/v1/admin/permissions/simulate`:
```json
{
  "user_id": "usr_78a1bc23",
  "action": "EXECUTE",
  "resource": "device.configuration",
  "site_id": "site_hq_jakarta"
}
```
**Response:**
```json
{
  "allowed": false,
  "action": "EXECUTE",
  "resource": "device.configuration",
  "site_id": "site_hq_jakarta",
  "reason": "Action 'EXECUTE' on 'device.configuration' requires approval or elevated role 'ADMIN'.",
  "evaluated_at": "2026-11-06T12:00:00Z"
}
```

---

## 3. 12-Stage Epistemic Reasoning Pipeline

AIRA OS replaces unconstrained LLM hallucinations with a deterministic 12-stage epistemic pipeline located in `core/ai/reasoning_engine.py`:

```
 Stage 1: Symptom & Intent Deconstruction
   │
 Stage 2: Tenant & Site Boundary Validation
   │
 Stage 3: Topology & Inventory Graph Retrieval
   │
 Stage 4: Multi-Source Telemetry Corroboration
   │
 Stage 5: Device Capability & OS Version Detection
   │
 Stage 6: Hypothesis Generation (Root Cause Analysis)
   │
 Stage 7: Evidence Weighting & Bayesian Elimination
   │
 Stage 8: Mathematical & Heuristic Verification
   │
 Stage 9: Multi-Vendor Syntax Adaptation (MikroTik v6 vs v7, Cisco, Linux)
   │
 Stage 10: Risk Assessment & Approval Policy Evaluation
   │
 Stage 11: Rollback & Safety Postcondition Formulation
   │
 Stage 12: Epistemic Confidence Scoring & Output Guard Sanitization
```

### 3.1 Confidence Scoring Calibration
Confidence is computed empirically from evidence completeness:
$$C = \sum_{i=1}^{k} w_i \cdot e_i$$
- **HIGH ($\ge 0.85$):** Multi-device corroboration, physical link verification, recent telemetry ($< 60\text{s}$). Full automated action proposition allowed.
- **MEDIUM ($0.60 - 0.84$):** Single-device telemetry or partial routing table reachability. Manual review required.
- **LOW ($< 0.60$):** Uncorroborated symptoms, stale evidence ($> 15\text{m}$), or unreachable nodes. Automation disabled; advisory prompt emitted.

### 3.2 Version-Aware Multi-Vendor Syntax Engine
The syntax engine generates vendor-exact, version-validated commands:

- **MikroTik RouterOS v6:**
  ```routeros
  /ip route add dst-address=0.0.0.0/0 gateway=10.0.0.1 distance=1
  ```
- **MikroTik RouterOS v7:**
  ```routeros
  /ip route add dst-address=0.0.0.0/0 gateway=10.0.0.1 routing-table=main distance=1
  ```
- **Cisco IOS / XE:**
  ```cisco
  ip route 0.0.0.0 0.0.0.0 10.0.0.1
  ```
- **Linux Network Stack:**
  ```bash
  ip route add default via 10.0.0.1 proto static
  ```

---

## 4. Action Governance Framework

All network configuration mutations adhere to the **Two-Person Integrity (TPI)** model:
1. **Risk Classification:**
   - `READ_ONLY`: Passive diagnostics, ping, traceroute.
   - `LOW`: Monitoring interval adjustments.
   - `MEDIUM`: DNS forwarders, interface descriptions.
   - `HIGH`: VLAN creation, static routing, NAT masquerade, firewall filters.
   - `CRITICAL`: Reboot, factory reset, credential alteration, firmware upgrades.
2. **Deterministic Lifecycle:**
   $$\text{PROPOSED} \longrightarrow \text{PENDING\_APPROVAL} \xrightarrow{\text{Admin Resolution}} \text{APPROVED} \longrightarrow \text{EXECUTING} \longrightarrow \text{VERIFYING} \longrightarrow \text{SUCCESS}$$
3. **Rollback & Verification:**
   Every approved action is required to store:
   - Complete `diff_text`
   - Explicit `verification_plan` executed automatically post-deploy
   - Executable `rollback_plan` triggered if verification fails.
