# AIRA OS — NETWORKING VI: MODULAR PROTOCOL INTELLIGENCE MATRIX (WP 6.8)

## 1. Overview & Architectural Boundaries

Protocol Intelligence in Networking VI consists of 9 decoupled, version-aware diagnostic analyzers located under `core/network_intelligence/protocols/`. Each analyzer strictly operates on read-only normalized evidence, declares explicit evidentiary prerequisites, evaluates operational failure states, and surfaces structured diagnostic findings without guessing or modifying network configurations.

---

## 2. Protocol Capability & Limitation Matrix

| Protocol Domain | Module | Supported Versions | Required Evidence Types | Optional Evidence Types | Key Diagnostic Rules | Known Operational Limitations |
|---|---|---|---|---|---|---|
| **Layer 2** | `layer2.py` | RouterOS v6, v7 | `interfaces` | `bridge`, `bridge_ports`, `bridge_vlan`, `arp` | VLAN isolation, PVID mismatch, trunk untagged leaks, bridge STP state, MTU/L2MTU limits | Hardware-offloaded ASIC switching internals require CLI export; STP topology change count only observable if reported in bridge status. |
| **IPv4** | `ipv4.py` | Universal | `ip_addresses`, `interfaces` | `routes`, `arp` | Subnet overlap, duplicate IP assignment, missing interface binding, missing default gateway | Does not inspect dynamic DHCP client leases unless captured in addressing evidence. |
| **IPv6** | `ipv6.py` | RouterOS v6, v7 | `interfaces` | `ipv6_addresses`, `ipv6_routes`, `ipv6_neighbors` | IPv6 prefix matching, link-local vs global unicast reachability, missing default `::/0` | Live CLI read-only allowlist currently does not include `/ipv6 route print`; IPv6 support is explicit and documented as bounded by collected evidence. |
| **Static Routing** | `static_routing.py` | RouterOS v6, v7 | `routes` | `interfaces` | LPM preference, administrative distance conflict, recursive loop detection, blackhole/unreachable isolation | Standard routing table evaluation does not simulate complex mangle routing marks unless captured in route rule tables. |
| **OSPF** | `ospf.py` | OSPFv2 (RouterOS v6 & v7) | `routes` | `ospf_instance`, `ospf_neighbors`, `ospf_interfaces` | Adjacency stuck in Init/2-Way/ExStart/Exchange, MTU mismatch, area mismatch, duplicate router ID, missing default route redistribution | Encrypted MD5/SHA authentication keys cannot and must not be exposed; authentication errors inferred via neighbor state and timeout. |
| **BGP** | `bgp.py` | BGP4 (RouterOS v6 & v7) | `routes` | `bgp_peers`, `bgp_routes` | 6-stage prefix lifecycle, Idle/Active session state, eBGP multi-hop next-hop reachability, AS-Path loop rejection, prefix limits | Inbound route filtering (prefix-lists / routing filters) only observable through accepted vs received counts or explicit route drops. |
| **NAT & Firewall** | `nat_firewall.py` | RouterOS v6, v7 | `interfaces` | `nat_rules`, `firewall_filter` | Rule shadowing, zero-counter masquerade drop, asymmetric return path disruption, invalid connection tracking drop | Live connection tracking table (`/ip firewall connection print`) is high-cardinality and sampled; per-packet traversal is inferred. |
| **QoS & Queues** | `qos.py` | RouterOS v6, v7 | `interfaces` | `qos_queues` | Queue saturation, dropped packet acceleration, parent-child rate exhaustion, queue burst bottleneck | Simple queues and queue trees analyzed based on point-in-time byte/packet counters and drop rates. |
| **Tunnels & VPN** | `tunnels.py` | GRE, IPIP, EoIP, WG, IPsec, L2TP | `interfaces` | `tunnels`, `routes` | Tunnel keepalive timeout, remote endpoint unreachability, MTU/MSS clamping mismatch, missing static return route | Dynamic cryptographic keys are strictly redacted; tunnel state evaluated via interface operational status and remote IP reachability. |

---

## 3. Strict 6-Stage BGP Prefix Lifecycle

AIRA strictly distinguishes the 6 operational states of a BGP prefix to prevent amateurish conflation:

1. `SESSION_ESTABLISHED`: TCP port 179 connected and BGP OPEN negotiation completed (`state == 'established'`).
2. `ROUTE_RECEIVED`: Prefix advertised by peer into the local routing process.
3. `ROUTE_ACCEPTED`: Prefix permitted by local inbound routing filter / prefix-list.
4. `ROUTE_SELECTED`: Best-path algorithm selects prefix over alternate candidates (AS_PATH, LOCAL_PREF, MED).
5. `ROUTE_INSTALLED`: Prefix written into kernel / RIB routing table (`active = True`).
6. `FORWARDING_VERIFIED`: Prefix confirmed active in hardware/FIB offload and verified by successful data-plane forwarding.
