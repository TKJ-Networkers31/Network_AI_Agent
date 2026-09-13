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
    sendRaw,
    waitForConnection,
    registerVoiceCallHandlers,
    persona,
    personaReady,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const bottomRef = useRef(null);

  const { notify } = useToast();

  // ------------------------------------------------------------
  // VOICE CALL MODE (Whisper + Kokoro LOKAL via WebSocket, BUKAN Web
  // Speech API browser). Mic capture + VAD ditangani hook ini; audio
  // dikirim lewat sendRaw() ke WS yang sama dengan chat teks.
  // ------------------------------------------------------------
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

  // Mic & speaker WAJIB mati kalau ChatPage ditinggalkan/ditutup.
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

  // FIX (Chat Session Lifecycle): jangan render ChatPage sampai sesi
  // aktif ter-resolve (SessionsContext) DAN persona ter-load
  // (ChatRuntimeContext). Ini titik "Ready" di lifecycle diagram -
  // tidak ada blank screen, tidak butuh refresh. Semua hook di atas
  // TETAP dipanggil sebelum early-return ini (Rules of Hooks).
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

  /**
   * FIX bug "Koneksi belum siap - tidak bisa mengirim audio":
   * sebelumnya voice call langsung mulai menangkap mic tanpa memastikan
   * (1) sudah ada session_id, dan (2) WebSocket-nya benar-benar OPEN.
   * Kalau user membuka "Chat baru" (activeId masih null) lalu langsung
   * pencet mic, WS tidak pernah connect sama sekali - jadi begitu ada
   * ucapan yang selesai (VAD deteksi jeda), pengiriman audio pasti gagal.
   *
   * Sekarang: sebelum mic mulai menangkap, kita PASTIKAN dulu sesi ada
   * (buat via REST kalau belum ada) dan WS-nya open, baru voiceCall
   * benar-benar dimulai. Kalau chat teks biasa tidak terpengaruh sama
   * sekali oleh perubahan ini.
   */
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

        {/* FIX (Dynamic Greeting): greeting dibangun lokal dari Persona
            + jam saat ini, HANYA muncul saat sesi belum punya pesan
            sama sekali (sesi baru / pertama kali dibuka). Begitu
            messages.length > 0, blok ini otomatis hilang dan tidak
            pernah muncul lagi di sesi yang sama - bukan AI response,
            tidak pernah memanggil backend/LLM. */}
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