"""
AIRA OS — Multi-Device Route Collection Service (Networking IV / WP 4.6.1).

Integrates CanonicalDevice, UnifiedCommandExecutor (ConnectionManager + read-only allowlist),
and UnifiedRouteParser to collect, normalize, associate, and govern routing evidence across
multiple registered MikroTik RouterOS v6/v7 devices.

Guarantees:
- CanonicalDevice primary identity (never bare IP-only attribution)
- Identity collision detection across inventory and observed CLI identities
- Bounded concurrency (ThreadPoolExecutor with hard upper cap)
- Per-device single-flight exclusion lock (no overlapping SSH collection on the same router)
- Per-device timeout, cancellation token support (zero busy-loops), and transient backoff
- Strictly read-only RouterOS execution via UnifiedCommandExecutor
- Zero SQLite write transactions held during SSH or parsing
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from core.canonical_network import (
    CanonicalDevice,
    CanonicalNetworkRegistry,
    get_canonical_registry,
    parse_routeros_major_version,
)
from core.network_intelligence.command_execution import (
    CommandExecutionRequest,
    CommandExecutionResult,
    ExecutionStatus,
    UnifiedCommandExecutor,
)
from core.network_intelligence.models import EvidenceFreshness, EvidenceItem, EvidenceState
from core.routing.unified_route_parser import (
    NormalizedRoute,
    RouteParseReport,
    UnifiedRouteParser,
)
from core.topology_models import sanitize_untrusted_text
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.routing.collector")

PARSER_VERSION = "4.6.0"
DEFAULT_MAX_CONCURRENCY = 3
ABSOLUTE_MAX_CONCURRENCY = 8
DEFAULT_DEVICE_TIMEOUT_SEC = 15.0
MAX_CACHED_JOBS = 100


class RouteCollectionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNREACHABLE = "UNREACHABLE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    IN_PROGRESS = "IN_PROGRESS"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    SECURITY_REJECTED = "SECURITY_REJECTED"


class RouteCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    FAILED = "FAILED"
    UNREACHABLE = "UNREACHABLE"
    CANCELLED = "CANCELLED"


@dataclass
class RouteCollectionResult:
    """
    Structured per-device routing evidence collection result (WP 4.6.1).
    Preserves CanonicalDevice provenance, completeness, and parser diagnostics.
    """
    device_id: str
    device_identity: str
    platform: str = "mikrotik"
    router_os_version: str = ""
    ros_major_version: Optional[int] = None
    management_ip: str = ""
    status: str = RouteCollectionStatus.SUCCESS.value
    collected_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    source_command: str = "/ip route print detail"
    parser_version: str = PARSER_VERSION
    routes: List[NormalizedRoute] = field(default_factory=list)
    routing_tables: List[str] = field(default_factory=list)
    parser_report: Optional[RouteParseReport] = None
    completeness: str = RouteCompleteness.COMPLETE.value
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    evidence_id: str = field(default_factory=lambda: f"ev_routes_{uuid.uuid4().hex[:10]}")
    retries_used: int = 0
    duplicate_prevented: bool = False
    identity_collision: bool = False

    @property
    def route_count(self) -> int:
        return len(self.routes)

    @property
    def active_route_count(self) -> int:
        return sum(1 for r in self.routes if r.active and not r.disabled and not r.unreachable)

    def freshness(self, now: Optional[float] = None) -> str:
        ts = now if now is not None else time.time()
        age = max(0.0, ts - self.collected_at)
        if self.status in (
            RouteCollectionStatus.FAILED.value,
            RouteCollectionStatus.UNREACHABLE.value,
            RouteCollectionStatus.CANCELLED.value,
            RouteCollectionStatus.SECURITY_REJECTED.value,
        ):
            return EvidenceFreshness.UNKNOWN.value
        if age < 60.0:
            return EvidenceFreshness.FRESH.value
        if age < 300.0:
            return EvidenceFreshness.STALE.value
        return EvidenceFreshness.EXPIRED.value

    def to_evidence_item(self) -> EvidenceItem:
        """Converts this RouteCollectionResult into a standard Networking III EvidenceItem."""
        is_ok = self.status in (RouteCollectionStatus.SUCCESS.value, RouteCollectionStatus.PARTIAL.value)
        state = (
            EvidenceState.OBSERVED.value
            if self.status == RouteCollectionStatus.SUCCESS.value
            else EvidenceState.INVALID.value
            if self.status == RouteCollectionStatus.PARTIAL.value
            else EvidenceState.UNAVAILABLE.value
        )
        norm_val = {
            "count": len(self.routes),
            "active_count": self.active_route_count,
            "routing_tables": list(self.routing_tables),
            "parser_version": self.parser_version,
            "completeness": self.completeness,
            "routes": [
                {
                    **r.to_dict(),
                    "dst_address": r.dst_prefix,
                }
                for r in self.routes
            ],
            "has_default_route": any(r.is_default_route() for r in self.routes),
            "has_active_default_route": any(
                r.is_default_route() and r.active and not r.disabled and not r.unreachable
                for r in self.routes
            ),
        }
        limitations = "; ".join(self.errors + self.warnings)
        return EvidenceItem(
            evidence_id=self.evidence_id,
            device_identity=self.device_id,
            observation_type="routes",
            source_command=self.source_command,
            collection_timestamp=self.collected_at,
            collection_status="SUCCESS" if self.status == RouteCollectionStatus.SUCCESS.value else (
                "PARTIAL" if is_ok else "FAILED"
            ),
            normalized_value=norm_val if is_ok else None,
            raw_excerpt=mask_sensitive_data(
                f"Routes collected={len(self.routes)}, active={self.active_route_count}, "
                f"tables={','.join(self.routing_tables) or 'main'}"
            ),
            freshness=self.freshness(),
            is_derived=False,
            limitations=mask_sensitive_data(limitations)[:500],
            state=state,
        )

    def to_dict(
        self,
        include_routes: bool = True,
        routing_table: Optional[str] = None,
        protocol: Optional[str] = None,
        active_only: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        filtered = self.routes
        if routing_table:
            filtered = [r for r in filtered if (r.routing_table or "main") == routing_table]
        if protocol:
            p_low = protocol.strip().lower()
            filtered = [r for r in filtered if (r.protocol or "").lower() == p_low]
        if active_only:
            filtered = [r for r in filtered if r.active and not r.disabled and not r.unreachable]

        total_filtered = len(filtered)
        if offset > 0:
            filtered = filtered[offset:]
        if limit is not None and limit >= 0:
            filtered = filtered[:limit]

        pr_dict = None
        if self.parser_report is not None:
            pr_dict = {
                "status": self.parser_report.status,
                "total_parsed": self.parser_report.total_parsed,
                "active_count": self.parser_report.active_count,
                "elapsed_ms": round(self.parser_report.elapsed_ms, 2),
                "warning": self.parser_report.warning,
                "is_partial": self.parser_report.is_partial,
            }

        data: Dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "device_id": self.device_id,
            "device_identity": sanitize_untrusted_text(self.device_identity, 128),
            "platform": sanitize_untrusted_text(self.platform, 64),
            "router_os_version": sanitize_untrusted_text(self.router_os_version, 64),
            "ros_major_version": self.ros_major_version,
            "management_ip": self.management_ip,
            "status": self.status,
            "completeness": self.completeness,
            "freshness": self.freshness(),
            "collected_at": self.collected_at,
            "duration_ms": round(self.duration_ms, 2),
            "source_command": self.source_command,
            "parser_version": self.parser_version,
            "route_count": len(self.routes),
            "active_route_count": self.active_route_count,
            "filtered_route_count": total_filtered,
            "routing_tables": list(self.routing_tables),
            "parser_report": pr_dict,
            "retries_used": self.retries_used,
            "duplicate_prevented": self.duplicate_prevented,
            "identity_collision": self.identity_collision,
            "errors": [mask_sensitive_data(str(e)) for e in self.errors],
            "warnings": [mask_sensitive_data(str(w)) for w in self.warnings],
        }
        if include_routes:
            data["routes"] = [r.to_dict() for r in filtered]
        return data


@dataclass
class MultiDeviceRouteCollectionReport:
    """
    Aggregated fleet-level route collection report across multiple CanonicalDevice targets.
    """
    job_id: str
    started_at: float
    completed_at: float
    duration_ms: float
    max_concurrency: int
    status: str  # SUCCESS, PARTIAL, FAILED, CANCELLED
    results: Dict[str, RouteCollectionResult] = field(default_factory=dict)
    identity_collisions: List[str] = field(default_factory=list)
    unresolved_targets: List[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def total_devices(self) -> int:
        return len(self.results) + len(self.unresolved_targets)

    @property
    def successful_devices(self) -> int:
        return sum(1 for r in self.results.values() if r.status == RouteCollectionStatus.SUCCESS.value)

    @property
    def partial_devices(self) -> int:
        return sum(1 for r in self.results.values() if r.status == RouteCollectionStatus.PARTIAL.value)

    @property
    def failed_devices(self) -> int:
        return sum(
            1
            for r in self.results.values()
            if r.status in (
                RouteCollectionStatus.FAILED.value,
                RouteCollectionStatus.UNREACHABLE.value,
                RouteCollectionStatus.TIMEOUT.value,
                RouteCollectionStatus.SECURITY_REJECTED.value,
            )
        ) + len(self.unresolved_targets)

    @property
    def cancelled_devices(self) -> int:
        return sum(1 for r in self.results.values() if r.status == RouteCollectionStatus.CANCELLED.value)

    def to_dict(self, include_routes: bool = True, route_limit_per_device: Optional[int] = 500) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "max_concurrency": self.max_concurrency,
            "cancelled": self.cancelled,
            "summary": {
                "total_devices": self.total_devices,
                "resolved_devices": len(self.results),
                "successful_devices": self.successful_devices,
                "partial_devices": self.partial_devices,
                "failed_devices": self.failed_devices,
                "cancelled_devices": self.cancelled_devices,
                "unresolved_targets": list(self.unresolved_targets),
                "total_routes_collected": sum(r.route_count for r in self.results.values()),
                "total_active_routes": sum(r.active_route_count for r in self.results.values()),
            },
            "identity_collisions": list(self.identity_collisions),
            "unresolved_targets": list(self.unresolved_targets),
            "devices": {
                dev_id: res.to_dict(include_routes=include_routes, limit=route_limit_per_device)
                for dev_id, res in self.results.items()
            },
        }


def _deduplicate_routes(routes: List[NormalizedRoute]) -> Tuple[List[NormalizedRoute], int]:
    """
    Eliminates exact duplicate NormalizedRoute records within a single device collection
    while preserving legitimate ECMP and distinct VRF/distance entries.
    """
    seen: Set[Tuple[Any, ...]] = set()
    unique: List[NormalizedRoute] = []
    dup_count = 0
    for r in routes:
        key = (
            r.routing_table or "main",
            r.dst_prefix,
            r.gateway,
            tuple(r.gateways),
            r.interface_name or "",
            r.distance,
            r.metric,
            r.active,
            r.disabled,
            r.protocol,
        )
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        unique.append(r)
    return unique, dup_count


def _parse_identity_output(raw_text: str) -> str:
    """Extracts RouterOS identity name from `/system identity print` output."""
    if not raw_text:
        return ""
    m = re.search(r"name\s*[:=]\s*([^\r\n]+)", raw_text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"')
    return ""


def _parse_version_output(raw_text: str) -> str:
    """Extracts RouterOS version string from `/system resource print` output."""
    if not raw_text:
        return ""
    m = re.search(r"version\s*[:=]\s*([^\r\n]+)", raw_text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"')
    return ""


class MultiDeviceRouteCollector:
    """
    Authoritative multi-device route collection service (WP 4.6.1).
    Reuses CanonicalNetworkRegistry, UnifiedCommandExecutor, and UnifiedRouteParser.
    """

    def __init__(
        self,
        registry: Optional[CanonicalNetworkRegistry] = None,
        command_executor: Optional[UnifiedCommandExecutor] = None,
        parser: Optional[UnifiedRouteParser] = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ):
        self.registry = registry or get_canonical_registry()
        self.executor = command_executor or UnifiedCommandExecutor(registry=self.registry)
        self.parser = parser or UnifiedRouteParser()
        self.default_max_concurrency = max(1, min(max_concurrency, ABSOLUTE_MAX_CONCURRENCY))

        self._state_lock = threading.RLock()
        self._device_locks: Dict[str, threading.Lock] = {}
        self._in_progress_devices: Set[str] = set()
        self._latest_results: Dict[str, RouteCollectionResult] = {}
        self._seen_evidence_ids: Set[str] = set()
        self._active_jobs: Dict[str, Tuple[threading.Event, float, List[str]]] = {}
        self._recent_reports: Dict[str, Dict[str, Any]] = {}

    def _get_device_lock(self, device_id: str) -> threading.Lock:
        with self._state_lock:
            lock = self._device_locks.get(device_id)
            if lock is None:
                lock = threading.Lock()
                self._device_locks[device_id] = lock
            return lock

    # ------------------------------------------------------------------
    # Target Resolution & Identity Collision Checks
    # ------------------------------------------------------------------

    def resolve_targets(
        self,
        targets: Optional[Sequence[Union[str, CanonicalDevice]]] = None,
    ) -> Tuple[List[CanonicalDevice], List[str], List[str]]:
        """
        Resolves target queries or CanonicalDevice instances into deduplicated CanonicalDevices.
        Only authorized managed devices are selected when `targets` is None.
        Detects management IP or identity collisions across resolved targets.
        """
        resolved: List[CanonicalDevice] = []
        unresolved: List[str] = []
        collisions: List[str] = []
        seen_ids: Set[str] = set()

        if targets is None:
            all_devs = self.registry.list_devices(force_refresh=True)
            for dev in all_devs:
                if dev.is_managed and dev.device_id not in seen_ids:
                    seen_ids.add(dev.device_id)
                    resolved.append(dev)
        else:
            for item in targets:
                if isinstance(item, CanonicalDevice):
                    dev = item
                else:
                    q = str(item or "").strip()
                    if not q:
                        continue
                    dev = self.registry.resolve_device(q)
                    if dev is None or not dev.is_managed:
                        # Security requirement 13.2: only interact with authorized registered devices
                        unresolved.append(q)
                        continue
                if dev.device_id not in seen_ids:
                    seen_ids.add(dev.device_id)
                    resolved.append(dev)

        # Check for management IP collisions among distinct canonical devices
        ip_owners: Dict[str, List[CanonicalDevice]] = {}
        ident_owners: Dict[str, List[CanonicalDevice]] = {}
        for dev in resolved:
            if dev.management_ip:
                ip_owners.setdefault(dev.management_ip, []).append(dev)
            ident_key = (dev.observed_identity or dev.hostname or "").strip().lower()
            if ident_key:
                ident_owners.setdefault(ident_key, []).append(dev)

        for ip, owners in ip_owners.items():
            if len(owners) > 1:
                ids = ", ".join(d.device_id for d in owners)
                collisions.append(
                    f"Management IP collision detected: IP {ip} is shared by multiple canonical devices ({ids})."
                )
        for ident, owners in ident_owners.items():
            if len(owners) > 1:
                ids = ", ".join(d.device_id for d in owners)
                collisions.append(
                    f"Observed identity collision detected: identity '{ident}' is reported by multiple devices ({ids})."
                )

        return resolved, unresolved, collisions

    # ------------------------------------------------------------------
    # Single-Device Collection with Exclusion, Backoff & Cancellation
    # ------------------------------------------------------------------

    def collect_device_routes(
        self,
        device: Union[str, CanonicalDevice],
        timeout_sec: float = DEFAULT_DEVICE_TIMEOUT_SEC,
        max_retries: int = 1,
        backoff_base_sec: float = 0.25,
        cancel_event: Optional[threading.Event] = None,
        verify_identity: bool = False,
        reuse_fresh_sec: float = 0.0,
    ) -> RouteCollectionResult:
        """
        Collects and normalizes routing evidence for a single CanonicalDevice.
        Enforces per-device exclusion lock so concurrent invocations never execute
        overlapping SSH commands against the same router.
        """
        t0 = time.perf_counter()
        wall_start = time.time()

        # Resolve CanonicalDevice
        if isinstance(device, CanonicalDevice):
            dev = device
        else:
            resolved_dev = self.registry.resolve_device(str(device))
            if resolved_dev is None or not resolved_dev.is_managed:
                return RouteCollectionResult(
                    device_id=str(device),
                    device_identity=str(device),
                    status=RouteCollectionStatus.FAILED.value,
                    collected_at=wall_start,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    completeness=RouteCompleteness.FAILED.value,
                    errors=[
                        f"Device '{device}' is not an authorized managed device in CanonicalNetworkRegistry."
                    ],
                )
            dev = resolved_dev

        device_id = dev.device_id
        device_identity = dev.observed_identity or dev.display_name or dev.inventory_name or device_id
        platform = dev.platform or dev.device_type or "mikrotik"
        ros_version = dev.os_version or ""
        ros_major = dev.ros_major_version or parse_routeros_major_version(ros_version) or 7

        # Optional fresh-cache reuse (WP 4.6.6 optimization)
        if reuse_fresh_sec > 0.0:
            cached = self.get_latest_result(device_id)
            if (
                cached is not None
                and cached.status == RouteCollectionStatus.SUCCESS.value
                and (wall_start - cached.collected_at) <= reuse_fresh_sec
            ):
                return cached

        # Pre-flight cancellation check
        if cancel_event is not None and cancel_event.is_set():
            return RouteCollectionResult(
                device_id=device_id,
                device_identity=device_identity,
                platform=platform,
                router_os_version=ros_version,
                ros_major_version=ros_major,
                management_ip=dev.management_ip,
                status=RouteCollectionStatus.CANCELLED.value,
                collected_at=wall_start,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                completeness=RouteCompleteness.CANCELLED.value,
                errors=["Collection cancelled prior to execution."],
            )

        # Per-device non-overlapping exclusion lock
        dev_lock = self._get_device_lock(device_id)
        acquired = dev_lock.acquire(blocking=False)
        if not acquired:
            cached = self.get_latest_result(device_id)
            if cached is not None:
                return RouteCollectionResult(
                    device_id=device_id,
                    device_identity=device_identity,
                    platform=platform,
                    router_os_version=cached.router_os_version or ros_version,
                    ros_major_version=cached.ros_major_version or ros_major,
                    management_ip=dev.management_ip,
                    status=RouteCollectionStatus.SKIPPED_DUPLICATE.value,
                    collected_at=cached.collected_at,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    source_command=cached.source_command,
                    parser_version=cached.parser_version,
                    routes=list(cached.routes),
                    routing_tables=list(cached.routing_tables),
                    parser_report=cached.parser_report,
                    completeness=cached.completeness,
                    warnings=["Duplicate overlapping collection prevented; returning latest cached evidence."],
                    evidence_id=cached.evidence_id,
                    duplicate_prevented=True,
                )
            return RouteCollectionResult(
                device_id=device_id,
                device_identity=device_identity,
                platform=platform,
                router_os_version=ros_version,
                ros_major_version=ros_major,
                management_ip=dev.management_ip,
                status=RouteCollectionStatus.SKIPPED_DUPLICATE.value,
                collected_at=wall_start,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                completeness=RouteCompleteness.PARTIAL.value,
                warnings=["Overlapping collection for this device is already in progress; duplicate execution prevented."],
                duplicate_prevented=True,
            )

        with self._state_lock:
            self._in_progress_devices.add(device_id)

        try:
            errors: List[str] = []
            warnings: List[str] = []
            identity_collision = False
            target_ref = dev.inventory_name or dev.device_id

            # Optional lightweight identity & version verification when connected
            if verify_identity:
                if cancel_event is not None and cancel_event.is_set():
                    return self._cancelled_result(dev, ros_version, ros_major, wall_start, t0)
                id_req = CommandExecutionRequest(
                    device_id=target_ref,
                    command_str="/system identity print",
                    observation_domain="identity",
                    timeout=min(5.0, timeout_sec),
                )
                id_res = self.executor.execute(id_req)
                if id_res.is_success:
                    live_ident = _parse_identity_output(id_res.raw_output)
                    if (
                        live_ident
                        and dev.observed_identity
                        and live_ident.lower() != dev.observed_identity.lower()
                    ):
                        identity_collision = True
                        warnings.append(
                            f"Device identity mismatch: expected '{dev.observed_identity}', "
                            f"observed '{live_ident}' on {dev.management_ip or device_id}."
                        )
                    elif live_ident:
                        device_identity = live_ident

            # Approved read-only route command for RouterOS v6 & v7
            primary_cmd = "/ip route print detail"
            exec_res: Optional[CommandExecutionResult] = None
            retries_used = 0
            max_attempts = max(1, 1 + max(0, max_retries))

            for attempt in range(max_attempts):
                if cancel_event is not None and cancel_event.is_set():
                    return self._cancelled_result(dev, ros_version, ros_major, wall_start, t0)

                remaining_timeout = max(0.5, timeout_sec - (time.perf_counter() - t0))
                req = CommandExecutionRequest(
                    device_id=target_ref,
                    command_str=primary_cmd,
                    observation_domain="routes",
                    timeout=remaining_timeout,
                )
                exec_res = self.executor.execute(req)

                if exec_res.is_success:
                    break

                # Never retry security rejections or target-not-found errors
                if exec_res.execution_status == ExecutionStatus.SECURITY_REJECTED:
                    break
                if exec_res.error_classification == "TARGET_NOT_FOUND":
                    break
                if (time.perf_counter() - t0) >= timeout_sec:
                    break

                # Transient failure backoff (using Event.wait instead of busy-loop/uninterruptible sleep)
                if attempt + 1 < max_attempts:
                    retries_used += 1
                    delay = min(2.0, backoff_base_sec * (2 ** attempt))
                    if cancel_event is not None:
                        if cancel_event.wait(timeout=delay):
                            return self._cancelled_result(dev, ros_version, ros_major, wall_start, t0)
                    else:
                        evt = threading.Event()
                        evt.wait(timeout=delay)

            assert exec_res is not None
            collected_ts = time.time()

            # Handle command execution failures
            if not exec_res.is_success:
                err_clean = mask_sensitive_data(exec_res.raw_output or exec_res.error_classification or "Execution failed")
                errors.append(err_clean)
                if exec_res.execution_status == ExecutionStatus.SECURITY_REJECTED:
                    status = RouteCollectionStatus.SECURITY_REJECTED.value
                    completeness = RouteCompleteness.FAILED.value
                elif exec_res.execution_status == ExecutionStatus.TIMEOUT:
                    status = RouteCollectionStatus.TIMEOUT.value
                    completeness = RouteCompleteness.UNREACHABLE.value
                else:
                    low_err = err_clean.lower()
                    if any(k in low_err for k in ("unreachable", "refused", "timed out", "timeout", "no route to host", "offline", "gagal")):
                        status = RouteCollectionStatus.UNREACHABLE.value
                        completeness = RouteCompleteness.UNREACHABLE.value
                    else:
                        status = RouteCollectionStatus.FAILED.value
                        completeness = RouteCompleteness.FAILED.value

                result = RouteCollectionResult(
                    device_id=device_id,
                    device_identity=device_identity,
                    platform=platform,
                    router_os_version=ros_version,
                    ros_major_version=ros_major,
                    management_ip=dev.management_ip,
                    status=status,
                    collected_at=collected_ts,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    source_command=primary_cmd,
                    parser_version=PARSER_VERSION,
                    routes=[],
                    routing_tables=[],
                    completeness=completeness,
                    errors=errors,
                    warnings=warnings,
                    retries_used=retries_used,
                    identity_collision=identity_collision,
                )
                self._store_result(result)
                return result

            # Parse raw route output through authoritative UnifiedRouteParser
            raw_output = exec_res.raw_output or ""
            is_truncated = exec_res.truncated or ("[truncated]" in raw_output.lower())
            evidence_id = f"ev_routes_{uuid.uuid4().hex[:10]}"

            try:
                parsed_routes, parse_report = self.parser.parse_with_report(
                    raw_output,
                    device_id=device_id,
                    ros_version=ros_major,
                )
            except Exception as parse_exc:
                logger.warning("Parser exception on device %s: %s", device_id, parse_exc)
                err_msg = mask_sensitive_data(f"UnifiedRouteParser error: {parse_exc}")
                fail_res = RouteCollectionResult(
                    device_id=device_id,
                    device_identity=device_identity,
                    platform=platform,
                    router_os_version=ros_version,
                    ros_major_version=ros_major,
                    management_ip=dev.management_ip,
                    status=RouteCollectionStatus.FAILED.value,
                    collected_at=collected_ts,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    source_command=primary_cmd,
                    parser_version=PARSER_VERSION,
                    routes=[],
                    routing_tables=[],
                    parser_report=RouteParseReport(status="ERROR", warning=err_msg, is_partial=True),
                    completeness=RouteCompleteness.FAILED.value,
                    errors=[err_msg],
                    warnings=warnings,
                    evidence_id=evidence_id,
                    retries_used=retries_used,
                    identity_collision=identity_collision,
                )
                self._store_result(fail_res)
                return fail_res

            # Handle parser-reported CLI error
            if parse_report.status == "ERROR":
                errors.append(parse_report.warning or "RouterOS route CLI output reported an error.")
                err_res = RouteCollectionResult(
                    device_id=device_id,
                    device_identity=device_identity,
                    platform=platform,
                    router_os_version=ros_version,
                    ros_major_version=ros_major,
                    management_ip=dev.management_ip,
                    status=RouteCollectionStatus.FAILED.value,
                    collected_at=collected_ts,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    source_command=primary_cmd,
                    parser_version=PARSER_VERSION,
                    routes=[],
                    routing_tables=[],
                    parser_report=parse_report,
                    completeness=RouteCompleteness.FAILED.value,
                    errors=errors,
                    warnings=warnings,
                    evidence_id=evidence_id,
                    retries_used=retries_used,
                    identity_collision=identity_collision,
                )
                self._store_result(err_res)
                return err_res

            # Deduplicate identical routes & stamp canonical provenance
            deduped_routes, dup_removed = _deduplicate_routes(parsed_routes)
            if dup_removed > 0:
                warnings.append(f"Deduplicated {dup_removed} identical route entries from raw output.")

            tables_seen: List[str] = []
            tables_set: Set[str] = set()
            detected_ros_major = ros_major

            for r in deduped_routes:
                r.device_id = device_id
                r.collection_timestamp = collected_ts
                r.parser_version = PARSER_VERSION
                if r.source_ros_version in (6, 7):
                    detected_ros_major = r.source_ros_version
                r.evidence_provenance = {
                    "evidence_id": evidence_id,
                    "device_id": device_id,
                    "device_identity": device_identity,
                    "source_command": primary_cmd,
                    "collected_at": collected_ts,
                    "parser_version": PARSER_VERSION,
                }
                tbl = r.routing_table or "main"
                if tbl not in tables_set:
                    tables_set.add(tbl)
                    tables_seen.append(tbl)

            if not tables_seen and deduped_routes:
                tables_seen = ["main"]

            if not ros_version and detected_ros_major in (6, 7):
                ros_version = f"v{detected_ros_major}"

            if parse_report.warning:
                warnings.append(parse_report.warning)
            if is_truncated:
                warnings.append("CLI route output was truncated by transport limit; dataset is partial.")

            # Determine completeness & collection status
            if is_truncated or parse_report.is_partial:
                completeness = RouteCompleteness.PARTIAL.value
                status = RouteCollectionStatus.PARTIAL.value
            elif parse_report.status == "EMPTY" or len(deduped_routes) == 0:
                completeness = RouteCompleteness.EMPTY.value
                status = RouteCollectionStatus.PARTIAL.value
                warnings.append("Device returned zero parseable routes.")
            elif identity_collision:
                completeness = RouteCompleteness.PARTIAL.value
                status = RouteCollectionStatus.PARTIAL.value
            else:
                completeness = RouteCompleteness.COMPLETE.value
                status = RouteCollectionStatus.SUCCESS.value

            final_result = RouteCollectionResult(
                device_id=device_id,
                device_identity=device_identity,
                platform=platform,
                router_os_version=ros_version,
                ros_major_version=detected_ros_major,
                management_ip=dev.management_ip,
                status=status,
                collected_at=collected_ts,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                source_command=primary_cmd,
                parser_version=PARSER_VERSION,
                routes=deduped_routes,
                routing_tables=tables_seen,
                parser_report=parse_report,
                completeness=completeness,
                errors=errors,
                warnings=warnings,
                evidence_id=evidence_id,
                retries_used=retries_used,
                identity_collision=identity_collision,
            )
            self._store_result(final_result)
            return final_result

        finally:
            with self._state_lock:
                self._in_progress_devices.discard(device_id)
            dev_lock.release()

    def _cancelled_result(
        self,
        dev: CanonicalDevice,
        ros_version: str,
        ros_major: Optional[int],
        wall_start: float,
        t0: float,
    ) -> RouteCollectionResult:
        return RouteCollectionResult(
            device_id=dev.device_id,
            device_identity=dev.display_name or dev.device_id,
            platform=dev.platform or dev.device_type or "mikrotik",
            router_os_version=ros_version,
            ros_major_version=ros_major,
            management_ip=dev.management_ip,
            status=RouteCollectionStatus.CANCELLED.value,
            collected_at=wall_start,
            duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            completeness=RouteCompleteness.CANCELLED.value,
            errors=["Route collection cancelled."],
        )

    def _store_result(self, result: RouteCollectionResult) -> None:
        with self._state_lock:
            if result.evidence_id in self._seen_evidence_ids:
                return
            self._seen_evidence_ids.add(result.evidence_id)
            if len(self._seen_evidence_ids) > 2000:
                # Keep bounded set size
                self._seen_evidence_ids = {r.evidence_id for r in self._latest_results.values()} | {result.evidence_id}
            # Never overwrite valid complete route evidence with a skipped duplicate placeholder
            if result.status == RouteCollectionStatus.SKIPPED_DUPLICATE.value and result.device_id in self._latest_results:
                return
            self._latest_results[result.device_id] = result

    # ------------------------------------------------------------------
    # Multi-Device Concurrent Collection
    # ------------------------------------------------------------------

    def collect_multi_device_routes(
        self,
        targets: Optional[Sequence[Union[str, CanonicalDevice]]] = None,
        max_concurrency: Optional[int] = None,
        timeout_per_device: float = DEFAULT_DEVICE_TIMEOUT_SEC,
        max_retries: int = 1,
        backoff_base_sec: float = 0.25,
        cancel_event: Optional[threading.Event] = None,
        verify_identity: bool = False,
        reuse_fresh_sec: float = 0.0,
        job_id: Optional[str] = None,
    ) -> MultiDeviceRouteCollectionReport:
        """
        Collects normalized route datasets across multiple CanonicalDevice targets
        with bounded thread-pool concurrency, partial failure isolation, and cancellation.
        """
        jid = job_id or f"rjob_{uuid.uuid4().hex[:10]}"
        started_at = time.time()
        t0 = time.perf_counter()
        job_cancel = cancel_event or threading.Event()

        resolved_devs, unresolved_targets, collisions = self.resolve_targets(targets)
        concurrency = max(
            1,
            min(
                max_concurrency if max_concurrency is not None else self.default_max_concurrency,
                ABSOLUTE_MAX_CONCURRENCY,
                max(1, len(resolved_devs)),
            ),
        )

        with self._state_lock:
            self._active_jobs[jid] = (job_cancel, started_at, [d.device_id for d in resolved_devs])

        results: Dict[str, RouteCollectionResult] = {}
        collision_device_ids: Set[str] = set()
        if collisions:
            # Flag devices participating in IP/identity collisions
            ip_counts: Dict[str, List[str]] = {}
            id_counts: Dict[str, List[str]] = {}
            for d in resolved_devs:
                if d.management_ip:
                    ip_counts.setdefault(d.management_ip, []).append(d.device_id)
                ik = (d.observed_identity or d.hostname or "").strip().lower()
                if ik:
                    id_counts.setdefault(ik, []).append(d.device_id)
            for grp in list(ip_counts.values()) + list(id_counts.values()):
                if len(grp) > 1:
                    collision_device_ids.update(grp)

        try:
            if resolved_devs:
                with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="aira_route_col") as pool:
                    future_map: Dict[Future[RouteCollectionResult], CanonicalDevice] = {}
                    for dev in resolved_devs:
                        if job_cancel.is_set():
                            results[dev.device_id] = self._cancelled_result(
                                dev,
                                dev.os_version or "",
                                dev.ros_major_version,
                                time.time(),
                                t0,
                            )
                            continue
                        fut = pool.submit(
                            self.collect_device_routes,
                            dev,
                            timeout_per_device,
                            max_retries,
                            backoff_base_sec,
                            job_cancel,
                            verify_identity,
                            reuse_fresh_sec,
                        )
                        future_map[fut] = dev

                    for fut in as_completed(future_map):
                        dev = future_map[fut]
                        try:
                            res = fut.result()
                        except Exception as exc:
                            err_txt = mask_sensitive_data(f"Unhandled worker error: {exc}")
                            res = RouteCollectionResult(
                                device_id=dev.device_id,
                                device_identity=dev.display_name or dev.device_id,
                                platform=dev.platform or dev.device_type or "mikrotik",
                                router_os_version=dev.os_version or "",
                                ros_major_version=dev.ros_major_version,
                                management_ip=dev.management_ip,
                                status=RouteCollectionStatus.FAILED.value,
                                collected_at=time.time(),
                                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                                completeness=RouteCompleteness.FAILED.value,
                                errors=[err_txt],
                            )
                            self._store_result(res)

                        if dev.device_id in collision_device_ids and not res.identity_collision:
                            res.identity_collision = True
                            res.warnings.append(
                                "Registry identity/IP collision detected with another target device."
                            )
                            if res.status == RouteCollectionStatus.SUCCESS.value:
                                res.status = RouteCollectionStatus.PARTIAL.value
                                res.completeness = RouteCompleteness.PARTIAL.value

                        results[dev.device_id] = res
        finally:
            with self._state_lock:
                self._active_jobs.pop(jid, None)

        completed_at = time.time()
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        was_cancelled = job_cancel.is_set()

        # Determine overall report status
        succ = sum(1 for r in results.values() if r.status == RouteCollectionStatus.SUCCESS.value)
        part = sum(
            1
            for r in results.values()
            if r.status in (RouteCollectionStatus.PARTIAL.value, RouteCollectionStatus.SKIPPED_DUPLICATE.value)
        )
        if was_cancelled and succ == 0 and part == 0:
            overall = RouteCollectionStatus.CANCELLED.value
        elif len(results) > 0 and succ == len(results) and not unresolved_targets and not collisions:
            overall = RouteCollectionStatus.SUCCESS.value
        elif succ > 0 or part > 0:
            overall = RouteCollectionStatus.PARTIAL.value
        else:
            overall = RouteCollectionStatus.FAILED.value

        report = MultiDeviceRouteCollectionReport(
            job_id=jid,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            max_concurrency=concurrency,
            status=overall,
            results=results,
            identity_collisions=collisions,
            unresolved_targets=unresolved_targets,
            cancelled=was_cancelled,
        )

        with self._state_lock:
            self._recent_reports[jid] = report.to_dict(include_routes=False)
            if len(self._recent_reports) > MAX_CACHED_JOBS:
                oldest_key = next(iter(self._recent_reports))
                self._recent_reports.pop(oldest_key, None)

        return report

    # ------------------------------------------------------------------
    # Cancellation & Evidence Retrieval / Status
    # ------------------------------------------------------------------

    def cancel_job(self, job_id: str) -> bool:
        """Signals cancellation for an active multi-device route collection job."""
        with self._state_lock:
            entry = self._active_jobs.get(job_id)
            if not entry:
                return False
            entry[0].set()
            return True

    def ingest_bundle_routes(self, bundle_devices: Any) -> Dict[str, RouteCollectionResult]:
        """
        Extracts or normalizes RouteCollectionResults from an existing MultiDeviceEvidenceBundle
        (or its `device_bundles` mapping) so downstream route analytics can reuse already-collected
        evidence without double SSH!
        """
        ingested: Dict[str, RouteCollectionResult] = {}
        mapping = getattr(bundle_devices, "device_bundles", bundle_devices) or {}
        for target_key, dev_bundle in mapping.items():
            dev = self.registry.resolve_device(target_key)
            dev_id = dev.device_id if dev else str(target_key)
            dev_ident = (
                dev.display_name
                if dev
                else str(dev_bundle.get("display_name") or dev_bundle.get("target") or target_key)
            )
            ros_major = dev_bundle.get("ros_major_version") or (dev.ros_major_version if dev else 7) or 7
            ros_ver = (dev.os_version if dev and dev.os_version else f"v{ros_major}")

            route_item = None
            for it in dev_bundle.get("evidence_items", []):
                obs_t = getattr(it, "observation_type", None) or (it.get("observation_type") if isinstance(it, dict) else None)
                if obs_t == "routes":
                    route_item = it
                    break

            if route_item is None:
                res = RouteCollectionResult(
                    device_id=dev_id,
                    device_identity=dev_ident,
                    router_os_version=ros_ver,
                    ros_major_version=ros_major,
                    management_ip=dev.management_ip if dev else "",
                    status=RouteCollectionStatus.FAILED.value,
                    completeness=RouteCompleteness.FAILED.value,
                    errors=list(dev_bundle.get("collection_errors", [])) or ["No route observation in bundle."],
                )
                ingested[dev_id] = res
                continue

            coll_status = getattr(route_item, "collection_status", None) or (
                route_item.get("collection_status") if isinstance(route_item, dict) else "FAILED"
            )
            coll_ts = getattr(route_item, "collection_timestamp", None) or (
                route_item.get("collection_timestamp") if isinstance(route_item, dict) else time.time()
            )
            src_cmd = getattr(route_item, "source_command", None) or (
                route_item.get("source_command") if isinstance(route_item, dict) else "/ip route print detail"
            )
            ev_id = getattr(route_item, "evidence_id", None) or (
                route_item.get("evidence_id") if isinstance(route_item, dict) else f"ev_routes_{uuid.uuid4().hex[:8]}"
            )
            norm_val = getattr(route_item, "normalized_value", None)
            if norm_val is None and isinstance(route_item, dict):
                norm_val = route_item.get("normalized_value")

            if coll_status not in ("SUCCESS", "PARTIAL") or not isinstance(norm_val, dict):
                lim = getattr(route_item, "limitations", "") if not isinstance(route_item, dict) else route_item.get("limitations", "")
                res = RouteCollectionResult(
                    device_id=dev_id,
                    device_identity=dev_ident,
                    router_os_version=ros_ver,
                    ros_major_version=ros_major,
                    management_ip=dev.management_ip if dev else "",
                    status=RouteCollectionStatus.UNREACHABLE.value if "timeout" in str(lim).lower() else RouteCollectionStatus.FAILED.value,
                    collected_at=float(coll_ts or time.time()),
                    source_command=str(src_cmd),
                    completeness=RouteCompleteness.FAILED.value,
                    errors=[str(lim or "Route collection failed in evidence bundle.")],
                    evidence_id=str(ev_id),
                )
                ingested[dev_id] = res
                continue

            routes_list: List[NormalizedRoute] = []
            tables_seen: List[str] = []
            for rd in norm_val.get("routes", []):
                if isinstance(rd, NormalizedRoute):
                    nr = rd
                elif isinstance(rd, dict):
                    nr = NormalizedRoute(
                        dst_prefix=str(rd.get("dst_prefix") or rd.get("dst_address") or "0.0.0.0/0"),
                        gateway=str(rd.get("gateway") or ""),
                        device_id=dev_id,
                        interface_name=rd.get("interface_name") or rd.get("interface"),
                        routing_table=str(rd.get("routing_table") or "main"),
                        gateways=list(rd.get("gateways") or []),
                        immediate_gw=rd.get("immediate_gw"),
                        pref_src=rd.get("pref_src"),
                        protocol=str(rd.get("protocol") or ("connected" if rd.get("connect") else "static")),
                        distance=int(rd.get("distance") if rd.get("distance") is not None else 1),
                        metric=rd.get("metric"),
                        scope=rd.get("scope"),
                        target_scope=rd.get("target_scope"),
                        active=bool(rd.get("active", True)),
                        disabled=bool(rd.get("disabled", False)),
                        unreachable=bool(rd.get("unreachable", False)),
                        dynamic=bool(rd.get("dynamic", False)),
                        connect=bool(rd.get("connect", False)),
                        static=bool(rd.get("static", False)),
                        ospf=bool(rd.get("ospf", False)),
                        bgp=bool(rd.get("bgp", False)),
                        raw_flags=str(rd.get("raw_flags") or ""),
                        source_ros_version=ros_major,
                        collection_timestamp=float(coll_ts or time.time()),
                        parser_version=PARSER_VERSION,
                        evidence_provenance={"evidence_id": str(ev_id), "device_id": dev_id, "source_command": str(src_cmd)},
                    )
                else:
                    continue
                nr.device_id = dev_id
                routes_list.append(nr)
                if nr.routing_table not in tables_seen:
                    tables_seen.append(nr.routing_table)

            completeness = (
                RouteCompleteness.COMPLETE.value
                if coll_status == "SUCCESS" and routes_list
                else RouteCompleteness.PARTIAL.value
                if coll_status == "PARTIAL"
                else RouteCompleteness.EMPTY.value
            )
            res = RouteCollectionResult(
                device_id=dev_id,
                device_identity=dev_ident,
                router_os_version=ros_ver,
                ros_major_version=ros_major,
                management_ip=dev.management_ip if dev else "",
                status=RouteCollectionStatus.SUCCESS.value if coll_status == "SUCCESS" else RouteCollectionStatus.PARTIAL.value,
                collected_at=float(coll_ts or time.time()),
                source_command=str(src_cmd),
                parser_version=PARSER_VERSION,
                routes=routes_list,
                routing_tables=tables_seen or ["main"],
                completeness=completeness,
                evidence_id=str(ev_id),
            )
            self._store_result(res)
            ingested[dev_id] = res

        return ingested

    def get_latest_result(self, device_query: str) -> Optional[RouteCollectionResult]:
        with self._state_lock:
            if device_query in self._latest_results:
                return self._latest_results[device_query]
        dev = self.registry.resolve_device(device_query)
        if dev:
            with self._state_lock:
                return self._latest_results.get(dev.device_id)
        return None

    def list_latest_results(self) -> Dict[str, RouteCollectionResult]:
        with self._state_lock:
            return dict(self._latest_results)

    def store_result_for_testing_or_import(self, result: RouteCollectionResult) -> None:
        """Explicitly registers a RouteCollectionResult (used by historical replay or controlled fixtures)."""
        self._store_result(result)

    def clear_cache(self) -> None:
        with self._state_lock:
            self._latest_results.clear()
            self._seen_evidence_ids.clear()
            self._recent_reports.clear()

    def get_collection_status(self) -> Dict[str, Any]:
        with self._state_lock:
            active_jobs = [
                {
                    "job_id": jid,
                    "started_at": started,
                    "cancelling": evt.is_set(),
                    "target_device_ids": list(devs),
                }
                for jid, (evt, started, devs) in self._active_jobs.items()
            ]
            in_prog = sorted(self._in_progress_devices)
            devices_meta = {
                dev_id: res.to_dict(include_routes=False)
                for dev_id, res in self._latest_results.items()
            }
            recent_jobs = list(self._recent_reports.values())[-20:]

        return {
            "parser_version": PARSER_VERSION,
            "default_max_concurrency": self.default_max_concurrency,
            "absolute_max_concurrency": ABSOLUTE_MAX_CONCURRENCY,
            "in_progress_devices": in_prog,
            "active_jobs_count": len(active_jobs),
            "active_jobs": active_jobs,
            "cached_devices_count": len(devices_meta),
            "devices": devices_meta,
            "recent_jobs": recent_jobs,
        }


_route_collector_singleton: Optional[MultiDeviceRouteCollector] = None
_route_collector_lock = threading.Lock()


def get_route_collector() -> MultiDeviceRouteCollector:
    global _route_collector_singleton
    if _route_collector_singleton is None:
        with _route_collector_lock:
            if _route_collector_singleton is None:
                _route_collector_singleton = MultiDeviceRouteCollector()
    return _route_collector_singleton
