/**
 * src/platform/adaptive-experience/renderer/mermaidParser.test.js
 *
 * Tests for lightweight Mermaid flowchart parsing and SVG generation.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { parseMermaidCode, generateMermaidSvg } from "./mermaidParser.js";

test("Mermaid Parser: parses basic graph TD with directional nodes", () => {
  const code = `
    graph TD
    A[Core Router] --> B(Dist Switch)
    B --> C[Edge Device]
  `;

  const parsed = parseMermaidCode(code);
  assert.equal(parsed.direction, "TD");
  assert.equal(parsed.nodes.size, 3);
  assert.equal(parsed.nodes.get("A").label, "Core Router");
  assert.equal(parsed.nodes.get("B").label, "Dist Switch");
  assert.equal(parsed.nodes.get("C").label, "Edge Device");
  assert.equal(parsed.edges.length, 2);
  assert.equal(parsed.edges[0].from, "A");
  assert.equal(parsed.edges[0].to, "B");
});

test("Mermaid Parser: parses graph LR with edge labels and styles", () => {
  const code = `
    flowchart LR
    Ingress[Ingress Gateway] -->|BGP Sync| Aggregator[Route Reflector]
    Aggregator -.->|Telemetry| VERA[VERA Core]
    VERA ==>|Enforce Policy| Firewall[Edge Firewall]
  `;

  const parsed = parseMermaidCode(code);
  assert.equal(parsed.direction, "LR");
  assert.equal(parsed.nodes.size, 4);
  assert.equal(parsed.edges.length, 3);

  assert.equal(parsed.edges[0].label, "BGP Sync");
  assert.equal(parsed.edges[0].style, "solid");

  assert.equal(parsed.edges[1].label, "Telemetry");
  assert.equal(parsed.edges[1].style, "dashed");

  assert.equal(parsed.edges[2].label, "Enforce Policy");
  assert.equal(parsed.edges[2].style, "thick");
});

test("Mermaid Parser: generates valid SVG output", () => {
  const code = `
    graph TD
    NodeA --> NodeB
  `;

  const result = generateMermaidSvg(code);
  assert.equal(result.success, true);
  assert.equal(result.nodeCount, 2);
  assert.equal(result.edgeCount, 1);
  assert.match(result.svg, /<svg xmlns="http:\/\/www.w3.org\/2000\/svg"/);
  assert.match(result.svg, /vae-arrow/);
  assert.match(result.svg, /NodeA/);
  assert.match(result.svg, /NodeB/);
});

test("Mermaid Parser: gracefully handles empty or invalid code", () => {
  const empty = generateMermaidSvg("");
  assert.equal(empty.success, false);
  assert.equal(empty.nodeCount, 0);

  const invalid = generateMermaidSvg("%% comment only\n\n");
  assert.equal(invalid.success, false);
});
