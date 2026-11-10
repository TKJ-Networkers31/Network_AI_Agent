/**
 * src/platform/adaptive-experience/index.js
 *
 * Public Entrypoint for VERA Adaptive Experience (VAE).
 * Consolidates Protocol, Registry, Renderers, Interactions, Asset Policies, and Telemetry.
 */

// Protocol
export {
  normalizeVaePayload,
  isVaePayload,
  createVaePayload,
  VAE_BLOCK_TYPES,
  DEFAULT_VAE_VERSION,
} from "./protocol/vaeProtocol.js";

// Registry
export {
  getVaeComponent,
  registerVaeComponent,
  hasVaeComponent,
  listRegisteredVaeComponents,
} from "./registry/componentRegistry.jsx";

// Renderers
export { default as ExperienceRenderer } from "./renderer/ExperienceRenderer.jsx";
export { default as ComponentErrorBoundary } from "./renderer/ComponentErrorBoundary.jsx";
export { default as UnknownBlockFallback } from "./renderer/UnknownBlockFallback.jsx";
export { parseMermaidCode, generateMermaidSvg } from "./renderer/mermaidParser.js";

// Interactions
export { ActionGateway, simulatePermission, executeAction, submitApproval } from "./interactions/ActionGateway.js";
export { default as UnifiedActionCard } from "./interactions/UnifiedActionCard.jsx";

// Assets & Security Policies
export { buildSafeSvg, isSvgContent } from "./assets/svgBuilder.js";
export {
  validateImageUrl,
  isSafeImageUrl,
  IMAGE_SECURITY_ATTRIBUTES,
} from "./assets/imagePolicy.js";

// Telemetry
export {
  ExperienceTelemetry,
  trackBlockRendered,
  trackInteractionSubmitted,
  getTelemetryEvents,
  clearTelemetryEvents,
  setTelemetryEnabled,
} from "./telemetry/experienceTelemetry.js";
