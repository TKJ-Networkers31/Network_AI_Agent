"""
core/network_intelligence/evidence.py — Evidence Collection, Normalization, Freshness, and Contradiction Detection.

Gathers read-only network facts via ConnectionManager and CanonicalNetworkRegistry with
bounded timeouts and safe redaction.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from agents.akane.connection_manager import get_connection_manager
from core.canonical_network import get_canonical_registry, parse_routeros_major_version
from core.network_intelligence.models import (
    EvidenceFreshness,
    EvidenceItem,
    EvidenceState,
)
from core.network_intelligence.security import (
    validate_readonly_command,
)
from core.topology_models import normalize_ip, sanitize_cli_excerpt, sanitize_untrusted_text
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.network_intelligence.evidence")

# Evidence command mapping for RouterOS
COMMAND_MAP_V6 = {
    "identity": "/system identity print",
    "resources": "/system resource print",
    "interfaces": "/interface print detail",
    "ip_addresses": "/ip address print detail",
    "routes": "/ip route print detail",
    "routing_rules": "/ip route rule print detail",
    "firewall_filter": "/ip firewall filter print detail",
    "nat_rules": "/ip firewall nat print detail",
    "mangle_rules": "/ip firewall mangle print detail",
    "bridge": "/interface bridge print detail",
    "bridge_ports": "/interface bridge port print detail",
    "bridge_vlan": "/interface bridge vlan print detail",
    "ospf_neighbors": "/routing ospf neighbor print",
    "ospf_instance": "/routing ospf instance print detail",
    "bgp_peers": "/routing bgp peer print detail",
    "arp": "/ip arp print detail",
    "dns": "/ip dns print",
}

COMMAND_MAP_V7 = {
    "identity": "/system identity print",
    "resources": "/system resource print",
    "interfaces": "/interface print detail",
    "ip_addresses": "/ip address print detail",
    "routes": "/ip route print detail",
    "routing_rules": "/routing rule print detail",
    "firewall_filter": "/ip firewall filter print detail",
    "nat_rules": "/ip firewall nat print detail",
    "mangle_rules": "/ip firewall mangle print detail",
    "bridge": "/interface bridge print detail",
    "bridge_ports": "/interface bridge port print detail",
    "bridge_vlan": "/interface bridge vlan print detail",
    "ospf_neighbors": "/routing ospf neighbor print",
    "ospf_instance": "/routing ospf instance print",
    "bgp_peers": "/routing bgp connection print detail",
    "arp": "/ip arp print detail",
    "dns": "/ip dns print",
}


def sanitize_raw_output(raw_text: str, max_chars: int = 1500) -> str:
    """Masks secrets and bounds excerpt length for safe UI presentation."""
    if not raw_text:
        return ""
    masked = mask_sensitive_data(raw_text)
    sanitized = sanitize_cli_excerpt(masked, max_chars)
    return sanitized


def determine_freshness(timestamp: float, current_time: Optional[float] = None) -> str:
    """Categorizes observation age into FRESH (<60s), STALE (<300s), or EXPIRED."""
    now = current_time or time.time()
    age = max(0.0, now - timestamp)
    if age < 60.0:
        return EvidenceFreshness.FRESH.value
    elif age < 300.0:
        return EvidenceFreshness.STALE.value
    else:
        return EvidenceFreshness.EXPIRED.value


def _is_ip_in_subnets(ip_str: str, subnet_strs: List[str]) -> bool:
    """Helper to check if an IP belongs to any CIDR subnets."""
    try:
        clean = normalize_ip(ip_str)
        if not clean:
            return False
        addr = ipaddress.ip_address(clean)
        for s in subnet_strs:
            try:
                net = ipaddress.ip_network(s.strip(), strict=False)
                if addr in net:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


class EvidenceCollector:
    """Orchestrates bounded, read-only evidence collection and normalization."""

    def __init__(self):
        self.cm = get_connection_manager()
        self.registry = get_canonical_registry()

    def resolve_target_device(self, query: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Resolves query to (target_identifier, ros_major_version, display_name).
        Returns (None, None, None) if device cannot be resolved.
        """
        dev = self.registry.resolve_device(query)
        if dev:
            ros_major = dev.ros_major_version or parse_routeros_major_version(dev.os_version) or 7
            return dev.inventory_name or dev.management_ip, ros_major, dev.display_name
        return None, None, None

    def collect_evidence_bundle(
        self,
        target: str,
        required_types: List[str],
        timeout_per_cmd: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Collects requested evidence types for the target with bounded execution.
        Returns a dictionary containing:
        - target: str
        - ros_major_version: int
        - display_name: str
        - evidence_items: List[EvidenceItem]
        - contradictions: List[str]
        - collection_errors: List[str]
        """
        dev_id, ros_major, display_name = self.resolve_target_device(target)
        if not dev_id:
            # Fallback to direct name/IP if not found in registry
            dev_id = target
            ros_major = 7
            display_name = target

        cmd_map = COMMAND_MAP_V7 if ros_major == 7 else COMMAND_MAP_V6
        collected_items: List[EvidenceItem] = []
        errors: List[str] = []

        for obs_type in required_types:
            cmd = cmd_map.get(obs_type)
            if not cmd:
                continue

            # Read-only policy validation before dispatching to transport
            is_valid, reason = validate_readonly_command(cmd)
            t0 = time.time()
            if not is_valid:
                errors.append(f"{obs_type}: Blocked by security policy ({reason})")
                collected_items.append(EvidenceItem(
                    evidence_id=f"ev_{obs_type}_{uuid.uuid4().hex[:6]}",
                    device_identity=dev_id,
                    observation_type=obs_type,
                    source_command=cmd,
                    collection_timestamp=t0,
                    collection_status="FAILED",
                    normalized_value=None,
                    raw_excerpt=f"[Security Rejection: {reason}]",
                    freshness=EvidenceFreshness.UNKNOWN.value,
                    limitations=reason,
                    state=EvidenceState.UNAVAILABLE.value,
                ))
                continue

            try:
                res = self.cm.execute_for_device(dev_id, cmd, timeout=timeout_per_cmd)
                if res.get("success"):
                    raw_out = res.get("output", "").strip()
                    is_invalid = (
                        not raw_out
                        or "[truncated]" in raw_out.lower()
                        or "syntax error" in raw_out.lower()
                        or "bad command" in raw_out.lower()
                        or "interrupted" in raw_out.lower()
                    )

                    norm_val = self._normalize_observation(obs_type, raw_out, ros_major)
                    excerpt = sanitize_raw_output(raw_out, max_chars=1200)

                    state = EvidenceState.INVALID.value if is_invalid else EvidenceState.OBSERVED.value
                    coll_status = "PARTIAL" if is_invalid else "SUCCESS"
                    limit_text = "Output CLI kosong, terpotong, atau tidak terparse secara valid." if is_invalid else ""

                    item = EvidenceItem(
                        evidence_id=f"ev_{obs_type}_{uuid.uuid4().hex[:6]}",
                        device_identity=dev_id,
                        observation_type=obs_type,
                        source_command=cmd,
                        collection_timestamp=t0,
                        collection_status=coll_status,
                        normalized_value=norm_val,
                        raw_excerpt=excerpt,
                        freshness=EvidenceFreshness.FRESH.value,
                        is_derived=False,
                        limitations=limit_text,
                        state=state,
                    )
                    collected_items.append(item)
                else:
                    err_msg = res.get("error") or "Execution failed"
                    errors.append(f"{obs_type}: {err_msg}")
                    item = EvidenceItem(
                        evidence_id=f"ev_{obs_type}_{uuid.uuid4().hex[:6]}",
                        device_identity=dev_id,
                        observation_type=obs_type,
                        source_command=cmd,
                        collection_timestamp=t0,
                        collection_status="FAILED",
                        normalized_value=None,
                        raw_excerpt=f"[Error: {err_msg}]",
                        freshness=EvidenceFreshness.UNKNOWN.value,
                        limitations=err_msg,
                        state=EvidenceState.UNAVAILABLE.value,
                    )
                    collected_items.append(item)
            except Exception as exc:
                logger.warning("Error collecting %s from %s: %s", obs_type, dev_id, exc)
                errors.append(f"{obs_type}: {str(exc)}")
                collected_items.append(EvidenceItem(
                    evidence_id=f"ev_{obs_type}_{uuid.uuid4().hex[:6]}",
                    device_identity=dev_id,
                    observation_type=obs_type,
                    source_command=cmd,
                    collection_timestamp=t0,
                    collection_status="FAILED",
                    normalized_value=None,
                    raw_excerpt=f"[Exception: {str(exc)}]",
                    freshness=EvidenceFreshness.UNKNOWN.value,
                    limitations=str(exc),
                    state=EvidenceState.UNAVAILABLE.value,
                ))

        contradictions = self.detect_contradictions(collected_items)

        return {
            "target": dev_id,
            "ros_major_version": ros_major,
            "display_name": display_name,
            "evidence_items": collected_items,
            "contradictions": contradictions,
            "collection_errors": errors,
        }

    # -----------------------------------------------------------------------
    # Normalizers
    # -----------------------------------------------------------------------

    def _normalize_observation(self, obs_type: str, raw_text: str, ros_major: int) -> Dict[str, Any]:
        """Dispatches raw output to typed deterministic normalizers."""
        if obs_type == "routes":
            from agents.akane.reasoning_engine import parse_routeros_routes
            parsed = parse_routeros_routes(raw_text)
            return {
                "count": len(parsed),
                "routes": [
                    {
                        "dst_address": r.dst_address,
                        "gateway": r.gateway,
                        "distance": r.distance,
                        "active": r.active,
                        "dynamic": r.dynamic,
                        "connect": r.connect,
                        "static": r.static,
                        "prefix_len": r.prefix_len,
                        "raw_flags": r.raw_flags,
                    }
                    for r in parsed
                ],
                "has_default_route": any(r.dst_address == "0.0.0.0/0" for r in parsed),
                "has_active_default_route": any(r.dst_address == "0.0.0.0/0" and r.active for r in parsed),
            }

        elif obs_type == "ip_addresses":
            return self._parse_ip_addresses(raw_text)

        elif obs_type == "interfaces":
            return self._parse_interfaces(raw_text)

        elif obs_type == "firewall_filter":
            from agents.akane.reasoning_engine import parse_routeros_firewall
            parsed = parse_routeros_firewall(raw_text)
            return {
                "count": len(parsed),
                "rules": [
                    {
                        "index": r.index,
                        "chain": r.chain,
                        "action": r.action,
                        "connection_state": r.connection_state,
                        "protocol": r.protocol,
                        "dst_port": r.dst_port,
                        "in_interface": r.in_interface,
                        "out_interface": r.out_interface,
                        "comment": r.comment,
                        "disabled": r.disabled,
                    }
                    for r in parsed
                ],
                "forward_rules_count": sum(1 for r in parsed if r.chain == "forward"),
                "input_rules_count": sum(1 for r in parsed if r.chain == "input"),
            }

        elif obs_type == "nat_rules":
            return self._parse_nat_rules(raw_text)

        elif obs_type == "bridge_vlan" or obs_type == "bridge_ports" or obs_type == "bridge":
            return self._parse_bridge_vlan(raw_text)

        elif obs_type == "ospf_neighbors":
            return self._parse_ospf_neighbors(raw_text)

        elif obs_type == "bgp_peers":
            return self._parse_bgp_peers(raw_text, ros_major)

        elif obs_type == "arp":
            return self._parse_arp_table(raw_text)

        return {"raw_length": len(raw_text), "lines_count": len(raw_text.splitlines())}

    def _parse_ip_addresses(self, text: str) -> Dict[str, Any]:
        """Parses /ip address print output (detail and tabular formats)."""
        addrs = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#") or line_s.startswith("Flags") or line_s.startswith("Columns"):
                continue
            # Detail format: address=192.168.1.1/24 interface=ether1
            addr_m = re.search(r"address=([0-9\.\/]+)", line_s)
            if not addr_m:
                addr_m = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b", line_s)
            if addr_m:
                addr = addr_m.group(1)
                if_m = re.search(r"interface=([^\s]+)", line_s)
                net_m = re.search(r"network=([^\s]+)", line_s)

                tokens = line_s.split()
                if if_m:
                    if_name = if_m.group(1)
                elif len(tokens) >= 3 and not re.match(r"^\d+\.\d+\.\d+\.\d+", tokens[-1]):
                    # Tabular format: interface is last token
                    if_name = tokens[-1]
                else:
                    if_name = "unknown"

                if net_m:
                    net_str = net_m.group(1)
                else:
                    # Look for non-CIDR IPv4 network address in tokens
                    net_cands = [t for t in tokens if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", t)]
                    net_str = net_cands[0] if net_cands else ""

                dis = "disabled=yes" in line_s or "X" in line_s[:4]
                addrs.append({
                    "address": addr,
                    "interface": if_name,
                    "network": net_str,
                    "disabled": dis,
                })
        return {"count": len(addrs), "addresses": addrs}

    def _parse_interfaces(self, text: str) -> Dict[str, Any]:
        """Parses /interface print detail output."""
        ifaces = []
        cur_iface: Dict[str, Any] = {}

        def flush():
            if cur_iface and cur_iface.get("name"):
                ifaces.append(dict(cur_iface))
                cur_iface.clear()

        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("Flags:"):
                continue
            m_idx = re.match(r"^(\d+)\s+([RXSDID\s]*)(.*)", line_s)
            if m_idx:
                flush()
                flags = m_idx.group(2).upper()
                cur_iface = {
                    "index": int(m_idx.group(1)),
                    "running": "R" in flags or "running=yes" in line_s,
                    "disabled": "X" in flags or "disabled=yes" in line_s,
                    "type": "ethernet",
                    "raw": line_s,
                }
                rest = m_idx.group(3)
            else:
                rest = line_s

            name_m = re.search(r"name=\"?([^\"\s]+)\"?", rest)
            if name_m and "name" not in cur_iface:
                cur_iface["name"] = name_m.group(1)

            type_m = re.search(r"type=\"?([^\"\s]+)\"?", rest)
            if type_m:
                cur_iface["type"] = type_m.group(1)

            if "running=yes" in rest:
                cur_iface["running"] = True
            elif "running=no" in rest:
                cur_iface["running"] = False

        flush()
        return {"count": len(ifaces), "interfaces": ifaces}

    def _parse_nat_rules(self, text: str) -> Dict[str, Any]:
        """Parses /ip firewall nat print detail output."""
        rules = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("Flags:") or line_s.startswith("#"):
                continue
            chain_m = re.search(r"chain=([^\s]+)", line_s)
            action_m = re.search(r"action=([^\s]+)", line_s)
            out_if_m = re.search(r"out-interface(?:-list)?=([^\s]+)", line_s)
            src_addr_m = re.search(r"src-address=([^\s]+)", line_s)
            to_addr_m = re.search(r"to-addresses=([^\s]+)", line_s)
            to_ports_m = re.search(r"to-ports=([^\s]+)", line_s)

            if chain_m and action_m:
                rules.append({
                    "chain": chain_m.group(1).lower(),
                    "action": action_m.group(1).lower(),
                    "out_interface": out_if_m.group(1) if out_if_m else "",
                    "src_address": src_addr_m.group(1) if src_addr_m else "",
                    "to_addresses": to_addr_m.group(1) if to_addr_m else "",
                    "to_ports": to_ports_m.group(1) if to_ports_m else "",
                    "disabled": "disabled=yes" in line_s or "X" in line_s[:4],
                    "raw": line_s,
                })
        has_masquerade = any(r["action"] == "masquerade" and not r["disabled"] for r in rules)
        return {"count": len(rules), "rules": rules, "has_masquerade": has_masquerade}

    def _parse_bridge_vlan(self, text: str) -> Dict[str, Any]:
        """Parses bridge and bridge vlan tables (detail and tabular formats)."""
        vlan_ids = []
        tagged = []
        untagged = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#") or line_s.startswith("Flags") or line_s.startswith("Columns"):
                continue
            v_m = re.search(r"vlan-ids?=(\d+(?:-\d+)?)", line_s)
            if v_m:
                vlan_ids.append(v_m.group(1))
            else:
                # Tabular match: 0 bridge1 10 ether2
                parts = line_s.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    if re.match(r"^\d+(?:-\d+)?$", parts[2]):
                        vlan_ids.append(parts[2])
                        if len(parts) >= 4 and not parts[3].isdigit():
                            tagged.append(parts[3])
                        if len(parts) >= 5 and not parts[4].isdigit():
                            untagged.append(parts[4])

            tag_m = re.search(r"tagged=([^\s]+)", line_s)
            if tag_m:
                tagged.extend(tag_m.group(1).split(","))
            untag_m = re.search(r"untagged=([^\s]+)", line_s)
            if untag_m:
                untagged.extend(untag_m.group(1).split(","))

        vlan_filtering = "vlan-filtering=yes" in text.lower() or "vlan_filtering=true" in text.lower()
        return {
            "vlan_filtering": vlan_filtering,
            "vlan_ids": sorted(list(set(vlan_ids))),
            "tagged_ports": sorted(list(set(tagged))),
            "untagged_ports": sorted(list(set(untagged))),
        }

    def _parse_ospf_neighbors(self, text: str) -> Dict[str, Any]:
        """Parses /routing ospf neighbor print output."""
        neighbors = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#") or line_s.startswith("Flags"):
                continue
            # Look for neighbor-id or IP address and state
            r_id_m = re.search(r"router-id=([0-9\.]+)", line_s) or re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", line_s)
            state_m = re.search(r"state=\"?([a-zA-Z]+)\"?", line_s) or re.search(r"\b(Full|2-Way|Init|Down|ExStart|Exchange|Loading)\b", line_s, re.IGNORECASE)
            addr_m = re.search(r"address=([0-9\.]+)", line_s)
            if r_id_m:
                st = state_m.group(1) if state_m else "Unknown"
                neighbors.append({
                    "router_id": r_id_m.group(1),
                    "address": addr_m.group(1) if addr_m else "",
                    "state": st,
                    "is_full": st.lower() == "full",
                    "raw": line_s,
                })
        return {
            "count": len(neighbors),
            "neighbors": neighbors,
            "all_full": bool(neighbors) and all(n["is_full"] for n in neighbors),
        }

    def _parse_bgp_peers(self, text: str, ros_major: int) -> Dict[str, Any]:
        """Parses BGP peer / connection table for v6 and v7."""
        peers = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("Flags:") or line_s.startswith("#"):
                continue
            name_m = re.search(r"name=\"?([^\"\s]+)\"?", line_s)
            state_m = re.search(r"state=\"?([a-zA-Z]+)\"?", line_s) or re.search(r"\b(established|idle|active|connect|openconfirm|opensent)\b", line_s, re.IGNORECASE)
            remote_ip_m = re.search(r"remote\.address=([0-9\.]+)", line_s) or re.search(r"remote-address=([0-9\.]+)", line_s)
            remote_as_m = re.search(r"remote\.as=(\d+)", line_s) or re.search(r"remote-as=(\d+)", line_s)
            prefix_count_m = re.search(r"prefix-count=(\d+)", line_s) or re.search(r"prefixes=(\d+)", line_s)

            if remote_ip_m or name_m:
                st = state_m.group(1).lower() if state_m else "unknown"
                p_count = int(prefix_count_m.group(1)) if prefix_count_m else 0
                peers.append({
                    "name": name_m.group(1) if name_m else "peer",
                    "remote_ip": remote_ip_m.group(1) if remote_ip_m else "",
                    "remote_as": remote_as_m.group(1) if remote_as_m else "",
                    "state": st,
                    "is_established": st == "established",
                    "prefix_count": p_count,
                    "raw": line_s,
                })
        return {
            "count": len(peers),
            "peers": peers,
            "has_established": any(p["is_established"] for p in peers),
        }

    def _parse_arp_table(self, text: str) -> Dict[str, Any]:
        """Parses /ip arp print detail output."""
        entries = []
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("Flags:"):
                continue
            ip_m = re.search(r"address=([0-9\.]+)", line_s)
            mac_m = re.search(r"mac-address=([0-9A-Fa-f:]+)", line_s)
            if_m = re.search(r"interface=([^\s]+)", line_s)
            complete = "C" in line_s[:4] or "complete=yes" in line_s
            if ip_m:
                entries.append({
                    "ip": ip_m.group(1),
                    "mac": mac_m.group(1) if mac_m else "",
                    "interface": if_m.group(1) if if_m else "",
                    "complete": complete,
                })
        return {"count": len(entries), "entries": entries}

    # -----------------------------------------------------------------------
    # Contradiction Detection
    # -----------------------------------------------------------------------

    def detect_contradictions(self, items: List[EvidenceItem]) -> List[str]:
        """
        Detects contradictory observations between collected network artifacts.
        E.g., configured IP on an interface that is down, routes with unresolvable ARP next-hops,
        BGP sessions established without prefixes, or cross-device/cross-timestamp mismatches.
        """
        contradictions: List[str] = []
        by_type: Dict[str, Any] = {
            it.observation_type: it.normalized_value
            for it in items
            if it.collection_status in ("SUCCESS", "PARTIAL") and it.normalized_value is not None
        }
        contradictory_types: set[str] = set()

        # 0. Cross-device and cross-timestamp mismatch
        device_ids = {it.device_identity for it in items if it.device_identity}
        if len(device_ids) > 1:
            contradictions.append(
                f"Bukti terdeteksi berasal dari target perangkat yang berbeda ({', '.join(sorted(device_ids))})."
            )
            for it in items:
                it.state = EvidenceState.CONTRADICTORY.value

        valid_timestamps = [it.collection_timestamp for it in items if it.collection_timestamp > 0]
        if valid_timestamps and (max(valid_timestamps) - min(valid_timestamps) > 300.0):
            delta_s = max(valid_timestamps) - min(valid_timestamps)
            contradictions.append(
                f"Bukti memiliki rentang waktu observasi yang terlalu lebar ({delta_s:.1f} detik). "
                f"Bukti lama berpotensi basi dan bertentangan dengan observasi terkini."
            )
            for it in items:
                if (max(valid_timestamps) - it.collection_timestamp) > 300.0:
                    it.state = EvidenceState.STALE.value

        # 1. IP address configured on interface marked down / disabled
        if "ip_addresses" in by_type and "interfaces" in by_type:
            ip_data = by_type["ip_addresses"]
            if_data = by_type["interfaces"]
            if isinstance(ip_data, dict) and isinstance(if_data, dict):
                ifaces_map = {ifc.get("name"): ifc for ifc in if_data.get("interfaces", [])}
                for addr in ip_data.get("addresses", []):
                    if_name = addr.get("interface")
                    if if_name in ifaces_map:
                        ifc = ifaces_map[if_name]
                        if not ifc.get("running") and not addr.get("disabled"):
                            contradictions.append(
                                f"Alamat IP {addr.get('address')} terpasang pada interface '{if_name}' "
                                f"namun interface tersebut berstatus DOWN (running=no)."
                            )
                            contradictory_types.update(["ip_addresses", "interfaces"])

        # 2. Default route active but gateway interface down or next-hop unresolvable
        if "routes" in by_type:
            routes_data = by_type["routes"]
            if isinstance(routes_data, dict):
                routes_list = routes_data.get("routes", [])
                default_routes = [r for r in routes_list if r.get("dst_address") == "0.0.0.0/0" and r.get("active")]

                if "interfaces" in by_type:
                    if_data = by_type["interfaces"]
                    if isinstance(if_data, dict):
                        ifaces_map = {ifc.get("name"): ifc for ifc in if_data.get("interfaces", [])}
                        for r in default_routes:
                            gw = r.get("gateway", "")
                            if gw in ifaces_map and not ifaces_map[gw].get("running"):
                                contradictions.append(
                                    f"Default route aktif menunjuk interface gateway '{gw}', tetapi interface tersebut berstatus DOWN."
                                )
                                contradictory_types.update(["routes", "interfaces"])

                if "arp" in by_type:
                    arp_data = by_type["arp"]
                    if isinstance(arp_data, dict):
                        arp_entries = arp_data.get("entries", [])
                        arp_map = {e.get("ip"): e for e in arp_entries if e.get("ip")}
                        for r in default_routes:
                            gw = r.get("gateway", "")
                            if gw in arp_map:
                                entry = arp_map[gw]
                                if not entry.get("complete") or not entry.get("mac"):
                                    contradictions.append(
                                        f"Default route aktif menunjuk next-hop IP {gw}, tetapi entri ARP untuk gateway tersebut "
                                        f"berstatus INCOMPLETE / MAC tidak teresolusi."
                                    )
                                    contradictory_types.update(["routes", "arp"])

                if "ip_addresses" in by_type:
                    ip_data = by_type["ip_addresses"]
                    if isinstance(ip_data, dict):
                        subnets = [a.get("address") for a in ip_data.get("addresses", []) if a.get("address")]
                        for r in default_routes:
                            gw = r.get("gateway", "")
                            if gw and not gw.isalpha() and "." in gw and ":" not in gw:
                                if subnets and not _is_ip_in_subnets(gw, subnets):
                                    contradictions.append(
                                        f"Default route menunjuk next-hop IP {gw}, namun IP tersebut tidak berada dalam subnet lokal "
                                        f"yang terhubung pada router (unreachable next-hop)."
                                    )
                                    contradictory_types.update(["routes", "ip_addresses"])

        # 3. BGP Established but prefix count is 0
        if "bgp_peers" in by_type:
            bgp_data = by_type["bgp_peers"]
            if isinstance(bgp_data, dict):
                for peer in bgp_data.get("peers", []):
                    if peer.get("is_established") and peer.get("prefix_count", 0) == 0:
                        contradictions.append(
                            f"Sesi BGP peer '{peer.get('name')}' berstatus ESTABLISHED, namun jumlah prefix yang diterima adalah 0 "
                            f"(BGP prefix filtering atau tidak ada route advertisement)."
                        )
                        contradictory_types.add("bgp_peers")

        # 4. OSPF Full but data-plane path failure
        if "ospf_neighbors" in by_type:
            ospf_data = by_type["ospf_neighbors"]
            if isinstance(ospf_data, dict):
                for n in ospf_data.get("neighbors", []):
                    if n.get("is_full"):
                        n_if = n.get("interface")
                        if n_if and "interfaces" in by_type:
                            if_data = by_type["interfaces"]
                            ifaces_map = {ifc.get("name"): ifc for ifc in if_data.get("interfaces", [])}
                            if n_if in ifaces_map and not ifaces_map[n_if].get("running"):
                                contradictions.append(
                                    f"OSPF neighbor '{n.get('router_id')}' tercatat FULL, namun interface lokal '{n_if}' berstatus DOWN."
                                )
                                contradictory_types.update(["ospf_neighbors", "interfaces"])
                        n_ip = n.get("address")
                        if n_ip and "arp" in by_type:
                            arp_entries = by_type["arp"].get("entries", [])
                            arp_map = {e.get("ip"): e for e in arp_entries if e.get("ip")}
                            if n_ip in arp_map and not arp_map[n_ip].get("complete"):
                                contradictions.append(
                                    f"OSPF neighbor '{n.get('router_id')}' berstatus FULL, namun ARP data-plane untuk {n_ip} INCOMPLETE."
                                )
                                contradictory_types.update(["ospf_neighbors", "arp"])

        # 5. Bridge VLAN filtering enabled but no VLAN IDs defined or ports unproven
        if "bridge_vlan" in by_type:
            bv = by_type["bridge_vlan"]
            if isinstance(bv, dict):
                if bv.get("vlan_filtering") and not bv.get("vlan_ids"):
                    contradictions.append(
                        "Bridge VLAN filtering aktif, tetapi tidak ada entri VLAN ID di bridge vlan table. Semua frame bertag akan didrop."
                    )
                    contradictory_types.add("bridge_vlan")
                elif not bv.get("vlan_filtering") and bv.get("vlan_ids"):
                    contradictions.append(
                        "VLAN ID terdaftar di bridge vlan table, tetapi vlan-filtering=no pada bridge. Frame tagging L2 hardware tidak ditegakkan."
                    )
                    contradictory_types.add("bridge_vlan")

        # Mark affected evidence items as CONTRADICTORY
        for it in items:
            if it.observation_type in contradictory_types and it.state != EvidenceState.UNAVAILABLE.value:
                it.state = EvidenceState.CONTRADICTORY.value

        return contradictions
