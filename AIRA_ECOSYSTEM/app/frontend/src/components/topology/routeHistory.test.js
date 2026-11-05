// src/components/topology/routeHistory.test.js
// Frontend Unit Test Suite for WP 4.6.4 Historical Route Analytics & View Isolation

import test from "node:test";
import assert from "node:assert/strict";
import {
  listRouteSnapshots,
  getRouteSnapshot,
  createRouteSnapshots,
  verifyRouteSnapshot,
  compareRouteSnapshots,
  listRouteChanges,
  getRouteChangeDetail,
  getRouteHistoricalAnalytics,
  getRouteSnapshotBadgeState,
  applyLiveRoutePollingUpdate,
} from "./routeHistoryApi.js";

async function withMockFetch(mockFn, testFn) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFn;
  try {
    return await testFn();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

test("listRouteSnapshots encodes device_id, completeness, and pagination", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return { ok: true, json: async () => ({ success: true, snapshots: [], total: 0 }) };
    },
    async () => {
      await listRouteSnapshots({
        device_id: "dev_chr",
        completeness: "COMPLETE",
        limit: 20,
        offset: 10,
      });
    }
  );
  assert.ok(calledUrl.includes("/api/topology/route-snapshots"));
  assert.ok(calledUrl.includes("device_id=dev_chr"));
  assert.ok(calledUrl.includes("completeness=COMPLETE"));
  assert.ok(calledUrl.includes("limit=20"));
});

test("compareRouteSnapshots and verifyRouteSnapshot call dedicated route-snapshots endpoints", async () => {
  const urls = [];
  await withMockFetch(
    async (url) => {
      urls.push(String(url));
      return {
        ok: true,
        json: async () => ({
          success: true,
          verified: true,
          diff: { removal_suppression_active: true, changes: [] },
        }),
      };
    },
    async () => {
      await verifyRouteSnapshot("rsnap_1");
      const cmp = await compareRouteSnapshots("rsnap_1", "rsnap_2");
      assert.equal(cmp.diff.removal_suppression_active, true);
    }
  );
  assert.ok(urls[0].includes("/api/topology/route-snapshots/rsnap_1/verify"));
  assert.ok(urls[1].includes("/api/topology/route-snapshots/compare"));
  assert.ok(urls[1].includes("base_id=rsnap_1"));
  assert.ok(urls[1].includes("target_id=rsnap_2"));
});

test("createRouteSnapshots, getRouteSnapshot, listRouteChanges, getRouteChangeDetail, and analytics serialize cleanly", async () => {
  const calls = [];
  await withMockFetch(
    async (url, init) => {
      calls.push({ url: String(url), method: init?.method || "GET" });
      return { ok: true, json: async () => ({ success: true }) };
    },
    async () => {
      await createRouteSnapshots({ device_ids: ["dev_a"], description: "Baseline" });
      await getRouteSnapshot("rsnap_a");
      await listRouteChanges({ device_id: "dev_a", change_type: "GATEWAY_CHANGED" });
      await getRouteChangeDetail(42);
      await getRouteHistoricalAnalytics({ device_id: "dev_a", correlation_window_sec: 90 });
    }
  );
  assert.equal(calls[0].method, "POST");
  assert.ok(calls[1].url.includes("/route-snapshots/rsnap_a"));
  assert.ok(calls[2].url.includes("change_type=GATEWAY_CHANGED"));
  assert.ok(calls[3].url.includes("/route-snapshots/changes/42"));
  assert.ok(calls[4].url.includes("/route-snapshots/analytics"));
});

test("getRouteSnapshotBadgeState keeps SHA-256 integrity orthogonal to RIB completeness", () => {
  const partialVerified = getRouteSnapshotBadgeState("verified", "PARTIAL");
  assert.equal(partialVerified.integrity.status, "verified");
  assert.equal(partialVerified.completeness.isComplete, false);
  assert.equal(partialVerified.completeness.status, "PARTIAL");

  const completeCompromised = getRouteSnapshotBadgeState("compromised", "COMPLETE");
  assert.equal(completeCompromised.integrity.status, "compromised");
  assert.equal(completeCompromised.completeness.isComplete, true);
});

test("applyLiveRoutePollingUpdate isolates historical snapshot viewing from background live polling", () => {
  const historicalRoutes = [{ dst_prefix: "10.10.0.0/16", gateway: "10.0.0.1" }];
  const liveRoutes = [{ dst_prefix: "0.0.0.0/0", gateway: "10.99.99.1" }];

  const historicalViewState = {
    mode: "historical",
    activeSnapshot: { snapshot_id: "rsnap_old" },
    displayedRoutes: historicalRoutes,
    cachedLiveRoutes: [],
  };

  const nextHistorical = applyLiveRoutePollingUpdate(historicalViewState, {
    routes: liveRoutes,
    timestamp: 12345,
  });

  // Historical displayed routes MUST NOT be overwritten by live polling!
  assert.deepEqual(nextHistorical.displayedRoutes, historicalRoutes);
  assert.equal(nextHistorical.activeSnapshot.snapshot_id, "rsnap_old");
  assert.deepEqual(nextHistorical.cachedLiveRoutes, liveRoutes);

  // In live mode, displayedRoutes updates immediately
  const liveViewState = {
    mode: "live",
    activeSnapshot: null,
    displayedRoutes: [],
    cachedLiveRoutes: [],
  };
  const nextLive = applyLiveRoutePollingUpdate(liveViewState, {
    routes: liveRoutes,
    timestamp: 12346,
  });
  assert.deepEqual(nextLive.displayedRoutes, liveRoutes);
});
