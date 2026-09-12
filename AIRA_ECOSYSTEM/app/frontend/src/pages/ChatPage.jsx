import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import LiveSteps from "../components/LiveSteps.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoice } from "../hooks/useVoice.js";
import { useAiraSocket } from "../hooks/useAiraSocket.js";

export default function ChatPage({ onOpenMenu }) {
  const {
    sessions,
    activeId,
    setActiveId,
    upsertSession,
  } = useSessionsContext();

  const [messages, setMessages] = useState([]);
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [phase, setPhase] = useState(null);
  const [liveTools, setLiveTools] = useState([]);
  const bottomRef = useRef(null);

  const skipNextReloadRef = useRef(false);

  const { notify } = useToast();

  const voice = useVoice({
    onTranscript: (text) => handleSend(text),
    notify,
  });

  const socket = useAiraSocket(activeId, {
    onEvent: (evt) => {
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
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: evt.data.answer, steps: evt.data.steps, isNew: true },
        ]);

        const now = Date.now() / 1000;
        upsertSession({
          id: evt.data.session_id,
          title: evt.data.session_title,
          updated_at: now,
        });

        setLoading(false);

        if (evt.data.answer) {
          voice.speak(evt.data.answer);
        }
      } else if (evt.type === "error") {
        setPhase(null);
        setLiveTools([]);
        setLoading(false);
        notify({ type: "error", message: evt.data.message });
      }
    },
  });

  useEffect(() => {
    api
      .tools()
      .then((res) => setTools(res.tools))
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }

    if (skipNextReloadRef.current) {
      skipNextReloadRef.current = false;
      return;
    }

    let cancelled = false;
    setSwitching(true);

    api.sessions
      .messages(activeId)
      .then((res) => {
        if (cancelled) return;
        setMessages(
          res.turns.map((t) => ({
            role: t.role,
            content: t.content,
            steps: t.steps,
          }))
        );
      })
      .catch((e) => notify({ type: "error", message: e.message }))
      .finally(() => {
        if (!cancelled) setSwitching(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  async function handleSend(text) {
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    setPhase("Menganalisis permintaan...");

    // Kalau socket sudah connect DAN sesi sudah ada -> pakai WebSocket.
    // Hasilnya ditangani di onEvent (event "response") di atas.
    if (activeId && socket.isOpen) {
      const sent = socket.send(text);
      if (sent) return;
    }

    // --- Fallback REST (dipakai untuk chat pertama / socket belum siap) ---
    try {
      const result = await api.chat(text, activeId);

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.answer, steps: result.steps, isNew: true },
      ]);

      const now = Date.now() / 1000;

      if (result.session_id !== activeId) {
        skipNextReloadRef.current = true;
        upsertSession({
          id: result.session_id,
          title: result.session_title,
          updated_at: now,
        });
        setActiveId(result.session_id);
      } else {
        upsertSession({
          id: result.session_id,
          title: result.session_title,
          updated_at: now,
        });
      }

      if (result.answer) {
        voice.speak(result.answer);
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setLoading(false);
      setPhase(null);
    }
  }

  const activeTitle =
    sessions.find((s) => s.id === activeId)?.title || "Chat baru";

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      {voice.listening && (
        <VoiceOverlay
          interimText={voice.interimText}
          onCancel={voice.stopListening}
        />
      )}

      <TopBar
        title={activeTitle}
        subtitle="Ngobrol atau ketik '/' untuk pakai tool langsung"
        onMenuClick={onOpenMenu}
        wsStatus={socket.status}
      />

      <div className="flex-1 overflow-y-auto min-h-0 space-y-3 sm:space-y-4 pr-1 pb-3">
        {switching && (
          <p className="text-white/30 text-sm text-center mt-10">
            Memuat percakapan...
          </p>
        )}

        {!switching && messages.length === 0 && !loading && (
          <p className="text-white/30 text-sm text-center mt-10 px-4">
            Mulai percakapan baru, ketik{" "}
            <span className="font-mono text-accent-light">/</span> untuk
            pakai tool langsung, atau tekan mic untuk bicara.
          </p>
        )}

        {!switching &&
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              role={m.role}
              content={m.content}
              steps={m.steps}
              isNew={m.isNew}
            />
          ))}

        {loading && (
          <div className="flex justify-start">
            <LiveSteps phase={phase} liveTools={liveTools} />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="mt-2 sm:mt-3 mb-1">
        <ChatInput
          onSend={handleSend}
          disabled={loading}
          tools={tools}
          voiceControls={
            <VoiceControls
              supported={voice.supported}
              listening={voice.listening}
              speaking={voice.speaking}
              speakEnabled={voice.speakEnabled}
              onToggleListen={voice.toggleListening}
              onToggleSpeak={voice.toggleSpeak}
            />
          }
        />
      </div>
    </div>
  );
}