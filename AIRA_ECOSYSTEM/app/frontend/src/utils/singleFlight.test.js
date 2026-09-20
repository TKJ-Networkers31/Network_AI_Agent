import test from "node:test";
import assert from "node:assert/strict";
import { createSingleFlight } from "./singleFlight.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("panggilan bersamaan berbagi satu eksekusi", async () => {
  let calls = 0;
  const run = createSingleFlight(async () => {
    calls += 1;
    await sleep(10);
    return "sesi-1";
  });

  const results = await Promise.all([run(), run(), run()]);

  assert.equal(calls, 1);
  assert.deepEqual(results, ["sesi-1", "sesi-1", "sesi-1"]);
});

test("setelah selesai, panggilan berikutnya menjalankan task baru", async () => {
  let calls = 0;
  const run = createSingleFlight(async () => {
    calls += 1;
    return `sesi-${calls}`;
  });

  assert.equal(await run(), "sesi-1");
  assert.equal(await run(), "sesi-2");
  assert.equal(calls, 2);
});

test("kegagalan tidak membuat single-flight macet", async () => {
  let calls = 0;
  const run = createSingleFlight(async () => {
    calls += 1;
    if (calls === 1) throw new Error("gagal");
    return "ok";
  });

  await assert.rejects(run(), /gagal/);
  assert.equal(await run(), "ok");
  assert.equal(calls, 2);
});

test("semua pemanggil bersamaan menerima error yang sama", async () => {
  const run = createSingleFlight(async () => {
    await sleep(5);
    throw new Error("boom");
  });

  const results = await Promise.allSettled([run(), run()]);
  assert.ok(results.every((r) => r.status === "rejected"));
});