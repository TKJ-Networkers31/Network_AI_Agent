import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import LiveSteps from "../components/LiveSteps.jsx";
import BootScreen from "../components/boot/BootScreen.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoiceCall } from "../hooks/useVoiceCall.js";

const QUICK_ACTIONS = [
  { label: "Create Image", icon: "✧" },
  { label: "Brainstorm", icon: "✦" },
  { label: "Make a plan", icon: "▤" },
];

const FEATURE_CARDS = [
  {
    title: "Image Generator",
    description: "Create high-quality images instantly from text.",
    action: "Create Image",
    icon: "▧",
  },
  {
    title: "AI Presentation",
    description: "Turn ideas into engaging professional presentations.",
    action: "Make Slides",
    icon: "▤",
  },
  {
    title: "Dev Assistant",
    description: "Generate cleaner, production-ready code in seconds.",
    action: "Generate Code",
    icon: "</>",
  },
];

export default function ChatPage({ onOpenMenu }) {
  const { sessions, activeId, setActiveId, loadSessions, sessionsReady } =
    useSessionsContext();

  const {
    messages,
    loading,
    phase,
    liveTools,
    switching,
    wsStatus,
    sendMessage,
    sendRaw,
    waitForConnection,
    registerVoiceCallHandlers,
    personaReady,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const bottomRef = useRef(null);

  const { notify } = useToast();

  const voiceCall = useVoiceCall({
    onSendAudio: (payload) => {
      const sent = sendRaw(payload);
      if (!sent) {
        notify({
          type: "error",
          message: "Koneksi terputus saat mengirim audio - menunggu tersambung ulang...",
        });
        voiceCall.cancelWaiting();
      }
    },
    notify,
  });

  useEffect(() => {
    registerVoiceCallHandlers({
      playResponseAudio: voiceCall.playResponseAudio,
      cancelWaiting: voiceCall.cancelWaiting,
    });

    return () => {
      registerVoiceCallHandlers(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceCall.playResponseAudio, voiceCall.cancelWaiting]);

  useEffect(() => {
    return () => {
      voiceCall.endCall();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    api
      .tools()
      .then((res) => setTools(res.tools))
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  if (!sessionsReady || !personaReady) {
    return <BootScreen />;
  }

  async function handleSend(text) {
    await sendMessage(text, {
      onNewSession: (newId) => {
        setActiveId(newId);
        loadSessions?.();
      },
    });
  }

  async function handleToggleVoiceCall() {
    if (voiceCall.callActive) {
      voiceCall.endCall();
      return;
    }

    setVoiceConnecting(true);

    try {
      let sessionId = activeId;

      if (!sessionId) {
        const created = await api.sessions.create();
        sessionId = created.id;
        setActiveId(sessionId);
        loadSessions?.();
      }

      await waitForConnection(8000);
      voiceCall.startCall();
    } catch (err) {
      notify({
        type: "error",
        message: `Gagal memulai sesi suara: ${err.message || err}`,
      });
    } finally {
      setVoiceConnecting(false);
    }
  }

  const activeTitle =
    sessions.find((s) => s.id === activeId)?.title || "Chat baru";
  const isEmptyState = !switching && messages.length === 0 && !loading;

  return (
    <div className="chat-page-shell flex-1 flex flex-col min-w-0 min-h-0">
      {(voiceCall.callActive || voiceConnecting) && (
        <VoiceOverlay
          connecting={voiceConnecting && !voiceCall.callActive}
          interimText={voiceCall.listening ? "Mendengarkan..." : ""}
          subtitle={voiceCall.subtitle}
          speaking={voiceCall.speaking}
          waitingReply={voiceCall.waitingReply}
          onCancel={() => {
            voiceCall.endCall();
            setVoiceConnecting(false);
          }}
        />
      )}

      {!isEmptyState && (
        <TopBar
          title={activeTitle}
          subtitle="Ngobrol atau ketik '/' untuk pakai tool langsung"
          onMenuClick={onOpenMenu}
          wsStatus={wsStatus}
        />
      )}

      {isEmptyState ? (
        <div className="chat-empty-state">
          <div className="chat-empty-orb" aria-hidden="true">
            <span className="chat-empty-orb-core" />
          </div>
          <h1 className="chat-empty-title">Ready to create something new?</h1>
          <p className="chat-empty-description">
            Your AI workspace is ready. Ask anything, explore ideas, or start building.
          </p>

          <div className="chat-quick-actions" aria-label="Quick actions">
            {QUICK_ACTIONS.map((action) => (
              <span key={action.label} className="chat-quick-action">
                <span aria-hidden="true">{action.icon}</span>
                {action.label}
              </span>
            ))}
          </div>

          <div className="chat-feature-grid">
            {FEATURE_CARDS.map((card) => (
              <div key={card.title} className="chat-feature-card">
                <div className="chat-feature-card-topline">
                  <span className="chat-feature-icon" aria-hidden="true">{card.icon}</span>
                  <span className="chat-feature-action">{card.action}</span>
                </div>
                <h2>{card.title}</h2>
                <p>{card.description}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0 space-y-3 sm:space-y-4 pr-1 pb-3">
          {switching && (
            <p className="text-white/30 text-sm text-center mt-10">
              Memuat percakapan...
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
      )}

      <div className="chat-input-dock mt-2 sm:mt-3 mb-1">
        <ChatInput
          onSend={handleSend}
          disabled={loading}
          tools={tools}
          voiceControls={
            <VoiceControls
              supported={voiceCall.supported}
              listening={voiceCall.callActive || voiceConnecting}
              speaking={voiceCall.speaking}
              speakEnabled={voiceCall.callActive}
              onToggleListen={handleToggleVoiceCall}
              onToggleSpeak={handleToggleVoiceCall}
            />
          }
        />
      </div>
    </div>
  );
}
