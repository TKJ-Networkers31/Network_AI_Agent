# VERA Adaptive Experience (VAE) — Protocol Specification

**Specification Version:** 1.0.0  
**Status:** Standard  
**Compatibility:** VERA 2.0+ (Backward compatible with AIRA Legacy Response Schemas)  

---

## 1. Abstract

This specification defines the communication and data interchange format for the VERA Adaptive Experience (VAE) platform. The protocol establishes a deterministic JSON representation for dynamic AI responses, interactive workflows, structured telemetry metrics, and visual diagrams.

---

## 2. Core Data Structures

### 2.1 `VaePayload`

The top-level envelope returned by AI conversation endpoints or message event streams.

```json
{
  "version": "1.0",
  "blocks": [ ... ],
  "metadata": {
    "session_id": "ses_01928374",
    "turn_id": "trn_98234123",
    "model": "deepseek-r1:14b",
    "timestamp": 1731081600000
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | `string` | Yes | Protocol version string (default: `"1.0"`). |
| `blocks` | `Array<VaeBlock>` | Yes | Ordered array of display and interaction blocks. |
| `metadata` | `object` | No | Arbitrary execution metadata (model, latency, session). |

---

### 2.2 `VaeBlock`

The fundamental unit of content in a VAE message.

```typescript
interface VaeBlock {
  id: string;                    // Unique identifier (e.g. "blk_e3f9a1b2")
  type: VaeBlockType;           // Supported block kind
  data: Record<string, any>;     // Block-specific payload
  metadata?: Record<string, any>;// Optional presentation hints
}
```

---

## 3. Supported Block Types (`VaeBlockType`)

| Block Type | Primary Component | Required `data` Properties | Description |
|---|---|---|---|
| `markdown` | `Markdown.jsx` / `StreamingMarkdown.jsx` | `content` (string) | Rich text, headings, tables, formulas (KaTeX). |
| `text` | `Markdown.jsx` | `content` (string) | Plain or formatted text (alias of `markdown`). |
| `metric-card` | `MetricCard.jsx` | `title`, `value` | Enterprise KPI metrics with trends and status badges. |
| `dio-interaction`| `Renderer.jsx` (DIO) | `schema` (DIO Schema object)| Interactive dynamic input forms. |
| `action-card` | `UnifiedActionCard.jsx` | `title` or `syntax` | Remediation actions with RBAC simulation and approval. |
| `unified-action-card`| `UnifiedActionCard.jsx` | `title` or `syntax` | Explicit unified action card type. |
| `graph` | `GraphBlock.jsx` | `graph` (JSON string or object)| Network topology graphs (`nodes` + `edges`). |
| `map` | `MapBlock.jsx` | `map` (JSON string or object) | Geographical Leaflet map coordinates. |
| `mermaid` | `MermaidBlock.jsx` | `code` or `syntax` (string) | Flowcharts, sequence diagrams, and architecture flows. |
| `unknown` | `UnknownBlockFallback.jsx` | `raw_type`, `raw_data` | Safe fallback block for unrecognized types. |

---

## 4. Block Payload Specifications

### 4.1 `metric-card` Block
```json
{
  "id": "blk_metric_01",
  "type": "metric-card",
  "data": {
    "title": "BGP Peer Flap Rate",
    "value": "0.02",
    "unit": "flaps/hr",
    "trend": "down",
    "status": "healthy",
    "subtitle": "Last 24 hours across 12 edge peers"
  }
}
```

### 4.2 `action-card` Block
```json
{
  "id": "blk_action_01",
  "type": "action-card",
  "data": {
    "action_id": "act_bgp_soft_reset",
    "title": "Soft Reset BGP Session",
    "target_device": "cr01.jkt01",
    "risk_level": "HIGH",
    "syntax": "clear ip bgp 10.254.1.1 soft in",
    "description": "Performs inbound soft reconfiguration without tearing down TCP peering.",
    "requires_approval": true
  }
}
```

### 4.3 `mermaid` Block
```json
{
  "id": "blk_mermaid_01",
  "type": "mermaid",
  "data": {
    "code": "graph TD\nEdgeRouter[Edge Router] --> DistSwitch[Dist Switch]\nDistSwitch --> Core[VERA Core]"
  }
}
```

---

## 5. Backward Compatibility & Normalization Rules

The VAE protocol layer must accept legacy non-VAE structures and adapt them transparently:

1. **Legacy String Input:**
   A raw string `"Hello VERA"` is normalized to:
   ```json
   {
     "version": "1.0",
     "blocks": [{ "id": "blk_...", "type": "markdown", "data": { "content": "Hello VERA" } }]
   }
   ```
2. **Legacy Dual Content + DIO Schema:**
   A response containing `{ content: "Please confirm", interaction_schema: { ... } }` is adapted into:
   - Block 1: `type: "markdown"`, `data: { content: "Please confirm" }`
   - Block 2: `type: "dio-interaction"`, `data: { schema: { ... } }`
3. **Corrupted or Unknown Blocks:**
   Blocks lacking required fields or specifying unregistered types are never dropped silently; they are transformed into `type: "unknown"` and presented cleanly to the user with debugging information.
