// src/components/topology/multiDeviceRouteOverlay.test.js
import test from "node:test";
import assert from "node:assert/strict";
import {
  ROUTE_OVERLAY_SEGMENT_TYPES,
  fetchCrossDeviceRouteIntelligence,
  fetchTopologyRouteOverlay,
  getOverlaySegmentVisualStyle,
} from "./routeOverlayApi.js";
import { getMultiLayerEdgeVisualConfig, RELATIONSHIP_CLASSES } from "./topologyConstants.js";

async function withMockFetch(mockImpl, fn) {
  const orig = globalThis.fetch;
  globalThis.fetch = mockImpl;
  try {
    return await fn();
  } finally {
    globalThis.fetch = orig;
  }
}

test("getOverlaySegmentVisualStyle keeps inferred route overlay visually distinct from physical edges", () => {
  const physicalEdgeVis = getMultiLayerEdgeVisualConfig(
    {
      id: "e1",
      relationship_class: RELATIONSHIP_CLASSES.physical.id,
      verification_status: "confirmed",
      confidence_tier: "confirmed",
      oper_status: "up",
    },
    { id: "dev_a" },
    { id: "dev_b" },
    false
  );

  const inferredSegVis = getOverlaySegmentVisualStyle({
    overlay_segment_type: ROUTE_OVERLAY_SEGMENT_TYPES.INFERRED_ROUTE_PATH,
    hop_index: 1,
  });
  const recursiveSegVis = getOverlaySegmentVisualStyle({
    overlay_segment_type: ROUTE_OVERLAY_SEGMENT_TYPES.RECURSIVE_NEXT_HOP_DEPENDENCY,
    hop_index: 2,
  });
  const uncertainSegVis = getOverlaySegmentVisualStyle({
    overlay_segment_type: ROUTE_OVERLAY_SEGMENT_TYPES.ROUTE_UNCERTAINTY,
    hop_index: 3,
  });

  // Physical confirmed edge is solid ("none"), whereas every route overlay segment is dashed & non-physical
  assert.equal(physicalEdgeVis.strokeDasharray, "none");
  assert.equal(inferredSegVis.isPhysicalLink, false);
  assert.ok(inferredSegVis.strokeDasharray.length > 0);
  assert.equal(recursiveSegVis.isPhysicalLink, false);
  assert.equal(recursiveSegVis.strokeDasharray, "3 3");
  assert.equal(uncertainSegVis.isPhysicalLink, false);
  assert.match(uncertainSegVis.badge, /UNCERTAIN/);
});

test("fetchTopologyRouteOverlay and fetchCrossDeviceRouteIntelligence pass query & JSON parameters cleanly", async () => {
  const calls = [];
  await withMockFetch(
    async (url, opts) => {
      calls.push({ url: String(url), opts });
      return {
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          overlay: { mutates_physical_topology: false, segments_count: 2, segments: [] },
        }),
      };
    },
    async () => {
      const ov = await fetchTopologyRouteOverlay({
        sourceDevice: "dev_a",
        destination: "10.20.0.5",
        routingTable: "main",
      });
      assert.equal(ov.overlay.mutates_physical_topology, false);

      const xdev = await fetchCrossDeviceRouteIntelligence({
        source_device: "dev_a",
        destination: "10.20.0.5",
      });
      assert.equal(xdev.success, true);
    }
  );

  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/api\/topology\/route-overlay\?.*source_device=dev_a/);
  assert.match(calls[1].url, /\/api\/intelligence\/routes\/cross-device$/);
  assert.equal(calls[1].opts.method, "POST");
});
