"""
core/topology_discovery.py — Evidence-based discovery pipeline, ISP boundary detection,
identity resolution, wiring confidence, and bounded recursive interrogation for AIRA Topology Fabric V2.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.topology_models import (
    calculate_deterministic_node_status,
    extract_physical_port_name,
    ip_in_subnets,
    is_randomized_or_local_mac,
    is_vpn_or_tunnel_interface,
    normalize_ip,
    normalize_mac,
    sanitize_cli_excerpt,
    sanitize_untrusted_text,
)
from core.topology_parsers import (
    parse_mikrotik_addresses,
    parse_mikrotik_arp,
    parse_mikrotik_bridge_hosts,
    parse_mikrotik_bridge_ports,
    parse_mikrotik_dhcp_clients,
    parse_mikrotik_dhcp_leases,
    parse_mikrotik_interfaces,
    parse_mikrotik_neighbors,
    parse_mikrotik_routerboard,
    parse_mikrotik_routes,
    parse_mikrotik_vlans,
)

logger = logging.getLogger("aira.topology.discovery")


def classify_device_type_from_hints(identity: str, board: str, platform_str: str, caps: str = "") -> str:
    combined = f"{identity} {board} {platform_str} {caps}".lower()
    if any(k in combined for k in ("crs", "css", "switch", "sw-", "catalyst", "procurve")):
        return "switch"
    if any(k in combined for k in ("wap", "cap", "groove", "sxt", "lhg", "ap-", "unifi", "wlan-ap")):
        return "access_point"
    if any(k in combined for k in ("ccr", "rb", "router", "chr", "core", "gateway", "mikrotik", "hap", "vyos", "isr")):
        return "router"
    if any(k in combined for k in ("server", "nas", "pve", "proxmox", "esxi", "truenas")):
        return "server"
    return "client"


def _matches_device_list(
    entries: List[str],
    *,
    ip: str = "",
    mac: str = "",
    identity: str = "",
    node_id: str = "",
) -> bool:
    if not entries:
        return False
    norm_ip = normalize_ip(ip)
    norm_mac = normalize_mac(mac)
    ident_l = (identity or "").strip().lower()
    nid_l = (node_id or "").strip().lower()

    for raw in entries:
        token = str(raw or "").strip()
        if not token:
            continue
        tl = token.lower()
        if norm_ip and (token == norm_ip or ip_in_subnets(norm_ip, [token])):
            return True
        if norm_mac and normalize_mac(token) == norm_mac:
            return True
        if ident_l and tl == ident_l:
            return True
        if nid_l and tl == nid_l:
            return True
    return False


def _is_interface_in_boundary_policy(source_name: str, source_id: str, iface: str, boundary_list: List[str]) -> bool:
    if not iface or not boundary_list:
        return False
    ifl = iface.strip().lower()
    snl = (source_name or "").strip().lower()
    sidl = (source_id or "").strip().lower()
    for item in boundary_list:
        t = str(item or "").strip().lower()
        if not t:
            continue
        if ":" in t:
            dev_part, if_part = t.split(":", 1)
            if dev_part in (snl, sidl) and if_part == ifl:
                return True
        elif t == ifl:
            return True
    return False


class TopologyDiscoveryMixin:
    """
    Mixin providing Stages 1-10 of the Evidence-Based Discovery Pipeline to TopologyEngine.
    Expects self to provide SQLite helper methods defined on TopologyEngine.
    """

    def interrogate_routeros_readonly(
        self,
        conn_mgr: Any,
        *,
        device_name: str,
        host: str,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Stage B: Read-only, version-aware interrogation of an authorized RouterOS device.
        Never executes state-changing commands or secret exports.
        """
        outputs: Dict[str, str] = {}
        limitations: List[str] = []

        def _run_ro(cmd: str) -> Tuple[bool, str, str]:
            res = conn_mgr.execute_command(cmd, device_name=device_name, host=host, timeout=timeout)
            if not res.get("success"):
                return False, "", sanitize_untrusted_text(res.get("error", "Command failed"), 200)
            out = sanitize_cli_excerpt(res.get("output", ""), max_len=16000)
            return True, out, ""

        ok_id, id_out, err_id = _run_ro("/system identity print")
        if not ok_id:
            return {"success": False, "error": err_id or f"Unable to interrogate {device_name} ({host})."}
        outputs["identity"] = id_out

        _, res_out, _ = _run_ro("/system resource print")
        outputs["resource"] = res_out

        is_v7 = "version: 7." in res_out.lower() or " 7." in res_out.lower()

        # Hardware RouterBOARD serial/model (may be absent on CHR / x86)
        ok_rb, rb_out, _ = _run_ro("/system routerboard print")
        outputs["routerboard"] = rb_out if ok_rb else ""

        # Core Layer 2 / Layer 3 read-only tables
        core_cmds = {
            "interface": "/interface print detail",
            "ip_address": "/ip address print detail",
            "route": "/ip route print detail",
            "neighbor": "/ip neighbor print detail",
            "arp": "/ip arp print detail",
            "dhcp_client": "/ip dhcp-client print detail",
            "bridge_port": "/interface bridge port print detail",
            "bridge_host": "/interface bridge host print detail",
            "dhcp_lease": "/ip dhcp-server lease print detail",
            "vlan": "/interface vlan print detail",
            "bridge_vlan": "/interface bridge vlan print detail",
            "nat": "/ip firewall nat print",
        }

        for key, cmd in core_cmds.items():
            ok, out, err = _run_ro(cmd)
            if ok and "bad command name" not in out.lower():
                outputs[key] = out
            else:
                outputs[key] = ""
                if err:
                    limitations.append(f"{key}: {err}")

        # Version-aware wireless read-only check
        wlan_cmd = "/interface wifi print detail" if is_v7 else "/interface wireless print detail"
        ok_w, w_out, _ = _run_ro(wlan_cmd)
        if not ok_w or "bad command name" in w_out.lower():
            if is_v7:
                ok_w2, w_out2, _ = _run_ro("/interface wireless print detail")
                outputs["wireless"] = w_out2 if (ok_w2 and "bad command name" not in w_out2.lower()) else ""
            else:
                outputs["wireless"] = ""
        else:
            outputs["wireless"] = w_out

        return {
            "success": True,
            "outputs": outputs,
            "limitations": limitations,
            "is_v7": is_v7,
        }

    def discover_from_device_output(
        self,
        source_name: str,
        source_ip: str,
        identity_output: str,
        resource_output: str,
        neighbor_output: str,
        interface_output: str,
        route_output: str = "",
        nat_output: str = "",
        arp_output: str = "",
        dhcp_client_output: str = "",
        wireless_output: str = "",
        *,
        routerboard_output: str = "",
        ip_address_output: str = "",
        bridge_port_output: str = "",
        bridge_host_output: str = "",
        dhcp_lease_output: str = "",
        vlan_output: str = "",
        bridge_vlan_output: str = "",
        policy: Optional[Dict[str, Any]] = None,
        inventory_devices: Optional[List[Dict[str, Any]]] = None,
        hop_depth: int = 0,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Stages 3-10: Deterministic, evidence-based observation parsing, identity resolution,
        ISP boundary classification, wiring verification, and idempotent DB reconciliation.
        """
        now = now_ts if now_ts is not None else time.time()
        pol = policy or self.get_policy()
        inv_devs = inventory_devices if inventory_devices is not None else self._safe_list_inventory_devices()

        inv_by_ip: Dict[str, Dict[str, Any]] = {}
        inv_by_name: Dict[str, Dict[str, Any]] = {}
        for d in inv_devs:
            if not d.get("enabled", True):
                continue
            dip = normalize_ip(d.get("host"))
            if dip:
                inv_by_ip[dip] = d
            dname = (d.get("name") or "").strip().lower()
            if dname:
                inv_by_name[dname] = d

        # 1. Normalize Seed / Interrogated Device Identity & Hardware Info
        clean_source_name = sanitize_untrusted_text(source_name or "Seed-Router", 64)
        clean_source_ip = normalize_ip(source_ip)

        identity = clean_source_name
        m_id = re.search(r'name:\s*"?([^"\r\n]+)"?', identity_output or "")
        if m_id:
            identity = sanitize_untrusted_text(m_id.group(1).strip(), 64)

        rb_info = parse_mikrotik_routerboard(routerboard_output)
        serial_number = rb_info.get("serial-number", "")

        metadata: Dict[str, Any] = {}
        m_cpu = re.search(r"cpu-load:\s*([0-9]+)%?", resource_output or "")
        if m_cpu:
            metadata["cpu_load"] = int(m_cpu.group(1))
        m_up = re.search(r"uptime:\s*([^\r\n]+)", resource_output or "")
        if m_up:
            metadata["uptime"] = sanitize_untrusted_text(m_up.group(1).strip(), 64)
        m_board = re.search(r"board-name:\s*([^\r\n]+)", resource_output or "")
        if m_board:
            metadata["board"] = sanitize_untrusted_text(m_board.group(1).strip(), 64)
        elif rb_info.get("model"):
            metadata["board"] = rb_info["model"]
        m_ver = re.search(r"version:\s*([^\r\n]+)", resource_output or "")
        if m_ver:
            metadata["version"] = sanitize_untrusted_text(m_ver.group(1).strip(), 64)

        interfaces_map = parse_mikrotik_interfaces(interface_output)
        ip_addresses = parse_mikrotik_addresses(ip_address_output)
        routes = parse_mikrotik_routes(route_output)
        dhcp_clients = parse_mikrotik_dhcp_clients(dhcp_client_output)
        bridge_ports = parse_mikrotik_bridge_ports(bridge_port_output)
        bridge_hosts = parse_mikrotik_bridge_hosts(bridge_host_output)
        dhcp_leases = parse_mikrotik_dhcp_leases(dhcp_lease_output)
        vlans = parse_mikrotik_vlans(vlan_output, bridge_vlan_output)
        neighbors = parse_mikrotik_neighbors(neighbor_output)
        arp_entries = parse_mikrotik_arp(arp_output)

        source_all_ips = sorted(
            {clean_source_ip, *(a["ip"] for a in ip_addresses if a.get("ip"))} - {""}
        )
        source_all_macs = sorted(
            {info["mac"] for info in interfaces_map.values() if info.get("mac")} - {""}
        )

        source_node_id = self._resolve_or_select_node_id(
            preferred_id=f"node_{re.sub(r'[^a-zA-Z0-9_]', '_', clean_source_name.lower())}",
            serial_number=serial_number,
            mac=source_all_macs[0] if source_all_macs else "",
            ip=clean_source_ip,
            identity=identity,
            board=metadata.get("board", ""),
            all_macs=source_all_macs,
            is_interrogated_device=True,
        )

        # 2. Multi-Signal WAN / ISP Boundary Analysis (No single-signal ownership leaps!)
        wan_signals_by_iface: Dict[str, List[str]] = {}
        default_routes: List[Dict[str, Any]] = []

        for rt in routes:
            if rt.get("dst") == "0.0.0.0/0":
                default_routes.append(rt)
                rif = rt.get("interface", "")
                if rif:
                    wan_signals_by_iface.setdefault(rif, []).append("default_route")

        for dc in dhcp_clients:
            dif = dc.get("interface", "")
            if dif and dc.get("add_default_route", True):
                wan_signals_by_iface.setdefault(dif, []).append(f"dhcp_client:{dc.get('status') or 'configured'}")

        if nat_output:
            for m_nat in re.finditer(r'out-interface[=:\s]+"?([a-zA-Z0-9_.\-]+)"?', sanitize_cli_excerpt(nat_output, 4000), re.IGNORECASE):
                nif = m_nat.group(1)
                wan_signals_by_iface.setdefault(nif, []).append("nat_masquerade")

        for if_name, if_info in interfaces_map.items():
            if if_info.get("type") in ("pppoe-out", "lte"):
                wan_signals_by_iface.setdefault(if_name, []).append(f"wan_tunnel:{if_info['type']}")

        policy_boundary_ifaces: Set[str] = set()
        for if_name in set(list(interfaces_map.keys()) + list(wan_signals_by_iface.keys())):
            if _is_interface_in_boundary_policy(clean_source_name, source_node_id, if_name, pol.get("isp_boundary_interfaces", [])):
                policy_boundary_ifaces.add(if_name)
                wan_signals_by_iface.setdefault(if_name, []).append("policy_isp_boundary")

        # Determine primary WAN boundary interface (requires explicit policy OR >=2 WAN indicators,
        # while keeping single default_route tracked as a routed upstream gateway without assuming ISP ownership)
        confirmed_boundary_ifaces: Set[str] = set(policy_boundary_ifaces)
        for if_name, sigs in wan_signals_by_iface.items():
            distinct_kinds = {s.split(":")[0] for s in sigs}
            if len(distinct_kinds) >= 2 or any(s.startswith("wan_tunnel:") for s in sigs):
                confirmed_boundary_ifaces.add(if_name)

        primary_wan_iface: Optional[str] = None
        if policy_boundary_ifaces:
            primary_wan_iface = sorted(policy_boundary_ifaces)[0]
        elif confirmed_boundary_ifaces:
            primary_wan_iface = sorted(confirmed_boundary_ifaces)[0]
        elif default_routes and default_routes[0].get("interface"):
            primary_wan_iface = default_routes[0]["interface"]

        wan_ssid = ""
        m_ssid = re.search(r'ssid[=:\s]+"?([^"\s\r\n]+)"?', sanitize_cli_excerpt(wireless_output, 2000), re.IGNORECASE)
        if m_ssid:
            wan_ssid = sanitize_untrusted_text(m_ssid.group(1).strip(), 64)

        wan_active = any(rt.get("active") for rt in default_routes) or any(
            dc.get("status") == "bound" for dc in dhcp_clients
        )

        metadata["role"] = "backbone" if (confirmed_boundary_ifaces or hop_depth == 0) else "distribution"
        metadata["internet_status"] = "online" if wan_active else "no_default_route"
        if primary_wan_iface:
            metadata["wan_interface"] = primary_wan_iface
        if wan_ssid:
            metadata["wan_ssid"] = wan_ssid
        if bridge_ports:
            metadata["bridge_ports"] = list(bridge_ports.values())

        # Reconcile Interrogated Source Node
        seed_scope = "enterprise_edge" if confirmed_boundary_ifaces else "enterprise_internal"
        seed_zone = "edge" if confirmed_boundary_ifaces else "internal"
        ex_x, ex_y = self._get_existing_position(source_node_id)

        interrogated_dev_type = classify_device_type_from_hints(
            f"{clean_source_name} {identity}", metadata.get("board", ""), "mikrotik"
        )
        if interrogated_dev_type not in ("router", "switch", "access_point"):
            interrogated_dev_type = "router"

        self._reconcile_discovered_node(
            node_id=source_node_id,
            name=clean_source_name,
            identity=identity,
            ip=clean_source_ip,
            mac=source_all_macs[0] if source_all_macs else "",
            device_type=interrogated_dev_type,
            device_role=metadata["role"],
            discovery_status="discovered",
            ownership_status="owned",
            topology_scope=seed_scope,
            trust_zone=seed_zone,
            confidence="high",
            confidence_reason="Authenticated SSH interrogation on registered inventory device.",
            ssh_ok=True,
            management_authorized=True,
            observability="fully_observable",
            observability_reason="Direct RouterOS read-only CLI telemetry collected.",
            source_device_id=source_node_id,
            serial_number=serial_number,
            all_ips=source_all_ips,
            all_macs=source_all_macs,
            vlans=vlans,
            pos_x=ex_x if ex_x is not None else 450.0,
            pos_y=ex_y if ex_y is not None else (210.0 + hop_depth * 180.0),
            metadata=metadata,
            now=now,
        )
        self.record_evidence(
            subject_type="node",
            subject_id=source_node_id,
            evidence_type="ssh_identity",
            protocol="ssh",
            observing_device_id=source_node_id,
            observed_endpoint=clean_source_ip or clean_source_name,
            directness="direct",
            confidence="high",
            explanation=f"Interrogated RouterOS identity '{identity}' via authorized SSH.",
            raw_excerpt=identity_output,
            observed_at=now,
        )

        # Build Bridge Host MAC -> physical port lookup & port multiplicity (to detect downstream switches/hubs)
        bridge_mac_to_port: Dict[str, str] = {}
        macs_per_port: Dict[str, Set[str]] = {}
        for bh in bridge_hosts:
            bmac = bh["mac"]
            bport = bh["interface"]
            if bmac and bport:
                bridge_mac_to_port[bmac] = bport
                macs_per_port.setdefault(bport, set()).add(bmac)

        arp_by_mac: Dict[str, Dict[str, Any]] = {a["mac"]: a for a in arp_entries if a.get("mac")}
        lease_by_mac: Dict[str, Dict[str, Any]] = {l["mac"]: l for l in dhcp_leases if l.get("mac")}
        lease_by_ip: Dict[str, Dict[str, Any]] = {l["ip"]: l for l in dhcp_leases if l.get("ip")}

        seen_macs: Set[str] = set(source_all_macs)
        seen_ips: Set[str] = set(source_all_ips)
        neighbor_node_ids_by_ip: Dict[str, str] = {}
        downstream_candidates: List[Dict[str, Any]] = []
        child_render_queue: List[Dict[str, Any]] = []

        # 3. Process Direct Layer 2 / VPN Neighbors (MNDP / LLDP / CDP)
        approved_protos = {p.lower() for p in pol.get("approved_discovery_protocols", ["mndp", "lldp", "cdp", "arp", "route"])}
        for n in neighbors:
            proto = n.get("_protocol", "mndp")
            if approved_protos and proto not in approved_protos and not approved_protos.intersection({"mndp", "lldp", "cdp"}):
                continue

            n_mac = normalize_mac(n.get("mac-address", ""))
            arp_match = arp_by_mac.get(n_mac)
            n_ip = normalize_ip(n.get("address", "")) or (arp_match["ip"] if arp_match else "")

            # Enforce subnet exclusion: record observation in review/conflicts if excluded, do not import as active internal
            if n_ip and ip_in_subnets(n_ip, pol.get("excluded_subnets", [])):
                self.record_conflict(
                    conflict_type="excluded_subnet_observation",
                    subject_id=f"excluded:{n_ip}",
                    candidate_data={"ip": n_ip, "mac": n_mac, "identity": n.get("identity", ""), "source": source_node_id},
                    reason=f"Neighbor {n_ip} falls within excluded_subnets policy and was skipped.",
                    now=now,
                )
                continue

            raw_local_if = n.get("interface", "")
            local_port, is_bridge_only = extract_physical_port_name(raw_local_if)
            used_bridge_table = False
            if is_bridge_only and n_mac and n_mac in bridge_mac_to_port:
                local_port = bridge_mac_to_port[n_mac]
                is_bridge_only = False
                used_bridge_table = True

            # CRITICAL: Never invent 'eth0' when remote interface is absent!
            raw_remote_if = (n.get("interface-name") or n.get("port-id") or n.get("to-interface") or "").strip()
            remote_port, _ = extract_physical_port_name(raw_remote_if) if raw_remote_if else ("", False)

            raw_ident = sanitize_untrusted_text(n.get("identity") or n.get("system-description") or "", 64)
            n_board = sanitize_untrusted_text(n.get("board") or "", 64)
            n_platform = sanitize_untrusted_text(n.get("platform") or "", 64)
            n_version = sanitize_untrusted_text(n.get("version") or "", 64)
            n_caps = sanitize_untrusted_text(n.get("system-caps") or "", 64)

            if not raw_ident:
                if arp_match and lease_by_mac.get(n_mac, {}).get("hostname"):
                    raw_ident = lease_by_mac[n_mac]["hostname"]
                else:
                    raw_ident = f"Neighbor-{local_port or 'port'} ({n_ip})" if n_ip else f"Neighbor-{n_mac[-5:] or 'unknown'}"
            elif raw_ident.lower() == "mikrotik" and n_board:
                raw_ident = f"MikroTik ({n_board})"

            dev_type = classify_device_type_from_hints(raw_ident, n_board, n_platform, n_caps)

            # Resolve stable candidate node ID (detecting conflicts without overwriting unrelated devices)
            fallback_slug = re.sub(r"[^a-zA-Z0-9_]", "_", (n_mac or f"{raw_ident}_{n_ip}").lower())
            target_node_id, conflict_detected = self._resolve_neighbor_node_id(
                preferred_id=f"node_{fallback_slug}",
                mac=n_mac,
                ip=n_ip,
                identity=raw_ident,
                board=n_board,
                now=now,
            )

            # Classify Ownership, Scope, and Trust Zone (Principle 2.1: Discovery != Ownership!)
            if_info = interfaces_map.get(local_port, {})
            is_vpn = is_vpn_or_tunnel_interface(local_port, if_info.get("type", ""))
            on_isp_boundary = (
                local_port in confirmed_boundary_ifaces
                or raw_local_if in confirmed_boundary_ifaces
                or _is_interface_in_boundary_policy(clean_source_name, source_node_id, local_port, pol.get("isp_boundary_interfaces", []))
            )

            is_known_isp = _matches_device_list(
                pol.get("known_isp_devices", []), ip=n_ip, mac=n_mac, identity=raw_ident, node_id=target_node_id
            )
            is_known_ext = _matches_device_list(
                pol.get("known_external_devices", []), ip=n_ip, mac=n_mac, identity=raw_ident, node_id=target_node_id
            )
            inv_match = (inv_by_ip.get(n_ip) if n_ip else None) or inv_by_name.get(raw_ident.lower())

            if is_known_isp:
                ownership = "third_party"
                scope = "isp_upstream"
                zone = "isp"
                disc_status = "discovered"
                conf = "high"
                conf_reason = "Matched configured known_isp_devices boundary list."
            elif is_known_ext:
                ownership = "third_party"
                scope = "external"
                zone = "external"
                disc_status = "discovered"
                conf = "high"
                conf_reason = "Matched configured known_external_devices list."
            elif on_isp_boundary:
                # Neighbor on ISP boundary port is NEVER automatically owned!
                ownership = "unknown"
                scope = "isp_upstream"
                zone = "isp"
                disc_status = "pending_review" if pol.get("require_review_for_unknown_devices", True) else "discovered"
                conf = "medium"
                conf_reason = f"Observed via {proto.upper()} on WAN/ISP boundary interface '{local_port}'; ownership unverified."
            elif is_vpn:
                ownership = "owned" if inv_match else "unknown"
                scope = "vpn_remote"
                zone = "vpn"
                disc_status = "discovered" if inv_match else ("pending_review" if pol.get("require_review_for_unknown_devices", True) else "discovered")
                conf = "high" if inv_match else "medium"
                conf_reason = f"Observed over VPN/tunnel interface '{local_port}'."
            elif inv_match:
                ownership = "owned"
                scope = "enterprise_internal"
                zone = "internal"
                disc_status = "discovered"
                conf = "high"
                conf_reason = f"Matched authorized enterprise inventory device '{inv_match.get('name')}'."
            else:
                ownership = "unknown"
                scope = "unclassified"
                zone = "unknown"
                disc_status = "pending_review" if pol.get("require_review_for_unknown_devices", True) else "discovered"
                conf = "medium"
                conf_reason = f"Discovered via {proto.upper()} neighbor advertisement; ownership requires administrator confirmation."

            if not pol.get("auto_include_unknown_neighbors", True) and ownership == "unknown":
                self.record_conflict(
                    conflict_type="unclassified_neighbor_held",
                    subject_id=target_node_id,
                    candidate_data={"name": raw_ident, "ip": n_ip, "mac": n_mac, "local_port": local_port, "remote_port": remote_port},
                    reason="Held from active graph because auto_include_unknown_neighbors=False.",
                    now=now,
                )
                continue

            if n_mac:
                seen_macs.add(n_mac)
            if n_ip:
                seen_ips.add(n_ip)
                neighbor_node_ids_by_ip[n_ip] = target_node_id

            # Observability indicator for switches / downstream routers
            if dev_type in ("switch", "router", "access_point"):
                if inv_match:
                    obs_cap = "partially_observable"
                    obs_reason = "Registered in inventory; run enterprise_managed discovery to interrogate downstream ports."
                elif ownership in ("third_party", "unknown") and scope == "isp_upstream":
                    obs_cap = "not_attempted"
                    obs_reason = "Outside enterprise internal scope (ISP/edge boundary); recursive interrogation blocked by policy."
                else:
                    obs_cap = "not_observable" if not n_ip else "not_attempted"
                    obs_reason = (
                        "No management IP configured on neighbor; add management IP & inventory credentials to inspect downstream ports."
                        if not n_ip
                        else "Device not authorized in inventory; downstream ports behind this device are not interrogated."
                    )
            else:
                obs_cap = "not_attempted"
                obs_reason = "End-host or non-managed endpoint."

            ev_type = f"{proto}_neighbor"
            child_render_queue.append({
                "node_id": target_node_id,
                "name": inv_match["name"] if inv_match else raw_ident,
                "identity": raw_ident,
                "ip": n_ip,
                "mac": n_mac,
                "device_type": dev_type,
                "device_role": "isp_cpe" if scope == "isp_upstream" else ("access" if dev_type in ("switch", "access_point") else "neighbor"),
                "discovery_status": disc_status,
                "ownership_status": ownership,
                "topology_scope": scope,
                "trust_zone": zone,
                "confidence": "low" if conflict_detected else conf,
                "confidence_reason": conf_reason,
                "management_authorized": bool(inv_match),
                "observability": obs_cap,
                "observability_reason": obs_reason,
                "metadata": {
                    "discovered_via": clean_source_name,
                    "discovery_protocol": proto.upper(),
                    "platform": n_platform,
                    "board": n_board,
                    "version": n_version,
                    "remote_port": remote_port,
                },
                "node_evidence": [
                    {
                        "evidence_type": ev_type,
                        "protocol": proto,
                        "local_interface": local_port,
                        "remote_interface": remote_port,
                        "directness": "direct",
                        "confidence": "high" if proto in ("lldp", "cdp") else "medium",
                        "explanation": f"Observed via {proto.upper()} on {clean_source_name}:{local_port or raw_local_if}.",
                        "raw_excerpt": n.get("_raw", ""),
                    }
                ],
                "link_spec": {
                    "local_port": local_port,
                    "remote_port": remote_port,
                    "is_vpn": is_vpn,
                    "is_wireless": "wlan" in local_port.lower() or "wifi" in local_port.lower(),
                    "is_bridge_only": is_bridge_only,
                    "used_bridge_table": used_bridge_table,
                    "protocol": proto,
                    "ev_type": ev_type,
                    "raw_excerpt": n.get("_raw", ""),
                },
            })

            can_expand_managed = (
                inv_match
                and ownership == "owned"
                and scope == "enterprise_internal"
            )
            can_expand_authorized = (
                inv_match
                and pol.get("discovery_mode") == "authorized_expansion"
                and pol.get("allow_routed_expansion", False)
                and scope in ("enterprise_internal", "vpn_remote", "enterprise_edge")
                and bool(n_ip and ip_in_subnets(n_ip, pol.get("approved_discovery_scopes", [])))
            )
            if (can_expand_managed or can_expand_authorized) and not (
                n_ip and ip_in_subnets(n_ip, pol.get("excluded_subnets", []))
            ):
                downstream_candidates.append({
                    "device_name": inv_match["name"],
                    "host": inv_match["host"],
                    "node_id": target_node_id,
                })

        # 4. Process Upstream Routed Gateways (Default Routes 0.0.0.0/0 NOT already represented by an L2 neighbor)
        if not approved_protos or "route" in approved_protos:
            for rt in default_routes:
                gw_ip = rt.get("gateway_ip", "")
                rt_if = rt.get("interface") or primary_wan_iface or ""
                if gw_ip and ip_in_subnets(gw_ip, pol.get("excluded_subnets", [])):
                    continue

                # If gateway IP already corresponds to a discovered neighbor, attach route_entry evidence to it,
                # NEVER overwrite its link or ownership with naive assumptions!
                if gw_ip and gw_ip in neighbor_node_ids_by_ip:
                    existing_nid = neighbor_node_ids_by_ip[gw_ip]
                    self.record_evidence(
                        subject_type="node",
                        subject_id=existing_nid,
                        evidence_type="route_entry",
                        protocol="routing_table",
                        observing_device_id=source_node_id,
                        observed_endpoint=gw_ip,
                        local_interface=rt_if,
                        directness="indirect",
                        confidence="medium",
                        explanation=f"Default route 0.0.0.0/0 points to next-hop {gw_ip} via {rt_if or 'unspecified'}.",
                        raw_excerpt=rt.get("raw", ""),
                        observed_at=now,
                    )
                    continue

                # Otherwise create/update a routed gateway node (Principle 2.3 & Test #3, #9, #18):
                # Default route alone does NOT prove ISP ownership and NEVER creates a physical cable!
                is_known_isp_gw = _matches_device_list(pol.get("known_isp_devices", []), ip=gw_ip)
                on_confirmed_wan = bool(rt_if and rt_if in confirmed_boundary_ifaces)

                gw_node_id = f"node_gw_{re.sub(r'[^a-zA-Z0-9_]', '_', gw_ip or rt_if or 'default')}"
                if is_known_isp_gw:
                    gw_own = "third_party"
                    gw_scope = "isp_upstream"
                    gw_zone = "isp"
                    gw_conf = "high"
                    gw_reason = f"Gateway {gw_ip} matches configured known_isp_devices."
                elif on_confirmed_wan:
                    gw_own = "unknown"
                    gw_scope = "isp_upstream"
                    gw_zone = "isp"
                    gw_conf = "medium"
                    gw_reason = f"Next-hop gateway on WAN boundary interface '{rt_if}'; ISP vs third-party ownership unverified."
                else:
                    gw_own = "unknown"
                    gw_scope = "unclassified"
                    gw_zone = "unknown"
                    gw_conf = "low"
                    gw_reason = "Inferred solely from 0.0.0.0/0 default route; neither physical link nor ISP ownership is proven."

                gw_label = (
                    f"Upstream Gateway ({gw_ip})"
                    if gw_ip
                    else (f"WAN Uplink ({wan_ssid})" if wan_ssid else f"Upstream Route ({rt_if or '0.0.0.0/0'})")
                )
                gw_x, gw_y = self._get_existing_position(gw_node_id)
                self._reconcile_discovered_node(
                    node_id=gw_node_id,
                    name=gw_label,
                    identity=gw_label,
                    ip=gw_ip,
                    mac=next((a["mac"] for a in arp_entries if a["ip"] == gw_ip), ""),
                    device_type="wan" if (is_known_isp_gw or on_confirmed_wan) else "router",
                    device_role="upstream_gateway",
                    discovery_status="discovered",
                    ownership_status=gw_own,
                    topology_scope=gw_scope,
                    trust_zone=gw_zone,
                    confidence=gw_conf,
                    confidence_reason=gw_reason,
                    ssh_ok=None,
                    management_authorized=False,
                    observability="not_attempted",
                    observability_reason="Upstream next-hop route target; not authorized for SSH interrogation.",
                    source_device_id=source_node_id,
                    pos_x=gw_x if gw_x is not None else 450.0,
                    pos_y=gw_y if gw_y is not None else 45.0,
                    metadata={"role": "upstream_gateway", "connected_via": rt_if, "ssid": wan_ssid},
                    now=now,
                    evidence_batch=[
                        {
                            "evidence_type": "route_entry",
                            "protocol": "routing_table",
                            "local_interface": rt_if,
                            "remote_interface": "",
                            "directness": "indirect",
                            "confidence": "medium" if rt.get("active") else "low",
                            "explanation": f"Next-hop gateway from route 0.0.0.0/0 via {rt_if or 'routing table'}.",
                            "raw_excerpt": rt.get("raw", ""),
                        }
                    ],
                )
                self._reconcile_discovered_link(
                    source_id=source_node_id,
                    target_id=gw_node_id,
                    local_port=rt_if,
                    remote_port="",
                    link_type="wireless" if (rt_if and "wlan" in rt_if.lower()) else "routed",
                    verification_status="inferred",
                    confidence="low",
                    confidence_reason="Logical next-hop relationship from routing table; does not prove direct physical cabling.",
                    oper_status="up" if rt.get("active") else "down",
                    bandwidth="Routed Next-Hop",
                    evidence_item={
                        "evidence_type": "route_entry",
                        "protocol": "routing_table",
                        "local_interface": rt_if,
                        "remote_interface": "",
                        "directness": "indirect",
                        "confidence": "low",
                        "explanation": f"Inferred next-hop reachability to {gw_ip or gw_label}.",
                        "raw_excerpt": rt.get("raw", ""),
                    },
                    now=now,
                )
                if gw_ip:
                    seen_ips.add(gw_ip)

        # 5. Process End-Host Observations from ARP + DHCP Leases + Bridge Host Table
        # CRITICAL (Section 6.2 & Tests #10, #16): ARP/DHCP NEVER creates confirmed physical links
        # and NEVER independently proves 'reachable' online status!
        if not approved_protos or "arp" in approved_protos:
            for arp in arp_entries:
                a_ip = arp["ip"]
                a_mac = arp["mac"]
                a_iface_raw = arp["interface"]

                if not a_ip or a_ip in seen_ips or (a_mac and a_mac in seen_macs):
                    continue
                if ip_in_subnets(a_ip, pol.get("excluded_subnets", [])):
                    continue

                local_port, is_bridge = extract_physical_port_name(a_iface_raw)
                has_bridge_port = False
                if a_mac and a_mac in bridge_mac_to_port:
                    local_port = bridge_mac_to_port[a_mac]
                    is_bridge = False
                    has_bridge_port = True

                on_isp_boundary = local_port in confirmed_boundary_ifaces or a_iface_raw in confirmed_boundary_ifaces
                if on_isp_boundary and not pol.get("auto_include_unknown_neighbors", True):
                    continue

                lease = lease_by_mac.get(a_mac) or lease_by_ip.get(a_ip)
                hostname = lease["hostname"] if (lease and lease.get("hostname")) else ""
                rand_mac = is_randomized_or_local_mac(a_mac)

                # Stable ID: prefer non-randomized MAC over mutable IP so DHCP renewals don't duplicate nodes!
                if a_mac and not rand_mac:
                    pref_id = f"node_mac_{re.sub(r'[^a-zA-Z0-9_]', '_', a_mac.lower())}"
                else:
                    pref_id = f"node_host_{re.sub(r'[^a-zA-Z0-9_]', '_', (hostname or a_ip).lower())}"

                target_node_id, _ = self._resolve_neighbor_node_id(
                    preferred_id=pref_id,
                    mac="" if rand_mac else a_mac,
                    ip=a_ip,
                    identity=hostname,
                    board="",
                    now=now,
                )

                seen_ips.add(a_ip)
                if a_mac:
                    seen_macs.add(a_mac)

                disp_name = hostname or f"Host-{local_port or 'lan'} ({a_ip})"
                ev_batch = [
                    {
                        "evidence_type": "arp_entry",
                        "protocol": "arp",
                        "local_interface": local_port or a_iface_raw,
                        "remote_interface": "",
                        "directness": "indirect",
                        "confidence": "low",
                        "explanation": f"ARP cache entry ({'dynamic' if arp.get('dynamic') else 'static'}) on {a_iface_raw}; may traverse downstream switch/AP.",
                        "raw_excerpt": arp.get("raw", ""),
                    }
                ]
                if lease:
                    ev_batch.append({
                        "evidence_type": "dhcp_lease",
                        "protocol": "dhcp",
                        "local_interface": local_port or a_iface_raw,
                        "remote_interface": "",
                        "directness": "indirect",
                        "confidence": "medium",
                        "explanation": f"DHCP lease hostname='{hostname or 'none'}' status='{lease.get('status', '')}'.",
                        "raw_excerpt": lease.get("raw", ""),
                    })
                if has_bridge_port:
                    multi_mac_count = len(macs_per_port.get(local_port, set()))
                    ev_batch.append({
                        "evidence_type": "bridge_host_table",
                        "protocol": "bridge_fdb",
                        "local_interface": local_port,
                        "remote_interface": "",
                        "directness": "indirect" if multi_mac_count > 1 else "direct",
                        "confidence": "low" if multi_mac_count > 1 else "medium",
                        "explanation": (
                            f"MAC learned on bridge port {local_port} alongside {multi_mac_count - 1} other MAC(s) (downstream switch/AP likely)."
                            if multi_mac_count > 1
                            else f"MAC learned on bridge port {local_port}."
                        ),
                        "raw_excerpt": "",
                    })

                inv_match = inv_by_ip.get(a_ip)
                child_render_queue.append({
                    "node_id": target_node_id,
                    "name": inv_match["name"] if inv_match else disp_name,
                    "identity": hostname or f"ARP Host ({a_ip})",
                    "ip": a_ip,
                    "mac": a_mac,
                    "device_type": "client",
                    "device_role": "end_host",
                    "discovery_status": "discovered" if inv_match else ("pending_review" if pol.get("require_review_for_unknown_devices", True) else "candidate"),
                    "ownership_status": "owned" if inv_match else "unknown",
                    "topology_scope": "isp_upstream" if on_isp_boundary else ("enterprise_internal" if inv_match else "unclassified"),
                    "trust_zone": "isp" if on_isp_boundary else ("internal" if inv_match else "unknown"),
                    "confidence": "low",
                    "confidence_reason": (
                        "Observed via ARP/DHCP only (locally-administered/randomized MAC detected)."
                        if rand_mac
                        else "Observed via Layer 3 ARP table; ownership and physical switch port are unverified."
                    ),
                    "management_authorized": bool(inv_match),
                    "observability": "not_observable",
                    "observability_reason": "End-host observed via ARP; does not expose L2 topology MIBs.",
                    "metadata": {
                        "discovered_via": clean_source_name,
                        "discovery_protocol": "ARP+DHCP" if lease else "ARP",
                        "interface": local_port or a_iface_raw,
                        "randomized_mac": rand_mac,
                        "arp_published_proxy": bool(arp.get("published")),
                    },
                    "node_evidence": ev_batch,
                    "link_spec": {
                        "local_port": local_port or a_iface_raw,
                        "remote_port": "",  # Never invent 'NIC' or 'eth0'!
                        "is_arp_only": True,
                        "has_bridge_port": has_bridge_port,
                        "ev_type": "bridge_host_table" if has_bridge_port else "arp_entry",
                        "protocol": "bridge_fdb" if has_bridge_port else "arp",
                        "raw_excerpt": arp.get("raw", ""),
                    },
                })

        # 6. Persist Reconciled Child Nodes & Classified Links
        nodes_processed = 0
        links_processed = 0
        total_children = len(child_render_queue)

        for idx, item in enumerate(child_render_queue):
            cid = item["node_id"]
            cx, cy = self._get_existing_position(cid)
            if cx is None or cy is None:
                spacing = 215.0
                start_x = 450.0 - ((total_children - 1) * spacing) / 2.0
                cx = max(80.0, start_x + idx * spacing)
                cy = 390.0 + hop_depth * 180.0

            self._reconcile_discovered_node(
                node_id=cid,
                name=item["name"],
                identity=item["identity"],
                ip=item["ip"],
                mac=item["mac"],
                device_type=item["device_type"],
                device_role=item["device_role"],
                discovery_status=item["discovery_status"],
                ownership_status=item["ownership_status"],
                topology_scope=item["topology_scope"],
                trust_zone=item["trust_zone"],
                confidence=item["confidence"],
                confidence_reason=item["confidence_reason"],
                ssh_ok=None,
                management_authorized=item["management_authorized"],
                observability=item["observability"],
                observability_reason=item["observability_reason"],
                source_device_id=source_node_id,
                all_ips=[item["ip"]] if item["ip"] else [],
                all_macs=[item["mac"]] if item["mac"] else [],
                pos_x=cx,
                pos_y=cy,
                metadata=item["metadata"],
                now=now,
                evidence_batch=item["node_evidence"],
            )
            nodes_processed += 1

            ls = item["link_spec"]
            if ls.get("is_arp_only"):
                l_type = "inferred"
                v_status = "inferred"
                l_conf = "low"
                l_reason = (
                    f"Inferred reachability via router interface '{ls['local_port']}' (ARP/FDB); "
                    "does not prove direct port-to-port Ethernet cabling."
                )
                bw = "Inferred L3/FDB"
            elif ls.get("is_vpn"):
                l_type = "vpn"
                v_status = "observed"
                l_conf = "medium"
                l_reason = f"Observed over logical VPN/tunnel interface '{ls['local_port']}'."
                bw = "VPN Tunnel"
            elif ls.get("is_wireless"):
                l_type = "wireless"
                v_status = "observed"
                l_conf = "medium" if ls["remote_port"] else "low"
                l_reason = "Observed wireless neighbor association."
                bw = "Wireless"
            else:
                # MNDP / LLDP / CDP Layer 2 neighbor
                l_type = "layer2_adjacency"
                v_status = "observed"
                if ls["remote_port"] and not ls.get("is_bridge_only"):
                    l_conf = "high" if ls["protocol"] in ("lldp", "cdp") else "medium"
                    l_reason = (
                        f"Single-sided {ls['protocol'].upper()} neighbor observation reporting "
                        f"{ls['local_port']} <-> {ls['remote_port']} (awaiting peer correlation or admin confirmation)."
                    )
                elif not ls["remote_port"]:
                    l_conf = "low"
                    l_reason = (
                        f"Neighbor observed on local port '{ls['local_port']}' via {ls['protocol'].upper()}, "
                        "but remote port identifier is missing; port-to-port wiring is incomplete."
                    )
                else:
                    l_conf = "low"
                    l_reason = (
                        f"Neighbor observed on multipoint bridge '{ls['local_port']}' without physical bridge-port mapping."
                    )
                bw = "1 Gbps" if "ether" in (ls["local_port"] or "").lower() else ("10 Gbps" if "sfp" in (ls["local_port"] or "").lower() else "")

            self._reconcile_discovered_link(
                source_id=source_node_id,
                target_id=cid,
                local_port=ls["local_port"],
                remote_port=ls["remote_port"],
                link_type=l_type,
                verification_status=v_status,
                confidence=l_conf,
                confidence_reason=l_reason,
                oper_status="up",
                bandwidth=bw,
                evidence_item={
                    "evidence_type": ls["ev_type"],
                    "protocol": ls["protocol"],
                    "local_interface": ls["local_port"],
                    "remote_interface": ls["remote_port"],
                    "directness": "indirect" if ls.get("is_arp_only") else "direct",
                    "confidence": l_conf,
                    "explanation": l_reason,
                    "raw_excerpt": ls.get("raw_excerpt", ""),
                },
                now=now,
            )
            links_processed += 1

        return {
            "success": True,
            "source_node": source_node_id,
            "neighbors_found": len(neighbors),
            "arp_hosts_found": len(arp_entries),
            "new_nodes_added": nodes_processed,
            "links_added": links_processed,
            "wan_interface": primary_wan_iface,
            "wan_active": wan_active,
            "downstream_candidates": downstream_candidates,
        }
