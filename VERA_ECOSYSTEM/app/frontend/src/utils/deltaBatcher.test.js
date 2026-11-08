import test from "node:test";
import assert from "node:assert/strict";
import { createStreamBatcher } from "./deltaBatcher.js";

/** Jam + timer palsu: waktu hanya maju lewat advance(). */
function fakeClock() {
  let time = 1000;
  let nextId = 1;
  const timers = new Map();

  return {
    now: () => time,
    setTimer: (fn, ms) => {
      const id = nextId++;
      timers.set(id, { fn, at: time + ms });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
    advance(ms) {
      const target = time + ms;

      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];

        if (!due) break;

        time = Math.max(time, due[1].at);
        timers.delete(due[0]);
        due[1].fn();
      }

      time = target;
    },
    timers: () => timers.size,
  };
}

const delta = (sid, run, seq, text = `t${seq}`) => ({
  type: "stream_delta",
  data: { session_id: sid, run_id: run, call: 1, attempt: 1, seq, text },
});

function setup(options = {}) {
  const clock = fakeClock();
  const applied = [];
  const batcher = createStreamBatcher({
    apply: (sid, events) => applied.push({ sid, events }),
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
    ...options,
  });

  return { clock, applied, batcher };
}

test("batcher: apply wajib fungsi", () => {
  assert.throws(() => createStreamBatcher({}), TypeError);
});

test("batcher: delta yang datang rapat digabung menjadi SATU apply, urutan terjaga", () => {
  const { clock, applied, batcher } = setup();

  for (let seq = 1; seq <= 30; seq += 1) batcher.push("s1", delta("s1", "r1", seq));

  assert.equal(applied.length, 0); // belum ada tulis sebelum timer
  assert.equal(batcher.pending("s1"), 30);

  clock.advance(0);

  assert.equal(applied.length, 1);
  assert.deepEqual(applied[0].events.map((e) => e.data.seq), Array.from({ length: 30 }, (_, i) => i + 1));
  assert.equal(batcher.pending(), 0);
});

test("batcher: paling sering sekali per minIntervalMs (bukan satu tulis per chunk)", () => {
  const { clock, applied, batcher } = setup({ minIntervalMs: 32 });
  let seq = 0;

  // 1 detik: satu chunk tiap 2 ms = 500 chunk
  for (let t = 0; t < 1000; t += 2) {
    batcher.push("s1", delta("s1", "r1", ++seq));
    clock.advance(2);
  }
  clock.advance(100);

  const total = applied.reduce((n, a) => n + a.events.length, 0);

  assert.equal(total, 500); // tidak ada event hilang
  assert.ok(applied.length <= Math.ceil(1000 / 32) + 2, `terlalu banyak tulis: ${applied.length}`);
  assert.ok(applied.length >= 25, `terlalu sedikit tulis: ${applied.length}`);

  // urutan seq global tetap
  const seqs = applied.flatMap((a) => a.events.map((e) => e.data.seq));
  assert.deepEqual(seqs, Array.from({ length: 500 }, (_, i) => i + 1));
});

test("batcher: event pertama setelah jeda lama diserahkan tanpa menunggu penuh minIntervalMs", () => {
  const { clock, applied, batcher } = setup({ minIntervalMs: 32 });

  clock.advance(500);
  batcher.push("s1", delta("s1", "r1", 1));
  clock.advance(0);

  assert.equal(applied.length, 1);
});

test("batcher: flush(sid) menyerahkan sekarang tanpa menyentuh sesi lain", () => {
  const { applied, batcher } = setup();

  batcher.push("A", delta("A", "rA", 1));
  batcher.push("B", delta("B", "rB", 1));

  assert.equal(batcher.flush("A"), 1);
  assert.deepEqual(applied.map((a) => a.sid), ["A"]);
  assert.equal(batcher.pending("A"), 0);
  assert.equal(batcher.pending("B"), 1);
});

test("batcher: isolasi sesi - tiap sesi menerima event miliknya sendiri", () => {
  const { clock, applied, batcher } = setup();

  batcher.push("A", delta("A", "rA", 1, "a1"));
  batcher.push("B", delta("B", "rB", 1, "b1"));
  batcher.push("A", delta("A", "rA", 2, "a2"));
  batcher.push("B", delta("B", "rB", 2, "b2"));
  clock.advance(0);

  const bySession = Object.fromEntries(applied.map((a) => [a.sid, a.events.map((e) => e.data.text)]));

  assert.deepEqual(bySession, { A: ["a1", "a2"], B: ["b1", "b2"] });
});

test("batcher: discard(sid, runId) membuang antrean run yang di-Stop, run lain tetap", () => {
  const { clock, applied, batcher } = setup();

  batcher.push("A", delta("A", "old", 1));
  batcher.push("A", delta("A", "old", 2));
  batcher.push("A", delta("A", "new", 1));

  assert.equal(batcher.discard("A", "old"), 2);
  clock.advance(0);

  assert.equal(applied.length, 1);
  assert.deepEqual(applied[0].events.map((e) => e.data.run_id), ["new"]);

  batcher.push("A", delta("A", "old", 3));
  assert.equal(batcher.discard("A", "old"), 1);
  assert.equal(batcher.pending("A"), 0);
  assert.equal(batcher.discard("tidak-ada", "x"), 0);
});

test("batcher: cancel() membatalkan timer dan mengosongkan antrean", () => {
  const { clock, applied, batcher } = setup();

  batcher.push("A", delta("A", "r", 1));
  assert.equal(clock.timers(), 1);

  batcher.cancel();
  clock.advance(1000);

  assert.equal(applied.length, 0);
  assert.equal(clock.timers(), 0);
  assert.equal(batcher.pending(), 0);
});

test("batcher: flushAll() melanjutkan sesi lain walau satu apply melempar, lalu melempar error pertama", () => {
  const seen = [];
  const clock = fakeClock();
  const batcher = createStreamBatcher({
    apply: (sid, events) => {
      seen.push(sid);
      if (sid === "A") throw new Error("boom A");
    },
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });

  batcher.push("A", delta("A", "r", 1));
  batcher.push("B", delta("B", "r", 1));

  assert.throws(() => batcher.flushAll(), /boom A/);
  assert.deepEqual(seen, ["A", "B"]);
  assert.equal(batcher.pending(), 0);
});

test("batcher: re-entrant - apply yang memanggil push/flush tidak memproses event dua kali", () => {
  const clock = fakeClock();
  const seen = [];
  let batcher;

  batcher = createStreamBatcher({
    apply: (sid, events) => {
      seen.push(events.map((e) => e.data.seq));

      if (events.some((e) => e.data.seq === 1)) {
        batcher.push(sid, delta(sid, "r", 99));
        batcher.flush(sid);
      }
    },
    now: clock.now,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });

  batcher.push("A", delta("A", "r", 1));
  batcher.flush("A");

  assert.deepEqual(seen, [[1], [99]]);
  assert.equal(batcher.pending(), 0);
});

test("batcher: input tidak valid (tanpa sid / event) diabaikan", () => {
  const { clock, applied, batcher } = setup();

  batcher.push("", delta("", "r", 1));
  batcher.push("A", null);
  clock.advance(100);

  assert.equal(applied.length, 0);
});
