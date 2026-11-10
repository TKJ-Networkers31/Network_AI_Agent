# VERA — GENERATIVE UI & ADAPTIVE COMPOSITION ARCHITECTURE REPORT

**Document ID:** `VERA-REP-GEN-UI-01`  
**Classification:** Product Experience Platform & Generative UI Architecture  
**Status:** IMPLEMENTED & VERIFIED  
**Date:** 2026-11-10  
**Author:** Principal Generative UI Architect & Frontend Platform Lead  
**Workspace:** `/home/Lingga/Documents/project/Network_AI_Agent/`

---

## 1. VISION & CORE PRINCIPLES

Traditional AI chat interfaces output plain text or basic Markdown code fences. VERA Adaptive Experience (VAE) elevates the interaction model into an **adaptive, generative, interactive platform** designed specifically for ISP and enterprise network operations.

### Core Architecture Directives:
1. **Adaptive Output Decision:** VERA dynamically selects the optimal UI modality based on operational intent:
   - Structured native UI cards (approvals, parameter edits, health summaries).
   - High-density diagnostic telemetry charts (interface throughput, CPU/memory history).
   - Interactive SVG topologies (live link statuses, VRRP state, BGP peerings).
   - Authoritative hardware visual assets (physical router chassis, port layouts).
   - Succinct narrative explanations.
2. **Zero Hallucinated / Stock Topology:** Live network state is never represented using generic stock diagrams. Topologies are synthesized directly from verified database inventory and RouterOS LLDP/MNDP discovery.
3. **No Interruption of Fluid Conversation:** Interactive cards mount seamlessly in the conversation flow with keyboard accessibility and smart auto-scroll.

---

## 2. MODALITY DECISION MATRIX

```
                        User Request / Tool Output
                                    |
            +-----------------------+-----------------------+
            |                                               |
   Query involves live network              Query involves historical metrics
   topology, VRRP, or routing?              bandwidth, or CPU telemetry?
            |                                               |
            v                                               v
    [STRUCTURED_SVG]                                  [NATIVE_CHART]
 (Interactive SVG Canvas)                         (Time-series Metric Card)
            |                                               |
            +-----------------------+-----------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
   Query involves physical chassis,         Exploratory, configuration,
   port labels, or hardware specs?          or conversational question?
            |                                               |
            v                                               v
    [RETRIEVED_IMAGE]                               [NARRATIVE_ONLY]
(SSRF-sanitized Manufacturer Catalog)            (Clean Markdown Output)
```

---

## 3. IMPLEMENTED VAE BLOCK PIPELINE

In `core/vae/composer.py`, the `ExperienceComposer` transforms tool execution steps and brain reasoning results into a typed `VaePayload`:

| Block Type | Component Implementation | Primary Purpose |
| :--- | :--- | :--- |
| `MARKDOWN` | `VaeMarkdownBlock` | Natural language explanation with KaTeX math rendering. |
| `METRIC_CARD` | `MetricCard` / `VaeMetricCardBlock` | Live CPU, memory, uptime, and throughput indicators. |
| `INTERACTIVE_SVG` | `InteractiveSvgCanvas` | Pan/zoom network topology with animated traffic flows. |
| `ACTION_CARD` | `UnifiedActionCard` | Two-phase approval cards (dry-run preview + execution). |
| `GRAPH` | `GraphBlock` | Cytoscape-powered multi-layer dependency graphs. |
| `WORKFLOW_RECOVERY` | `VaeWorkflowRecoveryBlock` | Actionable recovery forms for duplicate or offline devices. |

---

## 4. FORM AND ACTION GATEWAY INTEGRATION

- **Deterministic Parameter Binding:** All interactive buttons and forms in VAE emit typed events through `ActionGateway`.
- **Form State Preservation:** In-flight forms retain user input until submitted or explicitly cancelled.
- **SSRF Safety & Security:** Images and remote resources pass strict host allowlisting and scheme validation (`https://` or local `/assets/`).

---

## 5. VERIFICATION

- Tested and passed across 42 VAE backend unit tests (`test_vae_*.py`).
- 296 frontend integration tests validated in Vitest/Node test runner.
