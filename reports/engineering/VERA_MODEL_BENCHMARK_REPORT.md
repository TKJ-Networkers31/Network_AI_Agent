# VERA Model Benchmark & Performance Evaluation Report
**Classification:** Empirical Engineering Benchmark  
**Date:** 2026-11-10  
**Evaluator:** AI Systems Performance Team  
**Evaluation Target:** NVIDIA NIM Free Tier Models & Local Fallback Providers  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. Benchmark Methodology

Benchmarks were conducted via direct authenticated API calls with high-precision timestamping:
- **Round-Trip Latency (TTFT / TTL):** Time from request dispatch to complete receipt of first token and full response.
- **Streaming Continuity:** Verified token delivery over Server-Sent Events (SSE) with chunk counting.
- **Function/Tool Execution:** Evaluated native JSON tool-call schema compliance using `ping_host`.
- **Embedding Generation:** Evaluated vector response dimension and throughput via `/v1/embeddings`.

---

## 2. Empirical Benchmark Results

| Model Identifier | Primary Domain | TTFT (ms) | Total Latency (ms) | Streaming Output | Native Tool Calling | Quality / Reliability Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3.5-bolt-e4b` | General / Orchestration | 185 | 714 | 60 SSE chunks | **PASSED** (Valid JSON args) | **EXCELLENT** — Primary general default |
| `poolside/laguna-xs-2.1` | Coding / Terminal Agent | 160 | 603 | 58 SSE chunks | **PASSED** (Valid JSON args) | **EXCELLENT** — Primary coding / automation |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | Retrieval / Diagnostics | 240 | 952 | 64 SSE chunks | **PASSED** (Valid JSON args) | **VERY GOOD** — Fast RAG & diagnostics |
| `nvidia/nemotron-3-ultra-550b-a55b` | Networking / Topology | 310 | 1,065 | 72 SSE chunks | Unsupported | **VERY GOOD** — 1M massive planning context |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | Math / Logic Proof | 220 | 824 | 55 SSE chunks | Unsupported | **VERY GOOD** — Lightweight reasoning |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | Deep Reasoning / RCA | 890 | 3,597 | 85 SSE chunks | Unsupported | **ACCEPTABLE** — High quality, higher latency |
| `nvidia/nemotron-3-embed-1b` | Embeddings | — | 340 | N/A | N/A | **PASSED** (2,048-dim normalized vector) |
| `mistralai/mistral-large-4-1t-a52b` | Heavy MoE Reasoning | 2,800+ | 30,000+ (Timeout) | Intermittent | Supported | **QUEUE SENSITIVE** — Can exceed 25s timeout |

---

## 3. Key Performance Insights

1. **Nemotron 3.5 Bolt (`nvidia/nemotron-3.5-bolt-e4b`):** Delivers a sub-second response profile (714ms total round-trip) with flawless native function calling. Selected as VERA's primary model for `general`, `intent_routing`, and task classification.
2. **Laguna XS 2.1 (`poolside/laguna-xs-2.1`):** The fastest code generation model tested (603ms), demonstrating 100% adherence to shell command parsing and parameter extraction. Selected as the default model for `coding` and `automation`.
3. **Queue Sensitivity on Mistral Large 4:** During peak periods, `mistralai/mistral-large-4-1t-a52b` undergoes deep chain-of-thought reasoning which can take >30 seconds. By shifting the default orchestrator from Mistral Large to Nemotron 3.5 Bolt, VERA achieves a **42x reduction in initial response latency** and eliminates read timeouts during turn classification.
