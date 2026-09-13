import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api } from "../api.js";
import { useSessionsContext } from "./SessionsContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useAiraSocket } from "../hooks/useAiraSocket.js";

const ChatRuntimeContext = createContext(null);

const PENDING_KEY = "__new_session_pending__";

function truncate(text, max) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function notifyBrowser(title, body) {
  if (typeof window === "undefined" || !("Notification" in window)) return;

  if (Notification.permission === "granted") {
    new Notification(title, { body: truncate(body, 120) });
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then((perm) => {
      if (perm === "granted") {
        new Notification(title, { body: truncate(body, 120) });
      }
    });
  }
}

/**
 * Provider ini dipasang di LEVEL APP (bukan di dalam ChatPage), supaya
 * state percakapan + koneksi WebSocket TIDAK ikut mati saat user
 * pindah ke halaman lain (Settings, Devices, dst). ChatPage jadi cuma
 * "jendela" yang menampilkan data dari sini, bukan pemilik datanya.
 *
 * PENTING: koneksi WebSocket dibuat SATU KALI di sini (lewat
 * useAiraSocket), TIDAK boleh dibuat lagi di ChatPage atau komponen
 * lain manapun untuk sessionId yang sama.
 *
 * FIX (Voice Call Mode):
 * - Event WS baru "transcript" (bubble user dari hasil STT server) dan
 *   "transcript_empty" (beri tahu user + batalkan status menunggu di
 *   voice call hook).
 * - Event "response" bisa membawa "audio_base64" (giliran suara),
 *   diteruskan ke voiceCallHandlersRef yang di-registrasi ChatPage.
 * - sendRaw(payload): kirim payload mentah ke socket, dipakai voice call.
 * - waitForConnection(): expose socket.waitUntilOpen supaya ChatPage bisa
 *   menunggu WS benar-benar terbuka sebelum voice call mulai menangkap
 *   audio - ini yang mencegah "Koneksi belum siap" muncul saat sesi
 *   baru dibuka lalu langsung dipakai voice call.
 */
export function ChatRuntimeProvider({ children, isOnChatPage }) {
  const { activeId, setActiveId, upsertSession } = useSessionsContext();
  const { notify } = useToast();

  const [messagesBySession, setMessagesBySession] = useState({});
  const [loadingBySession, setLoadingBySession] = useState({});
  const [phaseBySession, setPhaseBySession] = useState({});
  const [liveToolsBySession, setLiveToolsBySession] = useState({});
  const [switching, setSwitching] = useState(false);
  const [unreadSessionIds, setUnreadSessionIds] = useState(() => new Set());

  const isOnChatPageRef = useRef(isOnChatPage);
  isOnChatPageRef.current = isOnChatPage;

  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  const voiceCallHandlersRef = useRef(null);

  const registerVoiceCallHandlers = useCallback((handlers) => {
    voiceCallHandlersRef.current = handlers;
  }, []);

  const messages = messagesBySession[activeId] || [];
  const loading = loadingBySession[activeId] || false;
  const phase = phaseBySession[activeId] || null;
  const liveTools = liveToolsBySession[activeId] || [];

  const setMessagesForSession = useCallback((sessionId, updater) => {
    setMessagesBySession((prev) => {
      const current = prev[sessionId] || [];
      const next = typeof updater === "function" ? updater(current) : updater;
      return { ...prev, [sessionId]: next };
    });
  }, []);

  const markUnread = useCallback((sessionId) => {
    setUnreadSessionIds((prev) => {
      const next = new Set(prev);
      next.add(sessionId);
      return next;
    });
  }, []);

  const socket = useAiraSocket(activeId, {
    onEvent: (evt) => {
      const sid = evt.data?.session_id || activeIdRef.current;
      if (!sid) return;

      if (evt.type === "ack") {
        return;
      } else if (evt.type === "transcript") {
        setMessagesForSession(sid, (prev) => [
          ...prev,
          { role: "user", content: evt.data.text },
        ]);
      } else if (evt.type === "transcript_empty") {
        voiceCallHandlersRef.current?.cancelWaiting?.();
        const isCurrentlyViewing = isOnChatPageRef.current && sid === activeIdRef.current;
        if (isCurrentlyViewing) {
          notify({ type: "warning", message: evt.data.message, duration: 2500 });
        }
      } else if (evt.type === "thinking") {
        setPhaseBySession((prev) => ({ ...prev, [sid]: evt.data.message }));
      } else if (evt.type === "tool_start") {
        setPhaseBySession((prev) => ({ ...prev, [sid]: null }));
        setLiveToolsBySession((prev) => ({
          ...prev,
          [sid]: [
            ...(prev[sid] || []),
            { type: "tool_call", name: evt.data.name, category: evt.data.category, success: null },
          ],
        }));
      } else if (evt.type === "tool_finish") {
        setLiveToolsBySession((prev) => ({
          ...prev,
          [sid]: (prev[sid] || []).map((s) =>
            s.name === evt.data.name && s.success === null
              ? { ...s, success: evt.data.success, duration: evt.data.duration }
              : s
          ),
        }));
      } else if (evt.type === "response") {
        setPhaseBySession((prev) => ({ ...prev, [sid]: null }));
        setLiveToolsBySession((prev) => ({ ...prev, [sid]: [] }));
        setLoadingBySession((prev) => ({ ...prev, [sid]: false }));

        setMessagesForSession(sid, (prev) => [
          ...prev,
          { role: "assistant", content: evt.data.answer, steps: evt.data.steps, isNew: true },
        ]);

        const now = Date.now() / 1000;
        upsertSession({
          id: evt.data.session_id,
          title: evt.data.session_title,
          updated_at: now,
        });

        const isCurrentlyViewing = isOnChatPageRef.current && sid === activeIdRef.current;

        if (evt.data.audio_base64 !== undefined) {
          voiceCallHandlersRef.current?.playResponseAudio?.(
            evt.data.audio_base64,
            evt.data.answer
          );
        }

        if (!isCurrentlyViewing) {
          markUnread(sid);
          notify({
            type: "success",
            message: `AIRA selesai menjawab: "${truncate(evt.data.answer, 60)}"`,
            duration: 5000,
          });
          notifyBrowser("AIRA selesai menjawab", evt.data.answer);
        }
      } else if (evt.type === "error") {
        setPhaseBySession((prev) => ({ ...prev, [sid]: null }));
        setLiveToolsBySession((prev) => ({ ...prev, [sid]: [] }));
        setLoadingBySession((prev) => ({ ...prev, [sid]: false }));
        voiceCallHandlersRef.current?.cancelWaiting?.();

        const isCurrentlyViewing = isOnChatPageRef.current && sid === activeIdRef.current;
        if (!isCurrentlyViewing) {
          markUnread(sid);
        }
        notify({ type: "error", message: evt.data.message });
      }
    },
  });

  useEffect(() => {
    if (!activeId) return;
    if (messagesBySession[activeId]) return;

    let cancelled = false;
    setSwitching(true);

    api.sessions
      .messages(activeId)
      .then((res) => {
        if (cancelled) return;
        setMessagesForSession(
          activeId,
          res.turns.map((t) => ({ role: t.role, content: t.content, steps: t.steps }))
        );
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setSwitching(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  useEffect(() => {
    if (isOnChatPage && activeId && unreadSessionIds.has(activeId)) {
      setUnreadSessionIds((prev) => {
        const next = new Set(prev);
        next.delete(activeId);
        return next;
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnChatPage, activeId]);

  const sendMessage = useCallback(
    async (text, { onNewSession } = {}) => {
      const sessionId = activeIdRef.current;
      const bucketKey = sessionId || PENDING_KEY;

      setMessagesForSession(bucketKey, (prev) => [...prev, { role: "user", content: text }]);
      setLoadingBySession((prev) => ({ ...prev, [bucketKey]: true }));
      setPhaseBySession((prev) => ({ ...prev, [bucketKey]: "Menganalisis permintaan..." }));

      if (sessionId && socket.isOpen) {
        const sent = socket.send(text);
        if (sent) return;
      }

      try {
        const result = await api.chat(text, sessionId);
        const finalId = result.session_id;

        setMessagesBySession((prev) => {
          const pending = prev[bucketKey] || [];
          const merged = [
            ...pending,
            { role: "assistant", content: result.answer, steps: result.steps, isNew: true },
          ];
          const next = { ...prev, [finalId]: merged };
          if (bucketKey !== finalId) delete next[bucketKey];
          return next;
        });

        setLoadingBySession((prev) => {
          const next = { ...prev, [finalId]: false };
          if (bucketKey !== finalId) delete next[bucketKey];
          return next;
        });
        setPhaseBySession((prev) => {
          const next = { ...prev, [finalId]: null };
          if (bucketKey !== finalId) delete next[bucketKey];
          return next;
        });

        const now = Date.now() / 1000;
        upsertSession({ id: finalId, title: result.session_title, updated_at: now });

        if (finalId !== sessionId) {
          onNewSession?.(finalId);
        }

        return result.answer;
      } catch (err) {
        notify({ type: "error", message: err.message });
        return null;
      } finally {
        setLoadingBySession((prev) => ({ ...prev, [bucketKey]: false }));
        setPhaseBySession((prev) => ({ ...prev, [bucketKey]: null }));
      }
    },
    [socket, upsertSession, notify, setMessagesForSession]
  );

  const sendRaw = useCallback(
    (payload) => {
      if (!socket.isOpen) return false;
      return socket.sendRaw(payload);
    },
    [socket]
  );

  const waitForConnection = useCallback(
    (timeoutMs) => socket.waitUntilOpen(timeoutMs),
    [socket]
  );

  const value = {
    messages,
    loading,
    phase,
    liveTools,
    switching,
    wsStatus: socket.status,
    sendMessage,
    sendRaw,
    waitForConnection,
    registerVoiceCallHandlers,
    unreadSessionIds,
  };

  return <ChatRuntimeContext.Provider value={value}>{children}</ChatRuntimeContext.Provider>;
}

export function useChatRuntime() {
  const ctx = useContext(ChatRuntimeContext);
  if (!ctx) {
    throw new Error("useChatRuntime must be used within a ChatRuntimeProvider");
  }
  return ctx;
}