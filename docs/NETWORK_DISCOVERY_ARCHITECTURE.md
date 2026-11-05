# AIRA OS — NETWORK DISCOVERY ARCHITECTURE
## Single Seed to Progressive Network Visibility & Pending Device Governance

**Version:** 1.0.0  
**Status:** Canonical Discovery Architecture  

---

## 1. Single Seed Discovery Philosophy

AIRA OS eliminates the tedious requirement of manually provisioning every router, switch, and access point. 

An engineer registers a single authorized gateway or core switch as the **initial discovery seed**. AIRA then autonomously interrogates available discovery protocols and maps the reachable infrastructure.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AUTHORIZED SEED DEVICE                          │
│               Core-Router-01 (192.168.1.1 / ASN 65001)                 │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
      L2 Discovery Protocols                    L3 Routing & ARP
      • MikroTik MNDP                           • Active IPv4/IPv6 ARP tables
      • IEEE 802.1AB LLDP                       • Next-hop route gateways
      • Cisco Discovery Protocol (CDP)          • DHCP Server Leases
              │                                         │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   CAPABILITY-BASED DISCOVERY ENGINE                    │
│                                                                        │
│  1. Ingest Raw Evidence & Normalize MAC / IP / Chassis IDs            │
│  2. Deduplicate Nodes via Stable Hardware & L2 Identifiers             │
│  3. Multi-Interface Link Synthesis (preserve port names)              │
│  4. Progressive Scoping (Bounded Depth: Hop <= 2, Approved Subnets)   │
│  5. Loop Prevention & Non-Invasive Passive Traversal                   │
│  6. Pending Device Classification (Do NOT inject dummy passwords)     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   MANAGED INFRASTRUCTURE                     PENDING DISCOVERED DEVICES
   • Verified credentials                     • "Device discovered — SNMP available
   • Live SNMP / SSH telemetry                  — SSH credentials not configured."
   • Real-time NMS monitoring                 • Contextual action:
                                                [ Add to Inventory / Configure Access ]
```

---

## 2. Multi-Protocol Evidence Normalization

Different hardware vendors expose varying levels of telemetry. AIRA uses capability-based parsers:
- **MikroTik MNDP:** Extracts identity, RouterOS software version, board name, chassis MAC address, and neighbor interface.
- **IEEE 802.1AB LLDP / CDP:** Vendor-neutral discovery extracting chassis ID, system name, port description, and management address.
- **ARP & Bridge Host Tables:** Correlates IP addresses with physical switch ports without active probing.
- **Routing Next-Hops:** Identifies layer 3 adjacent routers and gateway boundaries.

---

## 3. Pending Discovered Device Lifecycle

AIRA OS strictly rejects the practice of automatically creating inventory records with guessed or default passwords. Discovered devices progress through explicit, deterministic lifecycle states:

```
[ Discovered via L2/ARP ]
          │
          ▼
[ Pending Identification ] ──(SNMP probe succeeds)──► [ SNMP Accessible ]
          │                                                    │
          ▼                                                    ▼
[ Credential Required ] <──────────────────────────────────────┘
          │
          ▼  (Engineer provides verified SSH/API credentials via
              POST /api/devices/promote-discovered)
[ Credential Verified ]
          │
          ▼
[ Managed & Monitored ]
```

### Contextual Promotion (`POST /api/devices/promote-discovered`)
When promoting a pending device:
- The device is added to `inventory.db` with Fernet-encrypted credentials.
- The topology node provenance is updated from `discovery_managed` to `user_managed`.
- All discovered L2/L3 links, connected interfaces, and neighbor relationships are preserved without redrawing or recreating the graph.

---

## 4. Connection Types & Multi-Interface Model

AIRA classifies all relationships into 4 explicit relationship classes:
1. **Physical:** Verified direct cable adjacency (`direct_copper`, `fiber`, `sfp`).
2. **Layer 2 Adjacency:** Shared bridge, VLAN trunk, or LLDP/MNDP neighbor link.
3. **Layer 3 Reachability:** Routed subnet, point-to-point /30 or /31 link, next-hop relationship.
4. **Logical Overlay:** WireGuard, OpenVPN, EoIP tunnel, VXLAN, L2TP, GRE.

### Inferred vs. Confirmed Relationships
Links derived purely from single-sided ARP or shared subnets are rendered with distinctive dashed visual styling (`inferred`) and labeled with their mathematical confidence score until verified bidirectionally.
