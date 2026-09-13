import { useCallback, useRef, useState } from "react";

/**
 * Voice Call Mode — mic ditangkap client-side (VAD energi sederhana,
 * mirip agents/yuki/voice_io.py versi server), utterance dikirim
 * PENUH ke WebSocket sebagai {type:"voice_audio", audio_base64}.
 * Transkripsi (faster-whisper) dan sintesis balasan (Kokoro) terjadi
 * di SERVER (lihat api/routers/ws.py) - BUKAN Web Speech API browser,
 * jadi tidak butuh koneksi ke server pihak ketiga (Google) sama sekali.
 *
 * Dipakai bersama wsSend dari ChatRuntimeContext (lihat
 * useChatRuntime().sendVoiceAudio). Hook ini TIDAK tahu apa-apa soal
 * WebSocket - murni mic capture + VAD + audio playback balasan.
 */

const SAMPLE_RATE = 16000;
const FRAME_MS = 30;
const FRAME_SAMPLES = Math.round((SAMPLE_RATE * FRAME_MS) / 1000);
const ENERGY_THRESHOLD = 500;
const SILENCE_END_MS = 800;
const SILENCE_END_FRAMES = Math.round(SILENCE_END_MS / FRAME_MS);
const MIN_UTTERANCE_FRAMES = 10;

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
  const [listening, setListening] = useState(false); // sedang menangkap ucapan (energi > threshold)
  const [speaking, setSpeaking] = useState(false);    // audio balasan sedang diputar
  const [subtitle, setSubtitle] = useState("");
  const [waitingReply, setWaitingReply] = useState(false); // sudah kirim utterance, menunggu balasan

  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const audioElRef = useRef(null);

  const speechFramesRef = useRef([]);
  const silenceRunRef = useRef(0);
  const inSpeechRef = useRef(false);
  const pausedRef = useRef(false); // true saat menunggu balasan / TTS bicara
  const activeRef = useRef(false);

  const onSendAudioRef = useRef(onSendAudio);
  onSendAudioRef.current = onSendAudio;

  const stopMicOnly = useCallback(() => {
    try {
      processorRef.current && (processorRef.current.onaudioprocess = null);
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
    } catch {
      // abaikan - node mungkin sudah disconnect
    }

    streamRef.current?.getTracks().forEach((t) => t.stop());

    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;

    setListening(false);
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

    onSendAudioRef.current?.({
      type: "voice_audio",
      audio_base64,
      sample_rate: SAMPLE_RATE,
    });
  }, []);

  const startMicCapture = useCallback(async () => {
    if (!activeRef.current) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

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

      processor.onaudioprocess = (e) => {
        if (pausedRef.current || !activeRef.current) return;

        const input = e.inputBuffer.getChannelData(0);
        const down = downsampleTo16k(input, audioCtx.sampleRate);
        const int16Chunk = floatToInt16(down);

        for (let offset = 0; offset < int16Chunk.length; offset += FRAME_SAMPLES) {
          const frame = int16Chunk.slice(offset, offset + FRAME_SAMPLES);
          if (frame.length === 0) continue;

          const energy = frameRms(frame);
          const isSpeech = energy >= ENERGY_THRESHOLD;

          if (isSpeech) {
            speechFramesRef.current.push(frame);
            silenceRunRef.current = 0;
            if (!inSpeechRef.current) {
              inSpeechRef.current = true;
              setListening(true);
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
              }
            }
          }
        }
      };

      // Node dummy tujuan wajib supaya onaudioprocess jalan di semua browser.
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;

      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioCtx.destination);
    } catch (err) {
      notify?.({
        type: "error",
        message: "Tidak bisa mengakses mikrofon: " + (err?.message || err),
      });
      activeRef.current = false;
      setCallActive(false);
    }
  }, [notify, _sendUtterance]);

  /**
   * Dipanggil dari luar (ChatRuntimeContext) setiap kali event WS
   * "response" masuk untuk giliran suara. base64Wav bisa null (mis.
   * Kokoro belum ter-setup) - tetap resume mic supaya sesi tidak macet.
   */
  const playResponseAudio = useCallback((base64Wav, answerText) => {
    setWaitingReply(false);

    if (!base64Wav) {
      pausedRef.current = false;
      setSubtitle("");
      return;
    }

    setSubtitle(answerText || "");
    setSpeaking(true);
    pausedRef.current = true;

    const src = `data:audio/wav;base64,${base64Wav}`;
    const audioEl = new Audio(src);
    audioElRef.current = audioEl;

    const resumeMic = () => {
      setSpeaking(false);
      setSubtitle("");
      pausedRef.current = false;
    };

    audioEl.onended = resumeMic;
    audioEl.onerror = resumeMic;
    audioEl.play().catch(resumeMic);
  }, []);

  /** Dipanggil kalau backend melapor transkrip kosong / error, supaya
   * sesi tidak macet menunggu balasan yang tidak akan pernah datang. */
  const cancelWaiting = useCallback(() => {
    pausedRef.current = false;
    setWaitingReply(false);
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

    audioElRef.current?.pause();
    audioElRef.current = null;

    stopMicOnly();
  }, [stopMicOnly]);

  const toggleCall = useCallback(() => {
    if (callActive) endCall();
    else startCall();
  }, [callActive, startCall, endCall]);

  return {
    supported:
      typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
    callActive,
    listening,
    speaking,
    waitingReply,
    subtitle,
    startCall,
    endCall,
    toggleCall,
    playResponseAudio,
    cancelWaiting,
  };
}