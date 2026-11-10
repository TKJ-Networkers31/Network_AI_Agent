"""
core/management/models.py — Data contracts for VERA Multi-Path Device Management Architecture.

Defines supported management paths (SSH over IP, RouterOS API over IP, MAC Telnet, MAC WinBox, RoMON),
health evaluation states, selection reasons, RoMON neighbor discovery records, and controlled provisioning plans.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ManagementMethod(str, Enum):
    SSH_IP = "ssh_ip"
    API_IP = "api_ip"
    MAC_TELNET = "mac_telnet"
    MAC_WINBOX = "mac_winbox"
    ROMON = "romon"

    @classmethod
    def coerce(cls, value: Any) -> "ManagementMethod":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            val_clean = value.strip().lower()
            for member in cls:
                if member.value == val_clean or member.name.lower() == val_clean:
                    return member
        valid = ", ".join(m.value for m in cls)
        raise ValueError(f"Metode manajemen '{value}' tidak valid. Pilihan: {valid}.")


class PathStatus(str, Enum):
    ACTIVE = "active"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    AUTH_FAILED = "auth_failed"
    RESTRICTED = "restricted"


@dataclass
class ManagementPath:
    method: str
    target: str
    port: int = 22
    status: str = PathStatus.AVAILABLE.value
    is_preferred: bool = False
    is_active: bool = False
    intermediary_id: Optional[str] = None
    intermediary_name: Optional[str] = None
    hops: int = 1
    selection_reason: str = ""
    rejection_reason: str = ""
    latency_ms: Optional[float] = None
    last_tested_at: Optional[float] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManagementPath":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RomonNeighbor:
    romon_id: str
    mac: str
    identity: str
    version: str = ""
    board: str = ""
    hop_count: int = 1
    path: List[str] = field(default_factory=list)
    via_device_id: str = ""
    via_device_name: str = ""
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RomonNeighbor":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RomonProvisioningPlan:
    plan_token: str = field(default_factory=lambda: f"romon_plan_{uuid.uuid4().hex[:12]}")
    device_id: str = ""
    device_name: str = ""
    proposed_commands: List[str] = field(default_factory=list)
    security_implications: List[str] = field(default_factory=list)
    rollback_commands: List[str] = field(default_factory=list)
    requires_approval: bool = True
    approved: bool = False
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL | PROVISIONING | COMPLETED | FAILED | ROLLED_BACK
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RomonProvisioningPlan":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DeviceManagementProfile:
    device_id: str
    device_name: str
    device_type: str = "mikrotik"
    vendor: str = "MikroTik"
    model: str = ""
    routeros_version: str = ""
    ip: Optional[str] = None
    mac: Optional[str] = None
    paths: List[ManagementPath] = field(default_factory=list)
    active_path: Optional[ManagementPath] = None
    manual_selection: bool = False
    selection_rationale: str = ""
    romon_enabled: bool = False
    romon_id: Optional[str] = None
    layer2_adjacent: bool = False
    adjacent_interface: Optional[str] = None
    last_updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceManagementProfile":
        raw_paths = data.get("paths") or []
        paths = [ManagementPath.from_dict(p) if isinstance(p, dict) else p for p in raw_paths]
        active_p = data.get("active_path")
        active_path = ManagementPath.from_dict(active_p) if isinstance(active_p, dict) else active_p

        kwargs = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k not in ("paths", "active_path")}
        return cls(paths=paths, active_path=active_path, **kwargs)
