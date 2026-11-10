import test from "node:test";
import assert from "node:assert/strict";
import {
  validateVaeBlock,
  normalizeToVaeBlocks,
  VAE_BLOCK_TYPES,
  SUPPORTED_BLOCK_TYPES,
} from "./vaeProtocol.js";

test("vaeProtocol: exports frozen block types and supported set", () => {
  assert.equal(typeof VAE_BLOCK_TYPES.MARKDOWN, "string");
  assert.equal(typeof VAE_BLOCK_TYPES.DIO_INTERACTION, "string");
  assert.ok(SUPPORTED_BLOCK_TYPES.has("markdown"));
  assert.ok(SUPPORTED_BLOCK_TYPES.has("action-card"));
  assert.ok(!SUPPORTED_BLOCK_TYPES.has("unknown"));
});

test("vaeProtocol: validateVaeBlock accepts valid block", () => {
  const result = validateVaeBlock({
    id: "b1",
    type: "markdown",
    data: { content: "Sample text" },
  });
  assert.equal(result.isValid, true);
  assert.equal(result.block.id, "b1");
  assert.equal(result.block.type, "markdown");
  assert.equal(result.block.data.content, "Sample text");
});

test("vaeProtocol: validateVaeBlock falls back safely on unsupported type", () => {
  const result = validateVaeBlock({
    id: "b_hack",
    type: "malicious_script",
    data: { script: "alert(1)" },
  });
  assert.equal(result.isValid, false);
  assert.equal(result.block.type, "unknown");
  assert.ok(result.block.data.message.includes("tidak didukung"));
});

test("vaeProtocol: normalizeToVaeBlocks converts legacy text and interactionSchema", () => {
  const legacy = {
    content: "Please fill out this form:",
    interactionSchema: { id: "s1", mode: "form", fields: [] },
  };
  const blocks = normalizeToVaeBlocks(legacy);
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type, "dio-interaction");
  assert.equal(blocks[0].data.schema.id, "s1");
  assert.equal(blocks[1].type, "markdown");
  assert.equal(blocks[1].data.content, "Please fill out this form:");
});

test("vaeProtocol: normalizeToVaeBlocks handles raw string", () => {
  const blocks = normalizeToVaeBlocks("Pure string answer");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "markdown");
  assert.equal(blocks[0].data.content, "Pure string answer");
});

test("vaeProtocol: normalizeToVaeBlocks tolerates null/undefined", () => {
  assert.deepEqual(normalizeToVaeBlocks(null), []);
  assert.deepEqual(normalizeToVaeBlocks(undefined), []);
});
