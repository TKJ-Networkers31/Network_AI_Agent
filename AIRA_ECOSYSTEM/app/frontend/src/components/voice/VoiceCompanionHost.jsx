// src/components/voice/VoiceCompanionHost.jsx
//
// Host Global Voice Companion di level root App
// Menghubungkan useVoiceCompanion dengan Global Settings, navigasi halaman,
// pesan sistem, dan merender VoiceCompanionOverlay.

import { useCallback, useEffect } from "react";
import { useGlobalSettings } from "../../hooks/useGlobalSettings.js";
import { useChatRuntime } from "../../context/ChatRuntimeContext.jsx";
import { useToast } from "../Toast.jsx";
import { useVoiceCompanion, COMPANION_STATES } from "../../hooks/useVoiceCompanion.js";
import VoiceCompanionOverlay from "./VoiceCompanionOverlay.jsx";

export default function VoiceCompanionHost({ onNavigate }) {
  const settings = useGlobalSettings();
  const { notify } = useToast();

  const voiceEnabled = settings?.voice_enabled !== false;
  const wakeWordEnabled =
    typeof window !== "undefined" && localStorage.getItem("aira_voice_wake_word") !== null
      ? localStorage.getItem("aira_voice_wake_word") === "1"
      : settings?.voice_wake_word_enabled !== false;

  const savedTimeoutSec =
    typeof window !== "undefined" ? parseInt(localStorage.getItem("aira_voice_timeout"), 10) : NaN;
  const inactivitySec = Number.isFinite(savedTimeoutSec) && savedTimeoutSec > 0
    ? savedTimeoutSec
    : parseInt(settings?.voice_inactivity_timeout_sec, 10);

  const timeoutMs = Number.isFinite(inactivitySec) && inactivitySec > 0
    ? inactivitySec * 1000
    : 120_000;

  const savedRate =
    typeof window !== "undefined" ? parseFloat(localStorage.getItem("aira_voice_speech_rate")) : NaN;
  const speechRate = Number.isFinite(savedRate) && savedRate > 0
    ? savedRate
    : parseFloat(settings?.voice_speech_rate) || 1.0;

  const handleNavigate = useCallback(
    (target) => {
      if (onNavigate) {
        onNavigate(target);
      } else {
        window.dispatchEvent(
          new CustomEvent("aira:navigate", { detail: target })
        );
      }
    },
    [onNavigate]
  );

  const { sendMessage } = useChatRuntime();

  const handleChatQuery = useCallback(
    async (prompt) => {
      if (sendMessage) {
        try {
          await sendMessage(prompt);
          return "Permintaan berhasil dikirim ke AIRA.";
        } catch (err) {
          return "Maaf, kendala komunikasi: " + (err?.message || err);
        }
      }
      return "Sesi chat belum terhubung.";
    },
    [sendMessage]
  );

  const companion = useVoiceCompanion({
    enabled: voiceEnabled,
    wakeWordEnabled,
    inactivityTimeoutMs: timeoutMs,
    speechRate,
    onNavigate: handleNavigate,
    onChatQuery: handleChatQuery,
    notify,
  });

  // Siarkan perubahan status companion ke seluruh aplikasi
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("aira:voice-state-changed", {
        detail: { state: companion.state, overlayVisible: companion.overlayVisible },
      })
    );
  }, [companion.state, companion.overlayVisible]);

  // Dengarkan event toggle / aktivasi manual dari UI
  useEffect(() => {
    function onToggle() {
      companion.toggleOverlay();
    }

    function onActivate() {
      companion.activateManually();
    }

    window.addEventListener("aira:voice-toggle", onToggle);
    window.addEventListener("aira:voice-activate", onActivate);

    return () => {
      window.removeEventListener("aira:voice-toggle", onToggle);
      window.removeEventListener("aira:voice-activate", onActivate);
    };
  }, [companion]);

  if (!companion.overlayVisible && companion.state === COMPANION_STATES.STANDBY) {
    return null;
  }

  if (!companion.overlayVisible && companion.state === COMPANION_STATES.DISABLED) {
    return null;
  }

  return (
    <VoiceCompanionOverlay
      state={companion.state}
      userTranscript={companion.userTranscript}
      interimTranscript={companion.interimTranscript}
      airaResponse={companion.airaResponse}
      actionCard={companion.actionCard}
      errorMessage={companion.errorMessage}
      captionsVisible={companion.captionsVisible}
      onToggleCaptions={() => companion.setCaptionsVisible((v) => !v)}
      onActivateMic={companion.activateManually}
      onStopSpeaking={companion.stopSpeaking}
      onClose={companion.deactivateCompanion}
    />
  );
}
