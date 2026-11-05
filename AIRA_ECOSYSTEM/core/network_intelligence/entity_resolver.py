"""
AIRA OS — Conservative Multi-Attribute Network Entity Resolver (Networking VI / WP 6.2).

Resolves device, interface, IP, MAC, and peer observations into canonical entity identities
with explicit provenance and confidence.

Non-Negotiable Epistemic Rules:
- NEVER merge two devices merely because they share an IP address (e.g., default 192.168.88.1,
  VRRP virtual IP, overlapping VRF subnets, or duplicate IP misconfiguration).
- NEVER merge two devices merely because they share a hostname / RouterOS identity
  (e.g., default "MikroTik" or unconfigured branch routers).
- Reused interface names ("ether1", "bridge1", "vlan10") are always scoped to their owning
  `device_id` (`iface:<device_id>:<interface_name>`).
- Unmanaged or partially observed neighbors are preserved honestly as external/partial entities
  rather than dropped or merged into arbitrary managed routers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.topology_models import normalize_ip, normalize_mac

GENERIC_DEFAULT_HOSTNAMES: Set[str] = {
    "mikrotik",
    "routeros",
    "router",
    "switch",
    "chr",
    "localhost",
    "unknown",
    "",
}


@dataclass
class ResolvedDeviceIdentity:
    canonical_device_id: str
    display_name: str
    routeros_identity: str
    hostname: str
    management_ip: str
    known_ips: List[str] = field(default_factory=list)
    known_macs: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    is_managed: bool = False
    is_partial: bool = False
    identity_confidence: float = 0.90
    provenance: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_device_id": self.canonical_device_id,
            "display_name": self.display_name,
            "routeros_identity": self.routeros_identity,
            "hostname": self.hostname,
            "management_ip": self.management_ip,
            "known_ips": list(self.known_ips),
            "known_macs": list(self.known_macs),
            "interfaces": list(self.interfaces),
            "is_managed": self.is_managed,
            "is_partial": self.is_partial,
            "identity_confidence": round(float(self.identity_confidence), 4),
            "provenance": list(self.provenance),
            "conflicts": list(self.conflicts),
        }


@dataclass
class MergeEvaluation:
    should_merge: bool
    confidence: float
    reason: str
    conflict_detected: bool = False


class EntityResolver:
    """
    Confidence-scored entity resolver over `NetworkEvidenceBundle`.
    Maintains authoritative lookup tables for devices, interfaces, MACs, and IPs,
    preserving ambiguities instead of silently collapsing distinct devices.
    """

    def __init__(self) -> None:
        self.devices: Dict[str, ResolvedDeviceIdentity] = {}
        self.mac_to_devices: Dict[str, List[str]] = {}
        self.ip_to_devices: Dict[str, List[str]] = {}
        self.identity_to_devices: Dict[str, List[str]] = {}
        self.identity_conflicts: List[Dict[str, Any]] = []

    @staticmethod
    def canonical_device_node_id(device_id: str) -> str:
        return f"device:{device_id}"

    @staticmethod
    def canonical_interface_node_id(device_id: str, interface_name: str) -> str:
        return f"iface:{device_id}:{interface_name}"

    @staticmethod
    def evaluate_device_merge_candidate(
        dev_a: Dict[str, Any],
        dev_b: Dict[str, Any],
    ) -> MergeEvaluation:
        """
        Determines whether two device observation records represent the exact same physical/virtual router.
        Refuses merges based solely on shared IP or shared hostname/identity.
        """
        id_a = str(dev_a.get("inventory_id") or dev_a.get("device_id") or "").strip()
        id_b = str(dev_b.get("inventory_id") or dev_b.get("device_id") or "").strip()

        if id_a and id_b and id_a == id_b:
            return MergeEvaluation(
                should_merge=True,
                confidence=1.0,
                reason="Matched authoritative canonical/inventory ID.",
            )

        # If both have distinct explicit inventory IDs, NEVER merge them even if MAC/IP collide!
        if id_a and id_b and id_a != id_b and dev_a.get("is_managed") and dev_b.get("is_managed"):
            return MergeEvaluation(
                should_merge=False,
                confidence=0.98,
                reason=f"Distinct managed inventory IDs ({id_a} vs {id_b}); refusing merge.",
                conflict_detected=True,
            )

        mac_a = normalize_mac(str(dev_a.get("mac_address") or ""))
        mac_b = normalize_mac(str(dev_b.get("mac_address") or ""))
        if mac_a and mac_b and mac_a == mac_b and mac_a not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            # Verified unique hardware MAC match when at least one side is an unmerged discovery record
            return MergeEvaluation(
                should_merge=True,
                confidence=0.90,
                reason=f"Matched verified hardware MAC address ({mac_a}) without conflicting inventory IDs.",
            )

        ip_a = normalize_ip(str(dev_a.get("management_ip") or ""))
        ip_b = normalize_ip(str(dev_b.get("management_ip") or ""))
        name_a = str(dev_a.get("identity") or dev_a.get("hostname") or "").strip()
        name_b = str(dev_b.get("identity") or dev_b.get("hostname") or "").strip()

        if ip_a and ip_b and ip_a == ip_b:
            return MergeEvaluation(
                should_merge=False,
                confidence=0.35,
                reason=f"Shared IP ({ip_a}) alone is insufficient to merge devices (possible duplicate IP, VRRP, NAT, or VRF overlap).",
                conflict_detected=True,
            )

        if name_a and name_b and name_a.lower() == name_b.lower():
            return MergeEvaluation(
                should_merge=False,
                confidence=0.25,
                reason=f"Shared hostname/identity ('{name_a}') alone is insufficient to merge devices.",
                conflict_detected=(name_a.lower() not in GENERIC_DEFAULT_HOSTNAMES),
            )

        return MergeEvaluation(
            should_merge=False,
            confidence=0.0,
            reason="No authoritative identity match.",
        )

    def resolve_from_bundle(self, bundle: NetworkEvidenceBundle) -> Dict[str, ResolvedDeviceIdentity]:
        """Builds canonical device & interface lookup registries from a `NetworkEvidenceBundle`."""
        self.devices.clear()
        self.mac_to_devices.clear()
        self.ip_to_devices.clear()
        self.identity_to_devices.clear()
        self.identity_conflicts.clear()

        for dev_id, dinfo in bundle.device_evidence.items():
            mgmt_ip = normalize_ip(str(dinfo.get("management_ip") or "")) or str(dinfo.get("management_ip") or "")
            primary_mac = normalize_mac(str(dinfo.get("mac_address") or "")) or ""
            ident = str(dinfo.get("identity") or "").strip()
            disp = str(dinfo.get("display_name") or dev_id).strip()
            is_managed = bool(dinfo.get("is_managed"))

            known_ips: List[str] = [mgmt_ip] if mgmt_ip else []
            known_macs: List[str] = [primary_mac] if primary_mac else []
            iface_names: List[str] = []

            for iface in bundle.interface_evidence.get(dev_id, []):
                iname = str(iface.get("interface_name") or "").strip()
                if iname and iname not in iface_names:
                    iface_names.append(iname)
                imac = normalize_mac(str(iface.get("mac_address") or ""))
                if imac and imac not in known_macs:
                    known_macs.append(imac)

            pdata = bundle.protocol_evidence.get(dev_id, {})
            for ip_rec in pdata.get("ip_addresses") or []:
                if isinstance(ip_rec, dict) and not ip_rec.get("disabled") and not ip_rec.get("is_disabled"):
                    raw_addr = str(ip_rec.get("address") or "").split("/")[0].strip()
                    norm_addr = normalize_ip(raw_addr) or raw_addr
                    if norm_addr and norm_addr not in known_ips:
                        known_ips.append(norm_addr)
                    ifname = str(ip_rec.get("interface") or ip_rec.get("interface_name") or "").strip()
                    if ifname and ifname not in iface_names:
                        iface_names.append(ifname)

            prov: List[str] = ["inventory_managed" if is_managed else "topology_discovered"]
            if ident:
                prov.append("routeros_identity")
            if known_macs:
                prov.append("hardware_mac")

            conf = 0.96 if is_managed and (ident or known_macs) else (0.88 if is_managed else 0.65)
            is_partial = not is_managed or (not iface_names and not bundle.routing_evidence.get(dev_id))

            resolved = ResolvedDeviceIdentity(
                canonical_device_id=dev_id,
                display_name=disp,
                routeros_identity=ident,
                hostname=ident or disp,
                management_ip=mgmt_ip,
                known_ips=known_ips,
                known_macs=known_macs,
                interfaces=iface_names,
                is_managed=is_managed,
                is_partial=is_partial,
                identity_confidence=conf,
                provenance=prov,
            )
            self.devices[dev_id] = resolved

            for ip_val in known_ips:
                owners = self.ip_to_devices.setdefault(ip_val, [])
                if dev_id not in owners:
                    owners.append(dev_id)
            for mac_val in known_macs:
                owners = self.mac_to_devices.setdefault(mac_val, [])
                if dev_id not in owners:
                    owners.append(dev_id)
            if ident and ident.lower() not in GENERIC_DEFAULT_HOSTNAMES:
                owners = self.identity_to_devices.setdefault(ident.lower(), [])
                if dev_id not in owners:
                    owners.append(dev_id)

        # Record explicit conflicts without merging distinct devices
        for ip_val, owners in self.ip_to_devices.items():
            if len(owners) > 1:
                msg = f"Duplicate IP '{ip_val}' observed across distinct devices: {', '.join(owners)}"
                self.identity_conflicts.append(
                    {"type": "DUPLICATE_IP", "value": ip_val, "devices": list(owners), "description": msg}
                )
                for d in owners:
                    self.devices[d].conflicts.append(msg)

        for mac_val, owners in self.mac_to_devices.items():
            if len(owners) > 1:
                msg = f"Shared/duplicate MAC '{mac_val}' observed across devices: {', '.join(owners)}"
                self.identity_conflicts.append(
                    {"type": "DUPLICATE_MAC", "value": mac_val, "devices": list(owners), "description": msg}
                )
                for d in owners:
                    self.devices[d].conflicts.append(msg)

        for ident_key, owners in self.identity_to_devices.items():
            if len(owners) > 1:
                msg = f"Ambiguous RouterOS identity '{ident_key}' shared by devices: {', '.join(owners)}"
                self.identity_conflicts.append(
                    {"type": "AMBIGUOUS_IDENTITY", "value": ident_key, "devices": list(owners), "description": msg}
                )
                for d in owners:
                    self.devices[d].conflicts.append(msg)

        return self.devices

    def resolve_peer_by_ip(self, ip_address: str, exclude_device_id: Optional[str] = None) -> Tuple[Optional[str], float, str]:
        """
        Resolves a peer/gateway IP to a canonical device_id ONLY when unambiguous.
        If multiple devices claim the same IP, returns (None, 0.3, "AMBIGUOUS_DUPLICATE_IP")
        instead of guessing.
        """
        clean_ip = normalize_ip(str(ip_address or "").split("%")[0].strip()) or str(ip_address or "").strip()
        if not clean_ip:
            return None, 0.0, "EMPTY_IP"
        owners = [d for d in self.ip_to_devices.get(clean_ip, []) if d != exclude_device_id]
        if len(owners) == 1:
            dev = self.devices[owners[0]]
            return owners[0], dev.identity_confidence, "UNIQUE_IP_MATCH"
        if len(owners) > 1:
            return None, 0.30, f"AMBIGUOUS_IP_SHARED_BY:{','.join(owners)}"
        return None, 0.0, "EXTERNAL_OR_UNOBSERVED_IP"
