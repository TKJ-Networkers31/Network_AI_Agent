# WP 4.6.6 — Auto-Diagnosis Integration & Optimization

## 1. Overview

Work Package 4.6.6 integrates the entire Networking IV routing stack (WPs 4.6.0–4.6.5) with AIRA's [`AutomaticNetworkOrchestrator`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py), [`NetworkInvestigator`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/investigator.py), Dynamic Input Orchestrator ([`DIOAnalyzer`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/dio/analyzer.py)), AKANE agent tools, and [NetworkIntelligencePage.jsx](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/app/frontend/src/pages/NetworkIntelligencePage.jsx).

## 2. Implemented Capabilities

- **Natural-Language Routing Intent Classification (`classify_routing_intent`):**
  - Supports all 9 Section 10.2 routing intent classes: `ANALYZE_ALL_ROUTERS`, `LAN_INTERNET_REACHABILITY`, `UPSTREAM_DEPENDENCY_ANALYSIS`, `DEFAULT_ROUTE_VERIFICATION`, `SPECIFIC_PREFIX_PATH_ANALYSIS`, `GATEWAY_REACHABILITY_ANALYSIS`, `CROSS_DEVICE_INCONSISTENCY_SCAN`, `HISTORICAL_SNAPSHOT_COMPARISON`, and `PRE_FAILURE_CHANGE_CORRELATION`, automatically extracting IPv4/CIDR targets and `routing-table` / VRF names.
- **DIO Requirement Validation:**
  - When `require_dio_validation=True` and required inputs (`target_ip` or `target_devices`) are missing, returns `status="needs_input"` with a structured `InteractionPlan` (`dio_interaction_plan`) before touching SSH sessions.
- **Single-Pass Evidence Collection & TTL Reuse:**
  - Collects [`MultiDeviceEvidenceBundle`](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/core/network_intelligence/multi_device_collector.py) once per target/requirement signature, caches within `reuse_fresh_sec`, passes `prebuilt_bundle=mbundle` into `NetworkInvestigator.run_multi_device_investigation`, and ingests routes directly via `MultiDeviceRouteCollector.ingest_bundle_routes(mbundle)` with **zero duplicate SSH execution**.
- **Epistemic Root-Cause Synthesis (`_synthesize_root_causes`):**
  - Classifies every root cause into `"Confirmed finding"`, `"Strong hypothesis"`, `"Weak hypothesis"`, or `"Insufficient evidence"`.
  - Populates all 10 mandatory Section 10.4 fields (`description`, `affected_device`, `affected_prefix`, `evidence_ids`, `route_chain`, `related_topology`, `confidence`, `alternative_explanations`, `missing_evidence`, `recommended_verification_steps`).
  - Automatically caps confidence and downgrades `"Confirmed finding"` to `"Strong hypothesis"` when upstream/related evidence is incomplete (`partial_evidence_warnings`), and returns `"Insufficient evidence"` when all targets fail collection.
- **Read-Only Verification & Non-Mutating Proposals:**
  - Filters every verification command through `filter_safe_readonly_commands` -> `validate_readonly_command`.
  - Produces non-mutating `recommended_plan` (`ConfigurationPlan`) and `rollback_proposal` (`auto_remediation_executed=False`).
  - Supports cooperative cancellation via `POST /api/intelligence/auto-diagnose/{pipeline_id}/cancel`.

## 3. Verification Gate (`WP_4_6_6_ACCEPTED`)

Verified by [test_wp_4_6_6_auto_diagnosis_routing.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_wp_4_6_6_auto_diagnosis_routing.py) (**17/17 passed**) and [test_automatic_orchestration.py](file:///D:/data/agent_ai/AIRA_ECOSYSTEM/tests/test_automatic_orchestration.py) (**5/5 passed**).
