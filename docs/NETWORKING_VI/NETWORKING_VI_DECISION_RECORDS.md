# AIRA OS — NETWORKING VI ARCHITECTURAL DECISION RECORDS (ADR)
## Key Engineering Decisions & Trade-Offs (WP 6.0)

**Document Status:** WP 6.0 Accepted Specification

---

## ADR-601: Deterministic Reasoning Core as Sole Source of Truth
- **Context:** Network troubleshooting chatbots frequently hallucinate root causes, misread RouterOS flags, or conflate symptoms with causes when given raw CLI text.
- **Decision:** All entity resolution, LPM/recursive path inference, 13-dimension multi-device correlation, 14-step RCA ranking, 8-factor confidence scoring, health evaluation, and failure simulation are implemented as deterministic Python engines. `LLMReasoningOrchestrator` receives only bounded structured findings and falls back deterministically when Ollama/cloud providers are offline.
- **Consequences:** 100% reproducible diagnoses, sub-second deterministic RCA on 5–50 devices, and full offline resilience on the 8 GB ThinkPad X270.

## ADR-602: Separate `network_intelligence.db` for Mutable Intelligence Artifacts; Preserve Immutable `topology.db`
- **Context:** `topology.db` enforces strict immutability triggers (`trg_snapshot_no_update`, `trg_snapshot_no_delete`, `trg_route_snapshots_no_update`, `trg_route_snapshots_no_delete`) audited in Networking IV & V. Meanwhile, `core/network_intelligence/store.py` already manages `database/network_intelligence.db` in WAL mode.
- **Decision:** Keep `topology.db` 100% read-only from the Networking VI reasoning engines (except `NmsEngine`'s own telemetry writer remediated in WP 6.1), and add `intelligence_investigations`, `intelligence_baselines`, `intelligence_anomalies`, and `intelligence_contexts` additively inside `network_intelligence.db`.
- **Consequences:** Zero risk to snapshot immutability or NMS write contention; clean rollback boundary.

## ADR-603: Preserve Strict `validate_readonly_command` Allowlist Without Silent Expansion
- **Context:** `core/network_intelligence/security.py` enforces a 10-layer read-only command allowlist audited across Networking III–V. Certain optional protocol inspection commands (e.g., `/queue simple print`, `/ipv6 route print`, `/ip ipsec active-peers print`) are not in `APPROVED_PRINT_PREFIXES`.
- **Decision:** Do **not** weaken or silently expand `APPROVED_PRINT_PREFIXES` (per Section 1.2 & Section 24). Live RouterOS SSH collection executes strictly within existing approved prefixes; protocol analyzers (`ipv6`, `qos`, `tunnels`) analyze pre-collected/fixture payloads when provided and explicitly report `UNCOLLECTED_READONLY_BOUNDARY` / `PARTIAL` when live RouterOS evidence for unapproved commands is absent, documenting safe validation paths in `PROTOCOL_INTELLIGENCE_MATRIX.md`.
- **Consequences:** 100% preservation of audited read-only security guarantees with zero false capability claims.

## ADR-604: Epistemic Separation of `RIB_INFERRED`, `FIB_CONFIRMED`, and `OBSERVED_FORWARDING`
- **Context:** An installed route in `/ip route print` proves control-plane selection, not hardware FIB programming or end-to-end packet delivery through intermediate firewalls/NAT/L2 trunks.
- **Decision:** `NetworkPathIntelligenceEngine` defaults RIB-derived multi-hop paths to `RIB_INFERRED` (or `PARTIAL_PATH` if incomplete), promotes to `FIB_CONFIRMED` only when explicit FIB/hardware-offload attributes exist on every hop, and promotes to `OBSERVED_FORWARDING` only when corroborated by actual data-plane probes/counters.
- **Consequences:** Eliminates false certainty during silent blackholes, MTU drops, or firewall blocks.

## ADR-605: Extend Existing `/api/intelligence` Router & `NetworkIntelligencePage.jsx` Rather Than Creating Parallel Silos
- **Context:** `AIRA_ECOSYSTEM/api/routers/network_intelligence.py` is already mounted at `/api/intelligence` in `api/main.py`, and `NetworkIntelligencePage.jsx` is already wired into the main React navigation.
- **Decision:** Add all Networking VI REST endpoints additively to `api/routers/network_intelligence.py` and upgrade `NetworkIntelligencePage.jsx` with modular subcomponents under `app/frontend/src/components/network-intelligence/`, keeping existing tabs/endpoints intact.
- **Consequences:** Unified operator workflow, zero broken imports or routes, and full backward compatibility with Networking III/IV/V tests.

## ADR-606: Remediate Networking V Pre-Flight Conditions (N5-C1, N5-C2, N5-C3) in WP 6.1
- **Context:** Phase 0 audit found that `NmsEngine.poll_single_device()` lacked per-device single-flight locking, left `nms_raw_metrics` unpopulated during live runtime, set first-sample interface rates to `0.0` when `prev_s is None` in certain paths, and `AutomaticNetworkOrchestrator` did not reuse fresh NMS DB telemetry before SSH collection.
- **Decision:** Remediate all three conditions cleanly in WP 6.1 (`core/nms_engine.py`, `core/network_intelligence/evidence_service.py`, and `auto_orchestrator.py` in WP 6.13) while keeping 100% compatibility with existing `test_nms.py` and `test_wp_5_*` tests.
- **Consequences:** Eliminates duplicate SSH polls, ensures single-flight safety, and feeds historical `nms_raw_metrics` observations cleanly into Networking VI baselines and evidence bundles.
