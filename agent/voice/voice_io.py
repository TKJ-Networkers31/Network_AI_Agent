"""
Orkestrasi voice I/O: mic listening dengan VAD (webrtcvad),
kirim ke Whisper API saat deteksi akhir ucapan, dan kontrol
barge-in supaya mic tidak menangkap suara Kokoro sendiri.

Desain: listen_loop() jalan di background thread terus-menerus
selama voice mode aktif. Setiap kali VAD deteksi satu utterance
selesai (ada jeda diam cukup panjang setelah suara), audio
di-transkripsi dan hasil teksnya dimasukkan ke callback yang
diberikan caller (biasanya push ke queue utama di main.py).
"""

import threading
import collections

import numpy as np
import sounddevice as sd
import webrtcvad

from agent.voice.stt import transcribe
from agent.core.logger import log_error, logger


SAMPLE_RATE = 16000       # webrtcvad hanya terima 8k/16k/32k/48k
FRAME_MS = 30              # ukuran frame VAD: 10/20/30 ms
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

# Berapa lama diam (ms) dianggap akhir ucapan. Terlalu pendek bikin
# kalimat kepotong, terlalu panjang bikin jeda terasa lambat.
SILENCE_END_MS = 800
SILENCE_END_FRAMES = SILENCE_END_MS // FRAME_MS

# Sensitivitas VAD: 0 (paling longgar) - 3 (paling ketat/agresif
# nolak noise). 2 biasanya titik aman untuk ruangan normal.
VAD_AGGRESSIVENESS = 2

MIN_UTTERANCE_FRAMES = 10  # buang utterance super pendek (noise klik dsb)


class VoiceIO:

    def __init__(self, on_transcript):
        """
        on_transcript: callback(text: str) dipanggil tiap kali ada
        hasil transkripsi valid dari ucapan user.
        """

        self.on_transcript = on_transcript
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

        self._active = threading.Event()   # voice mode on/off
        self._paused = threading.Event()   # dipause selama TTS bicara
        self._stop = threading.Event()
        self._thread = None

    # --------------------------------------------------------
    # KONTROL
    # --------------------------------------------------------

    def start(self):
        """Aktifkan voice mode dan mulai listener thread kalau belum jalan."""

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
        """Matikan voice mode (listener thread berhenti total)."""

        self._active.clear()
        self._stop.set()

        logger.info("VOICE | voice mode dimatikan.")

    def is_active(self):
        return self._active.is_set()

    def pause_mic(self):
        """Dipanggil sebelum TTS mulai bicara - cegah barge-in loop."""
        self._paused.set()

    def resume_mic(self):
        """Dipanggil setelah TTS selesai bicara."""
        self._paused.clear()

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

            # Kalau mic sedang di-pause (TTS lagi bicara) atau voice
            # mode nonaktif, buang frame - jangan diproses sama sekali.
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

                frame = frame_queue.popleft()

                if len(frame) != FRAME_SAMPLES * 2:
                    # Frame size nggak pas (blocksize/format mismatch di
                    # device tertentu) - skip biar webrtcvad nggak error.
                    continue

                is_speech = self.vad.is_speech(frame, SAMPLE_RATE)

                if is_speech:

                    speech_buffer.append(frame)
                    silence_run = 0
                    in_speech = True

                elif in_speech:

                    silence_run += 1
                    speech_buffer.append(frame)  # simpan sedikit ekor diam

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

        if text:
            logger.info(f"VOICE | transkripsi: {text}")
            self.on_transcript(text)
        else:
            logger.info("VOICE | transkripsi kosong/gagal, diabaikan.")