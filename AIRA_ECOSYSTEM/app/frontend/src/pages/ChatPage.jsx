import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import LiveSteps from "../components/LiveSteps.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoice } from "../hooks/useVoice.js";

export default function ChatPage({ onOpenMenu }) {
  const { sessions, activeId, setActiveId } = useSessionsContext();

  // Koneksi WebSocket & seluruh state proses (loading/phase/liveTools)
  // datang dari ChatRuntimeContext (dipasang di App.jsx level atas).
  // ChatPage TIDAK membuat koneksi WebSocket sendiri - itu penting
  // supaya wsStatus yang ditampilkan di TopBar konsisten dengan
  // koneksi yang benar-benar dipakai untuk kirim/terima pesan.
  const {
    messages,
    loading,
    phase,
    liveTools,
    switching,
    wsStatus,
    sendMessage,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const bottomRef = useRef(null);
  const spokenCountRef = useRef(0);

  const { notify } = useToast();

  const voice = useVoice({
    onTranscript: (text) => handleSend(text),
    notify,
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
    if (messages.length === 0) return;
    if (messages.length <= spokenCountRef.current) return;

    spokenCountRef.current = messages.length;

    const last = messages[messages.length - 1];
    if (last.role === "assistant" && last.content) {
      voice.speak(last.content);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    spokenCountRef.current = messages.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  async function handleSend(text) {
    await sendMessage(text, {
      onNewSession: (newId) => {
        setActiveId(newId);
      },
    });
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
        wsStatus={wsStatus}
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