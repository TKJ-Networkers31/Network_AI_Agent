# AIRA OS — NETWORKING VII
# SERVICE DEPENDENCY INTELLIGENCE SPECIFICATION (WP 7.3)

**Module:** `AIRA_ECOSYSTEM/core/operations/service_intelligence.py`  
**Data Models:** `AIRA_ECOSYSTEM/core/operations/models.py`  
**Phase:** Phase D — Service Dependency Intelligence  
**Status:** IMPLEMENTED & SPECIFIED

---

## 1. Overview & Operational Problem

Network engineers often manage network elements in isolation (e.g. interfaces, routes, BGP sessions) without explicit visibility into which business services or revenue-generating applications are carried across those elements.

The **Service Dependency Intelligence Engine** connects business services to network infrastructure:
$$\text{Business Service} \longrightarrow \text{Endpoints (IP:Port / Subnet)} \longrightarrow \text{Transit Interfaces} \longrightarrow \text{Network Devices}$$

---

## 2. Business Criticality Tiers

| Criticality Tier | Target SLA | Blast Radius Priority | Notification Urgency |
| :--- | :--- | :--- | :--- |
| `TIER_1_MISSION_CRITICAL` | 99.99% | Emergency escalation | Immediate, overrides quiet hours |
| `TIER_2_BUSINESS_OPERATIONAL` | 99.9% | High priority | Escalated within 15 minutes |
| `TIER_3_OFFICE_PRODUCTIVITY` | 99.0% | Standard priority | Monitored during normal working hours |
| `TIER_4_DEVELOPMENT_TEST` | Best Effort | Low priority | Informational logging only |

---

## 3. High-Availability (HA) & Redundancy Scoring

1. **`HA_ACTIVE`:** The business service has redundant endpoints distributed across at least two physically distinct devices.
2. **`SINGLE_POINT_OF_FAILURE` (SPOF):** All service endpoints depend on a single physical router, switch, or transit interface.

Service health score is computed deterministically:
$$\text{Health Score} = \left(\frac{\text{Active Endpoints}}{\text{Total Endpoints}}\right) \times 100$$
- If all endpoints are active: `HEALTHY` (Score 100.0)
- If some endpoints are active: `DEGRADED` (Score $0 < S < 100$)
- If zero endpoints are active: `DOWN` (Score 0.0)

---

## 4. Knowledge Graph Integration

Services and endpoints are projected into `NetworkKnowledgeGraph`:
- Nodes: `node_id = "service:{service_id}"`, `entity_type = "SERVICE_ENDPOINT"`
- Edges:
  - `SERVICE` --(`DEPENDS_ON`)--> `SERVICE_ENDPOINT`
  - `SERVICE_ENDPOINT` --(`HOSTED_ON`)--> `device:{device_id}` or `interface:{device_id}:{interface_name}`
