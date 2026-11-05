# AIRA OS — UNIFIED EVIDENCE MODEL SPECIFICATION
## Canonical Evidence Envelope, Type-Aware Freshness & Zero-Duplicate Reuse (WP 6.0 / WP 6.1)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Design Objectives

Networking VI introduces `UnifiedEvidenceService` and `NetworkEvidenceBundle` (`core/network_intelligence/evidence_service.py`) to assemble multi-device evidence across Inventory, NMS, Topology, Route Analytics, and SSH CLI collectors **without redundant SSH queries, unbounded payload copies, or fabricated defaults**.

---

## 2. Canonical Evidence Record (`CanonicalEvidenceRecord`)

Every normalized observation wrapped or referenced in Networking VI carries:

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `str` | Deterministic or unique ID (`ev_<domain>_<dev>_<hash>`) |
| `device_id` | `str` | Canonical device ID (`dev_r1`, `topo_...`) |
| `device_identity` | `str` | Observed RouterOS identity / hostname or inventory name |
| `evidence_type` | `str` | Domain category (`device_resources`, `interfaces`, `routes`, `ip_addresses`, `arp`, `neighbors`, `ospf_neighbors`, `bgp_peers`, `bridge_vlan`, `firewall_filter`, `nat_rules`, `nms_telemetry`, `topology_edges`, `nms_incidents`, `route_snapshot`) |
| `source_subsystem` | `str` | `nms`, `topology`, `routing`, `inventory`, `ssh_cli`, `snmp` |
| `collection_method` | `str` | `icmp_probe`, `snmp_v2c`, `snmp_v3`, `routeros_ssh_readonly`, `sqlite_cache`, `snapshot_store` |
| `collected_at` | `float` | Epoch timestamp when AIRA collected the record |
| `observed_at` | `Optional[float]` | Underlying measurement timestamp (differs from `collected_at` when reading cached DB telemetry) |
| `validity_ttl_sec` | `float` | Evidence-type-specific freshness window |
| `freshness` | `str` | `FRESH`, `AGING`, `STALE`, `EXPIRED`, `UNKNOWN` |
| `quality` | `str` | `GOOD`, `PARTIAL`, `DISCONTINUOUS`, `UNCERTAIN`, `MISSING`, `CONTRADICTORY`, `INVALID` |
| `parser_version` | `str` | Parser contract version (e.g. `4.6.0` for `UnifiedRouteParser`, `6.1.0` for unified normalizer) |
| `normalized_payload` | `Dict[str, Any]` | Compact, structured, typed data projection |
| `source_reference` | `str` | Snapshot ID, DB table/row ref, or bundle ID |
| `sanitized_command_ref` | `str` | Redacted CLI command or OID group (never contains credentials) |
| `confidence` | `float` | `0.0`–`1.0` observation reliability score |
| `completeness` | `str` | `COMPLETE`, `PARTIAL`, `EMPTY`, `UNAVAILABLE` |
| `provenance` | `Dict[str, Any]` | Traceability metadata (`vantage_point`, `reused_from_cache`, `limitations`) |

---

## 3. Evidence-Type-Aware Freshness Model

Unlike a single rigid TTL, network observations age at fundamentally different rates. `evaluate_evidence_freshness(evidence_type, timestamp, now)` enforces domain-specific lifetimes:

| Evidence Category | `FRESH` ($\le$) | `AGING` ($\le$) | `STALE` ($\le$) | `EXPIRED` ($>$) | Engineering Rationale |
|---|---|---|---|---|---|
| **Fast Resource & Rate Telemetry** (`cpu`, `memory`, `latency`, `interface_rates`) | 45s | 120s | 300s | > 300s | Polling cycles run every 15–45s; 5-minute-old CPU load cannot prove current saturation. |
| **Interface Operational State** (`interfaces`, `oper_status`) | 60s | 180s | 600s | > 600s | Link state changes propagate via NMS events; >10m without verification is expired. |
| **Dynamic Routing & Neighbors** (`routes`, `ospf_neighbors`, `bgp_peers`, `arp`) | 90s | 300s | 900s | > 900s | Hold/dead timers and ARP caches turn over within 1–15 minutes. |
| **Topology Adjacency & Snapshots** (`topology_edges`, `neighbors`) | 300s | 900s | 3600s | > 3600s | Physical cabling and MNDP/LLDP topology change infrequently compared to CPU counters. |
| **Static Configuration Rules** (`ip_addresses`, `bridge_vlan`, `nat_rules`, `firewall_filter`, `routing_rules`) | 300s | 1800s | 7200s | > 7200s | Static rules persist until human change or DHCP lease renewal. |
| **Missing / Unset Timestamp** (`timestamp <= 0` or `None`) | — | — | — | `UNKNOWN` | Never fabricated as `FRESH`. |

---

## 4. Evidence Acquisition Precedence & Reuse Pipeline

When an investigation requests `NetworkEvidenceBundle(scope, target_devices, required_types, allow_live_collection)`:

1. **Step 1 — Canonical Device & Inventory Resolution:** Pull `CanonicalDevice` records from `CanonicalNetworkRegistry`.
2. **Step 2 — Reuse Fresh NMS Telemetry (`topology.db`):**
   - Read `nms_device_profiles`, latest `nms_device_metrics` / `nms_raw_metrics`, latest `nms_interface_metrics`, and open/recent `nms_incidents`.
   - If `device_resources` or `interfaces` are `FRESH` or `AGING` in NMS, synthesize `CanonicalEvidenceRecord` directly (`reused_from_cache=True`) — **zero SSH commands issued**.
   - First-sample interface rates without a prior counter baseline preserve `rx_rate_bps=None` (`SampleQuality.UNCERTAIN`), never `0.0` bps.
3. **Step 3 — Reuse Cached Route & Topology Intelligence:**
   - Read `MultiDeviceRouteCollector.get_latest_result(dev)` (and latest `route_snapshots` ref if available).
   - Read `TopologyEngine.get_topology()` edges (`EdgeEvidence`) and latest `topology_snapshots` ref.
4. **Step 4 — Selective Read-Only SSH Collection (Only When Needed & Permitted):**
   - Only for missing or `STALE`/`EXPIRED` observation types when `allow_live_collection=True` and the device is not already known `UNREACHABLE` within the cooldown window.
   - Dispatches bounded `MultiDeviceEvidenceOrchestrator` through `validate_readonly_command`.
5. **Step 5 — Gap & Contradiction Synthesis:**
   - Failed or skipped collections populate `collection_gaps` (`TELEMETRY_GAP` / `UNREACHABLE` / `NOT_COLLECTED`).
   - Cross-source contradictions (e.g., NMS ICMP `UP` while SSH fails `AUTH_FAILED`, or topology edge `UP` while local interface `oper_status="down"`, or duplicate IP across two routers) are recorded explicitly in `contradictions`.
