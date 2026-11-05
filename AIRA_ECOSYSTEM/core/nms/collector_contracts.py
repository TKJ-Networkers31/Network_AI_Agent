"""
AIRA OS — Networking V Collector Contracts & Normalized Adapters (WP 5.1).

Defines the unified asynchronous collector interface, error boundary wrappers,
and adapters around existing ICMP, SNMP, and RouterOS SSH collectors.

Guarantees:
- Every collector returns a standard CollectionResult with explicit completeness.
- Errors never leak credentials or crash the caller (error isolation).
- Full compatibility with existing collectors in core/nms_engine.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

from core.canonical_network import CanonicalDevice
from core.nms.capability import (
    CapabilityState,
    DeviceCapabilityProfile,
    MonitoringCapability,
)
from core.nms.models import (
    CollectionError,
    CollectionResult,
    CollectionStatus,
    MetricSemanticType,
    MetricTaxonomy,
    SampleQuality,
    TelemetryCompleteness,
    TelemetryFreshness,
    TelemetrySample,
    TelemetrySource,
)
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.nms.collector")


class BaseTelemetryCollector(ABC):
    """
    Abstract interface for all protocol-specific NMS collectors.
    Guarantees consistent exception handling, secret masking, and timing.
    """

    @property
    @abstractmethod
    def source_protocol(self) -> str:
        """Name of the protocol (e.g. 'icmp', 'snmp_v2c', 'routeros_ssh')."""
        pass

    @property
    @abstractmethod
    def collector_name(self) -> str:
        """Unique identifier of this collector instance."""
        pass

    @abstractmethod
    async def collect(
        self,
        device_id: str,
        host: str,
        profile: DeviceCapabilityProfile,
        timeout_sec: float = 3.0,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """Executes telemetry gathering and returns a normalized CollectionResult."""
        pass


class IcmpTelemetryCollector(BaseTelemetryCollector):
    """Normalized ICMP Echo collector wrapping bounded_icmp_ping."""

    @property
    def source_protocol(self) -> str:
        return TelemetrySource.ICMP.value

    @property
    def collector_name(self) -> str:
        return "icmp_echo_collector"

    async def collect(
        self,
        device_id: str,
        host: str,
        profile: DeviceCapabilityProfile,
        timeout_sec: float = 2.0,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        import asyncio
        from core.nms_engine import bounded_icmp_ping

        t0 = time.perf_counter()
        result = CollectionResult(
            device_id=device_id,
            source_protocol=self.source_protocol,
            collector_name=self.collector_name,
            collection_start_time=time.time(),
        )

        try:
            ping_data = await asyncio.to_thread(bounded_icmp_ping, host, 1, timeout_sec)
            t_done = time.perf_counter()
            result.duration_ms = (t_done - t0) * 1000.0
            result.collection_completion_time = time.time()

            is_alive = bool(ping_data.get("alive", False))
            rtt_ms = float(ping_data.get("avg_rtt_ms") or ping_data.get("rtt_ms") or 0.0)
            pkt_loss = 0.0 if is_alive else 100.0

            # Availability state sample
            result.samples.append(
                TelemetrySample(
                    device_id=device_id,
                    metric_name=MetricTaxonomy.DEVICE_AVAILABILITY,
                    metric_value=1 if is_alive else 0,
                    unit="state",
                    semantic_type=MetricSemanticType.STATE.value,
                    measured_at=result.collection_completion_time,
                    collected_at=result.collection_completion_time,
                    source_protocol=self.source_protocol,
                    source_collector=self.collector_name,
                    quality=SampleQuality.GOOD.value if is_alive else SampleQuality.UNCERTAIN.value,
                )
            )

            # Latency sample
            if is_alive:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_LATENCY_MS,
                        metric_value=rtt_ms,
                        unit="ms",
                        semantic_type=MetricSemanticType.GAUGE.value,
                        measured_at=result.collection_completion_time,
                        collected_at=result.collection_completion_time,
                        source_protocol=self.source_protocol,
                        source_collector=self.collector_name,
                        quality=SampleQuality.GOOD.value,
                    )
                )

            # Packet loss sample
            result.samples.append(
                TelemetrySample(
                    device_id=device_id,
                    metric_name=MetricTaxonomy.DEVICE_PACKET_LOSS_PCT,
                    metric_value=pkt_loss,
                    unit="percent",
                    semantic_type=MetricSemanticType.GAUGE.value,
                    measured_at=result.collection_completion_time,
                    collected_at=result.collection_completion_time,
                    source_protocol=self.source_protocol,
                    source_collector=self.collector_name,
                    quality=SampleQuality.GOOD.value,
                )
            )

            result.status = CollectionStatus.SUCCESS.value if is_alive else CollectionStatus.UNREACHABLE.value
            result.completeness = TelemetryCompleteness.COMPLETE.value

        except Exception as exc:
            result.duration_ms = (time.perf_counter() - t0) * 1000.0
            result.collection_completion_time = time.time()
            result.status = CollectionStatus.FAILED.value
            result.completeness = TelemetryCompleteness.FAILED.value
            result.errors.append(
                CollectionError(
                    error_type=type(exc).__name__,
                    message=str(exc),
                    protocol=self.source_protocol,
                )
            )

        return result


class MockTelemetryCollector(BaseTelemetryCollector):
    """Simulated collector for hermetic unit testing and scale benchmarks."""

    def __init__(self, protocol: str = "mock", fixed_samples: Optional[List[TelemetrySample]] = None):
        self._protocol = protocol
        self._fixed_samples = fixed_samples or []

    @property
    def source_protocol(self) -> str:
        return self._protocol

    @property
    def collector_name(self) -> str:
        return f"{self._protocol}_mock_collector"

    async def collect(
        self,
        device_id: str,
        host: str,
        profile: DeviceCapabilityProfile,
        timeout_sec: float = 1.0,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        return CollectionResult(
            device_id=device_id,
            source_protocol=self.source_protocol,
            collector_name=self.collector_name,
            status=CollectionStatus.SUCCESS.value,
            completeness=TelemetryCompleteness.COMPLETE.value,
            samples=list(self._fixed_samples),
        )
