/**
 * utils/runLifecycle.js — transisi state SATU proses chat di frontend.
 *
 *   kirim -> thinking -> (teks pertama) streaming -> response | error | cancel
 *
 * BUKAN sistem loading baru. State-nya tetap `runsBySession` di
 * ChatRuntimeContext (satu entri = satu proses berjalan) dan pesannya tetap
 * `messagesBySession`. File ini hanya memindahkan aturan transisi yang
 * sebelumnya tertanam di handleEvent() ke fungsi murni (tanpa React, tanpa
 * I/O) supaya bisa diuji dengan `node --test`.
 *
 * Bentuk `run`:
 *   { runId, status: "thinking" | "streaming", phase, liveTools }
 *
 * KONTRAK STREAMING AKTUAL (backend Sprint 2.5, api/ws_bridge.py +
 * docs/api_guideline.md) - dibaca dari implementasi, bukan ditebak:
 *
 *   { type: "stream_start", data: { session_id, run_id, call, attempt, model } }
 *   { type: "stream_delta", data: { session_id, run_id, call, attempt, seq, text } }
 *   { type: "response",     data: { answer, steps, streamed, ... } }   <- COMPLETE, otoritatif
 *
 *   - `stream_start` membuka buffer teks BARU untuk pasangan (call, attempt):
 *     tiap request ke provider (juga retry / fallback / panggilan LLM sesudah
 *     tool) mengirimnya lagi. Reset dilakukan MALAS: teks lama tetap tampil
 *     sampai potongan pertama buffer baru tiba (tidak ada bubble kosong/kedip).
 *   - `stream_delta.seq` dimulai dari 1 dan tanpa celah dalam satu (call, attempt).
 *     Reducer HANYA menerima seq berikutnya yang persis: duplikat diabaikan, dan
 *     kalau ada celah / kita bergabung di tengah stream (mis. socket tersambung
 *     ulang) buffer itu ditandai `desynced` dan tidak ditambah lagi - teks di layar
 *     selalu prefix yang utuh, tidak pernah berlubang. `response` yang menutup.
 *   - Satu giliran bisa berisi beberapa `call` (LLM -> tool -> LLM). Teks call
 *     yang berujung tool hanya pengantar; buffer call berikutnya menggantikannya.
 *   - Tidak ada event stream untuk jawaban non-streaming: `response` saja sudah cukup.
 *   - `interaction_schema` (DIO) dan hasil tool tidak ada di event stream; keduanya
 *     hanya datang di `response`.
 *
 * `response_chunk` {delta} adalah nama placeholder lama sebelum backend selesai;
 * tetap diterima sebagai alias tanpa pemeriksaan seq/call (append biasa).
 *
 * Aturan yang dijaga:
 *   1. Streaming MONOTONIK: setelah teks pertama, event thinking/ack susulan
 *      tidak mengembalikan fase thinking (animasi tidak restart). Delta berikutnya
 *      mengembalikan objek run yang SAMA (tanpa re-render).
 *   2. Pesan streaming dibuat SEKALI di teks pertama, ditambah di tempat, dan
 *      pada `response` DIGANTI di posisi yang sama (bukan di-push) - key bubble di
 *      ChatPage berbasis index, jadi tidak ada remount/animasi reveal ulang dan
 *      tidak ada bubble ganda. Pesan final yang berasal dari stream diberi
 *      `streamed: true` supaya renderer bertahap tidak di-unmount saat finalize.
 *   3. Isi pesan tidak pernah diperiksa di sini: potongan yang memuat fence
 *      ```svg, gambar Markdown, atau jawaban ber-interaction_schema (DIO) tidak
 *      mengubah state proses. Payload `response` adalah sumber kebenaran akhir.
 *   4. Event dari run basi (sudah di-Stop) atau run lain dibuang; delta yang
 *      datang saat tidak ada run (mis. sesudah response) juga dibuang.
 *   5. Error NON-fatal tidak mengakhiri proses: server SELALU mengirim
 *      `response` sesudahnya (api/routers/ws.py). Error fatal butuh snapshot
 *      rollback, jadi tetap ditangani failRun() di context.
 */

export const RUN_STATUS = Object.freeze({
  THINKING: "thinking",
  STREAMING: "streaming",
});

export const EVENT_STREAM_START = "stream_start";
export const EVENT_STREAM_DELTA = "stream_delta";
export const EVENT_RESPONSE_CHUNK = "response_chunk"; // alias lama (placeholder)

export const PHASE_SENDING = "Mengirim...";
export const PHASE_ACK = "Menganalisis permintaan...";
export const PHASE_REGENERATING = "Membuat ulang jawaban...";
const PHASE_FALLBACK = "Berpikir...";

const NO_TOOLS = Object.freeze([]);

/** Event yang boleh ditampung batcher (stream_start / stream_delta / alias lama). */
export function isStreamEvent(type) {
  return type === EVENT_STREAM_START || type === EVENT_STREAM_DELTA || type === EVENT_RESPONSE_CHUNK;
}

// ============================================================
// RUN
// ============================================================

export function createRun({ runId = null, phase = PHASE_SENDING } = {}) {
  return { runId, status: RUN_STATUS.THINKING, phase, liveTools: [] };
}

export function isStreaming(run) {
  return Boolean(run) && run.status === RUN_STATUS.STREAMING;
}

/**
 * Event dianggap basi kalau run_id-nya sudah di-Stop user, dan "run lain"
 * kalau run aktif di sesi ini punya run_id berbeda.
 */
export function classifyRunEvent(run, data = {}, staleRunIds = null) {
  const runId = data.run_id;

  return {
    isStale: Boolean(runId && staleRunIds && staleRunIds.has(runId)),
    isOtherRun: Boolean(run && run.runId && runId && run.runId !== runId),
  };
}

export function applyAck(run, runId) {
  if (!run) {
    // Giliran suara tidak punya run dari client -> adopsi dari server.
    return createRun({ runId: runId || null, phase: PHASE_ACK });
  }

  const nextRunId = runId || run.runId || null;
  const phase = isStreaming(run) ? run.phase : PHASE_ACK;

  if (nextRunId === run.runId && phase === run.phase) return run;

  // liveTools/status TIDAK direset: ack yang datang terlambat tidak boleh
  // menghapus kartu tool atau memundurkan fase streaming.
  return { ...run, runId: nextRunId, phase };
}

export function applyThinking(run, message) {
  if (!run || isStreaming(run)) return run;

  const phase = message || PHASE_FALLBACK;

  return phase === run.phase ? run : { ...run, phase };
}

export function applyToolStart(run, data) {
  if (!run) return run;

  return { ...run, liveTools: [...run.liveTools, { ...data, success: null }] };
}

export function applyToolFinish(run, data) {
  if (!run) return run;

  // update entri "success: null" TERAKHIR dengan nama yang sama
  const tools = run.liveTools;
  let idx = -1;

  for (let i = tools.length - 1; i >= 0; i -= 1) {
    if (tools[i].name === data.name && tools[i].success === null) {
      idx = i;
      break;
    }
  }

  if (idx === -1) return run;

  const nextTools = [...tools];
  nextTools[idx] = { ...nextTools[idx], ...data };

  return { ...run, liveTools: nextTools };
}

/** Teks pertama: thinking -> streaming (fase dikosongkan). Berikutnya: objek sama. */
export function applyChunkToRun(run) {
  if (!run || isStreaming(run)) return run;

  return { ...run, status: RUN_STATUS.STREAMING, phase: "" };
}

// ============================================================
// MESSAGES
// ============================================================

// Tanpa runId (event tanpa run_id) hanya mode streamingOnly yang bisa cocok:
// pesan streaming terakhir. Itu aman karena hanya ada satu run per sesi.
function findRunMessageIndex(messages, runId, { streamingOnly = false } = {}) {
  if (!runId && !streamingOnly) return -1;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];

    if (m.role !== "assistant") continue;
    if (streamingOnly && !m.streaming) continue;
    if (runId && m.runId !== runId) continue;

    return i;
  }

  return -1;
}

/** Tambah potongan ke pesan streaming milik run ini (dibuat di potongan pertama). Jalur alias lama. */
export function appendChunk(messages, runId, delta) {
  if (typeof delta !== "string" || delta === "") return messages;

  const idx = findRunMessageIndex(messages, runId, { streamingOnly: true });

  if (idx === -1) {
    return [
      ...messages,
      {
        role: "assistant",
        content: delta,
        steps: [],
        streaming: true,
        runId: runId || null,
        isNew: true,
      },
    ];
  }

  const next = messages.slice();
  next[idx] = { ...messages[idx], content: `${messages[idx].content || ""}${delta}` };

  return next;
}

function streamKeyOf(data) {
  const { call, attempt } = data || {};

  return Number.isInteger(call) && Number.isInteger(attempt) ? `${call}:${attempt}` : null;
}

/**
 * `stream_start`: buffer baru untuk (call, attempt). Reset MALAS - teks lama
 * tetap tampil sampai delta pertama buffer baru tiba. Tanpa pesan streaming
 * (belum ada teks sama sekali) tidak ada yang perlu dilakukan; delta pertama
 * membawa key-nya sendiri.
 */
export function applyStreamStart(messages, runId, data) {
  const key = streamKeyOf(data);

  if (key === null) return messages;

  const idx = findRunMessageIndex(messages, runId, { streamingOnly: true });

  if (idx === -1) return messages;

  const current = messages[idx];

  if (current.stream && current.stream.key === key) return messages; // start ganda

  const next = messages.slice();
  next[idx] = { ...current, stream: { key, seq: 0, reset: true, desynced: false } };

  return next;
}

/**
 * `stream_delta`: tambah teks HANYA kalau seq-nya persis berikutnya. Yang lain
 * diabaikan (messages yang sama dikembalikan) supaya teks di layar tidak
 * pernah berlubang / terduplikasi. Delta tanpa call/attempt/seq (alias lama)
 * jatuh ke appendChunk().
 */
export function applyStreamDelta(messages, runId, { text, call, attempt, seq } = {}) {
  if (typeof text !== "string" || text === "") return messages;

  const key = streamKeyOf({ call, attempt });

  if (key === null || !Number.isInteger(seq)) return appendChunk(messages, runId, text);

  const idx = findRunMessageIndex(messages, runId, { streamingOnly: true });

  if (idx === -1) {
    // Bergabung di tengah stream (seq > 1): lewatkan; jangan tampilkan teks tanpa awalnya.
    if (seq !== 1) return messages;

    return [
      ...messages,
      {
        role: "assistant",
        content: text,
        steps: [],
        streaming: true,
        runId: runId || null,
        isNew: true,
        stream: { key, seq, reset: false, desynced: false },
      },
    ];
  }

  const current = messages[idx];
  const state = current.stream;
  let content;
  let nextState;

  if (!state || state.key !== key) {
    // Buffer baru yang start-nya tidak sempat terlihat: sah hanya kalau ini potongan pertamanya.
    if (seq !== 1) return messages;

    content = text;
    nextState = { key, seq, reset: false, desynced: false };
  } else if (state.desynced || seq <= state.seq) {
    return messages;
  } else if (seq !== state.seq + 1) {
    // Celah: berhenti menambah teks buffer ini (prefix yang tampil tetap utuh).
    const next = messages.slice();
    next[idx] = { ...current, stream: { ...state, desynced: true } };

    return next;
  } else {
    content = state.reset ? text : `${current.content || ""}${text}`;
    nextState = { key, seq, reset: false, desynced: false };
  }

  const next = messages.slice();
  next[idx] = { ...current, content, stream: nextState };

  return next;
}

/**
 * Proses berakhir sebelum response (Stop / cancelled / error fatal): pesan
 * streaming yang sudah tampil dipertahankan sebagai pesan LOKAL (belum
 * tersimpan di server), tidak lagi streaming. No-op kalau tidak ada.
 */
export function settleStreamingMessage(messages, runId) {
  const idx = findRunMessageIndex(messages, runId, { streamingOnly: true });

  if (idx === -1) return messages;

  const { stream: _stream, ...rest } = messages[idx];
  const next = messages.slice();
  next[idx] = { ...rest, streaming: false, local: true };

  return next;
}

/**
 * Payload `response` -> daftar pesan. Pesan milik run yang sama (streaming
 * atau yang sudah di-settle) DIGANTI di tempat; kalau tidak ada, di-push.
 * Bubble user terakhir yang belum punya id server ikut diberi id.
 */
export function applyResponse(messages, data) {
  const next = [...messages];

  if (data.user_turn_id != null) {
    for (let i = next.length - 1; i >= 0; i -= 1) {
      if (next[i].role === "user" && !next[i].local) {
        if (next[i].turnId == null) {
          next[i] = { ...next[i], turnId: data.user_turn_id };
        }
        break;
      }
    }
  }

  const idx = findRunMessageIndex(next, data.run_id);
  const replaced = idx === -1 ? null : next[idx];

  const final = {
    role: "assistant",
    content: data.answer,
    steps: data.steps,
    interactionSchema: data.interaction_schema || null,
    turnId: data.assistant_turn_id ?? null,
    isNew: true,
    runId: data.run_id ?? null,
    // Berasal dari stream: renderer bertahap tetap terpasang (tanpa remount/kedip).
    ...(replaced && replaced.streaming !== undefined ? { streamed: true } : {}),
  };

  if (idx === -1) next.push(final);
  else next[idx] = final;

  return next;
}

// ============================================================
// REDUCER (satu sesi: { run, messages })
// ============================================================

/**
 * Event WebSocket -> { run, messages } baru. Tidak pernah memutasi input;
 * referensi run/messages yang TIDAK berubah dikembalikan apa adanya, jadi
 * pemanggil cukup membandingkan dengan `!==` untuk tahu apa yang perlu
 * ditulis ke state.
 *
 * Yang ditangani: ack, thinking, tool_start, tool_finish, stream_start,
 * stream_delta (+ alias response_chunk), response, error non-fatal.
 * Selebihnya (transcript, cancelled, error fatal, efek samping
 * unread/voice/snapshot) tetap di ChatRuntimeContext.
 */
export function reduceRunEvent(session, event, { staleRunIds = null } = {}) {
  const run = (session && session.run) || null;
  const messages = (session && session.messages) || [];
  const same = { run, messages };

  const { type, data = {} } = event || {};
  const { isStale, isOtherRun } = classifyRunEvent(run, data, staleRunIds);
  const skip = isStale || isOtherRun;

  switch (type) {
    case "ack":
      if (skip) return same;
      return { run: applyAck(run, data.run_id), messages };

    case "thinking":
      if (!run || skip) return same;
      return { run: applyThinking(run, data.message), messages };

    case "tool_start":
      if (!run || skip) return same;
      return { run: applyToolStart(run, data), messages };

    case "tool_finish":
      if (!run || skip) return same;
      return { run: applyToolFinish(run, data), messages };

    case EVENT_STREAM_START: {
      if (!run || skip) return same;

      const nextMessages = applyStreamStart(messages, data.run_id || run.runId, data);

      return nextMessages === messages ? same : { run, messages: nextMessages };
    }

    case EVENT_STREAM_DELTA:
    case EVENT_RESPONSE_CHUNK: {
      if (!run || skip) return same;

      const text = type === EVENT_RESPONSE_CHUNK ? data.delta : data.text;

      if (typeof text !== "string" || text === "") return same;

      const nextMessages = applyStreamDelta(messages, data.run_id || run.runId, {
        text,
        call: data.call,
        attempt: data.attempt,
        seq: data.seq,
      });

      // Diabaikan (duplikat / celah / bergabung di tengah): tidak ada teks baru,
      // jadi fase thinking juga tidak berubah.
      if (nextMessages === messages) return same;

      return { run: applyChunkToRun(run), messages: nextMessages };
    }

    case "response":
      // Selalu ditampilkan (termasuk run basi): kalau server sempat
      // menyelesaikan giliran sebelum Stop terbaca, hasilnya SUDAH tersimpan.
      return {
        run: isOtherRun ? run : null,
        messages: applyResponse(messages, data),
      };

    case "error":
      // Non-fatal: `response` menyusul dan membawa teks error-nya, jadi
      // proses (dan animasinya) berjalan sampai response. Fatal ditangani
      // failRun() di context karena butuh snapshot rollback.
      return same;

    default:
      return same;
  }
}

/**
 * Lipat beberapa event (satu batch dari StreamBatcher) menjadi SATU hasil,
 * supaya pemanggil menulis state React sekali, bukan sekali per event.
 */
export function reduceRunEvents(session, events, options) {
  let state = { run: (session && session.run) || null, messages: (session && session.messages) || [] };

  for (const event of events || []) {
    state = reduceRunEvent(state, event, options);
  }

  return state;
}

// ============================================================
// VIEW (nilai turunan untuk ChatPage)
// ============================================================

/**
 * `creatingSession`: New Chat sedang membuat sesi di server sebelum run
 * pertama ada. Selama itu (dan belum ada activeId) UI sudah menampilkan
 * "Mengirim..." dan input terkunci - tanpa ini tidak ada umpan balik sama
 * sekali antara tombol kirim dan run pertama.
 */
export function deriveChatView({ activeRun = null, creatingSession = false, activeId = null } = {}) {
  const pendingNewSession = Boolean(creatingSession && !activeId && !activeRun);

  return {
    loading: Boolean(activeRun) || pendingNewSession,
    streaming: isStreaming(activeRun),
    phase: activeRun ? activeRun.phase || "" : pendingNewSession ? PHASE_SENDING : "",
    liveTools: activeRun ? activeRun.liveTools : NO_TOOLS,
  };
}

/** LiveSteps hanya dirender kalau ada isinya (tanpa wadah kosong yang menambah jarak). */
export function shouldShowLiveSteps({ loading, phase, liveTools }) {
  return Boolean(loading) && (Boolean(phase) || (liveTools || []).length > 0);
}
