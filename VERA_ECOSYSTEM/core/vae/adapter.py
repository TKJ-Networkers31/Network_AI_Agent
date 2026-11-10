"""
core/vae/adapter.py — VAE Protocol Response Adapter.

Bridges BrainResponse, DIO InteractionSchema, and execution telemetry
into the unified VERA Adaptive Experience (VAE) protocol representation (v2.0).
Guarantees 100% backward compatibility with existing API contracts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.vae.composer import ExperienceComposer
from core.vae.models import VaeBlock, VaeBlockType, VaePayload
from core.vae.planner import ExperiencePlan, ExperiencePlanner, VaeIntent

logger = logging.getLogger("vera.vae.adapter")

_default_composer = ExperienceComposer()


def brain_response_to_vae_payload(
    answer: str,
    interaction_schema: Optional[Dict[str, Any]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = None,
    query: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> VaePayload:
    """
    Transforms BrainResponse outputs into a formal VaePayload v2.
    Employs ExperiencePlanner and ExperienceComposer to generate rich visual blocks.
    """
    try:
        return _default_composer.compose(
            answer=answer,
            steps=steps,
            interaction_schema=interaction_schema,
            session_id=session_id,
            query=query,
            context=context,
        )
    except Exception as exc:
        logger.error("VAE Adapter encountered unexpected error: %s. Falling back to basic payload.", exc)
        # Fallback to basic blocks
        blocks = []
        if answer and answer.strip():
            blocks.append(
                VaeBlock(
                    id="blk_fallback_txt",
                    type=VaeBlockType.MARKDOWN.value,
                    data={"content": answer.strip()},
                )
            )
        return VaePayload(
            blocks=blocks,
            protocol="vae",
            version="2.0",
            metadata={"session_id": session_id or "", "fallback": True},
        )
