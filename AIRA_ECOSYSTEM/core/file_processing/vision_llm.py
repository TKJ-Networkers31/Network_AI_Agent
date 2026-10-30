"""core/file_processing/vision_llm.py - VisionProvider memakai model berlabel 'vision'
di Model Router (Ollama llava/qwen-vl, Gemini, OpenRouter, NVIDIA). Kalau tidak ada model
vision multimodal yang aktif, melapor UNAVAILABLE - tidak pernah mengarang deskripsi."""
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

        # Cek apakah model bukan model teks murni yang tidak support vision
        m_lower = model.model_id.lower()
        if any(txt_only in m_lower for txt_only in ["nemotron", "qwen3:", "llama-3.1", "deepseek-coder"]):
            if not any(v_kw in m_lower for v_kw in ["vision", "vl", "multimodal"]):
                logger.info("Model '%s' adalah model teks (tidak mendukung multimodal vision), vision LLM dilewati.", model.display_name)
                return VisionResult(status=VisionStatus.UNAVAILABLE.value, provider=model.display_name,
                                    reason=f"Model '{model.display_name}' tidak mendukung multimodal vision input.")

        try:
            raw = Path(reference["absolute_path"]).read_bytes()
            b64 = base64.b64encode(raw).decode()
            if model.provider == "ollama":
                msgs = [{"role": "user", "content": PROMPT, "images": [b64]}]
            else:
                uri = f"data:{metadata.mime_type};base64,{b64}"
                msgs = [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                     {"type": "image_url", "image_url": {"url": uri}}]}]
            res = ProviderClient.chat(provider=model.provider, model=model.model_id, messages=msgs, tools=None, timeout=60)
        except Exception as exc:
            return VisionResult(status=VisionStatus.UNAVAILABLE.value, provider=model.display_name, reason=str(exc))

        if "error" in res:
            err = res["error"]
            if "does not support image" in err.lower() or "image input" in err.lower():
                return VisionResult(status=VisionStatus.UNAVAILABLE.value, provider=model.display_name, reason="Model tidak mendukung input gambar.")
            return VisionResult(status=VisionStatus.ERROR.value, provider=model.display_name, reason=err)

        text = ((res.get("message") or {}).get("content") or "").strip()
        return VisionResult(status=VisionStatus.AVAILABLE.value, provider=model.display_name,
                            analysis={"description": text})
