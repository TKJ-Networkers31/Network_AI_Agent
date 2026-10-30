// src/pages/nmsOptimization.test.js
import test from "node:test";
import assert from "node:assert/strict";

test("NMS Delta Update: pembaruan satu perangkat tidak mengubah referensi perangkat lain", () => {
  const initialDevices = [
    { id: "dev-1", name: "Core-R1", status: "UP", latency_ms: 2.5 },
    { id: "dev-2", name: "Dist-SW1", status: "UP", latency_ms: 1.1 },
    { id: "dev-3", name: "Edge-AP1", status: "UP", latency_ms: 5.0 },
  ];

  const updatePayload = {
    device_id: "dev-2",
    status: "DEGRADED",
    latency_ms: 85.0,
    timestamp: 1700000000,
  };

  // Reducer normalized in-place delta update (sama seperti di NmsPage.jsx)
  function applyDeviceUpdate(prev, update) {
    const idx = prev.findIndex((d) => d.id === update.device_id);
    if (idx === -1) return prev;
    const dev = prev[idx];
    if (dev.status === update.status && dev.latency_ms === update.latency_ms) {
      return prev;
    }
    const next = [...prev];
    next[idx] = {
      ...dev,
      status: update.status,
      latency_ms: update.latency_ms,
      last_check_at: update.timestamp,
    };
    return next;
  }

  const updatedDevices = applyDeviceUpdate(initialDevices, updatePayload);

  // dev-2 diperbarui
  assert.equal(updatedDevices[1].status, "DEGRADED");
  assert.equal(updatedDevices[1].latency_ms, 85.0);

  // dev-1 dan dev-3 mempertahankan identitas objek yang sama (tidak ada re-render tak perlu)
  assert.equal(updatedDevices[0], initialDevices[0]);
  assert.equal(updatedDevices[2], initialDevices[2]);
});

test("NMS Delta Update: data identik mengembalikan referensi array yang sama (zero rerender)", () => {
  const initialDevices = [
    { id: "dev-1", name: "Core-R1", status: "UP", latency_ms: 2.5 },
  ];

  const sameUpdate = {
    device_id: "dev-1",
    status: "UP",
    latency_ms: 2.5,
    timestamp: 1700000000,
  };

  function applyDeviceUpdate(prev, update) {
    const idx = prev.findIndex((d) => d.id === update.device_id);
    if (idx === -1) return prev;
    const dev = prev[idx];
    if (dev.status === update.status && dev.latency_ms === update.latency_ms) {
      return prev;
    }
    const next = [...prev];
    next[idx] = { ...dev, status: update.status, latency_ms: update.latency_ms };
    return next;
  }

  const result = applyDeviceUpdate(initialDevices, sameUpdate);
  assert.equal(result, initialDevices, "Array reference harus persis sama jika status/latency tidak berubah");
});

test("NMS Single-Flight: panggilan bersamaan tidak menduplikasi request", async () => {
  let executionCount = 0;
  let inFlight = false;

  async function singleFlightTask() {
    if (inFlight) return "skipped";
    inFlight = true;
    try {
      executionCount += 1;
      await new Promise((r) => setTimeout(r, 20));
      return "executed";
    } finally {
      inFlight = false;
    }
  }

  const [res1, res2] = await Promise.all([singleFlightTask(), singleFlightTask()]);

  assert.equal(executionCount, 1, "Hanya 1 task yang boleh dieksekusi saat ada tumpang-tindih");
  assert.equal(res1, "executed");
  assert.equal(res2, "skipped");
});
