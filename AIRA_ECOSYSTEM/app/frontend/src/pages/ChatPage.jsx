// AIRA_ECOSYSTEM/app/frontend/src/pages/ChatPage.jsx
//
// (Riwayat perubahan Sprint 2.5 dipertahankan: streaming, thinking, session, dst.)
//
// PERUBAHAN (Sprint 2.6 / W5 - Integrasi Cockpit):
// - <WorkspaceCockpit> dipasang tepat di bawah TopBar (menempel ke TopBar lewat
//   margin negatif; area pesan dan input tidak berubah).
// - Satu-satunya sapaan = DynamicHero, dari Greeting Resolver W4:
//     Global Settings -> useGlobalSettings -> resolveGreetingModel -> heroModel
//     -> WorkspaceCockpit -> DynamicHero
//   Hero.jsx (emblem + prompt cepat) tidak lagi menerima `greeting`; buildGreeting()
//   lama tidak dipanggil dari sini (greeting.js tetap ada sebagai fallback di resolver).
// - Data cockpit dari useCockpitData(): snapshot koneksi sekali + refresh berbasis
//   event (tanpa polling), runtime dari ChatRuntimeContext yang sudah ada.
// - Hero cockpit hanya tampil saat percakapan kosong DAN Settings sudah selesai
//   dimuat (tidak ada kedip greeting sebelum nama terisi).
// - TopBar menyembunyikan ConnectionIndicator (informasinya sudah ada di ConnectionDock).
//
// PERUBAHAN (Sprint 2.6 - Composer Cockpit UI fix):
// - Instrument row (ConnectionDock/WorkspaceStatus/ToolDock) DIPINDAH dari
//   bawah TopBar ke tepat di atas ChatInput lewat <ComposerCockpit>, supaya
//   AIRA terasa seperti copilot (composer-centric), bukan dashboard.
// - DynamicHero (teks sapaan) TETAP di area percakapan, tampil bersama
//   emblem <Hero> saat percakapan kosong - urutan dan kondisi tampilnya
//   (heroVisible/heroReady) tidak berubah.
// - WorkspaceCockpit.jsx TIDAK dihapus (masih dipertahankan untuk kompatibilitas
//   kalau dipakai di tempat lain); ChatPage sekarang memakai ComposerCockpit.

import { useEffect, useMemo, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import MessageBubble from "../components/MessageBubble.jsx";
import ChatInput from "../components/ChatInput.jsx";
import VoiceControls from "../components/VoiceControls.jsx";
import VoiceOverlay from "../components/VoiceOverlay.jsx";
import LiveSteps from "../components/LiveSteps.jsx";
import BootScreen from "../components/BootScreen.jsx";
import ComposerCockpit from "../components/cockpit/ComposerCockpit.jsx";
import DynamicHero from "../components/cockpit/DynamicHero.jsx";
import { api } from "../api.js";
import { useSessionsContext } from "../context/SessionsContext.jsx";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { useVoiceCall } from "../hooks/useVoiceCall.js";
import { useGlobalSettings } from "../hooks/useGlobalSettings.js";
import { useCockpitData } from "../hooks/useCockpitData.js";
import { navigateForTool } from "../utils/cockpitAdapter.js";
import { resolveGreetingModel } from "../utils/greetingResolver.js";
import { shouldShowLiveSteps } from "../utils/runLifecycle.js";
import Hero from "../Hero.jsx";

export default function ChatPage({ onOpenMenu }) {
  const { sessions, activeId, setActiveId, loadSessions, sessionsReady } =
    useSessionsContext();

  const {
    messages,
    loading,
    phase,
    liveTools,
    streaming,
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
    ensureSession,
  } = useChatRuntime();

  const [tools, setTools] = useState([]);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const bottomRef = useRef(null);

  const { notify } = useToast();

  // ---- Sprint 2.6: settings + cockpit + hero model -------------------------
  const settings = useGlobalSettings(); // null = belum dimuat, {} = gagal, {...} = snapshot
  const cockpit = useCockpitData();

  const heroVisible = !switching && messages.length === 0 && !loading;
  const heroReady = settings !== null;

  // heroVisible ikut dependency supaya periode ("pagi"/"siang"/...) dihitung ulang
  // setiap kali sapaan ditampilkan lagi (mis. New Chat), tanpa timer.
  const heroModel = useMemo(
    () =>
      resolveGreetingModel({
        settings,
        persona,
        workspace: null, // belum ada konsep "workspace aktif" di sistem (FSE selalu aktif)
        connections: cockpit.activeConnectionCount,
        activity: cockpit.activity,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [settings, persona, cockpit.activeConnectionCount, cockpit.activity, heroVisible]
  );

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
    bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
  }, [messages, loading, streaming]);

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

    // Worker 3 (Location): location_permission tidak punya entri di
    // schema.actions (tombolnya dirender sendiri oleh field-nya), jadi
    // cancelled/displayText di-special-case untuk dua action id ini.
    const cancelled =
      actionId === "deny_location" ? true : action ? action.style === "ghost" : false;

    const displayText =
      actionId === "grant_location"
        ? "📍 Lokasi diberikan."
        : actionId === "deny_location"
        ? "🚫 Izin lokasi ditolak."
        : cancelled
        ? "❌ Dibatalkan."
        : "📝 Form terkirim.";

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

    // Klik beruntun saat masih menyambung diabaikan (cegah sesi ganda).
    if (voiceConnecting) return;

    setVoiceConnecting(true);

    try {
      await ensureSession({
        onNewSession: (newId) => {
          setActiveId(newId);
          loadSessions?.();
        },
      });

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
        hideConnectionIndicator
      />

      {/* Area pesan: full-width (scrollbar di tepi kanan), konten di tengah */}
      <div className="flex-1 overflow-y-auto min-h-0 -mx-3 sm:-mx-5 lg:-mx-6 px-3 sm:px-5 lg:px-6">
        <div className="max-w-4xl mx-auto w-full space-y-3 sm:space-y-4 pb-3">
          {switching && (
            <p className="text-white/30 text-sm text-center mt-10">
              Memuat percakapan...
            </p>
          )}

          {/* Sapaan tetap di area percakapan (bukan di composer) */}
          {heroVisible && heroReady && <DynamicHero heroModel={heroModel} />}
          {heroVisible && <Hero onQuickPrompt={(text) => handleSend(text)} />}

          {!switching &&
            messages.map((m, i) => (
              <MessageBubble
                key={`${activeId || "baru"}-${i}`}
                role={m.role}
                content={m.content}
                steps={m.steps}
                isNew={m.isNew}
                local={m.local}
                streaming={Boolean(m.streaming)}
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

          {shouldShowLiveSteps({ loading, phase, liveTools }) && (
            <div className="flex justify-start">
              <LiveSteps phase={phase} liveTools={liveTools} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer: Composer Cockpit (compact instrument row) menempel
          langsung di atas ChatInput - satu unit visual, bukan header
          terpisah dari conversation. */}
      <ComposerCockpit
        connections={cockpit.connections}
        activity={cockpit.activity}
        tools={cockpit.tools}
        onToolSelect={navigateForTool}
      />

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