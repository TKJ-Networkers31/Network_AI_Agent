# AIRA OS — NETWORKING VI IMPLEMENTATION ROADMAP
## Sequential Work Package Execution Plan & Acceptance Gates (WP 6.0 – WP 6.18)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Sequential Delivery Phases

| Phase | WP | Deliverables | Primary Modules | Mandatory Gate Criteria |
|---|---|---|---|---|
| **0** | Pre-Flight | Networking V 18-point audit, DB & trigger check, live lab check | `docs/NETWORKING_VI/NETWORKING_VI_EXECUTION_LOG.md` | `NETWORKING_V_READY_WITH_CONDITIONS` verified; 73/73 NMS tests passing |
| **1** | **WP 6.0** | Architecture, Knowledge Graph, Evidence, Reasoning, API, AI Boundary, Resource & Decision specs | `docs/NETWORKING_VI/*.md` | All 9 WP 6.0 specification files complete and aligned with actual codebase |
| **2** | **WP 6.1** | Unified Evidence Service, `NetworkEvidenceBundle`, type-aware freshness, NMS single-flight & `nms_raw_metrics` runtime bridge | `core/network_intelligence/intelligence_models.py`, `evidence_service.py`, `core/nms_engine.py` | Fresh NMS evidence reused with 0 duplicate SSH calls; `None` vs `0.0` preserved; NMS tests pass |
| **3** | **WP 6.2** | Confidence-weighted `EntityResolver`, 21-node / 18-edge `NetworkKnowledgeGraph`, `GraphConsistencyValidator`, bounded `GraphQueryEngine`, immutable snapshot graph projection | `entity_resolver.py`, `knowledge_graph.py`, `graph_queries.py` | Zero false merges on shared IP/hostname; bounded traversal; immutable snapshot diffing |
| **4** | **WP 6.3** | `NetworkPathIntelligenceEngine` (`RIB_INFERRED`, `FIB_CONFIRMED`, `OBSERVED_FORWARDING`, `PARTIAL_PATH`, `UNKNOWN_PATH`), path explanations & comparator + `PATH_INTELLIGENCE_SPECIFICATION.md` | `path_intelligence.py` | All 14 routing scenarios (static, default, recursive, OSPF, eBGP, iBGP, ECMP, blackhole, inactive, unresolved, multi-VRF, asymmetric, withdrawal, v6/v7) verified |
| **5** | **WP 6.4** | 13-dimension `MultiDeviceCorrelationEngine` across Scenarios A–E | `correlation_engine.py` | Time proximity alone never claims causation; contradictions & missing evidence preserved |
| **6** | **WP 6.5** | Explainable 8-factor `ConfidenceScorer` + 14-step `RootCauseAnalysisEngine` across 17 categories + `CORRELATION_AND_RCA_SPECIFICATION.md` | `confidence_model.py`, `rca_engine.py` | Root cause separated from secondary symptoms & contributing factors; `is_calibrated_probability=False` |
| **7** | **WP 6.6** | Reboot-aware `BaselineEngine` (median/MAD/EWMA), `AnomalyDetectionEngine`, 8-dimension `NetworkHealthEngine` + `ANOMALY_AND_BASELINE_DESIGN.md` | `baseline_engine.py`, `anomaly_engine.py`, `health_engine.py` | Missing metrics never treated as `0.0`; reboot/counter-reset invalidates contaminated baseline; spikes without fault evidence not mislabeled as faults |
| **8** | **WP 6.7** | `ChangeImpactAnalyzer` (`OBSERVED_IMPACT` vs `POTENTIAL_IMPACT`) & non-destructive in-memory `AnalyticalFailureSimulator` | `impact_analyzer.py`, `failure_simulator.py` | Simulation never mutates devices or `topology.db`; results tagged `is_simulation=True` |
| **9** | **WP 6.8** | Modular Protocol Intelligence (`layer2`, `ipv4`, `ipv6`, `static_routing`, `ospf`, `bgp`, `nat_firewall`, `qos`, `tunnels`) + `PROTOCOL_INTELLIGENCE_MATRIX.md` | `core/network_intelligence/protocols/*` | BGP 6-state separation; OSPF adjacency/MTU/timer/area rules; honest unsupported disclosures |
| **10** | **WP 6.9** | Cross-domain `HistoricalIntelligenceEngine` (immutable snapshot diffs, incident before/after timeline, recurring fault detection, telemetry gap disclosure) | `historical_intelligence.py` | Zero mutation of `topology_snapshots` or `route_snapshots`; collection gaps explicit |
| **11** | **WP 6.10** | 14-intent EN/ID `IntentClassifier`, validated `InvestigationPlanner`, scoped secret-free `InvestigationContextManager` | `intent_classifier.py`, `investigation_planner.py` | Zero command execution in classifier; follow-up entity pronoun resolution works and expires when stale |
| **12** | **WP 6.11** | Grounded `LLMReasoningOrchestrator` via `call_model` with injection sanitization, JSON validation, Indonesian epistemic qualifiers & deterministic offline fallback | `reasoning_orchestrator.py` | Identical core findings with or without LLM; malformed/offline LLM falls back cleanly |
| **13** | **WP 6.12** | Upgrade `NetworkInvestigator` with 12-step Networking VI pipeline & cooperative cancellation | `investigator.py` | Backward-compatible with Networking III tests + full Networking VI deep investigation |
| **14** | **WP 6.13** | Upgrade `AutomaticNetworkOrchestrator` to reuse fresh NMS/Unified Evidence & Graph/RCA while strictly forbidding auto-remediation | `auto_orchestrator.py` | Zero duplicate SSH calls when NMS telemetry is fresh; read-only boundaries intact |
| **15** | **WP 6.14** | Integrated React experience in `NetworkIntelligencePage.jsx` + modular subcomponents (Overview, NL Investigator, Knowledge Graph Explorer, Path Analysis, RCA Timeline, Historical Intelligence, Evidence Inspector) | `app/frontend/src/api.js`, `pages/NetworkIntelligencePage.jsx`, `components/network-intelligence/*` | Preserves existing design language & tabs; displays freshness, uncertainty, collection failures vs device failures; `npm test` & `npm run build` pass |
| **16** | **WP 6.15** | Additive `/api/intelligence/*` endpoints + SQLite WAL persistence in `network_intelligence.db` + `API_REFERENCE.md` | `store.py`, `api/routers/network_intelligence.py` | Input validation, admin auth guards, timeouts, cancellation, pagination, secret redaction |
| **17** | **WP 6.16** | Unit, integration, 6 synthetic enterprise networks, adversarial misleading-evidence suite, read-only & prompt-injection security audit + full regression | `tests/test_networking_vi_*.py`, `SECURITY_AND_READ_ONLY_AUDIT.md` | 100% pass across Networking III, IV, V, VI, security, concurrency, snapshot immutability & frontend suites |
| **18** | **WP 6.17** | Empirical 5 / 20 / 50 / 100-device scale & RSS memory benchmarks + reliability verification | `tests/benchmark_networking_vi.py`, `PERFORMANCE_REPORT.md` | Actual process RSS measured; latency & DB growth documented honestly |
| **19** | **WP 6.18** | Honest live operational check against registered inventory + final A–J engineering report | `OPERATIONAL_ACCEPTANCE_REPORT.md`, `NETWORKING_VI_FINAL_ACCEPTANCE_REPORT.md` | `git diff --check` clean; synthetic vs live strictly separated; zero device config changes |

---

## 2. EventBus & WebSocket Integration

Networking VI reuses the existing `EventBus` (`core/events.py`) and `WebSocketEventBridge` (`api/ws_bridge.py`) without introducing background polling loops:
- Emits lightweight structured events (`intelligence.investigation.started`, `intelligence.investigation.completed`, `intelligence.anomaly.detected`) on demand when investigations or anomaly evaluations run.
- Existing `nms.*` and `topology.*` WebSocket channels continue operating unchanged.
