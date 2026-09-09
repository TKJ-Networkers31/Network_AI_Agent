"""
agents/yuki/tts.py — bagian Text-to-Speech dari YUKI, pakai Kokoro (ONNX,
lokal/offline).

Wrapper tipis di atas agent/voice/tts.py lama. TODO migrasi: git mv
agent/voice/tts.py -> agents/yuki/tts_engine.py, lalu import di sini.
"""

# from agents.yuki.tts_engine import speak as _speak


def speak(text: str, voice: str = "af_sarah", speed: float = 1.0,
          on_start=None, on_end=None) -> bool:
    """TODO: return _speak(text, voice, speed, on_start, on_end)"""
    raise NotImplementedError("TODO: port dari agent/voice/tts.py")
