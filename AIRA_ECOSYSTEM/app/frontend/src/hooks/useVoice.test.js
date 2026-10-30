// src/hooks/useVoice.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { MIC_STATES } from "./useVoice.js";

test("MIC_STATES: definisi status mikrofon lengkap & eksplisit", () => {
  assert.equal(MIC_STATES.UNAVAILABLE, "unavailable");
  assert.equal(MIC_STATES.IDLE, "idle");
  assert.equal(MIC_STATES.REQUESTING_PERMISSION, "requesting_permission");
  assert.equal(MIC_STATES.LISTENING, "listening");
  assert.equal(MIC_STATES.PERMISSION_DENIED, "permission_denied");
  assert.equal(MIC_STATES.ERROR, "error");
});
