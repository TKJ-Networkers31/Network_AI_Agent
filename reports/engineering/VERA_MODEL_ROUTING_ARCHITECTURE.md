# VERA Model Routing Architecture & Dynamic Selection Specification
**Classification:** Core System Architecture Specification  
**Date:** 2026-11-10  
**Modules:** `VERA_ECOSYSTEM/core/model_router.py`, `VERA_ECOSYSTEM/core/model_policy.py`, `VERA_ECOSYSTEM/core/model_store.py`

---

## 1. Architectural Routing Flow

VERA decouples model selection from agent execution. Agents (REI, AKANE) do not make hardcoded model selections; they consume `SelectedModel` contracts yielded by `ModelRouter` and validated by `ModelPolicy`:

```
User Query / Agent Task
          │
          ▼
TaskClassifier (LLM or Heuristic)
          │
          ▼ TaskClassification
ModelRouter.select(task)
   ├─ Checks default routing for task.primary_label
   ├─ Checks provider health (Circuit Breaker state)
   └─ Validates capability requirements (tools, vision, voice)
          │
          ▼ Candidate Model Record
ModelPolicy.ensure_usable()
   ├─ Validates enabled == 1
   ├─ Checks token budget against context_window (check_context)
   └─ Fallback resolution if model missing or disabled
          │
          ▼
     SelectedModel
          │
          ▼
ProviderClient.call_model() / ProviderClient.chat_stream()
```

---

## 2. Default Routing Matrix

The production routing table in `database/model_router.db` routes each primary label to an optimal, verified model:

| Task Label | Assigned Default Model Record | Upstream Model Identifier | Provider | Reasoning for Selection |
| :--- | :--- | :--- | :--- | :--- |
| `general` | `nemotron_3_5_bolt_fast_agent` | `nvidia/nemotron-3.5-bolt-e4b` | NVIDIA | Ultra-fast (714ms), native tool calling, reliable streaming. Replaces timeout-prone Mistral Large. |
| `reasoning` | `nemotron_3_5_super_120b_12b_moe` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | NVIDIA | 120B MoE deep reasoning, math proof, and root cause analysis. |
| `coding` | `laguna_xs_2_1_terminal_agentic` | `poolside/laguna-xs-2.1` | NVIDIA | 603ms latency, specialized for shell scripts, Python, regex, and terminal commands. |
| `networking` | `nemotron_3_ultra_550b_network_plan` | `nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA | 550B model with 1M context window for full-topology analysis and capacity planning. |
| `vision` | `llama_3_2_90b_vision` | `meta/llama-3.2-90b-vision-instruct` | NVIDIA | 90B multimodal vision model with diagram perception and OCR. |
| `voice` | `nemotron_3_5_bolt_voice_dialogue` | `nvidia/nemotron-3.5-bolt-e4b` | NVIDIA | Fast dialogue generation suitable for conversational voice synthesis. |
| `retrieval` | `nemotron_3_5_lightning_fast_rag` | `nvidia/nemotron-3.5-lightning-30b-a3b` | NVIDIA | Domain-specialized 30B MoE for high-speed document search and RAG synthesis. |
| `automation` | `laguna_xs_2_1_terminal_agentic` | `poolside/laguna-xs-2.1` | NVIDIA | Agentic tool-calling model verified against RouterOS and network automation commands. |

---

## 3. Fallback Hierarchy & Multi-Provider Resolution

When a model call encounters a failure, the resolution follows strict operational rules:

1. **Rule 1 (Model Disabled / Missing):**  
   If the designated model is disabled or deleted, `ModelPolicy.ensure_usable()` immediately shifts to the configured fallback model (`fallback_model_id`).
2. **Rule 2 (Context Window Exceeded):**  
   If `estimated_tokens > model.context_window`, `ModelPolicy.check_context()` locates a model with the same label possessing a larger context window (up to 1,048,576 tokens).
3. **Rule 3 (Model-Specific Non-Degrading Error - e.g. 404):**  
   The failing model is marked `UNAVAILABLE` locally. The provider circuit breaker remains `CLOSED`. `policy.on_provider_failure()` attempts an alternative model on the same provider.
4. **Rule 4 (Endpoint Degradation / Circuit Breaker OPEN - The P0 Fix):**  
   When the provider circuit breaker trips to `OPEN`:
   - All subsequent models on the degraded provider are **FAST-FAILED** and never called over the network.
   - `policy.on_provider_failure()` and `policy.fallback_candidates()` filter candidate models to **independent providers only** (e.g., local Ollama or secondary cloud API).
   - If no independent provider is registered or online, VERA terminates immediately with a clear circuit breaker notification, preventing the 15-model cascade.
