"""
AIRA OS — Networking V Canonical Telemetry Data Models & Taxonomy (WP 5.1).

Defines vendor-neutral, protocol-agnostic telemetry data structures,
metric naming conventions, semantic types, sample quality tags,
and structured collection containers shared across all monitoring subsystems.

Guarantees:
- Strict separation of measurement timestamp from ingestion timestamp.
- Explicit sample quality (GOOD, DISCONTINUOUS, UNCERTAIN, MISSING, ERROR).
- Missing samples are NEVER converted into valid zero measurements.
- Support for partial telemetry collections without data loss.
- Automatic secret masking across all serializations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

from core.nms_models import (
    NMS_STATUS_VALUES,
    NmsSchedulerState,
    calculate_traffic_rate,
    determine_device_availability,
    is_check_stale,
    parse_uptime_to_seconds,
    resolve_device_display_name,
)
from mcp_servers.network.security import mask_sensitive_data


_SECRET_RE = re.compile(
    r'(?i)\b(community\s+string|community|password|passwd|secret|private_key|token|api_key|priv_key|auth_key|key)[=:\s]+([^\s,;]+)'
)


def sanitize_telemetry_secrets(obj: Any) -> Any:
    """Recursively sanitizes dictionary keys, lists, and inline strings containing secrets."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return _SECRET_RE.sub(r'\1=***MASKED***', obj)
    elif isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("password", "secret", "private_key", "token", "community", "auth_key", "priv_key")):
                masked[k] = "***MASKED***" if v else v
            else:
                masked[k] = sanitize_telemetry_secrets(v)
        return masked
    elif isinstance(obj, list):
        return [sanitize_telemetry_secrets(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Telemetry Enumerations & Semantic Types
# ---------------------------------------------------------------------------

class TelemetrySource(str, Enum):
    """Protocol or subsystem that gathered the telemetry."""
    ICMP = "icmp"
    SNMP_V2C = "snmp_v2c"
    SNMP_V3 = "snmp_v3"
    ROUTEROS_SSH = "routeros_ssh"
    ROUTEROS_API = "routeros_api"
    LINUX_SSH = "linux_ssh"
    DERIVED = "derived"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class MetricSemanticType(str, Enum):
    """Semantic measurement behavior."""
    GAUGE = "gauge"          # Instantaneous value (e.g. CPU %, temperature, queue depth)
    COUNTER = "counter"      # Monotonically increasing counter (e.g. cumulative octets, packets)
    RATE = "rate"            # Calculated derivative per second (e.g. bps, pps)
    STATE = "state"          # Discrete operational/administrative status (e.g. UP, DOWN)
    HISTOGRAM = "histogram"  # Aggregated distribution / percentiles


class SampleQuality(str, Enum):
    """Quality and epistemic confidence of an individual sample."""
    GOOD = "GOOD"                            # Verified valid reading
    SUSPECT = "SUSPECT"                      # Extreme value pending verification
    DISCONTINUOUS = "DISCONTINUOUS"          # Counter wrapped or rebooted; rate calculation suppressed
    UNCERTAIN = "UNCERTAIN"                  # Transient response / high jitter
    MISSING = "MISSING"                      # Sample interval elapsed with no data received
    ERROR = "ERROR"                          # Protocol or parsing error during collection


class TelemetryFreshness(str, Enum):
    """Temporal freshness state."""
    FRESH = "FRESH"      # Collected within normal sampling window (< 2.5x interval)
    STALE = "STALE"      # Exceeded freshness threshold; retained for historical context
    EXPIRED = "EXPIRED"  # Older than active operational window
    UNKNOWN = "UNKNOWN"  # Freshness cannot be determined


class CollectionStatus(str, Enum):
    """Overall status of a collection job."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    EMPTY_VALID = "EMPTY_VALID"
    FAILED = "FAILED"
    UNREACHABLE = "UNREACHABLE"
    AUTH_FAILED = "AUTH_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    SKIPPED_OVERRUN = "SKIPPED_OVERRUN"


class TelemetryCompleteness(str, Enum):
    """Completeness indicator for telemetry payload."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Metric Taxonomy Constants
# ---------------------------------------------------------------------------

class MetricTaxonomy:
    """Canonical metric naming conventions for AIRA OS NMS."""

    # Device Level
    DEVICE_AVAILABILITY = "aira.nms.device.availability"            # State (1=Up, 0=Down)
    DEVICE_LATENCY_MS = "aira.nms.device.latency_ms"                # Gauge (ms)
    DEVICE_PACKET_LOSS_PCT = "aira.nms.device.packet_loss_pct"      # Gauge (%)
    DEVICE_CPU_UTILIZATION = "aira.nms.device.cpu.utilization"      # Gauge (%)
    DEVICE_MEMORY_USED = "aira.nms.device.memory.used"              # Gauge (bytes)
    DEVICE_MEMORY_TOTAL = "aira.nms.device.memory.total"            # Gauge (bytes)
    DEVICE_MEMORY_UTILIZATION = "aira.nms.device.memory.utilization"# Gauge (%)
    DEVICE_STORAGE_USED = "aira.nms.device.storage.used"            # Gauge (bytes)
    DEVICE_STORAGE_TOTAL = "aira.nms.device.storage.total"          # Gauge (bytes)
    DEVICE_UPTIME_SECONDS = "aira.nms.device.uptime"                # Gauge (seconds)
    DEVICE_TEMPERATURE = "aira.nms.device.temperature"              # Gauge (celsius)

    # Interface Level
    INTERFACE_OPER_STATUS = "aira.nms.interface.oper_status"        # State (1=Up, 0=Down)
    INTERFACE_ADMIN_STATUS = "aira.nms.interface.admin_status"      # State (1=Up, 0=Down)
    INTERFACE_SPEED_BPS = "aira.nms.interface.speed_bps"            # Gauge (bps)
    INTERFACE_RX_OCTETS = "aira.nms.interface.rx.octets"            # Counter (bytes)
    INTERFACE_TX_OCTETS = "aira.nms.interface.tx.octets"            # Counter (bytes)
    INTERFACE_RX_BPS = "aira.nms.interface.rx.bps"                  # Rate (bps)
    INTERFACE_TX_BPS = "aira.nms.interface.tx.bps"                  # Rate (bps)
    INTERFACE_RX_UTILIZATION = "aira.nms.interface.rx.utilization"  # Gauge (%)
    INTERFACE_TX_UTILIZATION = "aira.nms.interface.tx.utilization"  # Gauge (%)
    INTERFACE_RX_PACKETS = "aira.nms.interface.rx.packets"          # Counter (packets)
    INTERFACE_TX_PACKETS = "aira.nms.interface.tx.packets"          # Counter (packets)
    INTERFACE_RX_ERRORS = "aira.nms.interface.rx.errors"            # Counter (errors)
    INTERFACE_TX_ERRORS = "aira.nms.interface.tx.errors"            # Counter (errors)
    INTERFACE_RX_DROPS = "aira.nms.interface.rx.drops"              # Counter (drops)
    INTERFACE_TX_DROPS = "aira.nms.interface.tx.drops"              # Counter (drops)

    # Network Quality Level
    NETWORK_GATEWAY_REACHABLE = "aira.nms.network.gateway_reachable"# State (1=Up, 0=Down)
    NETWORK_DNS_REACHABLE = "aira.nms.network.dns_reachable"        # State (1=Up, 0=Down)
    NETWORK_WAN_AVAILABILITY = "aira.nms.network.wan_availability"  # State (1=Up, 0=Down)
    NETWORK_JITTER_MS = "aira.nms.network.jitter_ms"                # Gauge (ms)


# ---------------------------------------------------------------------------
# Telemetry Sample & Batch Containers
# ---------------------------------------------------------------------------

@dataclass
class CounterMetadata:
    """Metadata for tracking counter discontinuities and rates."""
    bit_width: int = 64                  # 32 or 64 bit
    last_reset_time: Optional[float] = None
    discontinuity_detected: bool = False
    wrap_detected: bool = False
    reboot_detected: bool = False
    raw_delta: Optional[int] = None


@dataclass
class TelemetrySample:
    """
    Atomic normalized telemetry sample point.
    Separates measured observation time from collection/ingestion time.
    """
    device_id: str
    metric_name: str
    metric_value: Union[float, int, str, bool]
    unit: str
    semantic_type: str = MetricSemanticType.GAUGE.value
    measured_at: float = field(default_factory=time.time)
    collected_at: float = field(default_factory=time.time)
    source_protocol: str = TelemetrySource.ICMP.value
    source_collector: str = "default_collector"
    interface_id: Optional[str] = None
    interface_name: Optional[str] = None
    sample_id: str = field(default_factory=lambda: f"smp_{uuid.uuid4().hex[:10]}")
    quality: str = SampleQuality.GOOD.value
    freshness: str = TelemetryFreshness.FRESH.value
    counter_meta: Optional[CounterMetadata] = None
    dimensions: Dict[str, str] = field(default_factory=dict)
    error_detail: Optional[str] = None

    def is_valid(self) -> bool:
        return self.quality in (SampleQuality.GOOD.value, SampleQuality.SUSPECT.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "semantic_type": self.semantic_type,
            "measured_at": self.measured_at,
            "collected_at": self.collected_at,
            "source_protocol": self.source_protocol,
            "source_collector": self.source_collector,
            "interface_id": self.interface_id,
            "interface_name": self.interface_name,
            "sample_id": self.sample_id,
            "quality": self.quality,
            "freshness": self.freshness,
            "dimensions": self.dimensions,
            "error_detail": sanitize_telemetry_secrets(self.error_detail) if self.error_detail else None,
        }


@dataclass
class CollectionError:
    """Structured collection failure description."""
    error_type: str
    message: str
    protocol: str
    timestamp: float = field(default_factory=time.time)
    recoverable: bool = True
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": sanitize_telemetry_secrets(self.message),
            "protocol": self.protocol,
            "timestamp": self.timestamp,
            "recoverable": self.recoverable,
            "context": sanitize_telemetry_secrets(self.context),
        }


@dataclass
class CollectionResult:
    """
    Normalized result container emitted by any telemetry collector.
    Guarantees consistent reporting across ICMP, SNMP, SSH, and API collectors.
    """
    device_id: str
    source_protocol: str
    collector_name: str
    status: str = CollectionStatus.SUCCESS.value
    completeness: str = TelemetryCompleteness.COMPLETE.value
    collection_start_time: float = field(default_factory=time.time)
    collection_completion_time: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    samples: List[TelemetrySample] = field(default_factory=list)
    errors: List[CollectionError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    result_id: str = field(default_factory=lambda: f"col_{uuid.uuid4().hex[:10]}")

    @property
    def successful_metric_count(self) -> int:
        return sum(1 for s in self.samples if s.is_valid())

    @property
    def failed_metric_count(self) -> int:
        return sum(1 for s in self.samples if not s.is_valid()) + len(self.errors)

    def mask_secrets(self) -> None:
        """Sanitizes any accidentally logged secrets in error messages and warnings."""
        for err in self.errors:
            err.message = sanitize_telemetry_secrets(err.message)
        self.warnings = [sanitize_telemetry_secrets(w) for w in self.warnings]

    def to_dict(self) -> Dict[str, Any]:
        self.mask_secrets()
        return {
            "result_id": self.result_id,
            "device_id": self.device_id,
            "source_protocol": self.source_protocol,
            "collector_name": self.collector_name,
            "status": self.status,
            "completeness": self.completeness,
            "collection_start_time": self.collection_start_time,
            "collection_completion_time": self.collection_completion_time,
            "duration_ms": round(self.duration_ms, 2),
            "successful_metric_count": self.successful_metric_count,
            "failed_metric_count": self.failed_metric_count,
            "samples": [s.to_dict() for s in self.samples],
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [sanitize_telemetry_secrets(w) for w in self.warnings],
        }


# ---------------------------------------------------------------------------
# Specialized Domain Telemetry Payloads
# ---------------------------------------------------------------------------

@dataclass
class InterfaceTelemetry:
    """Normalized operational telemetry for a single network interface."""
    device_id: str
    interface_name: str
    timestamp: float = field(default_factory=time.time)
    oper_status: str = "unknown"
    admin_status: str = "unknown"
    speed_bps: int = 0
    in_octets: int = 0
    out_octets: int = 0
    in_packets: int = 0
    out_packets: int = 0
    in_errors: int = 0
    out_errors: int = 0
    in_drops: int = 0
    out_drops: int = 0
    rx_rate_bps: float = 0.0
    tx_rate_bps: float = 0.0
    rx_utilization_pct: Optional[float] = None
    tx_utilization_pct: Optional[float] = None
    is_stale: bool = False
    rate_quality: str = SampleQuality.GOOD.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "interface_name": self.interface_name,
            "timestamp": self.timestamp,
            "oper_status": self.oper_status,
            "admin_status": self.admin_status,
            "speed_bps": self.speed_bps,
            "in_octets": self.in_octets,
            "out_octets": self.out_octets,
            "in_packets": self.in_packets,
            "out_packets": self.out_packets,
            "in_errors": self.in_errors,
            "out_errors": self.out_errors,
            "in_drops": self.in_drops,
            "out_drops": self.out_drops,
            "rx_rate_bps": round(self.rx_rate_bps, 2),
            "tx_rate_bps": round(self.tx_rate_bps, 2),
            "rx_utilization_pct": round(self.rx_utilization_pct, 2) if self.rx_utilization_pct is not None else None,
            "tx_utilization_pct": round(self.tx_utilization_pct, 2) if self.tx_utilization_pct is not None else None,
            "is_stale": self.is_stale,
            "rate_quality": self.rate_quality,
        }


@dataclass
class DeviceResourceTelemetry:
    """Normalized hardware resource telemetry for a network device."""
    device_id: str
    timestamp: float = field(default_factory=time.time)
    cpu_util_pct: Optional[float] = None
    memory_used_bytes: Optional[int] = None
    memory_total_bytes: Optional[int] = None
    memory_util_pct: Optional[float] = None
    storage_used_bytes: Optional[int] = None
    storage_total_bytes: Optional[int] = None
    uptime_seconds: Optional[int] = None
    temperature_celsius: Optional[float] = None
    latency_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    is_stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "cpu_util_pct": round(self.cpu_util_pct, 1) if self.cpu_util_pct is not None else None,
            "memory_used_bytes": self.memory_used_bytes,
            "memory_total_bytes": self.memory_total_bytes,
            "memory_util_pct": round(self.memory_util_pct, 1) if self.memory_util_pct is not None else None,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_total_bytes": self.storage_total_bytes,
            "uptime_seconds": self.uptime_seconds,
            "temperature_celsius": round(self.temperature_celsius, 1) if self.temperature_celsius is not None else None,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms is not None else None,
            "packet_loss_pct": round(self.packet_loss_pct, 1) if self.packet_loss_pct is not None else None,
            "is_stale": self.is_stale,
        }


@dataclass
class NetworkQualityTelemetry:
    """Normalized end-to-end network quality and reachability telemetry."""
    device_id: str
    timestamp: float = field(default_factory=time.time)
    target_destination: str = "8.8.8.8"
    latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    jitter_ms: Optional[float] = None
    gateway_reachable: bool = True
    dns_reachable: bool = True
    wan_available: bool = True
    probed_hops: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "target_destination": self.target_destination,
            "latency_ms": round(self.latency_ms, 2),
            "packet_loss_pct": round(self.packet_loss_pct, 1),
            "jitter_ms": round(self.jitter_ms, 2) if self.jitter_ms is not None else None,
            "gateway_reachable": self.gateway_reachable,
            "dns_reachable": self.dns_reachable,
            "wan_available": self.wan_available,
            "probed_hops": self.probed_hops,
        }


@dataclass
class TelemetryBatch:
    """Batch of telemetry samples intended for batched SQLite ingestion."""
    batch_id: str = field(default_factory=lambda: f"tb_{uuid.uuid4().hex[:10]}")
    created_at: float = field(default_factory=time.time)
    samples: List[TelemetrySample] = field(default_factory=list)
    device_ids: List[str] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return len(self.samples)
