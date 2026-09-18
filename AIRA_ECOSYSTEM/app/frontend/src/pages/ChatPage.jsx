// FIX (Optimalisasi DIO):
// - sendDioSubmission diambil dari ChatRuntimeContext.
// - resolvedInteractions (Set index pesan yang schema-nya sudah
//   di-submit) mencegah form yang sama disubmit dua kali dalam satu
//   sesi tampilan.
// - handleInteractionSubmit menentukan cancelled dari style aksi yang
//   ditekan (style "ghost" dipakai builder.py untuk semua aksi
//   batal/tolak), membangun teks bubble ringkas, lalu memanggil
//   sendDioSubmission - bukan sendMessage biasa.
import { useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import LiveSteps from "../components/LiveSteps.jsx";
import BootScreen from "../components/BootScreen.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoiceCall } from "../hooks/useVoiceCall.js";
import { buildGreeting } from "../utils/greeting.js";

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
    sendDioSubmission,
    sendRaw,
    waitForConnection,
    registerVoiceCallHandlers,
    persona,
    personaReady,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const [resolvedInteractions, setResolvedInteractions] = useState(() => new Set());
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

  function handleInteractionSubmit(index, actionId, values) {
    const message = messages[index];
    const schema = message?.interactionSchema;
    if (!schema) return;

    const action = (schema.actions || []).find((a) => a.id === actionId);
    const cancelled = action ? action.style === "ghost" : false;
    const displayText = cancelled ? "❌ Dibatalkan." : "📝 Form terkirim.";

    setResolvedInteractions((prev) => {
      const next = new Set(prev);
      next.add(index);
      return next;
    });

    sendDioSubmission(
      { schema_id: schema.id, action_id: actionId, values, cancelled },
      displayText
    );
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

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
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
          <div className="mt-6 px-1">
            <MessageBubble
              role="assistant"
              content={buildGreeting(persona)}
              isNew
            />
            <p className="text-white/30 text-xs text-center mt-3 px-4">
              Ketik <span className="font-mono text-accent-light">/</span>{" "}
              untuk pakai tool langsung, atau tekan mic untuk mulai sesi
              suara.
            </p>
          </div>
        )}

        {!switching &&
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              role={m.role}
              content={m.content}
              steps={m.steps}
              isNew={m.isNew}
              interactionSchema={m.interactionSchema}
              interactionResolved={resolvedInteractions.has(i)}
              onSubmitInteraction={(actionId, values) =>
                handleInteractionSubmit(i, actionId, values)
              }
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