/**
 * utils/deltaBatcher.js — StreamBatcher (Sprint 2.5 / Worker 3).
 *
 * Provider bisa mengirim puluhan `stream_delta` per detik. Menulis state React
 * untuk SETIAP chunk membuat seluruh UI render ulang puluhan kali per detik.
 * Batcher ini menampung event stream per sesi, lalu menyerahkannya SEKALIGUS
 * (dalam urutan yang sama) ke `apply(sessionId, events)` paling sering sekali
 * per `minIntervalMs`. Tidak ada teks yang digabung/dipotong di sini: event
 * tetap utuh dan diproses berurutan oleh reducer (utils/runLifecycle.js), jadi
 * batcher tidak bisa merusak urutan seq / call / attempt.
 *
 *   push(sid, event)   antre; jadwalkan flush kalau belum ada
 *   flush(sid)         serahkan SEKARANG semua event antrean sesi itu
 *                      (dipanggil sebelum event non-stream sesi tsb, supaya urutan terjaga)
 *   flushAll()         serahkan semua sesi
 *   discard(sid, run)  buang antrean sebuah run (mis. setelah Stop)
 *   cancel()           batalkan timer + kosongkan antrean
 *
 * Latensi: event pertama setelah jeda >= minIntervalMs diserahkan pada tick
 * berikutnya (hampir seketika); event yang datang rapat digabung ke satu tulis.
 *
 * Isolasi sesi: antrean per session_id; flush(sid) tidak menyentuh sesi lain.
 *
 * MURNI: jam & timer disuntik, jadi bisa diuji tanpa waktu nyata.
 */

export const DEFAULT_MIN_INTERVAL_MS = 32;

const defaultNow = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

export function createStreamBatcher({
  apply,
  minIntervalMs = DEFAULT_MIN_INTERVAL_MS,
  now = defaultNow,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (handle) => clearTimeout(handle),
} = {}) {
  if (typeof apply !== "function") {
    throw new TypeError("createStreamBatcher: 'apply' wajib berupa fungsi.");
  }

  const queues = new Map(); // sessionId -> event[]
  let timer = null;
  let lastFlushAt = -Infinity;

  function drain(sessionId) {
    const events = queues.get(sessionId);

    if (!events || events.length === 0) return 0;

    // Dikeluarkan dari antrean SEBELUM apply: kalau apply memicu push/flush
    // (re-entrant), event tidak diproses dua kali.
    queues.delete(sessionId);
    lastFlushAt = now();
    apply(sessionId, events);

    return events.length;
  }

  function flush(sessionId) {
    return drain(sessionId);
  }

  function flushAll() {
    let total = 0;
    let firstError = null;

    for (const sessionId of [...queues.keys()]) {
      try {
        total += drain(sessionId);
      } catch (error) {
        // Satu sesi bermasalah tidak boleh menahan sesi lain.
        if (firstError === null) firstError = error;
      }
    }

    if (firstError !== null) throw firstError;

    return total;
  }

  function onTimer() {
    timer = null;
    flushAll();
  }

  function push(sessionId, event) {
    if (!sessionId || !event) return;

    let queue = queues.get(sessionId);

    if (!queue) {
      queue = [];
      queues.set(sessionId, queue);
    }

    queue.push(event);

    if (timer === null) {
      timer = setTimer(onTimer, Math.max(0, lastFlushAt + minIntervalMs - now()));
    }
  }

  function discard(sessionId, runId) {
    const queue = queues.get(sessionId);

    if (!queue) return 0;

    const kept = queue.filter((event) => (event?.data?.run_id ?? null) !== runId);
    const removed = queue.length - kept.length;

    if (kept.length === 0) queues.delete(sessionId);
    else queues.set(sessionId, kept);

    return removed;
  }

  function cancel() {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }

    queues.clear();
  }

  function pending(sessionId) {
    if (sessionId === undefined) {
      let total = 0;
      for (const queue of queues.values()) total += queue.length;
      return total;
    }

    return queues.get(sessionId)?.length ?? 0;
  }

  return { push, flush, flushAll, discard, cancel, pending };
}
