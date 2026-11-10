"""
core/vae/protocol.py — VAE Protocol Validation & Serialization Engine.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.vae.models import VaeBlock, VaeBlockType, VaePayload

logger = logging.getLogger("vera.vae.protocol")

SUPPORTED_BLOCK_TYPES = frozenset({t.value for t in VaeBlockType if t != VaeBlockType.UNKNOWN})


def validate_vae_block(raw: Any) -> Tuple[bool, Optional[VaeBlock], Optional[str]]:
    """
    Validates a raw dictionary against VaeBlock contract.
    Returns (is_valid, block, error_message).
    """
    if not isinstance(raw, dict):
        return False, None, "Block must be a JSON object"

    block_id = raw.get("id")
    if not block_id or not isinstance(block_id, str):
        block_id = f"vae_{uuid.uuid4().hex[:8]}"

    block_type = raw.get("type")
    if not block_type or not isinstance(block_type, str):
        return False, VaeBlock(id=block_id, type="unknown", data={"raw": raw}), "Missing or invalid block type"

    block_type_clean = block_type.strip().lower()

    if block_type_clean not in SUPPORTED_BLOCK_TYPES:
        return False, VaeBlock(
            id=block_id,
            type="unknown",
            data={"unsupported_type": block_type, "original_data": raw.get("data", {})},
        ), f"Unsupported block type: '{block_type}'"

    data = raw.get("data")
    if data is None or not isinstance(data, dict):
        data = {}

    block = VaeBlock(
        id=block_id,
        type=block_type_clean,
        data=data,
        metadata=raw.get("metadata") or {},
        created_at=float(raw.get("created_at") or 0.0) or None,
    )
    return True, block, None


def validate_vae_payload(raw: Any) -> Tuple[bool, Optional[VaePayload], List[str]]:
    """
    Validates an entire VAE response envelope.
    """
    issues = []
    if not isinstance(raw, dict):
        return False, None, ["Payload must be a dictionary"]

    protocol = raw.get("protocol", "vae")
    version = str(raw.get("version", "1.0"))

    raw_blocks = raw.get("blocks", [])
    if not isinstance(raw_blocks, list):
        return False, None, ["'blocks' field must be an array"]

    validated_blocks = []
    for idx, b in enumerate(raw_blocks):
        ok, block, err = validate_vae_block(b)
        if ok and block:
            validated_blocks.append(block)
        elif block:
            # Fallback block included to prevent total crash
            validated_blocks.append(block)
            issues.append(f"Block [{idx}]: {err}")
        else:
            issues.append(f"Block [{idx}] dropped: {err}")

    payload = VaePayload(
        blocks=validated_blocks,
        protocol=protocol,
        version=version,
        metadata=raw.get("metadata") or {},
    )
    return len(issues) == 0, payload, issues
