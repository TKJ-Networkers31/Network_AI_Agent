"""
core/host/ — Host Abstraction Layer (HAL) untuk AIRA OS (Sprint 02).

Public API:
    from core.host import get_host_info, get_default_adapter, HostInfo

FSE (core/filesystem/*) HANYA boleh mengambil informasi host lewat
fungsi-fungsi ini - TIDAK PERNAH memanggil platform.system()/os.name
secara langsung.
"""

from core.host.models import HostInfo
from core.host.detector import (
    detect_host,
    get_host_adapter,
    get_host_info,
    get_default_adapter,
)

__all__ = [
    "HostInfo",
    "detect_host",
    "get_host_adapter",
    "get_host_info",
    "get_default_adapter",
]