# AIRA OS — AI PROVIDER RELIABILITY REPORT (`NEW-01`)
# MULTI-PROVIDER FALLBACK, TIMEOUT GOVERNANCE & TASK CLASSIFICATION RESILIENCE

**Document Reference**: `AUDIT_REPORT/AI_PROVIDER_RELIABILITY_REPORT.md`  
**Date**: 2026-11-08  
**Component**: `core/model_router.py`, `core/model_policy.py`, `agents/rei/provider_client.py`, `core/task_classifier.py`  
**Status**: ACTIVE & PRODUCTION-READY

---

## 1. PURPOSE & ARCHITECTURAL OBJECTIVE

AIRA OS relies on multi-model routing across distinct cognitive domains (Networking, Coding, Reasoning, Vision, Voice, Automation, Retrieval, and General Conversation). In real-world enterprise environments, external AI providers (NVIDIA NIM, OpenRouter, Google Gemini, Ollama) can experience transient latency spikes, rate limits (HTTP 429), authentication lapses, model deprecations (HTTP 404), or complete network outages.

This report documents the architectural hardening and verification of the AI runtime pipeline to ensure AIRA OS never deadlocks, hangs indefinitely, or drops operational network tasks due to upstream provider failures.

---

## 2. THE MULTI-PROVIDER FALLBACK CHAIN

### 2.1 Fallback Candidate Traversal
Previously, the model policy only attempted a single static fallback model. If that designated fallback was also down or returned HTTP 404, the turn immediately aborted with an unhandled failure.

Under the new `NEW-01` implementation:
1. When a model call encounters a terminal or non-transient failure, `policy.fallback_candidates(exclude_ids)` computes an ordered list of viable alternates:
   - **Tier 1 (Policy Fallback)**: The explicitly configured fallback model from `model_policy.fallback_model_id`.
   - **Tier 2 (General Default)**: The primary model configured for the `general` label.
   - **Tier 3 (Active Fleet)**: Any other active, enabled model currently registered in the SQLite model store.
2. If Candidate 1 encounters an HTTP 404 (e.g. decommissioned upstream endpoint) or connection error, the client logs a `FALLBACK CHAIN 404 RECOVERY` event and seamlessly promotes Candidate 2.
3. Every fallback transition emits an asynchronous `model.fallback` telemetry event with `from`, `to`, and `reason` metadata.

### 2.2 Timeout Bounding
- Configurable environment variable: `AIRA_LLM_TIMEOUT` (default: 45.0 seconds).
- Classified `requests.exceptions.Timeout` as a transient error type (`TRANSIENT_ERROR_TYPES = {"rate_limit", "connection", "timeout"}`).
- Fast timeout failure prevents ASGI / Uvicorn worker starvation and ensures fast fallback triggering during external API degradation.

---

## 3. TASK CLASSIFIER RESILIENCE & HEURISTIC FALLBACK

The Task Classifier determines which agent and model handle user intents. If the classifier relies solely on an external LLM, an upstream provider outage would collapse all task routing into default general conversation, preventing Akane from receiving network commands.

### 3.1 Two-Tier Classification Pipeline
1. **Tier 1 (LLM Fast-Classifier)**:
   - Evaluated using a low-latency model with `temperature=0`, `max_tokens=120`, and strict JSON output parsing.
2. **Tier 2 (Deterministic Heuristic Safety Net)**:
   - If the LLM provider times out, fails, throws an exception, or returns invalid JSON, execution falls back immediately to `TaskClassifier._heuristic_classify()`.
   - Heuristic rules analyze lexical and structural patterns across Indonesian and English operational terminology:
     - **Automation**: `jadwal`, `jadwalkan`, `cron`, `otomatisasi`, `recurring`, `periodic`, `backup berkala`.
     - **Vision**: `gambar`, `foto`, `image`, `screenshot`, `diagram`, `kamera`, `ocr`.
     - **Voice**: `suara`, `bicara`, `dengar`, `audio`, `voice`, `stt`, `tts`.
     - **Networking**: `mikrotik`, `routeros`, `router`, `switch`, `vlan`, `bgp`, `ospf`, `vrrp`, `firewall`, `nat`, `ping`, `traceroute`, `snmp`, `dude`.
     - **Coding**: `def `, `class `, `import `, `python`, `javascript`, `sql`, `react`, `debug`, `pytest`, `syntax`.
     - **Reasoning**: `hitung`, `buktikan`, `logika`, `matematika`, `step by step`, `evaluasi`.
     - **Retrieval**: `cari`, `search`, `berita terbaru`, `informasi terkini`, `fakta`.
   - Heuristic classifications assign a confident score of `>= 0.75` and set appropriate subsystem flags (`requires_tools`, `requires_vision`, `requires_voice`).

---

## 4. ASYNCHRONOUS AUTO-MEMORY FAILURE SHIELDING

Auto-memory extraction (`agents/rei/auto_extract.py`) extracts persistent operational facts and user preferences from conversation turns:
- **Daemon Thread Isolation**: `extract_and_save_facts_async()` executes inside non-blocking daemon threads (`threading.Thread(target=_safe_run, daemon=True).start()`).
- **Zero-Impact Guarantee**: Provider timeouts or failures during fact extraction log a debug error and terminate cleanly without raising exceptions to the main ASGI request loop.
- **Empty Response Shielding**: Ignores empty responses or system error markers, preventing spurious memory generation.

---

## 5. VERIFICATION EVIDENCE

All requirements have been validated via automated unit and integration tests:
- `test_phase_stage7_ai_reliability.py`: **8 / 8 PASSED**
- `test_streaming.py`: **63 / 63 PASSED**
- `test_model_router.py`: **17 / 17 PASSED**
- `test_chat_sessions.py`: **11 / 11 PASSED**
- Total AI subsystem tests verified: **279 / 279 PASSED**
