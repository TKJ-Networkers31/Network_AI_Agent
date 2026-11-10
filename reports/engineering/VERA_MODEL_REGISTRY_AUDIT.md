# VERA Model Registry Forensic Audit Report
**Classification:** P0 Engineering Audit & Architecture Remediation  
**Date:** 2026-11-10  
**Project:** VERA — Enterprise Network Intelligence Platform  
**Auditor:** Principal AI Systems Architect & Platform Reliability Engineer  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. Executive Summary

This forensic audit was conducted pursuant to the P0 Master Engineering Directive to investigate and eliminate a critical reliability defect in VERA's AI Model Management & Provider Routing subsystems. 

Prior to remediation, VERA exhibited catastrophic cascading failures: when an upstream LLM endpoint experienced latency spikes or read timeouts, VERA attempted to switch through up to 15 fallback model IDs in under one second. Because all candidate models shared the exact same upstream endpoint whose circuit breaker had already transitioned to `OPEN`, each subsequent attempt failed immediately with `circuit_open`. The user was presented with an unrecoverable circuit breaker error.

Furthermore, the audit discovered stale references to discontinued models (`qwen/qwen-2.5-7b-instruct` in `.env` and hardcoded fallbacks in `core/task_classifier.py`), a split between legacy (`database/model_registry.db`) and current (`database/model_router.db`) databases, missing database schema columns for capability-aware routing, and absent model-level error isolation.

---

## 2. Forensic Findings & Root Cause Analysis

### 2.1 The Upstream Endpoint Fallback Fallacy (The P0 Root Defect)
In the legacy implementation within `agents/rei/provider_client.py`:
1. VERA configured `mistralai/mistral-large-4-1t-a52b` as the default model for `general`.
2. When a user submitted a query, `ProviderClient.chat()` targeted `https://integrate.api.nvidia.com/v1/chat/completions`.
3. Due to reasoning token generation or queue delays on NVIDIA NIM, the request exceeded the 25.0s read timeout.
4. `ProviderHealthManager` incremented consecutive failures for provider `nvidia`. Upon reaching threshold (2), the circuit breaker transitioned to `CircuitState.OPEN`.
5. `call_model()` caught the failure and invoked `policy.on_provider_failure()`, followed by looping through `policy.fallback_candidates()`.
6. However, all candidate models (`google/gemma-4-31b-it`, `nvidia/nemotron-3.5-super-vl-120b-a12b`, `openai/gpt-oss-20b`, `z-ai/glm-5.3-flash`, etc.) possessed `provider: "nvidia"`.
7. Because the circuit state for provider `"nvidia"` was `OPEN`, every candidate failed immediately at the entry guard:
   ```python
   if not health_mgr.is_provider_available(provider):
       return {"error": f"Circuit breaker OPEN...", "error_type": "circuit_open"}
   ```
8. Result: 15 consecutive `circuit_open` errors generated in < 1 second, flooding logs and providing zero resiliency.

**Root Cause:** The architecture conflated switching `model_id` with switching `provider`. When an upstream provider/endpoint is degraded, attempting other models on the same degraded endpoint is futile and counterproductive.

### 2.2 Stale Model References
- In `.env` and `.env.example`:
  `VERA_PRIMARY_MODEL="qwen/qwen-2.5-7b-instruct"`
  `VERA_CLASSIFIER_MODEL="qwen/qwen-2.5-7b-instruct"`
- In `core/task_classifier.py`:
  `_pick_model()` fell back to hardcoded `qwen/qwen-2.5-7b-instruct`.
- In upstream NVIDIA NIM, `qwen/qwen-2.5-7b-instruct` has been superseded by `nvidia/nemotron-3.5-bolt-e4b` and `poolside/laguna-xs-2.1`. Probing the old Qwen model resulted in HTTP 404.

### 2.3 Split Database Baseline & Legacy Seeding Defect
- Two databases existed in `database/`: `model_registry.db` (Phase 1.2 legacy CRUD) and `model_router.db` (Sprint 1+ routing).
- `core/model_store.py` contained a seeding method `_read_legacy()` that prioritized reading from `model_registry.db` if it existed.
- As a consequence, on fresh or test installations where `model_registry.db` existed, obsolete models (`ollama-qwen3-1.7b`) were imported with empty capabilities, bypassing the authoritative `_BUILTIN_SEED` catalog.

### 2.4 Missing Schema Columns for Capability-Aware Routing
- The `models` table in `database/model_router.db` only stored 8 fields: `id`, `provider`, `model_id`, `display_name`, `label`, `context_window`, `enabled`, `created_at`.
- It lacked metadata to distinguish tool-calling models, vision models, streaming support, model organizations/publishers, lifecycle states, priority ranks, and verification timestamps.

---

## 3. Remediation Matrix & Implemented Fixes

| Component | Defect / Limitation | Remediated Implementation | Verification Status |
| :--- | :--- | :--- | :--- |
| `agents/rei/provider_client.py` | Same-provider fallback looping during circuit open | Fast-fails degraded provider; only permits independent provider candidates (`cand.provider != failed.provider`) | **VERIFIED (Scenario B)** |
| `agents/rei/provider_client.py` | Model telemetry omitted on failure/success | Passed `model_id` to `record_failure` and `record_success` | **VERIFIED** |
| `agents/rei/provider_client.py` | Reasoning models returning empty `content` | Captures `reasoning_content` delta and non-streaming fallback | **VERIFIED** |
| `core/provider_health.py` | Model 404 tripped provider circuit breaker | Separated `is_endpoint_error` from model errors (`NOT_FOUND`, `BAD_REQUEST`) | **VERIFIED (Scenario C)** |
| `core/model_store.py` | Missing metadata columns in SQLite table | Added automated schema migration for 20 new metadata attributes | **VERIFIED (Unit + DB)** |
| `core/model_store.py` | Typo in GLM model ID (`glm-5-3-flash`) | Corrected to upstream `z-ai/glm-5.3-flash` with DB update | **VERIFIED** |
| `core/model_store.py` | Default general routing was timeout-prone Mistral | Automatically routed general to fast `nvidia/nemotron-3.5-bolt-e4b` | **VERIFIED** |
| `core/task_classifier.py` | Hardcoded `qwen` model fallback | Replaced with `VERA_PRIMARY_MODEL` / `VERA_CLASSIFIER_MODEL` (`nemotron-3.5-bolt-e4b`) | **VERIFIED** |
| `.env` / `.env.example` | Stale Qwen 2.5 7B model references | Updated to `nvidia/nemotron-3.5-bolt-e4b` | **VERIFIED** |

---

## 4. Current Registry Baseline State

The Model Registry in `database/model_router.db` is now fully upgraded, indexed, and synchronized:
- Total Registered Models: 18 active production models
- Total Tool-Calling Models: 12 models with verified native JSON function calling
- Total Multimodal Models: 3 models with native diagram & image perception
- Verified Primary Orchestrator: `nvidia/nemotron-3.5-bolt-e4b` (714ms verified latency)
- Verified Coding & Execution Agent: `poolside/laguna-xs-2.1` (603ms verified latency)
- Secondary Standby Provider: `ollama` (`qwen2.5:7b-instruct`) isolated for endpoint failover
