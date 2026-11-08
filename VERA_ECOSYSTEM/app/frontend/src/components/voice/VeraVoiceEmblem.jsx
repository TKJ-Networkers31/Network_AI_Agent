// src/components/voice/VeraVoiceEmblem.jsx
//
// Emblem Suara Animasi Modern VERA (Animated Voice Intelligence Emblem)
// Terintegrasi dengan identitas visual VERA (Geometric Network Core & Electric Cyan).
//
// Status Visual:
// - STANDBY    : Kilauan napas lembut (idle glow), hemat CPU.
// - LISTENING  : Gelombang cincin berdenyut cyan & electric blue aktif.
// - PROCESSING : Cincin orbit pemrosesan berputar halus.
// - SPEAKING   : Batang equalizer dinamis yang merespons pembicaraan.
// - ERROR      : Cincin peringatan amber/merah dengan tanda status.

import { useMemo } from "react";
import BrandEmblem from "../BrandEmblem.jsx";
import { COMPANION_STATES } from "../../hooks/useVoiceCompanion.js";

export default function VeraVoiceEmblem({
  state = COMPANION_STATES.STANDBY,
  size = 64,
  onClick,
  className = "",
}) {
  const isListening = state === COMPANION_STATES.LISTENING;
  const isProcessing = state === COMPANION_STATES.PROCESSING;
  const isSpeaking = state === COMPANION_STATES.SPEAKING;
  const isError = state === COMPANION_STATES.ERROR;
  const isStandby = state === COMPANION_STATES.STANDBY;

  // Ukuran dasar container
  const boxSize = size * 1.5;

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={`VERA Voice Companion (${state})`}
      className={`relative flex items-center justify-center select-none ${
        onClick ? "cursor-pointer hover:scale-105 active:scale-95 transition-transform" : ""
      } ${className}`}
      style={{ width: boxSize, height: boxSize }}
    >
      {/* 1. Efek Cincin Gelombang Berdenyut (LISTENING) */}
      {isListening && (
        <>
          <span
            className="absolute inset-0 rounded-full border-2 border-cyan-400/40 animate-ping"
            style={{ animationDuration: "2s" }}
          />
          <span
            className="absolute inset-2 rounded-full border-2 border-blue-500/40 animate-pulse"
            style={{ animationDuration: "1.4s" }}
          />
        </>
      )}

      {/* 2. Efek Spinner Orbit (PROCESSING) */}
      {isProcessing && (
        <div
          className="absolute inset-1 rounded-full border-2 border-transparent border-t-cyan-400 border-r-blue-500 animate-spin"
          style={{ animationDuration: "1s" }}
        />
      )}

      {/* 3. Efek Equalizer Audio (SPEAKING) */}
      {isSpeaking && (
        <div className="absolute inset-0 rounded-full border border-blue-500/40 animate-pulse">
          <div className="absolute -bottom-2 inset-x-0 flex items-center justify-center gap-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <span
                key={i}
                className="w-1 rounded-full bg-gradient-to-t from-cyan-400 to-blue-500 animate-pulse"
                style={{
                  height: 12 + (i % 3) * 6,
                  animationDelay: `${i * 0.15}s`,
                  animationDuration: "0.6s",
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* 4. Efek Halo Status Error */}
      {isError && (
        <span className="absolute inset-0 rounded-full border-2 border-red-500/50 bg-red-500/10" />
      )}

      {/* 5. Efek Breathing Halus (STANDBY) */}
      {isStandby && (
        <span className="absolute inset-2 rounded-full bg-cyan-500/5 border border-cyan-400/20" />
      )}

      {/* 6. Inti Network Core VERA */}
      <div
        className={`relative flex items-center justify-center rounded-full transition-all duration-300 ${
          isListening
            ? "shadow-lg shadow-cyan-500/30 ring-2 ring-cyan-400/50"
            : isSpeaking
            ? "shadow-lg shadow-blue-500/30 ring-2 ring-blue-400/50"
            : isProcessing
            ? "shadow-md shadow-cyan-500/20"
            : "shadow-sm shadow-white/5"
        }`}
      >
        <BrandEmblem size={size} glow={isListening || isSpeaking} />
      </div>
    </div>
  );
}
