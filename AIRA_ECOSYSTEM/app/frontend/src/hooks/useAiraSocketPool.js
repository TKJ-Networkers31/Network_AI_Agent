import { useCallback, useEffect, useRef, useState } from "react";

// hooks/useAiraSocketPool.js  (FILE BARU - menggantikan useAiraSocket.js
// HANYA untuk ChatRuntimeContext; file lama tidak dihapus/diubah.)
//
// KENAPA ADA: useAiraSocket.js hanya memegang SATU socket milik sesi
// yang sedang aktif. Begitu user pindah sesi, socket sesi lama DITUTUP
// (cleanup effect) - padahal server masih memproses prompt sesi itu.
// Akibatnya balasan/event-nya tidak pernah sampai ke client, dan state
// "loading" yang global ikut nyangkut di sesi lain.
//
// Pool ini menjaga satu socket per sesi yang DIBUTUHKAN:
//   - sesi aktif (activeId), dan
//   - sesi yang punya proses berjalan (keepAliveIds)
// Socket sesi yang tidak lagi dibutuhkan ditutup otomatis. Auto-reconnect
// (exponential backoff) berlaku per socket, sama seperti hook lama.

const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 1000;

function buildWsUrl(sessionId) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  return `${proto}//${host}/ws/chat/${encodeURIComponent(sessionId)}`;
}

export function useAiraSocketPool({ activeId, keepAliveIds = [], onEvent } = {}) {
  // status per sesi: "connecting" | "open" | "closed" (tidak ada = idle)
  const [statusById, setStatusById] = useState({});
  const entriesRef = useRef(new Map()); // sid -> { ws, retry, timer, closedByUser }
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const setStatus = useCallback((sid, status) => {
    setStatusById((prev) => (prev[sid] === status ? prev : { ...prev, [sid]: status }));
  }, []);

  const connectEntry = useCallback(
    (sid) => {
      const entry = entriesRef.current.get(sid);
      if (!entry || entry.closedByUser) return;

      const existing = entry.ws;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      setStatus(sid, "connecting");
      const ws = new WebSocket(buildWsUrl(sid));
      entry.ws = ws;

      ws.onopen = () => {
        if (entry.ws !== ws) return;
        entry.retry = 0;
        setStatus(sid, "open");
      };

      ws.onmessage = (event) => {
        if (entry.ws !== ws) return;
        try {
          const parsed = JSON.parse(event.data);
          onEventRef.current?.(parsed);
        } catch {
          // abaikan payload non-JSON
        }
      };

      ws.onclose = () => {
        if (entry.ws !== ws) return;

        setStatus(sid, "closed");
        if (entry.closedByUser) return;

        const delay = Math.min(BASE_BACKOFF_MS * 2 ** entry.retry, MAX_BACKOFF_MS);
        entry.retry += 1;

        clearTimeout(entry.timer);
        entry.timer = setTimeout(() => {
          entry.timer = null;
          connectEntry(sid);
        }, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    },
    [setStatus]
  );

  const closeEntry = useCallback((sid) => {
    const entry = entriesRef.current.get(sid);
    if (!entry) return;

    entry.closedByUser = true;
    clearTimeout(entry.timer);

    const ws = entry.ws;
    if (ws) {
      ws.onclose = null;
      ws.onmessage = null;
      ws.onerror = null;
      try {
        ws.close();
      } catch {
        // abaikan
      }
    }

    entriesRef.current.delete(sid);

    setStatusById((prev) => {
      if (!(sid in prev)) return prev;
      const next = { ...prev };
      delete next[sid];
      return next;
    });
  }, []);

  // Sinkronkan daftar socket dengan daftar sesi yang dibutuhkan.
  const keepKey = [...(keepAliveIds || [])].sort().join(",");

  useEffect(() => {
    const wanted = new Set(keepKey ? keepKey.split(",") : []);
    if (activeId) wanted.add(activeId);

    wanted.forEach((sid) => {
      if (!entriesRef.current.has(sid)) {
        entriesRef.current.set(sid, { ws: null, retry: 0, timer: null, closedByUser: false });
      }
      connectEntry(sid); // no-op kalau sudah OPEN/CONNECTING
    });

    [...entriesRef.current.keys()].forEach((sid) => {
      if (!wanted.has(sid)) closeEntry(sid);
    });
  }, [activeId, keepKey, connectEntry, closeEntry]);

  // Tutup semua socket saat provider di-unmount.
  useEffect(() => {
    return () => {
      [...entriesRef.current.keys()].forEach((sid) => closeEntry(sid));
    };
  }, [closeEntry]);

  const isOpenFor = useCallback((sid) => {
    const ws = sid ? entriesRef.current.get(sid)?.ws : null;
    return Boolean(ws && ws.readyState === WebSocket.OPEN);
  }, []);

  const sendTo = useCallback((sid, payload) => {
    const ws = sid ? entriesRef.current.get(sid)?.ws : null;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  const waitUntilOpen = useCallback(
    (sid, timeoutMs = 8000) =>
      new Promise((resolve, reject) => {
        if (isOpenFor(sid)) {
          resolve();
          return;
        }

        const startedAt = Date.now();

        const interval = setInterval(() => {
          if (isOpenFor(sid)) {
            clearInterval(interval);
            resolve();
          } else if (Date.now() - startedAt > timeoutMs) {
            clearInterval(interval);
            reject(new Error("Waktu menyambungkan ke server habis. Coba lagi."));
          }
        }, 100);
      }),
    [isOpenFor]
  );

  return { statusById, sendTo, waitUntilOpen, isOpenFor };
}
