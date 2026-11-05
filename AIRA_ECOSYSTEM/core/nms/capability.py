"""
AIRA OS — Networking V Device Capability Prober & Capability-Aware Monitoring (WP 5.1).

Defines the capability hierarchy, discovery logic, capability caching,
and protocol qualification rules.

Guarantees:
- Capability probing is bounded, safe, and cacheable with TTL.
- Protocol failures (e.g. SNMP AUTH_FAILED) NEVER mark the entire device UNHEALTHY.
- Capabilities distinguish SUPPORTED, UNSUPPORTED, UNKNOWN, AUTH_FAILED,
  TEMPORARILY_UNAVAILABLE, and DISABLED_BY_POLICY.
- Zero configuration mutation or intrusive probes during discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Set

from core.canonical_network import CanonicalDevice
from core.nms.models import sanitize_telemetry_secrets

logger = logging.getLogger("aira.nms.capability")


class CapabilityState(str, Enum):
    """Evaluation status of a specific monitoring protocol or feature."""
    SUPPORTED = "SUPPORTED"                          # Tested and verified working
    UNSUPPORTED = "UNSUPPORTED"                      # Target device does not implement this protocol
    UNKNOWN = "UNKNOWN"                              # Not yet tested or pending discovery
    AUTH_FAILED = "AUTH_FAILED"                      # Protocol present but rejected credentials
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE" # Network timeout or target busy
    DISABLED_BY_POLICY = "DISABLED_BY_POLICY"        # Administratively turned off in device profile


class MonitoringCapability(str, Enum):
    """Individual monitoring capability domains."""
    ICMP = "icmp"
    SNMP_V2C = "snmp_v2c"
    SNMP_V3 = "snmp_v3"
    ROUTEROS_SSH = "routeros_ssh"
    ROUTEROS_API = "routeros_api"
    LINUX_SSH = "linux_ssh"
    INTERFACE_METRICS = "interface_metrics"
    RESOURCE_METRICS = "resource_metrics"
    TEMPERATURE_METRICS = "temperature_metrics"
    NETWORK_QUALITY = "network_quality"


@dataclass
class CapabilityAssessment:
    """Detailed capability assessment for a single protocol/domain."""
    capability: str
    state: str = CapabilityState.UNKNOWN.value
    last_tested_at: float = field(default_factory=time.time)
    response_time_ms: float = 0.0
    error_message: Optional[str] = None
    tested_port: Optional[int] = None

    @property
    def is_usable(self) -> bool:
        return self.state == CapabilityState.SUPPORTED.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "state": self.state,
            "last_tested_at": self.last_tested_at,
            "response_time_ms": round(self.response_time_ms, 2),
            "error_message": sanitize_telemetry_secrets(self.error_message) if self.error_message else None,
            "tested_port": self.tested_port,
            "is_usable": self.is_usable,
        }


@dataclass
class DeviceCapabilityProfile:
    """
    Complete capability state matrix for a registered device.
    Cached in memory and persisted into nms_device_profiles.
    """
    device_id: str
    management_ip: str
    platform: str = "mikrotik"
    ros_major_version: Optional[int] = None
    profile_ttl_seconds: float = 3600.0          # Cache capabilities for 1 hour by default
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    capabilities: Dict[str, CapabilityAssessment] = field(default_factory=dict)

    def is_expired(self, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.time()
        return (ts - self.updated_at) > self.profile_ttl_seconds

    def get_state(self, capability: MonitoringCapability) -> str:
        asmt = self.capabilities.get(capability.value)
        return asmt.state if asmt else CapabilityState.UNKNOWN.value

    def is_supported(self, capability: MonitoringCapability) -> bool:
        asmt = self.capabilities.get(capability.value)
        return bool(asmt and asmt.is_usable)

    def set_assessment(
        self,
        capability: MonitoringCapability,
        state: CapabilityState,
        response_time_ms: float = 0.0,
        error_message: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self.capabilities[capability.value] = CapabilityAssessment(
            capability=capability.value,
            state=state.value,
            last_tested_at=time.time(),
            response_time_ms=response_time_ms,
            error_message=error_message,
            tested_port=port,
        )
        self.updated_at = time.time()

    def preferred_telemetry_source(self) -> str:
        """Determines the most efficient supported telemetry protocol for this device."""
        if self.is_supported(MonitoringCapability.SNMP_V2C) or self.is_supported(MonitoringCapability.SNMP_V3):
            return "snmp"
        if self.is_supported(MonitoringCapability.ROUTEROS_SSH) or self.is_supported(MonitoringCapability.LINUX_SSH):
            return "ssh"
        if self.is_supported(MonitoringCapability.ROUTEROS_API):
            return "routeros_api"
        return "icmp_only"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "management_ip": self.management_ip,
            "platform": self.platform,
            "ros_major_version": self.ros_major_version,
            "updated_at": self.updated_at,
            "preferred_telemetry_source": self.preferred_telemetry_source(),
            "capabilities": {k: v.to_dict() for k, v in self.capabilities.items()},
        }


class CapabilityProber:
    """
    Thread-safe and async-safe capability discovery prober.
    Ensures capability probing is performed only on demand or when cache expires,
    preventing repeated port hammering during continuous polling cycles.
    """

    def __init__(self, cache_ttl_seconds: float = 3600.0):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, DeviceCapabilityProfile] = {}

    def get_cached_profile(self, device_id: str) -> Optional[DeviceCapabilityProfile]:
        prof = self._cache.get(device_id)
        if prof and not prof.is_expired():
            return prof
        return None

    def store_profile(self, profile: DeviceCapabilityProfile) -> None:
        self._cache[profile.device_id] = profile

    def invalidate(self, device_id: str) -> None:
        self._cache.pop(device_id, None)

    def evaluate_initial_profile_from_inventory(
        self,
        device_id: str,
        host: str,
        device_meta: Optional[Dict[str, Any]] = None,
    ) -> DeviceCapabilityProfile:
        """
        Synthesizes an initial capability profile from existing Inventory metadata
        before active network interrogation commences.
        """
        meta = device_meta or {}
        platform = str(meta.get("device_type", "mikrotik")).lower()
        profile = DeviceCapabilityProfile(
            device_id=device_id,
            management_ip=host,
            platform=platform,
            profile_ttl_seconds=self.cache_ttl_seconds,
        )

        # ICMP is always candidate by default
        profile.set_assessment(MonitoringCapability.ICMP, CapabilityState.UNKNOWN)

        # Check SNMP config
        snmp_enabled = bool(meta.get("snmp_enabled", False))
        if snmp_enabled:
            snmp_ver = str(meta.get("snmp_version", "v2c")).lower()
            if "3" in snmp_ver:
                profile.set_assessment(MonitoringCapability.SNMP_V3, CapabilityState.UNKNOWN, port=int(meta.get("snmp_port", 161)))
            else:
                profile.set_assessment(MonitoringCapability.SNMP_V2C, CapabilityState.UNKNOWN, port=int(meta.get("snmp_port", 161)))
        else:
            profile.set_assessment(MonitoringCapability.SNMP_V2C, CapabilityState.DISABLED_BY_POLICY)

        # Check SSH config
        if platform == "mikrotik":
            profile.set_assessment(MonitoringCapability.ROUTEROS_SSH, CapabilityState.UNKNOWN, port=int(meta.get("port", 22)))
            profile.set_assessment(MonitoringCapability.LINUX_SSH, CapabilityState.UNSUPPORTED)
        elif platform in ("linux", "server"):
            profile.set_assessment(MonitoringCapability.LINUX_SSH, CapabilityState.UNKNOWN, port=int(meta.get("port", 22)))
            profile.set_assessment(MonitoringCapability.ROUTEROS_SSH, CapabilityState.UNSUPPORTED)
        else:
            profile.set_assessment(MonitoringCapability.ROUTEROS_SSH, CapabilityState.UNKNOWN)

        self.store_profile(profile)
        return profile
