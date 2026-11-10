# VERA VAE PROTOCOL V2 SPECIFICATION
## Wire Format, Block Typing, Composition Contracts & Backward Compatibility

**Document Identity:** VERA-PROTOCOL-V2-SPEC-2026-V1  
**Classification:** Core System Protocol Specification  
**Status:** COMPLETE & RATIFIED  
**Date:** November 2026  
**Ecosystem Path:** `/home/Lingga/Documents/project/Network_AI_Agent/VERA_ECOSYSTEM/`

---

## 1. PROTOCOL OVERVIEW

The VERA Adaptive Experience Protocol (VAE Protocol v2) establishes the typed contract between the backend reasoning engines and client presentation tiers.

### Key Version 2.0 Additions:
1. **Extended Visual Block Types:** Native support for `resource-gauge`, `metric-grid`, `interface-status`, `hop-by-hop-traceroute`, `route-table-view`, `incident-summary`, and `config-diff`.
2. **First-Class Metadata:** Standardized attributes for block confidence, layout hints (`grid`, `full-width`), source device tagging, and execution evidence.
3. **100% Backward Compatibility:** Legacy clients reading `.answer`, `.steps`, or Protocol v1.0 payloads continue to operate without breaking changes.

---

## 2. ENVELOPE SPECIFICATION

The root response envelope must conform to the following JSON schema:

```typescript
interface VaePayload {
  protocol: "vae";
  version: "2.0";
  created_at: number; // Unix timestamp
  metadata: {
    intent: string;
    confidence: number;
    primary_device?: string;
    step_count?: number;
    session_id?: string;
    [key: string]: any;
  };
  blocks: Array<VaeBlock>;
}
```

---

## 3. BLOCK SPECIFICATION

Each block within `blocks` conforms to the discriminated block contract:

```typescript
interface VaeBlock {
  id: string; // e.g. "blk_txt_8f1a2c3d" or "blk_gauge_5e2b1c4a"
  type: string; // Member of VaeBlockType enum
  data: Record<string, any>; // Component-specific payload
  metadata: {
    layout?: "full-width" | "grid" | "half-width";
    confidence?: number;
    source_device?: string;
    evidence_refs?: Array<string>;
    [key: string]: any;
  };
  created_at?: number;
}
```

---

## 4. NORMALIZATION & ERROR TOLERANCE

Client-side normalization in `app/frontend/src/platform/adaptive-experience/protocol/vaeProtocol.js:normalizeToVaeBlocks(input)` handles three distinct payload scenarios:

1. **Pure Protocol v2:** An object with `protocol: "vae"` and `blocks: [...]`. Validates every block; malformed blocks degrade to safe fallback cards without crashing the session.
2. **Protocol v1.0 Envelope:** Validates against legacy types, automatically promoting compatible blocks.
3. **Mixed Legacy Response:** `{ answer: "...", interaction_schema: {...}, vae_payload: {...} }`. If `vae_payload` is present, it takes precedence. Otherwise, synthesizes a primary `markdown` block and an optional `dio-interaction` block.

---

## 5. NARRATIVE-FIRST RULE IMPLEMENTATION

VAE Protocol v2 enforces that every multi-block payload **MUST** include a primary `markdown` narrative block as its first entry (`index 0`). This ensures that screen readers, audio synthesis engines (TTS), and text-based operational logs receive an executive summary before visual diagrams and telemetry cards are parsed.
