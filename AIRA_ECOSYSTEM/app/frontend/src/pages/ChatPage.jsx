import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoice } from "../hooks/useVoice.js";

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
  const bottomRef = useRef(null);

  // Dipakai supaya begitu KITA sendiri yang baru saja membuat sesi
  // baru (lewat handleSend), efek di bawah tidak refetch riwayat dari
  // server - datanya sudah ada di layar. Tanpa ini, layar sempat
  // "kedip" nyembunyiin pesan yang baru dijawab lalu nampilin lagi,
  // yang keliatan kayak "keluar dari sesi, bikin sesi baru".
  const skipNextReloadRef = useRef(false);

  const { notify } = useToast();

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

    try {
      const result = await api.chat(text, activeId);

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.answer, steps: result.steps },
      ]);

      const now = Date.now() / 1000;

      if (result.session_id !== activeId) {
        // Sesi baru lahir dari pesan ini - update sidebar secara
        // lokal (instan) dan tandai supaya efek activeId di atas
        // tidak fetch ulang riwayat yang sudah kita punya.
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
    }
  }

  const voice = useVoice({
    onTranscript: (text) => handleSend(text),
    notify,
  });

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
            />
          ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-card border border-border rounded-xl2 px-4 py-3 text-sm text-white/50">
              <span className="animate-pulse">Agent sedang berpikir...</span>
            </div>
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
