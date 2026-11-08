// src/hooks/useVoiceCompanion.js
//
// Mesin Status & Orkestrasi AIRA Voice Companion
// Mengelola siklus hidup suara: DISABLED -> STANDBY -> LISTENING -> PROCESSING -> SPEAKING -> ERROR
// Mengimplementasikan deteksi wake-word "AIRA" (dengan toleransi fonetik STT bahasa Indonesia),
// timeout inaktivitas 2 menit, audio chime instan, debounced auto-restart Chromium,
// barge-in, navigasi UI otomatis, dan live captions.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  containsWakeWord,
  isPureWakeWord,
  routeVoiceCommand,
  stripWakeWord,
} from "../utils/voiceCommandRouter.js";

export const COMPANION_STATES = {
  DISABLED: "DISABLED",
  STANDBY: "STANDBY",
  LISTENING: "LISTENING",
  PROCESSING: "PROCESSING",
  SPEAKING: "SPEAKING",
  ERROR: "ERROR",
};

const DEFAULT_INACTIVITY_TIMEOUT_MS = 120_000; // 2 menit

/**
 * Pembersih teks untuk TTS agar tidak membacakan sintaks Markdown / code blocks secara harfiah
 */
export function cleanTextForSpeech(text) {
  if (!text || typeof text !== "string") return "";
  return text
    .replace(/```[\s\S]*?```/g, " ") // Hapus blok kode
    .replace(/`([^`]+)`/g, "$1")     // Hapus backtick inline
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1") // Ubah markdown link jadi teks
    .replace(/[#*_~>]/g, "")         // Hapus simbol markdown
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Memainkan nada chime lembut 2-nada (Web Audio API) saat wake word "AIRA" terdeteksi
 */
export function playWakeChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, t); // D5
    osc.frequency.exponentialRampToValueAtTime(880, t + 0.12); // A5

    gain.gain.setValueAtTime(0.18, t);
    gain.gain.exponentialRampToValueAtTime(0.01, t + 0.28);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.28);
    setTimeout(() => {
      try {
        ctx.close();
      } catch {}
    }, 400);
  } catch {}
}

export function useVoiceCompanion({
  enabled = true,
  wakeWordEnabled = true,
  inactivityTimeoutMs = DEFAULT_INACTIVITY_TIMEOUT_MS,
  speechRate = 1.0,
  onNavigate,
  onChatQuery,
  notify,
} = {}) {
  const [companionState, setCompanionState] = useState(
    enabled ? COMPANION_STATES.STANDBY : COMPANION_STATES.DISABLED
  );
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [userTranscript, setUserTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [airaResponse, setAiraResponse] = useState("");
  const [actionCard, setActionCard] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [captionsVisible, setCaptionsVisible] = useState(true);

  const recognitionRef = useRef(null);
  const isListeningIntentRef = useRef(false);
  const isPausedRef = useRef(false);
  const consecutiveRestartsRef = useRef(0);
  const restartTimerRef = useRef(null);
  const inactivityTimerRef = useRef(null);
  const activeUtteranceRef = useRef(null);
  const speakingWatchdogRef = useRef(null);
  const stateRef = useRef(companionState);
  stateRef.current = companionState;

  const overlayVisibleRef = useRef(overlayVisible);
  overlayVisibleRef.current = overlayVisible;

  const onNavigateRef = useRef(onNavigate);
  onNavigateRef.current = onNavigate;

  const onChatQueryRef = useRef(onChatQuery);
  onChatQueryRef.current = onChatQuery;

  const notifyRef = useRef(notify);
  notifyRef.current = notify;

  const SpeechRecognitionImpl =
    typeof window !== "undefined"
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null;

  const isSpeechSupported = Boolean(SpeechRecognitionImpl);
  const isSynthesisSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  // -------------------------------------------------------------
  // Reset / Kelola Inactivity Timer (Default 2 Menit)
  // -------------------------------------------------------------
  const resetInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }

    if (
      stateRef.current === COMPANION_STATES.LISTENING ||
      stateRef.current === COMPANION_STATES.PROCESSING ||
      stateRef.current === COMPANION_STATES.SPEAKING
    ) {
      inactivityTimerRef.current = setTimeout(() => {
        if (stateRef.current !== COMPANION_STATES.DISABLED) {
          setCompanionState(COMPANION_STATES.STANDBY);
          stateRef.current = COMPANION_STATES.STANDBY;
          setOverlayVisible(false);
          setInterimTranscript("");
          if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
          try {
            recognitionRef.current?.stop();
          } catch {}
          isListeningIntentRef.current = false;
          if (isSynthesisSupported) window.speechSynthesis.cancel();
        }
      }, inactivityTimeoutMs);
    }
  }, [inactivityTimeoutMs, isSynthesisSupported]);

  const clearInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
  }, []);

  // -------------------------------------------------------------
  // Speech Synthesis (TTS) dengan Suara Bahasa Indonesia & Barge-in
  // -------------------------------------------------------------
  const stopSpeaking = useCallback(() => {
    if (speakingWatchdogRef.current) {
      clearTimeout(speakingWatchdogRef.current);
      speakingWatchdogRef.current = null;
    }
    activeUtteranceRef.current = null;
    if (typeof window !== "undefined") {
      window._aira_active_utterance = null;
    }
    if (isSynthesisSupported) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    if (stateRef.current === COMPANION_STATES.SPEAKING) {
      setCompanionState(COMPANION_STATES.LISTENING);
      stateRef.current = COMPANION_STATES.LISTENING;
    }
  }, [isSynthesisSupported]);

  const speakResponse = useCallback(
    (text, onEnded) => {
      if (!isSynthesisSupported || !text || !text.trim()) {
        onEnded?.();
        return;
      }

      if (speakingWatchdogRef.current) {
        clearTimeout(speakingWatchdogRef.current);
        speakingWatchdogRef.current = null;
      }

      try {
        window.speechSynthesis.cancel();
      } catch {}

      setCompanionState(COMPANION_STATES.SPEAKING);
      stateRef.current = COMPANION_STATES.SPEAKING;
      resetInactivityTimer();

      const cleaned = cleanTextForSpeech(text);
      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.lang = "id-ID";
      utterance.rate = speechRate || 1.0;

      // Cegah Chromium garbage collection bug dengan menyimpan ref aktif
      activeUtteranceRef.current = utterance;
      if (typeof window !== "undefined") {
        window._aira_active_utterance = utterance;
      }

      const voices = window.speechSynthesis.getVoices?.() || [];
      const idVoice =
        voices.find(
          (v) =>
            v.lang?.toLowerCase().startsWith("id") ||
            v.name?.toLowerCase().includes("indonesia")
        ) || null;

      if (idVoice) utterance.voice = idVoice;

      const finishSpeech = () => {
        if (speakingWatchdogRef.current) {
          clearTimeout(speakingWatchdogRef.current);
          speakingWatchdogRef.current = null;
        }
        activeUtteranceRef.current = null;
        if (typeof window !== "undefined") {
          window._aira_active_utterance = null;
        }
        if (stateRef.current === COMPANION_STATES.SPEAKING) {
          setCompanionState(COMPANION_STATES.LISTENING);
          stateRef.current = COMPANION_STATES.LISTENING;
          resetInactivityTimer();
        }
        onEnded?.();
      };

      utterance.onstart = () => {
        setCompanionState(COMPANION_STATES.SPEAKING);
        stateRef.current = COMPANION_STATES.SPEAKING;
      };

      utterance.onend = finishSpeech;
      utterance.onerror = finishSpeech;

      // Safety watchdog: jika browser Chromium tidak memicu onend, paksa kembali ke LISTENING
      const estDurationMs = Math.max(3000, Math.min(25000, cleaned.length * 150));
      speakingWatchdogRef.current = setTimeout(() => {
        if (stateRef.current === COMPANION_STATES.SPEAKING) {
          console.warn("[AIRA Voice] TTS watchdog triggered. Returning to LISTENING.");
          finishSpeech();
        }
      }, estDurationMs);

      try {
        window.speechSynthesis.speak(utterance);
      } catch {
        finishSpeech();
      }
    },
    [isSynthesisSupported, speechRate, resetInactivityTimer]
  );

  // -------------------------------------------------------------
  // Eksekusi Perintah Terstruktur dari Voice Command Router
  // -------------------------------------------------------------
  const handleRoutedCommand = useCallback(
    async (command) => {
      setCompanionState(COMPANION_STATES.PROCESSING);
      stateRef.current = COMPANION_STATES.PROCESSING;
      resetInactivityTimer();

      // 1. Perintah Pengakhiran Sesi ("bye")
      if (command.intent === "control:bye") {
        setActionCard({
          title: "Sesi Suara Selesai",
          target: "bye",
          status: "success",
        });
        setAiraResponse(command.spokenResponse);
        speakResponse(command.spokenResponse, () => {
          setCompanionState(COMPANION_STATES.STANDBY);
          stateRef.current = COMPANION_STATES.STANDBY;
          setOverlayVisible(false);
          clearInactivityTimer();
        });
        return;
      }

      // 2. Perintah Menghentikan Pembicaraan ("stop")
      if (command.intent === "control:stop_speaking") {
        stopSpeaking();
        setActionCard({
          title: "Pembicaraan Dihentikan",
          target: "stop",
          status: "success",
        });
        setCompanionState(COMPANION_STATES.LISTENING);
        stateRef.current = COMPANION_STATES.LISTENING;
        return;
      }

      // 3. Perintah Navigasi Halaman UI (mis. "buka topology")
      if (command.type === "navigation" && command.action?.target) {
        const targetPage = command.action.target;
        setActionCard({
          title: command.actionTitle,
          target: targetPage,
          status: "executing",
        });
        setAiraResponse(command.spokenResponse);

        let navSuccess = false;
        try {
          if (onNavigateRef.current) {
            onNavigateRef.current(targetPage);
            navSuccess = true;
          } else {
            window.dispatchEvent(
              new CustomEvent("aira:navigate", { detail: targetPage })
            );
            navSuccess = true;
          }
        } catch {
          navSuccess = false;
        }

        setActionCard({
          title: command.actionTitle,
          target: targetPage,
          status: navSuccess ? "success" : "failed",
        });

        const speakText = navSuccess
          ? command.spokenResponse
          : `Gagal membuka halaman ${command.action.pageLabel || targetPage}.`;

        speakResponse(speakText, () => {
          setCompanionState(COMPANION_STATES.LISTENING);
          stateRef.current = COMPANION_STATES.LISTENING;
          resetInactivityTimer();
        });
        return;
      }

      // 4. Murni Panggilan Wake Word ("AIRA")
      if (command.type === "wake_acknowledgement") {
        setAiraResponse(command.spokenResponse);
        setActionCard({
          title: "AIRA Siap",
          target: "wake",
          status: "success",
        });
        speakResponse(command.spokenResponse, () => {
          setCompanionState(COMPANION_STATES.LISTENING);
          stateRef.current = COMPANION_STATES.LISTENING;
          resetInactivityTimer();
        });
        return;
      }

      // 5. Perintah Pengulangan Respons ("ulangi")
      if (command.intent === "control:repeat") {
        setActionCard({
          title: "Mengulangi Respons",
          target: "repeat",
          status: "success",
        });
        const repText = command.spokenResponse || "Tidak ada respons sebelumnya untuk diulangi.";
        setAiraResponse(repText);
        speakResponse(repText, () => {
          setCompanionState(COMPANION_STATES.LISTENING);
          stateRef.current = COMPANION_STATES.LISTENING;
          resetInactivityTimer();
        });
        return;
      }

      // 6. Perintah Bantuan / Help
      if (command.intent === "control:help" || command.type === "info") {
        setActionCard({
          title: "Bantuan Perintah Suara",
          target: "help",
          status: "success",
        });
        setAiraResponse(command.spokenResponse);
        speakResponse(command.spokenResponse, () => {
          setCompanionState(COMPANION_STATES.LISTENING);
          stateRef.current = COMPANION_STATES.LISTENING;
          resetInactivityTimer();
        });
        return;
      }

      // 7. Perintah Kosong
      if (command.type === "empty") {
        setCompanionState(COMPANION_STATES.LISTENING);
        stateRef.current = COMPANION_STATES.LISTENING;
        return;
      }

      // 8. Fallback ke Chat Query (AI Engine)
      if (command.type === "chat_query") {
        setActionCard({
          title: "Memproses Pertanyaan AI",
          target: "chat",
          status: "executing",
        });
        setAiraResponse("Sedang memproses pertanyaanmu...");

        if (onChatQueryRef.current) {
          try {
            const answer = await onChatQueryRef.current(command.action.prompt);
            const answerText = answer || "Selesai memproses.";
            setAiraResponse(answerText);
            setActionCard({
              title: "Jawaban AI Selesai",
              target: "chat",
              status: "success",
            });
            speakResponse(answerText, () => {
              setCompanionState(COMPANION_STATES.LISTENING);
              stateRef.current = COMPANION_STATES.LISTENING;
              resetInactivityTimer();
            });
            return;
          } catch {
            setActionCard({
              title: "Gagal Memproses Chat",
              target: "chat",
              status: "failed",
            });
            speakResponse("Maaf, terjadi kendala saat memproses permintaanmu.", () => {
              setCompanionState(COMPANION_STATES.LISTENING);
              stateRef.current = COMPANION_STATES.LISTENING;
              resetInactivityTimer();
            });
            return;
          }
        } else {
          const response =
            "Saya mendengar: " +
            command.commandText +
            ". Silakan coba katakan 'buka topology' atau 'buka chat'.";
          setAiraResponse(response);
          setActionCard({
            title: "Perintah Diterima",
            target: "chat",
            status: "success",
          });
          speakResponse(response, () => {
            setCompanionState(COMPANION_STATES.LISTENING);
            stateRef.current = COMPANION_STATES.LISTENING;
            resetInactivityTimer();
          });
          return;
        }
      }

      // 9. Catch-all pemulihan state agar tidak menggantung di PROCESSING
      setCompanionState(COMPANION_STATES.LISTENING);
      stateRef.current = COMPANION_STATES.LISTENING;
      resetInactivityTimer();
    },
    [speakResponse, stopSpeaking, resetInactivityTimer, clearInactivityTimer]
  );

  // -------------------------------------------------------------
  // Setup SpeechRecognition Client-Side (Ringan, Tanpa Beban CPU)
  // -------------------------------------------------------------
  const initRecognition = useCallback(() => {
    if (!isSpeechSupported) return null;

    try {
      const recognition = new SpeechRecognitionImpl();
      recognition.lang = "id-ID";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        isListeningIntentRef.current = true;
        consecutiveRestartsRef.current = 0;
      };

      recognition.onresult = (event) => {
        let interim = "";
        let finalUtterance = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const item = event.results[i];
          const transcript = item[0]?.transcript || "";
          if (item.isFinal) {
            finalUtterance += transcript;
          } else {
            interim += transcript;
          }
        }

        // Barge-in: hentikan suara AIRA jika pengguna mulai berbicara
        if (stateRef.current === COMPANION_STATES.SPEAKING) {
          if (finalUtterance.trim() || interim.trim().length > 2) {
            stopSpeaking();
          } else {
            return;
          }
        }

        if (interim.trim()) {
          setInterimTranscript(interim);
          resetInactivityTimer();
        }

        // Cek jika sedang dalam STANDBY dan mendengar wake word "AIRA"
        if (stateRef.current === COMPANION_STATES.STANDBY) {
          const checkText = (finalUtterance || interim).trim();
          if (containsWakeWord(checkText)) {
            // Wake word terdeteksi! Beri feedback instan
            playWakeChime();
            setOverlayVisible(true);
            setCompanionState(COMPANION_STATES.LISTENING);
            stateRef.current = COMPANION_STATES.LISTENING;
            resetInactivityTimer();

            // Jika ucapan mengandung perintah lengkap sekaligus (mis. "AIRA buka topology")
            const stripped = stripWakeWord(checkText);
            if (stripped && finalUtterance) {
              setInterimTranscript("");
              setUserTranscript(finalUtterance);
              const routed = routeVoiceCommand(finalUtterance);
              handleRoutedCommand(routed);
              return;
            } else if (isPureWakeWord(checkText) || !stripped) {
              setInterimTranscript("");
              setUserTranscript(checkText);
              setAiraResponse("Ya, ada yang bisa saya bantu?");
              speakResponse("Ya, ada yang bisa saya bantu?");
              return;
            }
          }
        } else if (
          stateRef.current === COMPANION_STATES.LISTENING &&
          finalUtterance.trim()
        ) {
          // Sedang dalam sesi aktif LISTENING dan ucapan final selesai
          setInterimTranscript("");
          setUserTranscript(finalUtterance.trim());
          resetInactivityTimer();

          const routed = routeVoiceCommand(finalUtterance.trim());
          handleRoutedCommand(routed);
        }
      };

      recognition.onerror = (event) => {
        if (event.error === "no-speech" || event.error === "aborted") {
          return;
        }

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          setCompanionState(COMPANION_STATES.ERROR);
          stateRef.current = COMPANION_STATES.ERROR;
          setErrorMessage(
            "Izin akses mikrofon browser belum aktif. Klik tombol Companion di atas untuk mengizinkan."
          );
        } else if (event.error === "network") {
          setErrorMessage(
            "Tidak dapat terhubung ke layanan pengenalan suara browser. Pastikan koneksi internet aktif."
          );
        } else {
          setErrorMessage(`Kendala pengenalan suara: ${event.error}`);
        }
      };

      recognition.onend = () => {
        isListeningIntentRef.current = false;
        if (isPausedRef.current) {
          return;
        }
        // HANYA restart jika sesi suara benar-benar aktif (LISTENING).
        // Pada state STANDBY, DISABLED, ERROR, atau SPEAKING: JANGAN restart mikrofon!
        // Ini mencegah indikator privasi Windows muncul-hilang berulang kali di latar belakang.
        if (stateRef.current === COMPANION_STATES.LISTENING) {
          if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
          if (consecutiveRestartsRef.current >= 3) {
            console.warn("[AIRA Voice] Batas restart pengenalan suara tercapai, kembali ke STANDBY.");
            setCompanionState(COMPANION_STATES.STANDBY);
            stateRef.current = COMPANION_STATES.STANDBY;
            setOverlayVisible(false);
            return;
          }
          consecutiveRestartsRef.current += 1;
          restartTimerRef.current = setTimeout(() => {
            if (stateRef.current === COMPANION_STATES.LISTENING && !isPausedRef.current) {
              try {
                recognition.start();
                isListeningIntentRef.current = true;
              } catch {
                // Retry fallback singkat satu kali
                setTimeout(() => {
                  if (stateRef.current === COMPANION_STATES.LISTENING && !isPausedRef.current) {
                    try {
                      recognition.start();
                      isListeningIntentRef.current = true;
                    } catch {}
                  }
                }, 400);
              }
            }
          }, 300);
        }
      };

      return recognition;
    } catch {
      setCompanionState(COMPANION_STATES.ERROR);
      stateRef.current = COMPANION_STATES.ERROR;
      setErrorMessage("Gagal menginisialisasi modul pengenalan suara browser.");
      return null;
    }
  }, [
    isSpeechSupported,
    SpeechRecognitionImpl,
    resetInactivityTimer,
    handleRoutedCommand,
    speakResponse,
  ]);

  // -------------------------------------------------------------
  // Siklus Hidup & Efek Listener
  // -------------------------------------------------------------
  useEffect(() => {
    if (!enabled || !isSpeechSupported) {
      setCompanionState(COMPANION_STATES.DISABLED);
      stateRef.current = COMPANION_STATES.DISABLED;
      setOverlayVisible(false);
      try {
        recognitionRef.current?.stop();
      } catch {}
      return;
    }

    const recognition = initRecognition();
    recognitionRef.current = recognition;

    // PADA STANDBY: mikrofon TIDAK dibuka agar tidak memicu indikator privasi Windows.
    // Mikrofon hanya dibuka saat sesi aktif (LISTENING) lewat activateManually / toggle.
    setCompanionState(COMPANION_STATES.STANDBY);
    stateRef.current = COMPANION_STATES.STANDBY;

    return () => {
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      try {
        recognition?.stop();
      } catch {}
      clearInactivityTimer();
      if (isSynthesisSupported) window.speechSynthesis.cancel();
    };
  }, [enabled, isSpeechSupported, initRecognition, clearInactivityTimer, isSynthesisSupported]);

  // Arbitrase mikrofon: jeda background recognition saat chat speech aktif
  useEffect(() => {
    function onMicClaimed() {
      isPausedRef.current = true;
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      try {
        recognitionRef.current?.stop();
      } catch {}
    }

    function onMicReleased() {
      isPausedRef.current = false;
      // HANYA aktifkan kembali jika state sedang aktif LISTENING
      if (stateRef.current === COMPANION_STATES.LISTENING) {
        if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
        restartTimerRef.current = setTimeout(() => {
          try {
            recognitionRef.current?.start();
          } catch {}
        }, 300);
      }
    }

    window.addEventListener('aira:mic-claimed', onMicClaimed);
    window.addEventListener('aira:mic-released', onMicReleased);
    return () => {
      window.removeEventListener('aira:mic-claimed', onMicClaimed);
      window.removeEventListener('aira:mic-released', onMicReleased);
    };
  }, []);

  // -------------------------------------------------------------
  // Aktivasi Manual (Fallback 1-Klik Tanpa Menunggu Wake-Word)
  // -------------------------------------------------------------
  const activateManually = useCallback(async () => {
    if (!isSpeechSupported) {
      notifyRef.current?.({
        type: "warning",
        message:
          "Web Speech API belum didukung di browser ini. Disarankan menggunakan Google Chrome atau Microsoft Edge.",
      });
      return;
    }

    // Minta izin mikrofon browser secara eksplisit via getUserMedia agar muncul dialog allow browser
    try {
      if (navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((t) => t.stop());
      }
    } catch {
      setCompanionState(COMPANION_STATES.ERROR);
      stateRef.current = COMPANION_STATES.ERROR;
      setErrorMessage("Izin mikrofon belum diberikan. Klik ikon gembok di sebelah URL browser dan pilih 'Allow Microphone'.");
      notifyRef.current?.({
        type: "error",
        message: "Izin mikrofon belum diizinkan. Klik ikon gembok di browser dan pilih Izinkan Mikrofon.",
      });
      return;
    }

    playWakeChime();
    setOverlayVisible(true);
    setCompanionState(COMPANION_STATES.LISTENING);
    stateRef.current = COMPANION_STATES.LISTENING;
    setUserTranscript("");
    setInterimTranscript("");
    setAiraResponse("Halo! Saya mendengarkan, silakan bicara.");
    speakResponse("Halo! Saya mendengarkan, silakan bicara.");
    setActionCard(null);
    setErrorMessage("");
    resetInactivityTimer();

    // Pastikan recognition berjalan dengan me-restart / re-init jika perlu
    try {
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      try {
        recognitionRef.current?.stop();
      } catch {}
      const freshRec = initRecognition();
      recognitionRef.current = freshRec;
      freshRec?.start();
      isListeningIntentRef.current = true;
    } catch (err) {
      console.warn("[AIRA Voice] Gagal start fresh recognition:", err);
    }
  }, [isSpeechSupported, initRecognition, resetInactivityTimer, speakResponse]);

  const deactivateCompanion = useCallback(() => {
    setOverlayVisible(false);
    setCompanionState(COMPANION_STATES.STANDBY);
    stateRef.current = COMPANION_STATES.STANDBY;
    setInterimTranscript("");
    clearInactivityTimer();
    stopSpeaking();
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
    try {
      recognitionRef.current?.stop();
    } catch {}
    isListeningIntentRef.current = false;
  }, [clearInactivityTimer, stopSpeaking]);

  const toggleOverlay = useCallback(() => {
    if (overlayVisible) {
      deactivateCompanion();
    } else {
      activateManually();
    }
  }, [overlayVisible, deactivateCompanion, activateManually]);

  return {
    state: companionState,
    isSpeechSupported,
    isSynthesisSupported,
    overlayVisible,
    userTranscript,
    interimTranscript,
    airaResponse,
    actionCard,
    errorMessage,
    captionsVisible,
    setCaptionsVisible,
    activateManually,
    deactivateCompanion,
    toggleOverlay,
    stopSpeaking,
  };
}
