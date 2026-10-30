import AiraVoiceEmblem from "./voice/AiraVoiceEmblem.jsx";
import { COMPANION_STATES } from "../hooks/useVoiceCompanion.js";
import { VOICE_DIAGNOSTICS } from "../hooks/useVoiceCall.js";
import { AlertCircle, Mic, ShieldAlert, Volume2 } from "lucide-react";

export default function VoiceOverlay({
  connecting,
  interimText,
  subtitle,
  speaking,
  waitingReply,
  onCancel,
  diagnosticState = VOICE_DIAGNOSTICS.IDLE,
  audioLevel = 0,
  deviceLabel = "",
  errorMessage = "",
}) {
  const currentState = connecting
    ? COMPANION_STATES.PROCESSING
    : speaking
    ? COMPANION_STATES.SPEAKING
    : waitingReply
    ? COMPANION_STATES.PROCESSING
    : COMPANION_STATES.LISTENING;

  let statusLabel = "Mendengarkan...";
  let statusBadgeClass = "bg-sky-500/20 text-sky-300 border-sky-500/40";

  switch (diagnosticState) {
    case VOICE_DIAGNOSTICS.REQUESTING_PERMISSION:
      statusLabel = "Meminta Izin Mikrofon...";
      statusBadgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/40";
      break;
    case VOICE_DIAGNOSTICS.READY:
      statusLabel = "Mikrofon Siap";
      statusBadgeClass = "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
      break;
    case VOICE_DIAGNOSTICS.SPEECH_DETECTED:
      statusLabel = "Suara Terdeteksi";
      statusBadgeClass = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      break;
    case VOICE_DIAGNOSTICS.PROCESSING:
      statusLabel = "Memproses Transkripsi...";
      statusBadgeClass = "bg-purple-500/20 text-purple-300 border-purple-500/40";
      break;
    case VOICE_DIAGNOSTICS.TRANSCRIPT_RECEIVED:
      statusLabel = "AIRA Menjawab...";
      statusBadgeClass = "bg-indigo-500/20 text-indigo-300 border-indigo-500/40";
      break;
    case VOICE_DIAGNOSTICS.PERMISSION_DENIED:
      statusLabel = "Izin Mikrofon Ditolak";
      statusBadgeClass = "bg-red-500/20 text-red-300 border-red-500/40";
      break;
    case VOICE_DIAGNOSTICS.NO_INPUT_DETECTED:
      statusLabel = "Tidak Ada Suara Terdeteksi";
      statusBadgeClass = "bg-amber-500/20 text-amber-300 border-amber-500/40";
      break;
    case VOICE_DIAGNOSTICS.ERROR:
      statusLabel = "Kendala Mikrofon";
      statusBadgeClass = "bg-red-500/20 text-red-300 border-red-500/40";
      break;
    default:
      if (connecting) {
        statusLabel = "Menyambungkan...";
        statusBadgeClass = "bg-purple-500/20 text-purple-300 border-purple-500/40";
      } else if (speaking) {
        statusLabel = "AIRA Menjawab...";
        statusBadgeClass = "bg-indigo-500/20 text-indigo-300 border-indigo-500/40";
      } else if (waitingReply) {
        statusLabel = "Memproses...";
        statusBadgeClass = "bg-purple-500/20 text-purple-300 border-purple-500/40";
      }
      break;
  }

  const bodyText = errorMessage
    ? errorMessage
    : connecting
    ? "Menyiapkan sesi suara, tunggu sebentar."
    : speaking
    ? subtitle
    : waitingReply
    ? "Menunggu balasan AIRA..."
    : diagnosticState === VOICE_DIAGNOSTICS.NO_INPUT_DETECTED
    ? "Tidak ada suara yang terdengar dalam beberapa detik terakhir. Coba bicara lebih dekat ke mikrofon."
    : diagnosticState === VOICE_DIAGNOSTICS.PERMISSION_DENIED
    ? "Akses ke mikrofon ditolak oleh browser. Buka pengaturan izin situs untuk mengaktifkan."
    : interimText || "Silakan bicara — utterance otomatis dikirim setelah kamu berhenti sejenak.";

  return (
    <div className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-black/85 backdrop-blur-md px-6 select-none">
      {/* Emblem Animasi */}
      <div className="mb-4 flex items-center justify-center">
        <AiraVoiceEmblem state={currentState} size={80} />
      </div>

      {/* Status Badge */}
      <div className={`px-3 py-1 rounded-full border text-xs font-semibold mb-3 flex items-center gap-1.5 ${statusBadgeClass}`}>
        <Volume2 size={13} className={speaking || diagnosticState === VOICE_DIAGNOSTICS.SPEECH_DETECTED ? "animate-bounce" : ""} />
        <span>{statusLabel}</span>
      </div>

      {/* Active Audio VU Meter */}
      <div className="w-56 h-2 bg-white/10 rounded-full overflow-hidden my-2 border border-white/10">
        <div
          className="h-full bg-gradient-to-r from-sky-400 via-emerald-400 to-purple-400 transition-all duration-75 rounded-full"
          style={{ width: `${Math.min(100, Math.max(audioLevel, 4))}%` }}
        />
      </div>

      {/* Device Info */}
      {deviceLabel && (
        <div className="flex items-center gap-1.5 text-[11px] text-white/40 font-mono mb-2">
          <Mic size={12} className="text-sky-400" />
          <span>{deviceLabel}</span>
        </div>
      )}

      {/* Caption / Helper Text */}
      <p className="text-white/80 text-sm max-w-md text-center min-h-[2.5rem] leading-relaxed px-4 my-2">
        {bodyText}
      </p>

      {/* Troubleshooting Hint when Silence or Denied */}
      {diagnosticState === VOICE_DIAGNOSTICS.NO_INPUT_DETECTED && (
        <div className="mt-2 text-[11px] text-amber-300/80 bg-amber-500/10 border border-amber-500/20 px-3 py-1.5 rounded-xl max-w-sm text-center">
          Pastikan mikrofon laptop tidak di-mute secara fisik (tombol FN / saklar).
        </div>
      )}

      {diagnosticState === VOICE_DIAGNOSTICS.PERMISSION_DENIED && (
        <div className="mt-2 text-[11px] text-red-300/80 bg-red-500/10 border border-red-500/20 px-3 py-1.5 rounded-xl max-w-sm text-center flex items-center gap-1">
          <ShieldAlert size={14} />
          <span>Klik ikon gembok di sebelah URL browser dan izinkan "Microphone".</span>
        </div>
      )}

      {/* Exit Button */}
      <button
        onClick={onCancel}
        className="mt-8 px-6 py-2.5 rounded-full border border-white/20 bg-white/5 hover:bg-white/10 text-white/70 hover:text-white hover:border-red-400/50 text-sm font-medium transition"
      >
        Akhiri sesi suara
      </button>
    </div>
  );
}
