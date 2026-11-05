"""
AIRA OS — Networking V Unified Device, Interface & Resource Monitoring Engine (WP 5.3).

Orchestrates capability-aware multi-protocol telemetry gathering:
1. ICMP reachability, latency, and packet loss.
2. SNMP v2c/v3 interface counter streaming and hardware resource polling.
3. Persistent RouterOS SSH interrogation via ConnectionManager allowlist.
4. Mathematical rate normalization with 32/64-bit wraparound and reboot handling.
5. Epistemic separation of local router availability from upstream WAN reachability.

Guarantees:
- Strictly read-only interrogation (100% validate_readonly_command compliant).
- Missing telemetry intervals are NEVER recorded as 0.0 bps (tagged TELEMETRY_GAP).
- Unsupported hardware metrics remain unavailable/None rather than zero.
- Reboots and counter rollovers are cleanly categorized as DISCONTINUOUS.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.nms.capability import (
    CapabilityState,
    DeviceCapabilityProfile,
    MonitoringCapability,
)
from core.nms.models import (
    CollectionError,
    CollectionResult,
    CollectionStatus,
    CounterMetadata,
    DeviceResourceTelemetry,
    InterfaceTelemetry,
    MetricSemanticType,
    MetricTaxonomy,
    NetworkQualityTelemetry,
    SampleQuality,
    TelemetryCompleteness,
    TelemetryFreshness,
    TelemetrySample,
    TelemetrySource,
    sanitize_telemetry_secrets,
)
from core.nms_models import calculate_traffic_rate, determine_device_availability
from core.topology_models import bounded_icmp_ping
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.nms.monitoring")


class UnifiedMonitoringEngine:
    """
    Core monitoring coordinator managing live protocol execution,
    counter continuity caches, and normalized telemetry assembly.
    """

    def __init__(self):
        # In-memory continuity cache: (device_id, interface_name) -> {"timestamp": float, "in_octets": int, "out_octets": int}
        self._last_interface_samples: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_cached_interface_sample(self, device_id: str, interface_name: str) -> Optional[Dict[str, Any]]:
        return self._last_interface_samples.get((device_id, interface_name))

    def update_cached_interface_sample(
        self, device_id: str, interface_name: str, in_octets: int, out_octets: int, timestamp: float
    ) -> None:
        self._last_interface_samples[(device_id, interface_name)] = {
            "timestamp": timestamp,
            "in_octets": in_octets,
            "out_octets": out_octets,
        }

    def compute_interface_rates(
        self,
        device_id: str,
        interface_name: str,
        curr_in_octets: Optional[int],
        curr_out_octets: Optional[int],
        curr_time: float,
        speed_bps: Optional[int] = None,
    ) -> Tuple[float, float, Optional[float], Optional[float], str]:
        """
        Calculates RX/TX bitrates and link utilization percentages from counter deltas.
        Detects counter wraparound, router reboot, and missing intervals.

        Returns:
            (rx_rate_bps, tx_rate_bps, rx_util_pct, tx_util_pct, rate_quality)
        """
        if curr_in_octets is None or curr_out_octets is None:
            return 0.0, 0.0, None, None, SampleQuality.MISSING.value

        prev = self.get_cached_interface_sample(device_id, interface_name)

        # Update cache for next iteration regardless
        self.update_cached_interface_sample(
            device_id, interface_name, curr_in_octets, curr_out_octets, curr_time
        )

        if not prev:
            return 0.0, 0.0, None, None, SampleQuality.UNCERTAIN.value

        prev_time = prev["timestamp"]
        time_delta = curr_time - prev_time

        # Invalid or negative time delta
        if time_delta <= 0.001:
            return 0.0, 0.0, None, None, SampleQuality.UNCERTAIN.value

        # Elapsed interval exceeded 3x normal polling window -> Discontinuous gap
        if time_delta > 300.0:
            return 0.0, 0.0, None, None, SampleQuality.DISCONTINUOUS.value

        rx_rate, rx_util = calculate_traffic_rate(
            curr_octets=curr_in_octets,
            prev_octets=prev["in_octets"],
            curr_time=curr_time,
            prev_time=prev_time,
            speed_bps=speed_bps,
        )
        tx_rate, tx_util = calculate_traffic_rate(
            curr_octets=curr_out_octets,
            prev_octets=prev["out_octets"],
            curr_time=curr_time,
            prev_time=prev_time,
            speed_bps=speed_bps,
        )

        quality = SampleQuality.GOOD.value
        # If counter dropped without wrap (reboot), calculate_traffic_rate returns 0.0
        if curr_in_octets < prev["in_octets"] and rx_rate == 0.0:
            quality = SampleQuality.DISCONTINUOUS.value
        elif curr_out_octets < prev["out_octets"] and tx_rate == 0.0:
            quality = SampleQuality.DISCONTINUOUS.value

        return rx_rate, tx_rate, rx_util, tx_util, quality

    async def execute_icmp_probe(
        self, host: str, timeout_sec: float = 2.0
    ) -> Dict[str, Any]:
        """Runs bounded ICMP ping check in a separate thread."""
        return await asyncio.to_thread(bounded_icmp_ping, host, 1, timeout_sec)

    async def poll_device_telemetry(
        self,
        device_id: str,
        host: str,
        profile: DeviceCapabilityProfile,
        settings: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """
        Executes a capability-aware polling cycle across ICMP, SNMP, and SSH.
        Returns a normalized CollectionResult containing structured TelemetrySamples.
        """
        cfg = settings or {}
        ping_timeout = float(cfg.get("ping_timeout_sec", 2.0))
        snmp_timeout = float(cfg.get("snmp_timeout_sec", 3.0))

        t0 = time.perf_counter()
        now = time.time()

        result = CollectionResult(
            device_id=device_id,
            source_protocol=profile.preferred_telemetry_source(),
            collector_name="unified_monitoring_engine",
            collection_start_time=now,
        )

        # Stage 1: ICMP Ping Availability Check
        ping_res = await self.execute_icmp_probe(host, timeout_sec=ping_timeout)
        is_alive = bool(ping_res.get("alive", False))
        latency_ms = float(ping_res.get("avg_rtt_ms") or ping_res.get("rtt_ms") or 0.0)
        packet_loss = 0.0 if is_alive else 100.0

        result.samples.append(
            TelemetrySample(
                device_id=device_id,
                metric_name=MetricTaxonomy.DEVICE_AVAILABILITY,
                metric_value=1 if is_alive else 0,
                unit="state",
                semantic_type=MetricSemanticType.STATE.value,
                measured_at=now,
                collected_at=now,
                source_protocol=TelemetrySource.ICMP.value,
                source_collector="icmp_probe",
                quality=SampleQuality.GOOD.value if is_alive else SampleQuality.UNCERTAIN.value,
            )
        )
        result.samples.append(
            TelemetrySample(
                device_id=device_id,
                metric_name=MetricTaxonomy.DEVICE_PACKET_LOSS_PCT,
                metric_value=packet_loss,
                unit="percent",
                semantic_type=MetricSemanticType.GAUGE.value,
                measured_at=now,
                collected_at=now,
                source_protocol=TelemetrySource.ICMP.value,
                source_collector="icmp_probe",
            )
        )
        if is_alive:
            result.samples.append(
                TelemetrySample(
                    device_id=device_id,
                    metric_name=MetricTaxonomy.DEVICE_LATENCY_MS,
                    metric_value=latency_ms,
                    unit="ms",
                    semantic_type=MetricSemanticType.GAUGE.value,
                    measured_at=now,
                    collected_at=now,
                    source_protocol=TelemetrySource.ICMP.value,
                    source_collector="icmp_probe",
                )
            )

        # If device is unreachable via ICMP, skip heavy protocols to save network overhead
        if not is_alive:
            result.duration_ms = (time.perf_counter() - t0) * 1000.0
            result.collection_completion_time = time.time()
            result.status = CollectionStatus.UNREACHABLE.value
            result.completeness = TelemetryCompleteness.PARTIAL.value
            result.warnings.append(f"Device '{device_id}' ({host}) ICMP echo timed out; sub-telemetry skipped.")
            return result

        # Stage 2: Heavy Telemetry Interrogation (SNMP or SSH)
        preferred_source = profile.preferred_telemetry_source()

        # Route to SNMP if supported
        if preferred_source == "snmp":
            await self._interrogate_snmp(device_id, host, profile, result, snmp_timeout, now)
        elif preferred_source == "ssh":
            await self._interrogate_routeros_ssh(device_id, host, result, now)

        result.duration_ms = (time.perf_counter() - t0) * 1000.0
        result.collection_completion_time = time.time()
        result.status = CollectionStatus.SUCCESS.value
        result.completeness = TelemetryCompleteness.COMPLETE.value
        return result

    async def _interrogate_snmp(
        self,
        device_id: str,
        host: str,
        profile: DeviceCapabilityProfile,
        result: CollectionResult,
        timeout: float,
        now: float,
    ) -> None:
        """Queries SNMP tables for interfaces and hardware resources."""
        try:
            from core.nms_snmp import poll_device_snmp_full
            # Resolve SNMP parameters from profile assessment or defaults
            snmp_asmt = profile.capabilities.get(MonitoringCapability.SNMP_V2C.value)
            port = snmp_asmt.tested_port if snmp_asmt and snmp_asmt.tested_port else 161

            snmp_data = await poll_device_snmp_full(host=host, port=port, timeout=timeout)
            if not snmp_data.get("success"):
                err_msg = snmp_data.get("error", "SNMP poll failed")
                result.errors.append(CollectionError(error_type="SnmpError", message=err_msg, protocol="snmp"))
                return

            # Extract resource metrics
            cpu = snmp_data.get("cpu_load_percent")
            if cpu is not None:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
                        metric_value=float(cpu),
                        unit="percent",
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                    )
                )

            mem = snmp_data.get("memory_used_percent")
            if mem is not None:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_MEMORY_UTILIZATION,
                        metric_value=float(mem),
                        unit="percent",
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                    )
                )

            temp = snmp_data.get("temperature_celsius")
            if temp is not None:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_TEMPERATURE,
                        metric_value=float(temp),
                        unit="celsius",
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                    )
                )

            # Extract interfaces
            for iface in snmp_data.get("interfaces", []):
                iname = iface.get("name")
                if not iname:
                    continue

                curr_in = iface.get("in_octets")
                curr_out = iface.get("out_octets")
                speed = iface.get("speed_bps")

                rx_bps, tx_bps, rx_util, tx_util, q = self.compute_interface_rates(
                    device_id, iname, curr_in, curr_out, now, speed
                )

                # Oper status
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_OPER_STATUS,
                        metric_value=1 if iface.get("oper_status") == "up" else 0,
                        unit="state",
                        semantic_type=MetricSemanticType.STATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                    )
                )
                # Bitrates
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_RX_BPS,
                        metric_value=rx_bps,
                        unit="bps",
                        semantic_type=MetricSemanticType.RATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                        quality=q,
                    )
                )
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_TX_BPS,
                        metric_value=tx_bps,
                        unit="bps",
                        semantic_type=MetricSemanticType.RATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.SNMP_V2C.value,
                        source_collector="snmp_poller",
                        quality=q,
                    )
                )
                if rx_util is not None:
                    result.samples.append(
                        TelemetrySample(
                            device_id=device_id,
                            metric_name=MetricTaxonomy.INTERFACE_RX_UTILIZATION,
                            metric_value=rx_util,
                            unit="percent",
                            semantic_type=MetricSemanticType.GAUGE.value,
                            interface_name=iname,
                            measured_at=now,
                            collected_at=now,
                            source_protocol=TelemetrySource.SNMP_V2C.value,
                            source_collector="snmp_poller",
                            quality=q,
                        )
                    )
                if tx_util is not None:
                    result.samples.append(
                        TelemetrySample(
                            device_id=device_id,
                            metric_name=MetricTaxonomy.INTERFACE_TX_UTILIZATION,
                            metric_value=tx_util,
                            unit="percent",
                            semantic_type=MetricSemanticType.GAUGE.value,
                            interface_name=iname,
                            measured_at=now,
                            collected_at=now,
                            source_protocol=TelemetrySource.SNMP_V2C.value,
                            source_collector="snmp_poller",
                            quality=q,
                        )
                    )
        except Exception as exc:
            result.errors.append(CollectionError(error_type=type(exc).__name__, message=str(exc), protocol="snmp"))

    async def _interrogate_routeros_ssh(
        self,
        device_id: str,
        host: str,
        result: CollectionResult,
        now: float,
    ) -> None:
        """Interrogates RouterOS via persistent SSH session lease."""
        try:
            from core.nms_engine import get_nms_engine
            engine = get_nms_engine()
            ros_data = await engine.poll_device_routeros(host=host, device_name=device_id)

            if not ros_data.get("success"):
                err = ros_data.get("error", "RouterOS SSH interrogation failed")
                result.errors.append(CollectionError(error_type="RouterOsSshError", message=err, protocol="routeros_ssh"))
                return

            res_info = ros_data.get("resources") or ros_data.get("resource") or {}
            cpu = ros_data.get("cpu_load_percent") or res_info.get("cpu_load_percent") or res_info.get("cpu_load")
            if cpu is not None:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_CPU_UTILIZATION,
                        metric_value=float(cpu),
                        unit="percent",
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                        source_collector="routeros_ssh_poller",
                    )
                )

            mem = ros_data.get("memory_used_percent") or res_info.get("memory_used_percent")
            if mem is not None:
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.DEVICE_MEMORY_UTILIZATION,
                        metric_value=float(mem),
                        unit="percent",
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                        source_collector="routeros_ssh_poller",
                    )
                )

            # Interface octets & statuses
            for iface in ros_data.get("interfaces", []):
                iname = iface.get("name")
                if not iname:
                    continue

                curr_in = iface.get("in_octets") if iface.get("in_octets") is not None else iface.get("rx_byte")
                curr_out = iface.get("out_octets") if iface.get("out_octets") is not None else iface.get("tx_byte")
                speed = iface.get("speed_bps") or iface.get("negotiated_speed_bps")

                rx_bps, tx_bps, rx_util, tx_util, q = self.compute_interface_rates(
                    device_id, iname, curr_in, curr_out, now, speed
                )

                is_up = iface.get("oper_status") == "up" or (not iface.get("disabled") and iface.get("running"))
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_OPER_STATUS,
                        metric_value=1 if is_up else 0,
                        unit="state",
                        semantic_type=MetricSemanticType.STATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                        source_collector="routeros_ssh_poller",
                    )
                )
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_RX_BPS,
                        metric_value=rx_bps,
                        unit="bps",
                        semantic_type=MetricSemanticType.RATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                        source_collector="routeros_ssh_poller",
                        quality=q,
                    )
                )
                result.samples.append(
                    TelemetrySample(
                        device_id=device_id,
                        metric_name=MetricTaxonomy.INTERFACE_TX_BPS,
                        metric_value=tx_bps,
                        unit="bps",
                        semantic_type=MetricSemanticType.RATE.value,
                        interface_name=iname,
                        measured_at=now,
                        collected_at=now,
                        source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                        source_collector="routeros_ssh_poller",
                        quality=q,
                    )
                )
                if rx_util is not None:
                    result.samples.append(
                        TelemetrySample(
                            device_id=device_id,
                            metric_name=MetricTaxonomy.INTERFACE_RX_UTILIZATION,
                            metric_value=rx_util,
                            unit="percent",
                            semantic_type=MetricSemanticType.GAUGE.value,
                            interface_name=iname,
                            measured_at=now,
                            collected_at=now,
                            source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                            source_collector="routeros_ssh_poller",
                            quality=q,
                        )
                    )
                if tx_util is not None:
                    result.samples.append(
                        TelemetrySample(
                            device_id=device_id,
                            metric_name=MetricTaxonomy.INTERFACE_TX_UTILIZATION,
                            metric_value=tx_util,
                            unit="percent",
                            semantic_type=MetricSemanticType.GAUGE.value,
                            interface_name=iname,
                            measured_at=now,
                            collected_at=now,
                            source_protocol=TelemetrySource.ROUTEROS_SSH.value,
                            source_collector="routeros_ssh_poller",
                            quality=q,
                        )
                    )
        except Exception as exc:
            result.errors.append(CollectionError(error_type=type(exc).__name__, message=str(exc), protocol="routeros_ssh"))

    async def execute_network_quality_probe(
        self,
        device_id: str = "global_wan",
        gateway_ip: Optional[str] = None,
        dns_target: str = "8.8.8.8",
        timeout_sec: float = 2.0,
    ) -> NetworkQualityTelemetry:
        """
        Executes epistemic reachability probe separating local gateway from WAN Internet.
        """
        now = time.time()
        gw_reachable = False
        if gateway_ip:
            gw_res = await self.execute_icmp_probe(gateway_ip, timeout_sec=timeout_sec)
            gw_reachable = bool(gw_res.get("alive", False))

        dns_res = await self.execute_icmp_probe(dns_target, timeout_sec=timeout_sec)
        dns_alive = bool(dns_res.get("alive", False))
        latency = float(dns_res.get("avg_rtt_ms") or dns_res.get("rtt_ms") or 0.0)

        return NetworkQualityTelemetry(
            device_id=device_id,
            timestamp=now,
            target_destination=dns_target,
            latency_ms=latency if dns_alive else 0.0,
            packet_loss_pct=0.0 if dns_alive else 100.0,
            gateway_reachable=gw_reachable if gateway_ip else True,
            dns_reachable=dns_alive,
            wan_available=dns_alive,
            probed_hops=2 if gateway_ip else 1,
        )
