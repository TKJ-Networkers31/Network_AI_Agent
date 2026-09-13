"""agents/yuki/tts.py — wrapper Text-to-Speech (Kokoro).

Dua mode:
- speak(): audio diputar di speaker SERVER (mode terminal).
- synthesize_bytes(): audio dikembalikan sebagai bytes WAV, dipakai
  api/routers/ws.py untuk giliran suara PWA (diputar di browser).
"""

from agents.yuki.tts_engine import (
    speak as _speak,
    synthesize_bytes as _synthesize_bytes,
)


def speak(text: str, voice: str = "af_sarah", speed: float = 1.0,
          on_start=None, on_end=None) -> bool:
    return _speak(text, voice=voice, speed=speed, on_start=on_start, on_end=on_end)


def synthesize_bytes(text: str, voice: str = "af_sarah", speed: float = 1.0):
    return _synthesize_bytes(text, voice=voice, speed=speed)