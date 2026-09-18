import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useSessionsContext } from "./SessionsContext.jsx";
import { useAiraSocket } from "../hooks/useAiraSocket.js";
import { api } from "../api.js";

const ChatRuntimeContext = createContext(null);

/**
 * ChatRuntimeProvider — dipasang di App.jsx level (bukan di dalam
 * ChatPage) supaya koneksi WebSocket + state pesan TIDAK putus saat
 * user pindah ke halaman lain (Devices/Models/Persona/dst) lalu balik
 * lagi ke Chat.
 *
 * FIX: file ini sebelumnya ketimpa isi MessageBubble.jsx saat proses
 * rekonstruksi UI - akibatnya seluruh state runtime (wsStatus,
 * sendMessage, sendDioSubmission, unreadSessionIds, dst) hilang total
 * dan semua consumer (ChatPage.jsx, Sidebar.jsx) crash / silently
 * broken. Direkonstruksi dari pemakaian nyata di kedua file itu.
 */
export function ChatRuntimeProvider({ children, isOnChatPage }) {
  const { activeId, upsertSession } = useSessionsContext();

  // Pesan disimpan PER session_id supaya pindah sesi tidak saling
  // menimpa / tidak perlu re-fetch tiap kali balik ke sesi yang sama.
  const [messagesBySession, setMessagesBySession] = useState({});
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState("");
  const [liveTools, setLiveTools] = useState([]);
  const [switching, setSwitching] = useState(false);
  const [unreadSessionIds, setUnreadSessionIds] = useState(() => new Set());
  const [persona, setPersona] = useState(null);
  const [personaReady, setPersonaReady] = useState(false);

  const voiceHandlersRef = useRef(null);
  const loadedSessionsRef = useRef(new Set());

  const messages = messagesBySession[activeId] || [];

  const setMessagesForSession = useCallback((sessionId, updater) => {
    if (!sessionId) return;
    setMessagesBySession((prev) => {
      const current = prev[sessionId] || [];
      const next = typeof updater === "function" ? updater(current) : updater;
      return { ...prev, [sessionId]: next };
    });
  }, []);

  // --------------------------------------------------------------
  // WEBSOCKET EVENT HANDLER — satu jalur untuk teks, suara, DAN
  // dio_submission (semuanya lewat api/routers/ws.py::chat_ws).
  // --------------------------------------------------------------
  const handleEvent = useCallback(
    (event) => {
      const { type, data } = event || {};
      if (!type) return;

      switch (type) {
        case "ack": {
          setLoading(true);
          setPhase("Menganalisis permintaan...");
          setLiveTools([]);
          break;
        }

        case "thinking": {
          setPhase(data?.message || "Berpikir...");
          break;
        }

        case "tool_start": {
          setLiveTools((prev) => [...prev, { ...data, success: null }]);
          break;
        }

        case "tool_finish": {
          setLiveTools((prev) => {
            // update entri "success: null" TERAKHIR dengan nama yang sama
            const idx = [...prev]
              .reverse()
              .findIndex((t) => t.name === data.name && t.success === null);
            if (idx === -1) return prev;
            const realIdx = prev.length - 1 - idx;
            const next = [...prev];
            next[realIdx] = { ...next[realIdx], ...data };
            return next;
          });
          break;
        }

        case "transcript": {
          // hasil STT dari voice call mode - tampilkan sebagai bubble user
          setMessagesForSession(data.session_id, (prev) => [
            ...prev,
            { role: "user", content: data.text, isNew: true },
          ]);
          break;
        }

        case "transcript_empty": {
          voiceHandlersRef.current?.cancelWaiting?.();
          setLoading(false);
          setPhase("");
          break;
        }

        case "response": {
          const sid = data.session_id;

          setMessagesForSession(sid, (prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.answer,
              steps: data.steps,
              interactionSchema: data.interaction_schema || null,
              isNew: true,
            },
          ]);

          setLoading(false);
          setPhase("");
          setLiveTools([]);

          if (data.session_title) {
            upsertSession({
              id: sid,
              title: data.session_title,
              updated_at: Date.now() / 1000,
            });
          }

          if (sid && sid !== activeId) {
            setUnreadSessionIds((prev) => {
              const next = new Set(prev);
              next.add(sid);
              return next;
            });
          }

          voiceHandlersRef.current?.playResponseAudio?.(
            data.audio_base64,
            data.answer
          );
          break;
        }

        case "error": {
          const sid = data.session_id || activeId;
          setMessagesForSession(sid, (prev) => [
            ...prev,
            { role: "assistant", content: `⚠ ${data.message}`, isNew: true },
          ]);
          setLoading(false);
          setPhase("");
          setLiveTools([]);
          voiceHandlersRef.current?.cancelWaiting?.();
          break;
        }

        default:
          break;
      }
    },
    [activeId, setMessagesForSession, upsertSession]
  );

  const {
    status: wsStatus,
    send,
    sendRaw,
    waitUntilOpen,
  } = useAiraSocket(activeId, { onEvent: handleEvent });

  // --------------------------------------------------------------
  // PERSONA — dimuat sekali, dipakai Hero/greeting (buildGreeting)
  // --------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    api.persona
      .get()
      .then((res) => {
        if (!cancelled) setPersona(res.profile || {});
      })
      .catch(() => {
        if (!cancelled) setPersona({});
      })
      .finally(() => {
        if (!cancelled) setPersonaReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // --------------------------------------------------------------
  // LOAD HISTORY — sekali per session_id (cache di loadedSessionsRef),
  // supaya reload halaman / buka sesi lama tetap tampil riwayatnya.
  // --------------------------------------------------------------
  useEffect(() => {
    if (!activeId) return;
    if (loadedSessionsRef.current.has(activeId)) return;

    setSwitching(true);

    api.sessions
      .messages(activeId)
      .then((res) => {
        const turns = (res.turns || []).map((t) => ({
          role: t.role,
          content: t.content,
          steps: t.steps || [],
          interactionSchema: t.interaction_schema || null,
        }));
        setMessagesForSession(activeId, turns);
        loadedSessionsRef.current.add(activeId);
      })
      .catch(() => {
        // sesi baru / belum ada riwayat - biarkan messages tetap kosong
        loadedSessionsRef.current.add(activeId);
      })
      .finally(() => setSwitching(false));
  }, [activeId, setMessagesForSession]);

  // Tandai sesi aktif sebagai "sudah dibaca" saat user membuka Chat page
  useEffect(() => {
    if (!activeId || !isOnChatPage) return;
    setUnreadSessionIds((prev) => {
      if (!prev.has(activeId)) return prev;
      const next = new Set(prev);
      next.delete(activeId);
      return next;
    });
  }, [activeId, isOnChatPage]);

  // --------------------------------------------------------------
  // ACTIONS
  // --------------------------------------------------------------

  const sendMessage = useCallback(
    async (text, { onNewSession } = {}) => {
      let sessionId = activeId;

      if (!sessionId) {
        const created = await api.sessions.create();
        sessionId = created.id;
        onNewSession?.(sessionId);
        // beri waktu socket pindah/connect ke session_id baru sebelum kirim
        await waitUntilOpen(8000).catch(() => {});
      }

      setMessagesForSession(sessionId, (prev) => [
        ...prev,
        { role: "user", content: text, isNew: true },
      ]);

      setLoading(true);
      setPhase("Mengirim...");
      setLiveTools([]);

      const ok = send(text);

      if (!ok) {
        setLoading(false);
        setPhase("");
        setMessagesForSession(sessionId, (prev) => [
          ...prev,
          {
            role: "assistant",
            content: "⚠ Koneksi belum siap, coba lagi sebentar.",
            isNew: true,
          },
        ]);
      }
    },
    [activeId, send, setMessagesForSession, waitUntilOpen]
  );

  // Dipakai ChatPage.jsx saat user submit form/pilihan interaktif DIO
  // (hasil request_structured_input()) - lihat agents/rei/dio_tools.py.
  const sendDioSubmission = useCallback(
    (submission, displayText) => {
      if (!activeId) return;

      setMessagesForSession(activeId, (prev) => [
        ...prev,
        { role: "user", content: displayText, isNew: true },
      ]);

      setLoading(true);
      setPhase("Memproses...");
      setLiveTools([]);

      const ok = sendRaw({
        message: displayText,
        dio_submission: submission,
      });

      if (!ok) {
        setLoading(false);
        setPhase("");
        setMessagesForSession(activeId, (prev) => [
          ...prev,
          {
            role: "assistant",
            content: "⚠ Koneksi terputus saat mengirim form, coba lagi.",
            isNew: true,
          },
        ]);
      }
    },
    [activeId, sendRaw, setMessagesForSession]
  );

  const waitForConnection = useCallback(
    (timeoutMs) => waitUntilOpen(timeoutMs),
    [waitUntilOpen]
  );

  const registerVoiceCallHandlers = useCallback((handlers) => {
    voiceHandlersRef.current = handlers;
  }, []);

  return (
    <ChatRuntimeContext.Provider
      value={{
        messages,
        loading,
        phase,
        liveTools,
        switching,
        wsStatus,
        sendMessage,
        sendDioSubmission,
        sendRaw,
        waitForConnection,
        registerVoiceCallHandlers,
        persona,
        personaReady,
        unreadSessionIds,
      }}
    >
      {children}
    </ChatRuntimeContext.Provider>
  );
}

export function useChatRuntime() {
  const ctx = useContext(ChatRuntimeContext);
  if (!ctx) {
    throw new Error("useChatRuntime must be used within a ChatRuntimeProvider");
  }
  return ctx;
}