"""
AIRA OS — Edge Gateway Domain Models (Networking VIII / WP 8.4.1).

Defines authoritative domain contracts for:
- EdgeGateway lifecycle and site binding
- GatewayEnrollmentToken single-use cryptographic credentials
- GatewayHeartbeat health reports
- GatewayEnvelope telemetry ingestion wrappers
- GatewaySequenceState replay protection and deduplication
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from typing import Any, Dict, List, Optional
import uuid


class GatewayLifecycleState(str, Enum):
    PROVISIONING = "PROVISIONING"
    ENROLLMENT_PENDING = "ENROLLMENT_PENDING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    REVOKED = "REVOKED"
    DECOMMISSIONED = "DECOMMISSIONED"


class EnrollmentTokenStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class TelemetryType(str, Enum):
    INTERFACE_METRICS = "INTERFACE_METRICS"
    DEVICE_HEALTH = "DEVICE_HEALTH"
    TOPOLOGY_NEIGHBORS = "TOPOLOGY_NEIGHBORS"
    ROUTE_TABLE_SAMPLE = "ROUTE_TABLE_SAMPLE"
    DIAGNOSTIC_PING = "DIAGNOSTIC_PING"


class GatewayHealthStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


@dataclass
class EdgeGateway:
    """Canonical Edge Gateway entity representing a hybrid customer-edge collector."""
    gateway_id: str
    tenant_id: str
    site_id: str
    name: str
    status: str = GatewayLifecycleState.ACTIVE.value
    version: str = "1.0.0"
    certificate_fingerprint: Optional[str] = None
    auth_token_hash: Optional[str] = None
    last_seen_at_utc: Optional[str] = None
    last_ip: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "name": self.name,
            "status": self.status,
            "version": self.version,
            "certificate_fingerprint": self.certificate_fingerprint,
            "last_seen_at_utc": self.last_seen_at_utc,
            "last_ip": self.last_ip,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class GatewayEnrollmentToken:
    """Short-lived, single-use token for onboarding an edge gateway."""
    token_id: str
    token_hash: str
    tenant_id: str
    site_id: str
    created_by: str
    status: str = EnrollmentTokenStatus.ACTIVE.value
    expires_at_utc: str = ""
    redeemed_at_utc: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "created_by": self.created_by,
            "status": self.status,
            "expires_at_utc": self.expires_at_utc,
            "redeemed_at_utc": self.redeemed_at_utc,
            "created_at": self.created_at,
        }


@dataclass
class GatewayHeartbeat:
    """Periodic health ping sent by edge gateway to Central NOC."""
    gateway_id: str
    tenant_id: str
    site_id: str
    timestamp_utc: str
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    queue_depth: int = 0
    oldest_message_age_sec: float = 0.0
    collector_status: str = "HEALTHY"
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "timestamp_utc": self.timestamp_utc,
            "cpu_utilization": self.cpu_utilization,
            "memory_utilization": self.memory_utilization,
            "queue_depth": self.queue_depth,
            "oldest_message_age_sec": self.oldest_message_age_sec,
            "collector_status": self.collector_status,
            "version": self.version,
        }


@dataclass
class GatewayEnvelope:
    """Ingestion envelope packaging telemetry samples from the edge."""
    envelope_id: str
    gateway_id: str
    tenant_id: str
    site_id: str
    sequence_number: int
    sent_at_utc: str
    telemetry_type: str
    payload: Dict[str, Any]
    source_timestamp: Optional[float] = None
    gateway_receive_timestamp: Optional[float] = None
    central_receive_timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "gateway_id": self.gateway_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "sequence_number": self.sequence_number,
            "sent_at_utc": self.sent_at_utc,
            "telemetry_type": self.telemetry_type,
            "payload": self.payload,
            "source_timestamp": self.source_timestamp,
            "gateway_receive_timestamp": self.gateway_receive_timestamp,
            "central_receive_timestamp": self.central_receive_timestamp,
        }


@dataclass
class GatewaySequenceState:
    """Tracks sequence numbers and duplicate attempts per gateway."""
    gateway_id: str
    last_sequence_number: int
    last_received_at_utc: str
    duplicate_count: int = 0
    dropped_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "last_sequence_number": self.last_sequence_number,
            "last_received_at_utc": self.last_received_at_utc,
            "duplicate_count": self.duplicate_count,
            "dropped_count": self.dropped_count,
        }


@dataclass
class GatewayHealth:
    """Observability summary of a gateway's connectivity and buffer health."""
    gateway_id: str
    tenant_id: str
    site_id: str
    status: str = GatewayHealthStatus.UNKNOWN.value
    last_heartbeat_at_utc: Optional[str] = None
    seconds_since_last_heartbeat: Optional[float] = None
    queue_depth: int = 0
    collector_status: str = "UNKNOWN"
    software_version: str = "1.0.0"
    certificate_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "status": self.status,
            "last_heartbeat_at_utc": self.last_heartbeat_at_utc,
            "seconds_since_last_heartbeat": self.seconds_since_last_heartbeat,
            "queue_depth": self.queue_depth,
            "collector_status": self.collector_status,
            "software_version": self.software_version,
            "certificate_valid": self.certificate_valid,
        }


@dataclass
class GatewayCapabilityProfile:
    """Supported diagnostic capabilities and collection protocols."""
    supported_protocols: List[str] = field(default_factory=lambda: ["ROUTEROS_API", "SNMP_V2C", "SSH_RO"])
    max_batch_size: int = 100
    max_message_bytes: int = 524288  # 512 KB
    supports_offline_buffering: bool = True
    max_buffer_capacity: int = 5000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supported_protocols": list(self.supported_protocols),
            "max_batch_size": self.max_batch_size,
            "max_message_bytes": self.max_message_bytes,
            "supports_offline_buffering": self.supports_offline_buffering,
            "max_buffer_capacity": self.max_buffer_capacity,
        }
