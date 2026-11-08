import test from "node:test";
import assert from "node:assert/strict";
import {
  RUN_STATUS,
  createRun,
  deriveChatView,
  isStreamEvent,
  reduceRunEvent,
  reduceRunEvents,
  settleStreamingMessage,
} from "./runLifecycle.js";
import { IncrementalResponseParser } from "./streamParser.js";
import { createStreamBatcher } from "./deltaBatcher.js";

// ------------------------------------------------------------ fixtures
// SEMUA bentuk event backend hanya didefinisikan di sini. Kalau kontrak W2
// ternyata berbeda, cukup ubah tiga fungsi ini.

const start = (sid, run, call = 1, attempt = 1) => ({
  type: "stream_start",
  data: { session_id: sid, run_id: run, call, attempt, model: "m" },
});

const delta = (sid, run, seq, text, call = 1, attempt = 1) => ({
  type: "stream_delta",
  data: { session_id: sid, run_id: run, call, attempt, seq, text },
});

const response = (sid, run, answer, extra = {}) => ({
  type: "response",
  data: { session_id: sid, run_id: run, answer, steps: [], streamed: true, ...extra },
});

const session = (runId = "r1") => ({
  run: createRun({ runId }),
  messages: [{ role: "user", content: "halo" }],
});

const fold = (state, events, options) => reduceRunEvents(state, events, options);
const last = (state) => state.messages.at(-1);

// ============================================================
// 1-3. TEKS BIASA / STREAMING LIFECYCLE
// ============================================================

test("stream: thinking -> streaming pada teks pertama; pesan dibuat SEKALI lalu ditambah di tempat", () => {
  let state = session();

  state = fold(state, [start("s1", "r1")]);
  assert.equal(state.run.status, RUN_STATUS.THINKING);
  assert.equal(state.messages.length, 1); // belum ada bubble kosong

  state = fold(state, [delta("s1", "r1", 1, "Ha")]);
  assert.equal(state.run.status, RUN_STATUS.STREAMING);
  assert.equal(state.run.phase, "");
  assert.equal(state.messages.length, 2);
  assert.equal(last(state).streaming, true);
  assert.equal(last(state).content, "Ha");

  const bubble = last(state);
  state = fold(state, [delta("s1", "r1", 2, "lo "), delta("s1", "r1", 3, "dunia")]);

  assert.equal(state.messages.length, 2); // tidak ada bubble baru
  assert.equal(last(state).content, "Halo dunia");
  assert.notEqual(last(state), bubble); // immutable
});

test("stream: delta berikutnya tidak mengubah objek run (tidak memicu render ulang state run)", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "a")]);
  const run = state.run;

  state = fold(state, [delta("s1", "r1", 2, "b")]);

  assert.equal(state.run, run);
});

test("stream: fase tidak mundur ke thinking setelah teks pertama (ack/thinking terlambat)", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "teks")]);

  state = fold(state, [
    { type: "ack", data: { run_id: "r1" } },
    { type: "thinking", data: { run_id: "r1", message: "Berpikir..." } },
  ]);

  assert.equal(state.run.status, RUN_STATUS.STREAMING);
  assert.equal(state.run.phase, "");
});

test("stream: tool_start/tool_finish di tengah stream tetap tercatat, teks tidak terganggu", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "Cek dulu. ")]);

  state = fold(state, [
    { type: "tool_start", data: { run_id: "r1", name: "ping" } },
    { type: "tool_finish", data: { run_id: "r1", name: "ping", success: true } },
  ]);

  assert.deepEqual(state.run.liveTools.map((t) => [t.name, t.success]), [["ping", true]]);
  assert.equal(last(state).content, "Cek dulu. ");
});

// ============================================================
// SEQ / CALL / ATTEMPT
// ============================================================

test("seq: duplikat diabaikan, celah menghentikan penambahan (prefix tetap utuh), tidak ada teks berlubang", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "A"), delta("s1", "r1", 2, "B")]);

  state = fold(state, [delta("s1", "r1", 2, "B")]); // duplikat
  assert.equal(last(state).content, "AB");

  state = fold(state, [delta("s1", "r1", 4, "D")]); // celah (3 hilang)
  assert.equal(last(state).content, "AB");
  assert.equal(last(state).stream.desynced, true);

  state = fold(state, [delta("s1", "r1", 3, "C"), delta("s1", "r1", 5, "E")]);
  assert.equal(last(state).content, "AB"); // buffer ini sudah tidak dipercaya
});

test("seq: bergabung di tengah stream (socket tersambung ulang, seq>1) -> dilewati, tanpa bubble", () => {
  const state = fold(session(), [delta("s1", "r1", 7, "tengah")]);

  assert.equal(state.messages.length, 1);
  assert.equal(state.run.status, RUN_STATUS.THINKING);
});

test("multi-call: buffer call berikutnya MENGGANTIKAN teks call sebelumnya (reset malas, tanpa kedip)", () => {
  let state = fold(session(), [
    start("s1", "r1", 1, 1),
    delta("s1", "r1", 1, "Saya cek dulu ya.", 1, 1),
    { type: "tool_start", data: { run_id: "r1", name: "ping" } },
    { type: "tool_finish", data: { run_id: "r1", name: "ping", success: true } },
    start("s1", "r1", 2, 1),
  ]);

  // start call 2 sudah tiba, tapi teks lama tetap tampil sampai delta pertama call 2
  assert.equal(last(state).content, "Saya cek dulu ya.");
  assert.equal(state.messages.length, 2);

  state = fold(state, [delta("s1", "r1", 1, "Hasil: OK.", 2, 1), delta("s1", "r1", 2, " Latensi 4ms.", 2, 1)]);

  assert.equal(last(state).content, "Hasil: OK. Latensi 4ms.");
  assert.equal(state.messages.length, 2);
});

test("retry/fallback: attempt baru mengganti teks attempt gagal", () => {
  let state = fold(session(), [start("s1", "r1", 1, 1), delta("s1", "r1", 1, "Draf gagal", 1, 1)]);

  state = fold(state, [start("s1", "r1", 1, 2), delta("s1", "r1", 1, "Draf baik", 1, 2)]);

  assert.equal(last(state).content, "Draf baik");
});

test("delta buffer baru tanpa stream_start (start tak sempat terlihat) sah hanya kalau seq==1", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "lama", 1, 1)]);

  const ignored = fold(state, [delta("s1", "r1", 5, "salah", 2, 1)]);
  assert.equal(last(ignored).content, "lama");

  const accepted = fold(state, [delta("s1", "r1", 1, "baru", 2, 1)]);
  assert.equal(last(accepted).content, "baru");
});

test("alias lama response_chunk tetap bekerja (append biasa)", () => {
  const state = fold(session(), [
    { type: "response_chunk", data: { run_id: "r1", delta: "a" } },
    { type: "response_chunk", data: { run_id: "r1", delta: "b" } },
  ]);

  assert.equal(last(state).content, "ab");
  assert.equal(isStreamEvent("response_chunk"), true);
  assert.equal(isStreamEvent("response"), false);
});

// ============================================================
// 6. DIO (kontrak: hanya di `response`)
// ============================================================

test("DIO tidak lengkap: JSON schema setengah jadi di teks stream tidak mengubah state proses", () => {
  const partialSchema = 'Isi form: {"schema_id":"cek-router","fields":[{"name":"ip"';
  let state = fold(session(), [delta("s1", "r1", 1, partialSchema)]);

  assert.equal(last(state).content, partialSchema);
  assert.equal(last(state).interactionSchema, undefined);
  assert.equal(state.run.status, RUN_STATUS.STREAMING);
});

test("DIO lengkap: interaction_schema tiba di `response` dan ditempelkan ke bubble yang SAMA (tanpa bubble ganda)", () => {
  const schema = { schema_id: "cek-router", mode: "form", fields: [{ name: "ip", type: "text" }] };
  let state = fold(session(), [delta("s1", "r1", 1, "Isi form berikut:")]);
  const before = state.messages.length;

  state = fold(state, [response("s1", "r1", "Isi form berikut:", { interaction_schema: schema, assistant_turn_id: 7 })]);

  assert.equal(state.messages.length, before);
  assert.deepEqual(last(state).interactionSchema, schema);
  assert.equal(last(state).streaming, undefined);
  assert.equal(last(state).streamed, true);
  assert.equal(last(state).turnId, 7);
  assert.equal(state.run, null);
});

// ============================================================
// 12. COMPLETION
// ============================================================

test("selesai: response menggantikan teks stream dengan jawaban otoritatif di posisi yang sama", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "Draf")]);
  const index = state.messages.length - 1;

  state = fold(state, [response("s1", "r1", "Jawaban final.", { steps: [{ tool: "ping" }], user_turn_id: 3 })]);

  assert.equal(state.messages.length, index + 1);
  assert.equal(state.messages[index].content, "Jawaban final.");
  assert.deepEqual(state.messages[index].steps, [{ tool: "ping" }]);
  assert.equal(state.messages[0].turnId, 3);
  assert.equal(state.run, null);
});

test("selesai: delta yang datang sesudah response dibuang (tidak menghidupkan proses lagi)", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "a"), response("s1", "r1", "a")]);
  const snapshot = state;

  state = fold(state, [delta("s1", "r1", 2, "telat")]);

  assert.equal(state.run, null);
  assert.equal(state.messages, snapshot.messages);
});

// ============================================================
// 13. ERROR
// ============================================================

test("error non-fatal: proses & teks parsial tidak berubah; response yang menyusul menutup", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "Sebagian jawaban")]);
  const before = state;

  state = fold(state, [{ type: "error", data: { run_id: "r1", message: "provider timeout", fatal: false } }]);

  assert.equal(state.run, before.run);
  assert.equal(state.messages, before.messages);
  assert.equal(last(state).content, "Sebagian jawaban");

  state = fold(state, [response("s1", "r1", "Maaf, terjadi gangguan.")]);
  assert.equal(last(state).content, "Maaf, terjadi gangguan.");
  assert.equal(state.messages.length, before.messages.length);
});

test("error fatal: settleStreamingMessage mempertahankan teks parsial sebagai pesan lokal (bukan hilang, bukan streaming)", () => {
  const state = fold(session(), [delta("s1", "r1", 1, "Jawaban yang sempat tampil")]);
  const settled = settleStreamingMessage(state.messages, "r1");

  assert.equal(settled.at(-1).content, "Jawaban yang sempat tampil");
  assert.equal(settled.at(-1).streaming, false);
  assert.equal(settled.at(-1).local, true);
  assert.equal(settled.at(-1).stream, undefined);
  assert.equal(settled.length, state.messages.length);
});

test("error fatal: tanpa pesan streaming -> no-op (referensi sama)", () => {
  const messages = [{ role: "user", content: "x" }];

  assert.equal(settleStreamingMessage(messages, "r1"), messages);
});

// ============================================================
// 14. CANCELLATION
// ============================================================

test("cancel: teks parsial dipertahankan; delta susulan dari run yang di-Stop dibuang", () => {
  let state = fold(session(), [delta("s1", "r1", 1, "Parsial")]);
  const stale = new Set(["r1"]);

  state = { run: null, messages: settleStreamingMessage(state.messages, "r1") };
  const settled = state;

  state = fold(state, [delta("s1", "r1", 2, " susulan")], { staleRunIds: stale });

  assert.equal(state.messages, settled.messages);
  assert.equal(last(state).content, "Parsial");
  assert.equal(last(state).streaming, false);
});

test("cancel: run baru sesudah Stop tidak tercemar event run lama", () => {
  const stale = new Set(["old"]);
  let state = {
    run: createRun({ runId: "new" }),
    messages: [{ role: "assistant", content: "Parsial lama", streaming: false, local: true, runId: "old" }],
  };

  state = fold(state, [delta("s1", "old", 3, "hantu"), delta("s1", "new", 1, "Jawaban baru")], { staleRunIds: stale });

  assert.equal(state.messages[0].content, "Parsial lama");
  assert.equal(state.messages.at(-1).content, "Jawaban baru");
  assert.equal(state.messages.at(-1).runId, "new");
});

test("cancel: response run basi tetap ditampilkan (server sempat menyelesaikan & menyimpan)", () => {
  const stale = new Set(["r1"]);
  let state = { run: null, messages: settleStreamingMessage(fold(session(), [delta("s1", "r1", 1, "Par")]).messages, "r1") };

  state = fold(state, [response("s1", "r1", "Selesai juga")], { staleRunIds: stale });

  assert.equal(state.messages.filter((m) => m.role === "assistant").length, 1);
  assert.equal(last(state).content, "Selesai juga");
});

// ============================================================
// 15. SESSION ISOLATION (session_id + run_id)
// ============================================================

test("isolasi: event run lain pada sesi yang sama dibuang", () => {
  const state = fold(session("r1"), [delta("s1", "rX", 1, "bukan milik r1")]);

  assert.equal(state.messages.length, 1);
  assert.equal(state.run.status, RUN_STATUS.THINKING);
});

test("isolasi: dua sesi mengalir bersamaan lewat batcher tanpa saling bocor (state per sesi)", () => {
  const sessions = {
    A: session("rA"),
    B: session("rB"),
  };
  const applyCount = { A: 0, B: 0 };

  let timerFn = null;
  const batcher = createStreamBatcher({
    apply: (sid, events) => {
      applyCount[sid] += 1;
      sessions[sid] = reduceRunEvents(sessions[sid], events);
    },
    now: () => 0,
    setTimer: (fn) => { timerFn = fn; return 1; },
    clearTimer: () => { timerFn = null; },
  });

  // interleaved
  batcher.push("A", delta("A", "rA", 1, "alfa "));
  batcher.push("B", delta("B", "rB", 1, "bravo "));
  batcher.push("A", delta("A", "rA", 2, "satu"));
  batcher.push("B", delta("B", "rB", 2, "dua"));
  // event dengan run_id salah dikirim ke sesi yang salah -> dibuang reducer
  batcher.push("A", delta("B", "rB", 3, "SALAH"));

  timerFn();

  assert.equal(last(sessions.A).content, "alfa satu");
  assert.equal(last(sessions.B).content, "bravo dua");
  assert.equal(sessions.A.messages.length, 2);
  assert.equal(sessions.B.messages.length, 2);
  assert.deepEqual(applyCount, { A: 1, B: 1 });
});

test("isolasi: response sesi A tidak menyentuh state sesi B, dan view loading/streaming per sesi", () => {
  let a = fold(session("rA"), [delta("A", "rA", 1, "a")]);
  const b = fold(session("rB"), [delta("B", "rB", 1, "b")]);

  a = fold(a, [response("A", "rA", "a-final")]);

  assert.equal(a.run, null);
  assert.equal(deriveChatView({ activeRun: a.run }).loading, false);
  assert.equal(deriveChatView({ activeRun: b.run }).loading, true);
  assert.equal(deriveChatView({ activeRun: b.run }).streaming, true);
  assert.equal(last(b).content, "b");
});

// ============================================================
// 16. NON-STREAMING
// ============================================================

test("non-streaming: hanya `response` (tanpa stream_*) -> satu bubble final, tanpa flag streamed", () => {
  let state = session();

  state = fold(state, [
    { type: "ack", data: { run_id: "r1" } },
    { type: "thinking", data: { run_id: "r1", message: "Berpikir..." } },
    { type: "response", data: { session_id: "s1", run_id: "r1", answer: "Jawaban utuh", steps: [], streamed: false } },
  ]);

  assert.equal(state.messages.length, 2);
  assert.equal(last(state).content, "Jawaban utuh");
  assert.equal(last(state).streamed, undefined);
  assert.equal(state.run, null);
});

test("non-streaming: response tanpa run aktif (mis. voice / reload) tetap ditambahkan", () => {
  const state = reduceRunEvent({ run: null, messages: [] }, response("s1", "rZ", "Halo"));

  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].content, "Halo");
});

// ============================================================
// END-TO-END: reducer -> parser (teks di layar == teks final)
// ============================================================

test("e2e: teks hasil reducer diberi ke parser di tiap batch; SVG tidak pernah bocor setengah jadi; final == non-streaming", () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>';
  const answer = `Topologi:\n\n\`\`\`svg\n${svg}\n\`\`\`\n\nLihat ![foto](https://x.test/f.jpg) dan selesai.`;
  const parser = new IncrementalResponseParser();
  const events = [];
  let seq = 0;

  for (let i = 0; i < answer.length; i += 7) events.push(delta("s1", "r1", ++seq, answer.slice(i, i + 7)));

  let state = session();

  for (let i = 0; i < events.length; i += 3) {
    state = fold(state, events.slice(i, i + 3)); // batch 3 event
    const snap = parser.sync(last(state).content);
    const visible = [...snap.blocks.map((b) => b.source), snap.tail?.source ?? ""].join("\n");

    if (visible.includes("<svg")) assert.ok(visible.includes("</svg>"));
    for (const m of visible.matchAll(/!\[[^\]]*\]/g)) {
      assert.match(visible.slice(m.index), /^!\[[^\]]*\]\([^)]*\)/);
    }
  }

  assert.equal(last(state).content, answer);

  state = fold(state, [response("s1", "r1", answer)]);
  const streamedFinal = new IncrementalResponseParser().sync(answer, { final: true });
  const nonStreaming = new IncrementalResponseParser().sync(state.messages.at(-1).content, { final: true });

  assert.deepEqual(streamedFinal, nonStreaming);
  assert.equal(streamedFinal.blocks.filter((b) => b.kind === "svg").length, 1);
});
