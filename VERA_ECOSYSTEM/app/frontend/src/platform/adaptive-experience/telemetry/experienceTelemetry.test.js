/**
 * src/platform/adaptive-experience/telemetry/experienceTelemetry.test.js
 *
 * Tests for VAE Diagnostic Telemetry Logger.
 */

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  trackBlockRendered,
  trackInteractionSubmitted,
  getTelemetryEvents,
  clearTelemetryEvents,
  setTelemetryEnabled,
} from "./experienceTelemetry.js";

beforeEach(() => {
  clearTelemetryEvents();
  setTelemetryEnabled(true);
});

test("Experience Telemetry: tracks block rendered events", () => {
  trackBlockRendered({
    blockType: "metric-card",
    blockId: "blk_001",
    durationMs: 4.2,
    success: true,
  });

  const events = getTelemetryEvents();
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "block_rendered");
  assert.equal(events[0].blockType, "metric-card");
  assert.equal(events[0].blockId, "blk_001");
  assert.equal(events[0].success, true);
});

test("Experience Telemetry: tracks interaction submitted events", () => {
  trackInteractionSubmitted({
    interactionId: "act_123",
    actionType: "approval_decision",
    status: "success",
    details: { decision: "APPROVE" },
  });

  const events = getTelemetryEvents();
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "interaction_submitted");
  assert.equal(events[0].actionType, "approval_decision");
  assert.equal(events[0].details.decision, "APPROVE");
});

test("Experience Telemetry: honors setTelemetryEnabled(false)", () => {
  setTelemetryEnabled(false);
  trackBlockRendered({ blockType: "markdown" });

  const events = getTelemetryEvents();
  assert.equal(events.length, 0);
});
