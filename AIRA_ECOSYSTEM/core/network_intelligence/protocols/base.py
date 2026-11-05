"""
AIRA OS — Base Modular Protocol Analyzer Contract (Networking VI / WP 6.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle


@dataclass
class ProtocolFinding:
    finding_id: str
    protocol: str
    device_id: str
    severity: str  # info, warning, critical
    category: str
    summary: str
    technical_detail: str
    evidence_ids: List[str] = field(default_factory=list)
    affected_entities: List[str] = field(default_factory=list)
    remediation_suggestion: str = ""
    confidence: float = 0.90
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "protocol": self.protocol,
            "device_id": self.device_id,
            "severity": self.severity,
            "category": self.category,
            "summary": self.summary,
            "technical_detail": self.technical_detail,
            "evidence_ids": list(self.evidence_ids),
            "affected_entities": list(self.affected_entities),
            "remediation_suggestion": self.remediation_suggestion,
            "confidence": round(float(self.confidence), 4),
            "detected_at": self.detected_at,
        }


class BaseProtocolAnalyzer:
    """Base protocol analyzer interface."""

    protocol_name: str = "base"
    supported_versions: List[str] = ["RouterOS v6", "RouterOS v7"]
    required_evidence: List[str] = []
    optional_evidence: List[str] = []
    known_limitations: List[str] = []

    def can_analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> bool:
        """Returns True if minimum required evidence exists for the target device."""
        if not self.required_evidence:
            return True
        for req in self.required_evidence:
            if req == "device_resources" and device_id in bundle.device_evidence:
                continue
            if req == "interfaces" and bundle.interface_evidence.get(device_id):
                continue
            if req == "routes" and bundle.routing_evidence.get(device_id):
                continue
            pdata = bundle.protocol_evidence.get(device_id) or {}
            if req in pdata and pdata[req] is not None:
                continue
            return False
        return True

    def analyze(self, bundle: NetworkEvidenceBundle, device_id: str) -> List[ProtocolFinding]:
        raise NotImplementedError
