# AIRA OS — NETWORK KNOWLEDGE GRAPH MODEL
## Multi-Layer Entity, Relationship & Consistency Specification (WP 6.0 / WP 6.2)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Purpose & Epistemic Rules

The `NetworkKnowledgeGraph` represents the network as an interconnected multi-layer system rather than flat device-to-device lines. Every node and directed/bidirectional relationship carries explicit **evidence IDs, provenance, timestamps, freshness, and confidence**.

### Fundamental Invariants
1. **Layer Preservation:** Physical cabling, Layer-2 switching/bridging, Layer-3 IP reachability, routing control-plane dependencies, tunnels, and logical service dependencies NEVER collapse into a generic "connected" edge.
2. **No False Merging:** Two entities are never merged solely because they share an IP address (e.g., VRRP/anycast/duplicate IP collision, default `192.168.88.1`) or generic hostname (`MikroTik`).
3. **Partial Knowledge Tolerance:** An unobserved upstream gateway, unmanaged L2 switch, or external BGP AS is represented honestly as an external/unmanaged or partial entity (`completeness="PARTIAL"`) rather than an error or fabricated router.

---

## 2. Canonical Entity Types (21 Types)

All graph nodes use `KnowledgeNode` with deterministic canonical IDs (`<entity_type>:<scope_key>`):

| # | Entity Type (`GraphEntityType`) | Canonical ID Pattern | Primary Source(s) | Key Attributes |
|---|---|---|---|---|
| 1 | `DEVICE` | `device:<device_id>` | `CanonicalNetworkRegistry`, `TopologyEngine` | `display_name`, `management_ip`, `vendor`, `model`, `os_version`, `ros_major`, `is_managed`, `nms_status` |
| 2 | `INTERFACE` | `iface:<device_id>:<iface_name>` | `EvidenceCollector`, `NmsEngine` | `interface_type`, `mac_address`, `oper_status`, `admin_status`, `mtu`, `l2mtu`, `speed_bps` |
| 3 | `IP_ADDRESS` | `ip:<device_id>:<address>/<plen>` | `ip_addresses` evidence | `address`, `prefix_len`, `family`, `interface_name`, `is_dynamic`, `is_disabled` |
| 4 | `SUBNET` | `subnet:<vrf>:<network_cidr>` | Derived from `IP_ADDRESS` & connected routes | `network_cidr`, `prefix_len`, `family`, `vrf` |
| 5 | `VLAN` | `vlan:<scope>:<vlan_id>` | `bridge_vlan`, `/interface vlan` | `vlan_id`, `name`, `bridge_name`, `tagged_ports`, `untagged_ports` |
| 6 | `BRIDGE` | `bridge:<device_id>:<bridge_name>` | `bridge`, `bridge_ports` | `bridge_name`, `vlan_filtering`, `protocol_mode`, `ports` |
| 7 | `VRF` | `vrf:<device_id>:<vrf_name>` | `NormalizedRoute.routing_table` | `vrf_name`, `device_id` |
| 8 | `ROUTING_TABLE` | `rtable:<device_id>:<table>` | `RouteCollectionResult` | `table_name`, `route_count`, `active_count` |
| 9 | `ROUTE` | `route:<device_id>:<table>:<prefix>:<gw>:<dist>` | `UnifiedRouteParser` (`NormalizedRoute`) | `dst_prefix`, `gateway`, `protocol`, `distance`, `scope`, `target_scope`, `active`, `route_type` |
| 10 | `NEXT_HOP` | `nexthop:<device_id>:<table>:<gw_ip>` | `NormalizedRoute` / `RouteDependencyAnalyzer` | `gateway_ip`, `resolved_iface`, `is_recursive`, `resolution_state` |
| 11 | `GATEWAY` | `gateway:<gw_ip>` | Route gateways & DHCP/WAN config | `ip_address`, `owner_device_id`, `is_external` |
| 12 | `ROUTING_PROTOCOL_INSTANCE` | `proto:<device_id>:<proto>:<name>` | `ospf_instance`, `bgp_peers` | `protocol` (`ospf`/`bgp`), `router_id`, `as_number`, `areas` |
| 13 | `OSPF_NEIGHBOR` | `ospf_nbr:<device_id>:<neighbor_id>:<iface>` | `ospf_neighbors` | `router_id`, `address`, `interface`, `state`, `area` |
| 14 | `BGP_PEER` | `bgp_peer:<device_id>:<remote_addr>` | `bgp_peers` | `remote_address`, `remote_as`, `local_as`, `peer_type` (`ebgp`/`ibgp`), `state`, `prefixes_received` |
| 15 | `TUNNEL` | `tunnel:<device_id>:<iface_name>` | Tunnel interfaces (`gre`, `ipip`, `eoip`, `wg`, `l2tp`) | `tunnel_type`, `local_address`, `remote_address`, `mtu`, `oper_status` |
| 16 | `WAN_CONNECTION` | `wan:<device_id>:<iface_or_gw>` | Default route egress + ISP scope | `egress_interface`, `gateway_ip`, `latency_ms`, `packet_loss_pct`, `status` |
| 17 | `SERVICE_ENDPOINT` | `service:<service_type>:<target>` | DNS, NTP, management, or probed target | `service_type`, `address`, `port`, `reachable` |
| 18 | `NETWORK_SEGMENT` | `segment:<segment_key>` | Broadcast domain / bridged L2/VLAN segment | `vlan_id`, `subnet_cidr`, `member_count` |
| 19 | `INCIDENT` | `incident:<source>:<incident_id>` | `nms_incidents`, `network_intelligence.db` | `severity`, `status`, `incident_type`, `started_at`, `suppressed` |
| 20 | `TELEMETRY_OBSERVATION` | `telemetry:<device_id>:<metric>:<iface>` | `nms_raw_metrics`, `nms_device_metrics` | `metric_name`, `value`, `unit`, `quality`, `freshness` |
| 21 | `CONFIGURATION_SNAPSHOT` | `cfgsnap:<device_id>:<snapshot_id>` | `route_snapshots`, `topology_snapshots`, plans | `snapshot_type`, `sha256_hash`, `captured_at`, `completeness` |

---

## 3. Canonical Relationship Types (18 Types)

Every `KnowledgeEdge` carries `edge_id`, `source_id`, `target_id`, `relationship_type`, `layer`, `evidence_ids`, `provenance`, `confidence`, `observed_at`, `valid_until`, `freshness`, and `is_inferred`:

| # | Relationship Type (`GraphRelationshipType`) | Source $\to$ Target | Semantics & Evidentiary Requirement |
|---|---|---|---|
| 1 | `PHYSICAL_ADJACENCY` | `DEVICE`/`INTERFACE` $\leftrightarrow$ `DEVICE`/`INTERFACE` | Direct Layer-1 link verified by bidirectional LLDP/MNDP/CDP port match or explicit operator confirmation. **Never** inferred from subnet or ARP alone. |
| 2 | `LAYER2_ADJACENCY` | `DEVICE`/`INTERFACE` $\leftrightarrow$ `DEVICE`/`INTERFACE` | Same switched/bridged L2 domain evidenced by bridge host table, unidirectional neighbor discovery, or mutual ARP + subnet match. |
| 3 | `LAYER3_REACHABILITY` | `DEVICE` $\to$ `DEVICE` / `IP_ADDRESS` | Observed IP-level reachability (ICMP probe or active L3 management session). |
| 4 | `LOGICAL_RELATIONSHIP` | Entity $\to$ Entity | Logical grouping, VPN overlay peerage, or management dependency. |
| 5 | `HOSTED_ON` | `INTERFACE` / `VRF` / `ROUTING_TABLE` / `BRIDGE` / `TUNNEL` / `ROUTING_PROTOCOL_INSTANCE` $\to$ `DEVICE` | Structural containment on a specific device. |
| 6 | `MEMBER_OF` | `INTERFACE` $\to$ `BRIDGE` / `VLAN` / `VRF` / `NETWORK_SEGMENT`, or `IP_ADDRESS` $\to$ `SUBNET` | Membership in a logical or broadcast container. |
| 7 | `ADDRESSED_WITH` | `INTERFACE` / `DEVICE` $\to$ `IP_ADDRESS` | Assigned IPv4/IPv6 interface address. |
| 8 | `ROUTES_TO` | `ROUTING_TABLE` / `ROUTE` $\to$ `SUBNET` | Control-plane route destination prefix coverage. |
| 9 | `NEXT_HOP_OF` | `NEXT_HOP` / `GATEWAY` $\to$ `ROUTE` | Next-hop gateway used by a RIB route entry. |
| 10 | `PEERS_WITH` | `ROUTING_PROTOCOL_INSTANCE` / `OSPF_NEIGHBOR` / `BGP_PEER` $\leftrightarrow$ `DEVICE` / `IP_ADDRESS` | Control-plane routing protocol peering/adjacency. |
| 11 | `ADVERTISES` | `ROUTING_PROTOCOL_INSTANCE` / `DEVICE` $\to$ `SUBNET` / `ROUTE` | Prefix advertised to peers when protocol evidence confirms advertisement. |
| 12 | `LEARNS` | `ROUTING_TABLE` / `DEVICE` $\to$ `ROUTE` | Dynamic route learned via OSPF, BGP, RIP, or DHCP. |
| 13 | `DEPENDS_ON` | Downstream Entity $\to$ Upstream Entity | Operational or recursive forwarding dependency (e.g., recursive route $\to$ resolving route; LAN segment $\to$ WAN connection; downstream device $\to$ upstream transit router). |
| 14 | `CARRIES` | `INTERFACE` / `BRIDGE` / `TUNNEL` $\to$ `VLAN` / `SUBNET` | Trunk/access port or tunnel carrying traffic for a VLAN or subnet. |
| 15 | `CONNECTS_TO` | `INTERFACE` / `WAN_CONNECTION` / `TUNNEL` $\to$ `NETWORK_SEGMENT` / `GATEWAY` / `SUBNET` | Attachment of an interface or tunnel endpoint to a network segment or upstream gateway. |
| 16 | `AFFECTS` | `INCIDENT` $\to$ `DEVICE` / `INTERFACE` / `SUBNET` / `WAN_CONNECTION` | Incident scope attachment. |
| 17 | `OBSERVED_BY` | `TELEMETRY_OBSERVATION` / `CONFIGURATION_SNAPSHOT` $\to$ `DEVICE` | Telemetry or snapshot provenance link. |
| 18 | `CAUSED_POSSIBLY_BY` | `INCIDENT` (Symptom) $\to$ `INCIDENT` / Entity (Candidate Cause) | Epistemic hypothesis link produced by correlation/RCA (explicitly non-confirmed causation). |

---

## 4. Graph Consistency & Bounded Query Rules

1. **Consistency Validation (`validate_graph_consistency`):**
   - Detects unknown/unresolved device references, orphaned interfaces, dangling edge endpoints, stale/expired edges, duplicate canonical relationships, IP address collisions across distinct devices, and conflicting operational states (e.g., interface `DOWN` on one side of a `PHYSICAL_ADJACENCY` while peer port reports `UP`).
2. **Bounded Traversal Guarantees:**
   - Every graph traversal enforces `max_depth` (default `8`, hard ceiling `16`) and `max_visited_nodes` (default `500`, hard ceiling `2,000`) using iterative `collections.deque` (never unbounded recursion).
3. **Immutable Historical Projection:**
   - Historical graph views reconstruct `NetworkKnowledgeGraph` instances strictly in-memory from immutable `topology_snapshots` and `route_snapshots` without mutating persisted snapshot rows.
