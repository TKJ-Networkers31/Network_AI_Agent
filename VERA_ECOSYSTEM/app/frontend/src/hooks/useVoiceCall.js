import { useCallback, useRef, useState } from "react";

/**
 * Voice Call Mode — mic ditangkap client-side (Adaptive VAD),
 * utterance dikirim PENUH ke WebSocket sebagai {type:"voice_audio", audio_base64}.
 * Menyediakan diagnostik pipeline observable: Audio Track, Noise Floor Calibration,
 * Live Volume Level, dan Silence Timeout.
 */

export const VOICE_DIAGNOSTICS = {
  IDLE: "idle",
  REQUESTING_PERMISSION: "requesting_permission",
  READY: "ready",
  LISTENING: "listening",
  SPEECH_DETECTED: "speech_detected",
  PROCESSING: "processing",
  TRANSCRIPT_RECEIVED: "transcript_received",
  PERMISSION_DENIED: "permission_denied",
  NO_INPUT_DETECTED: "no_input_detected",
  ERROR: "error",
};

const SAMPLE_RATE = 16000;
const FRAME_MS = 30;
const FRAME_SAMPLES = Math.round((SAMPLE_RATE * FRAME_MS) / 1000);
const DEFAULT_ENERGY_THRESHOLD = 120; // Sensible default for normal conversational mic
const SILENCE_END_MS = 800;
const SILENCE_END_FRAMES = Math.round(SILENCE_END_MS / FRAME_MS);
const MIN_UTTERANCE_FRAMES = 10;
const CALIBRATION_FRAMES = 10; // ~300ms initial ambient noise sampling
const SILENCE_TIMEOUT_MS = 10_000; // 10s without any speech triggers no_input_detected

function downsampleTo16k(buffer, inputRate) {
  if (inputRate === SAMPLE_RATE) return buffer;
  const ratio = inputRate / SAMPLE_RATE;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.floor(i * ratio)] || 0;
  }
  return result;
}

function floatToInt16(float32) {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16;
}

function frameRms(int16) {
  if (int16.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < int16.length; i++) sum += int16[i] * int16[i];
  return Math.sqrt(sum / int16.length);
}

function int16ToBase64(int16) {
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export function useVoiceCall({ onSendAudio, notify } = {}) {
  const [callActive, setCallActive] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [subtitle, setSubtitle] = useState("");
  const [waitingReply, setWaitingReply] = useState(false);

  // Observable Voice Diagnostics
  const [diagnosticState, setDiagnosticState] = useState(VOICE_DIAGNOSTICS.IDLE);
  const [audioLevel, setAudioLevel] = useState(0); // 0-100 normalized
  const [deviceLabel, setDeviceLabel] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const audioElRef = useRef(null);

  const speechFramesRef = useRef([]);
  const silenceRunRef = useRef(0);
  const inSpeechRef = useRef(false);
  const pausedRef = useRef(false);
  const activeRef = useRef(false);

  // Adaptive VAD refs
  const thresholdRef = useRef(DEFAULT_ENERGY_THRESHOLD);
  const calibrationSumRef = useRef(0);
  const calibrationCountRef = useRef(0);
  const lastSpeechTimeRef = useRef(0);
  const lastLevelUpdateRef = useRef(0);

  const onSendAudioRef = useRef(onSendAudio);
  onSendAudioRef.current = onSendAudio;

  const stopMicOnly = useCallback(() => {
    try {
      if (processorRef.current) processorRef.current.onaudioprocess = null;
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
    } catch {
      // ignore
    }

    streamRef.current?.getTracks().forEach((t) => t.stop());

    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;

    setListening(false);
    setAudioLevel(0);
  }, []);

  const _sendUtterance = useCallback((frames) => {
    const totalLength = frames.reduce((s, f) => s + f.length, 0);
    if (totalLength === 0) return;

    const merged = new Int16Array(totalLength);
    let pos = 0;
    for (const f of frames) {
      merged.set(f, pos);
      pos += f.length;
    }

    const audio_base64 = int16ToBase64(merged);

    pausedRef.current = true;
    setWaitingReply(true);
    setDiagnosticState(VOICE_DIAGNOSTICS.PROCESSING);

    onSendAudioRef.current?.({
      type: "voice_audio",
      audio_base64,
      sample_rate: SAMPLE_RATE,
    });
  }, []);

  const startMicCapture = useCallback(async () => {
    if (!activeRef.current) return;

    setDiagnosticState(VOICE_DIAGNOSTICS.REQUESTING_PERMISSION);
    setErrorMessage("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const tracks = stream.getAudioTracks();
      if (!tracks || tracks.length === 0) {
        throw new Error("Tidak ada track audio mikrofon aktif.");
      }
      const track = tracks[0];
      setDeviceLabel(track.label || "Mikrofon Perangkat");
      setDiagnosticState(VOICE_DIAGNOSTICS.READY);

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = audioCtxRef.current || new AudioCtx();
      audioCtxRef.current = audioCtx;

      if (audioCtx.state === "suspended") {
        await audioCtx.resume();
      }

      const source = audioCtx.createMediaStreamSource(stream);
      sourceRef.current = source;

      const bufferSize = 4096;
      const processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      speechFramesRef.current = [];
      silenceRunRef.current = 0;
      inSpeechRef.current = false;
      calibrationSumRef.current = 0;
      calibrationCountRef.current = 0;
      thresholdRef.current = DEFAULT_ENERGY_THRESHOLD;
      lastSpeechTimeRef.current = Date.now();
      lastLevelUpdateRef.current = 0;

      setDiagnosticState(VOICE_DIAGNOSTICS.LISTENING);

      processor.onaudioprocess = (e) => {
        if (pausedRef.current || !activeRef.current) return;

        const input = e.inputBuffer.getChannelData(0);
        const down = downsampleTo16k(input, audioCtx.sampleRate);
        const int16Chunk = floatToInt16(down);

        for (let offset = 0; offset < int16Chunk.length; offset += FRAME_SAMPLES) {
          const frame = int16Chunk.slice(offset, offset + FRAME_SAMPLES);
          if (frame.length === 0) continue;

          const energy = frameRms(frame);

          // Update live audio meter (throttled ~60ms)
          const now = Date.now();
          if (now - lastLevelUpdateRef.current > 60) {
            lastLevelUpdateRef.current = now;
            const norm = Math.min(100, Math.round((energy / 300) * 100));
            setAudioLevel(norm);
          }

          // Adaptive Noise Calibration (~300ms awal)
          if (calibrationCountRef.current < CALIBRATION_FRAMES) {
            calibrationSumRef.current += energy;
            calibrationCountRef.current += 1;
            if (calibrationCountRef.current === CALIBRATION_FRAMES) {
              const ambient = calibrationSumRef.current / CALIBRATION_FRAMES;
              thresholdRef.current = Math.max(75, Math.min(240, Math.round(ambient * 1.8)));
            }
            continue;
          }

          const isSpeech = energy >= thresholdRef.current;

          // Silence timeout check
          if (!inSpeechRef.current && (now - lastSpeechTimeRef.current > SILENCE_TIMEOUT_MS)) {
            setDiagnosticState(VOICE_DIAGNOSTICS.NO_INPUT_DETECTED);
          }

          if (isSpeech) {
            lastSpeechTimeRef.current = now;
            speechFramesRef.current.push(frame);
            silenceRunRef.current = 0;
            if (!inSpeechRef.current) {
              inSpeechRef.current = true;
              setListening(true);
              setDiagnosticState(VOICE_DIAGNOSTICS.SPEECH_DETECTED);
            }
          } else if (inSpeechRef.current) {
            silenceRunRef.current += 1;
            speechFramesRef.current.push(frame);

            if (silenceRunRef.current >= SILENCE_END_FRAMES) {
              const frames = speechFramesRef.current;
              speechFramesRef.current = [];
              silenceRunRef.current = 0;
              inSpeechRef.current = false;
              setListening(false);

              if (frames.length >= MIN_UTTERANCE_FRAMES) {
                _sendUtterance(frames);
              } else {
                setDiagnosticState(VOICE_DIAGNOSTICS.LISTENING);
              }
            }
          }
        }
      };

      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;

      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioCtx.destination);
    } catch (err) {
      const isDenied = err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError";
      const diagState = isDenied ? VOICE_DIAGNOSTICS.PERMISSION_DENIED : VOICE_DIAGNOSTICS.ERROR;
      const msg = isDenied
        ? "Izin akses mikrofon ditolak oleh browser. Silakan izinkan akses mikrofon di pengaturan browser Anda."
        : "Tidak bisa mengakses mikrofon: " + (err?.message || err);

      setDiagnosticState(diagState);
      setErrorMessage(msg);
      notify?.({ type: "error", message: msg });
      activeRef.current = false;
      setCallActive(false);
    }
  }, [notify, _sendUtterance]);

  const playResponseAudio = useCallback((base64Wav, answerText) => {
    setWaitingReply(false);

    if (!base64Wav) {
      pausedRef.current = false;
      setSubtitle("");
      setDiagnosticState(VOICE_DIAGNOSTICS.LISTENING);
      return;
    }

    setSubtitle(answerText || "");
    setSpeaking(true);
    setDiagnosticState(VOICE_DIAGNOSTICS.TRANSCRIPT_RECEIVED);
    pausedRef.current = true;

    const src = `data:audio/wav;base64,${base64Wav}`;
    const audioEl = new Audio(src);
    audioElRef.current = audioEl;

    const resumeMic = () => {
      setSpeaking(false);
      setSubtitle("");
      pausedRef.current = false;
      setDiagnosticState(VOICE_DIAGNOSTICS.LISTENING);
      lastSpeechTimeRef.current = Date.now();
    };

    audioEl.onended = resumeMic;
    audioEl.onerror = resumeMic;
    audioEl.play().catch(resumeMic);
  }, []);

  const cancelWaiting = useCallback(() => {
    pausedRef.current = false;
    setWaitingReply(false);
    setDiagnosticState(VOICE_DIAGNOSTICS.LISTENING);
    lastSpeechTimeRef.current = Date.now();
  }, []);

  const startCall = useCallback(() => {
    activeRef.current = true;
    pausedRef.current = false;
    setCallActive(true);
    startMicCapture();
  }, [startMicCapture]);

  const endCall = useCallback(() => {
    activeRef.current = false;
    pausedRef.current = false;

    setCallActive(false);
    setListening(false);
    setSpeaking(false);
    setWaitingReply(false);
    setSubtitle("");
    setDiagnosticState(VOICE_DIAGNOSTICS.IDLE);
    setAudioLevel(0);

    audioElRef.current?.pause();
    audioElRef.current = null;

    stopMicOnly();
  }, [stopMicOnly]);

  const toggleCall = useCallback(() => {
    if (callActive) endCall();
    else startCall();
  }, [callActive, startCall, endCall]);

  return {
    supported: typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
    callActive,
    listening,
    speaking,
    waitingReply,
    subtitle,
    diagnosticState,
    audioLevel,
    deviceLabel,
    errorMessage,
    startCall,
    endCall,
    toggleCall,
    playResponseAudio,
    cancelWaiting,
  };
}
