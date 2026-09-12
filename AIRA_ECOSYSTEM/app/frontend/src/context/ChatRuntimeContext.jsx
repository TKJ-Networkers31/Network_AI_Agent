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
 */
export function ChatRuntimeProvider({ children, isOnChatPage }) {
  const { activeId, setActiveId, upsertSession } = useSessionsContext();
  const { notify } = useToast();

  const [messagesBySession, setMessagesBySession] = useState({});
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState(null);
  const [liveTools, setLiveTools] = useState([]);
  const [switching, setSwitching] = useState(false);
  const [unreadSessionIds, setUnreadSessionIds] = useState(() => new Set());

  // Ref supaya callback socket selalu baca nilai TERBARU tanpa perlu
  // reconnect socket tiap kali isOnChatPage/activeId berubah.
  const isOnChatPageRef = useRef(isOnChatPage);
  isOnChatPageRef.current = isOnChatPage;

  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  const messages = messagesBySession[activeId] || [];

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
      const sessionId = activeIdRef.current;

      if (evt.type === "thinking") {
        setPhase(evt.data.message);
      } else if (evt.type === "tool_start") {
        setPhase(null);
        setLiveTools((prev) => [
          ...prev,
          { type: "tool_call", name: evt.data.name, category: evt.data.category, success: null },
        ]);
      } else if (evt.type === "tool_finish") {
        setLiveTools((prev) =>
          prev.map((s) =>
            s.name === evt.data.name && s.success === null
              ? { ...s, success: evt.data.success, duration: evt.data.duration }
              : s
          )
        );
      } else if (evt.type === "response") {
        setPhase(null);
        setLiveTools([]);
        setLoading(false);

        setMessagesForSession(sessionId, (prev) => [
          ...prev,
          { role: "assistant", content: evt.data.answer, steps: evt.data.steps, isNew: true },
        ]);

        const now = Date.now() / 1000;
        upsertSession({
          id: evt.data.session_id,
          title: evt.data.session_title,
          updated_at: now,
        });

        // User sedang TIDAK di halaman Chat saat jawaban ini datang
        // -> tandai belum dibaca + kasih notifikasi.
        if (!isOnChatPageRef.current) {
          markUnread(sessionId);
          notify({
            type: "success",
            message: `AIRA selesai menjawab: "${truncate(evt.data.answer, 60)}"`,
            duration: 5000,
          });
          notifyBrowser("AIRA selesai menjawab", evt.data.answer);
        }
      } else if (evt.type === "error") {
        setPhase(null);
        setLiveTools([]);
        setLoading(false);

        if (!isOnChatPageRef.current) {
          markUnread(sessionId);
        }
        notify({ type: "error", message: evt.data.message });
      }
    },
  });

  // Load riwayat sesi HANYA kalau belum ada di cache lokal - supaya
  // balik ke sesi yang sama tidak fetch ulang & tidak menimpa pesan
  // yang baru saja masuk lewat WS selama kamu tidak di halaman ini.
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

  // Begitu user membuka halaman Chat untuk sesi ini, hapus tanda
  // "belum dibaca".
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
      setLoading(true);
      setPhase("Menganalisis permintaan...");

      // Sesi sudah ada & socket connect -> pakai WebSocket, hasil
      // ditangani di onEvent di atas.
      if (sessionId && socket.isOpen) {
        const sent = socket.send(text);
        if (sent) return;
      }

      // --- Fallback REST (chat pertama / socket belum siap) ---
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
        setLoading(false);
        setPhase(null);
      }
    },
    [socket, upsertSession, notify, setMessagesForSession]
  );

  const value = {
    messages,
    loading,
    phase,
    liveTools,
    switching,
    wsStatus: socket.status,
    sendMessage,
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