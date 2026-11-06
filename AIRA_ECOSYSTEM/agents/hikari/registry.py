"""
agents/hikari/registry.py — HIKARI agent registry.
Vision & YOLO modules have been decommissioned for lightweight VPS deployment.
"""

from typing import Any, Dict, List, Set

HIKARI_TOOLS: Dict[str, Any] = {}
HIKARI_TOOL_CATEGORY: Dict[str, str] = {}
HIKARI_DANGEROUS_TOOLS: Set[str] = set()
HIKARI_TOOL_SCHEMAS: List[Dict[str, Any]] = []
