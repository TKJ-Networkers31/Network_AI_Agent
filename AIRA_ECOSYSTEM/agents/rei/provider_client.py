"""
agents/rei/provider_client.py

SATU-SATUNYA file di seluruh ekosistem AIRA yang boleh memanggil provider
LLM eksternal (OpenRouter/Nemotron) atau lokal (Ollama). Aturan keras dari
master prompt: "Jangan memanggil OpenRouter langsung dari tool" - jadi
agents/akane, agents/hikari, agents/yuki, dan tools/* TIDAK BOLEH import
`requests` ke openrouter.ai atau ke Ollama sama sekali. Kalau mereka butuh
reasoning, mereka minta lewat agents/rei/planner.py, bukan langsung ke sini.

Ini adalah port 1:1 dari agent/core/providers.py lama - PROVIDERS dict,
call_model(), _call_ollama(), _call_openai_compatible(), retry util,
dan get_openrouter_credits() semuanya pindah ke sini tanpa perubahan logic.

Model mapping sesuai master prompt:
  - Nemotron 120B (nvidia/nemotron-3-super-120b-a12b:free) -> reasoning berat
  - Nemotron Lightning (nvidia/nemotron-3.5-lightning:free) -> chat/cepat
  - Ollama qwen3 -> fallback lokal kalau OpenRouter tidak tersedia
"""

import logging

logger = logging.getLogger("aira.rei.provider_client")

# TODO: pindahkan PROVIDERS dict persis dari agent/core/providers.py di sini.
PROVIDERS: dict = {}

DEFAULT_PROVIDER_KEY = "ollama-qwen3-1.7b"


def get_active_provider_key() -> str:
    raise NotImplementedError("TODO: port dari agent/core/providers.py (baca dari core.memory facts)")


def call_model(messages: list[dict], tools: list[dict]) -> dict:
    """
    Bentuk return SERAGAM: {"message": {...}, "usage": {...}|None} atau
    {"error": "..."} - kontrak ini dipakai agents/rei/planner.py, jangan
    diubah tanpa update planner.py juga.

    TODO: port _call_ollama / _call_openai_compatible / _normalize_message
    dari agent/core/providers.py apa adanya.
    """
    raise NotImplementedError("TODO: port dari agent/core/providers.py::call_model")


def get_openrouter_credits() -> dict:
    raise NotImplementedError("TODO: port dari agent/core/providers.py::get_openrouter_credits")
