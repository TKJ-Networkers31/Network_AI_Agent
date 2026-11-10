# VERA VAE GENERATIVE EXPERIENCE ARCHITECTURE
## Evolutionary Design, Adaptive Presentation & Interaction Orchestration

**Document Identity:** VERA-VAE-ARCH-2026-V1  
**Classification:** Product Platform Architecture  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. ARCHITECTURAL VISION & PRINCIPLES

VERA Adaptive Experience (VAE) evolves the conversational AI platform beyond static Markdown documents and raw JSON payloads.

VAE functions as an **adaptive presentation and interaction orchestration engine** that dynamically synthesizes the optimal user interface based on:
1. **User Intent:** What the operator is trying to accomplish (inspection, diagnostic, audit, repair, exploration).
2. **Task Classification:** Read-only inspection vs state-changing operation.
3. **Actual Tool Telemetry:** Live hardware measurements, routing tables, and interface states.
4. **Network Context:** Target devices, blast radius, topology relationships.
5. **Component Registry:** Officially registered, sandbox-tested React visual components.
6. **Authorization & Safety:** RBAC roles and interactive approval requirements.

### Core Architectural Policy: Narrative-First
- **Conclusions and Explanations:** Conveyed in concise, natural narrative text.
- **Key Measurements:** Presented in high-impact visual gauges or metric cards.
- **Topological Paths & Hops:** Visualized as interactive hop-by-hop nodes.
- **Tabular Records:** Formatted in structured, sortable, status-aware data blocks.
- **State Changes:** Wrapped in explicit `action-card` components with preview diffs and confirmation triggers.
- **Zero Raw Metadata:** System logs, execution counts (e.g., `"1 tool digunakan"`), and unparsed JSON are never dumped onto the operator.

---

## 2. TWO-TIER RUNTIME PIPELINE

The VAE Generative Experience is powered by two complementary subsystems in `core/vae/`:

```
   +--------------------------------------------------------------+
   |                     Brain / LLM Turn                         |
   |           (Natural Answer, Tool Execution Steps)             |
   +------------------------------+-------------------------------+
                                  |
                                  v
   +--------------------------------------------------------------+
   |                  TIER 1: ExperiencePlanner                   |
   |   - Intent Classification (Resource, Diagnostics, Route, etc)|
   |   - Tool Signal & Query Semantic Analysis                    |
   |   - ExperiencePlan (Block Priorities, Layout Hints)          |
   +------------------------------+-------------------------------+
                                  |
                                  v
   +--------------------------------------------------------------+
   |                  TIER 2: ExperienceComposer                  |
   |   - Narrative Sanitation (purges leakage & fixes tags)       |
   |   - Telemetry Extraction (CPU, RAM, Hops, Interfaces)        |
   |   - Protocol v2 Validation & Envelope Assembly               |
   +------------------------------+-------------------------------+
                                  |
                                  v
   +--------------------------------------------------------------+
   |                 Frontend: ExperienceRenderer                 |
   |   - ComponentRegistry Resolution                             |
   |   - Suspense & ErrorBoundary Isolation                       |
   |   - Unified Action Gateway & Interactive Triggers            |
   +--------------------------------------------------------------+
```

---

## 3. PROTOCOL V2 CONTRACT

The VAE Protocol v2 envelope guarantees backward compatibility while supporting structured visual layouts:

```json
{
  "protocol": "vae",
  "version": "2.0",
  "created_at": 1731168000.0,
  "metadata": {
    "intent": "resource_inspection",
    "confidence": 0.95,
    "primary_device": "MikroTik-hAP-ac-lite",
    "step_count": 1
  },
  "blocks": [
    {
      "id": "blk_txt_8f1a2c3d",
      "type": "markdown",
      "data": {
        "content": "Router hAP-ac-lite saat ini beroperasi normal dengan CPU stabil dan memori bebas 41 MB."
      },
      "metadata": { "layout": "full-width" }
    },
    {
      "id": "blk_gauge_5e2b1c4a",
      "type": "resource-gauge",
      "data": {
        "device": "hAP ac lite",
        "cpu": { "value": 12.0, "unit": "%", "status": "healthy" },
        "memory": { "value": 35.9, "used_mb": 23.0, "total_mb": 64.0, "status": "healthy" },
        "disk": { "value": 48.8, "used_mb": 7.8, "total_mb": 16.0, "status": "healthy" }
      },
      "metadata": { "layout": "grid", "confidence": 0.95 }
    },
    {
      "id": "blk_grid_9c3d4e5f",
      "type": "metric-grid",
      "data": {
        "items": [
          { "title": "CPU Load", "value": 12.0, "unit": "%", "status": "healthy" },
          { "title": "Free RAM", "value": 41.0, "unit": "MB", "status": "healthy" },
          { "title": "Uptime", "value": "4h51m16s", "unit": "", "status": "healthy" },
          { "title": "OS Version", "value": "6.49.18", "unit": "", "status": "healthy" }
        ]
      },
      "metadata": { "layout": "grid" }
    }
  ]
}
```

---

## 4. FRONTEND ARCHITECTURE & SAFETY
1. **Isolated Failure Domains:** Every block is rendered inside a `ComponentErrorBoundary`. If any component throws a JavaScript rendering exception, only that specific block degrades to an alert pill; the remaining blocks and the primary narrative remain fully visible.
2. **Safe DOM Sanitization:** All markdown and HTML rendering utilizes DOMPurify, eliminating XSS vectors.
3. **No Arbitrary Code Execution:** LLMs cannot output raw unvalidated `<script>` tags or arbitrary HTML components. Rendering is restricted strictly to components declared in `componentRegistry.jsx`.
4. **Action Gateways:** State-changing operations render as `action-card` components that communicate with the backend `ActionGateway` to verify user permissions and prompt for confirmation before invoking backend endpoints.
