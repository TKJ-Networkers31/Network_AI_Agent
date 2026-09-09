"""agents/yuki/tts.py — wrapper Text-to-Speech (Kokoro)."""

from agents.yuki.tts_engine import speak as _speak


def speak(text: str, voice: str = "af_sarah", speed: float = 1.0,
          on_start=None, on_end=None) -> bool:
    return _speak(text, voice=voice, speed=speed, on_start=on_start, on_end=on_end)
