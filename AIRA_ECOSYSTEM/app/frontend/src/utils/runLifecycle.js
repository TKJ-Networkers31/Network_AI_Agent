/**
 * utils/runLifecycle.js — transisi state SATU proses chat di frontend.
 *
 *   kirim -> thinking -> (chunk pertama) streaming -> response | error | cancel
 *
 * BUKAN sistem loading baru. State-nya tetap `runsBySession` di
 * ChatRuntimeContext (satu entri = satu proses berjalan) dan pesannya tetap
 * `messagesBySession`. File ini hanya memindahkan aturan transisi yang
 * sebelumnya tertanam di handleEvent() ke fungsi murni (tanpa React, tanpa
 * I/O) supaya bisa diuji dengan `node --test`, sambil menambah fase
 * "streaming". Animasi thinking (LiveSteps/ThinkingBubble) tidak disentuh.
 *
 * Bentuk `run`:
 *   { runId, status: "thinking" | "streaming", phase, liveTools }
 *
 * Aturan yang dijaga:
 *   1. Streaming MONOTONIK: setelah chunk pertama, event thinking/ack susulan
 *      tidak mengembalikan fase thinking (animasi tidak restart). Chunk
 *      berikutnya mengembalikan objek run yang SAMA (tanpa re-render).
 *   2. Pesan streaming dibuat SEKALI di chunk pertama, ditambah di tempat, dan
 *      pada `response` DIGANTI di posisi yang sama (bukan di-push) - key
 *      bubble di ChatPage berbasis index, jadi tidak ada remount/animasi
 *      reveal ulang dan tidak ada bubble ganda.
 *   3. Isi pesan tidak pernah diperiksa di sini: potongan yang memuat fence
 *      ```svg, gambar Markdown, atau jawaban ber-interaction_schema (DIO)
 *      tidak mengubah state proses. Payload `response` adalah sumber
 *      kebenaran akhir (answer, steps, interaction_schema, turn id).
 *   4. Event dari run basi (sudah di-Stop) atau run lain dibuang; chunk yang
 *      datang saat tidak ada run (mis. sesudah response) juga dibuang.
 *   5. Error NON-fatal tidak mengakhiri proses: server SELALU mengirim
 *      `response` sesudahnya (api/routers/ws.py). Error fatal butuh snapshot
 *      rollback, jadi tetap ditangani failRun() di context.
 *
 * Kontrak event streaming (frontend siap menerima):
 *   { type: "response_chunk", data: { session_id, run_id, delta: "<teks>" } }
 * CATATAN: backend BELUM mengirim event ini (provider_client memakai
 * stream=false). Tanpa event ini alur tetap berjalan: thinking -> response.
 */

export const RUN_STATUS = Object.freeze({
  THINKING: "thinking",
  STREAMING: "streaming",
});

export const EVENT_RESPONSE_CHUNK = "response_chunk";

export const PHASE_SENDING = "Mengirim...";
export const PHASE_ACK = "Menganalisis permintaan...";
export const PHASE_REGENERATING = "Membuat ulang jawaban...";
const PHASE_FALLBACK = "Berpikir...";

const NO_TOOLS = Object.freeze([]);

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

/** Chunk pertama: thinking -> streaming (fase dikosongkan). Berikutnya: objek sama. */
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

/** Tambah potongan ke pesan streaming milik run ini (dibuat di chunk pertama). */
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

/**
 * Proses berakhir sebelum response (Stop / cancelled / error fatal): pesan
 * streaming yang sudah tampil dipertahankan sebagai pesan LOKAL (belum
 * tersimpan di server), tidak lagi streaming. No-op kalau tidak ada.
 */
export function settleStreamingMessage(messages, runId) {
  const idx = findRunMessageIndex(messages, runId, { streamingOnly: true });

  if (idx === -1) return messages;

  const next = messages.slice();
  next[idx] = { ...messages[idx], streaming: false, local: true };

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

  const final = {
    role: "assistant",
    content: data.answer,
    steps: data.steps,
    interactionSchema: data.interaction_schema || null,
    turnId: data.assistant_turn_id ?? null,
    isNew: true,
    runId: data.run_id ?? null,
  };

  const idx = findRunMessageIndex(next, data.run_id);

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
 * Yang ditangani: ack, thinking, tool_start, tool_finish, response_chunk,
 * response, error non-fatal. Selebihnya (transcript, cancelled, error fatal,
 * efek samping unread/voice/snapshot) tetap di ChatRuntimeContext.
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

    case EVENT_RESPONSE_CHUNK: {
      if (!run || skip) return same;
      if (typeof data.delta !== "string" || data.delta === "") return same;

      return {
        run: applyChunkToRun(run),
        messages: appendChunk(messages, data.run_id || run.runId, data.delta),
      };
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