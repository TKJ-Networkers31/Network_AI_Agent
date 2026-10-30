"""
agents/yuki/voice_io.py — orkestrasi mic listening + VAD + barge-in untuk
YUKI. Fusion visual TIDAK diimport langsung dari HIKARI - callback
fusion_callback di-inject dari luar (core/orchestrator.py), sesuai aturan
"tiap agent internal tidak saling kenal implementasi satu sama lain".

Siklus hidup background voice service:
  STOPPED -> STARTING -> LISTENING -> RUNNING -> PROCESSING -> ERROR / PAUSED
"""

import collections
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import numpy as np
import sounddevice as sd

from agents.yuki.stt import transcribe

logger = logging.getLogger("aira.yuki.voice_io")

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
ENERGY_THRESHOLD = 500
SILENCE_END_MS = 800
SILENCE_END_FRAMES = SILENCE_END_MS // FRAME_MS
MIN_UTTERANCE_FRAMES = 10

from enum import Enum

# Status siklus hidup resmi
class VoiceState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"
    PAUSED = "PAUSED"

STATE_STOPPED = VoiceState.STOPPED.value
STATE_STARTING = VoiceState.STARTING.value
STATE_RUNNING = VoiceState.RUNNING.value
STATE_LISTENING = VoiceState.LISTENING.value
STATE_PROCESSING = VoiceState.PROCESSING.value
STATE_ERROR = VoiceState.ERROR.value
STATE_PAUSED = VoiceState.PAUSED.value


def _frame_rms(frame_int16: np.ndarray) -> float:
    if len(frame_int16) == 0:
        return 0.0
    samples = frame_int16.astype(np.float64)
    return float(np.sqrt(np.mean(samples ** 2)))


def _mask_transcript(text: str) -> str:
    """Mask transcript for safe logging without leaking sensitive user speech."""
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= 2:
        return f"{words[0][:2]}***" if words else "***"
    return f"{words[0]} *** {words[-1]}"


class VoiceIO:

    def __init__(self, on_transcript: Optional[Callable[[str], None]] = None, fusion_callback: Optional[Callable[[str], str]] = None):
        self.on_transcript = on_transcript
        self.fusion_callback = fusion_callback  # (text) -> text

        self._active = threading.Event()
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._fusion_enabled = threading.Event()

        self._state: str = STATE_STOPPED
        self._pause_reason: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_capture_at: Optional[float] = None
        self._last_transcript_at: Optional[float] = None
        self._last_transcript_masked: Optional[str] = None
        self._device_info: Dict[str, Any] = {}

        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == STATE_ERROR:
                return STATE_ERROR
            if not self._active.is_set():
                return STATE_STOPPED
            if self._paused.is_set():
                return STATE_PAUSED
            return self._state

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    @property
    def device_info(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._device_info)

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            current_state = self.state
            return {
                "state": current_state,
                "is_active": self._active.is_set(),
                "is_listening": current_state == STATE_LISTENING,
                "is_paused": self._paused.is_set(),
                "pause_reason": self._pause_reason,
                "paused_reason": self._pause_reason,
                "audio_backend": "sounddevice (PortAudio)",
                "active_backend": "sounddevice (PortAudio)",
                "sample_rate": SAMPLE_RATE,
                "energy_threshold": ENERGY_THRESHOLD,
                "last_error": self._last_error,
                "last_capture_at": self._last_capture_at,
                "last_transcript_at": self._last_transcript_at,
                "last_transcript_snippet": self._last_transcript_masked,
                "device": dict(self._device_info),
            }

    def start(self) -> Dict[str, Any]:
        """Memulai background listener service dengan proteksi duplikasi."""
        with self._lock:
            if self._active.is_set() and self._thread and self._thread.is_alive():
                logger.info("VoiceIO.start: listener sudah aktif (idempoten).")
                return {"success": True, "already_running": True, "state": self.state}

            self._state = STATE_STARTING
            self._last_error = None
            self._pause_reason = None
            self._paused.clear()
            self._stop.clear()

            # Verifikasi ketersediaan perangkat audio input
            try:
                devices = sd.query_devices()
                default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else None
                input_dev = None
                if default_in is not None and 0 <= default_in < len(devices):
                    d = devices[default_in]
                    if d.get("max_input_channels", 0) > 0:
                        input_dev = d
                        self._device_info = {
                            "index": default_in,
                            "name": d.get("name", "Default Input"),
                            "channels": d.get("max_input_channels", 1),
                            "default_samplerate": d.get("default_samplerate", SAMPLE_RATE),
                        }
                if not input_dev:
                    for idx, d in enumerate(devices):
                        if d.get("max_input_channels", 0) > 0:
                            input_dev = d
                            self._device_info = {
                                "index": idx,
                                "name": d.get("name", "Audio Input"),
                                "channels": d.get("max_input_channels", 1),
                                "default_samplerate": d.get("default_samplerate", SAMPLE_RATE),
                            }
                            break

                if not input_dev:
                    err_msg = "Tidak ditemukan perangkat input audio (mikrofon) pada sistem host."
                    self._state = STATE_ERROR
                    self._last_error = err_msg
                    logger.warning("VoiceIO | %s", err_msg)
                    return {"success": False, "error": err_msg, "state": STATE_ERROR}

            except Exception as exc:
                err_msg = f"Gagal memeriksa perangkat audio: {exc}"
                self._state = STATE_ERROR
                self._last_error = err_msg
                logger.error("VoiceIO | %s", err_msg)
                return {"success": False, "error": err_msg, "state": STATE_ERROR}

            self._active.set()
            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="AiraVoiceIO")
            self._thread.start()
            logger.info("VoiceIO | Listener thread dimulai pada perangkat '%s'.", self._device_info.get("name"))
            return {"success": True, "state": STATE_STARTING, "device": self._device_info}

    def stop(self) -> Dict[str, Any]:
        """Menghentikan background listener service dan melepas resource audio."""
        with self._lock:
            self._active.clear()
            self._stop.set()
            self._paused.clear()
            self._state = STATE_STOPPED

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        logger.info("VoiceIO | Background voice mode dihentikan dan stream ditutup.")
        return {"success": True, "state": STATE_STOPPED}

    def is_active(self) -> bool:
        return self._active.is_set()

    def pause_mic(self, reason: str = "manual") -> Dict[str, Any]:
        """Menjeda penangkapan mikrofon sementara (mis. saat Chat Speech mengklaim mic)."""
        with self._lock:
            self._paused.set()
            self._pause_reason = reason
            logger.info("VoiceIO | Mic listening dijeda (alasan: %s).", reason)
            return {"success": True, "state": STATE_PAUSED, "reason": reason}

    def resume_mic(self) -> Dict[str, Any]:
        """Melanjutkan penangkapan mikrofon kembali jika service aktif."""
        with self._lock:
            self._paused.clear()
            self._pause_reason = None
            new_st = STATE_LISTENING if self._active.is_set() else STATE_STOPPED
            self._state = new_st
            logger.info("VoiceIO | Mic listening dilanjutkan kembali.")
            return {"success": True, "state": new_st}

    def enable_fusion(self):
        self._fusion_enabled.set()
        logger.info("VoiceIO | Fusion suara+visual diaktifkan.")

    def disable_fusion(self):
        self._fusion_enabled.clear()

    def is_fusion_enabled(self) -> bool:
        return self._fusion_enabled.is_set()

    def _listen_loop(self):
        try:
            self._run_stream()
        except Exception as exc:
            with self._lock:
                self._state = STATE_ERROR
                self._last_error = str(exc)
            logger.exception("VoiceIO | _listen_loop mengalami exception: %s", exc)

    def _run_stream(self):
        frame_queue = collections.deque()
        speech_buffer = []
        silence_run = 0
        in_speech = False

        def audio_callback(indata, frames, time_info, status):
            if self._paused.is_set() or not self._active.is_set():
                return
            pcm16 = (indata[:, 0] * 32767).astype(np.int16)
            frame_queue.append(pcm16.tobytes())

        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=FRAME_SAMPLES,
                callback=audio_callback,
            )
        except Exception as exc:
            with self._lock:
                self._state = STATE_ERROR
                self._last_error = f"Gagal membuka InputStream PortAudio: {exc}"
            logger.error("VoiceIO | %s", self._last_error)
            return

        with stream:
            with self._lock:
                self._state = STATE_LISTENING

            while not self._stop.is_set():
                if not frame_queue:
                    sd.sleep(10)
                    continue

                frame_bytes = frame_queue.popleft()
                frame_int16 = np.frombuffer(frame_bytes, dtype=np.int16)
                rms = _frame_rms(frame_int16)
                is_speech = rms >= ENERGY_THRESHOLD

                if is_speech:
                    now = time.time()
                    with self._lock:
                        self._last_capture_at = now
                        if self._state != STATE_RUNNING:
                            self._state = STATE_RUNNING
                    speech_buffer.append(frame_bytes)
                    silence_run = 0
                    in_speech = True
                elif in_speech:
                    silence_run += 1
                    speech_buffer.append(frame_bytes)
                    if silence_run >= SILENCE_END_FRAMES:
                        if len(speech_buffer) >= MIN_UTTERANCE_FRAMES:
                            self._process_utterance(speech_buffer)
                        speech_buffer = []
                        silence_run = 0
                        in_speech = False
                        with self._lock:
                            if self._state != STATE_PAUSED and self._active.is_set():
                                self._state = STATE_LISTENING

    def _process_utterance(self, frames):
        with self._lock:
            self._state = STATE_PROCESSING

        raw = b"".join(frames)
        audio_int16 = np.frombuffer(raw, dtype=np.int16)
        text = transcribe(audio_int16, SAMPLE_RATE)

        if not text or not text.strip():
            logger.debug("VoiceIO | Transkripsi kosong atau diabaikan oleh VAD.")
            with self._lock:
                self._state = STATE_PAUSED if self._paused.is_set() else STATE_LISTENING
            return

        masked = _mask_transcript(text)
        now = time.time()
        with self._lock:
            self._last_transcript_at = now
            self._last_transcript_masked = masked
            self._state = STATE_PAUSED if self._paused.is_set() else STATE_LISTENING

        logger.info("VoiceIO | Transkripsi suara diterima: '%s' (panjang: %d)", masked, len(text))

        if self._fusion_enabled.is_set() and self.fusion_callback:
            try:
                text = self.fusion_callback(text)
            except Exception as exc:
                logger.warning("VoiceIO | Error pada visual fusion callback: %s", exc)

        if self.on_transcript:
            try:
                self.on_transcript(text)
            except Exception as exc:
                logger.error("VoiceIO | Error saat mengeksekusi on_transcript: %s", exc)
