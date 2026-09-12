import { useCallback, useEffect, useRef, useState } from "react";

const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 1000;

function buildWsUrl(sessionId) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  return `${proto}//${host}/ws/chat/${encodeURIComponent(sessionId)}`;
}

/**
 * Hook WebSocket AIRA — auto-reconnect (exponential backoff).
 * sessionId=null berarti "belum ada sesi" (chat baru) - hook tidak
 * connect sampai sessionId tersedia. status yang dikembalikan:
 * "idle" | "connecting" | "open" | "closed" - dipakai TopBar untuk
 * menampilkan badge Live/Menyambung/Terputus/Offline.
 */
export function useAiraSocket(sessionId, { onEvent } = {}) {
  const [status, setStatus] = useState("idle");
  const wsRef = useRef(null);
  const retryRef = useRef(0);
  const closedByUserRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (existing) {
      existing.onclose = null;
      existing.onmessage = null;
      existing.onerror = null;
      try {
        existing.close();
      } catch {
        // abaikan
      }
    }

    setStatus("connecting");
    const ws = new WebSocket(buildWsUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      retryRef.current = 0;
      setStatus("open");
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;
      try {
        const parsed = JSON.parse(event.data);
        onEventRef.current?.(parsed);
      } catch {
        // abaikan payload non-JSON
      }
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;

      setStatus("closed");
      if (closedByUserRef.current) return;

      const delay = Math.min(BASE_BACKOFF_MS * 2 ** retryRef.current, MAX_BACKOFF_MS);
      retryRef.current += 1;

      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sessionId, clearReconnectTimer]);

  useEffect(() => {
    closedByUserRef.current = false;
    retryRef.current = 0;

    if (sessionId) {
      connect();
    } else {
      setStatus("idle");
    }

    return () => {
      closedByUserRef.current = true;
      clearReconnectTimer();

      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null;
        ws.onmessage = null;
        ws.onerror = null;
        try {
          ws.close();
        } catch {
          // abaikan
        }
        wsRef.current = null;
      }
      setStatus("idle");
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