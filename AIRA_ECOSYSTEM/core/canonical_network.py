"""
core/canonical_network.py — Canonical Network State & Unified Device Identity for AIRA OS.

Provides a single source of truth for device identity, observed hardware facts,
configuration metadata, and health state across Inventory, NMS, Topology, and AKANE.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.topology_models import (
    compute_observation_freshness,
    normalize_ip,
    normalize_mac,
    sanitize_untrusted_text,
)

logger = logging.getLogger("aira.canonical_network")


@dataclass
class CanonicalDevice:
    """
    Unified Device Identity representation across AIRA OS.
    Preserves separation between user-configured identity and observed telemetry.
    """
    device_id: str
    inventory_name: str = ""
    observed_identity: str = ""
    management_ip: str = ""
    management_port: int = 22
    all_ips: List[str] = field(default_factory=list)
    primary_mac: str = ""
    all_macs: List[str] = field(default_factory=list)
    device_type: str = "mikrotik"
    vendor: str = "MikroTik"
    model: str = ""
    os_version: str = ""
    ros_major_version: Optional[int] = None
    serial_number: str = ""
    reachability_status: str = "unknown"
    management_status: str = "not_attempted"
    nms_status: str = "UNKNOWN"
    observation_freshness: str = "unknown"
    first_seen: Optional[float] = None
    last_seen: Optional[float] = None
    last_verified: Optional[float] = None
    is_managed: bool = True
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """
        User-facing label precedence:
        1. User override name/label (if set)
        2. Inventory configured name (e.g. 'R1')
        3. Observed RouterOS system identity (e.g. 'MikroTik-Core')
        4. Management IP or fallback
        """
        if self.user_overrides.get("custom_name"):
            return str(self.user_overrides["custom_name"])
        if self.inventory_name:
            return self.inventory_name
        if self.observed_identity:
            return self.observed_identity
        return self.management_ip or self.device_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "inventory_name": self.inventory_name,
            "observed_identity": self.observed_identity,
            "management_ip": self.management_ip,
            "management_port": self.management_port,
            "all_ips": list(self.all_ips),
            "primary_mac": self.primary_mac,
            "all_macs": list(self.all_macs),
            "device_type": self.device_type,
            "vendor": self.vendor,
            "model": self.model,
            "os_version": self.os_version,
            "ros_major_version": self.ros_major_version,
            "serial_number": self.serial_number,
            "reachability_status": self.reachability_status,
            "management_status": self.management_status,
            "nms_status": self.nms_status,
            "observation_freshness": self.observation_freshness,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "last_verified": self.last_verified,
            "is_managed": self.is_managed,
            "user_overrides": self.user_overrides,
        }


def parse_routeros_major_version(version_str: Optional[str]) -> Optional[int]:
    """Detects RouterOS v6 vs v7 from version strings like '6.49.10', 'v7.12', or '7.14.3 (stable)'."""
    if not version_str:
        return None
    m = re.search(r"(?:^|[^\d])v?([67])\.\d+", str(version_str), re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


class CanonicalNetworkRegistry:
    """
    Registry for resolving and aggregating canonical device state.
    Queries Inventory, Topology, and NMS caches without destructive side effects.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._cache: Dict[str, CanonicalDevice] = {}
        self._last_refresh: float = 0.0
        self._cache_ttl_sec: float = 5.0

    def resolve_device(self, query: str) -> Optional[CanonicalDevice]:
        """
        Resolves a single device by ID, inventory name, identity, management IP, or MAC.
        Safe against partial matches or conflicting targets.
        """
        if not query:
            return None

        clean_query = str(query).strip()
        devices = self.list_devices()

        # 1. Exact device_id match
        for dev in devices:
            if dev.device_id.lower() == clean_query.lower():
                return dev

        # 2. Exact inventory_name match
        for dev in devices:
            if dev.inventory_name and dev.inventory_name.lower() == clean_query.lower():
                return dev

        # 3. Exact observed_identity match
        for dev in devices:
            if dev.observed_identity and dev.observed_identity.lower() == clean_query.lower():
                return dev

        # 4. IP match (management IP first, then all_ips)
        norm_ip = normalize_ip(clean_query)
        if norm_ip:
            for dev in devices:
                if dev.management_ip == norm_ip:
                    return dev
            for dev in devices:
                if norm_ip in dev.all_ips:
                    return dev

        # 5. MAC match
        norm_mac = normalize_mac(clean_query)
        if norm_mac:
            for dev in devices:
                if dev.primary_mac == norm_mac or norm_mac in dev.all_macs:
                    return dev

        return None

    def list_devices(self, force_refresh: bool = False) -> List[CanonicalDevice]:
        """
        Aggregates devices from Inventory, Topology, and NMS.
        Enforces conservative merging:
        - Inventory entries are authoritative anchors.
        - Topology provides observed hardware, version, MACs, and discovered neighbors.
        - NMS provides live health, reachability, and metric counters.
        - Never merges devices with different non-empty hostnames or conflicting MACs.
        """
        now = time.time()
        with self._lock:
            if not force_refresh and (now - self._last_refresh) < self._cache_ttl_sec and self._cache:
                return list(self._cache.values())

            merged: Dict[str, CanonicalDevice] = {}

            # Step 1: Ingest Inventory Store devices
            inv_devs = self._fetch_inventory_devices()
            for inv in inv_devs:
                name = str(inv.get("name") or "").strip()
                host = normalize_ip(inv.get("host")) or str(inv.get("host") or "").strip()
                dev_id = f"dev_{name.lower()}"
                port = int(inv.get("port") or 22)
                dtype = str(inv.get("device_type") or "mikrotik").lower()

                dev = CanonicalDevice(
                    device_id=dev_id,
                    inventory_name=name,
                    management_ip=host,
                    management_port=port,
                    device_type=dtype,
                    is_managed=bool(inv.get("enabled", 1)),
                    first_seen=float(inv.get("created_at") or now),
                    last_seen=float(inv.get("updated_at") or now),
                )
                merged[dev_id] = dev

            # Step 2: Correlate and enrich from Topology Engine
            topo_nodes = self._fetch_topology_nodes()
            for node in topo_nodes:
                matched_id = self._match_topology_node(node, merged)
                if matched_id:
                    dev = merged[matched_id]
                    self._enrich_device_with_topology(dev, node)
                else:
                    # Discovered non-inventory node (e.g. neighbor, switch, printer)
                    node_id = str(node.get("id") or f"topo_{len(merged)+1}")
                    new_dev = self._create_device_from_topology(node_id, node)
                    merged[node_id] = new_dev

            # Step 3: Correlate and enrich from NMS Engine
            nms_statuses = self._fetch_nms_statuses()
            for dev in merged.values():
                nms_info = nms_statuses.get(dev.inventory_name.lower()) or nms_statuses.get(dev.management_ip)
                if nms_info:
                    dev.nms_status = nms_info.get("status", "UNKNOWN")
                    if nms_info.get("last_check_at"):
                        dev.last_verified = float(nms_info["last_check_at"])

            self._cache = merged
            self._last_refresh = now
            return list(merged.values())

    def _match_topology_node(self, node: Dict[str, Any], current_devices: Dict[str, CanonicalDevice]) -> Optional[str]:
        """
        Conservative matching:
        Matches topology node to an existing inventory device only if:
        1. Exact inventory name matches, OR
        2. Exact management IP matches, OR
        3. Primary MAC matches.
        Refuses to match if hostnames conflict.
        """
        node_id = str(node.get("id") or "").lower()
        node_name = str(node.get("name") or "").strip().lower()
        node_ip = normalize_ip(node.get("ip"))
        node_mac = normalize_mac(node.get("mac"))
        node_ident = str(node.get("identity") or "").strip().lower()

        # Check by device_id or inventory name
        for dev_id, dev in current_devices.items():
            if dev_id == node_id or (dev.inventory_name and dev.inventory_name.lower() == node_name):
                return dev_id

        # Check by IP
        if node_ip:
            for dev_id, dev in current_devices.items():
                if dev.management_ip == node_ip:
                    # Prevent merging if both have distinct, incompatible identities
                    if dev.observed_identity and node_ident and dev.observed_identity.lower() != node_ident:
                        continue
                    return dev_id

        # Check by MAC
        if node_mac:
            for dev_id, dev in current_devices.items():
                if dev.primary_mac == node_mac or node_mac in dev.all_macs:
                    return dev_id

        return None

    def _enrich_device_with_topology(self, dev: CanonicalDevice, node: Dict[str, Any]) -> None:
        """Enriches an inventory device with observed live topology facts."""
        ident = sanitize_untrusted_text(node.get("identity") or "")
        if ident and not dev.observed_identity:
            dev.observed_identity = ident

        if not dev.primary_mac:
            dev.primary_mac = normalize_mac(node.get("mac"))

        all_macs = set(dev.all_macs)
        for m in node.get("all_macs_json") or []:
            norm = normalize_mac(m)
            if norm:
                all_macs.add(norm)
        dev.all_macs = sorted(all_macs)

        all_ips = set(dev.all_ips)
        for ip in node.get("all_ips_json") or []:
            norm = normalize_ip(ip)
            if norm:
                all_ips.add(norm)
        if dev.management_ip:
            all_ips.add(dev.management_ip)
        dev.all_ips = sorted(all_ips)

        meta = node.get("metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        if not dev.vendor and node.get("vendor"):
            dev.vendor = sanitize_untrusted_text(node["vendor"])
        if not dev.model and (node.get("model") or meta.get("board")):
            dev.model = sanitize_untrusted_text(node.get("model") or meta.get("board"))
        if not dev.os_version and meta.get("version"):
            dev.os_version = sanitize_untrusted_text(meta["version"])
            dev.ros_major_version = parse_routeros_major_version(dev.os_version)
        if not dev.serial_number and node.get("serial_number"):
            dev.serial_number = sanitize_untrusted_text(node["serial_number"])

        dev.reachability_status = str(node.get("reachability_status") or dev.reachability_status)
        dev.management_status = str(node.get("management_status") or dev.management_status)
        dev.observation_freshness = str(node.get("observation_freshness") or dev.observation_freshness)

        if node.get("last_seen"):
            dev.last_seen = max(dev.last_seen or 0.0, float(node["last_seen"]))
        if node.get("last_verified"):
            dev.last_verified = max(dev.last_verified or 0.0, float(node["last_verified"]))

        overrides = node.get("user_overrides_json")
        if isinstance(overrides, dict):
            dev.user_overrides.update(overrides)

    def _create_device_from_topology(self, node_id: str, node: Dict[str, Any]) -> CanonicalDevice:
        """Constructs a CanonicalDevice for a discovered topology node."""
        name = sanitize_untrusted_text(node.get("name") or node.get("identity") or node_id)
        ident = sanitize_untrusted_text(node.get("identity") or "")
        ip = normalize_ip(node.get("ip"))
        mac = normalize_mac(node.get("mac"))
        dtype = str(node.get("device_type") or "generic").lower()
        vendor = sanitize_untrusted_text(node.get("vendor") or "Unknown")
        model = sanitize_untrusted_text(node.get("model") or "")

        all_ips = [ip] if ip else []
        for extra_ip in node.get("all_ips_json") or []:
            norm = normalize_ip(extra_ip)
            if norm and norm not in all_ips:
                all_ips.append(norm)

        all_macs = [mac] if mac else []
        for extra_mac in node.get("all_macs_json") or []:
            norm = normalize_mac(extra_mac)
            if norm and norm not in all_macs:
                all_macs.append(norm)

        meta = node.get("metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        os_ver = sanitize_untrusted_text(meta.get("version") or "")

        return CanonicalDevice(
            device_id=node_id,
            inventory_name="",
            observed_identity=ident or name,
            management_ip=ip,
            all_ips=all_ips,
            primary_mac=mac,
            all_macs=all_macs,
            device_type=dtype,
            vendor=vendor,
            model=model or meta.get("board", ""),
            os_version=os_ver,
            ros_major_version=parse_routeros_major_version(os_ver),
            serial_number=sanitize_untrusted_text(node.get("serial_number") or ""),
            reachability_status=str(node.get("reachability_status") or "unknown"),
            management_status=str(node.get("management_status") or "not_attempted"),
            nms_status="UNKNOWN",
            observation_freshness=str(node.get("observation_freshness") or "unknown"),
            first_seen=float(node.get("first_seen") or time.time()),
            last_seen=float(node.get("last_seen") or time.time()),
            last_verified=float(node.get("last_verified") or 0.0) if node.get("last_verified") else None,
            is_managed=False,
            user_overrides=node.get("user_overrides_json") if isinstance(node.get("user_overrides_json"), dict) else {},
            raw_metadata=meta,
        )

    def _fetch_inventory_devices(self) -> List[Dict[str, Any]]:
        try:
            from core.inventory_store import get_inventory_store
            res = get_inventory_store().list_devices(enabled_only=False)
            return res.get("devices", []) if res.get("success") else []
        except Exception as exc:
            logger.debug("Failed to read inventory devices: %s", exc)
            return []

    def _fetch_topology_nodes(self) -> List[Dict[str, Any]]:
        try:
            from core.topology_engine import get_topology_engine
            res = get_topology_engine().get_topology()
            return res.get("nodes", []) if isinstance(res, dict) else []
        except Exception as exc:
            logger.debug("Failed to read topology nodes: %s", exc)
            return []

    def _fetch_nms_statuses(self) -> Dict[str, Dict[str, Any]]:
        try:
            from core.nms_engine import get_nms_engine
            engine = get_nms_engine()
            res = engine.get_overview()
            status_map = {}
            for dev in res.get("devices", []):
                name = str(dev.get("name") or "").lower()
                ip = str(dev.get("host") or "").strip()
                if name:
                    status_map[name] = dev
                if ip:
                    status_map[ip] = dev
            return status_map
        except Exception as exc:
            logger.debug("Failed to read NMS statuses: %s", exc)
            return {}


_canonical_registry_singleton: Optional[CanonicalNetworkRegistry] = None
_canonical_registry_lock = threading.Lock()


def get_canonical_registry() -> CanonicalNetworkRegistry:
    global _canonical_registry_singleton
    if _canonical_registry_singleton is None:
        with _canonical_registry_lock:
            if _canonical_registry_singleton is None:
                _canonical_registry_singleton = CanonicalNetworkRegistry()
    return _canonical_registry_singleton
