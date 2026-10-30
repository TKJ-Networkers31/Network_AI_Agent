// src/components/VoiceControls.jsx
import { AlertCircle, Loader2, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { MIC_STATES } from "../hooks/useVoice.js";

export default function VoiceControls({
  supported = true,
  listening = false,
  speaking = false,
  speakEnabled = false,
  micState = MIC_STATES.IDLE,
  errorMessage = "",
  onToggleListen,
  onToggleSpeak,
}) {
  const isRequesting = micState === MIC_STATES.REQUESTING_PERMISSION;
  const isDenied = micState === MIC_STATES.PERMISSION_DENIED;
  const isError = micState === MIC_STATES.ERROR;
  const isUnavailable = !supported || micState === MIC_STATES.UNAVAILABLE;

  const micTitle = isUnavailable
    ? "Browser ini belum mendukung pengenalan suara"
    : isDenied
    ? "Izin akses mikrofon ditolak — klik untuk mencoba lagi"
    : isError
    ? errorMessage || "Kendala mikrofon — klik untuk mencoba lagi"
    : isRequesting
    ? "Meminta izin akses mikrofon browser..."
    : listening
    ? "Sedang mendengarkan... klik untuk selesai & kirim teks"
    : "Bicara ke agent (klik untuk mendikte ucapan ke chat)";

  const speakTitle = speaking
    ? "Sedang membacakan jawaban — klik untuk berhenti"
    : speakEnabled
    ? "Mode baca aktif — jawaban agent dibacakan otomatis (klik untuk matikan)"
    : "Mode baca mati — klik untuk membacakan jawaban agent";

  return (
    <div className="flex items-center gap-1.5 shrink-0">
      {/* Tombol Dikte Suara (Microphone) */}
      <button
        type="button"
        onClick={onToggleListen}
        disabled={isUnavailable}
        title={micTitle}
        aria-label={micTitle}
        aria-pressed={listening}
        className={`relative w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all duration-200 select-none
          ${
            listening
              ? "bg-red-500/20 border-red-400 text-red-300 shadow-sm shadow-red-500/30"
              : isRequesting
              ? "bg-amber-500/20 border-amber-400 text-amber-300 animate-pulse"
              : isDenied || isError
              ? "bg-red-500/10 border-red-500/40 text-red-400 hover:bg-red-500/20"
              : "bg-white/5 border-white/10 text-white/60 hover:text-cyan-300 hover:bg-cyan-500/10 hover:border-cyan-500/30"
          }
          disabled:opacity-30 disabled:cursor-not-allowed`}
      >
        {listening && (
          <span className="absolute inset-0 rounded-xl bg-red-400/30 animate-ping pointer-events-none" />
        )}
        {isRequesting ? (
          <Loader2 size={16} className="animate-spin text-amber-300" />
        ) : isDenied || isError ? (
          <AlertCircle size={16} className="text-red-400" />
        ) : isUnavailable ? (
          <MicOff size={16} className="text-white/30" />
        ) : (
          <Mic size={16} className={`relative ${listening ? "text-red-300" : ""}`} />
        )}
      </button>

      {/* Tombol Bacakan Jawaban (Speaker/TTS) */}
      <button
        type="button"
        onClick={onToggleSpeak}
        title={speakTitle}
        aria-label={speakTitle}
        aria-pressed={speakEnabled}
        className={`relative w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-xl border transition-all duration-200 select-none
          ${
            speaking
              ? "bg-pink-500/20 border-pink-400 text-pink-300 shadow-sm shadow-pink-500/30 animate-pulse"
              : speakEnabled
              ? "bg-cyan-500/20 border-cyan-400 text-cyan-300"
              : "bg-white/5 border-white/10 text-white/50 hover:text-white/80 hover:bg-white/10"
          }`}
      >
        {speaking ? (
          <Volume2 size={16} className="text-pink-300 animate-bounce" />
        ) : speakEnabled ? (
          <Volume2 size={16} className="text-cyan-300" />
        ) : (
          <VolumeX size={16} className="text-white/40" />
        )}
      </button>
    </div>
  );
}
