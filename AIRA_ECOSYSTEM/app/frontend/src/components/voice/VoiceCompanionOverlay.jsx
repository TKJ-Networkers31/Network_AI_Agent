// src/components/voice/VoiceCompanionOverlay.jsx
//
// Overlay Visual Interaktif Pendamping Suara AIRA (Voice Companion Overlay)
// Menampilkan emblem animasi, live captions pengguna & AIRA, kartu eksekusi aksi UI,
// status state machine, serta kontrol manual (barge-in, aktivasi mic, tutup sesi).

import { useState } from "react";
import {
  Mic,
  MicOff,
  Square,
  X,
  Volume2,
  VolumeX,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Subtitles,
} from "lucide-react";
import AiraVoiceEmblem from "./AiraVoiceEmblem.jsx";
import { COMPANION_STATES } from "../../hooks/useVoiceCompanion.js";

const STATE_CONFIG = {
  [COMPANION_STATES.DISABLED]: {
    label: "Nonaktif",
    color: "text-white/40",
    bg: "bg-white/5 border-white/10",
  },
  [COMPANION_STATES.STANDBY]: {
    label: "Standby (Menunggu 'AIRA')",
    color: "text-cyan-400",
    bg: "bg-cyan-500/10 border-cyan-500/30",
  },
  [COMPANION_STATES.LISTENING]: {
    label: "Mendengarkan...",
    color: "text-cyan-300",
    bg: "bg-cyan-500/20 border-cyan-400/50",
  },
  [COMPANION_STATES.PROCESSING]: {
    label: "Memproses Permintaan...",
    color: "text-purple-300",
    bg: "bg-purple-500/20 border-purple-400/50",
  },
  [COMPANION_STATES.SPEAKING]: {
    label: "AIRA Menjawab...",
    color: "text-pink-300",
    bg: "bg-pink-500/20 border-pink-400/50",
  },
  [COMPANION_STATES.ERROR]: {
    label: "Kendala Suara",
    color: "text-red-400",
    bg: "bg-red-500/20 border-red-500/40",
  },
};

export default function VoiceCompanionOverlay({
  state = COMPANION_STATES.STANDBY,
  userTranscript = "",
  interimTranscript = "",
  airaResponse = "",
  actionCard = null,
  errorMessage = "",
  captionsVisible = true,
  onToggleCaptions,
  onActivateMic,
  onStopSpeaking,
  onClose,
}) {
  const [isMinimized, setIsMinimized] = useState(false);
  const cfg = STATE_CONFIG[state] || STATE_CONFIG[COMPANION_STATES.STANDBY];

  const isSpeaking = state === COMPANION_STATES.SPEAKING;
  const isListening = state === COMPANION_STATES.LISTENING;
  const isProcessing = state === COMPANION_STATES.PROCESSING;

  const currentSpeechText = interimTranscript || userTranscript;

  return (
    <div
      className={`fixed z-[85] transition-all duration-300 pointer-events-auto ${
        isMinimized
          ? "bottom-4 right-4"
          : "bottom-4 right-4 max-w-sm sm:max-w-md w-[calc(100vw-2rem)]"
      }`}
    >
      <div className="relative rounded-2xl bg-[#0c1222]/95 backdrop-blur-xl border border-white/10 shadow-2xl overflow-hidden p-4">
        {/* Header Bar */}
        <div className="flex items-center justify-between gap-2 pb-3 border-b border-white/[0.08] mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-xs font-semibold text-white/90 tracking-wide">
              AIRA Voice Companion
            </span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full border ${cfg.bg} ${cfg.color} font-medium truncate`}
            >
              {cfg.label}
            </span>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {onToggleCaptions && (
              <button
                type="button"
                onClick={onToggleCaptions}
                title={captionsVisible ? "Sembunyikan teks caption" : "Tampilkan teks caption"}
                className={`p-1.5 rounded-lg border text-xs transition ${
                  captionsVisible
                    ? "bg-white/10 border-white/20 text-cyan-300"
                    : "bg-white/5 border-border text-white/50 hover:text-white"
                }`}
              >
                <Subtitles size={13} />
              </button>
            )}

            <button
              type="button"
              onClick={() => setIsMinimized((v) => !v)}
              title={isMinimized ? "Perbesar panel" : "Perkecil panel"}
              className="p-1.5 rounded-lg bg-white/5 border border-border text-white/50 hover:text-white text-xs transition"
            >
              {isMinimized ? "▲" : "▼"}
            </button>

            <button
              type="button"
              onClick={onClose}
              title="Tutup pendamping suara"
              className="p-1.5 rounded-lg bg-white/5 border border-border text-white/50 hover:text-red-400 text-xs transition"
            >
              <X size={13} />
            </button>
          </div>
        </div>

        {/* Content Area */}
        {!isMinimized && (
          <div className="space-y-3">
            {/* Center Area: Animated Emblem */}
            <div className="flex items-center justify-center py-2">
              <AiraVoiceEmblem
                state={state}
                size={54}
                onClick={isSpeaking ? onStopSpeaking : onActivateMic}
              />
            </div>

            {/* Error Message Alert */}
            {state === COMPANION_STATES.ERROR && errorMessage && (
              <div className="flex items-start gap-2 p-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-200">
                <AlertCircle size={15} className="shrink-0 mt-0.5 text-red-400" />
                <p className="leading-relaxed">{errorMessage}</p>
              </div>
            )}

            {/* Live Captions */}
            {captionsVisible && (
              <div className="space-y-2">
                {/* User Speech Caption */}
                {currentSpeechText && (
                  <div className="p-2.5 rounded-xl bg-white/[0.04] border border-white/[0.08] text-xs">
                    <div className="flex items-center gap-1.5 text-white/40 font-medium mb-1">
                      <Mic size={12} className="text-cyan-400" />
                      <span>Kamu:</span>
                    </div>
                    <p
                      className={`leading-relaxed ${
                        interimTranscript ? "text-cyan-200/80 italic" : "text-white font-medium"
                      }`}
                    >
                      &ldquo;{currentSpeechText}&rdquo;
                    </p>
                  </div>
                )}

                {/* Action Execution Card */}
                {actionCard && (
                  <div className="p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {actionCard.status === "executing" ? (
                          <Loader2 size={13} className="text-cyan-400 animate-spin shrink-0" />
                        ) : actionCard.status === "success" ? (
                          <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                        ) : (
                          <AlertCircle size={13} className="text-red-400 shrink-0" />
                        )}
                        <span className="font-semibold text-cyan-200 truncate">
                          {actionCard.title}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                          actionCard.status === "success"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : actionCard.status === "executing"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                            : "bg-red-500/20 text-red-300 border border-red-500/30"
                        }`}
                      >
                        {actionCard.status === "success"
                          ? "Sukses"
                          : actionCard.status === "executing"
                          ? "Berjalan"
                          : "Gagal"}
                      </span>
                    </div>
                  </div>
                )}

                {/* AIRA Response Caption */}
                {airaResponse && (
                  <div className="p-2.5 rounded-xl bg-purple-950/25 border border-purple-500/30 text-xs">
                    <div className="flex items-center gap-1.5 text-purple-300/60 font-medium mb-1">
                      <Sparkles size={12} className="text-purple-400" />
                      <span>AIRA:</span>
                    </div>
                    <p className="text-purple-100/90 leading-relaxed font-normal">
                      {airaResponse}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Quick Action Controls */}
            <div className="flex items-center justify-between gap-2 pt-2 border-t border-white/[0.08]">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={onActivateMic}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition ${
                    isListening
                      ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-300 animate-pulse"
                      : "bg-white/5 border-border text-white/70 hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Mic size={13} />
                  <span>{isListening ? "Mendengarkan..." : "Bicara"}</span>
                </button>

                {isSpeaking && (
                  <button
                    type="button"
                    onClick={onStopSpeaking}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/40 text-red-300 text-xs font-medium hover:bg-red-500/30 transition"
                  >
                    <Square size={12} className="fill-current" />
                    <span>Stop</span>
                  </button>
                )}
              </div>

              <div className="text-[10px] text-white/40 truncate text-right">
                Katakan &ldquo;AIRA&rdquo; atau &ldquo;bye&rdquo;
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
