"""
core/vae/models.py — VERA Adaptive Experience (VAE) Protocol Models v2.

Defines formal typed contracts for structured adaptive experience generation.
Protocol: "vae"
Version: "2.0" (Compatible with v1.0 clients)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid


class VaeBlockType(str, Enum):
    # Foundational Content
    MARKDOWN = "markdown"
    TEXT = "text"
    CODE = "code"
    TABLE = "table"
    IMAGE = "image"
    SVG = "svg"
    INTERACTIVE_SVG = "interactive-svg"
    VRRP = "vrrp"
    TOPOLOGY_GRAPH = "topology-graph"
    MERMAID = "mermaid"
    GRAPH = "graph"
    MAP = "map"

    # Telemetry & Resource Visualizations
    METRIC_CARD = "metric-card"
    METRIC_GRID = "metric-grid"
    RESOURCE_GAUGE = "resource-gauge"
    INTERFACE_STATUS = "interface-status"

    # Network Diagnostics & Path Analysis
    HOP_TRACEROUTE = "hop-by-hop-traceroute"
    ROUTE_TABLE = "route-table-view"

    # Operations & Intelligence
    INCIDENT_SUMMARY = "incident-summary"
    ROOT_CAUSE_PANEL = "root-cause-panel"
    REMEDIATION_PLAN = "remediation-plan"
    CONFIG_DIFF = "config-diff"
    INVESTIGATION_TIMELINE = "investigation-timeline"
    EVIDENCE_CARD = "evidence-card"
    HEALTH_SUMMARY = "health-summary"
    TOPOLOGY_DETAIL = "topology-detail"

    # Interaction & Action Execution
    ACTION_CARD = "action-card"
    DIO_INTERACTION = "dio-interaction"
    WORKFLOW_RECOVERY = "workflow-recovery"

    # Fallback
    UNKNOWN = "unknown"


def _clean_dict(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None}


@dataclass
class VaeBlock:
    id: str
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return _clean_dict({
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "metadata": self.metadata,
            "created_at": self.created_at,
        })


@dataclass
class VaePayload:
    blocks: List[VaeBlock] = field(default_factory=list)
    protocol: str = "vae"
    version: str = "2.0"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _clean_dict({
            "protocol": self.protocol,
            "version": self.version,
            "blocks": [b.to_dict() for b in self.blocks],
            "metadata": self.metadata,
            "created_at": self.created_at,
        })
