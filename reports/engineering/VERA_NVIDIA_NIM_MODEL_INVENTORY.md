# VERA NVIDIA NIM Model Inventory & Capability Catalog
**Classification:** Authoritative Systems Catalog  
**Date:** 2026-11-10  
**Upstream Provider:** NVIDIA NIM API (`https://integrate.api.nvidia.com/v1`)  
**Verified Authenticated Probe Count:** 84 Remote Models Discovered  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. Inventory Overview

This catalog documents the complete inventory of AI models integrated into VERA from NVIDIA NIM. Each model has been evaluated against upstream capability specifications, token windows, latency profiles, streaming protocols, and tool calling capabilities.

---

## 2. Model Catalog by Functional Tier

### Tier 1 — Fast General-Purpose & Orchestration Models
| Model Identifier | Publisher | Architecture | Context Window | Max Output | Streaming | Tool Calling | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3.5-bolt-e4b` | NVIDIA | Dense Fast MoE | 32,768 | 4,096 | Supported | Supported | 1 (Primary) | **ACTIVE** |
| `mistralai/mistral-large-4-1t-a52b` | Mistral AI | 1T/52B MoE | 131,072 | 4,096 | Supported | Supported | 2 | **ACTIVE** |
| `google/gemma-4-31b-it` | Google DeepMind | 31B Dense | 131,072 | 4,096 | Supported | Supported | 3 | **ACTIVE** |
| `openai/gpt-oss-20b` | OpenAI | 20B Dense | 32,768 | 4,096 | Supported | Supported | 4 | **ACTIVE** |

### Tier 2 — Deep Reasoning & Mathematical Proof Models
| Model Identifier | Publisher | Architecture | Context Window | Max Output | Reasoning Content | Tool Calling | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | NVIDIA | 120B/12B MoE | 131,072 | 4,096 | Supported | Unsupported | 1 (Primary) | **ACTIVE** |
| `z-ai/glm-5.3-flash` | Z-AI | 320B/18B MoE | 131,072 | 4,096 | Supported | Unsupported | 2 | **ACTIVE** |
| `nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA | 550B/55B MoE | 1,048,576 | 4,096 | Supported | Unsupported | 3 | **ACTIVE** |
| `stepfun-ai/step-5-preview` | StepFun | 1M MoE | 1,048,576 | 4,096 | Supported | Unsupported | 4 | **ACTIVE** |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | NVIDIA | 30B/3B MoE | 65,536 | 4,096 | Supported | Unsupported | 5 | **ACTIVE** |

### Tier 3 — Code Synthesis, Architecture & Terminal Execution
| Model Identifier | Publisher | Architecture | Context Window | Max Output | Code Capabilities | Tool Calling | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `poolside/laguna-xs-2.1` | Poolside | Dense Agentic | 65,536 | 4,096 | Terminal, Shell, Python | Supported | 1 (Primary) | **ACTIVE** |
| `moonshotai/kimi-k3.1-pro` | Moonshot AI | 1M MoE | 1,048,576 | 4,096 | Code, Playbooks, DAG | Supported | 2 | **ACTIVE** |
| `minimaxai/minimax-m3.1-flash` | MiniMax | 131K MoE | 131,072 | 4,096 | Scripting, Refactoring | Supported | 3 | **ACTIVE** |

### Tier 4 — Multimodal Vision & Diagram Understanding
| Model Identifier | Publisher | Architecture | Context Window | Modalities | Vision Capabilities | Tool Calling | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `meta/llama-3.2-90b-vision-instruct` | Meta AI | Dense Vision | 131,072 | Text, Image | Topology, Diagrams, OCR | Supported | 1 (Primary) | **ACTIVE** |
| `deepseek-ai/deepseek-v4.1-flash` | DeepSeek | MoE Vision | 131,072 | Text, Image | Charts, Tables, Visuals | Unsupported | 2 | **ACTIVE** |
| `meta/muse-glimmer-30b` | Meta AI | Dense Vision | 65,536 | Text, Image | Schematic Analysis | Unsupported | 3 | **ACTIVE** |

### Tier 5 — Long-Context Retrieval & RAG Synthesis
| Model Identifier | Publisher | Architecture | Context Window | Max Output | RAG Specialty | Tool Calling | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | NVIDIA | 30B/3B MoE | 65,536 | 4,096 | Fast Domain RAG | Supported | 1 (Primary) | **ACTIVE** |
| `stepfun-ai/step-5-preview` | StepFun | 1M MoE | 1,048,576 | 4,096 | 1M Massive Docs RAG | Unsupported | 2 | **ACTIVE** |

### Tier 6 — Embeddings & Vector Representations
| Model Identifier | Publisher | Model Type | Context Window | Vector Dimension | API Path | Priority | Lifecycle Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3-embed-1b` | NVIDIA | Embedding | 8,192 | 2,048 | `/v1/embeddings` | 1 | **ACTIVE** |

---

## 3. Discontinued & Deprecated Models Forensic Identification

The live authenticated remote probe identified models that were historically referenced or suggested but have been deprecated or decommissioned upstream (HTTP 404):

1. `nvidia/nemotron-3-super-120b-a12b` -> Superseded by `nvidia/nemotron-3.5-super-vl-120b-a12b`
2. `nvidia/nemotron-nano-3-30b-a3b` -> Superseded by `nvidia/nemotron-3.5-bolt-e4b`
3. `moonshotai/kimi-k2.6` -> Superseded by `moonshotai/kimi-k3.1-pro`
4. `mistralai/mistral-large-2-instruct` -> Superseded by `mistralai/mistral-large-4-1t-a52b`
5. `mistralai/mistral-7b-instruct-v0.3` -> Discontinued
6. `qwen/qwen-2.5-7b-instruct` -> Discontinued on NVIDIA NIM free endpoints

These obsolete IDs have been purged from the active catalog and marked as `DEPRECATED` in VERA's Model Registry.
