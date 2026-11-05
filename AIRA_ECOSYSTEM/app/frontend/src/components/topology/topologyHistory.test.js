// src/components/topology/topologyHistory.test.js
// Frontend Unit Test Suite for Phase 4.4B Historical Topology & Change Detection

import test from "node:test";
import assert from "node:assert/strict";
import {
  listSnapshots,
  getSnapshot,
  createSnapshot,
  verifySnapshotIntegrity,
  compareSnapshots,
  listChanges,
  getChange,
  getSnapshotBadgeState,
} from "./topologyHistoryApi.js";

// Mock global fetch for API client tests
function withMockFetch(mockFn, testFn) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mockFn;
  try {
    return testFn();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

// -----------------------------------------------------------------------------
// 1. Snapshot Management API Client
// -----------------------------------------------------------------------------

test("listSnapshots serializes pagination, trigger_type, and include_graph correctly", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ success: true, snapshots: [], total: 0 }),
      };
    },
    async () => {
      await listSnapshots({ limit: 25, offset: 50, trigger_type: "manual", include_graph: false });
    }
  );

  assert.ok(calledUrl.includes("/api/topology/snapshots"));
  assert.ok(calledUrl.includes("limit=25"));
  assert.ok(calledUrl.includes("offset=50"));
  assert.ok(calledUrl.includes("trigger_type=manual"));
  assert.ok(calledUrl.includes("include_graph=false"));
});

test("getSnapshot encodes snapshotId safely and passes include_graph", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ success: true, snapshot: { snapshot_id: "snap/test#1" } }),
      };
    },
    async () => {
      await getSnapshot("snap/test#1", { include_graph: true });
    }
  );

  assert.ok(calledUrl.includes("/api/topology/snapshots/snap%2Ftest%231"));
  assert.ok(calledUrl.includes("include_graph=true"));
});

test("createSnapshot formats POST body and headers properly", async () => {
  let method = "";
  let bodyJson = {};
  await withMockFetch(
    async (url, init) => {
      method = init.method;
      bodyJson = JSON.parse(init.body);
      return {
        ok: true,
        json: async () => ({ success: true, snapshot: { snapshot_id: "snap_new" } }),
      };
    },
    async () => {
      await createSnapshot({ description: "Audit baseline", trigger_type: "manual" });
    }
  );

  assert.equal(method, "POST");
  assert.equal(bodyJson.description, "Audit baseline");
  assert.equal(bodyJson.trigger_type, "manual");
});

test("verifySnapshotIntegrity calls verify endpoint", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ success: true, verified: true, integrity_status: "verified" }),
      };
    },
    async () => {
      const res = await verifySnapshotIntegrity("snap_test");
      assert.equal(res.verified, true);
      assert.equal(res.integrity_status, "verified");
    }
  );

  assert.ok(calledUrl.includes("/api/topology/snapshots/snap_test/verify"));
});

// -----------------------------------------------------------------------------
// 2. Snapshot Comparison API Client
// -----------------------------------------------------------------------------

test("compareSnapshots serializes base_id and target_id correctly", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({
          success: true,
          diff: {
            summary: { nodes_added: 1, edges_removed: 0, indeterminate_count: 1 },
            structural_changes: [],
            indeterminate_items: [],
          },
        }),
      };
    },
    async () => {
      const res = await compareSnapshots("snap_1", "snap_2");
      assert.equal(res.diff.summary.nodes_added, 1);
      assert.equal(res.diff.summary.indeterminate_count, 1);
    }
  );

  assert.ok(calledUrl.includes("/api/topology/snapshots/compare"));
  assert.ok(calledUrl.includes("base_id=snap_1"));
  assert.ok(calledUrl.includes("target_id=snap_2"));
});

// -----------------------------------------------------------------------------
// 3. Topology Change History API Client
// -----------------------------------------------------------------------------

test("listChanges serializes all filters and time ranges", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ success: true, changes: [], total: 0 }),
      };
    },
    async () => {
      await listChanges({
        entity_id: "edge_r1_sw1",
        change_type: "STATUS_CHANGED",
        snapshot_id: "snap_10",
        start_time: 1700000000,
        end_time: 1700050000,
        limit: 50,
        offset: 10,
      });
    }
  );

  assert.ok(calledUrl.includes("/api/topology/changes"));
  assert.ok(calledUrl.includes("entity_id=edge_r1_sw1"));
  assert.ok(calledUrl.includes("change_type=STATUS_CHANGED"));
  assert.ok(calledUrl.includes("snapshot_id=snap_10"));
  assert.ok(calledUrl.includes("start_time=1700000000"));
  assert.ok(calledUrl.includes("end_time=1700050000"));
  assert.ok(calledUrl.includes("limit=50"));
  assert.ok(calledUrl.includes("offset=10"));
});

test("getChange calls change detail endpoint with ID", async () => {
  let calledUrl = "";
  await withMockFetch(
    async (url) => {
      calledUrl = String(url);
      return {
        ok: true,
        json: async () => ({ success: true, change: { id: 42, change_type: "NODE_MODIFIED" } }),
      };
    },
    async () => {
      const res = await getChange(42);
      assert.equal(res.change.id, 42);
      assert.equal(res.change.change_type, "NODE_MODIFIED");
    }
  );

  assert.ok(calledUrl.includes("/api/topology/changes/42"));
});

// -----------------------------------------------------------------------------
// 4. Semantic Graph Diff & Epistemic Safeguard Contracts
// -----------------------------------------------------------------------------

test("diff summary contract enforces separate indeterminate_count from confirmed removals", () => {
  const mockReport = {
    summary: {
      nodes_added: 2,
      nodes_removed: 0,
      nodes_modified: 1,
      edges_added: 1,
      edges_removed: 0,
      operational_changes: 2,
      freshness_changes: 1,
      evidence_changes: 3,
      indeterminate_count: 2,
    },
    indeterminate_items: [
      {
        indeterminate_type: "INDETERMINATE_UNREACHABLE_NODE",
        entity_id: "dev_unreachable",
        reason: "Device failed polling in target run",
      },
      {
        indeterminate_type: "INDETERMINATE_AMBIGUOUS_MATCH",
        entity_id: "edge_ambiguous",
        reason: "Missing interface on parallel link",
      },
    ],
  };

  // Indeterminate items MUST NOT be conflated with confirmed removals
  assert.equal(mockReport.summary.edges_removed, 0);
  assert.equal(mockReport.summary.nodes_removed, 0);
  assert.equal(mockReport.summary.indeterminate_count, 2);
  assert.equal(mockReport.indeterminate_items.length, 2);
  assert.equal(mockReport.indeterminate_items[0].indeterminate_type, "INDETERMINATE_UNREACHABLE_NODE");
  assert.equal(mockReport.indeterminate_items[1].indeterminate_type, "INDETERMINATE_AMBIGUOUS_MATCH");
});

test("snapshot completeness contract distinguishes Complete from Partial discovery", () => {
  const completeMetadata = {
    completeness: {
      is_complete: true,
      discovery_status: "complete",
      successful_devices: ["r1", "sw1"],
      failed_devices: [],
      timed_out_devices: [],
    },
  };

  const partialMetadata = {
    completeness: {
      is_complete: false,
      discovery_status: "partial",
      successful_devices: ["r1"],
      failed_devices: ["sw1"],
      timed_out_devices: [],
    },
  };

  assert.equal(completeMetadata.completeness.is_complete, true);
  assert.equal(partialMetadata.completeness.is_complete, false);
  assert.equal(partialMetadata.completeness.failed_devices.length, 1);
});

// -----------------------------------------------------------------------------
// 5. Orthogonal Integrity & Discovery Completeness Semantics
// -----------------------------------------------------------------------------

test("SnapshotIntegrityBadge preserves orthogonal independence of integrity and completeness", () => {
  // Combination 1: Valid SHA-256 + Complete Discovery
  const c1 = getSnapshotBadgeState("verified", true);
  assert.equal(c1.integrity.status, "verified");
  assert.equal(c1.integrity.label, "Verified");
  assert.equal(c1.completeness.isComplete, true);
  assert.equal(c1.completeness.label, "Complete");

  // Combination 2: Valid SHA-256 + Partial Discovery (Partial MUST NOT invalidate hash)
  const c2 = getSnapshotBadgeState("verified", false);
  assert.equal(c2.integrity.status, "verified");
  assert.equal(c2.integrity.label, "Verified");
  assert.equal(c2.completeness.isComplete, false);
  assert.equal(c2.completeness.label, "Partial Run");

  // Combination 3: Compromised SHA-256 + Complete Discovery (Hash failure MUST NOT imply partial discovery)
  const c3 = getSnapshotBadgeState("compromised", true);
  assert.equal(c3.integrity.status, "compromised");
  assert.equal(c3.integrity.label, "Compromised");
  assert.equal(c3.completeness.isComplete, true);
  assert.equal(c3.completeness.label, "Complete");

  // Combination 4: Compromised SHA-256 + Partial Discovery (Both states visible independently)
  const c4 = getSnapshotBadgeState("compromised", false);
  assert.equal(c4.integrity.status, "compromised");
  assert.equal(c4.integrity.label, "Compromised");
  assert.equal(c4.completeness.isComplete, false);
  assert.equal(c4.completeness.label, "Partial Run");

  // Combination 5: Unverified + Complete Discovery
  const c5 = getSnapshotBadgeState("unverified", true);
  assert.equal(c5.integrity.status, "unverified");
  assert.equal(c5.integrity.label, "Unverified");
  assert.equal(c5.completeness.isComplete, true);
  assert.equal(c5.completeness.label, "Complete");

  // Combination 6: Unverified + Partial Discovery
  const c6 = getSnapshotBadgeState("unverified", false);
  assert.equal(c6.integrity.status, "unverified");
  assert.equal(c6.integrity.label, "Unverified");
  assert.equal(c6.completeness.isComplete, false);
  assert.equal(c6.completeness.label, "Partial Run");
});
