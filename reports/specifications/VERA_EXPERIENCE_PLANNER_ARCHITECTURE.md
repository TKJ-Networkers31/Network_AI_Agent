# VERA EXPERIENCE PLANNER ARCHITECTURE
## Dynamic Intent Classification, Dual-Signal UI Synthesis & Adaptive Composition Engine

**Project:** VERA — Enterprise Network Intelligence Platform  
**Subsystem:** VERA Adaptive Experience (VAE)  
**Classification:** P0 Architecture Specification  
**Date:** November 2026  
**Architect:** Principal Generative UI Architect & AI Systems Engineer  
**Reference Code:** `VERA_ECOSYSTEM/core/vae/planner.py`, `VERA_ECOSYSTEM/core/vae/composer.py`

---

## 1. System Overview

The **VERA Experience Planner** is the cognitive bridge between backend AI reasoning and frontend generative UI composition. Prior to its implementation, conversational responses were statically rendered as monolithic Markdown blocks. The Experience Planner transforms this paradigm by treating UI layout as an intentional, dynamic composition tailored to the user's operational goals and verified tool evidence.

```mermaid
flowchart TD
    subgraph Inputs
        U[User Natural Language Prompt]
        T[Executed Agent Tool Steps & Outputs]
        C[Session & Environmental Context]
    end

    subgraph Dual_Signal_Resolution["Dual-Signal Intent Resolution Engine"]
        NLU[Semantic Prompt Classifier]
        TE[Tool Output Inspector & Schema Matcher]
        DS[Confidence Arbitration & Synthesis]
    end

    subgraph Planning["Experience Planning"]
        EP[ExperiencePlanner.plan]
        PL[ExperiencePlan Object]
    end

    subgraph Composition["Adaptive Composition Engine"]
        EC[ExperienceComposer.compose]
        SAN[Narrative Sanitizer & Conclusion-First Engine]
        BLD[Domain Block Builders A-E]
        REC[Universal Workflow Recovery Hook]
    end

    subgraph Output["VAE Protocol v2.0 Output"]
        PAY[VaePayload: blocks[], metadata, layout]
    end

    U --> NLU
    T --> TE
    C --> DS
    NLU --> DS
    TE --> DS
    DS --> EP
    EP --> PL
    PL --> EC
    SAN --> BLD
    EC --> SAN
    BLD --> PAY
    REC --> PAY
```

---

## 2. The 8 Canonical Intent Classifications

The Experience Planner classifies every operational turn into one of eight canonical intents, determining the primary layout, visual components, and interaction patterns:

| Canonical Intent | Primary Operational Focus | Typical Tool Triggers | Target UI Component Families |
| :--- | :--- | :--- | :--- |
| **`SYSTEM_HEALTH`** | Router resource load, CPU, RAM, storage, uptime, system health | `mikrotik_get_resources`, `get_device`, `system_health` | `resource-gauge`, `metric-grid`, `health-summary` |
| **`INTERFACE_MONITORING`** | Port operational status, link speed, packet counters, MTU | `mikrotik_get_interfaces`, `interface_traffic`, `snmp_query` | `interface-status`, `metric-card` |
| **`INCIDENT_INVESTIGATION`**| Root cause analysis, alarms, active anomalies, event logs | `intelligence_get_incident`, `incident_rca`, `get_alerts` | `incident-summary`, `investigation-timeline`, `evidence-card` |
| **`TOPOLOGY_ANALYSIS`** | Multi-layer adjacency, neighbor discovery, cross-device path | `topology_query`, `lldp_discovery`, `get_topology` | `graph`, `topology-detail`, `map` |
| **`CONFIG_CHANGE_APPROVAL`**| RouterOS configuration changes, script execution, ACL edits | `mikrotik_apply_config`, `run_script`, `firewall_rule` | `unified-action-card`, `config-diff` |
| **`ROUTING_ANALYSIS`** | FIB/RIB route tables, BGP sessions, traceroutes, next-hops | `unified_routing`, `network_traceroute`, `bgp_status` | `route-table-view`, `traceroute-path` |
| **`INTERACTIVE_WORKFLOW`** | Device registration, configuration wizards, user input collection | `add_device`, `dio_form`, `user_input_prompt` | `dio-interaction`, `workflow-recovery` |
| **`GENERAL_EXPLANATION`** | Networking concepts, general queries, architectural guidance | *None or read-only knowledge tools* | `markdown` (formatted prose) |

---

## 3. Dual-Signal Intent Resolution

Relying solely on user prompt classification leads to false positives (e.g., user asks *"apa itu OSPF?"* and the system inappropriately renders an empty route table). Conversely, relying solely on tool outputs misses user context. The Experience Planner employs a **Dual-Signal Resolution Architecture**:

### Signal A: Natural Language Prompt Intent
The planner evaluates linguistic cues, regex tokens, and semantic markers in the user's prompt:
- Diagnostic triggers: `ping`, `traceroute`, `mtr`, `latensi`, `rtt`.
- Telemetry triggers: `cpu`, `ram`, `memory`, `storage`, `resource`, `suhu`.
- Interface triggers: `interface`, `port`, `ether`, `sfp`, `traffic`, `link`.
- Routing triggers: `route`, `routing`, `bgp`, `ospf`, `gateway`, `fib`, `rib`.

### Signal B: Executed Tool & Data Structure Signatures
The planner inspects the actual execution history of the turn:
- Tool names: `mikrotik_get_resources` strongly biases towards `SYSTEM_HEALTH`.
- Output keys: Presence of keys like `hops`, `cpu-load`, `routes`, `interfaces` provides deterministic verification.
- Tool errors: If any tool execution returned an error or failed status, the intent triggers a recovery hook (`workflow-recovery`).

### Synthesis & Confidence Arbitration
1. If **Signal B** contains structured evidence and aligns with **Signal A**, plan with high confidence ($0.95$).
2. If tool execution succeeded with structured diagnostic data, **Signal B** overrides prompt ambiguities ($0.90$).
3. If no tools were invoked, fallback to **Signal A** or `GENERAL_EXPLANATION` ($0.80$).

---

## 4. Experience Plan Data Contract

The planning phase produces an immutable `ExperiencePlan` model:

```python
@dataclass
class PlannedBlock:
    block_type: str
    priority: int
    source_step_index: Optional[int] = None
    layout_hint: str = "full"  # "full", "split-left", "split-right", "drawer"
    optional: bool = False

@dataclass
class ExperiencePlan:
    intent: VaeIntent
    confidence: float
    planned_blocks: List[PlannedBlock]
    primary_device: Optional[str] = None
    requires_approval: bool = False
    requires_recovery: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 5. Dynamic Block Composition Pipeline (`ExperienceComposer`)

Once the plan is synthesized, `ExperienceComposer` executes the following phased pipeline:

### Phase 1: Narrative Formulation & Sanitization
- Formulates a concise narrative conclusion (Block 0).
- Applies `_sanitize_narrative`:
  - Strips leaked tool strings (e.g., `[1 tool digunakan]`, ````json {"tool": ...} ````).
  - Removes trailing unresolved questions when interactive forms are present.
  - Ensures professional, conclusion-first tone.

### Phase 2: Domain Visual Block Synthesis
- Maps tool outputs to strongly-typed VAE data schemas:
  - `mikrotik_get_resources` $\rightarrow$ parses CPU percentage, free/total memory in MiB, HDD metrics $\rightarrow$ `resource-gauge` + `metric-grid`.
  - `network_traceroute` $\rightarrow$ parses hop numbers, IPs, hostnames, RTTs, reaches $\rightarrow$ `traceroute-path`.
  - `mikrotik_get_interfaces` $\rightarrow$ parses interface flags (`R`, `X`), MTU, types $\rightarrow$ `interface-status`.
  - `unified_routing` $\rightarrow$ parses destination, gateway, status, distance $\rightarrow$ `route-table-view`.
  - `intelligence_get_incident` $\rightarrow$ parses title, severity, root cause $\rightarrow$ `incident-summary` + `investigation-timeline`.

### Phase 3: Workflow Recovery & Action Gateway Interception
- Inspects step results for errors.
- If an error is detected (e.g., duplicate device registration):
  - Calls `UniversalRecoveryPlanner.plan_recovery(...)`.
  - Attaches a high-priority `workflow-recovery` block immediately following the narrative.
- If approval is required:
  - Synthesizes `unified-action-card` with simulation and execution endpoints.

---

## 6. Layout Hints & Adaptive Presentation

The composer assigns visual layout hints based on the target display profile:
- **Default Stack:** `[Narrative] -> [Primary Visual Block] -> [Secondary Grid] -> [Action / Recovery]`.
- **Side-by-Side (Desktop / Wide):** Split-view with narrative/timeline on the left and topology/diff on the right.
- **Drawer / Modal:** Deep technical details (e.g., full RIB raw route list) attached as drill-down actions rather than cluttering conversational flow.
