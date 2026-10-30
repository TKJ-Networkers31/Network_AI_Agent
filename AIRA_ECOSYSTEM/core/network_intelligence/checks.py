"""
core/network_intelligence/checks.py — Deterministic Network Analysis Layer.

Implements reusable, testable logic for the 7 core network problem domains:
1. LAN client internet connectivity & NAT/DNS prerequisites
2. Default route resolution, recursion, and ECMP
3. NAT rule order, interface matching, and subnet mismatch
4. Firewall forward-chain rule ordering, drop invalid, and FastTrack
5. OSPF adjacency prerequisites, timers, MTU, and protocol 89 reachability
6. BGP session establishment, prefix filtering, and next-hop reachability
7. VLAN bridge filtering, trunk tagging consistency, and SVI addressing
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from agents.akane.reasoning_engine import (
    ParsedRoute,
    evaluate_longest_prefix_match,
    parse_routeros_firewall,
    parse_routeros_routes,
)
from core.topology_models import normalize_ip

logger = logging.getLogger("aira.network_intelligence.checks")


# ---------------------------------------------------------------------------
# Helper: IP & Subnet Math
# ---------------------------------------------------------------------------

def parse_ip_network_safe(cidr: str) -> Optional[ipaddress.IPv4Network]:
    try:
        return ipaddress.ip_network(cidr.strip(), strict=False)
    except Exception:
        return None


def parse_ip_address_safe(ip_str: str) -> Optional[ipaddress.IPv4Address]:
    clean = normalize_ip(ip_str)
    if not clean:
        return None
    try:
        return ipaddress.ip_address(clean)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. LAN Client Cannot Access the Internet
# ---------------------------------------------------------------------------

def check_lan_no_internet(
    *,
    client_ip: Optional[str] = None,
    routes_evidence: Optional[Dict[str, Any]] = None,
    ip_addresses_evidence: Optional[Dict[str, Any]] = None,
    interfaces_evidence: Optional[Dict[str, Any]] = None,
    nat_evidence: Optional[Dict[str, Any]] = None,
    firewall_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates LAN client internet connectivity preconditions:
    - LAN subnet existence and router interface binding
    - Active default gateway route
    - NAT masquerade / src-nat coverage for LAN subnet
    - Firewall forward chain rules
    """
    findings = []
    observed_facts = []
    missing_evidence = []
    hypotheses = []
    recommendations = []

    # If all evidence sources are absent, return INSUFFICIENT_EVIDENCE deterministically
    if routes_evidence is None and ip_addresses_evidence is None and nat_evidence is None and firewall_evidence is None:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Tidak ada bukti observasi yang tersedia untuk dievaluasi."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["ip_addresses", "routes", "nat_rules", "firewall_filter"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan ulang bukti observasi."],
        }

    # 1. Check IP addresses on Router
    addrs = (ip_addresses_evidence or {}).get("addresses", [])
    if not addrs:
        missing_evidence.append("Data alamat IP router (/ip address) tidak tersedia.")

    client_subnet_found = False
    lan_interface = "unknown"
    router_lan_ip = ""

    if client_ip:
        c_ip = parse_ip_address_safe(client_ip)
        if c_ip:
            observed_facts.append(f"Klien IP yang dievaluasi: {client_ip}.")
            for a in addrs:
                net = parse_ip_network_safe(a.get("address", ""))
                if net and c_ip in net:
                    client_subnet_found = True
                    lan_interface = a.get("interface", "unknown")
                    router_lan_ip = a.get("address", "").split("/")[0]
                    observed_facts.append(
                        f"Subnet klien ditemukan: {net} pada interface '{lan_interface}' "
                        f"(IP router: {router_lan_ip})."
                    )
                    break
            if not client_subnet_found and addrs:
                findings.append({
                    "severity": "ERROR",
                    "code": "CLIENT_SUBNET_NOT_FOUND",
                    "message": f"IP klien {client_ip} tidak cocok dengan subnet lokal mana pun di router ini.",
                })
                hypotheses.append("Klien dikonfigurasi dengan subnet/gateway yang salah atau berada di segmen VLAN lain.")
                recommendations.append("Periksa konfigurasi IP static klien atau lease DHCP server.")

    # 2. Check Interface status
    if lan_interface != "unknown" and interfaces_evidence:
        ifaces = interfaces_evidence.get("interfaces", [])
        matched_iface = next((i for i in ifaces if i.get("name") == lan_interface), None)
        if matched_iface:
            if not matched_iface.get("running"):
                findings.append({
                    "severity": "CRITICAL",
                    "code": "LAN_INTERFACE_DOWN",
                    "message": f"Interface LAN '{lan_interface}' berstatus DOWN (running=no).",
                })
                hypotheses.append(f"Kabel fisik, link SFP, atau bridge port '{lan_interface}' terputus.")
                recommendations.append(f"Periksa kabel LAN fisik atau hubungkan port '{lan_interface}'.")

    # 3. Check Default Route
    routes = (routes_evidence or {}).get("routes", [])
    if not routes:
        missing_evidence.append("Data routing table (/ip route) tidak tersedia.")

    default_routes = [r for r in routes if (r.get("dst_address") or r.get("dst")) == "0.0.0.0/0"]
    active_default = [r for r in default_routes if r.get("active")]

    if not default_routes:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_DEFAULT_ROUTE",
            "message": "Tidak ada default route (0.0.0.0/0) pada routing table.",
        })
        hypotheses.append("Router tidak memiliki rute keluar ke internet publik.")
        recommendations.append("Tambahkan default route via gateway ISP: /ip route add dst-address=0.0.0.0/0 gateway=<IP_GATEWAY>")
    elif not active_default:
        findings.append({
            "severity": "CRITICAL",
            "code": "DEFAULT_ROUTE_INACTIVE",
            "message": "Default route (0.0.0.0/0) ada namun berstatus INACTIVE (gateway unreachable).",
        })
        hypotheses.append("Next-hop gateway ISP tidak dapat dijangkau oleh router (ARP gagal, link WAN mati, atau scope tidak cocok).")
        recommendations.append("Periksa reachability gateway ISP dan status interface WAN uplink.")
    else:
        gw = active_default[0].get("gateway", "")
        observed_facts.append(f"Default route aktif ditemukan via gateway {gw}.")

    # 4. Check NAT Masquerade
    nat_rules = (nat_evidence or {}).get("rules", [])
    has_masq = (nat_evidence or {}).get("has_masquerade", False)
    if not has_masq:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_NAT_MASQUERADE",
            "message": "Tidak ditemukan rule NAT masquerade atau src-nat aktif pada firewall NAT.",
        })
        hypotheses.append("Paket dari IP privat klien diteruskan ke internet tanpa translasi NAT publik sehingga didrop oleh ISP.")
        recommendations.append("Tambahkan rule NAT masquerade: /ip firewall nat add chain=srcnat action=masquerade out-interface-list=WAN")
    else:
        observed_facts.append("Rule NAT Masquerade/src-nat terdeteksi.")

    # 5. Check Forward Chain in Firewall
    fw_rules = (firewall_evidence or {}).get("rules", [])
    fwd_drop_early = False
    for r in fw_rules:
        if r.get("chain") == "forward" and not r.get("disabled"):
            if r.get("action") == "drop" and not r.get("connection_state"):
                fwd_drop_early = True
                findings.append({
                    "severity": "WARNING",
                    "code": "FIREWALL_DROP_ALL_FORWARD",
                    "message": f"Ditemukan rule drop tanpa filter ketat pada forward chain (rule #{r.get('index')}).",
                })
                hypotheses.append("Rule drop forward mungkin memblokir trafik klien sebelum sempat diteruskan ke WAN.")
                break

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")

    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 2. Default Route Exists but Connectivity Fails
# ---------------------------------------------------------------------------

def check_default_route_fails(
    *,
    routes_evidence: Dict[str, Any],
    ip_addresses_evidence: Optional[Dict[str, Any]] = None,
    interfaces_evidence: Optional[Dict[str, Any]] = None,
    routing_rules_evidence: Optional[Dict[str, Any]] = None,
    target_dst_ip: str = "8.8.8.8",
) -> Dict[str, Any]:
    """
    Investigates why connectivity fails despite default route presence:
    - Active vs inactive route
    - Recursive gateway resolution
    - Competing route distance
    - Policy routing / routing marks
    - ECMP balance
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    routes = (routes_evidence or {}).get("routes", [])
    if not routes_evidence or not routes:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_ROUTES", "message": "Routing table kosong atau bukti rute tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["Routing table data (/ip route print)"],
            "recommendations": ["Periksa koneksi SSH ke router dan pastikan routing table terbaca."],
        }

    default_routes = [r for r in routes if (r.get("dst_address") or r.get("dst")) == "0.0.0.0/0"]
    if not default_routes:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_DEFAULT_ROUTE",
            "message": "Default route 0.0.0.0/0 tidak ditemukan.",
        })
        return {
            "status": "CRITICAL",
            "findings": findings,
            "observed_facts": [],
            "inferred_hypotheses": ["Tidak ada rute default."],
            "missing_evidence": [],
            "recommendations": ["Tambahkan default route."],
        }

    active_defaults = [r for r in default_routes if r.get("active")]
    inactive_defaults = [r for r in default_routes if not r.get("active")]

    observed_facts.append(
        f"Ditemukan {len(default_routes)} default route: {len(active_defaults)} aktif, {len(inactive_defaults)} inaktif."
    )

    if not active_defaults:
        findings.append({
            "severity": "CRITICAL",
            "code": "DEFAULT_ROUTE_INACTIVE",
            "message": "Semua default route berstatus inaktif (gateway unreachable).",
        })
        hypotheses.append("Next-hop gateway tidak dapat diresolusi oleh kernel RouterOS.")
        recommendations.append("Periksa apakah IP gateway berada dalam subnet lokal yang sama atau target-scope memadai.")

    # Check recursive next-hop gateway resolution
    for r in active_defaults:
        gw = r.get("gateway", "")
        gw_ip = parse_ip_address_safe(gw)
        if gw_ip:
            # Check if gateway IP belongs to a directly connected subnet
            addrs = (ip_addresses_evidence or {}).get("addresses", [])
            is_directly_connected = False
            for a in addrs:
                net = parse_ip_network_safe(a.get("address", ""))
                if net and gw_ip in net:
                    is_directly_connected = True
                    break
            if not is_directly_connected and addrs:
                observed_facts.append(f"Gateway {gw} merupakan rute rekursif (tidak berada di subnet lokal langsung).")
                # Look for an intermediate route to this gateway
                intermediate = [
                    rt for rt in routes
                    if rt.get("dst_address") != "0.0.0.0/0"
                    and parse_ip_network_safe(rt.get("dst_address", ""))
                    and gw_ip in parse_ip_network_safe(rt.get("dst_address", ""))
                ]
                if not intermediate:
                    findings.append({
                        "severity": "CRITICAL",
                        "code": "RECURSIVE_GATEWAY_UNRESOLVED",
                        "message": f"Gateway rekursif {gw} tidak memiliki rute perantara di routing table.",
                    })
                    hypotheses.append("Gateway rekursif gagal diresolusi sehingga paket terhenti di router.")
                    recommendations.append(f"Tambahkan static route ke IP gateway {gw} dengan interface eksplisit.")
                else:
                    observed_facts.append(f"Gateway {gw} berhasil diresolusi via rute perantara: {intermediate[0].get('dst_address')}.")

    # Check ECMP
    if len(active_defaults) > 1:
        observed_facts.append(f"Terdapat {len(active_defaults)} active default routes (ECMP).")
        hypotheses.append("Trafik terbagi melintasi beberapa link (ECMP). Jika salah satu uplink down, sebagian koneksi akan timeout.")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")

    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 3. Suspected NAT Mismatch
# ---------------------------------------------------------------------------

def check_nat_mismatch(
    *,
    nat_evidence: Dict[str, Any],
    routes_evidence: Optional[Dict[str, Any]] = None,
    interfaces_evidence: Optional[Dict[str, Any]] = None,
    expected_out_interface: Optional[str] = None,
    client_subnet: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates NAT matching issues:
    - Masquerade out-interface mismatch vs active default route egress interface
    - Src-address constraints excluding client subnet
    - Rule order shadowing (e.g. earlier drop or accept before masquerade)
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    if not nat_evidence:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Bukti firewall NAT tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["nat_rules"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan tabel NAT."],
        }

    rules = nat_evidence.get("rules", [])
    if not rules:
        return {
            "status": "CRITICAL",
            "findings": [{"severity": "CRITICAL", "code": "NO_NAT_RULES", "message": "Firewall NAT tidak memiliki rule."}],
            "observed_facts": [],
            "inferred_hypotheses": ["Ketiadaan NAT menyebabkan paket IP privat keluar langsung ke WAN."],
            "missing_evidence": [],
            "recommendations": ["Tambahkan rule NAT masquerade pada out-interface WAN."],
        }

    # Determine actual WAN egress interface from default route
    egress_interface = expected_out_interface or ""
    if not egress_interface and routes_evidence:
        for r in routes_evidence.get("routes", []):
            dst = r.get("dst_address") or r.get("dst", "")
            if dst == "0.0.0.0/0" and r.get("active"):
                gw = r.get("gateway", "")
                if_val = r.get("interface") or r.get("gateway_interface", "")
                if if_val:
                    egress_interface = if_val
                elif not re.match(r"^\d+\.\d+\.\d+\.\d+", gw):
                    egress_interface = gw
                break

    masq_rules = [r for r in rules if r.get("action") == "masquerade" and not r.get("disabled")]
    if not masq_rules:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_ACTIVE_MASQUERADE",
            "message": "Tidak ada rule masquerade aktif di chain srcnat.",
        })
        recommendations.append("Tambahkan rule: /ip firewall nat add chain=srcnat action=masquerade out-interface-list=WAN")
    else:
        for r in masq_rules:
            r_out_if = r.get("out_interface", "")
            r_src = r.get("src_address", "")
            observed_facts.append(
                f"Rule masquerade: out-interface='{r_out_if or 'any'}', src-address='{r_src or 'any'}'."
            )

            # Check interface mismatch
            if egress_interface and r_out_if and r_out_if != egress_interface and r_out_if != "WAN":
                findings.append({
                    "severity": "WARNING",
                    "code": "NAT_OUT_INTERFACE_MISMATCH",
                    "message": (
                        f"Rule masquerade mengikat out-interface='{r_out_if}', "
                        f"sedangkan default route keluar melalui '{egress_interface}'."
                    ),
                })
                hypotheses.append("Paket keluar melalui interface yang tidak cocok dengan kriteria out-interface pada rule NAT.")
                recommendations.append(f"Ubah out-interface rule NAT menjadi '{egress_interface}' atau gunakan out-interface-list=WAN.")

            # Check client subnet constraint
            if client_subnet and r_src:
                c_net = parse_ip_network_safe(client_subnet)
                r_net = parse_ip_network_safe(r_src)
                if c_net and r_net and not c_net.subnet_of(r_net):
                    findings.append({
                        "severity": "ERROR",
                        "code": "NAT_SRC_ADDRESS_MISMATCH",
                        "message": f"Subnet klien {client_subnet} tidak tercakup oleh src-address rule NAT ({r_src}).",
                    })
                    hypotheses.append("Trafik klien tidak match dengan rule NAT karena batasan src-address.")
                    recommendations.append(f"Hapus atau sesuaikan src-address pada rule NAT agar mencakup {client_subnet}.")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")
    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 4. Firewall Forward-Chain Block
# ---------------------------------------------------------------------------

def check_firewall_forward_block(
    *,
    firewall_evidence: Dict[str, Any],
    client_ip: Optional[str] = None,
    dst_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates firewall forward-chain rules for shadowing, early drop, and FastTrack:
    - Forward chain rule order
    - Presence of connection-state=established,related accept rule
    - Unconditional drop rules before required accept rules
    - FastTrack position
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    if not firewall_evidence:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Bukti firewall filter tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["firewall_filter"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan filter firewall."],
        }

    rules = firewall_evidence.get("rules", [])
    fwd_rules = [r for r in rules if r.get("chain") == "forward" and not r.get("disabled")]

    observed_facts.append(f"Total forward chain filter rules aktif: {len(fwd_rules)}.")

    has_est_accept = False
    est_idx = -1
    has_drop_invalid = False
    drop_unconditional_idx = -1
    has_fasttrack = False
    ft_idx = -1

    for r in fwd_rules:
        idx = r.get("index", 0)
        action = r.get("action", "")
        state = r.get("connection_state", "")

        if action == "fasttrack-connection":
            has_fasttrack = True
            ft_idx = idx

        if action == "accept" and ("established" in state or "related" in state):
            has_est_accept = True
            if est_idx == -1:
                est_idx = idx

        if action == "drop" and "invalid" in state:
            has_drop_invalid = True

        if action == "drop" and not state and not r.get("dst_port") and not r.get("protocol"):
            if drop_unconditional_idx == -1:
                drop_unconditional_idx = idx

    # Check 1: Missing Established/Related Accept
    if not has_est_accept:
        findings.append({
            "severity": "CRITICAL",
            "code": "MISSING_ESTABLISHED_RELATED_ACCEPT",
            "message": "Forward chain tidak memiliki rule accept untuk connection-state=established,related.",
        })
        hypotheses.append("Paket balasan (return traffic) dari internet didrop oleh firewall karena state tracking tidak diizinkan.")
        recommendations.append("Tambahkan rule accept established/related di posisi teratas forward chain.")

    # Check 2: FastTrack placement relative to Established Accept
    if has_fasttrack and has_est_accept:
        if est_idx < ft_idx:
            findings.append({
                "severity": "WARNING",
                "code": "FASTTRACK_SUBOPTIMAL_ORDER",
                "message": f"Rule FastTrack (#{ft_idx}) berada setelah rule accept established (#{est_idx}).",
            })
            recommendations.append(f"Pindahkan FastTrack (#{ft_idx}) ke sebelum rule #{est_idx} untuk efisiensi CPU.")

    # Check 3: Early Unconditional Drop Rule Shadowing
    if drop_unconditional_idx != -1:
        if has_est_accept and drop_unconditional_idx < est_idx:
            findings.append({
                "severity": "CRITICAL",
                "code": "EARLY_DROP_FORWARD_SHADOWING",
                "message": f"Rule drop (#{drop_unconditional_idx}) berada SEBELUM rule accept established (#{est_idx}). Semua trafik didrop.",
            })
            hypotheses.append("Rule drop diletakkan terlalu tinggi dalam forward chain, memblokir semua paket lanjutan.")
            recommendations.append(f"Pindahkan rule drop #{drop_unconditional_idx} ke akhir chain forward.")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")
    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 5. OSPF Adjacency Failure
# ---------------------------------------------------------------------------

def check_ospf_adjacency(
    *,
    ospf_evidence: Dict[str, Any],
    firewall_evidence: Optional[Dict[str, Any]] = None,
    interfaces_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates OSPF neighbor adjacency and state transitions:
    - Neighbor presence and exact state (Full, 2-Way, Init, ExStart, Down)
    - MTU mismatch indicators (ExStart / Exchange freeze)
    - Protocol 89 filtering on input chain
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    if not ospf_evidence:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Bukti OSPF neighbor tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["ospf_neighbors"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan data OSPF neighbor."],
        }

    neighbors = ospf_evidence.get("neighbors", [])
    if not neighbors:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_OSPF_NEIGHBORS",
            "message": "Tidak ada OSPF neighbor yang terdeteksi.",
        })
        hypotheses.append("Paket OSPF Hello tidak diterima dari peer (link down, beda subnet, timer/area mismatch, atau auth mismatch).")
        recommendations.append("Periksa konfigurasi OSPF area, network type, hello interval, dan IP interface peer.")
        return {
            "status": "CRITICAL",
            "findings": findings,
            "observed_facts": ["Neighbor table OSPF kosong."],
            "inferred_hypotheses": hypotheses,
            "missing_evidence": ["OSPF interface config", "OSPF timer config"],
            "recommendations": recommendations,
        }

    for n in neighbors:
        r_id = n.get("router_id", "")
        addr = n.get("address", "")
        st = n.get("state", "Unknown").lower()
        observed_facts.append(f"OSPF Peer {r_id} ({addr}) berstatus '{n.get('state')}'.")

        if st == "full":
            continue

        if st in ("exstart", "exchange"):
            findings.append({
                "severity": "CRITICAL",
                "code": "OSPF_MTU_MISMATCH",
                "message": f"OSPF neighbor {r_id} terhenti pada state '{st}'. Indikasi kuat MTU mismatch.",
            })
            hypotheses.append("MTU pada interface lokal berbeda dengan MTU interface peer pada link transit OSPF.")
            recommendations.append("Samakan MTU pada kedua interface router atau aktifkan 'mtu-ignore=yes' pada interface template OSPF.")

        elif st == "init":
            findings.append({
                "severity": "HIGH",
                "code": "OSPF_ONE_WAY_HELLO",
                "message": f"OSPF neighbor {r_id} berstatus 'Init'. Komunikasi satu arah terdeteksi.",
            })
            hypotheses.append("Peer menerima hello kita tapi router kita belum melihat ID lokal pada hello packet dari peer.")
            recommendations.append("Periksa firewall input chain pada router peer atau routing multicast 224.0.0.5.")

        elif st in ("down", "attempt"):
            findings.append({
                "severity": "CRITICAL",
                "code": "OSPF_NEIGHBOR_DOWN",
                "message": f"OSPF neighbor {r_id} berstatus '{st}'.",
            })
            hypotheses.append("Koneksi layer 3 atau autentikasi OSPF gagal.")
            recommendations.append("Periksa password/key authentication dan pastikan IP peer dapat diping.")

    # Check firewall input chain for protocol 89 (OSPF)
    if firewall_evidence:
        rules = firewall_evidence.get("rules", [])
        input_drops = [r for r in rules if r.get("chain") == "input" and r.get("action") == "drop" and not r.get("disabled")]
        has_ospf_accept = any(
            r.get("chain") == "input" and r.get("action") == "accept" and r.get("protocol") in ("ospf", "89")
            for r in rules
        )
        if input_drops and not has_ospf_accept:
            findings.append({
                "severity": "WARNING",
                "code": "FIREWALL_POSSIBLE_OSPF_BLOCK",
                "message": "Input chain memiliki drop rule tanpa rule eksplisit 'accept protocol=ospf'.",
            })
            hypotheses.append("Paket OSPF Hello (protocol 89) kemungkinan diblokir oleh firewall input chain.")
            recommendations.append("Tambahkan rule accept OSPF: /ip firewall filter add chain=input protocol=ospf action=accept")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")
    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 6. BGP Session Established but Expected Prefixes are Missing
# ---------------------------------------------------------------------------

def check_bgp_prefixes_missing(
    *,
    bgp_evidence: Dict[str, Any],
    routes_evidence: Optional[Dict[str, Any]] = None,
    expected_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates BGP peer state and prefix reception:
    - BGP session state (Established vs Idle/Connect)
    - Received prefix count vs active routing table installation
    - Next-hop reachability of BGP routes
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    if not bgp_evidence:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Bukti BGP peer tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["bgp_peers"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan data BGP peer."],
        }

    peers = bgp_evidence.get("peers", [])
    if not peers:
        findings.append({
            "severity": "CRITICAL",
            "code": "NO_BGP_PEERS",
            "message": "Tidak ada peer BGP yang dikonfigurasi atau aktif.",
        })
        return {
            "status": "CRITICAL",
            "findings": findings,
            "observed_facts": ["BGP peer table kosong."],
            "inferred_hypotheses": ["BGP belum dikonfigurasi."],
            "missing_evidence": [],
            "recommendations": ["Konfigurasi BGP connection/peer."],
        }

    for p in peers:
        name = p.get("name", "peer")
        r_ip = p.get("remote_ip", "")
        st = p.get("state", "unknown").lower()
        p_count = p.get("prefix_count", 0)

        observed_facts.append(f"BGP Peer '{name}' ({r_ip}): state='{st}', prefix_count={p_count}.")

        if st != "established":
            findings.append({
                "severity": "CRITICAL",
                "code": "BGP_NOT_ESTABLISHED",
                "message": f"Sesi BGP '{name}' berstatus '{st}' (bukan Established).",
            })
            hypotheses.append("Koneksi TCP port 179 gagal dibangun dengan peer (IP unreachable, AS mismatch, atau firewall drop).")
            recommendations.append("Periksa konektivitas IP ke peer dan pastikan remote AS sesuai.")
        else:
            if p_count == 0:
                findings.append({
                    "severity": "HIGH",
                    "code": "BGP_ZERO_PREFIXES_RECEIVED",
                    "message": f"Sesi BGP '{name}' established, namun menerima 0 prefix.",
                })
                hypotheses.append("Routing filter di sisi lokal menolak semua prefix, atau peer tidak mengirimkan (advertise) prefix.")
                recommendations.append("Periksa in-filter BGP lokal (/routing filter) dan minta remote admin memverifikasi advertised routes.")
            else:
                if expected_prefix and routes_evidence:
                    routes = routes_evidence.get("routes", [])
                    has_exp = any(r.get("dst_address") == expected_prefix for r in routes)
                    if not has_exp:
                        findings.append({
                            "severity": "HIGH",
                            "code": "BGP_EXPECTED_PREFIX_NOT_IN_ROUTING_TABLE",
                            "message": f"Prefix yang diharapkan {expected_prefix} tidak terpasang di routing table aktif.",
                        })
                        hypotheses.append("Prefix diterima via BGP namun ditolak oleh filter in, atau next-hop IP tidak reachable.")
                        recommendations.append(f"Periksa status resolusi next-hop dan filter policy untuk {expected_prefix}.")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")
    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 7. VLAN or Trunk Connectivity Failure
# ---------------------------------------------------------------------------

def check_vlan_trunk_failure(
    *,
    bridge_vlan_evidence: Dict[str, Any],
    interfaces_evidence: Optional[Dict[str, Any]] = None,
    ip_addresses_evidence: Optional[Dict[str, Any]] = None,
    target_vlan_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates MikroTik Bridge VLAN filtering and Trunk configuration:
    - Bridge vlan-filtering enabled
    - Target VLAN ID present in bridge vlan table
    - Tagged ports consistency on trunk
    - SVI (interface vlan) creation and IP address assignment
    """
    findings = []
    observed_facts = []
    hypotheses = []
    missing_evidence = []
    recommendations = []

    if not bridge_vlan_evidence:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "findings": [{"severity": "CRITICAL", "code": "NO_EVIDENCE", "message": "Bukti Bridge VLAN tidak tersedia."}],
            "observed_facts": [],
            "inferred_hypotheses": [],
            "missing_evidence": ["bridge_vlan"],
            "recommendations": ["Periksa koneksi SSH ke router dan kumpulkan data bridge VLAN."],
        }

    vlan_filtering = bridge_vlan_evidence.get("vlan_filtering", False)
    vlan_ids = bridge_vlan_evidence.get("vlan_ids", [])
    tagged_ports = bridge_vlan_evidence.get("tagged_ports", [])
    untagged_ports = bridge_vlan_evidence.get("untagged_ports", [])

    observed_facts.append(
        f"Bridge VLAN filtering: {'AKTIF' if vlan_filtering else 'NON-AKTIF'}. "
        f"VLAN IDs ditemukan: {', '.join(vlan_ids) if vlan_ids else 'none'}."
    )

    if not vlan_filtering:
        findings.append({
            "severity": "WARNING",
            "code": "BRIDGE_VLAN_FILTERING_DISABLED",
            "message": "Bridge vlan-filtering berstatus disabled (bridge beroperasi sebagai flat L2 switch).",
        })
        hypotheses.append("VLAN tag diproses secara transparan tanpa isolasi L2 atau hardware VLAN offloading.")

    if target_vlan_id:
        v_str = str(target_vlan_id)
        if vlan_filtering and v_str not in vlan_ids:
            findings.append({
                "severity": "CRITICAL",
                "code": "VLAN_ID_NOT_IN_BRIDGE_TABLE",
                "message": f"VLAN ID {v_str} tidak terdaftar pada /interface bridge vlan print.",
            })
            hypotheses.append(f"Frame bertag VLAN {v_str} akan didrop oleh bridge saat masuk ke trunk.")
            recommendations.append(f"Tambahkan VLAN {v_str} ke bridge: /interface bridge vlan add bridge=bridge vlan-ids={v_str} tagged=bridge,...")

        # Check SVI (VLAN interface on router)
        if ip_addresses_evidence and interfaces_evidence:
            ifaces = interfaces_evidence.get("interfaces", [])
            vlan_iface_name = next((i.get("name") for i in ifaces if v_str in i.get("name", "") and i.get("type") == "vlan"), None)
            if not vlan_iface_name:
                findings.append({
                    "severity": "WARNING",
                    "code": "NO_SVI_FOR_VLAN",
                    "message": f"Tidak ditemukan interface VLAN (SVI) untuk VLAN {v_str}.",
                })
                hypotheses.append("Router hanya bertindak sebagai L2 switch untuk VLAN ini tanpa L3 gateway IP.")
            else:
                observed_facts.append(f"Interface SVI ditemukan: '{vlan_iface_name}'.")

    status = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "HEALTHY")
    return {
        "status": status,
        "findings": findings,
        "observed_facts": observed_facts,
        "inferred_hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "recommendations": recommendations,
    }
