// src/components/voice/VoiceCompanionPill.jsx
//
// Tombol Pill Ringkas di TopBar untuk Voice Companion
// Menampilkan status pendamping suara secara realtime dan memicu aktivasi manual.

import { useEffect, useState } from "react";
import { AlertCircle, Mic, MicOff, Volume2 } from "lucide-react";
import { COMPANION_STATES } from "../../hooks/useVoiceCompanion.js";

export default function VoiceCompanionPill() {
  const [voiceState, setVoiceState] = useState(COMPANION_STATES.STANDBY);

  useEffect(() => {
    function onStateChange(e) {
      if (e.detail?.state) {
        setVoiceState(e.detail.state);
      }
    }

    window.addEventListener("aira:voice-state-changed", onStateChange);
    return () => window.removeEventListener("aira:voice-state-changed", onStateChange);
  }, []);

  const handleClick = () => {
    window.dispatchEvent(new CustomEvent("aira:voice-toggle"));
  };

  const isListening = voiceState === COMPANION_STATES.LISTENING;
  const isSpeaking = voiceState === COMPANION_STATES.SPEAKING;
  const isProcessing = voiceState === COMPANION_STATES.PROCESSING;
  const isDisabled = voiceState === COMPANION_STATES.DISABLED;
  const isError = voiceState === COMPANION_STATES.ERROR;

  return (
    <button
      type="button"
      onClick={handleClick}
      title={
        isError
          ? "Izin mikrofon browser belum aktif — klik untuk mengizinkan & bicara"
          : isDisabled
          ? "Voice Companion nonaktif — klik untuk mengaktifkan"
          : isListening
          ? "AIRA sedang mendengarkan ucapanmu..."
          : isSpeaking
          ? "AIRA sedang menjawab..."
          : `AIRA Voice Companion Siaga (Panggil 'AIRA' atau klik tombol ini)`
      }
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition select-none ${
        isError
          ? "bg-red-500/10 border-red-500/40 text-red-300 hover:bg-red-500/20"
          : isListening
          ? "bg-cyan-500/20 border-cyan-400 text-cyan-300 shadow-sm shadow-cyan-500/30 animate-pulse"
          : isSpeaking
          ? "bg-pink-500/20 border-pink-400 text-pink-300 shadow-sm shadow-pink-500/30"
          : isProcessing
          ? "bg-purple-500/20 border-purple-400 text-purple-300"
          : isDisabled
          ? "bg-white/5 border-border text-white/40 hover:text-white/70"
          : "bg-cyan-500/10 border-cyan-500/30 text-cyan-300/80 hover:text-cyan-200 hover:border-cyan-400/50"
      }`}
    >
      {isError ? (
        <AlertCircle size={13} className="shrink-0 text-red-400 animate-pulse" />
      ) : isDisabled ? (
        <MicOff size={13} className="shrink-0" />
      ) : isSpeaking ? (
        <Volume2 size={13} className="shrink-0 animate-bounce text-pink-400" />
      ) : (
        <Mic size={13} className={`shrink-0 ${isListening ? "text-cyan-300 animate-pulse" : ""}`} />
      )}
      <span className="hidden sm:inline">
        {isError
          ? "Izinkan Mic"
          : isListening
          ? "Mendengarkan..."
          : isSpeaking
          ? "Menjawab..."
          : isProcessing
          ? "Memproses..."
          : isDisabled
          ? "Companion Off"
          : "AIRA (Standby)"}
      </span>
    </button>
  );
}
