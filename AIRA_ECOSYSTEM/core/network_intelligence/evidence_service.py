"""
AIRA OS — Unified Network Evidence Intelligence Service (Networking VI / WP 6.1).

Provides Layer 1 (Evidence Acquisition) & Layer 2 (Evidence Normalization & Type-Aware Freshness):
- Assembles multi-device `NetworkEvidenceBundle` across Inventory, NMS, Topology, Route Snapshots,
  and selective read-only SSH collection without duplicate polling.
- Enforces evidence-type-aware freshness lifetimes (FRESH, AGING, STALE, EXPIRED, UNKNOWN).
- Strictly preserves `None` for missing/unestablished metrics (never fabricates 0.0).
- Surfaces explicit `CollectionGapRecord` and `EvidenceContradiction` entries.
- Maintains a bounded O(1) lookup index by `evidence_id` for API & UI Evidence Inspector.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import closing
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import uuid

from core.canonical_network import CanonicalDevice, CanonicalNetworkRegistry, get_canonical_registry
from core.network_intelligence.evidence import COMMAND_MAP_V7
from core.network_intelligence.intelligence_models import (
    CanonicalEvidenceRecord,
    CollectionGapRecord,
    EvidenceCompleteness,
    EvidenceContradiction,
    EvidenceQuality,
    IntelligenceFreshness,
    NetworkEvidenceBundle,
)
from core.network_intelligence.multi_device_collector import MultiDeviceEvidenceOrchestrator
from core.network_intelligence.security import redact_sensitive_values
from core.routing.route_collector import MultiDeviceRouteCollector, get_route_collector
from core.routing.unified_route_parser import NormalizedRoute, RouteType
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, get_topology_connection

logger = logging.getLogger("aira.network_intelligence.evidence_service")

# ---------------------------------------------------------------------------
# Evidence-Type-Aware Freshness Profiles (seconds: fresh_max, aging_max, stale_max)
# ---------------------------------------------------------------------------
FRESHNESS_TTL_PROFILES: Dict[str, Tuple[float, float, float]] = {
    # Fast resource & rate counters
    "cpu": (45.0, 120.0, 300.0),
    "memory": (45.0, 120.0, 300.0),
    "latency": (45.0, 120.0, 300.0),
    "device_resources": (45.0, 120.0, 300.0),
    "resources": (45.0, 120.0, 300.0),
    "nms_telemetry": (45.0, 120.0, 300.0),
    "interface_rates": (45.0, 120.0, 300.0),
    # Interface operational & counter state
    "interfaces": (60.0, 180.0, 600.0),
    "oper_status": (60.0, 180.0, 600.0),
    # Dynamic routing & neighbor state
    "routes": (90.0, 300.0, 900.0),
    "route_snapshot": (120.0, 600.0, 1800.0),
    "ospf_neighbors": (90.0, 300.0, 900.0),
    "ospf_instance": (180.0, 600.0, 1800.0),
    "bgp_peers": (90.0, 300.0, 900.0),
    "arp": (90.0, 300.0, 900.0),
    # Topology & discovery edges
    "topology_edges": (300.0, 900.0, 3600.0),
    "topology_snapshot": (300.0, 900.0, 3600.0),
    "neighbors": (300.0, 900.0, 3600.0),
    # Incidents & alert history
    "nms_incidents": (120.0, 600.0, 3600.0),
    # Semi-static configuration observations
    "identity": (300.0, 1800.0, 7200.0),
    "ip_addresses": (300.0, 1800.0, 7200.0),
    "bridge": (300.0, 1800.0, 7200.0),
    "bridge_ports": (300.0, 1800.0, 7200.0),
    "bridge_vlan": (300.0, 1800.0, 7200.0),
    "firewall_filter": (300.0, 1800.0, 7200.0),
    "nat_rules": (300.0, 1800.0, 7200.0),
    "mangle_rules": (300.0, 1800.0, 7200.0),
    "routing_rules": (300.0, 1800.0, 7200.0),
    "dns": (300.0, 1800.0, 7200.0),
    "tunnels": (120.0, 600.0, 1800.0),
    "qos_queues": (90.0, 300.0, 900.0),
    "ipv6_routes": (90.0, 300.0, 900.0),
}

DEFAULT_TTL_PROFILE: Tuple[float, float, float] = (90.0, 300.0, 900.0)

# Evidence types supported by existing approved read-only RouterOS SSH allowlist
APPROVED_SSH_EVIDENCE_TYPES: Set[str] = set(COMMAND_MAP_V7.keys())


def get_freshness_ttl_profile(evidence_type: str) -> Tuple[float, float, float]:
    """Returns (fresh_max_sec, aging_max_sec, stale_max_sec) for a given evidence type."""
    key = (evidence_type or "").strip().lower()
    return FRESHNESS_TTL_PROFILES.get(key, DEFAULT_TTL_PROFILE)


def evaluate_evidence_freshness(
    evidence_type: str,
    timestamp: Optional[float],
    current_time: Optional[float] = None,
) -> str:
    """
    Evaluates evidence-type-aware freshness state:
    FRESH, AGING, STALE, EXPIRED, or UNKNOWN.
    Never treats missing/zero timestamps as FRESH.
    """
    if timestamp is None:
        return IntelligenceFreshness.UNKNOWN.value
    try:
        ts_val = float(timestamp)
    except (TypeError, ValueError):
        return IntelligenceFreshness.UNKNOWN.value
    if ts_val <= 0.0:
        return IntelligenceFreshness.UNKNOWN.value

    now = float(current_time) if current_time is not None else time.time()
    age = max(0.0, now - ts_val)
    fresh_max, aging_max, stale_max = get_freshness_ttl_profile(evidence_type)

    if age <= fresh_max:
        return IntelligenceFreshness.FRESH.value
    if age <= aging_max:
        return IntelligenceFreshness.AGING.value
    if age <= stale_max:
        return IntelligenceFreshness.STALE.value
    return IntelligenceFreshness.EXPIRED.value


def _make_evidence_id(domain: str, device_id: str, suffix: str = "") -> str:
    seed = f"{domain}:{device_id}:{suffix}:{uuid.uuid4().hex[:8]}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    clean_dev = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (device_id or "net"))[:24]
    return f"ev_{domain}_{clean_dev}_{digest}"


def _route_from_dict(device_id: str, raw: Dict[str, Any]) -> NormalizedRoute:
    rtype_str = str(raw.get("route_type") or "unicast").lower()
    try:
        rtype = RouteType(rtype_str)
    except ValueError:
        rtype = RouteType.UNICAST
    gws = list(raw.get("gateways") or ([raw["gateway"]] if raw.get("gateway") else []))
    raw_attrs = dict(raw.get("raw_attributes") or raw.get("extra_attributes") or {})
    if raw.get("fib") is not None:
        raw_attrs["fib"] = bool(raw.get("fib"))
    if raw.get("hw_offloaded") is not None:
        raw_attrs["hw_offloaded"] = bool(raw.get("hw_offloaded"))
    if raw.get("comment"):
        raw_attrs["comment"] = str(raw.get("comment"))
    return NormalizedRoute(
        device_id=device_id,
        routing_table=str(raw.get("routing_table") or "main"),
        dst_prefix=str(raw.get("dst_prefix") or "0.0.0.0/0"),
        gateway=str(raw.get("gateway") or ""),
        gateways=gws,
        immediate_gw=raw.get("immediate_gw"),
        interface_name=raw.get("interface_name"),
        pref_src=raw.get("pref_src"),
        distance=int(raw.get("distance") if raw.get("distance") is not None else 1),
        scope=raw.get("scope"),
        target_scope=raw.get("target_scope"),
        metric=raw.get("metric"),
        protocol=str(raw.get("protocol") or "static"),
        route_type=rtype,
        active=bool(raw.get("active", True)),
        disabled=bool(raw.get("disabled", False)),
        selected=raw.get("selected"),
        dynamic=bool(raw.get("dynamic", False)),
        static=bool(raw.get("static", False)),
        connect=bool(raw.get("connect", False)),
        unreachable=bool(raw.get("unreachable", False) or rtype == RouteType.UNREACHABLE),
        source_ros_version=raw.get("source_ros_version"),
        raw_flags=str(raw.get("raw_flags") or ""),
        evidence_provenance=dict(raw.get("evidence_provenance") or {}),
        raw_attributes=raw_attrs,
    )


class UnifiedEvidenceService:
    """
    Authoritative Layer 1 & Layer 2 Evidence Service for Networking VI.
    Reuses fresh NMS, Topology, Route, and cached CLI observations before issuing any SSH query.
    """

    def __init__(
        self,
        topology_db_path: Optional[Path | str] = None,
        registry: Optional[CanonicalNetworkRegistry] = None,
        route_collector: Optional[MultiDeviceRouteCollector] = None,
        ssh_orchestrator: Optional[MultiDeviceEvidenceOrchestrator] = None,
        max_cached_bundles: int = 24,
        max_indexed_records: int = 2500,
    ) -> None:
        self.db_path = (Path(topology_db_path) if topology_db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.registry = registry or get_canonical_registry()
        self.route_collector = route_collector or get_route_collector()
        self.ssh_orchestrator = ssh_orchestrator or MultiDeviceEvidenceOrchestrator(registry=self.registry)

        self._lock = threading.RLock()
        self._max_cached_bundles = max(4, max_cached_bundles)
        self._max_indexed_records = max(200, max_indexed_records)
        self._bundle_cache: OrderedDict[str, NetworkEvidenceBundle] = OrderedDict()
        self._record_index: OrderedDict[str, CanonicalEvidenceRecord] = OrderedDict()
        # Per-device CLI observation cache: (device_id, obs_type) -> CanonicalEvidenceRecord
        self._cli_cache: OrderedDict[Tuple[str, str], CanonicalEvidenceRecord] = OrderedDict()

    # ------------------------------------------------------------------
    # Index & Cache Helpers
    # ------------------------------------------------------------------
    def _index_record(self, record: CanonicalEvidenceRecord) -> None:
        with self._lock:
            self._record_index[record.evidence_id] = record
            self._record_index.move_to_end(record.evidence_id)
            while len(self._record_index) > self._max_indexed_records:
                self._record_index.popitem(last=False)

    def get_evidence_by_id(self, evidence_id: str, now: Optional[float] = None) -> Optional[CanonicalEvidenceRecord]:
        with self._lock:
            rec = self._record_index.get(evidence_id)
        if rec is None:
            return None
        # Re-evaluate freshness dynamically at inspection time
        ts = rec.observed_at if rec.observed_at is not None else rec.collected_at
        rec.freshness = evaluate_evidence_freshness(rec.evidence_type, ts, current_time=now)
        return rec

    def clear_caches(self) -> None:
        with self._lock:
            self._bundle_cache.clear()
            self._cli_cache.clear()

    # ------------------------------------------------------------------
    # Primary Bundle Assembly
    # ------------------------------------------------------------------
    def assemble_evidence_bundle(
        self,
        scope: str = "network",
        target_devices: Optional[Sequence[str]] = None,
        selected_interfaces: Optional[Sequence[str]] = None,
        required_types: Optional[Sequence[str]] = None,
        allow_live_collection: bool = False,
        synthetic_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> NetworkEvidenceBundle:
        """
        Assembles a multi-device `NetworkEvidenceBundle` with zero duplicate polling.
        If `synthetic_data` is supplied, builds a deterministic hermetic bundle from it.
        """
        curr_ts = float(now) if now is not None else time.time()
        corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:10]}"
        bundle_id = f"neb_{uuid.uuid4().hex[:12]}"

        if synthetic_data is not None:
            bundle = self._assemble_from_synthetic(
                bundle_id=bundle_id,
                correlation_id=corr_id,
                scope=scope,
                synthetic_data=synthetic_data,
                selected_interfaces=list(selected_interfaces or []),
                now=curr_ts,
            )
            self._finalize_bundle(bundle, curr_ts)
            return bundle

        req_types = list(
            required_types
            or [
                "device_resources",
                "interfaces",
                "routes",
                "topology_edges",
                "nms_incidents",
            ]
        )

        # 1. Resolve canonical devices + topology DB devices
        resolved_devices = self._resolve_device_map(target_devices)
        selected_dev_ids = list(resolved_devices.keys())

        bundle = NetworkEvidenceBundle(
            bundle_id=bundle_id,
            correlation_id=corr_id,
            assembled_at=curr_ts,
            scope=scope,
            selected_devices=selected_dev_ids,
            selected_interfaces=list(selected_interfaces or []),
        )

        # 2. Acquire NMS, Topology & Route Snapshot state from topology.db in one read-only pass
        db_state = self._read_topology_and_nms_db(selected_dev_ids)
        bundle.topology_snapshot_ref = db_state.get("latest_topology_snapshot_id")
        bundle.route_snapshot_refs = dict(db_state.get("latest_route_snapshot_ids") or {})
        bundle.historical_refs = {
            "latest_topology_snapshot_id": bundle.topology_snapshot_ref,
            "topology_snapshot_count": db_state.get("topology_snapshot_count", 0),
            "route_snapshot_ids": dict(bundle.route_snapshot_refs),
        }

        # 3. Normalize per-device NMS & inventory evidence
        devices_needing_ssh: Dict[str, List[str]] = {}
        for dev_id, dev_meta in resolved_devices.items():
            nms_prof = db_state["profiles"].get(dev_id, {})
            nms_metric = db_state["latest_device_metrics"].get(dev_id)
            nms_ifaces = db_state["latest_iface_metrics"].get(dev_id, [])

            # Device Evidence (never fabricating 0.0 for missing CPU/Memory/Latency)
            obs_ts = (
                (nms_metric.get("timestamp") if nms_metric else None)
                or nms_prof.get("last_check_at")
                or nms_prof.get("last_polled_at")
            )
            dev_freshness = evaluate_evidence_freshness("device_resources", obs_ts, curr_ts)
            nms_status = str(nms_prof.get("status") or dev_meta.get("nms_status") or "UNKNOWN")

            cpu_val = nms_metric.get("cpu_load_percent") if nms_metric else None
            mem_pct = nms_metric.get("memory_used_percent") if nms_metric else None
            mem_used = nms_metric.get("memory_used_bytes") if nms_metric else None
            mem_total = nms_metric.get("memory_total_bytes") if nms_metric else None
            storage_used = nms_metric.get("storage_used_bytes") if nms_metric else None
            storage_total = nms_metric.get("storage_total_bytes") if nms_metric else None
            uptime_sec = nms_metric.get("uptime_seconds") if nms_metric else None
            # Only treat latency as measured if device responded to probe or metric exists
            latency_val: Optional[float] = None
            if nms_metric and nms_metric.get("latency_ms") is not None:
                latency_val = float(nms_metric["latency_ms"])
            elif nms_status in ("UP", "DEGRADED", "MONITORING_UNAVAILABLE") and nms_prof.get("latency_ms") is not None:
                latency_val = float(nms_prof["latency_ms"])

            dev_payload = {
                "device_id": dev_id,
                "display_name": dev_meta.get("display_name") or dev_id,
                "identity": nms_prof.get("device_identity") or dev_meta.get("identity") or "",
                "management_ip": dev_meta.get("management_ip") or "",
                "mac_address": dev_meta.get("mac_address") or "",
                "model": nms_prof.get("routeros_model") or dev_meta.get("model") or "",
                "routeros_version": nms_prof.get("routeros_version") or dev_meta.get("os_version") or "",
                "ros_major_version": dev_meta.get("ros_major_version"),
                "device_type": dev_meta.get("device_type") or "router",
                "is_managed": bool(dev_meta.get("is_managed") or nms_prof.get("management_mode") == "managed"),
                "reachability_status": nms_status,
                "monitoring_method": nms_prof.get("monitoring_method") or "unknown",
                "cpu_load_percent": cpu_val,
                "memory_used_percent": mem_pct,
                "memory_used_bytes": mem_used,
                "memory_total_bytes": mem_total,
                "storage_used_bytes": storage_used,
                "storage_total_bytes": storage_total,
                "uptime_seconds": uptime_sec,
                "latency_ms": latency_val,
                "last_successful_observation": nms_prof.get("last_success_at") or nms_prof.get("last_successful_poll_at"),
                "last_check_at": obs_ts,
                "last_error": redact_sensitive_values(str(nms_prof.get("last_error") or "")),
                "capabilities": {
                    "snmp_enabled": bool(nms_prof.get("snmp_enabled")),
                    "ssh_registered": bool(dev_meta.get("is_managed")),
                },
            }
            bundle.device_evidence[dev_id] = dev_payload

            has_resource_metrics = any(v is not None for v in (cpu_val, mem_pct, uptime_sec))
            if obs_ts is not None:
                qual = (
                    EvidenceQuality.GOOD.value
                    if has_resource_metrics and nms_status == "UP"
                    else EvidenceQuality.PARTIAL.value
                )
                comp = (
                    EvidenceCompleteness.COMPLETE.value
                    if has_resource_metrics
                    else EvidenceCompleteness.PARTIAL.value
                )
                rec = CanonicalEvidenceRecord(
                    evidence_id=_make_evidence_id("dev", dev_id),
                    device_id=dev_id,
                    device_identity=dev_payload["identity"] or dev_payload["display_name"],
                    evidence_type="device_resources",
                    source_subsystem="nms",
                    collection_method=dev_payload["monitoring_method"] or "sqlite_cache",
                    collected_at=curr_ts,
                    observed_at=float(obs_ts),
                    validity_ttl_sec=get_freshness_ttl_profile("device_resources")[1],
                    freshness=dev_freshness,
                    quality=qual,
                    parser_version="6.1.0",
                    normalized_payload=dev_payload,
                    source_reference=f"topology.db:nms_device_profiles/{dev_id}",
                    sanitized_command_ref="nms_poll_cache",
                    confidence=0.92 if has_resource_metrics else 0.70,
                    completeness=comp,
                    provenance={"reused_from_cache": True, "vantage_point": "aira_nms"},
                )
                bundle.records.append(rec)
                bundle.reused_cached_count += 1
            else:
                bundle.collection_gaps.append(
                    CollectionGapRecord(
                        gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                        device_id=dev_id,
                        evidence_type="device_resources",
                        gap_reason="TELEMETRY_GAP",
                        detail="Belum ada sampel telemetri NMS yang tercatat untuk perangkat ini.",
                        timestamp=curr_ts,
                    )
                )

            if nms_status in ("DOWN", "SUSPECTED_DOWN"):
                bundle.collection_gaps.append(
                    CollectionGapRecord(
                        gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                        device_id=dev_id,
                        evidence_type="reachability",
                        gap_reason="DEVICE_UNREACHABLE",
                        detail=dev_payload["last_error"] or f"Status perangkat di NMS: {nms_status} (bukan bukti mati listrik tanpa koroborasi).",
                        timestamp=curr_ts,
                    )
                )
            elif nms_status == "MONITORING_UNAVAILABLE":
                bundle.collection_gaps.append(
                    CollectionGapRecord(
                        gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                        device_id=dev_id,
                        evidence_type="management_telemetry",
                        gap_reason="MANAGEMENT_UNAVAILABLE",
                        detail=dev_payload["last_error"] or "Host merespons ICMP, tetapi manajemen SSH/SNMP gagal.",
                        timestamp=curr_ts,
                    )
                )

            # Interface Evidence from NMS
            if nms_ifaces:
                if_ts = max((float(i.get("timestamp") or 0.0) for i in nms_ifaces), default=0.0)
                if_fresh = evaluate_evidence_freshness("interfaces", if_ts if if_ts > 0 else None, curr_ts)
                norm_ifaces: List[Dict[str, Any]] = []
                for row in nms_ifaces:
                    iname = row.get("interface_name") or ""
                    if selected_interfaces and iname not in selected_interfaces and f"{dev_id}:{iname}" not in selected_interfaces:
                        continue
                    # Preserve None when rate is unestablished (never treat None as 0.0)
                    rx_rate = row.get("rx_rate_bps")
                    tx_rate = row.get("tx_rate_bps")
                    norm_ifaces.append(
                        {
                            "device_id": dev_id,
                            "interface_name": iname,
                            "interface_type": row.get("interface_type") or "ether",
                            "oper_status": row.get("oper_status") or "unknown",
                            "admin_status": row.get("admin_status") or "enabled",
                            "mac_address": row.get("mac_address") or "",
                            "speed_bps": row.get("negotiated_speed_bps") or row.get("speed_bps") or None,
                            "duplex": row.get("duplex") or "unknown",
                            "rx_bytes": row.get("in_octets"),
                            "tx_bytes": row.get("out_octets"),
                            "rx_rate_bps": float(rx_rate) if rx_rate is not None else None,
                            "tx_rate_bps": float(tx_rate) if tx_rate is not None else None,
                            "rx_utilization_percent": row.get("rx_utilization_percent"),
                            "tx_utilization_percent": row.get("tx_utilization_percent"),
                            "in_errors": row.get("in_errors"),
                            "out_errors": row.get("out_errors"),
                            "in_drops": row.get("in_drops"),
                            "out_drops": row.get("out_drops"),
                            "last_counter_update": row.get("timestamp"),
                        }
                    )
                bundle.interface_evidence[dev_id] = norm_ifaces
                if_rec = CanonicalEvidenceRecord(
                    evidence_id=_make_evidence_id("iface", dev_id),
                    device_id=dev_id,
                    device_identity=dev_payload["identity"] or dev_payload["display_name"],
                    evidence_type="interfaces",
                    source_subsystem="nms",
                    collection_method=dev_payload["monitoring_method"] or "sqlite_cache",
                    collected_at=curr_ts,
                    observed_at=if_ts if if_ts > 0 else None,
                    validity_ttl_sec=get_freshness_ttl_profile("interfaces")[1],
                    freshness=if_fresh,
                    quality=EvidenceQuality.GOOD.value,
                    parser_version="6.1.0",
                    normalized_payload=norm_ifaces,
                    source_reference=f"topology.db:nms_interface_metrics/{dev_id}",
                    sanitized_command_ref="nms_interface_cache",
                    confidence=0.92,
                    completeness=EvidenceCompleteness.COMPLETE.value,
                    provenance={"reused_from_cache": True},
                )
                bundle.records.append(if_rec)
                bundle.reused_cached_count += 1
            else:
                bundle.interface_evidence[dev_id] = []

            # Routing Evidence from MultiDeviceRouteCollector or immutable route_snapshots
            route_res = self.route_collector.get_latest_result(dev_id)
            if route_res and route_res.routes:
                r_fresh = evaluate_evidence_freshness("routes", route_res.collected_at, curr_ts)
                bundle.routing_evidence[dev_id] = list(route_res.routes)
                r_rec = CanonicalEvidenceRecord(
                    evidence_id=route_res.evidence_id or _make_evidence_id("routes", dev_id),
                    device_id=dev_id,
                    device_identity=route_res.device_identity or dev_id,
                    evidence_type="routes",
                    source_subsystem="routing",
                    collection_method="routeros_ssh_readonly",
                    collected_at=curr_ts,
                    observed_at=route_res.collected_at,
                    validity_ttl_sec=get_freshness_ttl_profile("routes")[1],
                    freshness=r_fresh,
                    quality=EvidenceQuality.GOOD.value if route_res.completeness == "COMPLETE" else EvidenceQuality.PARTIAL.value,
                    parser_version=route_res.parser_version,
                    normalized_payload=[r.to_dict() for r in route_res.routes[:250]],
                    source_reference=bundle.route_snapshot_refs.get(dev_id, "route_collector_memory"),
                    sanitized_command_ref=route_res.source_command,
                    confidence=0.95 if route_res.completeness == "COMPLETE" else 0.75,
                    completeness=route_res.completeness,
                    provenance={"reused_from_cache": True, "route_count": len(route_res.routes)},
                )
                bundle.records.append(r_rec)
                bundle.reused_cached_count += 1
            elif dev_id in db_state["latest_route_snapshot_payloads"]:
                snap_info = db_state["latest_route_snapshot_payloads"][dev_id]
                snap_routes = [_route_from_dict(dev_id, rd) for rd in snap_info["routes"]]
                r_fresh = evaluate_evidence_freshness("route_snapshot", snap_info["created_at"], curr_ts)
                bundle.routing_evidence[dev_id] = snap_routes
                r_rec = CanonicalEvidenceRecord(
                    evidence_id=_make_evidence_id("routesnap", dev_id),
                    device_id=dev_id,
                    device_identity=dev_payload["identity"] or dev_id,
                    evidence_type="routes",
                    source_subsystem="routing",
                    collection_method="snapshot_store",
                    collected_at=curr_ts,
                    observed_at=snap_info["created_at"],
                    validity_ttl_sec=get_freshness_ttl_profile("route_snapshot")[1],
                    freshness=r_fresh,
                    quality=EvidenceQuality.GOOD.value,
                    parser_version="4.6.0",
                    normalized_payload=snap_info["routes"][:250],
                    source_reference=f"topology.db:route_snapshots/{snap_info['snapshot_id']}",
                    sanitized_command_ref="immutable_route_snapshot",
                    confidence=0.88,
                    completeness=snap_info["completeness"],
                    provenance={"reused_from_cache": True, "snapshot_id": snap_info["snapshot_id"]},
                )
                bundle.records.append(r_rec)
                bundle.reused_cached_count += 1
            else:
                bundle.routing_evidence[dev_id] = []

            # Reuse any fresh/aging CLI observations cached in UnifiedEvidenceService
            bundle.protocol_evidence.setdefault(dev_id, {})
            for rtype in req_types:
                if rtype in ("device_resources", "topology_edges", "nms_incidents"):
                    continue
                cached_cli = self._get_cached_cli_record(dev_id, rtype, curr_ts)
                if cached_cli is not None:
                    bundle.records.append(cached_cli)
                    bundle.reused_cached_count += 1
                    bundle.protocol_evidence[dev_id][rtype] = cached_cli.normalized_payload
                    continue

                # Determine if selective live SSH collection is warranted and permitted
                already_satisfied = (
                    (rtype == "interfaces" and bool(bundle.interface_evidence.get(dev_id)) and evaluate_evidence_freshness("interfaces", bundle.interface_evidence[dev_id][0].get("last_counter_update"), curr_ts) in (IntelligenceFreshness.FRESH.value, IntelligenceFreshness.AGING.value))
                    or (rtype == "routes" and bool(bundle.routing_evidence.get(dev_id)) and route_res is not None and evaluate_evidence_freshness("routes", route_res.collected_at, curr_ts) in (IntelligenceFreshness.FRESH.value, IntelligenceFreshness.AGING.value))
                )
                if already_satisfied:
                    continue

                if rtype not in APPROVED_SSH_EVIDENCE_TYPES and rtype not in ("interfaces", "routes", "resources", "identity"):
                    bundle.collection_gaps.append(
                        CollectionGapRecord(
                            gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                            device_id=dev_id,
                            evidence_type=rtype,
                            gap_reason="UNSUPPORTED_READONLY_BOUNDARY",
                            detail=f"Tipe bukti '{rtype}' tidak memiliki perintah CLI dalam daftar allowlist read-only saat ini.",
                            timestamp=curr_ts,
                        )
                    )
                    continue

                if allow_live_collection and dev_payload["is_managed"] and nms_status != "DOWN":
                    ssh_type = "resources" if rtype == "device_resources" else rtype
                    if ssh_type in APPROVED_SSH_EVIDENCE_TYPES:
                        devices_needing_ssh.setdefault(dev_id, []).append(ssh_type)
                else:
                    if rtype not in ("interfaces", "routes") or not (bundle.interface_evidence.get(dev_id) or bundle.routing_evidence.get(dev_id)):
                        bundle.collection_gaps.append(
                            CollectionGapRecord(
                                gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                                device_id=dev_id,
                                evidence_type=rtype,
                                gap_reason="NOT_COLLECTED",
                                detail=f"Bukti '{rtype}' belum tersedia di cache lokal (live SSH collection={'aktif' if allow_live_collection else 'nonaktif'}).",
                                timestamp=curr_ts,
                            )
                        )

        # 4. Selective Live Read-Only SSH Collection (only for missing/expired items when enabled)
        if allow_live_collection and devices_needing_ssh:
            self._collect_selective_ssh(bundle, devices_needing_ssh, curr_ts)

        # 5. Topology Edges & NMS Incidents Evidence
        for edge in db_state["topology_edges"]:
            e_ts = edge.get("last_verified_at") or edge.get("last_seen_at") or edge.get("created_at")
            e_fresh = evaluate_evidence_freshness("topology_edges", e_ts, curr_ts)
            edge_copy = dict(edge)
            edge_copy["freshness"] = e_fresh
            bundle.topology_evidence.append(edge_copy)

        if bundle.topology_evidence:
            latest_edge_ts = max(
                (float(e.get("last_verified_at") or e.get("last_seen_at") or 0.0) for e in bundle.topology_evidence),
                default=0.0,
            )
            topo_rec = CanonicalEvidenceRecord(
                evidence_id=_make_evidence_id("topo", "fabric"),
                device_id="network",
                device_identity="TopologyEngine",
                evidence_type="topology_edges",
                source_subsystem="topology",
                collection_method="sqlite_cache",
                collected_at=curr_ts,
                observed_at=latest_edge_ts if latest_edge_ts > 0 else None,
                validity_ttl_sec=get_freshness_ttl_profile("topology_edges")[1],
                freshness=evaluate_evidence_freshness("topology_edges", latest_edge_ts if latest_edge_ts > 0 else None, curr_ts),
                quality=EvidenceQuality.GOOD.value,
                parser_version="6.1.0",
                normalized_payload=bundle.topology_evidence,
                source_reference=f"topology.db:topology_edges (snapshot={bundle.topology_snapshot_ref or 'live'})",
                sanitized_command_ref="topology_edges_store",
                confidence=0.90,
                completeness=EvidenceCompleteness.COMPLETE.value,
                provenance={"reused_from_cache": True, "edge_count": len(bundle.topology_evidence)},
            )
            bundle.records.append(topo_rec)
            bundle.reused_cached_count += 1

        for inc in db_state["incidents"]:
            bundle.incident_evidence.append(dict(inc))
        if bundle.incident_evidence:
            latest_inc_ts = max((float(i.get("started_at") or 0.0) for i in bundle.incident_evidence), default=curr_ts)
            inc_rec = CanonicalEvidenceRecord(
                evidence_id=_make_evidence_id("inc", "nms"),
                device_id="network",
                device_identity="NmsIncidentStore",
                evidence_type="nms_incidents",
                source_subsystem="nms",
                collection_method="sqlite_cache",
                collected_at=curr_ts,
                observed_at=latest_inc_ts,
                validity_ttl_sec=get_freshness_ttl_profile("nms_incidents")[1],
                freshness=evaluate_evidence_freshness("nms_incidents", latest_inc_ts, curr_ts),
                quality=EvidenceQuality.GOOD.value,
                parser_version="6.1.0",
                normalized_payload=bundle.incident_evidence,
                source_reference="topology.db:nms_incidents",
                sanitized_command_ref="nms_incidents_store",
                confidence=0.95,
                completeness=EvidenceCompleteness.COMPLETE.value,
                provenance={"reused_from_cache": True, "incident_count": len(bundle.incident_evidence)},
            )
            bundle.records.append(inc_rec)
            bundle.reused_cached_count += 1

        self._finalize_bundle(bundle, curr_ts)
        return bundle

    # ------------------------------------------------------------------
    # Synthetic / Fixture Assembly (Hermetic Testing & Simulation)
    # ------------------------------------------------------------------
    def _assemble_from_synthetic(
        self,
        bundle_id: str,
        correlation_id: str,
        scope: str,
        synthetic_data: Dict[str, Any],
        selected_interfaces: List[str],
        now: float,
    ) -> NetworkEvidenceBundle:
        devices_raw = synthetic_data.get("devices") or {}
        bundle = NetworkEvidenceBundle(
            bundle_id=bundle_id,
            correlation_id=correlation_id,
            assembled_at=now,
            scope=scope,
            selected_devices=list(devices_raw.keys()),
            selected_interfaces=selected_interfaces,
            topology_snapshot_ref=synthetic_data.get("topology_snapshot_ref"),
            route_snapshot_refs=dict(synthetic_data.get("route_snapshot_refs") or {}),
            historical_refs=dict(synthetic_data.get("historical_refs") or {}),
        )

        for dev_id, ddata in devices_raw.items():
            obs_ts = ddata.get("observed_at", now)
            dev_fresh = evaluate_evidence_freshness("device_resources", obs_ts, now)
            dev_info = {
                "device_id": dev_id,
                "display_name": ddata.get("display_name") or dev_id,
                "identity": ddata.get("identity") or ddata.get("display_name") or dev_id,
                "management_ip": ddata.get("management_ip") or "",
                "mac_address": ddata.get("mac_address") or "",
                "model": ddata.get("model") or "CHR",
                "routeros_version": ddata.get("routeros_version") or "7.16",
                "ros_major_version": ddata.get("ros_major_version") or (6 if str(ddata.get("routeros_version", "7")).startswith("6") else 7),
                "device_type": ddata.get("device_type") or "router",
                "is_managed": bool(ddata.get("is_managed", True)),
                "reachability_status": ddata.get("reachability_status") or "UP",
                "monitoring_method": ddata.get("monitoring_method") or "synthetic_fixture",
                "cpu_load_percent": ddata.get("cpu_load_percent"),
                "memory_used_percent": ddata.get("memory_used_percent"),
                "memory_used_bytes": ddata.get("memory_used_bytes"),
                "memory_total_bytes": ddata.get("memory_total_bytes"),
                "storage_used_bytes": ddata.get("storage_used_bytes"),
                "storage_total_bytes": ddata.get("storage_total_bytes"),
                "uptime_seconds": ddata.get("uptime_seconds"),
                "latency_ms": ddata.get("latency_ms"),
                "packet_loss_percent": ddata.get("packet_loss_percent"),
                "last_successful_observation": ddata.get("last_successful_observation", obs_ts),
                "last_check_at": obs_ts,
                "last_error": redact_sensitive_values(str(ddata.get("last_error") or "")),
                "capabilities": dict(ddata.get("capabilities") or {"ssh_registered": True}),
            }
            bundle.device_evidence[dev_id] = dev_info

            if dev_info["reachability_status"] in ("DOWN", "SUSPECTED_DOWN", "UNREACHABLE"):
                bundle.collection_gaps.append(
                    CollectionGapRecord(
                        gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                        device_id=dev_id,
                        evidence_type="reachability",
                        gap_reason="DEVICE_UNREACHABLE",
                        detail=dev_info["last_error"] or f"Device {dev_id} unreachable.",
                        timestamp=now,
                    )
                )

            if ddata.get("telemetry_gap"):
                bundle.collection_gaps.append(
                    CollectionGapRecord(
                        gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                        device_id=dev_id,
                        evidence_type="device_resources",
                        gap_reason="TELEMETRY_GAP",
                        detail=str(ddata.get("telemetry_gap_reason") or "Telemetry collection failed/timed out."),
                        timestamp=now,
                    )
                )
            else:
                bundle.records.append(
                    CanonicalEvidenceRecord(
                        evidence_id=ddata.get("device_evidence_id") or _make_evidence_id("dev", dev_id),
                        device_id=dev_id,
                        device_identity=dev_info["identity"],
                        evidence_type="device_resources",
                        source_subsystem="nms",
                        collection_method=dev_info["monitoring_method"],
                        collected_at=now,
                        observed_at=obs_ts,
                        validity_ttl_sec=get_freshness_ttl_profile("device_resources")[1],
                        freshness=dev_fresh,
                        quality=EvidenceQuality.GOOD.value if dev_info["reachability_status"] == "UP" else EvidenceQuality.PARTIAL.value,
                        normalized_payload=dev_info,
                        source_reference=f"synthetic:{dev_id}:device",
                        sanitized_command_ref="/system resource print",
                        confidence=float(ddata.get("confidence", 0.95)),
                        completeness=EvidenceCompleteness.COMPLETE.value if dev_info["cpu_load_percent"] is not None else EvidenceCompleteness.PARTIAL.value,
                        provenance={"reused_from_cache": True, "synthetic": True},
                    )
                )
                bundle.reused_cached_count += 1

            # Interfaces
            ifaces_in = ddata.get("interfaces") or []
            ifaces_norm: List[Dict[str, Any]] = []
            for idx, iface in enumerate(ifaces_in):
                iname = iface.get("interface_name") or iface.get("name") or f"ether{idx + 1}"
                ifaces_norm.append(
                    {
                        "device_id": dev_id,
                        "interface_name": iname,
                        "interface_type": iface.get("interface_type") or "ether",
                        "oper_status": iface.get("oper_status") or "up",
                        "admin_status": iface.get("admin_status") or "enabled",
                        "mac_address": iface.get("mac_address") or "",
                        "mtu": iface.get("mtu", 1500),
                        "l2mtu": iface.get("l2mtu"),
                        "speed_bps": iface.get("speed_bps"),
                        "duplex": iface.get("duplex") or "full",
                        "rx_bytes": iface.get("rx_bytes"),
                        "tx_bytes": iface.get("tx_bytes"),
                        "rx_rate_bps": iface.get("rx_rate_bps"),  # Preserves None!
                        "tx_rate_bps": iface.get("tx_rate_bps"),  # Preserves None!
                        "rx_utilization_percent": iface.get("rx_utilization_percent"),
                        "tx_utilization_percent": iface.get("tx_utilization_percent"),
                        "in_errors": iface.get("in_errors"),
                        "out_errors": iface.get("out_errors"),
                        "in_drops": iface.get("in_drops"),
                        "out_drops": iface.get("out_drops"),
                        "last_counter_update": iface.get("last_counter_update", obs_ts),
                        "comment": redact_sensitive_values(str(iface.get("comment") or "")),
                    }
                )
            bundle.interface_evidence[dev_id] = ifaces_norm
            if ifaces_norm:
                if_ts = ifaces_norm[0].get("last_counter_update", obs_ts)
                bundle.records.append(
                    CanonicalEvidenceRecord(
                        evidence_id=_make_evidence_id("iface", dev_id),
                        device_id=dev_id,
                        device_identity=dev_info["identity"],
                        evidence_type="interfaces",
                        source_subsystem="nms",
                        collection_method=dev_info["monitoring_method"],
                        collected_at=now,
                        observed_at=if_ts,
                        validity_ttl_sec=get_freshness_ttl_profile("interfaces")[1],
                        freshness=evaluate_evidence_freshness("interfaces", if_ts, now),
                        quality=EvidenceQuality.GOOD.value,
                        normalized_payload=ifaces_norm,
                        source_reference=f"synthetic:{dev_id}:interfaces",
                        sanitized_command_ref="/interface print detail",
                        confidence=0.95,
                        completeness=EvidenceCompleteness.COMPLETE.value,
                        provenance={"reused_from_cache": True, "synthetic": True},
                    )
                )

            # Routes
            routes_in = ddata.get("routes")
            if routes_in is not None:
                norm_routes: List[NormalizedRoute] = []
                for r in routes_in:
                    if isinstance(r, NormalizedRoute):
                        norm_routes.append(r)
                    elif isinstance(r, dict):
                        norm_routes.append(_route_from_dict(dev_id, r))
                bundle.routing_evidence[dev_id] = norm_routes
                r_ts = ddata.get("routes_observed_at", obs_ts)
                bundle.records.append(
                    CanonicalEvidenceRecord(
                        evidence_id=_make_evidence_id("routes", dev_id),
                        device_id=dev_id,
                        device_identity=dev_info["identity"],
                        evidence_type="routes",
                        source_subsystem="routing",
                        collection_method=dev_info["monitoring_method"],
                        collected_at=now,
                        observed_at=r_ts,
                        validity_ttl_sec=get_freshness_ttl_profile("routes")[1],
                        freshness=evaluate_evidence_freshness("routes", r_ts, now),
                        quality=EvidenceQuality.GOOD.value,
                        parser_version="4.6.0",
                        normalized_payload=[nr.to_dict() for nr in norm_routes],
                        source_reference=f"synthetic:{dev_id}:routes",
                        sanitized_command_ref="/ip route print detail",
                        confidence=0.95,
                        completeness=EvidenceCompleteness.COMPLETE.value,
                        provenance={"reused_from_cache": True, "synthetic": True},
                    )
                )
            else:
                bundle.routing_evidence[dev_id] = []
                if ddata.get("missing_route_snapshot"):
                    bundle.collection_gaps.append(
                        CollectionGapRecord(
                            gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                            device_id=dev_id,
                            evidence_type="routes",
                            gap_reason="NOT_COLLECTED",
                            detail="Snapshot/tabel routing tidak tersedia untuk perangkat ini.",
                            timestamp=now,
                        )
                    )

            # Protocol & addressing observations (ip_addresses, vlans, bridges, ospf, bgp, arp, nat, firewall, tunnels, qos, ipv6, forwarding_observations)
            proto_dict: Dict[str, Any] = {}
            for pkey in (
                "ip_addresses",
                "arp",
                "neighbors",
                "bridge",
                "bridge_ports",
                "bridge_vlan",
                "vlans",
                "ospf_instance",
                "ospf_neighbors",
                "ospf_interfaces",
                "bgp_peers",
                "bgp_routes",
                "nat_rules",
                "firewall_filter",
                "qos_queues",
                "tunnels",
                "ipv6_addresses",
                "ipv6_routes",
                "ipv6_neighbors",
                "forwarding_observations",
                "dns",
            ):
                if pkey in ddata and ddata[pkey] is not None:
                    proto_dict[pkey] = ddata[pkey]
                    p_ts = ddata.get(f"{pkey}_observed_at", obs_ts)
                    bundle.records.append(
                        CanonicalEvidenceRecord(
                            evidence_id=_make_evidence_id(pkey[:10], dev_id),
                            device_id=dev_id,
                            device_identity=dev_info["identity"],
                            evidence_type=pkey,
                            source_subsystem="protocol",
                            collection_method=dev_info["monitoring_method"],
                            collected_at=now,
                            observed_at=p_ts,
                            validity_ttl_sec=get_freshness_ttl_profile(pkey)[1],
                            freshness=evaluate_evidence_freshness(pkey, p_ts, now),
                            quality=EvidenceQuality.GOOD.value,
                            normalized_payload=ddata[pkey],
                            source_reference=f"synthetic:{dev_id}:{pkey}",
                            sanitized_command_ref=COMMAND_MAP_V7.get(pkey, pkey),
                            confidence=0.93,
                            completeness=EvidenceCompleteness.COMPLETE.value,
                            provenance={"reused_from_cache": True, "synthetic": True},
                        )
                    )
            bundle.protocol_evidence[dev_id] = proto_dict

        # Topology edges
        for edge in synthetic_data.get("topology_edges") or []:
            e_ts = edge.get("observed_at", now)
            ecopy = dict(edge)
            ecopy["freshness"] = evaluate_evidence_freshness("topology_edges", e_ts, now)
            bundle.topology_evidence.append(ecopy)
        if bundle.topology_evidence:
            e_ts0 = bundle.topology_evidence[0].get("observed_at", now)
            bundle.records.append(
                CanonicalEvidenceRecord(
                    evidence_id=_make_evidence_id("topo", "fabric"),
                    device_id="network",
                    device_identity="TopologyEngine",
                    evidence_type="topology_edges",
                    source_subsystem="topology",
                    collection_method="synthetic_fixture",
                    collected_at=now,
                    observed_at=e_ts0,
                    validity_ttl_sec=get_freshness_ttl_profile("topology_edges")[1],
                    freshness=evaluate_evidence_freshness("topology_edges", e_ts0, now),
                    quality=EvidenceQuality.GOOD.value,
                    normalized_payload=bundle.topology_evidence,
                    source_reference="synthetic:topology_edges",
                    sanitized_command_ref="topology_edges",
                    confidence=0.92,
                    completeness=EvidenceCompleteness.COMPLETE.value,
                    provenance={"synthetic": True},
                )
            )

        # Incidents
        for inc in synthetic_data.get("incidents") or []:
            bundle.incident_evidence.append(dict(inc))
        if bundle.incident_evidence:
            inc_ts = max((float(i.get("started_at") or now) for i in bundle.incident_evidence), default=now)
            bundle.records.append(
                CanonicalEvidenceRecord(
                    evidence_id=_make_evidence_id("inc", "nms"),
                    device_id="network",
                    device_identity="NmsIncidentStore",
                    evidence_type="nms_incidents",
                    source_subsystem="nms",
                    collection_method="synthetic_fixture",
                    collected_at=now,
                    observed_at=inc_ts,
                    validity_ttl_sec=get_freshness_ttl_profile("nms_incidents")[1],
                    freshness=evaluate_evidence_freshness("nms_incidents", inc_ts, now),
                    quality=EvidenceQuality.GOOD.value,
                    normalized_payload=bundle.incident_evidence,
                    source_reference="synthetic:incidents",
                    sanitized_command_ref="nms_incidents",
                    confidence=0.95,
                    completeness=EvidenceCompleteness.COMPLETE.value,
                    provenance={"synthetic": True},
                )
            )

        return bundle

    # ------------------------------------------------------------------
    # Internal Helpers: DB Readers, Selective SSH, Contradictions & Summary
    # ------------------------------------------------------------------
    def _resolve_device_map(self, target_devices: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        try:
            canon_list: List[CanonicalDevice] = self.registry.list_devices(force_refresh=False)
        except Exception:
            canon_list = []

        by_key: Dict[str, CanonicalDevice] = {}
        for cd in canon_list:
            by_key[cd.device_id] = cd
            if cd.inventory_name:
                by_key[cd.inventory_name] = cd
            if cd.management_ip:
                by_key[cd.management_ip] = cd
            if getattr(cd, "topology_node_id", None):
                by_key[cd.topology_node_id] = cd

        if target_devices:
            for q in target_devices:
                q_str = str(q or "").strip()
                if not q_str:
                    continue
                cd = by_key.get(q_str) or self.registry.resolve_device(q_str)
                if cd:
                    did = getattr(cd, "topology_node_id", None) or cd.device_id
                    result[did] = {
                        "device_id": did,
                        "canonical_id": cd.device_id,
                        "display_name": cd.display_name,
                        "identity": cd.observed_identity or cd.hostname or "",
                        "management_ip": cd.management_ip or "",
                        "mac_address": cd.primary_mac or "",
                        "model": cd.model or "",
                        "os_version": cd.os_version or "",
                        "ros_major_version": cd.ros_major_version,
                        "device_type": getattr(cd, "device_role", getattr(cd, "role", "router")) or "router",
                        "is_managed": cd.is_managed,
                    }
                else:
                    result[q_str] = {
                        "device_id": q_str,
                        "canonical_id": q_str,
                        "display_name": q_str,
                        "identity": "",
                        "management_ip": "",
                        "mac_address": "",
                        "model": "",
                        "os_version": "",
                        "ros_major_version": None,
                        "device_type": "router",
                        "is_managed": False,
                    }
        else:
            for cd in canon_list:
                did = getattr(cd, "topology_node_id", None) or cd.device_id
                result[did] = {
                    "device_id": did,
                    "canonical_id": cd.device_id,
                    "display_name": cd.display_name,
                    "identity": cd.observed_identity or cd.hostname or "",
                    "management_ip": cd.management_ip or "",
                    "mac_address": cd.primary_mac or "",
                    "model": cd.model or "",
                    "os_version": cd.os_version or "",
                    "ros_major_version": cd.ros_major_version,
                    "device_type": getattr(cd, "device_role", getattr(cd, "role", "router")) or "router",
                    "is_managed": cd.is_managed,
                }

        # Supplement with topology_nodes if db exists
        if self.db_path.exists():
            try:
                with closing(get_topology_connection(self.db_path, timeout=10.0)) as conn:
                    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                    if "topology_nodes" in tables:
                        rows = conn.execute("SELECT * FROM topology_nodes").fetchall()
                        for r in rows:
                            nid = r["id"]
                            if target_devices and nid not in result and (r["name"] not in target_devices) and (r["ip"] not in target_devices):
                                continue
                            if nid not in result:
                                result[nid] = {
                                    "device_id": nid,
                                    "canonical_id": nid,
                                    "display_name": r["name"] or nid,
                                    "identity": r["identity"] or "",
                                    "management_ip": r["ip"] or "",
                                    "mac_address": r["mac"] or "",
                                    "model": "",
                                    "os_version": "",
                                    "ros_major_version": None,
                                    "device_type": r["device_type"] or "router",
                                    "is_managed": (r["ownership_status"] == "verified_owned"),
                                }
            except Exception as exc:
                logger.debug("Topology node supplement skipped: %s", exc)

        return result

    def _read_topology_and_nms_db(self, device_ids: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "profiles": {},
            "latest_device_metrics": {},
            "latest_iface_metrics": {},
            "topology_edges": [],
            "incidents": [],
            "latest_topology_snapshot_id": None,
            "topology_snapshot_count": 0,
            "latest_route_snapshot_ids": {},
            "latest_route_snapshot_payloads": {},
        }
        if not self.db_path.exists():
            return out

        dev_set = set(device_ids)
        try:
            with closing(get_topology_connection(self.db_path, timeout=10.0)) as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

                if "nms_device_profiles" in tables:
                    for r in conn.execute("SELECT * FROM nms_device_profiles").fetchall():
                        did = r["device_id"]
                        if not dev_set or did in dev_set:
                            out["profiles"][did] = dict(r)

                if "nms_device_metrics" in tables:
                    rows = conn.execute(
                        """
                        SELECT m1.*
                        FROM nms_device_metrics m1
                        INNER JOIN (
                            SELECT device_id, MAX(timestamp) AS max_ts
                            FROM nms_device_metrics
                            GROUP BY device_id
                        ) m2 ON m1.device_id = m2.device_id AND m1.timestamp = m2.max_ts
                        """
                    ).fetchall()
                    for r in rows:
                        did = r["device_id"]
                        if not dev_set or did in dev_set:
                            out["latest_device_metrics"][did] = dict(r)

                if "nms_interface_metrics" in tables:
                    rows = conn.execute(
                        """
                        SELECT m1.*
                        FROM nms_interface_metrics m1
                        INNER JOIN (
                            SELECT device_id, interface_name, MAX(timestamp) AS max_ts
                            FROM nms_interface_metrics
                            GROUP BY device_id, interface_name
                        ) m2 ON m1.device_id = m2.device_id
                            AND m1.interface_name = m2.interface_name
                            AND m1.timestamp = m2.max_ts
                        """
                    ).fetchall()
                    for r in rows:
                        did = r["device_id"]
                        if not dev_set or did in dev_set:
                            out["latest_iface_metrics"].setdefault(did, []).append(dict(r))

                if "topology_edges" in tables:
                    for r in conn.execute("SELECT * FROM topology_edges WHERE lifecycle_state != 'EXPIRED'").fetchall():
                        d = dict(r)
                        if not dev_set or d.get("source_node_id") in dev_set or d.get("target_node_id") in dev_set:
                            out["topology_edges"].append(d)
                elif "topology_links" in tables:
                    for r in conn.execute("SELECT * FROM topology_links").fetchall():
                        d = dict(r)
                        if not dev_set or d.get("source_id") in dev_set or d.get("target_id") in dev_set:
                            out["topology_edges"].append(d)

                if "nms_incidents" in tables:
                    for r in conn.execute("SELECT * FROM nms_incidents ORDER BY started_at DESC LIMIT 100").fetchall():
                        d = dict(r)
                        if not dev_set or d.get("device_id") in dev_set:
                            out["incidents"].append(d)

                if "topology_snapshots" in tables:
                    cnt_row = conn.execute("SELECT COUNT(*) AS c FROM topology_snapshots").fetchone()
                    out["topology_snapshot_count"] = int(cnt_row["c"]) if cnt_row else 0
                    snap_row = conn.execute("SELECT snapshot_id FROM topology_snapshots ORDER BY created_at DESC LIMIT 1").fetchone()
                    if snap_row:
                        out["latest_topology_snapshot_id"] = snap_row["snapshot_id"]

                if "route_snapshots" in tables:
                    rs_rows = conn.execute(
                        """
                        SELECT rs1.*
                        FROM route_snapshots rs1
                        INNER JOIN (
                            SELECT device_id, MAX(collected_at) AS max_ts
                            FROM route_snapshots
                            GROUP BY device_id
                        ) rs2 ON rs1.device_id = rs2.device_id AND rs1.collected_at = rs2.max_ts
                        """
                    ).fetchall()
                    for r in rs_rows:
                        did = r["device_id"]
                        if not dev_set or did in dev_set:
                            out["latest_route_snapshot_ids"][did] = r["snapshot_id"]
                            try:
                                routes_json = json.loads(r["routes_json"] or "[]")
                            except Exception:
                                routes_json = []
                            out["latest_route_snapshot_payloads"][did] = {
                                "snapshot_id": r["snapshot_id"],
                                "created_at": float(r["collected_at"]),
                                "completeness": r["completeness"] or "COMPLETE",
                                "routes": routes_json,
                            }
        except sqlite3.Error as exc:
            logger.warning("SQLite read warning in UnifiedEvidenceService: %s", exc)

        return out

    def _get_cached_cli_record(self, device_id: str, obs_type: str, now: float) -> Optional[CanonicalEvidenceRecord]:
        with self._lock:
            rec = self._cli_cache.get((device_id, obs_type))
        if rec is None:
            return None
        ts = rec.observed_at if rec.observed_at is not None else rec.collected_at
        fresh = evaluate_evidence_freshness(obs_type, ts, now)
        rec.freshness = fresh
        if fresh in (IntelligenceFreshness.FRESH.value, IntelligenceFreshness.AGING.value):
            return rec
        return None

    def _collect_selective_ssh(
        self,
        bundle: NetworkEvidenceBundle,
        devices_needing_ssh: Dict[str, List[str]],
        now: float,
    ) -> None:
        # Group by union of requested types to run bounded multi-device collection once
        all_types: List[str] = sorted({t for tlist in devices_needing_ssh.values() for t in tlist})
        targets = list(devices_needing_ssh.keys())
        if not targets or not all_types:
            return

        mbundle = self.ssh_orchestrator.collect_multi_device_bundle(
            targets=targets,
            required_types=all_types,
            max_concurrency=min(3, len(targets)),
            timeout_per_cmd=6.0,
        )
        # Ingest any collected routes into MultiDeviceRouteCollector
        try:
            ingested = self.route_collector.ingest_multi_device_evidence_bundle(mbundle)
            for did, rres in ingested.items():
                bundle.routing_evidence[did] = list(rres.routes)
        except Exception as exc:
            logger.debug("Route ingestion from live SSH bundle skipped: %s", exc)

        for dev_id, dbun in mbundle.device_bundles.items():
            for item in dbun.get("evidence_items", []):
                obs_type = item.observation_type
                if item.collection_status == "SUCCESS":
                    rec = CanonicalEvidenceRecord(
                        evidence_id=item.evidence_id,
                        device_id=dev_id,
                        device_identity=item.device_identity,
                        evidence_type=obs_type,
                        source_subsystem="ssh_cli",
                        collection_method="routeros_ssh_readonly",
                        collected_at=item.collection_timestamp,
                        observed_at=item.collection_timestamp,
                        validity_ttl_sec=get_freshness_ttl_profile(obs_type)[1],
                        freshness=evaluate_evidence_freshness(obs_type, item.collection_timestamp, now),
                        quality=EvidenceQuality.GOOD.value,
                        parser_version="6.1.0",
                        normalized_payload=item.normalized_value,
                        source_reference=mbundle.bundle_id,
                        sanitized_command_ref=item.source_command,
                        confidence=0.95,
                        completeness=EvidenceCompleteness.COMPLETE.value,
                        provenance={"reused_from_cache": False, "bundle_id": mbundle.bundle_id},
                    )
                    bundle.records.append(rec)
                    bundle.live_collected_count += 1
                    bundle.protocol_evidence.setdefault(dev_id, {})[obs_type] = item.normalized_value
                    with self._lock:
                        self._cli_cache[(dev_id, obs_type)] = rec
                        self._cli_cache.move_to_end((dev_id, obs_type))
                        while len(self._cli_cache) > 400:
                            self._cli_cache.popitem(last=False)
                else:
                    bundle.collection_gaps.append(
                        CollectionGapRecord(
                            gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                            device_id=dev_id,
                            evidence_type=obs_type,
                            gap_reason="TELEMETRY_GAP",
                            detail=redact_sensitive_values(item.limitations or "Gagal mengumpulkan observasi CLI."),
                            timestamp=now,
                        )
                    )

    def _finalize_bundle(self, bundle: NetworkEvidenceBundle, now: float) -> None:
        # 1. Detect cross-source & cross-device contradictions
        self._detect_contradictions(bundle)

        # 2. Index every evidence record & compute freshness/completeness summaries
        fresh_counts: Dict[str, int] = {
            IntelligenceFreshness.FRESH.value: 0,
            IntelligenceFreshness.AGING.value: 0,
            IntelligenceFreshness.STALE.value: 0,
            IntelligenceFreshness.EXPIRED.value: 0,
            IntelligenceFreshness.UNKNOWN.value: 0,
        }
        for rec in bundle.records:
            ts = rec.observed_at if rec.observed_at is not None else rec.collected_at
            rec.freshness = evaluate_evidence_freshness(rec.evidence_type, ts, now)
            fresh_counts[rec.freshness] = fresh_counts.get(rec.freshness, 0) + 1
            self._index_record(rec)

        bundle.freshness_summary = fresh_counts

        total_devs = len(bundle.selected_devices)
        reachable_devs = sum(
            1
            for d in bundle.device_evidence.values()
            if d.get("reachability_status") in ("UP", "DEGRADED")
        )
        overall_comp = (
            EvidenceCompleteness.EMPTY.value
            if not bundle.records
            else (
                EvidenceCompleteness.COMPLETE.value
                if not bundle.collection_gaps and reachable_devs == total_devs
                else EvidenceCompleteness.PARTIAL.value
            )
        )
        bundle.completeness_summary = {
            "overall": overall_comp,
            "selected_device_count": total_devs,
            "reachable_device_count": reachable_devs,
            "record_count": len(bundle.records),
            "gap_count": len(bundle.collection_gaps),
            "contradiction_count": len(bundle.contradictions),
        }

        with self._lock:
            self._bundle_cache[bundle.bundle_id] = bundle
            self._bundle_cache.move_to_end(bundle.bundle_id)
            while len(self._bundle_cache) > self._max_cached_bundles:
                self._bundle_cache.popitem(last=False)

    def _detect_contradictions(self, bundle: NetworkEvidenceBundle) -> None:
        # A. ICMP UP vs Management Unavailable
        for dev_id, dinfo in bundle.device_evidence.items():
            if dinfo.get("reachability_status") == "MONITORING_UNAVAILABLE":
                bundle.contradictions.append(
                    EvidenceContradiction(
                        contradiction_id=f"contra_{uuid.uuid4().hex[:8]}",
                        contradiction_type="REACHABLE_BUT_MANAGEMENT_FAILED",
                        description=f"Perangkat {dev_id} merespons probe ICMP tetapi sesi manajemen (SSH/SNMP) gagal.",
                        involved_devices=[dev_id],
                        severity="warning",
                    )
                )

        # B. Duplicate IPv4/IPv6 addresses across distinct devices
        ip_owners: Dict[str, List[str]] = {}
        for dev_id, dinfo in bundle.device_evidence.items():
            mip = str(dinfo.get("management_ip") or "").strip()
            if mip:
                ip_owners.setdefault(mip, []).append(dev_id)
        for dev_id, pdata in bundle.protocol_evidence.items():
            for ip_entry in pdata.get("ip_addresses") or []:
                if isinstance(ip_entry, dict) and not ip_entry.get("disabled") and not ip_entry.get("is_disabled"):
                    addr = str(ip_entry.get("address") or "").split("/")[0].strip()
                    if addr and dev_id not in ip_owners.get(addr, []):
                        ip_owners.setdefault(addr, []).append(dev_id)

        for ip_addr, owners in ip_owners.items():
            unique_owners = sorted(set(owners))
            if len(unique_owners) > 1:
                bundle.contradictions.append(
                    EvidenceContradiction(
                        contradiction_id=f"contra_{uuid.uuid4().hex[:8]}",
                        contradiction_type="DUPLICATE_IP_OBSERVED",
                        description=f"Alamat IP {ip_addr} teramati pada lebih dari satu perangkat: {', '.join(unique_owners)}.",
                        involved_devices=unique_owners,
                        severity="critical",
                    )
                )

        # C. Topology active link vs interface oper_status down
        iface_oper_lookup: Dict[Tuple[str, str], str] = {}
        for dev_id, iflist in bundle.interface_evidence.items():
            for iface in iflist:
                iface_oper_lookup[(dev_id, str(iface.get("interface_name") or ""))] = str(
                    iface.get("oper_status") or "unknown"
                ).lower()

        for edge in bundle.topology_evidence:
            src_dev = edge.get("source_node_id") or edge.get("source_id") or ""
            dst_dev = edge.get("target_node_id") or edge.get("target_id") or ""
            src_if = edge.get("source_interface") or edge.get("local_interface_id") or ""
            dst_if = edge.get("target_interface") or edge.get("remote_interface_id") or ""
            lstate = str(edge.get("lifecycle_state") or edge.get("oper_status") or "ACTIVE").upper()
            if lstate in ("ACTIVE", "UP"):
                src_st = iface_oper_lookup.get((src_dev, src_if))
                dst_st = iface_oper_lookup.get((dst_dev, dst_if))
                if src_st in ("down", "disabled") or dst_st in ("down", "disabled"):
                    bundle.contradictions.append(
                        EvidenceContradiction(
                            contradiction_id=f"contra_{uuid.uuid4().hex[:8]}",
                            contradiction_type="TOPOLOGY_EDGE_INTERFACE_STATE_MISMATCH",
                            description=(
                                f"Relasi topologi {src_dev}:{src_if} <-> {dst_dev}:{dst_if} tercatat aktif, "
                                f"namun status antarmuka lokal/peer adalah ({src_st or 'unknown'} / {dst_st or 'unknown'})."
                            ),
                            involved_devices=[d for d in (src_dev, dst_dev) if d],
                            severity="warning",
                        )
                    )


_evidence_service_singleton: Optional[UnifiedEvidenceService] = None
_evidence_service_lock = threading.Lock()


def get_unified_evidence_service() -> UnifiedEvidenceService:
    global _evidence_service_singleton
    if _evidence_service_singleton is None:
        with _evidence_service_lock:
            if _evidence_service_singleton is None:
                _evidence_service_singleton = UnifiedEvidenceService()
    return _evidence_service_singleton
