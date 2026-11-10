"""
core/management/ — Multi-Path MikroTik Device Management Subsystem (Phase 3).

Provides:
- Dedicated management methods: SSH over IP, RouterOS API, MAC Telnet, MAC WinBox, RoMON
- Deterministic capability detection and evidence-based selection engine
- RoMON neighbor discovery, multi-hop routing, and controlled provisioning workflow
- MultiPathManager singleton
"""

from core.management.models import (
    ManagementMethod,
    PathStatus,
    ManagementPath,
    DeviceManagementProfile,
    RomonNeighbor,
    RomonProvisioningPlan,
)
from core.management.capability_detector import (
    CapabilityDetector,
    is_mac,
    is_ip,
)
from core.management.selection_engine import SelectionEngine
from core.management.mac_manager import MacManager
from core.management.romon_manager import RomonManager
from core.management.manager import MultiPathManager, get_multi_path_manager

__all__ = [
    "ManagementMethod",
    "PathStatus",
    "ManagementPath",
    "DeviceManagementProfile",
    "RomonNeighbor",
    "RomonProvisioningPlan",
    "CapabilityDetector",
    "is_mac",
    "is_ip",
    "SelectionEngine",
    "MacManager",
    "RomonManager",
    "MultiPathManager",
    "get_multi_path_manager",
]
