// AIRA_ECOSYSTEM/app/frontend/src/pages/ChatPage.jsx
//
// FIX (Optimalisasi Greeting):
// - buildGreeting() dibungkus useMemo, key-nya `persona` saja, supaya greeting
//   di Hero tidak "kedip" saat komponen re-render (loading/liveTools).
// - Tidak ada pesan pembuka statis dari backend/LLM - Hero murni client-side.
//
// PERUBAHAN (Chat Session):
// - Tombol Stop (ChatInput), Edit prompt, Salin, dan Buat ulang jawaban
//   (MessageBubble) disambungkan ke ChatRuntimeContext.
// - `loading` / `switching` milik SESI AKTIF saja.
// - Status "form sudah dikirim" disimpan di pesannya sendiri.
// - Key bubble menyertakan session id.
//
// PERUBAHAN (UI Layout): area pesan full-width (scrollbar di tepi kanan)
// dengan konten dibatasi max-w-4xl di tengah; ChatInput menempel ke bawah.
// Logic TIDAK berubah.

import { useEffect, useMemo, useRef, useState } from "react";
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
import Hero from "../Hero.jsx";

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
    stopRun,
    regenerate,
    editMessage,
    markInteractionResolved,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const bottomRef = useRef(null);

  const { notify } = useToast();

  const greetingText = useMemo(() => buildGreeting(persona), [persona]);

  // Posisi pesan non-lokal terakhir, dan pesan assistant yang boleh
  // menampilkan tombol "Buat ulang" (jawaban atas pesan user terakhir,
  // sebelum ada pesan user lain sesudahnya).
  const { lastNonLocalIdx, regenIdx } = useMemo(() => {
    let lastUser = -1;
    let lastNonLocal = -1;

    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (lastUser === -1 && messages[i].role === "user") lastUser = i;
      if (lastNonLocal === -1 && !messages[i].local) lastNonLocal = i;
      if (lastUser !== -1 && lastNonLocal !== -1) break;
    }

    let regen = -1;
    if (lastUser !== -1) {
      for (let i = messages.length - 1; i > lastUser; i -= 1) {
        if (messages[i].role === "assistant" && !messages[i].local) {
          regen = i;
          break;
        }
      }
    }

    return { lastNonLocalIdx: lastNonLocal, regenIdx: regen };
  }, [messages]);

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

    markInteractionResolved(index);

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

      {/* Area pesan: full-width (scrollbar di tepi kanan), konten di tengah */}
      <div className="flex-1 overflow-y-auto min-h-0 -mx-3 sm:-mx-5 lg:-mx-6 px-3 sm:px-5 lg:px-6">
        <div className="max-w-4xl mx-auto w-full space-y-3 sm:space-y-4 pb-3">
          {switching && (
            <p className="text-white/30 text-sm text-center mt-10">
              Memuat percakapan...
            </p>
          )}

          {!switching && messages.length === 0 && !loading && (
            <Hero
              greeting={greetingText}
              onQuickPrompt={(text) => handleSend(text)}
            />
          )}

          {!switching &&
            messages.map((m, i) => (
              <MessageBubble
                key={`${activeId || "baru"}-${i}`}
                role={m.role}
                content={m.content}
                steps={m.steps}
                isNew={m.isNew}
                local={m.local}
                interactionSchema={m.interactionSchema}
                interactionResolved={Boolean(m.interactionResolved)}
                onSubmitInteraction={(actionId, values) =>
                  handleInteractionSubmit(i, actionId, values)
                }
                busy={loading}
                canRegenerate={i === regenIdx}
                onRegenerate={regenerate}
                hasFollowing={i < lastNonLocalIdx}
                onEdit={m.role === "user" ? (text) => editMessage(i, text) : undefined}
              />
            ))}

          {loading && (
            <div className="flex justify-start">
              <LiveSteps phase={phase} liveTools={liveTools} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input menempel ke bawah (full-bleed diatur di dalam ChatInput) */}
      <ChatInput
        onSend={handleSend}
        disabled={loading || switching}
        isRunning={loading}
        onStop={() => stopRun()}
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
  );
}