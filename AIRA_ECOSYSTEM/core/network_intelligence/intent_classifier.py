"""
AIRA OS — Natural Language Network Investigation Intent Classifier (Networking VI / WP 6.10).

Deterministically classifies Indonesian and English network operations queries into all 14
`InvestigationIntent` categories with zero command execution.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.network_intelligence.intelligence_models import InvestigationIntent


class IntentClassifier:
    """Zero-command deterministic intent classifier supporting Indonesian and English."""

    PATTERNS: List[Tuple[InvestigationIntent, List[str]]] = [
        (
            InvestigationIntent.FAILURE_SIMULATION,
            [
                r"\b(simulasi|simulasikan|what if|bagaimana jika|apa dampak jika.*gagal|jika.*down)\b",
                r"\b(seandainya|andaikan|simulate)\b",
            ],
        ),
        (
            InvestigationIntent.CHANGE_IMPACT,
            [
                r"\b(dampak|impact|blast radius|siapa yang terdampak|efek jika|pengaruh)\b",
                r"\b(dependen|dependency paling besar|ketergantungan)\b",
            ],
        ),
        (
            InvestigationIntent.HISTORICAL_COMPARISON,
            [
                r"\b(bandingkan|sebelumnya|pernah terjadi|sejarah|history|historical|kemarin|tadi)\b",
                r"\b(compare|recurring|berulang|trend|sebelum insiden)\b",
            ],
        ),
        (
            InvestigationIntent.PATH_ANALYSIS,
            [
                r"\b(jalur|path|traceroute|rute trafik|menuju ke|dari.*ke|forwarding|lewat mana)\b",
                r"\b(trace|next hop|hop sequence)\b",
            ],
        ),
        (
            InvestigationIntent.ROOT_CAUSE_ANALYSIS,
            [
                r"\b(kenapa|mengapa|penyebab|akar masalah|root cause|rca|sebab|alasan)\b",
                r"\b(why|cause|bukti bahwa.*penyebab)\b",
            ],
        ),
        (
            InvestigationIntent.ANOMALY_INVESTIGATION,
            [
                r"\b(anomali|anomaly|tidak biasa|lonjakan|spike|unusual|deviasi|flapping)\b",
            ],
        ),
        (
            InvestigationIntent.HEALTH_ASSESSMENT,
            [
                r"\b(kesehatan|health|kondisi jaringan|status keseluruhan|overall condition)\b",
                r"\b(sehat|degraded|critical)\b",
            ],
        ),
        (
            InvestigationIntent.INCIDENT_INVESTIGATION,
            [
                r"\b(insiden|incident|gangguan|alert|alarm|peringatan|outage)\b",
            ],
        ),
        (
            InvestigationIntent.PROTOCOL_ANALYSIS,
            [
                r"\b(ospf|bgp|vlan|bridge|l2|tunnel|gre|wireguard|ipsec|nat|firewall|qos)\b",
                r"\b(adjacency|peer|session|trunk)\b",
            ],
        ),
        (
            InvestigationIntent.ROUTE_INVESTIGATION,
            [
                r"\b(routing|route|tabel rute|rib|fib|prefix|lpm|default gateway)\b",
            ],
        ),
        (
            InvestigationIntent.INTERFACE_INVESTIGATION,
            [
                r"\b(interface|antarmuka|port|ether\d|sfp|crc|drop|error counter|link)\b",
            ],
        ),
        (
            InvestigationIntent.DEVICE_INVESTIGATION,
            [
                r"\b(router|switch|cpu|memory|ram|uptime|reboot|perangkat|device)\b",
            ],
        ),
        (
            InvestigationIntent.NETWORK_CONCEPT_EXPLANATION,
            [
                r"\b(apa itu|jelaskan konsep|pengertian|definisi|bagaimana cara kerja)\b",
            ],
        ),
        (
            InvestigationIntent.NETWORK_OVERVIEW,
            [
                r"\b(overview|ringkasan|rangkuman|inventaris|topologi|semua router|daftar)\b",
            ],
        ),
    ]

    @classmethod
    def classify(cls, query: str) -> Tuple[InvestigationIntent, float, List[str]]:
        """
        Classifies query text into an InvestigationIntent.
        Returns `(intent, confidence, matched_keywords)`.
        Guaranteed to execute zero device commands.
        """
        q = (query or "").strip().lower()
        if not q:
            return InvestigationIntent.NETWORK_OVERVIEW, 0.50, []

        for intent, patterns in cls.PATTERNS:
            for pat in patterns:
                m = re.search(pat, q, re.IGNORECASE)
                if m:
                    return intent, 0.92, [m.group(0)]

        # Default fallback
        return InvestigationIntent.NETWORK_OVERVIEW, 0.60, []
