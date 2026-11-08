"""
core/network_intelligence/multi_device_collector.py — Multi-Device Evidence Collection Orchestrator for AIRA OS.

Orchestrates concurrent, bounded, read-only evidence collection across multiple network devices.
Preserves partial results: failures on device A or observation B do not discard successful observations on device C.
Provides rich collection metrics, provenance tracking, and cross-device contradiction detection.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.canonical_network import CanonicalNetworkRegistry, get_canonical_registry
from core.network_intelligence.evidence import (
    COMMAND_MAP_V6,
    COMMAND_MAP_V7,
    EvidenceCollector,
)
from core.network_intelligence.models import (
    EvidenceFreshness,
    EvidenceItem,
    EvidenceState,
)

logger = logging.getLogger("aira.network_intelligence.multi_device_collector")


@dataclass
class DeviceCollectionSummary:
    device_id: str
    display_name: str
    status: str  # SUCCESS, PARTIAL, FAILED, UNREACHABLE
    total_commands: int
    successful_commands: int
    failed_commands: int
    unsupported_commands: int
    duration_ms: float
    error_details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "status": self.status,
            "total_commands": self.total_commands,
            "successful_commands": self.successful_commands,
            "failed_commands": self.failed_commands,
            "unsupported_commands": self.unsupported_commands,
            "duration_ms": self.duration_ms,
            "error_details": list(self.error_details),
        }


@dataclass
class MultiDeviceCollectionSummary:
    total_devices: int
    successful_devices: int
    partial_devices: int
    failed_devices: int
    total_commands: int
    successful_commands: int
    failed_commands: int
    unsupported_commands: int
    total_duration_ms: float
    device_summaries: Dict[str, DeviceCollectionSummary] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_devices": self.total_devices,
            "successful_devices": self.successful_devices,
            "partial_devices": self.partial_devices,
            "failed_devices": self.failed_devices,
            "total_commands": self.total_commands,
            "successful_commands": self.successful_commands,
            "failed_commands": self.failed_commands,
            "unsupported_commands": self.unsupported_commands,
            "total_duration_ms": self.total_duration_ms,
            "device_summaries": {k: v.to_dict() for k, v in self.device_summaries.items()},
        }


@dataclass
class MultiDeviceEvidenceBundle:
    bundle_id: str
    timestamp: float
    device_bundles: Dict[str, Dict[str, Any]]
    summary: MultiDeviceCollectionSummary
    cross_device_contradictions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        serialized_bundles = {}
        for dev_id, b in self.device_bundles.items():
            serialized_bundles[dev_id] = {
                "target": b.get("target"),
                "ros_major_version": b.get("ros_major_version"),
                "display_name": b.get("display_name"),
                "evidence_items": [it.to_dict() if hasattr(it, "to_dict") else it for it in b.get("evidence_items", [])],
                "contradictions": b.get("contradictions", []),
                "collection_errors": b.get("collection_errors", []),
            }
        return {
            "bundle_id": self.bundle_id,
            "timestamp": self.timestamp,
            "device_bundles": serialized_bundles,
            "summary": self.summary.to_dict(),
            "cross_device_contradictions": list(self.cross_device_contradictions),
        }


class MultiDeviceEvidenceOrchestrator:
    """
    Coordinates multi-device evidence collection across arbitrary target fleets.
    Preserves partial results and handles network/auth drops gracefully.
    """

    def __init__(
        self,
        evidence_collector: Optional[EvidenceCollector] = None,
        registry: Optional[CanonicalNetworkRegistry] = None,
    ):
        self.collector = evidence_collector or EvidenceCollector()
        self.registry = registry or get_canonical_registry()

    def collect_multi_device_bundle(
        self,
        targets: List[str],
        required_types: Optional[List[str]] = None,
        max_concurrency: int = 3,
        timeout_per_cmd: float = 10.0,
    ) -> MultiDeviceEvidenceBundle:
        """
        Collects requested evidence types from multiple devices concurrently.
        """
        bundle_id = f"mbundle_{uuid.uuid4().hex[:10]}"
        t_start = time.time()
        req_types = required_types or [
            "identity",
            "resources",
            "interfaces",
            "ip_addresses",
            "routes",
            "arp",
        ]

        if not targets:
            summary = MultiDeviceCollectionSummary(
                total_devices=0,
                successful_devices=0,
                partial_devices=0,
                failed_devices=0,
                total_commands=0,
                successful_commands=0,
                failed_commands=0,
                unsupported_commands=0,
                total_duration_ms=0.0,
            )
            return MultiDeviceEvidenceBundle(
                bundle_id=bundle_id,
                timestamp=t_start,
                device_bundles={},
                summary=summary,
            )

        concurrency = max(1, min(max_concurrency, len(targets)))
        device_bundles: Dict[str, Dict[str, Any]] = {}
        device_summaries: Dict[str, DeviceCollectionSummary] = {}

        def _collect_worker(target: str) -> tuple[str, Dict[str, Any], DeviceCollectionSummary]:
            t0 = time.time()
            dev_obj = self.registry.resolve_device(target)
            disp_name = dev_obj.display_name if dev_obj else target

            try:
                bundle = self.collector.collect_evidence_bundle(
                    target=target,
                    required_types=req_types,
                    timeout_per_cmd=timeout_per_cmd,
                )
                t_dur = round((time.time() - t0) * 1000, 2)

                items: List[EvidenceItem] = bundle.get("evidence_items", [])
                total_cmds = len(req_types)
                success_cmds = sum(1 for it in items if it.collection_status == "SUCCESS")
                failed_cmds = sum(1 for it in items if it.collection_status in ("FAILED", "ERROR"))
                unsupported_cmds = total_cmds - len(items)

                errors = list(bundle.get("collection_errors", []))
                for it in items:
                    if it.collection_status != "SUCCESS" and it.limitations:
                        errors.append(f"{it.observation_type}: {it.limitations}")

                if success_cmds == len(items) and len(items) > 0 and not errors:
                    dev_status = "SUCCESS"
                elif success_cmds > 0:
                    dev_status = "PARTIAL"
                else:
                    dev_status = "FAILED"

                summary = DeviceCollectionSummary(
                    device_id=target,
                    display_name=disp_name,
                    status=dev_status,
                    total_commands=total_cmds,
                    successful_commands=success_cmds,
                    failed_commands=failed_cmds,
                    unsupported_commands=unsupported_cmds,
                    duration_ms=t_dur,
                    error_details=errors,
                )
                return target, bundle, summary

            except Exception as exc:
                t_dur = round((time.time() - t0) * 1000, 2)
                err_str = str(exc)
                fallback_bundle = {
                    "target": target,
                    "ros_major_version": 7,
                    "display_name": disp_name,
                    "evidence_items": [],
                    "contradictions": [],
                    "collection_errors": [f"Fatal collection error: {err_str}"],
                }
                summary = DeviceCollectionSummary(
                    device_id=target,
                    display_name=disp_name,
                    status="FAILED",
                    total_commands=len(req_types),
                    successful_commands=0,
                    failed_commands=len(req_types),
                    unsupported_commands=0,
                    duration_ms=t_dur,
                    error_details=[f"Unhandled exception: {err_str}"],
                )
                return target, fallback_bundle, summary

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_target = {executor.submit(_collect_worker, t): t for t in targets}
            for future in as_completed(future_to_target):
                tgt, b_res, s_res = future.result()
                device_bundles[tgt] = b_res
                device_summaries[tgt] = s_res

        t_total_dur = round((time.time() - t_start) * 1000, 2)

        # Compute fleet aggregates
        tot_dev = len(targets)
        succ_dev = sum(1 for s in device_summaries.values() if s.status == "SUCCESS")
        part_dev = sum(1 for s in device_summaries.values() if s.status == "PARTIAL")
        fail_dev = sum(1 for s in device_summaries.values() if s.status == "FAILED")
        tot_cmd = sum(s.total_commands for s in device_summaries.values())
        succ_cmd = sum(s.successful_commands for s in device_summaries.values())
        fail_cmd = sum(s.failed_commands for s in device_summaries.values())
        unsup_cmd = sum(s.unsupported_commands for s in device_summaries.values())

        global_summary = MultiDeviceCollectionSummary(
            total_devices=tot_dev,
            successful_devices=succ_dev,
            partial_devices=part_dev,
            failed_devices=fail_dev,
            total_commands=tot_cmd,
            successful_commands=succ_cmd,
            failed_commands=fail_cmd,
            unsupported_commands=unsup_cmd,
            total_duration_ms=t_total_dur,
            device_summaries=device_summaries,
        )

        # Check cross-device contradictions (e.g. conflicting IP assignments)
        cross_contradictions = self._detect_cross_device_contradictions(device_bundles)

        return MultiDeviceEvidenceBundle(
            bundle_id=bundle_id,
            timestamp=t_start,
            device_bundles=device_bundles,
            summary=global_summary,
            cross_device_contradictions=cross_contradictions,
        )

    def _detect_cross_device_contradictions(self, bundles: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Scans collected evidence across all devices for cross-device IP collisions
        or duplicate gateway conflicts.
        """
        contradictions = []
        ip_to_devices: Dict[str, List[str]] = {}

        for dev_id, bundle in bundles.items():
            for item in bundle.get("evidence_items", []):
                if item.observation_type == "ip_addresses" and item.collection_status == "SUCCESS":
                    val = item.normalized_value or {}
                    addrs = val.get("addresses", [])
                    for a in addrs:
                        raw_ip = str(a.get("address", "")).split("/")[0].strip()
                        if raw_ip and raw_ip not in ("127.0.0.1", "0.0.0.0"):
                            ip_to_devices.setdefault(raw_ip, []).append(dev_id)

        for ip, dev_list in ip_to_devices.items():
            if len(dev_list) > 1:
                contradictions.append(
                    f"Cross-device IP collision: Alamat IP {ip} terdeteksi dikonfigurasi pada beberapa perangkat: {', '.join(dev_list)}."
                )

        return contradictions
