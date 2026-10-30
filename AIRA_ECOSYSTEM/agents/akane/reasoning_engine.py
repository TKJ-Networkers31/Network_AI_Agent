"""
agents/akane/reasoning_engine.py — AKANE Autonomous Network Reasoning Engine.

Deterministic, evidence-backed diagnostic analysis:
- Routing Analysis & IPv4 Longest Prefix Match (LPM) evaluator for RouterOS v6 & v7.
- Firewall Filter, FastTrack, NAT, and Chain Order Analyzer.
- L2 Bridge & VLAN Configuration Analyzer.
- Standard Structured Evidence Contract Generator.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.topology_models import normalize_ip, sanitize_untrusted_text

logger = logging.getLogger("aira.akane.reasoning")


# ---------------------------------------------------------------------------
# Route Parsing & Deterministic Longest Prefix Match (LPM)
# ---------------------------------------------------------------------------

@dataclass
class ParsedRoute:
    dst_address: str
    gateway: str
    distance: int = 1
    active: bool = True
    dynamic: bool = False
    connect: bool = False
    static: bool = False
    raw_flags: str = ""
    prefix_len: int = 0
    network: Optional[ipaddress.IPv4Network] = None

    def __post_init__(self):
        try:
            net = ipaddress.ip_network(self.dst_address, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                self.network = net
                self.prefix_len = net.prefixlen
        except ValueError:
            self.network = None
            self.prefix_len = 0


def parse_routeros_routes(raw_text: str) -> List[ParsedRoute]:
    """
    Parses RouterOS v6 and v7 routing table prints into normalized ParsedRoute objects.
    Robust against spaces in flag columns, detail print output, and varied column alignments.
    """
    routes: List[ParsedRoute] = []
    lines = (raw_text or "").splitlines()

    # Pattern for destination CIDR: e.g. 0.0.0.0/0 or 192.168.1.0/24
    dst_cidr_pattern = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b")

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#") or line_clean.startswith("Flags") or line_clean.startswith("Columns"):
            continue

        # In RouterOS print detail format:
        # dst-address=0.0.0.0/0 gateway=192.168.1.1 distance=1 active=yes
        if "dst-address=" in line_clean:
            dst_m = re.search(r"dst-address=([0-9\.\/]+)", line_clean)
            gw_m = re.search(r"gateway=([^\s]+)", line_clean)
            dist_m = re.search(r"distance=(\d+)", line_clean)
            prefix = line_clean.split("dst-address=")[0].strip()
            flags_m = prefix.split()[-1] if prefix else ""
            active_m = ("A" in flags_m) or ("active=yes" in line_clean) or ("active=no" not in line_clean and not flags_m)
            dynamic_m = ("D" in flags_m) or ("dynamic=yes" in line_clean)
            connect_m = ("C" in flags_m.upper()) or ("connect=yes" in line_clean)
            static_m = ("S" in flags_m.upper()) or ("static=yes" in line_clean)
            if dst_m:
                dst = dst_m.group(1)
                gw = gw_m.group(1) if gw_m else ""
                dist = int(dist_m.group(1)) if dist_m else 1
                routes.append(ParsedRoute(
                    dst_address=dst,
                    gateway=gw,
                    distance=dist,
                    active=active_m,
                    dynamic=dynamic_m,
                    connect=connect_m,
                    static=static_m,
                    raw_flags=flags_m or "DETAIL",
                ))
            continue

        # Line starting with an index number
        m_idx = re.match(r"^\s*(\d+)\s+(.*)", line)
        if m_idx:
            rest = m_idx.group(2)
            cidr_m = dst_cidr_pattern.search(rest)
            if cidr_m:
                dst = cidr_m.group(1)
                flags = rest[: cidr_m.start()].strip()
                after_dst = rest[cidr_m.end() :].strip().split()

                gw = ""
                dist = 1
                if after_dst:
                    # Last token is often distance if integer
                    if after_dst[-1].isdigit():
                        dist = int(after_dst[-1])
                        remaining_tokens = after_dst[:-1]
                    else:
                        remaining_tokens = after_dst

                    # Gateway is typically the first non-empty token or last non-IP pref-src
                    if remaining_tokens:
                        gw = remaining_tokens[-1]

                flags_upper = flags.upper()
                is_active = "A" in flags_upper or not flags_upper
                is_dynamic = "D" in flags_upper
                is_connect = "C" in flags_upper
                is_static = "S" in flags_upper

                routes.append(ParsedRoute(
                    dst_address=dst,
                    gateway=gw,
                    distance=dist,
                    active=is_active,
                    dynamic=is_dynamic,
                    connect=is_connect,
                    static=is_static,
                    raw_flags=flags,
                ))

    return routes


def evaluate_longest_prefix_match(routes: List[ParsedRoute], target_ip: str) -> Dict[str, Any]:
    """
    Evaluates Longest Prefix Match (LPM) for target destination IPv4.
    Finds the most specific active route (highest prefix_len), breaking ties by lowest distance.
    """
    clean_ip = normalize_ip(target_ip)
    if not clean_ip:
        return {"matched": False, "error": f"Invalid target IPv4 address: '{target_ip}'"}

    try:
        addr = ipaddress.ip_address(clean_ip)
    except ValueError as exc:
        return {"matched": False, "error": str(exc)}

    matching_routes: List[Tuple[ParsedRoute, int]] = []

    for r in routes:
        if r.network and addr in r.network:
            matching_routes.append((r, r.prefix_len))

    if not matching_routes:
        return {
            "matched": False,
            "target_ip": clean_ip,
            "matching_routes_count": 0,
            "best_route": None,
            "reason": "No route matches this destination IP (unreachable destination, missing default route).",
        }

    def route_sort_key(item: Tuple[ParsedRoute, int]):
        r, plen = item
        return (1 if r.active else 0, plen, -r.distance)

    matching_routes.sort(key=route_sort_key, reverse=True)
    best_route, best_plen = matching_routes[0]

    all_matches = [
        {
            "dst_address": r.dst_address,
            "gateway": r.gateway,
            "prefix_len": r.prefix_len,
            "distance": r.distance,
            "active": r.active,
            "flags": r.raw_flags,
            "is_default_route": r.dst_address == "0.0.0.0/0",
        }
        for r, _ in matching_routes
    ]

    # Audit D: Check ECMP and recursive gateway indicators
    ecmp_gateways: List[str] = []
    if "," in best_route.gateway:
        ecmp_gateways = [g.strip() for g in best_route.gateway.split(",") if g.strip()]
    else:
        # Check if multiple active routes match the same prefix and distance
        same_cost_routes = [
            r for r, _ in matching_routes
            if r.dst_address == best_route.dst_address
            and r.distance == best_route.distance
            and r.active == best_route.active
        ]
        if len(same_cost_routes) > 1:
            ecmp_gateways = [r.gateway for r in same_cost_routes]

    is_ecmp = len(ecmp_gateways) > 1 or ("," in best_route.gateway)
    is_interface_gateway = not bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", best_route.gateway))

    recursive_gateway_candidate = False
    if best_route.gateway and not is_interface_gateway:
        try:
            gw_ip = ipaddress.ip_address(best_route.gateway.split(",")[0].strip())
            for r in routes:
                if r.dst_address != "0.0.0.0/0" and r.dst_address != best_route.dst_address and r.network and gw_ip in r.network:
                    recursive_gateway_candidate = True
                    break
        except Exception:
            pass

    observed_facts = [
        f"Ditemukan {len(matching_routes)} rute yang mencakup target IP {clean_ip}.",
        f"Rute terseleksi: dst={best_route.dst_address} via {best_route.gateway} (prefix_len=/{best_route.prefix_len}, distance={best_route.distance}, active={best_route.active}).",
    ]
    if is_ecmp:
        observed_facts.append(f"Rute menggunakan ECMP (multi-gateway: {', '.join(ecmp_gateways) if ecmp_gateways else best_route.gateway}).")

    inferred_hypotheses = [
        f"LPM memilih rute prefix terpanjang (/{best_route.prefix_len}) dengan prioritas active status dan distance terkecil."
    ]
    if recursive_gateway_candidate:
        inferred_hypotheses.append("Next-hop gateway merupakan IP rute tidak langsung (recursive gateway candidate) yang memerlukan look-up tabel rute sekunder.")

    missing_evidence = [
        "Routing mark / mangle table rules belum dievaluasi.",
        "Policy routing rules (/ip route rule atau /routing rule) belum dievaluasi.",
        "Status resolusi gateway rekursif (scope / target-scope) belum divalidasi terhadap interface fisik.",
        "Source routing (pref-src selection) belum dipastikan.",
    ]

    recommendations = []
    if not best_route.active:
        recommendations.append("Rute terpilih berstatus INACTIVE. Periksa apakah interface gateway UP atau target scope reachable.")
    if best_route.dst_address == "0.0.0.0/0":
        recommendations.append("Trafik menuju host ini bergantung pada default gateway. Pastikan uplink WAN beroperasi normal.")

    return {
        "matched": True,
        "target_ip": clean_ip,
        "matching_routes_count": len(matching_routes),
        "is_ecmp": is_ecmp,
        "ecmp_gateways": ecmp_gateways,
        "recursive_gateway_candidate": recursive_gateway_candidate,
        "best_route": {
            "dst_address": best_route.dst_address,
            "gateway": best_route.gateway,
            "prefix_len": best_route.prefix_len,
            "distance": best_route.distance,
            "active": best_route.active,
            "flags": best_route.raw_flags,
            "is_default_route": best_route.dst_address == "0.0.0.0/0",
            "is_ecmp": is_ecmp,
            "is_interface_gateway": is_interface_gateway,
        },
        "all_matches": all_matches,
        "is_default_route_match": best_route.dst_address == "0.0.0.0/0",
        "observed_facts": observed_facts,
        "inferred_hypotheses": inferred_hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
        "limits_disclosure": (
            "LPM mengevaluasi tabel rute 'main' standar. Forwarding aktual pada RouterOS dapat "
            "berbeda jika terdapat routing-mark (mangle), policy rules (/ip route rule), "
            "atau VRF terisolasi."
        ),
    }


# ---------------------------------------------------------------------------
# Firewall / FastTrack / NAT Rule Analysis
# ---------------------------------------------------------------------------

@dataclass
class FirewallRule:
    index: int
    chain: str
    action: str
    connection_state: str = ""
    protocol: str = ""
    dst_port: str = ""
    in_interface: str = ""
    out_interface: str = ""
    comment: str = ""
    disabled: bool = False
    raw: str = ""


def parse_routeros_firewall(raw_text: str) -> List[FirewallRule]:
    """
    Parses firewall filter rule lines, supporting multi-line comments and wrapped attributes.
    """
    rules: List[FirewallRule] = []
    lines = (raw_text or "").splitlines()
    cur_comment = ""
    cur_rule_dict: Optional[Dict[str, Any]] = None

    def flush_rule():
        nonlocal cur_rule_dict
        if cur_rule_dict:
            rules.append(FirewallRule(**cur_rule_dict))
            cur_rule_dict = None

    for line in lines:
        line_s = line.strip()
        if not line_s or line_s.startswith("Flags:"):
            continue

        if line_s.startswith(";;;"):
            cur_comment = line_s.lstrip(";").strip()
            continue

        # Check line index and flags
        m_idx = re.match(r"^(\d+)\s+([XID\s]*)(.*)", line_s)
        if m_idx:
            flush_rule()
            idx = int(m_idx.group(1))
            flags = m_idx.group(2)
            rest = m_idx.group(3)
            disabled = "X" in flags

            cur_rule_dict = {
                "index": idx,
                "chain": "forward",
                "action": "accept",
                "connection_state": "",
                "protocol": "",
                "dst_port": "",
                "in_interface": "",
                "out_interface": "",
                "comment": cur_comment,
                "disabled": disabled,
                "raw": line_s,
            }
            cur_comment = ""
            line_to_parse = rest
        else:
            line_to_parse = line_s

        if cur_rule_dict:
            cur_rule_dict["raw"] += " " + line_to_parse
            chain_m = re.search(r"chain=([^\s]+)", line_to_parse)
            if chain_m:
                cur_rule_dict["chain"] = chain_m.group(1).lower()

            action_m = re.search(r"action=([^\s]+)", line_to_parse)
            if action_m:
                cur_rule_dict["action"] = action_m.group(1).lower()

            state_m = re.search(r"connection-state=([^\s]+)", line_to_parse)
            if state_m:
                cur_rule_dict["connection_state"] = state_m.group(1).lower()

            proto_m = re.search(r"protocol=([^\s]+)", line_to_parse)
            if proto_m:
                cur_rule_dict["protocol"] = proto_m.group(1).lower()

            port_m = re.search(r"dst-port=([^\s]+)", line_to_parse)
            if port_m:
                cur_rule_dict["dst_port"] = port_m.group(1)

            in_if_m = re.search(r"in-interface(?:-list)?=([^\s]+)", line_to_parse)
            if in_if_m:
                cur_rule_dict["in_interface"] = in_if_m.group(1)

            out_if_m = re.search(r"out-interface(?:-list)?=([^\s]+)", line_to_parse)
            if out_if_m:
                cur_rule_dict["out_interface"] = out_if_m.group(1)

    flush_rule()
    return rules


def analyze_firewall_rules(filter_rules: Union[List[FirewallRule], List[Dict[str, Any]]], nat_raw: str = "") -> Dict[str, Any]:
    """
    Evaluates firewall health, FastTrack placement, rule shadowing, and NAT coverage.
    Supports either FirewallRule objects or raw dictionaries.
    """
    normalized_rules: List[FirewallRule] = []
    for i, r in enumerate(filter_rules or []):
        if isinstance(r, FirewallRule):
            normalized_rules.append(r)
        elif isinstance(r, dict):
            normalized_rules.append(FirewallRule(
                index=r.get("index", i),
                chain=r.get("chain", "forward"),
                action=r.get("action", "accept"),
                connection_state=r.get("connection_state", r.get("connection-state", "")),
                protocol=r.get("protocol", ""),
                dst_port=r.get("dst_port", r.get("dst-port", "")),
                in_interface=r.get("in_interface", r.get("in-interface", "")),
                out_interface=r.get("out_interface", r.get("out-interface", "")),
                comment=r.get("comment", ""),
                disabled=bool(r.get("disabled", False)),
                raw=r.get("raw", str(r)),
            ))

    issues = []
    observations = []

    # 1. Forward chain analysis & FastTrack
    fwd_rules = [r for r in normalized_rules if r.chain == "forward" and not r.disabled]
    has_fasttrack = False
    has_established_accept = False
    fasttrack_idx = -1
    established_idx = -1

    for r in fwd_rules:
        if r.action == "fasttrack-connection":
            has_fasttrack = True
            fasttrack_idx = r.index
        if r.action == "accept" and "established" in r.connection_state:
            has_established_accept = True
            established_idx = r.index

    if has_fasttrack:
        observations.append(f"FastTrack connection enabled at rule #{fasttrack_idx}.")
        if has_established_accept and established_idx < fasttrack_idx:
            issues.append(f"FastTrack rule #{fasttrack_idx} diletakkan SETELAH accept established rule #{established_idx}. Harus berada sebelum accept untuk efisiensi CPU.")
    else:
        observations.append("FastTrack tidak terdeteksi pada forward chain (evaluasi rule penuh untuk semua paket).")

    # 2. Input chain exposure analysis
    input_rules = [r for r in normalized_rules if r.chain == "input" and not r.disabled]
    has_drop_all_input = any(r.action == "drop" and (not r.connection_state or "invalid" not in r.connection_state) for r in input_rules)
    has_drop_invalid = any(r.action == "drop" and "invalid" in r.connection_state for r in input_rules)

    if not has_drop_invalid:
        issues.append("Input chain belum memiliki rule 'drop invalid packets' untuk membuang paket korup/malformed.")
    if not has_drop_all_input:
        issues.append("Input chain tidak memiliki default drop rule di akhir. Router mungkin terekspos scan port dari luar.")

    # 3. NAT Masquerade analysis
    has_masquerade = "masquerade" in (nat_raw or "").lower() or "src-nat" in (nat_raw or "").lower()
    if not has_masquerade:
        issues.append("Tidak ditemukan rule NAT (masquerade/src-nat). Klien LAN mungkin tidak dapat mengakses internet.")
    else:
        observations.append("NAT masquerade/src-nat terdeteksi.")

    status = "CRITICAL" if any("NAT" in iss for iss in issues) else ("WARNING" if issues else "HEALTHY")

    observed_facts = [
        f"Total filter rules terbaca: {len(normalized_rules)}",
        f"FastTrack: {'Aktif di rule #' + str(fasttrack_idx) if has_fasttrack else 'Tidak terpasang'}",
        f"NAT Masquerade/src-nat: {'Terdeteksi' if has_masquerade else 'Tidak ditemukan'}",
    ]
    drop_rules = [r for r in normalized_rules if r.action == "drop" and not r.disabled]
    for dr in drop_rules:
        desc = f"Rule #{dr.index} drop pada chain '{dr.chain}'"
        if dr.comment:
            desc += f" ({dr.comment})"
        if dr.raw:
            desc += f": {dr.raw}"
        observed_facts.append(desc)
    missing_evidence = [
        "Tabel mangle (prerouting, postrouting) belum diperiksa.",
        "Tabel raw (prerouting drops) belum diperiksa.",
        "Anggota interface-list (WAN, LAN) belum dicocokkan dengan port fisik.",
    ]
    recommendations = []
    if not has_masquerade:
        recommendations.append("Tambahkan rule NAT masquerade pada out-interface WAN: /ip firewall nat add chain=srcnat action=masquerade out-interface-list=WAN")
    if not has_drop_invalid:
        recommendations.append("Tambahkan rule drop invalid pada input chain: /ip firewall filter add chain=input action=drop connection-state=invalid")
    if has_established_accept and established_idx < fasttrack_idx:
        recommendations.append(f"Pindahkan FastTrack rule #{fasttrack_idx} ke sebelum rule #{established_idx} menggunakan: /ip firewall filter move {fasttrack_idx} {established_idx}")

    return {
        "status": status,
        "summary": {
            "status": status,
            "total_rules": len(normalized_rules),
            "issues_count": len(issues),
        },
        "total_rules": len(normalized_rules),
        "issues_detected": issues,
        "observations": observations,
        "observed_facts": observed_facts,
        "inferred_hypotheses": [
            "Penempatan FastTrack yang optimal mengurangi beban CPU secara signifikan pada RouterBOARD/Cloud Core.",
            "Ketiadaan NAT masquerade umumnya menyebabkan klien LAN kehilangan konektivitas internet publik.",
        ],
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
        "has_fasttrack": has_fasttrack,
        "has_masquerade": has_masquerade,
    }


# ---------------------------------------------------------------------------
# L2 Bridge & VLAN Configuration Analyzer
# ---------------------------------------------------------------------------

def analyze_vlan_configuration(
    bridge_print_raw: str,
    vlan_print_raw: str,
    ports_print_raw: str,
) -> Dict[str, Any]:
    """
    Analyzes MikroTik bridge VLAN filtering, PVID assignments, and tagged/untagged consistency.
    """
    issues = []
    observations = []

    # Check vlan-filtering=yes on bridge
    vlan_filtering_enabled = "vlan-filtering=yes" in (bridge_print_raw or "").lower()
    if vlan_filtering_enabled:
        observations.append("Bridge VLAN filtering AKTIF (isolasi layer 2 beroperasi penuh).")
    else:
        observations.append("Bridge VLAN filtering NON-AKTIF (semua port bertindak sebagai flat switch tanpa pemisahan broadcast domain).")

    # Check VLAN IDs
    vlan_ids = re.findall(r"vlan-ids?=(\d+(?:-\d+)?)", vlan_print_raw or "")
    if vlan_filtering_enabled and not vlan_ids:
        issues.append("Bridge VLAN filtering aktif, namun tidak ada entri VLAN ID di /interface bridge vlan print. Trafik VLAN akan diblokir.")

    # Check PVIDs
    pvid_matches = re.findall(r"pvid=(\d+)", ports_print_raw or "")
    if pvid_matches:
        observations.append(f"Port PVID terkonfigurasi untuk VLAN: {', '.join(sorted(set(pvid_matches)))}.")

    status = "WARNING" if issues else "HEALTHY"
    return {
        "status": status,
        "vlan_filtering_enabled": vlan_filtering_enabled,
        "vlan_ids_found": vlan_ids,
        "issues_detected": issues,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Master Evidence Contract Generator
# ---------------------------------------------------------------------------

def generate_evidence_contract(
    *,
    symptom: str,
    affected_device: str,
    evidence_collected: List[Dict[str, Any]],
    hypotheses: List[str],
    confirmed_facts: List[str],
    unknowns: List[str],
    recommended_action: str,
    severity: str = "warning",
) -> Dict[str, Any]:
    """
    Generates standard, structured AKANE diagnostic evidence contracts.
    """
    return {
        "symptom": symptom,
        "affected_device": affected_device,
        "severity": severity,
        "timestamp": time.time(),
        "evidence_collected": evidence_collected,
        "hypotheses": hypotheses,
        "confirmed_facts": confirmed_facts,
        "unknowns": unknowns,
        "recommended_action": recommended_action,
    }
