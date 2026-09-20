import test from "node:test";
import assert from "node:assert/strict";
import {
  EVENT_RESPONSE_CHUNK,
  PHASE_ACK,
  PHASE_SENDING,
  RUN_STATUS,
  appendChunk,
  applyAck,
  applyResponse,
  createRun,
  deriveChatView,
  reduceRunEvent,
  settleStreamingMessage,
  shouldShowLiveSteps,
} from "./runLifecycle.js";

const SID = "s1";
const RID = "r1";

const ev = (type, data = {}) => ({ type, data: { session_id: SID, run_id: RID, ...data } });
const chunk = (delta, data = {}) => ev(EVENT_RESPONSE_CHUNK, { delta, ...data });

// Keadaan sesudah user menekan kirim (runTurn): run "Mengirim..." + bubble user.
function afterSend(overrides = {}) {
  return {
    run: createRun({ runId: RID }),
    messages: [{ role: "user", content: "halo", isNew: true }],
    ...overrides,
  };
}

function play(events, start = afterSend(), opts = {}) {
  return events.reduce((state, event) => reduceRunEvent(state, event, opts), start);
}

const assistantMessages = (messages) => messages.filter((m) => m.role === "assistant");

// ============================================================
// KIRIM -> THINKING
// ============================================================

test("kirim: run langsung berstatus thinking dengan fase 'Mengirim...' dan tanpa tool", () => {
  const run = createRun({ runId: RID });

  assert.equal(run.status, RUN_STATUS.THINKING);
  assert.equal(run.phase, PHASE_SENDING);
  assert.deepEqual(run.liveTools, []);
});

test("ack: fase jadi 'Menganalisis permintaan...', runId dan status terjaga", () => {
  const { run } = play([ev("ack")]);

  assert.equal(run.phase, PHASE_ACK);
  assert.equal(run.runId, RID);
  assert.equal(run.status, RUN_STATUS.THINKING);
});

test("ack tanpa run (giliran suara) membuat run dari run_id server", () => {
  const { run } = play([ev("ack")], { run: null, messages: [] });

  assert.equal(run.runId, RID);
  assert.equal(run.phase, PHASE_ACK);
});

test("ack berulang tidak mengganti objek run dan tidak menghapus kartu tool", () => {
  const started = play([ev("ack"), ev("tool_start", { name: "ping", category: "network" })]);
  const again = reduceRunEvent(started, ev("ack"));

  assert.equal(again.run, started.run);
  assert.equal(again.run.liveTools.length, 1);
});

test("ack terlambat (fase masih 'Mengirim...') mengubah fase tapi TIDAK mereset kartu tool", () => {
  const withTool = play([ev("tool_start", { name: "ping", category: "network" })]);

  assert.equal(withTool.run.phase, PHASE_SENDING);

  const acked = reduceRunEvent(withTool, ev("ack"));

  assert.equal(acked.run.phase, PHASE_ACK);
  assert.equal(acked.run.liveTools.length, 1);
  assert.equal(acked.run.liveTools[0].name, "ping");
});

test("thinking memperbarui fase; pesan yang sama tidak membuat objek run baru", () => {
  const first = play([ev("thinking", { message: "Menyusun jawaban..." })]);
  const second = reduceRunEvent(first, ev("thinking", { message: "Menyusun jawaban..." }));

  assert.equal(first.run.phase, "Menyusun jawaban...");
  assert.equal(second.run, first.run);
});

test("tool_start/tool_finish: kartu tool berjalan lalu selesai (perilaku lama terjaga)", () => {
  const state = play([
    ev("tool_start", { name: "ping", category: "network" }),
    ev("tool_start", { name: "get_routes", category: "mikrotik" }),
    ev("tool_finish", { name: "ping", success: true, duration: 0.4 }),
  ]);

  const [ping, routes] = state.run.liveTools;

  assert.equal(ping.success, true);
  assert.equal(ping.duration, 0.4);
  assert.equal(routes.success, null);
});

test("tool_finish tanpa pasangan tool_start tidak mengubah run", () => {
  const start = afterSend();
  const after = reduceRunEvent(start, ev("tool_finish", { name: "ping", success: true }));

  assert.equal(after.run, start.run);
});

// ============================================================
// STREAMING: chunk pertama -> response mulai tampil
// ============================================================

test("chunk pertama: thinking berhenti, pesan assistant streaming muncul setelah bubble user", () => {
  const { run, messages } = play([ev("ack"), chunk("Halo")]);

  assert.equal(run.status, RUN_STATUS.STREAMING);
  assert.equal(run.phase, "");

  assert.equal(messages.length, 2);
  assert.deepEqual(messages[1], {
    role: "assistant",
    content: "Halo",
    steps: [],
    streaming: true,
    runId: RID,
    isNew: true,
  });
});

test("chunk berikutnya: run tetap OBJEK YANG SAMA dan pesan diperpanjang di posisi yang sama", () => {
  const afterFirst = play([ev("ack"), chunk("Ha")]);
  const afterSecond = reduceRunEvent(afterFirst, chunk("lo, "));
  const afterThird = reduceRunEvent(afterSecond, chunk("dunia"));

  assert.equal(afterSecond.run, afterFirst.run);
  assert.equal(afterThird.run, afterFirst.run);

  assert.equal(afterThird.messages.length, 2);
  assert.equal(afterThird.messages[1].content, "Halo, dunia");
  assert.equal(afterThird.messages[1].streaming, true);
});

test("thinking/ack yang datang terlambat saat streaming TIDAK menghidupkan animasi thinking lagi", () => {
  const streaming = play([ev("ack"), chunk("Halo")]);

  const lateThinking = reduceRunEvent(streaming, ev("thinking", { message: "Menyusun jawaban..." }));
  const lateAck = reduceRunEvent(streaming, ev("ack"));

  assert.equal(lateThinking.run, streaming.run);
  assert.equal(lateAck.run, streaming.run);
  assert.equal(lateThinking.run.phase, "");
  assert.equal(lateAck.run.phase, "");
});

test("tool tetap tercatat saat streaming tanpa mengembalikan fase thinking", () => {
  const state = play([
    chunk("Halo"),
    ev("tool_start", { name: "ping", category: "network" }),
    ev("tool_finish", { name: "ping", success: true }),
  ]);

  assert.equal(state.run.status, RUN_STATUS.STREAMING);
  assert.equal(state.run.phase, "");
  assert.equal(state.run.liveTools[0].success, true);
});

test("chunk kosong / bukan string diabaikan (tanpa transisi, tanpa pesan)", () => {
  const start = afterSend();

  for (const delta of ["", null, undefined, 42]) {
    const after = reduceRunEvent(start, chunk(delta));
    assert.equal(after.run, start.run);
    assert.equal(after.messages, start.messages);
  }
});

test("chunk tanpa run_id memakai run_id run aktif", () => {
  const start = afterSend();
  const event = { type: EVENT_RESPONSE_CHUNK, data: { session_id: SID, delta: "Halo" } };

  const after = reduceRunEvent(start, event);

  assert.equal(after.messages[1].runId, RID);
});

test("chunk saat tidak ada run (mis. sesudah response) dibuang: tidak ada pesan hantu", () => {
  const done = play([chunk("Halo"), ev("response", { answer: "Halo!", steps: [] })]);

  assert.equal(done.run, null);

  const late = reduceRunEvent(done, chunk(" telat"));

  assert.equal(late.messages, done.messages);
  assert.equal(assistantMessages(late.messages).length, 1);
});

test("chunk dari run yang sudah di-Stop atau run lain dibuang", () => {
  const start = afterSend();

  const stale = reduceRunEvent(start, chunk("x"), { staleRunIds: new Set([RID]) });
  const other = reduceRunEvent(start, chunk("x", { run_id: "r-lain" }));

  assert.equal(stale.messages, start.messages);
  assert.equal(stale.run, start.run);
  assert.equal(other.messages, start.messages);
  assert.equal(other.run, start.run);
});

// ============================================================
// COMPLETE: animasi berhenti, pesan diganti di tempat
// ============================================================

test("response sesudah streaming: run selesai, pesan DIGANTI di index yang sama (tanpa bubble ganda)", () => {
  const streaming = play([ev("ack"), chunk("Ha"), chunk("lo")]);
  const indexBefore = streaming.messages.findIndex((m) => m.streaming);

  const done = reduceRunEvent(
    streaming,
    ev("response", {
      answer: "Halo, ada yang bisa dibantu?",
      steps: [{ type: "tool_call", name: "ping", success: true }],
      user_turn_id: 10,
      assistant_turn_id: 11,
    })
  );

  assert.equal(done.run, null);
  assert.equal(done.messages.length, streaming.messages.length);
  assert.equal(assistantMessages(done.messages).length, 1);

  const final = done.messages[indexBefore];

  assert.equal(final.content, "Halo, ada yang bisa dibantu?");
  assert.equal(final.streaming, undefined);
  assert.equal(final.local, undefined);
  assert.equal(final.turnId, 11);
  assert.equal(final.isNew, true);
  assert.equal(final.steps.length, 1);

  assert.equal(done.messages[0].turnId, 10);
});

test("response tanpa chunk (perilaku backend saat ini): tepat satu pesan assistant ditambahkan", () => {
  const done = play([ev("ack"), ev("response", { answer: "Selesai", steps: [], assistant_turn_id: 5 })]);

  assert.equal(done.run, null);
  assert.equal(done.messages.length, 2);
  assert.equal(done.messages[1].content, "Selesai");
  assert.equal(done.messages[1].isNew, true);
});

test("response memakai answer server sebagai sumber kebenaran walau chunk berbeda", () => {
  const done = play([chunk("draf sementara"), ev("response", { answer: "Jawaban final", steps: [] })]);

  assert.equal(done.messages[1].content, "Jawaban final");
});

test("response dari run lain: pesan tetap ditampilkan, run aktif TIDAK dihentikan", () => {
  const start = afterSend();
  const after = reduceRunEvent(start, ev("response", { run_id: "r-lain", answer: "punya run lain", steps: [] }));

  assert.equal(after.run, start.run);
  assert.equal(assistantMessages(after.messages).length, 1);
});

test("response dari run basi menggantikan potongan yang sudah di-settle, bukan menggandakan", () => {
  const streaming = play([chunk("sebagian")]);
  const settled = { run: null, messages: settleStreamingMessage(streaming.messages, RID) };

  const late = reduceRunEvent(
    settled,
    ev("response", { answer: "lengkap", steps: [] }),
    { staleRunIds: new Set([RID]) }
  );

  assert.equal(assistantMessages(late.messages).length, 1);
  assert.equal(late.messages[1].content, "lengkap");
  assert.equal(late.messages[1].local, undefined);
});

// ============================================================
// DIO / SVG / IMAGE tidak merusak lifecycle
// ============================================================

const SVG_ANSWER = [
  "Ini diagramnya:",
  "```svg",
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>',
  "```",
  "![router](https://example.com/r.jpg)",
].join("\n");

test("potongan berisi fence svg/gambar (termasuk yang belum lengkap) tidak mengubah state proses", () => {
  const first = play([chunk("Ini diagramnya:\n```svg\n<svg xmlns=")]);

  for (const part of [
    '"http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
    "<rect/></svg>\n```\n",
    "![router](https://exam",
    "ple.com/r.jpg)",
  ]) {
    const next = reduceRunEvent(first, chunk(part));
    assert.equal(next.run, first.run);
    assert.equal(next.messages.length, first.messages.length);
  }
});

test("jawaban svg+gambar: final menggantikan pesan streaming apa adanya, run berhenti", () => {
  const streaming = play([chunk("Ini diagramnya:\n```svg\n<svg")]);
  const done = reduceRunEvent(streaming, ev("response", { answer: SVG_ANSWER, steps: [] }));

  assert.equal(done.run, null);
  assert.equal(assistantMessages(done.messages).length, 1);
  assert.equal(done.messages[1].content, SVG_ANSWER);
});

test("jawaban DIO: interaction_schema terbawa, tanpa status 'resolved', animasi berhenti", () => {
  const schema = { id: "schema_abc", mode: "form", sections: [], actions: [] };

  const streaming = play([chunk("Sebentar, aku butuh data tambahan.")]);
  const done = reduceRunEvent(
    streaming,
    ev("response", {
      answer: "Sebentar, aku butuh data tambahan.",
      steps: [{ type: "tool_call", name: "request_structured_input", success: true }],
      interaction_schema: schema,
      assistant_turn_id: 21,
    })
  );

  const final = done.messages[1];

  assert.equal(done.run, null);
  assert.deepEqual(final.interactionSchema, schema);
  assert.equal(final.interactionResolved, undefined);
  assert.equal(final.turnId, 21);
  assert.equal(assistantMessages(done.messages).length, 1);
});

test("jawaban DIO tanpa teks: pesan tetap dibuat sekali dengan schema", () => {
  const schema = { id: "schema_x", mode: "location_permission", sections: [], actions: [] };
  const done = play([ev("ack"), ev("response", { answer: "", steps: [], interaction_schema: schema })]);

  assert.equal(done.run, null);
  assert.equal(done.messages.length, 2);
  assert.deepEqual(done.messages[1].interactionSchema, schema);
});

test("response tanpa interaction_schema menghasilkan interactionSchema null (bukan undefined)", () => {
  const done = play([ev("response", { answer: "ok", steps: [] })]);

  assert.equal(done.messages[1].interactionSchema, null);
});

// ============================================================
// ERROR / CANCEL
// ============================================================

test("error NON-fatal: proses & animasi tetap hidup, tidak ada bubble ganda; response yang mengakhiri", () => {
  const start = afterSend();
  const errored = reduceRunEvent(start, ev("error", { message: "Model timeout" }));

  assert.equal(errored.run, start.run);
  assert.equal(errored.messages, start.messages);

  const done = reduceRunEvent(
    errored,
    ev("response", { answer: "Terjadi error saat menghubungi model: Model timeout", steps: [], error: true })
  );

  assert.equal(done.run, null);
  assert.equal(assistantMessages(done.messages).length, 1);
});

test("error fatal tidak diproses reducer (butuh snapshot rollback di failRun)", () => {
  const start = afterSend();
  const after = reduceRunEvent(start, ev("error", { message: "boom", fatal: true }));

  assert.equal(after.run, start.run);
  assert.equal(after.messages, start.messages);
});

test("event basi/run lain untuk ack, thinking, tool tidak mengubah apa pun", () => {
  const start = afterSend();

  for (const opts of [{ staleRunIds: new Set([RID]) }, {}]) {
    const runId = opts.staleRunIds ? RID : "r-lain";

    for (const type of ["ack", "thinking", "tool_start", "tool_finish"]) {
      const after = reduceRunEvent(start, ev(type, { run_id: runId, name: "ping", message: "x" }), opts);
      assert.equal(after.run, start.run, `${type} (${runId})`);
    }
  }
});

test("Stop/cancel/error fatal saat streaming: potongan dipertahankan sebagai pesan lokal, tidak streaming lagi", () => {
  const streaming = play([chunk("Sebagian jawab")]);
  const settled = settleStreamingMessage(streaming.messages, RID);

  assert.equal(settled[1].streaming, false);
  assert.equal(settled[1].local, true);
  assert.equal(settled[1].content, "Sebagian jawab");
  assert.equal(settled.length, streaming.messages.length);
});

test("settleStreamingMessage: no-op (array sama) kalau tidak ada yang streaming atau run berbeda", () => {
  const plain = afterSend().messages;
  const streaming = play([chunk("x")]).messages;

  assert.equal(settleStreamingMessage(plain, RID), plain);
  assert.equal(settleStreamingMessage(streaming, "r-lain"), streaming);
});

test("chunk susulan dari run yang sudah di-Stop tidak membuat pesan hantu", () => {
  const streaming = play([chunk("Sebagian")]);
  const stopped = {
    run: null,
    messages: settleStreamingMessage(streaming.messages, RID),
  };

  const late = reduceRunEvent(stopped, chunk(" lanjutan"), { staleRunIds: new Set([RID]) });

  assert.equal(late.messages, stopped.messages);
  assert.equal(late.messages[1].content, "Sebagian");
});

// ============================================================
// HELPER PESAN
// ============================================================

test("appendChunk: hanya menambah ke pesan streaming milik run yang sama", () => {
  const first = appendChunk([], "rA", "A");
  const second = appendChunk(first, "rB", "B");

  assert.equal(second.length, 2);
  assert.equal(appendChunk(second, "rA", "1")[0].content, "A1");
  assert.equal(appendChunk(second, "rB", "2")[1].content, "B2");
});

test("applyResponse tanpa run_id selalu menambah pesan (tidak menimpa pesan lain)", () => {
  const messages = [{ role: "assistant", content: "lama", runId: null }];
  const next = applyResponse(messages, { answer: "baru", steps: [] });

  assert.equal(next.length, 2);
  assert.equal(next[0].content, "lama");
});

test("applyAck murni: tidak memutasi run masukan", () => {
  const run = Object.freeze(createRun({ runId: RID }));

  assert.doesNotThrow(() => applyAck(run, RID));
});

// ============================================================
// VIEW: nilai turunan untuk ChatPage
// ============================================================

test("deriveChatView: idle -> tidak loading, fase kosong", () => {
  const view = deriveChatView({ activeRun: null, activeId: SID });

  assert.deepEqual(
    { loading: view.loading, streaming: view.streaming, phase: view.phase, tools: view.liveTools.length },
    { loading: false, streaming: false, phase: "", tools: 0 }
  );
});

test("deriveChatView: thinking -> loading + fase; streaming -> tetap loading (Stop aktif) tapi fase kosong", () => {
  const thinking = deriveChatView({ activeRun: createRun({ runId: RID }), activeId: SID });
  const streamingRun = play([chunk("Halo")]).run;
  const streaming = deriveChatView({ activeRun: streamingRun, activeId: SID });

  assert.equal(thinking.loading, true);
  assert.equal(thinking.phase, PHASE_SENDING);
  assert.equal(thinking.streaming, false);

  assert.equal(streaming.loading, true);
  assert.equal(streaming.streaming, true);
  assert.equal(streaming.phase, "");
});

test("deriveChatView: New Chat yang sedang membuat sesi langsung menampilkan 'Mengirim...'", () => {
  const view = deriveChatView({ activeRun: null, creatingSession: true, activeId: null });

  assert.equal(view.loading, true);
  assert.equal(view.phase, PHASE_SENDING);
});

test("deriveChatView: creatingSession diabaikan di sesi lain / begitu run sudah ada", () => {
  const otherSession = deriveChatView({ activeRun: null, creatingSession: true, activeId: "sesi-lain" });
  const runExists = deriveChatView({
    activeRun: play([chunk("x")]).run,
    creatingSession: true,
    activeId: null,
  });

  assert.equal(otherSession.loading, false);
  assert.equal(otherSession.phase, "");
  assert.equal(runExists.phase, "");           // streaming: tidak kembali ke "Mengirim..."
  assert.equal(runExists.streaming, true);
});

test("shouldShowLiveSteps: tidak ada wadah kosong saat streaming tanpa tool, tampil lagi kalau ada tool", () => {
  const streamingRun = play([chunk("Halo")]).run;
  const idle = deriveChatView({ activeRun: null, activeId: SID });
  const streaming = deriveChatView({ activeRun: streamingRun, activeId: SID });
  const streamingWithTool = deriveChatView({
    activeRun: play([chunk("Halo"), ev("tool_start", { name: "ping" })]).run,
    activeId: SID,
  });
  const thinking = deriveChatView({ activeRun: createRun({ runId: RID }), activeId: SID });

  assert.equal(shouldShowLiveSteps(idle), false);
  assert.equal(shouldShowLiveSteps(thinking), true);
  assert.equal(shouldShowLiveSteps(streaming), false);
  assert.equal(shouldShowLiveSteps(streamingWithTool), true);
});

// ============================================================
// ALUR PENUH (end-to-end pada level state)
// ============================================================

test("alur penuh streaming: kirim -> thinking -> chunk -> response; animasi mulai, berhenti di chunk pertama, tidak restart, selesai", () => {
  const trace = [];
  const view = (state) => deriveChatView({ activeRun: state.run, activeId: SID });
  const record = (label, state) => {
    const v = view(state);
    trace.push([label, v.loading, v.phase, shouldShowLiveSteps(v)]);
  };

  let state = afterSend();
  record("kirim", state);

  state = reduceRunEvent(state, ev("ack"));
  record("ack", state);

  state = reduceRunEvent(state, ev("thinking", { message: "Menyusun jawaban..." }));
  record("thinking", state);

  state = reduceRunEvent(state, chunk("Ha"));
  record("chunk-1", state);
  const runAtFirstChunk = state.run;

  state = reduceRunEvent(state, chunk("lo"));
  state = reduceRunEvent(state, ev("thinking", { message: "Menyusun jawaban..." }));
  state = reduceRunEvent(state, chunk("!"));
  record("chunk-n", state);

  assert.equal(state.run, runAtFirstChunk, "run tidak berganti sesudah chunk pertama");

  state = reduceRunEvent(state, ev("response", { answer: "Halo!", steps: [], assistant_turn_id: 2 }));
  record("response", state);

  assert.deepEqual(trace, [
    ["kirim", true, PHASE_SENDING, true],
    ["ack", true, PHASE_ACK, true],
    ["thinking", true, "Menyusun jawaban...", true],
    ["chunk-1", true, "", false],
    ["chunk-n", true, "", false],
    ["response", false, "", false],
  ]);

  assert.equal(assistantMessages(state.messages).length, 1);
  assert.equal(state.messages[1].content, "Halo!");
});