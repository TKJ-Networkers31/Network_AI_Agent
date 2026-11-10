/**
 * src/platform/adaptive-experience/protocol/vaeProtocol.js
 *
 * VERA Adaptive Experience (VAE) Protocol Definition & Normalizer.
 * Version: 1.0
 */

export const VAE_PROTOCOL_NAME = "vae";
export const VAE_PROTOCOL_VERSION = "2.0";

export const VAE_BLOCK_TYPES = Object.freeze({
  MARKDOWN: "markdown",
  TEXT: "text",
  CODE: "code",
  TABLE: "table",
  IMAGE: "image",
  SVG: "svg",
  INTERACTIVE_SVG: "interactive-svg",
  VRRP: "vrrp",
  TOPOLOGY_GRAPH: "topology-graph",
  MERMAID: "mermaid",
  GRAPH: "graph",
  MAP: "map",
  ACTION_CARD: "action-card",
  DIO_INTERACTION: "dio-interaction",
  METRIC_CARD: "metric-card",
  METRIC_GRID: "metric-grid",
  RESOURCE_GAUGE: "resource-gauge",
  INTERFACE_STATUS: "interface-status",
  HOP_TRACEROUTE: "hop-by-hop-traceroute",
  INCIDENT_SUMMARY: "incident-summary",
  ROOT_CAUSE_PANEL: "root-cause-panel",
  REMEDIATION_PLAN: "remediation-plan",
  ROUTE_TABLE: "route-table-view",
  CONFIG_DIFF: "config-diff",
  WORKFLOW_RECOVERY: "workflow-recovery",
  INVESTIGATION_TIMELINE: "investigation-timeline",
  EVIDENCE_CARD: "evidence-card",
  HEALTH_SUMMARY: "health-summary",
  TOPOLOGY_DETAIL: "topology-detail",
  UNKNOWN: "unknown",
});

export const SUPPORTED_BLOCK_TYPES = new Set(
  Object.values(VAE_BLOCK_TYPES).filter((t) => t !== VAE_BLOCK_TYPES.UNKNOWN)
);

function generateId(prefix = "blk") {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  }
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * Validates a single VAE block.
 * Never throws — returns a safe fallback block if invalid.
 */
export function validateVaeBlock(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      isValid: false,
      block: {
        id: generateId("err"),
        type: VAE_BLOCK_TYPES.UNKNOWN,
        data: { message: "Invalid block payload" },
      },
    };
  }

  const id = typeof raw.id === "string" && raw.id.trim() ? raw.id.trim() : generateId();
  const rawType = typeof raw.type === "string" ? raw.type.trim().toLowerCase() : "";

  if (!rawType || !SUPPORTED_BLOCK_TYPES.has(rawType)) {
    return {
      isValid: false,
      block: {
        id,
        type: VAE_BLOCK_TYPES.UNKNOWN,
        data: {
          originalType: raw.type,
          originalData: raw.data || {},
          message: `Komponen '${raw.type}' tidak didukung oleh VAE registry.`,
        },
      },
    };
  }

  return {
    isValid: true,
    block: {
      id,
      type: rawType,
      data: raw.data && typeof raw.data === "object" ? raw.data : {},
      metadata: raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {},
    },
  };
}

/**
 * Normalizes any response into an array of validated VAE blocks.
 * Seamlessly adapts legacy text/interactionSchema into VAE blocks.
 */
export function normalizeToVaeBlocks(input) {
  if (!input) return [];

  // Case 1: Already an array of VAE blocks
  if (Array.isArray(input)) {
    return input.map((b) => validateVaeBlock(b).block);
  }

  // Case 2: VAE Payload envelope { protocol: "vae", blocks: [...] }
  if (typeof input === "object" && Array.isArray(input.blocks)) {
    return input.blocks.map((b) => validateVaeBlock(b).block);
  }

  // Case 3: Mixed legacy payload { content?, answer?, interactionSchema?, vae_payload? }
  const blocks = [];

  const vaePayload = input.vae_payload || input.vaePayload;
  if (vaePayload && Array.isArray(vaePayload.blocks)) {
    return vaePayload.blocks.map((b) => validateVaeBlock(b).block);
  }

  const interactionSchema = input.interactionSchema || input.interaction_schema;
  if (interactionSchema && typeof interactionSchema === "object") {
    blocks.push({
      id: `dio_${interactionSchema.id || generateId()}`,
      type: VAE_BLOCK_TYPES.DIO_INTERACTION,
      data: { schema: interactionSchema },
      metadata: { mode: interactionSchema.mode || "form" },
    });
  }

  const rawText = input.content ?? input.answer ?? (typeof input === "string" ? input : null);
  if (typeof rawText === "string" && rawText.trim()) {
    blocks.push({
      id: generateId("txt"),
      type: VAE_BLOCK_TYPES.MARKDOWN,
      data: { content: rawText.trim() },
    });
  }

  return blocks;
}
