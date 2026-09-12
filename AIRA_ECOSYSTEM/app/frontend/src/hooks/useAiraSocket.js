import { useCallback, useEffect, useRef, useState } from "react";

const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 1000;

function buildWsUrl(sessionId) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Dev: Vite proxy tidak meng-cover WS secara default, jadi arahkan
  // langsung ke backend port 8000 saat dev; di production (di-serve
  // dari FastAPI StaticFiles yang sama), origin sama persis.
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  return `${proto}//${host}/ws/chat/${encodeURIComponent(sessionId)}`;
}

/**
 * Hook WebSocket AIRA — auto-reconnect (exponential backoff), tanpa
 * mengubah alur REST yang sudah ada. sessionId=null berarti "belum ada
 * sesi" (chat baru) - hook tidak connect sampai sessionId tersedia.
 */
export function useAiraSocket(sessionId, { onEvent } = {}) {
  const [status, setStatus] = useState("idle"); // idle | connecting | open | closed
  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const closedByUserRef = useRef(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    if (!sessionId) return;

    setStatus("connecting");
    const ws = new WebSocket(buildWsUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setStatus("open");
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        onEventRef.current?.(parsed);
      } catch {
        // abaikan payload non-JSON
      }
    };

    ws.onclose = () => {
      setStatus("closed");
      if (closedByUserRef.current) return;

      const delay = Math.min(BASE_BACKOFF_MS * 2 ** retryRef.current, MAX_BACKOFF_MS);
      retryRef.current += 1;
      setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sessionId]);

  useEffect(() => {
    closedByUserRef.current = false;

    if (sessionId) {
      connect();
    }

    return () => {
      closedByUserRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const send = useCallback((message) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ message }));
    return true;
  }, []);

  return { status, send, isOpen: status === "open" };
}