"""
AIRA OS — Modular Protocol Intelligence Subsystem (Networking VI / WP 6.8).
"""

from core.network_intelligence.protocols.base import BaseProtocolAnalyzer, ProtocolFinding
from core.network_intelligence.protocols.bgp import BGPAnalyzer
from core.network_intelligence.protocols.ipv4 import IPv4Analyzer
from core.network_intelligence.protocols.ipv6 import IPv6Analyzer
from core.network_intelligence.protocols.layer2 import Layer2Analyzer
from core.network_intelligence.protocols.nat_firewall import NATFirewallAnalyzer
from core.network_intelligence.protocols.ospf import OSPFAnalyzer
from core.network_intelligence.protocols.qos import QoSAnalyzer
from core.network_intelligence.protocols.static_routing import StaticRoutingAnalyzer
from core.network_intelligence.protocols.tunnels import TunnelAnalyzer

ALL_PROTOCOL_ANALYZERS = [
    Layer2Analyzer(),
    IPv4Analyzer(),
    IPv6Analyzer(),
    StaticRoutingAnalyzer(),
    OSPFAnalyzer(),
    BGPAnalyzer(),
    NATFirewallAnalyzer(),
    QoSAnalyzer(),
    TunnelAnalyzer(),
]

__all__ = [
    "BaseProtocolAnalyzer",
    "ProtocolFinding",
    "Layer2Analyzer",
    "IPv4Analyzer",
    "IPv6Analyzer",
    "StaticRoutingAnalyzer",
    "OSPFAnalyzer",
    "BGPAnalyzer",
    "NATFirewallAnalyzer",
    "QoSAnalyzer",
    "TunnelAnalyzer",
    "ALL_PROTOCOL_ANALYZERS",
]
