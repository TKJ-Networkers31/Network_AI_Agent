"""
Orkestrasi voice I/O: mic listening dengan VAD berbasis energi
audio (RMS threshold), kirim ke faster-whisper saat deteksi akhir
ucapan, dan kontrol barge-in supaya mic tidak menangkap suara
Kokoro sendiri.

Mendukung mode "sensor gabungan" (multimodal fusion) - kalau
diaktifkan, setiap ucapan yang selesai ditranskripsi juga otomatis
dilengkapi konteks visual dari webcam sebelum diteruskan ke LLM.
Lihat agent/core/multimodal.py untuk detail penggabungannya.
"""

import threading
import collections

import numpy as np
import sounddevice as sd

from agent.voice.stt import transcribe
from agent.core.multimodal import fuse_voice_and_vision
from agent.core.logger import log_error, logger


SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

ENERGY_THRESHOLD = 500

SILENCE_END_MS = 800
SILENCE_END_FRAMES = SILENCE_END_MS // FRAME_MS

MIN_UTTERANCE_FRAMES = 10


def _frame_rms(frame_int16):

    if len(frame_int16) == 0:
        return 0.0

    samples = frame_int16.astype(np.float64)

    return float(np.sqrt(np.mean(samples ** 2)))


class VoiceIO:

    def __init__(self, on_transcript):

        self.on_transcript = on_transcript

        self._active = threading.Event()
        self._paused = threading.Event()
        self._stop = threading.Event()

        # Mode fusion suara+visual - default OFF, diaktifkan manual
        # lewat command di main.py. OFF berarti perilaku persis
        # seperti sebelumnya (hanya transkripsi suara).
        self._fusion_enabled = threading.Event()

        self._thread = None

    # --------------------------------------------------------
    # KONTROL
    # --------------------------------------------------------

    def start(self):

        self._active.set()

        if self._thread is None or not self._thread.is_alive():

            self._stop.clear()

            self._thread = threading.Thread(
                target=self._listen_loop,
                daemon=True
            )

            self._thread.start()

            logger.info("VOICE | listener thread dimulai.")

    def stop(self):

        self._active.clear()
        self._stop.set()

        logger.info("VOICE | voice mode dimatikan.")

    def is_active(self):
        return self._active.is_set()

    def pause_mic(self):
        self._paused.set()

    def resume_mic(self):
        self._paused.clear()

    def enable_fusion(self):
        """Aktifkan sensor gabungan: tiap ucapan otomatis dilengkapi konteks visual."""
        self._fusion_enabled.set()
        logger.info("VOICE | fusion suara+visual diaktifkan.")

    def disable_fusion(self):
        self._fusion_enabled.clear()
        logger.info("VOICE | fusion suara+visual dimatikan.")

    def is_fusion_enabled(self):
        return self._fusion_enabled.is_set()

    # --------------------------------------------------------
    # LISTENER LOOP
    # --------------------------------------------------------

    def _listen_loop(self):

        try:
            self._run_stream()
        except Exception as exc:
            log_error("voice_io._listen_loop", exc)

    def _run_stream(self):

        frame_queue = collections.deque()
        speech_buffer = []
        silence_run = 0
        in_speech = False

        def audio_callback(indata, frames, time_info, status):

            if status:
                logger.info(f"VOICE | sounddevice status: {status}")

            if self._paused.is_set() or not self._active.is_set():
                return

            pcm16 = (indata[:, 0] * 32767).astype(np.int16)
            frame_queue.append(pcm16.tobytes())

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
            callback=audio_callback,
        )

        with stream:

            while not self._stop.is_set():

                if not frame_queue:
                    sd.sleep(10)
                    continue

                frame_bytes = frame_queue.popleft()
                frame_int16 = np.frombuffer(frame_bytes, dtype=np.int16)

                rms = _frame_rms(frame_int16)
                is_speech = rms >= ENERGY_THRESHOLD

                if is_speech:

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

    def _process_utterance(self, frames):

        raw = b"".join(frames)
        audio_int16 = np.frombuffer(raw, dtype=np.int16)

        text = transcribe(audio_int16, SAMPLE_RATE)

        if not text:
            logger.info("VOICE | transkripsi kosong/gagal, diabaikan.")
            return

        logger.info(f"VOICE | transkripsi: {text}")

        # Kalau fusion aktif, tambahkan konteks visual SEBELUM
        # dikirim ke callback (yang akan meneruskannya ke LLM
        # sebagai satu pesan user utuh). Ini dilakukan di sini,
        # bukan di main.py, supaya main.py tidak perlu tahu detail
        # webcam sama sekali - cukup terima teks jadi.
        if self._fusion_enabled.is_set():
            text = fuse_voice_and_vision(text)

        self.on_transcript(text)