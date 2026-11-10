# VERA EXPERIENCE PLANNER SPECIFICATION
## Semantic Intent Classification, Evidence Analysis & Adaptive Composition Planning

**Document Identity:** VERA-PLANNER-SPEC-2026-V1  
**Classification:** Core AI Subsystem Specification  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. SUBSYSTEM PURPOSE

The Experience Planner (`core/vae/planner.py:ExperiencePlanner`) acts as the presentation intelligence layer of VERA. It bridges raw conversational output with structured visual components, determining *what* visual representations should accompany the assistant's narrative response.

---

## 2. INTENT TAXONOMY & MAPPING RULES

The Planner defines eight distinct operational intents (`VaeIntent`), mapped to corresponding visual layouts:

```
+-----------------------------------------------------------------------------------------+
|                                    INTENT TAXONOMY                                      |
+--------------------------+------------------------------+-------------------------------+
| Intent Enum              | Primary Tools Evaluated      | Planned Visual Blocks         |
+--------------------------+------------------------------+-------------------------------+
| RESOURCE_INSPECTION      | mikrotik_get_resources       | markdown, resource-gauge,     |
|                          | get_resources, snmp_info     | metric-grid                   |
|                          |                              |                               |
| INTERFACE_INSPECTION     | mikrotik_get_interfaces      | markdown,                     |
|                          | snmp_traffic, get_interfaces | interface-status              |
|                          |                              |                               |
| NETWORK_DIAGNOSTICS      | network_traceroute,          | markdown,                     |
|                          | network_ping, mikrotik_trace | hop-by-hop-traceroute         |
|                          |                              |                               |
| ROUTING_ANALYSIS         | mikrotik_get_routes,         | markdown,                     |
|                          | route_lookup, route_analytics| route-table-view              |
|                          |                              |                               |
| INCIDENT_INVESTIGATION   | incident_analysis,           | markdown, incident-summary,   |
|                          | root_cause_analysis, nms     | root-cause-panel              |
|                          |                              |                               |
| CONFIGURATION_AUDIT      | config_diff, audit_firewall  | markdown, config-diff         |
|                          |                              |                               |
| REMEDIATION_PROPOSAL     | apply_config, action schemas | markdown, action-card,        |
|                          |                              | remediation-plan              |
|                          |                              |                               |
| GENERAL_EXPLANATION      | (None / Knowledge Query)     | markdown                      |
+--------------------------+------------------------------+-------------------------------+
```

---

## 3. DUAL-SIGNAL RESOLUTION ALGORITHM

To guarantee high fidelity and determinism, the Planner employs a two-tier decision hierarchy:

### Tier 1: Ground-Truth Execution Signals (Highest Priority)
If the current turn executed one or more tools, the Planner inspects the most recent tool name in `steps`. Tool execution directly sets the intent with a high confidence score of **0.95**. Furthermore, parameters passed to the tool (e.g. `device_name`) are extracted to identify the `primary_device`.

### Tier 2: Semantic Query Heuristics (Fallback)
If no specialized tool was executed (e.g. user asking for a status check where data came from session memory), the Planner performs keyword regex matching across the query string.
- Scored against weighted keyword lexicons.
- Confidence set to **0.80**.
- If no domain keywords match, safely defaults to `VaeIntent.GENERAL_EXPLANATION` (markdown only).

---

## 4. EXPERIENCE PLAN DATA MODEL

The Planner produces an immutable `ExperiencePlan` dataclass:

```python
@dataclass
class PlannedBlock:
    block_type: str
    target_data_source: str
    priority: int = 1
    layout_hint: str = "full-width"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExperiencePlan:
    intent: VaeIntent
    confidence: float
    planned_blocks: List[PlannedBlock]
    primary_device: Optional[str] = None
    requires_approval: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 5. DETERMINISTIC VERIFICATION
The Planner has been verified across 8 automated test scenarios in `VERA_ECOSYSTEM/tests/test_vae_generative_experience.py`:
- Resource inspection planning: Verified.
- Interface inspection planning: Verified.
- Network traceroute diagnostics: Verified.
- Routing analysis planning: Verified.
- Narrative-first fallback on general queries: Verified.
- Security confirmation trigger on remediation schemas: Verified.
