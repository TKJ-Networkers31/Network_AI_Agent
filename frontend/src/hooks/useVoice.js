import { useCallback, useRef, useState } from "react";

/**
 * Voice I/O untuk web UI, sepenuhnya client-side lewat Web Speech API
 * bawaan browser (dukungan terbaik di Chrome/Edge, butuh izin mic dan
 * koneksi https/localhost). Ini terpisah dari pipeline suara agent
 * terminal (faster-whisper + Kokoro) - di web tidak ada roundtrip
 * audio ke backend sama sekali, supaya tidak perlu endpoint baru.
 *
 * - "Dengar": merekam ucapan. Selama bicara, teks sementara (interim)
 *   dipublish lewat interimText supaya UI bisa nunjukin live caption.
 *   Begitu terdeteksi diam (browser yang mendeteksi, otomatis), hasil
 *   final dikirim ke onTranscript lalu recognition berhenti sendiri -
 *   tidak perlu klik lagi.
 * - "Bicara": kalau aktif, setiap jawaban assistant baru dibacakan
 *   otomatis lewat speechSynthesis.
 */
export function useVoice({ onTranscript, notify } = {}) {
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [speakEnabled, setSpeakEnabled] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const recognitionRef = useRef(null);

  const SpeechRecognitionImpl =
    typeof window !== "undefined"
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null;

  const speechSupported = Boolean(SpeechRecognitionImpl);
  const synthesisSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const startListening = useCallback(() => {
    if (!speechSupported) {
      notify?.({
        type: "warning",
        message:
          "Browser ini belum mendukung pengenalan suara. Coba buka lewat Chrome atau Edge.",
      });
      return;
    }

    setInterimText("");

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = "id-ID";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setListening(true);
    };

    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";

      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += transcript;
        } else {
          interim += transcript;
        }
      }

      if (interim) setInterimText(interim);

      if (finalText.trim()) {
        setInterimText("");
        onTranscript?.(finalText.trim());
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        notify?.({
          type: "error",
          message: "Akses mikrofon ditolak. Izinkan mic di pengaturan browser untuk pakai fitur ini.",
        });
      } else if (event.error !== "aborted" && event.error !== "no-speech") {
        notify?.({ type: "error", message: `Gagal mengenali suara (${event.error}).` });
      }
    };

    recognition.onend = () => {
      setListening(false);
      setInterimText("");
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch {
      // start() melempar kalau dipanggil dua kali beruntun - abaikan.
    }
  }, [SpeechRecognitionImpl, speechSupported, onTranscript, notify]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
    setInterimText("");
  }, []);

  const toggleListening = useCallback(() => {
    if (listening) {
      stopListening();
    } else {
      startListening();
    }
  }, [listening, startListening, stopListening]);

  const stopSpeaking = useCallback(() => {
    if (synthesisSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  }, [synthesisSupported]);

  const speak = useCallback(
    (text) => {
      if (!speakEnabled || !text || !synthesisSupported) return;

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "id-ID";
      utterance.rate = 1;

      const idVoice = window.speechSynthesis
        .getVoices()
        .find((v) => v.lang?.toLowerCase().startsWith("id"));

      if (idVoice) utterance.voice = idVoice;

      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [speakEnabled, synthesisSupported]
  );

  const toggleSpeak = useCallback(() => {
    setSpeakEnabled((prev) => {
      const next = !prev;

      if (!next) stopSpeaking();

      notify?.({
        type: "info",
        message: next ? "Mode bicara diaktifkan." : "Mode bicara dimatikan.",
        duration: 2500,
      });

      return next;
    });
  }, [stopSpeaking, notify]);

  return {
    supported: speechSupported,
    synthesisSupported,
    listening,
    interimText,
    speaking,
    speakEnabled,
    startListening,
    stopListening,
    toggleListening,
    speak,
    stopSpeaking,
    toggleSpeak,
  };
}
