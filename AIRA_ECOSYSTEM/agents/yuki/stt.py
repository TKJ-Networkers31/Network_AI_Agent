"""agents/yuki/stt.py — wrapper Speech-to-Text (faster-whisper)."""

from agents.yuki.stt_engine import transcribe as _transcribe


def transcribe(audio_int16, sample_rate: int = 16000):
    return _transcribe(audio_int16, sample_rate)
