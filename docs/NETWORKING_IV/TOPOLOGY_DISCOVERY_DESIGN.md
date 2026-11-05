# AIRA OS — TOPOLOGY DISCOVERY DESIGN
## Evidence-Based Multi-Layer Network Discovery Specification

**Document ID:** `AIRA-NET-IV-DISCOVERY-001`  
**Date:** 2026-10-31 (Revised)  
**Project:** AIRA OS — Phase Networking IV  
**Status:** ARCHITECTURE_DESIGN_SPECIFICATION  

---

## 1. Overview & Discovery Mission

Topology Discovery in AIRA OS is designed to construct an accurate, multi-layer graph of an enterprise network solely using authorized, non-intrusive, read-only observations.

Unlike simplistic discovery tools that assume any IP responding to an ARP request represents a physical cable connection, AIRA's discovery engine implements **Epistemic Layer Separation**: it strictly differentiates between Layer 1/2 physical and link-layer adjacencies, Layer 3 IP routing relationships, and Layer 2 broadcast domains.

### Primary Directives:
1. **Strict Read-Only Interrogation:** Only non-mutating inspection commands are permitted.
2. **Deterministic Confidence Tiers:** Every link must be classified into one of 4 strict tiers based on evidence quality.
3. **No False Physical Adjacency:** A shared IP subnet or ARP entry must never be promoted to physical cabling without verified Layer 2 neighbor or port-level switch proof.
4. **Boundary & Scope Protection:** Discovery never blindly scans the public internet or unauthorized upstream ISP networks.
5. **Multi-Edge Distinction:** Dual cables, VLAN trunks, and overlay tunnels between the same pair of nodes are recorded as separate, typed edges.

---

## 2. Read-Only Evidence Extraction Protocol

The discovery engine communicates with network devices via the **AIRA Persistent Connection Engine (APCE)** using version-aware command mappings:

### 2.1 RouterOS Command Matrix (v6 & v7)

| Telemetry Domain | RouterOS CLI Command | Primary Information Extracted |
|---|---|---|
| **Identity** | `/system identity print` | Device hostname / system identity string |
| **Hardware & OS** | `/system resource print`<br>`/system routerboard print` | Architecture, CPU, RAM, RouterOS version, model, serial number |
| **Interfaces** | `/interface print detail` | Interface names, types (`ether`, `bridge`, `vlan`, `wireguard`), MAC addresses, MTU, running (`R`) / disabled (`X`) flags |
| **IP Addressing** | `/ip address print detail` | Assigned IP addresses, subnet masks, bound interfaces |
| **Routing Information**| `/ip route print detail` | Connected routes (`DAC`), static routes (`DAS`), dynamic routes, default gateways (`0.0.0.0/0`), next-hop interfaces |
| **Neighbor Discovery** | `/ip neighbor print detail` | MNDP/LLDP/CDP neighbors: remote identity, chassis ID, remote interface, local interface, IP address |
| **ARP Table** | `/ip arp print detail` | IP-to-MAC mappings, bound interface, dynamic (`D`) / published (`P`) flags |
| **Bridge & Switching** | `/interface bridge port print detail`<br>`/interface bridge host print detail` | Bridge member ports, learned MAC addresses per port, aging timers |
| **VLAN Configuration** | `/interface vlan print detail`<br>`/interface bridge vlan print detail` | VLAN IDs, tagged/untagged port memberships |
| **DHCP Services** | `/ip dhcp-server lease print detail`<br>`/ip dhcp-client print detail` | Active leases, client hostnames, MAC addresses, upstream DHCP gateway |

---

## 3. Four-Tier Evidentiary Classification Model

To guarantee that operators can trust the topology canvas, every discovered edge between two nodes is classified into one of four deterministic confidence tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        4-TIER CONFIDENCE MODEL                         │
├───────┬─────────────────────────────────┬──────────────────────────────┤
│ Tier  │ Classification                  │ Permitted Relationship Class │
├───────┼─────────────────────────────────┼──────────────────────────────┤
│ Tier 1│ DIRECTLY OBSERVED CONNECTION    │ Strictly PHYSICAL or L2      │
│ Tier 2│ STRONGLY INFERRED RELATIONSHIP  │ L2 Fabric or L3 P2P Subnet   │
│ Tier 3│ WEAKLY INFERRED RELATIONSHIP    │ Multi-Access L3 Subnet/Route │
│ Tier 4│ UNKNOWN / CANDIDATE             │ Unverified IP/MAC or ISP Wan │
└───────┴─────────────────────────────────┴──────────────────────────────┘
```

### 3.1 Tier 1: Directly Observed Connection (`CONFIRMED`)
- **Definition:** Verified physical or direct link-layer connection where both endpoints identify each other across a specific port.
- **Required Evidence:**
  - Active MNDP, LLDP, or CDP neighbor advertisement received on local physical port $P_A$ advertising remote device B on physical port $P_B$.
  - Or bidirectional corroboration: Device A sees Device B on $P_A$, and Device B sees Device A on $P_B$.
  - Or explicit, verified administrator manual wiring entry (`user_confirmed`).
- **Permitted Class:** Strictly `PHYSICAL_ADJACENCY` (or `LAYER2_ADJACENCY` for bridge port members).
- **Visual Representation:** Solid bold line with verified interface badges on both endpoints (e.g., `ether1` $\leftrightarrow$ `ether2`).

### 3.2 Tier 2: Strongly Inferred Relationship (`OBSERVED`)
- **Definition:** High-probability direct point-to-point Layer 3 connection where neighbor discovery protocols are disabled or filtered, but network addressing and ARP provide unambiguous proof.
- **Required Evidence:**
  - Point-to-point subnet addressing: A dedicated `/30` (2 usable hosts) or `/31` (RFC 3021) subnet shared exclusively between Device A and Device B.
  - Mutual ARP corroboration: Device A has Device B's interface MAC in its ARP table on interface $I_A$, and Device B has Device A's interface MAC in its ARP table on interface $I_B$.
  - Or single-sided LLDP/MNDP neighbor where remote device is unmanaged but advertises a valid, non-randomized chassis MAC.
- **Permitted Class:** Strictly `LAYER3_REACHABILITY` (`routed_point_to_point`) or `LAYER2_ADJACENCY`.
- **Visual Representation:** Solid thin line with verified local interface and inferred/question-mark remote port.

### 3.3 Tier 3: Weakly Inferred Relationship (`INFERRED`)
- **Definition:** Logical reachability or common broadcast domain transit where physical cable topology cannot be proven.
- **Examples & Evidence:**
  - Common multi-access subnet (e.g., `/24`, `/23`): Device A and Device B share an IP subnet, but multiple other devices exist in that subnet (indicating an unmanaged switch or VLAN broadcast domain).
  - Routing Next-Hop: Device A's default route points to Device B's IP address, but without mutual port-level switch verification.
  - Bridge Host Table entry: Device A learned Device B's MAC on a bridge, but the bridge has multiple physical ports and no port-to-port LLDP match.
- **Permitted Class:** Strictly `LAYER3_REACHABILITY` (`routed_multiaccess`) or `LOGICAL_RELATIONSHIP`.
- **Visual Representation:** Dashed line with clear badge `[Inferred L3]` or `[Shared L2]`.

### 3.4 Tier 4: Unknown / Candidate Relationship (`UNKNOWN`)
- **Definition:** Newly discovered end-host, unclassified MAC, or upstream ISP boundary node that requires human review.
- **Evidence:**
  - ARP table entry with randomized/locally administered MAC address (IEEE 802 bit 1 set).
  - Out-of-band or upstream gateway observed via DHCP client on an ISP-designated interface.
- **Visual Representation:** Dotted line with warning badge and inclusion in the Operator Review Queue (`ReviewQueueModal`).

---

## 4. Multi-Source Evidence Fusion & Corroboration Engine

The discovery engine fuses multiple independent sources of telemetry into a single reconciled graph:

```
                ┌──────────────────────────────────────┐
                │          ROUTER CLI TELEMETRY        │
                └──────────────────┬───────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
┌────────▼──────────┐    ┌─────────▼─────────┐     ┌─────────▼─────────┐
│ Layer 2 Neighbors │    │  Layer 3 Routing  │     │   ARP & Bridge    │
│  (MNDP/LLDP/CDP)  │    │  (Subnets/Routes) │     │   (MACs/Ports)    │
└────────┬──────────┘    └─────────┬─────────┘     └─────────┬─────────┘
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ CrossDeviceEvidenceCorrelator│
                    │   - Rule-based reconciliation│
                    │   - Contradiction detection  │
                    │   - Confidence assignment    │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    Normalized Edge Graph    │
                    └─────────────────────────────┘
```

### Fusion Rules:
1. **Rule L2-Over-L3:** An L2 neighbor advertisement creates an edge of class `PHYSICAL_ADJACENCY` or `LAYER2_ADJACENCY`. A subnet or route overlap creates an edge of class `LAYER3_REACHABILITY`. They coexist as distinct parallel edges rather than overwriting each other.
2. **Rule Interface-Binding:** An edge must explicitly record `source_interface` and `target_interface`. If the remote interface cannot be discovered, `target_interface` is set to empty string `""` and rendered as `?` in the UI.
3. **Rule Contradiction-Detection:** If Device A claims to see Device B on `ether1`, but Device B is known to be connected to Device C on that exact MAC, a `topology_conflict` record is created and flagged for operator review.

---

## 5. Boundary Protection & Multi-Hop Traversal Policies

To prevent accidental discovery of external networks or overwhelming unauthorized devices, discovery is constrained by strict boundary policies stored in `topology_policy`:

### 5.1 Discovery Modes
1. **`seed_only` (Default):** Interrogates only the specified seed router. Discovers direct neighbors and local subnets without opening connections to any other devices.
2. **`enterprise_managed`:** Discovers the seed router, and recursively expands only to neighbor devices that are already registered and enabled in `AIRA Inventory` (`inventory.db`).
3. **`authorized_expansion`:** Allows discovery to attempt read-only SSH connection to newly discovered candidate devices, provided they reside strictly within `approved_discovery_scopes` (e.g. `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and are not in `excluded_subnets`.

### 5.2 ISP & Perimeter Boundary Rules
- Any interface configured in `isp_boundary_interfaces` (or carrying a default route via DHCP from a public IP) is classified as `topology_scope = "isp_upstream"`.
- Upstream nodes connected to ISP boundary interfaces are automatically classified as `ownership_status = "third_party"` and `trust_zone = "isp"`.
- Discovery **never** attempts SSH/SNMP probing toward upstream ISP gateways or public internet addresses.
