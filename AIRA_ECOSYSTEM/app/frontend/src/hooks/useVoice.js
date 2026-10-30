// src/hooks/useVoice.js
//
// Chat Speech & Listen Hook untuk Chat Interface AIRA OS
// Mengelola input ucapan (SpeechRecognition) dan keluaran suara (SpeechSynthesis)
// secara independen dari Background Voice Service, dengan arbitrase mikrofon eksplisit.

import { useCallback, useEffect, useRef, useState } from "react";
import { cleanTextForSpeech } from "./useVoiceCompanion.js";

export const MIC_STATES = {
  UNAVAILABLE: "unavailable",
  IDLE: "idle",
  REQUESTING_PERMISSION: "requesting_permission",
  LISTENING: "listening",
  PERMISSION_DENIED: "permission_denied",
  ERROR: "error",
};

export function useVoice({ onTranscript, notify } = {}) {
  const SpeechRecognitionImpl =
    typeof window !== "undefined"
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null;

  const speechSupported = Boolean(SpeechRecognitionImpl);
  const synthesisSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const [micState, setMicState] = useState(
    speechSupported ? MIC_STATES.IDLE : MIC_STATES.UNAVAILABLE
  );
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [speakEnabled, setSpeakEnabled] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const recognitionRef = useRef(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const notifyRef = useRef(notify);
  notifyRef.current = notify;

  // -------------------------------------------------------------
  // Arbitrase Mikrofon: Handoff ke Background Service & Companion
  // -------------------------------------------------------------
  const claimMic = useCallback(() => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("aira:mic-claimed", { detail: { source: "chat_speech" } })
      );
      fetch("/api/voice/service/pause", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "chat_speech_active" }),
      }).catch(() => {});
    }
  }, []);

  const releaseMic = useCallback(() => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("aira:mic-released", { detail: { source: "chat_speech" } })
      );
      fetch("/api/voice/service/resume", {
        method: "POST",
      }).catch(() => {});
    }
  }, []);

  // -------------------------------------------------------------
  // Speech Recognition (Dengar Ucapan untuk Chat Composer)
  // -------------------------------------------------------------
  const stopListening = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      // Abaikan jika sudah berhenti
    }
    setListening(false);
    setMicState(MIC_STATES.IDLE);
    setInterimText("");
    releaseMic();
  }, [releaseMic]);

  const startListening = useCallback(() => {
    if (!speechSupported) {
      setMicState(MIC_STATES.UNAVAILABLE);
      setErrorMessage("Browser ini belum mendukung pengenalan suara.");
      notifyRef.current?.({
        type: "warning",
        message:
          "Browser ini belum mendukung Web Speech API. Gunakan Chrome, Edge, atau browser berbasis Chromium.",
      });
      return;
    }

    // Jika sedang berbicara TTS, hentikan dulu sebelum merekam
    if (synthesisSupported && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
    }

    setErrorMessage("");
    setInterimText("");
    setMicState(MIC_STATES.REQUESTING_PERMISSION);

    // Klaim kepemilikan mic
    claimMic();

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }

      const recognition = new SpeechRecognitionImpl();
      recognition.lang = "id-ID";
      recognition.interimResults = true;
      recognition.continuous = false; // Satu giliran input ucapan
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setListening(true);
        setMicState(MIC_STATES.LISTENING);
      };

      recognition.onresult = (event) => {
        let finalText = "";
        let interim = "";

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const item = event.results[i];
          const transcript = item[0]?.transcript || "";
          if (item.isFinal) {
            finalText += transcript;
          } else {
            interim += transcript;
          }
        }

        if (interim) {
          setInterimText(interim);
        }

        if (finalText.trim()) {
          setInterimText("");
          onTranscriptRef.current?.(finalText.trim());
        }
      };

      recognition.onerror = (event) => {
        const err = event.error;
        if (err === "no-speech" || err === "aborted") {
          setMicState(MIC_STATES.IDLE);
          setListening(false);
          setInterimText("");
          releaseMic();
          return;
        }

        if (err === "not-allowed" || err === "service-not-allowed") {
          setMicState(MIC_STATES.PERMISSION_DENIED);
          setErrorMessage("Izin akses mikrofon ditolak oleh browser.");
          notifyRef.current?.({
            type: "error",
            message:
              "Akses mikrofon ditolak. Izinkan mikrofon di pengaturan browser untuk mendikte pesan.",
          });
        } else if (err === "audio-capture") {
          setMicState(MIC_STATES.ERROR);
          setErrorMessage("Perangkat mikrofon tidak terdeteksi atau sedang sibuk.");
          notifyRef.current?.({
            type: "error",
            message: "Mikrofon tidak terdeteksi atau sedang dipakai aplikasi lain.",
          });
        } else if (err === "network") {
          setMicState(MIC_STATES.ERROR);
          setErrorMessage("Koneksi jaringan pengenalan suara terputus.");
          notifyRef.current?.({
            type: "error",
            message: "Layanan pengenalan suara browser butuh koneksi internet aktif.",
          });
        } else {
          setMicState(MIC_STATES.ERROR);
          setErrorMessage(`Kendala pengenalan suara: ${err}`);
          notifyRef.current?.({
            type: "error",
            message: `Kendala pengenalan suara (${err}).`,
          });
        }

        setListening(false);
        releaseMic();
      };

      recognition.onend = () => {
        setListening(false);
        setMicState(MIC_STATES.IDLE);
        setInterimText("");
        releaseMic();
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (exc) {
      setMicState(MIC_STATES.ERROR);
      setErrorMessage(`Gagal memulai rekaman suara: ${exc?.message || exc}`);
      setListening(false);
      releaseMic();
    }
  }, [speechSupported, synthesisSupported, SpeechRecognitionImpl, claimMic, releaseMic]);

  const toggleListening = useCallback(() => {
    if (listening) {
      stopListening();
    } else {
      startListening();
    }
  }, [listening, startListening, stopListening]);

  // -------------------------------------------------------------
  // Speech Synthesis (Bicara Jawaban Assistant)
  // -------------------------------------------------------------
  const stopSpeaking = useCallback(() => {
    if (synthesisSupported) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    setSpeaking(false);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("aira:tts-end"));
    }
  }, [synthesisSupported]);

  const speak = useCallback(
    (text) => {
      if (!speakEnabled || !text || !synthesisSupported) return;

      const cleaned = cleanTextForSpeech(text);
      if (!cleaned) return;

      try {
        window.speechSynthesis.cancel();
      } catch {}

      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.lang = "id-ID";
      utterance.rate = 1.0;

      // Cari voice bahasa Indonesia jika tersedia
      const voices = window.speechSynthesis.getVoices();
      const idVoice = voices.find(
        (v) =>
          v.lang?.toLowerCase().startsWith("id") ||
          v.name?.toLowerCase().includes("indonesia")
      );
      if (idVoice) {
        utterance.voice = idVoice;
      }

      utterance.onstart = () => {
        setSpeaking(true);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("aira:tts-start"));
        }
      };

      utterance.onend = () => {
        setSpeaking(false);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("aira:tts-end"));
        }
      };

      utterance.onerror = () => {
        setSpeaking(false);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("aira:tts-end"));
        }
      };

      window.speechSynthesis.speak(utterance);
    },
    [speakEnabled, synthesisSupported]
  );

  const toggleSpeak = useCallback(() => {
    const next = !speakEnabled;
    setSpeakEnabled(next);

    if (!next) {
      stopSpeaking();
    }

    notifyRef.current?.({
      type: "info",
      message: next
        ? "Mode bicara aktif — jawaban assistant akan dibacakan otomatis."
        : "Mode bicara dinonaktifkan.",
      duration: 2500,
    });
  }, [speakEnabled, stopSpeaking]);

  // Cleanup saat unmount
  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {}
      if (synthesisSupported) {
        try {
          window.speechSynthesis.cancel();
        } catch {}
      }
    };
  }, [synthesisSupported]);

  return {
    supported: speechSupported,
    synthesisSupported,
    micState,
    listening,
    interimText,
    speaking,
    speakEnabled,
    errorMessage,
    startListening,
    stopListening,
    toggleListening,
    speak,
    stopSpeaking,
    toggleSpeak,
  };
}
