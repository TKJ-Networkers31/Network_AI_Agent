// src/components/topology/multiLayerTopology.test.js
// Frontend Unit Test Suite for Phase 4.5 Multi-Layer Network Topology Visualization

import test from "node:test";
import assert from "node:assert/strict";
import {
  RELATIONSHIP_CLASSES,
  CONFIDENCE_TIERS,
  normalizeEdge,
  computeCurvedEdgePath,
  getMultiLayerEdgeVisualConfig,
} from "./topologyConstants.js";

// -----------------------------------------------------------------------------
// 1. Relationship Class Taxonomy & Metadata Tests
// -----------------------------------------------------------------------------

test("RELATIONSHIP_CLASSES defines all four required network layers", () => {
  assert.ok(RELATIONSHIP_CLASSES.physical);
  assert.ok(RELATIONSHIP_CLASSES.layer2);
  assert.ok(RELATIONSHIP_CLASSES.layer3);
  assert.ok(RELATIONSHIP_CLASSES.logical);

  assert.equal(RELATIONSHIP_CLASSES.physical.shortLabel, "Physical");
  assert.equal(RELATIONSHIP_CLASSES.layer2.shortLabel, "Layer 2");
  assert.equal(RELATIONSHIP_CLASSES.layer3.shortLabel, "Layer 3");
  assert.equal(RELATIONSHIP_CLASSES.logical.shortLabel, "Logical");
});

// -----------------------------------------------------------------------------
// 2. Edge Normalization Tests
// -----------------------------------------------------------------------------

test("normalizeEdge handles legacy link mapping to multi-layer taxonomy", () => {
  // Legacy routed link -> Layer 3 Reachability
  const routed = normalizeEdge({
    id: "l_routed",
    source_id: "r1",
    target_id: "r2",
    link_type: "routed",
    status: "up",
  });
  assert.equal(routed.relationship_class, "layer3");
  assert.equal(routed.direction, "directed");
  assert.equal(routed.oper_status, "up");

  // Legacy L2 adjacency link -> Layer 2 Adjacency
  const l2 = normalizeEdge({
    id: "l_sw",
    source: "sw1",
    target: "ap1",
    link_type: "layer2_adjacency",
    verification_status: "observed",
  });
  assert.equal(l2.relationship_class, "layer2");
  assert.equal(l2.verification_status, "observed");

  // Legacy VPN link -> Logical Relationship
  const vpn = normalizeEdge({
    id: "l_vpn",
    source_id: "r1",
    target_id: "r_branch",
    link_type: "vpn",
  });
  assert.equal(vpn.relationship_class, "logical");
});

test("normalizeEdge preserves native TopologyEdge Phase 4.1 properties", () => {
  const edge = normalizeEdge({
    id: "edge_native_1",
    source_node_id: "r1",
    target_node_id: "sw1",
    source_interface: "sfp-sfpplus1",
    target_interface: "sfp-sfpplus1",
    relationship_class: "physical",
    relationship_subtype: "direct_fiber",
    oper_status: "up",
    verification_status: "confirmed",
    confidence_tier: "CONFIRMED",
    confidence_score: 1.0,
    confidence_rationale: "LLDP bidirectional port match",
    vlan_id: 10,
    bandwidth_bps: 10000000000,
  });

  assert.equal(edge.relationship_class, "physical");
  assert.equal(edge.relationship_subtype, "direct_fiber");
  assert.equal(edge.confidence_tier, "CONFIRMED");
  assert.equal(edge.confidence_score, 1.0);
  assert.equal(edge.vlan_id, 10);
  assert.equal(edge.source_port, "sfp-sfpplus1");
  assert.equal(edge.target_port, "sfp-sfpplus1");
});

// -----------------------------------------------------------------------------
// 3. Parallel Multi-Edge Curvature Tests
// -----------------------------------------------------------------------------

test("computeCurvedEdgePath generates straight line for single edge", () => {
  const res = computeCurvedEdgePath(100, 100, 300, 100, 0, 1);
  assert.equal(res.isCurved, false);
  assert.equal(res.pathD, "M 100 100 L 300 100");
  assert.equal(res.labelX, 200);
  assert.equal(res.labelY, 100);
});

test("computeCurvedEdgePath computes symmetric offsets for parallel edge bundles", () => {
  // Bundle of 2 parallel edges (e.g. physical link + overlay)
  const edge0 = computeCurvedEdgePath(100, 200, 300, 200, 0, 2);
  const edge1 = computeCurvedEdgePath(100, 200, 300, 200, 1, 2);

  assert.equal(edge0.isCurved, true);
  assert.equal(edge1.isCurved, true);

  // Normal vector for horizontal line points in y-direction
  assert.ok(edge0.pathD.includes("Q"));
  assert.ok(edge1.pathD.includes("Q"));

  // The two control points must be on opposite sides of the baseline
  assert.notEqual(edge0.cy, edge1.cy);
  assert.ok(Math.abs((edge0.cy + edge1.cy) / 2 - 200) < 0.001);
});

// -----------------------------------------------------------------------------
// 4. Multi-Layer Visual Config Tests
// -----------------------------------------------------------------------------

test("getMultiLayerEdgeVisualConfig returns distinct visual aesthetics per layer", () => {
  const phys = getMultiLayerEdgeVisualConfig(
    { relationship_class: "physical", verification_status: "confirmed" },
    { reachability_status: "reachable" },
    { reachability_status: "reachable" }
  );
  assert.ok(phys.badge.includes("Phys"));
  assert.equal(phys.strokeDasharray, "none");

  const l2 = getMultiLayerEdgeVisualConfig(
    { relationship_class: "layer2", verification_status: "observed", vlan_id: 100 },
    null,
    null
  );
  assert.ok(l2.badge.includes("L2"));
  assert.ok(l2.badge.includes("100"));

  const l3 = getMultiLayerEdgeVisualConfig(
    { relationship_class: "layer3", oper_status: "up" },
    null,
    null
  );
  assert.equal(l3.badge, "L3 Routed");
  assert.equal(l3.markerEnd, "url(#arrow-layer3)");
  assert.equal(l3.strokeDasharray, "5,4");

  const logical = getMultiLayerEdgeVisualConfig(
    { relationship_class: "logical", relationship_subtype: "wireguard_vpn" },
    null,
    null
  );
  assert.ok(logical.badge.includes("WIREGUARD VPN"));
  assert.equal(logical.strokeDasharray, "10,4,2,4");
});

test("operational down and conflict override layer-specific aesthetics", () => {
  const down = getMultiLayerEdgeVisualConfig(
    { relationship_class: "physical", oper_status: "down" },
    null,
    null
  );
  assert.equal(down.badge, "✕ Down");
  assert.equal(down.stroke, "#ef4444");

  const conflict = getMultiLayerEdgeVisualConfig(
    { relationship_class: "layer2", verification_status: "conflicting" },
    null,
    null
  );
  assert.equal(conflict.badge, "⚠ Conflict");
  assert.equal(conflict.stroke, "#f43f5e");
});

// -----------------------------------------------------------------------------
// 5. Phase 1 Semantic Correctness & Misclassification Safeguards
// -----------------------------------------------------------------------------

test("PHYSICAL_ADJACENCY is never inferred from IP reachability, subnet overlap, or ARP", () => {
  // ARP-only observation must map to Layer 3 or Layer 2, never physical
  const arpEdge = normalizeEdge({
    id: "arp_obs_1",
    source_id: "core_gw",
    target_id: "host_pc",
    link_type: "routed",
    metadata: { discovery_protocol: "arp" },
  });
  assert.notEqual(arpEdge.relationship_class, "physical");
  assert.equal(arpEdge.relationship_class, "layer3");

  // Inferred subnet transit must map to Layer 3, not physical
  const subnetEdge = normalizeEdge({
    id: "subnet_transit_1",
    source_id: "router_a",
    target_id: "router_b",
    link_type: "inferred",
  });
  assert.notEqual(subnetEdge.relationship_class, "physical");
  assert.equal(subnetEdge.relationship_class, "layer3");
});

test("Conflicting evidence is never silently promoted to confirmed", () => {
  const conflictingEdge = normalizeEdge({
    id: "edge_conflict_1",
    source_id: "sw1",
    target_id: "sw2",
    relationship_class: "physical",
    verification_status: "conflicting",
    confidence_tier: "LOW",
    confidence_score: 0.2,
  });
  assert.equal(conflictingEdge.verification_status, "conflicting");

  const vis = getMultiLayerEdgeVisualConfig(conflictingEdge, null, null);
  assert.equal(vis.badge, "⚠ Conflict");
  assert.notEqual(vis.badge, "✓ Confirmed");
  assert.equal(vis.stroke, "#f43f5e");
});

test("Unknown or ambiguous relationships are not rendered as confirmed", () => {
  const unverifiedEdge = normalizeEdge({
    id: "edge_unverified_1",
    source_id: "sw1",
    target_id: "unknown_box",
    relationship_class: "layer2",
    verification_status: "unknown",
  });
  assert.equal(unverifiedEdge.verification_status, "unknown");

  const vis = getMultiLayerEdgeVisualConfig(unverifiedEdge, null, null);
  assert.notEqual(vis.badge, "✓ Confirmed");
  assert.ok(vis.badge.includes("L2"));
});

test("Confidence, operational status, freshness, and relationship class remain independent", () => {
  // Operational down on physical link does not change relationship class or confidence
  const downPhysical = normalizeEdge({
    id: "phys_down_1",
    source_id: "core1",
    target_id: "dist1",
    relationship_class: "physical",
    oper_status: "down",
    verification_status: "confirmed",
    confidence_tier: "CONFIRMED",
    confidence_score: 1.0,
    observation_freshness: "fresh",
  });
  assert.equal(downPhysical.relationship_class, "physical");
  assert.equal(downPhysical.oper_status, "down");
  assert.equal(downPhysical.confidence_tier, "CONFIRMED");
  assert.equal(downPhysical.confidence_score, 1.0);
  assert.equal(downPhysical.observation_freshness, "fresh");

  // High confidence routed link never becomes physical cabling
  const highConfL3 = normalizeEdge({
    id: "l3_high_1",
    source_id: "core1",
    target_id: "isp_gw",
    relationship_class: "layer3",
    confidence_tier: "HIGH",
    confidence_score: 0.95,
    oper_status: "up",
  });
  assert.equal(highConfL3.relationship_class, "layer3");
  const visL3 = getMultiLayerEdgeVisualConfig(highConfL3, null, null);
  assert.equal(visL3.markerEnd, "url(#arrow-layer3)");
  assert.ok(visL3.badge.includes("L3"));
});
