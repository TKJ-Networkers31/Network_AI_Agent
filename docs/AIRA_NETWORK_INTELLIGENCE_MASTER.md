# AIRA OS — Network Intelligence Master Engineering Documentation
## Phase 2–4: Network Intelligence, Incident Investigation, Diagnostic Playbooks, and Configuration Planning & Simulation

---

## 1. Architecture & Module Ownership

AIRA OS upgrades from a monitoring assistant into an evidence-driven **Network Engineering Copilot**. The architecture guarantees strict separation between deterministic validation and generative interpretation, enforcing a single coherent pipeline:

$$\text{Evidence} \longrightarrow \text{Investigation} \longrightarrow \text{Playbook} \longrightarrow \text{Desired-State} \longrightarrow \text{Validation} \longrightarrow \text{Simulation} \longrightarrow \text{Review Package}$$

### Subsystem Boundaries

| Subsystem / Layer | Module Path | Responsibility | Storage / Anchor |
| :--- | :--- | :--- | :--- |
| **Canonical Device Identity** | `core.canonical_network` | Single source of truth for device ID, management IP, MAC, hardware model, and RouterOS major version. | `CanonicalNetworkRegistry` |
| **Evidence Collection** | `core.network_intelligence.evidence` | Read-only CLI output collection with session reuse, credential safety, and bounded timeouts. | `ConnectionManager` (`agents.akane`) |
| **Deterministic Checks** | `core.network_intelligence.checks` | IPv4 Longest Prefix Match (LPM), route recursiveness, firewall rule-order shadowing, NAT matching, VLAN tagging, OSPF & BGP state checks. | In-memory deterministic routines |
| **Incident Investigation** | `core.network_intelligence.investigator` | Intake, symptom classification, minimal evidence planning, and ranked hypothesis generation. | `database/network_intelligence.db` |
| **Diagnostic Playbooks** | `core.network_intelligence.playbooks` | Declarative, version-aware diagnostic state machines with operator checkpoints. | `database/network_intelligence.db` |
| **Configuration Planner** | `core.network_intelligence.planner` | Desired-state input normalization, version-aware candidate command generation (v6 vs v7), rollback pairs, and diffs. | `database/network_intelligence.db` |
| **Static Validation** | `core.network_intelligence.validator` | Subnet overlap checks, interface existence, VLAN boundary validation, and dependency acyclicity. | Deterministic rules |
| **Forwarding Simulation** | `core.network_intelligence.simulator` | Before-and-after LPM comparison and explicit disclosure of unmodeled dataplane behaviors. | Deterministic model |
| **REST API Layer** | `api.routers.network_intelligence` | FastAPI endpoints for incidents, playbooks, and configuration planning. | `api.main` |
| **Frontend Workspace** | `app/frontend/src/pages/NetworkIntelligencePage.jsx` | 6-section interactive copilot workspace. | React/Vite PWA |

---

## 2. Evidence Data Model

Every observation is represented as an immutable `EvidenceItem`:
```python
@dataclass
class EvidenceItem:
    evidence_id: str
    device_identity: str
    observation_type: str      # routes, ip_addresses, interfaces, nat_rules, firewall_filter, bridge_vlan, ospf_neighbors, bgp_peers
    source_command: str        # e.g. /ip route print detail
    collection_timestamp: float
    collection_status: str     # SUCCESS, PARTIAL, FAILED, TIMEOUT, CACHED
    normalized_value: Any      # Typed structured representation
    raw_excerpt: str           # Sanitized, masked CLI output excerpt
    freshness: str             # FRESH (<60s), STALE (<300s), EXPIRED (>300s)
    is_derived: bool           # Direct observation vs derived deduction
    limitations: str
```

### Contradiction Detection
The engine actively compares collected evidence across domains to catch real-world anomalies:
- Configured IP address on an interface that is down (`running=no`).
- Default route active but pointing to an interface gateway that is down.
- Bridge VLAN filtering enabled without any VLAN ID entries in the bridge VLAN table.

---

## 3. Incident Model & Lifecycle

Investigations transition through deterministic states:
```
CREATED ──> COLLECTING_EVIDENCE ──> ANALYZING ──> DIAGNOSIS_READY
   │               │                    │                │
   └──(error)──────┴──────(partial)─────┴──────(input)───┴──> AWAITING_OPERATOR_INPUT
```

Fields:
- `incident_id`: Unique identifier (`inc_<hex>`)
- `device_identity`: Resolved canonical device identifier
- `incident_type`: One of the 7 supported types or `CUSTOM`
- `severity`: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`
- `observed_facts`: Authoritative observed facts
- `inferred_hypotheses`: Ranked hypotheses with evidence links
- `missing_evidence`: Data items that were uncollected or unavailable
- `recommended_tests`: Actionable read-only diagnostic steps
- `confidence`: `HIGH`, `MEDIUM`, `LOW`, `INSUFFICIENT_EVIDENCE`

---

## 4. Supported Incident Types

1. **`LAN_NO_INTERNET`**:
   - Subnet membership, default gateway match, default route reachability, NAT masquerade, forward chain accept.
2. **`DEFAULT_ROUTE_FAILS`**:
   - Active flag check, recursive next-hop resolution, distance comparison, ECMP detection, policy routing mark checks.
3. **`NAT_MISMATCH`**:
   - Chain order, in/out interface matching, src/dst subnet coverage, mangle mark correlation.
4. **`FIREWALL_FORWARD_BLOCKED`**:
   - Forward chain rule shadowing, drop-invalid placement, interface list references, established/related rules.
5. **`OSPF_ADJACENCY_FAILURE`**:
   - Area ID, network type, hello/dead timers, MTU match, passive interfaces, auth type, protocol 89 filtering.
6. **`BGP_PREFIXES_MISSING`**:
   - Session state, address family, input/output filter rules, received vs accepted prefixes, next-hop reachability.
7. **`VLAN_TRUNK_FAILURE`**:
   - Bridge VLAN filtering enabled flag, PVID on bridge ports, tagged/untagged consistency on trunks, SVI IP configuration.

---

## 5. Diagnostic Playbook Schema & Execution

All 7 incident types are mapped to declarative playbooks (`PB-LAN-INTERNET`, `PB-DEFAULT-ROUTE`, `PB-NAT-MISMATCH`, `PB-FW-FORWARD`, `PB-OSPF-ADJ`, `PB-BGP-PREFIX`, `PB-VLAN-TRUNK`).

Each playbook guarantees:
- **Strictly Read-Only Actions**: Every command is an inspection command (`print`). Mutating verbs (`add`, `set`, `remove`, `enable`, `disable`) are forbidden.
- **Deterministic Branching**: Next-step decisions depend solely on observed normalized evidence.
- **Operator Checkpoints**: The engine halts and requests operator verification when an ambiguous branch is reached.

---

## 6. RouterOS v6 vs v7 Compatibility Boundaries

The configuration planner dynamically detects the target router's major version via `CanonicalNetworkRegistry` and formats commands accordingly:

| Feature / Domain | RouterOS v6 Syntax | RouterOS v7 Syntax |
| :--- | :--- | :--- |
| **BGP Peering** | `/routing bgp peer add name=... remote-address=... remote-as=...` | `/routing bgp connection add name=... remote.address=... remote.as=...` |
| **OSPF Instance/Template** | `/routing ospf network add network=... area=...` | `/routing ospf interface-template add area=... interfaces=...` |
| **Routing Tables & Rules** | `/ip route rule add dst-address=... table=...` | `/routing rule add dst-address=... table=...` |
| **Route Filtering** | `/routing filter add chain=... action=...` | `/routing filter rule add chain=... rule=...` |
| **VLAN Bridge** | Supported (`vlan-filtering=yes`) | Supported (`vlan-filtering=yes`) |

---

## 7. Hypothesis Ranking & Confidence Semantics

Confidence scores reflect empirical support rather than arbitrary probabilistic values:
- **`HIGH`**: Corroborated by deterministic check findings (e.g., active default route confirmed missing while interface is UP).
- **`MEDIUM`**: Plausible condition identified from partial or inferred evidence.
- **`LOW`**: Secondary or less likely explanation.
- **`INSUFFICIENT_EVIDENCE`**: Essential observations failed or could not be gathered.

---

## 8. Desired-State Schema & Validation

Input requests must specify mandatory parameters. Missing critical fields return status `NEEDS_INPUT` without guessing:
- `ADD_VLAN`: Requires `vlan_id` (1–4094), `bridge` or `interface`.
- `ADD_STATIC_ROUTE`: Requires `dst_address` (valid CIDR) and `gateway`.
- `CONFIGURE_NAT`: Requires `out_interface` or `out_interface_list`.
- `CONFIGURE_BGP`: Requires `remote_as` and `remote_ip`.

Static Validation Rules:
1. **Subnet Overlap**: Blocks prefixes that collide with existing assigned subnets.
2. **VLAN ID Boundaries**: Enforces `1 <= vlan_id <= 4094`.
3. **Interface Existence**: Blocks configurations targeting non-existent interfaces.
4. **Management Path Protection**: Flags changes to default route or management subnet as high-risk.

---

## 9. Dependency Graph & Ordering

Configuration plans order proposed changes using Kahn's topological sort algorithm:
$$\text{Bridge} \longrightarrow \text{Bridge Port} \longrightarrow \text{Bridge VLAN} \longrightarrow \text{VLAN Interface} \longrightarrow \text{IP Address} \longrightarrow \text{NAT / Firewall}$$

Circular dependencies are detected and immediately flagged as invalid plans.

---

## 10. Forwarding Simulation & Unmodeled Behavior

The static simulator compares before vs after routing state using Longest Prefix Match (LPM).

### Transparent Disclosures
Static simulation does **not** emulate the full hardware dataplane. The simulation output explicitly discloses unmodeled runtime factors:
- **FastTrack Connection Bypass**: Established connections bypass CPU firewall/routing evaluation.
- **Hardware Offload (Switch ASIC)**: L2 switching occurs in ASIC silicon.
- **ECMP Hashing**: Runtime 5-tuple hash distribution is unmodeled.
- **Connection Tracking**: Dynamic connection states (SYN_SENT, ESTABLISHED) are not tracked.
- **Dynamic Protocol Convergence**: Actual convergence requires live LSA/Hello exchanges.

---

## 11. Security & Read-Only Guarantees

- **No Production Changes**: The system produces candidate diffs and simulation reports. No configuration command is applied to any router during these phases.
- **Credential Protection**: Passwords and SNMP community strings are masked from all logs, excerpts, and UI views.
- **Bounded Concurrency**: Uses `ConnectionManager` per-target locks and session reuse to prevent SSH connection storms.

---

## 12. Automated Verification & Test Results

### Test Execution Metrics
- **Total Backend Tests Run**: 895 tests + 176 subtests
- **Tests Passed**: 895 passed (100% pass rate)
- **Execution Duration**: 99.32 seconds
- **Intelligence & Diagnostic Test Suites**:
  - `test_phase7_decision_engine.py` (10 passed)
  - `test_phase7_live_verification.py` (7 passed)
  - `test_phase6_diagnostic_validation.py` (8 passed)
  - `test_phase6_lab_preflight.py` (4 passed)
  - `test_phase6_observability_and_security.py` (3 passed)
  - `test_phase5_read_only_enforcement.py` (10 passed)
  - `test_phase5_adversarial_evidence.py` (16 passed)
  - `test_phase5_ros_compatibility.py` (18 passed)
  - `test_phase5_simulator_correctness.py` (16 passed)
  - `test_network_intelligence_investigation.py` (5 passed)
  - `test_network_intelligence_playbooks.py` (3 passed)
  - `test_network_intelligence_planning.py` (4 passed)
  - `test_network_intelligence_api.py` (3 passed)
  - `test_network_intelligence_pipeline.py` (1 passed)
- **Total Frontend Unit Tests Run**: 247 tests
- **Frontend Tests Passed**: 247 passed (100% pass rate)
- **Frontend Production Build**: Succeeded (`NetworkIntelligencePage` chunk at 32.38 kB / gzip 7.14 kB).

---

## 13. Acceptance Criteria Matrix

| Criterion | Target Requirement | Status |
| :--- | :--- | :--- |
| **Evidence Authoritativeness** | All incident findings reference observed evidence without fabrication. | `VERIFIED` |
| **Contradiction Representation** | Stale, missing, and contradictory evidence are surfaced explicitly. | `VERIFIED` |
| **7 Initial Playbooks** | Declarative diagnostic workflows for all 7 scenarios with decision branches. | `VERIFIED` |
| **Shared Analysis Layer** | Deterministic checks shared between investigation and playbooks. | `VERIFIED` |
| **Desired-State Planning** | Validates input, flags missing fields with `NEEDS_INPUT`. | `VERIFIED` |
| **Version-Aware Commands** | Accurate command generation for RouterOS v6 and v7. | `VERIFIED` |
| **Static Validation Engine** | Catches subnet overlap, invalid VLAN IDs, and missing interfaces. | `VERIFIED` |
| **Forwarding Simulation** | Before/after LPM diff with explicit disclosure of unmodeled datapath effects. | `VERIFIED` |
| **Read-Only Guarantee** | Strictly read-only; no automated configuration application. | `VERIFIED` |
| **Architecture Non-Regression** | SSH reuse, NMS polling, topology, and voice companion lifecycle preserved. | `VERIFIED` |
