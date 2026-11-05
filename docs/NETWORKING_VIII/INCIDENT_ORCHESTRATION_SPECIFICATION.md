# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.8
# MULTI-TENANT INCIDENT ORCHESTRATION & CORRELATION SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.8 — Multi-Tenant Incident Orchestration  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. OBJECTIVE & TENANT ISOLATION BOUNDARIES

The Multi-Tenant Incident Orchestration engine extends the existing `ProactiveIncidentEngine` and `NotificationHub` with strict customer boundary controls.

### 1.1 Strict Isolation Rules
- **Cross-Tenant Correlation Forbidden:** Incidents occurring in Tenant A are never correlated with events in Tenant B, even if both happen to use overlapping private RFC 1918 addresses (`192.168.1.1`) or occur simultaneously.
- **Privacy Separation in Notifications:** Internal NOC alerts may contain technical network identifiers and RCA hypotheses. Customer notifications are sanitized: internal credentials, IP topologies of other tenants, and sensitive NOC internal notes are stripped.
- **Tenant-Scoped State Machine:** State transitions (`ACKNOWLEDGE`, `INVESTIGATE`, `MITIGATE`, `RESOLVE`, `CLOSE`) verify user tenant permissions. Customer users can only view and acknowledge incidents assigned to their tenant organization.

---

## 2. DETERMINISTIC CORRELATION & DEDUPLICATION

### 2.1 Incident Deduplication Fingerprint
To prevent event storms from creating duplicate tickets, an incoming anomaly or alert generates a deterministic fingerprint:

$$\text{DedupKey} = \text{SHA-256}\left(\text{tenant\_id} \,\|\, \text{site\_id} \,\|\, \text{primary\_entity\_id} \,\|\, \text{failure\_class}\right)_{:16}$$

If an active incident with matching `DedupKey` exists in state $\in \{\text{DETECTED}, \text{ACKNOWLEDGED}, \text{INVESTIGATING}\}$, the new evidence record is appended to the existing incident's `evidence_ids` rather than creating a new ticket.

### 2.2 Intra-Tenant Correlation Factors
Within the same tenant, alerts are correlated into a single master incident based on:
1. Shared topological dependency in `NetworkKnowledgeGraph` (e.g. 5 access points offline because the upstream PoE switch failed).
2. Shared customer site and temporal proximity ($\le 5\text{ minutes}$).
3. Common business service impairment.

---

## 3. INCIDENT LIFECYCLE & STATE MACHINE

```
   [ Anomaly / Telemetry Breach ]
                 |
                 v
          +--------------+
          |   DETECTED   |
          +--------------+
                 |
                 v
          +--------------+
          | ACKNOWLEDGED |
          +--------------+
                 |
                 v
          +---------------+
          | INVESTIGATING |
          +---------------+
                 |
                 v
          +--------------+
          |  MITIGATED   |
          +--------------+
                 |
                 v
          +--------------+
          |   RESOLVED   |
          +--------------+
                 |
                 v
          +--------------+
          |    CLOSED    |
          +--------------+
```

Every transition requires:
- `actor_user_id` and `actor_role`
- `reason` or operational resolution notes
- Timestamp (UTC)
- Validated transition check against `VALID_INCIDENT_TRANSITIONS`
