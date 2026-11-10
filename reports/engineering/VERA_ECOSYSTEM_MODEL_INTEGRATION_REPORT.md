# VERA Ecosystem Model Integration Architecture Report
**Classification:** Cross-Subsystem Integration Architecture  
**Date:** 2026-11-10  
**Scope:** Integration of Model Registry Across All VERA Subsystems  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. Architectural Integration Map

The Model Registry serves as the unified intelligence backbone across the entire VERA ecosystem:

```mermaid
graph TD
    User([User Prompt / WebSocket]) --> TC[TaskClassifier (Nemotron 3.5 Bolt)]
    TC --> MR[ModelRouter]
    MR --> MP[ModelPolicy]
    MP --> MS[(ModelStore SQLite)]
    
    MR --> |SelectedModel Contract| REI[REI Agent / Planner]
    MR --> |SelectedModel Contract| AKANE[AKANE Reasoning Engine]
    MR --> |SelectedModel Contract| RAG[RAG & Memory Engine]
    MR --> |SelectedModel Contract| DIAG[RouterOS Diagnostics Engine]
    MR --> |SelectedModel Contract| VAE[VAE Generative UI Platform]
    
    REI --> PC[ProviderClient & Circuit Breaker]
    AKANE --> PC
    RAG --> PC
    DIAG --> PC
    VAE --> PC
    
    PC --> NIM[NVIDIA NIM Upstream]
    PC -.->|Failover| OLLAMA[Local Ollama]
```

---

## 2. Subsystem Integrations

### 2.1 REI Agent & Orchestration Planner
- **File:** `VERA_ECOSYSTEM/agents/rei/planner.py`, `VERA_ECOSYSTEM/agents/rei/provider_client.py`
- **Model Consumption:** Consumes `SelectedModel` emitted by `ModelRouter.select(task)`.
- **Streaming Handlers:** Connects directly to `WebSocketEventBridge`, piping SSE chunks from `ProviderClient.chat_stream()` to the UI stream sink in real time.

### 2.2 AKANE Reasoning & Safe Config Engine
- **File:** `VERA_ECOSYSTEM/agents/akane/reasoning_engine.py`, `safe_config_engine.py`
- **Model Consumption:** Routes deep network configuration validation and compliance audits to the `reasoning` tier (`nvidia/nemotron-3.5-super-vl-120b-a12b` or `z-ai/glm-5.3-flash`).
- **Safety Boundary:** Strict read-only simulation before any RouterOS mutation.

### 2.3 RAG & Semantic Context Memory
- **File:** `VERA_ECOSYSTEM/core/memory.py`, `core/context_semantic_memory.py`
- **Model Consumption:** Utilizes `nvidia/nemotron-3-embed-1b` for vector similarity searches over network manuals, runbooks, and device configurations.

### 2.4 RouterOS Live Hardware Diagnostics
- **File:** `VERA_ECOSYSTEM/core/nms_engine.py`, `core/network_diagnostics.py`
- **Model Consumption:** Utilizes tool-calling verified models (`nvidia/nemotron-3.5-bolt-e4b` and `poolside/laguna-xs-2.1`) to execute structured diagnostic functions (`ping`, `traceroute`, `interface_stats`, `vlan_verification`).

### 2.5 VAE Generative UI & Interactive SVG Platform
- **File:** `VERA_ECOSYSTEM/api/routers/vae.py`, `frontend/src/components/vae/`
- **Model Consumption:** Coordinates with `vision` and `networking` models to produce deterministic topology diagrams, interactive SVG maps, and rich visual telemetry blocks.
