# VERA Legacy AIRA Capability Map: Subsystem Lineage & Component Index

## Executive Summary

This document establishes the exhaustive mapping of every capability, service, engine, and interface originating in the AIRA development cycle and actively inherited by the **VERA Enterprise Network Intelligence Platform**. 

Every capability listed here has been audited and verified operating in `VERA_ECOSYSTEM/`.

---

## Master Capability Mapping Table

| ID | Capability Category | Legacy AIRA Origin | VERA Authoritative Component Path | Verification Status | Operational Mode |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CAP-01** | **User Authentication** | `core/auth/` (Stage 01/04) | `VERA_ECOSYSTEM/core/auth/auth_service.py` | VERIFIED | JWT token lifecycle, bcrypt hashing, session revocation. |
| **CAP-02** | **Multi-Tenancy Isolation** | `core/tenant/` (Stage 04) | `VERA_ECOSYSTEM/core/tenant/tenant_manager.py` | VERIFIED | Strict tenant boundary enforcement; zero memory/device leakage. |
| **CAP-03** | **Enterprise RBAC Engine** | `core/rbac/` (Stage 05) | `VERA_ECOSYSTEM/core/rbac/access_control.py` | VERIFIED | 82 granular permissions, 7 default roles (`SUPER_ADMIN` to `USER`). |
| **CAP-04** | **RBAC Simulation Sandbox**| `core/rbac/simulator.py` | `VERA_ECOSYSTEM/core/rbac/simulator.py` | VERIFIED | "Dry-run" permission tests for operators before grant commit. |
| **CAP-05** | **Zero-Trust SecretVault** | `core/vault/` (Stage 03) | `VERA_ECOSYSTEM/core/vault/secret_vault.py` | VERIFIED | AES-256-GCM encryption with PBKDF2 salt derivation. |
| **CAP-06** | **Credential Linking** | `agents/rei/inventory_tools.py` | `VERA_ECOSYSTEM/core/vault/credential_manager.py` | VERIFIED | Cryptographic association of router credentials to inventory items. |
| **CAP-07** | **Multi-Model Registry** | `core/model_registry.py` | `VERA_ECOSYSTEM/core/model_registry.py` | PRESERVED | Registry of OpenAI, Anthropic, OpenRouter, Ollama models. |
| **CAP-08** | **Intelligent Model Router** | `core/model_router.py` | `VERA_ECOSYSTEM/core/model_router.py` | PRESERVED | Cost, latency, and capability routing with automatic fallback. |
| **CAP-09** | **Model Policy Engine** | `core/model_policy.py` | `VERA_ECOSYSTEM/core/model_policy.py` | PRESERVED | Enterprise governance over allowed providers and temperature limits. |
| **CAP-10** | **AI Persona Engine** | `core/persona/` | `VERA_ECOSYSTEM/core/persona/engine.py` | VERIFIED | Dynamic system prompt builder enforcing canonical VERA identity. |
| **CAP-11** | **Semantic Context Memory**| `core/context/builder.py` | `VERA_ECOSYSTEM/core/context/builder.py` | VERIFIED | Context assembly across user memories, long-term facts, and heritage. |
| **CAP-12** | **Historical Heritage** | *New in VERA Migration* | `VERA_ECOSYSTEM/core/knowledge/heritage/` | VERIFIED | Deterministic retrieval of AIRA provenance and architectural history. |
| **CAP-13** | **14-Step Deterministic RCA**| `core/diagnostics/` (Net VI)| `VERA_ECOSYSTEM/core/diagnostics/rca_engine.py` | VERIFIED | Deterministic root cause diagnostics without LLM hallucination. |
| **CAP-14** | **RouterOS API Client** | `agents/akane/` (Net I-III)| `VERA_ECOSYSTEM/agents/akane/routeros_client.py` | VERIFIED | Binary RouterOS API connection pooling and command execution. |
| **CAP-15** | **SSH Network Execution** | `agents/akane/ssh_runner.py` | `VERA_ECOSYSTEM/agents/akane/ssh_runner.py` | VERIFIED | Paramiko-based authenticated SSH execution with output parsing. |
| **CAP-16** | **NMS Telemetry Engine** | `core/telemetry/` (Net V) | `VERA_ECOSYSTEM/core/telemetry/collector.py` | VERIFIED | Bounded concurrent polling for CPU, RAM, interfaces, and flaps. |
| **CAP-17** | **Metrics & Alert Hysteresis**| `core/telemetry/metrics.py` | `VERA_ECOSYSTEM/core/telemetry/metrics_store.py` | VERIFIED | Time-series telemetry storage with de-bounced alert triggers. |
| **CAP-18** | **The Dude Topology Fabric**| `core/topology/` (Net VII)| `VERA_ECOSYSTEM/core/topology/the_dude_fabric.py` | VERIFIED | Neighbor discovery via MNDP, CDP, LLDP, and dynamic ARP caches. |
| **CAP-19** | **Topology Layout Engine** | `core/topology/graph.py` | `VERA_ECOSYSTEM/core/topology/graph.py` | VERIFIED | Force-directed and hierarchical L2/L3 topology graph layout. |
| **CAP-20** | **Route Snapshot Engine** | `core/routing/` (Net IV) | `VERA_ECOSYSTEM/core/routing/snapshot.py` | VERIFIED | Cryptographically signed snapshots of IP routing tables. |
| **CAP-21** | **BGP / OSPF Analysis** | `core/routing/analyzer.py`| `VERA_ECOSYSTEM/core/routing/analyzer.py` | VERIFIED | Route flap detection, peer status monitoring, next-hop validation. |
| **CAP-22** | **OCR & Visual Intelligence**| `agents/hikari/` | `VERA_ECOSYSTEM/agents/hikari/vision_engine.py` | VERIFIED | Multi-modal OCR and network diagram parsing via vision models. |
| **CAP-23** | **Audio & Voice Processing**| `agents/yuki/` | `VERA_ECOSYSTEM/agents/yuki/voice_service.py` | VERIFIED | VAD (Voice Activity Detection), STT transcription, and TTS voice output. |
| **CAP-24** | **Dynamic Interaction (DIO)**| `core/dio/` (Stage 07) | `VERA_ECOSYSTEM/core/dio/engine.py` | VERIFIED | Structured input requests and confirmation dialogs for dangerous tools. |
| **CAP-25** | **VERA Adaptive Exp. (VAE)** | `core/vae/` (Sprint 3) | `VERA_ECOSYSTEM/core/vae/engine.py` | VERIFIED | Real-time generative UI component streaming over SSE/WebSocket. |
| **CAP-26** | **Sandbox Workspace FSE** | `core/filesystem/` | `VERA_ECOSYSTEM/core/filesystem/workspace.py` | VERIFIED | Sandboxed user workspace file manager with snapshot trash recovery. |
| **CAP-27** | **Real-Time Event Bus** | `core/events.py` (Stage 11)| `VERA_ECOSYSTEM/core/events.py` | VERIFIED | Pub/sub event broker connecting network alerts to UI listeners. |

---

## Summary of Parity

- **Total Capabilities Audited**: 27 Subsystems
- **Capabilities Maintained / Preserved**: 27 (100% Parity)
- **Capabilities Deprecated / Removed**: 1 (Token Debiting & Stripe Paywalls — per deliberate architectural decision `ADR-004` / `HERITAGE-04`)
- **New Capabilities Added**: VERA Heritage Knowledge Engine (`CAP-12`)
