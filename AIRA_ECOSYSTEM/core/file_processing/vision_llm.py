"""core/file_processing/vision_llm.py - VisionProvider nyata memakai model berlabel 'vision'
di Model Router (Ollama llava/qwen-vl, Gemini, OpenRouter, NVIDIA). Kalau tidak ada model
vision yang aktif, melapor UNAVAILABLE - tidak pernah mengarang deskripsi."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from core.vision.models import VisionResult, VisionStatus

logger = logging.getLogger("aira.file_processing.vision")
PROMPT = ("Jelaskan isi gambar ini secara faktual dan rinci (perangkat, label, koneksi, IP/VLAN yang "
          "terlihat, teks penting). Jangan menebak hal yang tidak terlihat.")


class LLMVisionProvider:
    name = "llm-vision"

    def analyze(self, reference, metadata) -> VisionResult:
        try:
            from agents.rei.provider_client import ProviderClient
            from core.model_router import get_model_router
            model = get_model_router().select_for_label("vision", publish=False)
        except Exception as exc:
            return VisionResult(status=VisionStatus.UNAVAILABLE.value, provider=self.name, reason=f"Model Router: {exc}")
        if model is None or not (reference and reference.get("absolute_path")):
            return VisionResult(status=VisionStatus.UNAVAILABLE.value, provider=self.name,
                                reason="Tidak ada model berlabel 'vision' yang aktif.")
        raw = Path(reference["absolute_path"]).read_bytes()
        b64 = base64.b64encode(raw).decode()
        if model.provider == "ollama":
            msgs = [{"role": "user", "content": PROMPT, "images": [b64]}]
        else:
            uri = f"data:{metadata.mime_type};base64,{b64}"
            msgs = [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                 {"type": "image_url", "image_url": {"url": uri}}]}]
        res = ProviderClient.chat(provider=model.provider, model=model.model_id, messages=msgs, tools=None, timeout=300)
        if "error" in res:
            return VisionResult(status=VisionStatus.ERROR.value, provider=model.display_name, reason=res["error"])
        text = ((res.get("message") or {}).get("content") or "").strip()
        return VisionResult(status=VisionStatus.AVAILABLE.value, provider=model.display_name,
                            analysis={"description": text})
