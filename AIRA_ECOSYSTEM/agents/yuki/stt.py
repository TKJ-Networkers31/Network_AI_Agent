"""
agents/yuki/stt.py — bagian Speech-to-Text dari YUKI (Your Unified
Knowledge Interface), pakai Whisper (faster-whisper, model 'tiny', CPU-only).

Wrapper tipis di atas agent/voice/stt.py lama. TODO migrasi: git mv
agent/voice/stt.py -> agents/yuki/stt_engine.py, lalu import di sini.
"""

# from agents.yuki.stt_engine import transcribe as _transcribe


def transcribe(audio_int16, sample_rate: int = 16000) -> str | None:
    """TODO: return _transcribe(audio_int16, sample_rate)"""
    raise NotImplementedError("TODO: port dari agent/voice/stt.py")
