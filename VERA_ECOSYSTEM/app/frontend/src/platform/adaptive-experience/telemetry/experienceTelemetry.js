/**
 * src/platform/adaptive-experience/telemetry/experienceTelemetry.js
 *
 * Lightweight Diagnostic Telemetry Logger for VERA Adaptive Experience (VAE).
 * Tracks block rendering, interaction submissions, and layout lifecycle events.
 */

const MAX_BUFFER_SIZE = 100;
const eventBuffer = [];
let telemetryEnabled = true;

/**
 * Records a block rendering lifecycle event.
 *
 * @param {{ blockType: string, blockId?: string, durationMs?: number, success?: boolean, error?: string }} event
 */
export function trackBlockRendered(event) {
  if (!telemetryEnabled) return;

  const record = {
    type: "block_rendered",
    timestamp: Date.now(),
    blockType: event?.blockType || "unknown",
    blockId: event?.blockId || null,
    durationMs: typeof event?.durationMs === "number" ? event.durationMs : 0,
    success: event?.success !== false,
    error: event?.error || null,
  };

  pushEvent(record);
}

/**
 * Records an interaction submission event (e.g. form submit, approval decision, action invocation).
 *
 * @param {{ interactionId: string, actionType: string, status: "pending" | "success" | "failure", details?: any }} event
 */
export function trackInteractionSubmitted(event) {
  if (!telemetryEnabled) return;

  const record = {
    type: "interaction_submitted",
    timestamp: Date.now(),
    interactionId: event?.interactionId || "unknown",
    actionType: event?.actionType || "generic",
    status: event?.status || "pending",
    details: event?.details || null,
  };

  pushEvent(record);
}

function pushEvent(record) {
  eventBuffer.push(record);
  if (eventBuffer.length > MAX_BUFFER_SIZE) {
    eventBuffer.shift();
  }
}

/**
 * Returns a shallow copy of recently recorded telemetry events.
 */
export function getTelemetryEvents() {
  return [...eventBuffer];
}

/**
 * Clears the telemetry in-memory buffer.
 */
export function clearTelemetryEvents() {
  eventBuffer.length = 0;
}

/**
 * Toggles telemetry event recording.
 */
export function setTelemetryEnabled(enabled) {
  telemetryEnabled = Boolean(enabled);
}

export const ExperienceTelemetry = Object.freeze({
  trackBlockRendered,
  trackInteractionSubmitted,
  getTelemetryEvents,
  clearTelemetryEvents,
  setTelemetryEnabled,
});

export default ExperienceTelemetry;
