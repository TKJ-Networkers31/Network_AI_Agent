# VERA Model Security, Credential Isolation & Configuration Report
**Classification:** Application Security & Governance Specification  
**Date:** 2026-11-10  
**Compliance Target:** Zero Credential Leakage & Resilient Configuration  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. Credential Isolation & Masking Architecture

VERA enforces strict isolation for all third-party AI provider credentials:

### 1.1 Non-Persistence in Database
API keys (`NVIDIA_API_KEY`, `OPENROUTER_API`, `GEMINI_API_KEY`) are **never written** to SQLite databases (`database/model_router.db` or `database/model_registry.db`). 
- Database records only contain `provider` strings (e.g. `"nvidia"`, `"ollama"`).
- `ProviderClient._resolve_api_key(provider)` dynamically retrieves the secret at runtime from process environment variables.

### 1.2 Zero Log Leakage & Masking Guarantees
- In all error reporting (`_request_error`), debug strings, and telemetry events (`model.failed`, `model.selected`), API keys and Authorization headers are masked or omitted.
- URLs logged never append query parameter tokens.
- All HTTP headers inspected by logging formatters mask Authorization tokens to `Bearer nvapi-***`.

---

## 2. Environment Configuration Reference

The production environment configuration in `.env` is standardized as follows:

```ini
# =========================================================================
# VERA MODEL INTELLIGENCE CONFIGURATION
# =========================================================================

# Primary Provider API Key (Keep strictly confidential)
NVIDIA_API_KEY=nvapi-your-secret-key-here

# Primary Production Models (Updated & Verified)
VERA_PRIMARY_MODEL="nvidia/nemotron-3.5-bolt-e4b"
VERA_CLASSIFIER_MODEL="nvidia/nemotron-3.5-bolt-e4b"
VERA_FALLBACK_MODEL="poolside/laguna-xs-2.1"

# Standby Local Provider (Optional Failover)
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_FALLBACK_MODEL="qwen2.5:7b-instruct"

# Upstream Timeout Thresholds (in seconds)
VERA_LLM_CONNECT_TIMEOUT=4.0
VERA_LLM_READ_TIMEOUT=25.0
VERA_CLASSIFIER_TIMEOUT=4.0

# Circuit Breaker Parameters
VERA_CIRCUIT_FAILURE_THRESHOLD=2
VERA_CIRCUIT_COOLDOWN_SECONDS=30.0
```

---

## 3. Prompt Injection Safeguards & Safety Boundaries

1. **Content Safety Heuristic Gate:**
   - Prompts containing malicious network exploits, privilege escalation, or payload injection patterns are trapped by heuristic check #0 in `core/task_classifier.py` before hitting LLM inference.
2. **Read-Only Enforced Sandbox:**
   - The AI agent cannot execute RouterOS mutations directly without two-phase approval from the network administrator (`safe_config_engine.py`).
3. **Execution Timeouts:**
   - Background tasks and agent streaming are bounded by timeout envelopes, preventing resource exhaustion or infinite token loops.
