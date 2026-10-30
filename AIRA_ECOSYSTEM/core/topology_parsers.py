"""
core/topology_parsers.py — Read-only RouterOS v6/v7 CLI output parsers for AIRA Topology Fabric V2.
Preserves exact observed fields without fabricating missing ports or identities.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from core.topology_models import (
    normalize_ip,
    normalize_mac,
    sanitize_cli_excerpt,
    sanitize_untrusted_text,
)

_KV_RE = re.compile(r'([a-zA-Z0-9_\-]+)=(?:"([^"]*)"|(\S+))')


def _parse_kv_blocks(raw_output: str) -> List[Dict[str, str]]:
    """Splits RouterOS 'print detail' output into item dicts with flags."""
    if not raw_output or not raw_output.strip():
        return []
    lower = raw_output.lower()
    if "bad command name" in lower or "no such item" in lower or "syntax error" in lower:
        return []

    blocks: List[str] = []
    current: List[str] = []
    for line in raw_output.splitlines():
        s = line.rstrip()
        if not s or s.strip().startswith("Flags:") or s.strip().startswith("Columns:"):
            continue
        if re.match(r"^\s*\d+\s+", s):
            if current:
                blocks.append(" ".join(current))
            current = [s.strip()]
        elif current:
            current.append(s.strip())
    if current:
        blocks.append(" ".join(current))

    parsed: List[Dict[str, str]] = []
    for blk in blocks:
        m_head = re.match(r"^(\d+)\s+(?:([A-Za-z*]+)\s+(?=[a-zA-Z0-9_\-]+=))?(.*)$", blk)
        flags = ""
        body = blk
        if m_head:
            flags = m_head.group(2) or ""
            body = m_head.group(3) or ""

        item: Dict[str, str] = {"_flags": flags, "_raw": sanitize_cli_excerpt(blk, 450)}
        for m in _KV_RE.finditer(body):
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else m.group(3)
            item[key] = sanitize_untrusted_text(val, 256)
        if len(item) > 2:
            parsed.append(item)
    return parsed


def parse_mikrotik_identity(raw_output: str) -> Optional[str]:
    """
    Parses '/system identity print' or '/system identity print detail'.
    Handles standard RouterOS key-value or 'name: ...' lines, ignores banners and license texts.
    Returns cleaned identity string or None if unparseable / error.
    """
    if not raw_output or not raw_output.strip():
        return None
    lower = raw_output.lower()
    if "bad command name" in lower or "syntax error" in lower or "no such item" in lower:
        return None

    for line in raw_output.splitlines():
        s = line.strip()
        if not s or ("routeros" in s.lower() and "license" in s.lower()):
            continue
        # Format 1: name: "Router-Core" or name: Core-CCR
        m1 = re.match(r"^name\s*:\s*\"?([^\"\r\n]+)\"?$", s, re.IGNORECASE)
        if m1:
            val = m1.group(1).strip()
            if val and not val.lower().startswith("license"):
                return sanitize_untrusted_text(val, 64)

        # Format 2: 0 name="Router-Core" or name="Router-Core"
        m2 = re.search(r'\bname="([^"]+)"', s)
        if m2:
            val = m2.group(1).strip()
            if val:
                return sanitize_untrusted_text(val, 64)

        # Format 3: name=Router-Core (unquoted)
        m3 = re.search(r'\bname=([^\s"]+)', s)
        if m3:
            val = m3.group(1).strip()
            if val and not val.lower().startswith("license"):
                return sanitize_untrusted_text(val, 64)

    return None


def parse_mikrotik_resource(raw_output: str) -> Dict[str, Any]:
    """
    Parses '/system resource print' key: value lines.
    Returns dictionary with version, uptime, cpu_load_percent, board_name, architecture, memory, etc.
    """
    info: Dict[str, Any] = {}
    if not raw_output or not raw_output.strip():
        return info

    for line in raw_output.splitlines():
        s = line.strip()
        if not s or ":" not in s:
            continue
        parts = s.split(":", 1)
        k = parts[0].strip().lower().replace(" ", "-")
        v = parts[1].strip().strip('"')
        info[k] = v

    parsed: Dict[str, Any] = {}
    if "version" in info:
        ver_str = info["version"]
        m_ver = re.match(r"^([0-9]+(?:\.[0-9]+)+(?:[a-zA-Z0-9.\-]*)?)", ver_str)
        parsed["version"] = m_ver.group(1) if m_ver else ver_str.split()[0]
        parsed["version_raw"] = ver_str
    if "uptime" in info:
        parsed["uptime"] = info["uptime"]
        from core.nms_models import parse_uptime_to_seconds
        parsed["uptime_seconds"] = parse_uptime_to_seconds(info["uptime"])
    if "cpu-load" in info:
        m_cpu = re.search(r"(\d+(?:\.\d+)?)", info["cpu-load"])
        if m_cpu:
            parsed["cpu_load_percent"] = float(m_cpu.group(1))
    if "board-name" in info:
        parsed["board_name"] = info["board-name"]
    if "architecture-name" in info:
        parsed["architecture"] = info["architecture-name"]
    if "platform" in info:
        parsed["platform"] = info["platform"]

    def _parse_bytes(s_val: str) -> Optional[int]:
        m = re.search(r"([0-9.]+)\s*([a-zA-Z]+)?", s_val)
        if not m:
            return None
        num = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if "gib" in unit or "gb" in unit:
            return int(num * 1024 * 1024 * 1024)
        if "mib" in unit or "mb" in unit:
            return int(num * 1024 * 1024)
        if "kib" in unit or "kb" in unit:
            return int(num * 1024)
        return int(num)

    if "total-memory" in info:
        parsed["total_memory_bytes"] = _parse_bytes(info["total-memory"])
    if "free-memory" in info:
        parsed["free_memory_bytes"] = _parse_bytes(info["free-memory"])
    if parsed.get("total_memory_bytes") and parsed.get("free_memory_bytes"):
        used = parsed["total_memory_bytes"] - parsed["free_memory_bytes"]
        parsed["used_memory_bytes"] = max(0, used)
        parsed["memory_used_percent"] = round((used / parsed["total_memory_bytes"]) * 100.0, 1)

    return parsed


def parse_speed_to_bps(speed_str: str) -> Optional[int]:
    """Parses speed strings such as '10Gbps', '1Gbps', '100Mbps', '10Mbps', '2.5Gbps' to bps."""
    if not speed_str:
        return None
    s = speed_str.strip().lower()
    if s in ("auto", "unknown", "none", "0"):
        return None
    m = re.search(r"([0-9.]+)\s*([gmk]?)bps?", s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "g":
        return int(val * 1_000_000_000)
    elif unit == "m":
        return int(val * 1_000_000)
    elif unit == "k":
        return int(val * 1_000)
    return int(val)


def parse_mikrotik_ethernet(raw_output: str) -> Dict[str, Dict[str, Any]]:
    """
    Parses '/interface ethernet print detail' into {iface_name: eth_info}.
    Extracts actual negotiated link speed, duplex mode, auto-negotiation, and running state.
    """
    ethernet: Dict[str, Dict[str, Any]] = {}
    if not raw_output or not raw_output.strip():
        return ethernet

    kv_items = _parse_kv_blocks(raw_output)
    if kv_items:
        for it in kv_items:
            name = it.get("name", "")
            if not name:
                continue
            flags = it.get("_flags", "")
            running = ("R" in flags) or (it.get("running") == "yes") or (it.get("status") == "link-ok")
            disabled = ("X" in flags) or (it.get("disabled") == "yes")
            full_duplex = it.get("full-duplex") == "yes"
            auto_neg = it.get("auto-negotiation") == "yes"

            speed_raw = it.get("speed") or it.get("rate") or ""
            parsed_speed = parse_speed_to_bps(speed_raw) if speed_raw else None

            # If interface is NOT running (no link) or disabled, negotiated speed is None
            negotiated_speed_bps = parsed_speed if (running and not disabled) else None
            speed_source = "routeros_ethernet_negotiated" if negotiated_speed_bps is not None else "unknown"

            ethernet[name] = {
                "name": name,
                "running": running,
                "disabled": disabled,
                "duplex": "full" if full_duplex else ("half" if (running and not disabled) else "unknown"),
                "auto_negotiation": auto_neg,
                "speed_raw": speed_raw,
                "negotiated_speed_bps": negotiated_speed_bps,
                "speed_source": speed_source,
                "mac": normalize_mac(it.get("mac-address") or it.get("orig-mac-address", "")),
            }
        return ethernet

    # Fallback for tabular '/interface ethernet print'
    for line in raw_output.splitlines():
        line_str = line.strip()
        if not line_str or line_str.startswith("Flags:") or line_str.startswith("#"):
            continue
        # Pattern: index [flags] name [mtu] [mac] [auto-neg] [rate/speed] [full-duplex]
        m = re.match(r"^\d+\s+([XRS\s]*)\s+([a-zA-Z0-9_\-\.]+)\s+(?:(\d+)\s+)?(?:([0-9A-Fa-f:]{17})\s+)?(?:(yes|no)\s+)?([0-9]+[MGKmgkTt]bps|[0-9]+[MGKmgkTt]|auto)?(?:\s+(yes|no))?", line_str)
        if m:
            flags_str = m.group(1).strip()
            name = m.group(2).strip()
            auto_neg_str = m.group(5)
            rate_str = m.group(6) or ""
            duplex_str = m.group(7)
            running = "R" in flags_str
            disabled = "X" in flags_str
            parsed_speed = parse_speed_to_bps(rate_str) if rate_str and rate_str != "auto" else None
            negotiated_speed_bps = parsed_speed if (running and not disabled) else None
            speed_source = "routeros_ethernet_negotiated" if negotiated_speed_bps is not None else "unknown"
            ethernet[name] = {
                "name": name,
                "running": running,
                "disabled": disabled,
                "duplex": "full" if duplex_str == "yes" else ("half" if (running and not disabled) else "unknown"),
                "auto_negotiation": auto_neg_str == "yes",
                "speed_raw": rate_str,
                "negotiated_speed_bps": negotiated_speed_bps,
                "speed_source": speed_source,
                "mac": normalize_mac(m.group(4) or ""),
            }

    return ethernet


def parse_mikrotik_routerboard(raw_output: str) -> Dict[str, str]:
    """Parses '/system routerboard print' key: value lines."""
    info: Dict[str, str] = {}
    if not raw_output:
        return info
    for line in raw_output.splitlines():
        m = re.match(r"^\s*([a-zA-Z0-9_\-]+)\s*:\s*(.+?)\s*$", line)
        if m:
            info[m.group(1).lower()] = sanitize_untrusted_text(m.group(2).strip('"'), 128)
    return info


def parse_mikrotik_neighbors(raw_output: str) -> List[Dict[str, str]]:
    """
    Parses '/ip neighbor print detail' across RouterOS v6 and v7.
    Infers discovery protocol ('mndp', 'lldp', 'cdp') from available fields without inventing ports.
    """
    items = _parse_kv_blocks(raw_output)
    results: List[Dict[str, str]] = []
    for item in items:
        if not (item.get("identity") or item.get("mac-address") or item.get("address")):
            continue
        item["mac-address"] = normalize_mac(item.get("mac-address", ""))
        if item.get("address"):
            item["address"] = normalize_ip(item.get("address")) or item["address"]

        # Determine underlying discovery protocol evidence
        discovered_by = (item.get("discovered-by") or "").lower()
        if "lldp" in discovered_by:
            proto = "lldp"
        elif "cdp" in discovered_by:
            proto = "cdp"
        elif "mndp" in discovered_by:
            proto = "mndp"
        elif item.get("system-caps") or item.get("system-description"):
            # RouterOS populates system-caps / system-description from LLDP TLVs when LLDP is active
            proto = "lldp" if not item.get("unpack") else "mndp"
        elif "cisco" in (item.get("platform") or "").lower():
            proto = "cdp"
        else:
            proto = "mndp"

        item["_protocol"] = proto
        results.append(item)
    return results


def parse_mikrotik_arp(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/ip arp print detail' or tabular '/ip arp print'."""
    if not raw_output or not raw_output.strip():
        return []

    entries: List[Dict[str, Any]] = []
    kv_items = _parse_kv_blocks(raw_output)
    if kv_items:
        for it in kv_items:
            flags = it.get("_flags", "")
            if "I" in flags or it.get("invalid") == "yes" or it.get("disabled") == "yes":
                continue
            ip_val = normalize_ip(it.get("address"))
            mac_val = normalize_mac(it.get("mac-address"))
            if ip_val and mac_val:
                entries.append({
                    "ip": ip_val,
                    "mac": mac_val,
                    "interface": sanitize_untrusted_text(it.get("interface", ""), 64),
                    "dynamic": ("D" in flags) or (it.get("dynamic") == "yes"),
                    "complete": ("C" in flags) or (it.get("complete") == "yes"),
                    "published": ("P" in flags) or (it.get("published") == "yes"),
                    "dhcp": ("H" in flags) or (it.get("DHCP") == "yes"),
                    "raw": it.get("_raw", ""),
                })
        if entries:
            return entries

    # Tabular fallback: 0 DC 192.168.0.254 54:E1:AD:93:31:AF ether1
    for line in raw_output.splitlines():
        s = line.strip()
        if not s or s.startswith("Flags:") or s.startswith("#"):
            continue
        m_tab = re.search(
            r"^\d+\s+([A-Za-z]*)\s+([0-9]{1,3}(?:\.[0-9]{1,3}){3})\s+([0-9A-Fa-f:]{17})\s+(\S+)",
            s,
        )
        if m_tab:
            flags, ip_addr, mac_addr, iface = m_tab.groups()
            if "I" in flags or "X" in flags:
                continue
            entries.append({
                "ip": normalize_ip(ip_addr),
                "mac": normalize_mac(mac_addr),
                "interface": sanitize_untrusted_text(iface, 64),
                "dynamic": "D" in flags,
                "complete": "C" in flags,
                "published": "P" in flags,
                "dhcp": "H" in flags,
                "raw": sanitize_cli_excerpt(s, 240),
            })
    return entries


def parse_mikrotik_interfaces(raw_output: str) -> Dict[str, Dict[str, Any]]:
    """Parses '/interface print detail' or '/interface print' into {iface_name: info}."""
    interfaces: Dict[str, Dict[str, Any]] = {}
    if not raw_output:
        return interfaces

    def _to_int(val: Any) -> Optional[int]:
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    kv_items = _parse_kv_blocks(raw_output)
    for it in kv_items:
        name = it.get("name", "")
        if not name:
            continue
        flags = it.get("_flags", "")
        running = ("R" in flags) or (it.get("running") == "yes")
        disabled = ("X" in flags) or (it.get("disabled") == "yes")

        interfaces[name] = {
            "name": name,
            "type": (it.get("type") or "ether").lower(),
            "mac": normalize_mac(it.get("mac-address", "")),
            "running": running,
            "disabled": disabled,
            "slave": ("S" in flags) or (it.get("slave") == "yes"),
            "rx_byte": _to_int(it.get("rx-byte")),
            "tx_byte": _to_int(it.get("tx-byte")),
            "rx_packet": _to_int(it.get("rx-packet")),
            "tx_packet": _to_int(it.get("tx-packet")),
            "rx_error": _to_int(it.get("rx-error")) or 0,
            "tx_error": _to_int(it.get("tx-error")) or 0,
            "rx_drop": _to_int(it.get("rx-drop")) or 0,
            "tx_drop": _to_int(it.get("tx-drop")) or 0,
            "raw": it.get("_raw", ""),
        }
    if interfaces:
        return interfaces

    # Tabular fallback: 0 R ether1 ether 1500
    for line in raw_output.splitlines():
        s = line.strip()
        m = re.match(r"^\d+\s+([A-Za-z]*)\s+(\S+)\s+(\S+)", s)
        if m:
            flags, name, if_type = m.groups()
            if "=" in name:
                continue
            interfaces[name] = {
                "name": sanitize_untrusted_text(name, 64),
                "type": sanitize_untrusted_text(if_type.lower(), 32),
                "mac": "",
                "running": "R" in flags,
                "disabled": "X" in flags,
                "slave": "S" in flags,
                "rx_byte": None,
                "tx_byte": None,
                "rx_packet": None,
                "tx_packet": None,
                "rx_error": 0,
                "tx_error": 0,
                "rx_drop": 0,
                "tx_drop": 0,
                "raw": sanitize_cli_excerpt(s, 240),
            }
    return interfaces


def parse_mikrotik_addresses(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/ip address print detail' or tabular '/ip address print'."""
    results: List[Dict[str, Any]] = []
    if not raw_output:
        return results

    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        if "X" in flags or "I" in flags:
            continue
        addr_cidr = it.get("address", "")
        ip_only = normalize_ip(addr_cidr)
        if ip_only:
            results.append({
                "cidr": addr_cidr,
                "ip": ip_only,
                "network": it.get("network", ""),
                "interface": it.get("actual-interface") or it.get("interface", ""),
                "dynamic": "D" in flags,
                "raw": it.get("_raw", ""),
            })
    if results:
        return results

    for line in raw_output.splitlines():
        s = line.strip()
        m = re.match(r"^\d+\s+([A-Za-z]*)\s+([0-9.]+/\d+)\s+([0-9.]+)\s+(\S+)", s)
        if m:
            flags, cidr, net, iface = m.groups()
            if "X" in flags or "I" in flags:
                continue
            results.append({
                "cidr": cidr,
                "ip": normalize_ip(cidr),
                "network": net,
                "interface": sanitize_untrusted_text(iface, 64),
                "dynamic": "D" in flags,
                "raw": sanitize_cli_excerpt(s, 240),
            })
    return results


def parse_mikrotik_routes(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/ip route print detail' or tabular '/ip route print'."""
    routes: List[Dict[str, Any]] = []
    if not raw_output:
        return routes

    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        dst = it.get("dst-address", "")
        gw = it.get("gateway", "")
        gw_status = it.get("gateway-status", "") or it.get("immediate-gw", "")
        active = ("A" in flags) or ("active" in gw_status.lower()) or ("reachable" in gw_status.lower())
        connected = ("C" in flags) or ("connect" in flags.lower())

        iface = it.get("interface", "")
        # Extract egress interface from gateway-status ("192.168.1.1 reachable via ether1") or immediate-gw ("192.168.1.1%ether1")
        if not iface:
            m_via = re.search(r"(?:via|%)\s*([a-zA-Z0-9_.\-]+)", gw_status + " " + gw)
            if m_via:
                iface = m_via.group(1)
            elif gw and not normalize_ip(gw):
                iface = gw.split(",")[0].strip()

        routes.append({
            "dst": dst,
            "gateway_ip": normalize_ip(gw),
            "gateway_raw": gw,
            "interface": sanitize_untrusted_text(iface, 64),
            "active": active,
            "connected": connected,
            "raw": it.get("_raw", ""),
        })
    if routes:
        return routes

    # Tabular fallback
    for line in raw_output.splitlines():
        s = line.strip()
        if not s or s.startswith("Flags:") or s.startswith("#"):
            continue
        m_def = re.search(r"^\d+\s+([A-Za-z+]*)\s+(\S+)\s+(\S+)", s)
        if m_def:
            flags, dst, gw = m_def.groups()
            gw_ip = normalize_ip(gw)
            iface = ""
            m_if = re.search(r"(?:via|%)\s*([a-zA-Z0-9_.\-]+)", s)
            if m_if:
                iface = m_if.group(1)
            elif not gw_ip and "/" not in gw:
                iface = gw
            else:
                m_tail = re.search(r"\b(wlan\d+|ether\d+|sfp\S*|pppoe\S*|lte\d+|wg\S*|ovpn\S*|l2tp\S*)\b", s, re.IGNORECASE)
                if m_tail:
                    iface = m_tail.group(1)
            routes.append({
                "dst": dst,
                "gateway_ip": gw_ip,
                "gateway_raw": gw,
                "interface": sanitize_untrusted_text(iface, 64),
                "active": "A" in flags or "reachable" in s.lower(),
                "connected": "C" in flags,
                "raw": sanitize_cli_excerpt(s, 240),
            })
    return routes


def parse_mikrotik_bridge_ports(raw_output: str) -> Dict[str, Dict[str, Any]]:
    """Parses '/interface bridge port print detail' -> {port_name: bridge_info}."""
    ports: Dict[str, Dict[str, Any]] = {}
    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        if "X" in flags or "I" in flags:
            continue
        iface = it.get("interface", "")
        if iface:
            ports[iface] = {
                "interface": iface,
                "bridge": it.get("bridge", ""),
                "pvid": int(it["pvid"]) if (it.get("pvid") or "").isdigit() else 1,
                "frame_types": it.get("frame-types", "admit-all"),
                "hw": "H" in flags or it.get("hw") == "yes",
                "raw": it.get("_raw", ""),
            }
    return ports


def parse_mikrotik_bridge_hosts(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/interface bridge host print detail' or tabular MAC forwarding table."""
    hosts: List[Dict[str, Any]] = []
    if not raw_output:
        return hosts

    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        if "L" in flags or it.get("local") == "yes":
            continue
        mac = normalize_mac(it.get("mac-address", ""))
        on_if = it.get("on-interface", "")
        if mac and on_if:
            hosts.append({
                "mac": mac,
                "interface": on_if,
                "bridge": it.get("bridge", ""),
                "vid": int(it["vid"]) if (it.get("vid") or "").isdigit() else None,
                "raw": it.get("_raw", ""),
            })
    if hosts:
        return hosts

    for line in raw_output.splitlines():
        s = line.strip()
        m = re.match(r"^\d+\s+([A-Za-z]*)\s+([0-9A-Fa-f:]{17})\s+(\S+)\s+(\S+)", s)
        if m:
            flags, mac, on_if, bridge = m.groups()
            if "L" in flags:
                continue
            hosts.append({
                "mac": normalize_mac(mac),
                "interface": sanitize_untrusted_text(on_if, 64),
                "bridge": sanitize_untrusted_text(bridge, 64),
                "vid": None,
                "raw": sanitize_cli_excerpt(s, 240),
            })
    return hosts


def parse_mikrotik_dhcp_leases(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/ip dhcp-server lease print detail'."""
    leases: List[Dict[str, Any]] = []
    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        if "X" in flags:
            continue
        ip_val = normalize_ip(it.get("active-address") or it.get("address"))
        mac_val = normalize_mac(it.get("active-mac-address") or it.get("mac-address"))
        if ip_val or mac_val:
            leases.append({
                "ip": ip_val,
                "mac": mac_val,
                "hostname": sanitize_untrusted_text(it.get("host-name", ""), 64),
                "server": it.get("server", ""),
                "status": it.get("status", ""),
                "last_seen": it.get("last-seen", ""),
                "raw": it.get("_raw", ""),
            })
    return leases


def parse_mikrotik_dhcp_clients(raw_output: str) -> List[Dict[str, Any]]:
    """Parses '/ip dhcp-client print detail' or tabular."""
    clients: List[Dict[str, Any]] = []
    if not raw_output:
        return clients

    for it in _parse_kv_blocks(raw_output):
        flags = it.get("_flags", "")
        if "X" in flags or "I" in flags:
            continue
        clients.append({
            "interface": it.get("interface", ""),
            "status": (it.get("status") or "").lower(),
            "address": normalize_ip(it.get("address", "")),
            "gateway": normalize_ip(it.get("gateway", "")),
            "dhcp_server": normalize_ip(it.get("dhcp-server", "")),
            "add_default_route": it.get("add-default-route", "yes") != "no",
            "raw": it.get("_raw", ""),
        })
    if clients:
        return clients

    for line in raw_output.splitlines():
        s = line.strip()
        m = re.match(r"^\d+\s+([A-Za-z]*)\s*(\S+)\s+\S+\s+(\S+)", s)
        if m:
            flags, iface, status = m.groups()
            if "=" in iface or "X" in flags:
                continue
            clients.append({
                "interface": sanitize_untrusted_text(iface, 64),
                "status": status.lower(),
                "address": "",
                "gateway": "",
                "dhcp_server": "",
                "add_default_route": True,
                "raw": sanitize_cli_excerpt(s, 240),
            })
    return clients


def parse_mikrotik_vlans(vlan_if_output: str, bridge_vlan_output: str = "") -> List[Dict[str, Any]]:
    """Parses '/interface vlan print detail' and '/interface bridge vlan print detail'."""
    vlans: List[Dict[str, Any]] = []
    for it in _parse_kv_blocks(vlan_if_output):
        flags = it.get("_flags", "")
        if "X" in flags:
            continue
        vid = it.get("vlan-id", "")
        if vid.isdigit():
            vlans.append({
                "kind": "routed_vlan_interface",
                "name": it.get("name", ""),
                "vlan_id": int(vid),
                "parent_interface": it.get("interface", ""),
                "tagged": [it.get("interface", "")] if it.get("interface") else [],
                "untagged": [],
            })

    for it in _parse_kv_blocks(bridge_vlan_output):
        flags = it.get("_flags", "")
        if "X" in flags:
            continue
        vids_raw = it.get("vlan-ids", "")
        tagged = [p.strip() for p in (it.get("tagged") or "").split(",") if p.strip()]
        untagged = [p.strip() for p in (it.get("untagged") or "").split(",") if p.strip()]
        vlans.append({
            "kind": "bridge_vlan",
            "bridge": it.get("bridge", ""),
            "vlan_ids": vids_raw,
            "tagged": tagged,
            "untagged": untagged,
        })
    return vlans
