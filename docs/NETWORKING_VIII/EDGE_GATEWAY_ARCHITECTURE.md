# AIRA OS — NETWORKING VIII: HYBRID EDGE GATEWAY ARCHITECTURE
## Secure Outbound Hybrid Agent, Enrollment Protocol & Offline Resiliency

**Document ID:** `AIRA-NET8-GATEWAY-001`  
**Date:** 2026-11-04  
**Workspace:** `D:\data\agent_ai`  
**Repository:** `https://github.com/TKJ-Networkers31/Network_AI_Agent.git`  
**Target Milestone:** Networking VIII  
**Organization:** LS Technology

---

## 1. Hybrid Deployment Topology

In managed enterprise networks, customer infrastructure is located behind strict corporate firewalls, carrier-grade NAT (CGNAT), and dynamic IP allocations. Requiring customer IT teams to open inbound firewall ports or establish complex site-to-site IPsec VPNs to Central NOC is operationally prohibitive.

**Core Design Principle:**
> The Customer Edge Gateway connects **outbound** to Central AIRA NOC over secure TLS / WebSocket. The customer network requires zero inbound port forwards.

```
 CUSTOMER PREMISES                                       LS TECHNOLOGY CENTRAL NOC
┌──────────────────────────────────────────────┐        ┌───────────────────────────────┐
│ [Customer Routers / Switches / APs]          │        │                               │
│  (192.168.1.0/24 LAN / Mgmt Subnet)          │        │                               │
│          ▲                                   │        │                               │
│          │ (Local Read-Only SSH / API / SNMP)│        │                               │
│          ▼                                   │        │                               │
│ ┌──────────────────────────────────────────┐ │        │ ┌───────────────────────────┐ │
│ │       AIRA Customer Edge Gateway         │ │        │ │   Central Edge Gateway    │ │
│ │                                          │ │        │ │       Ingestion Hub       │ │
│ │ ┌──────────────────────────────────────┐ │ │        │ └─────────────┬─────────────┘ │
│ │ │ Local Discovery & Collector Engine   │ │ │        │               │               │
│ │ └──────────────────┬───────────────────┘ │ │        │ ┌─────────────▼─────────────┐ │
│ │                    ▼                     │ │        │ │  Identity & Token Verify  │ │
│ │ ┌──────────────────────────────────────┐ │ │        │ └─────────────┬─────────────┘ │
│ │ │ Bounded Local Telemetry Buffer       │ │ │        │               │               │
│ │ │ (Max 5,000 samples / SQLite FIFO)    │ │ │        │ ┌─────────────▼─────────────┐ │
│ │ └──────────────────┬───────────────────┘ │ │        │ │ Decimation & Metrics Store│ │
│ │                    ▼                     │ │        │ └───────────────────────────┘ │
│ │ ┌──────────────────────────────────────┐ │ │        │                               │
│ │ │ Outbound TLS / WSS Transport Client  │ ┼─┼────────┼─► (WSS / TLS 1.3 Port 443)    │
│ │ └──────────────────────────────────────┘ │ │        │                               │
│ └──────────────────────────────────────────┘ │        │                               │
└──────────────────────────────────────────────┘        └───────────────────────────────┘
```

---

## 2. Gateway Identity & Enrollment Lifecycle

Each Edge Gateway is uniquely identified by:
- `gateway_id`: Globally unique identifier (e.g. `gw_c1a2_site1_9f3b`).
- `tenant_id`: Mandatory owning customer organization.
- `site_id`: Specific physical/logical customer site.
- `enrollment_state`: `UNENROLLED` $\rightarrow$ `ENROLLING` $\rightarrow$ `ENROLLED` $\rightarrow$ `REVOKED`.
- `connection_state`: `OFFLINE` $\rightarrow$ `CONNECTING` $\rightarrow$ `ONLINE` $\rightarrow$ `DEGRADED`.
- `certificate_fingerprint`: SHA-256 hash of gateway's client certificate or public key.

### 2.1 Enrollment Protocol Workflow

```
NOC Operator           Central AIRA NOC                 Customer Edge Gateway
     │                        │                                   │
     ├──(1. Create Token)────>│                                   │
     │   (tenant_id, site_id) │                                   │
     │<──(Token String)───────┤                                   │
     │                        │                                   │
  [Operator provides token    │                                   │
   to gateway config]         │                                   │
     │                        │                                   │
     │                        │<──(2. POST /api/v1/gateways/enroll)─┤
     │                        │   {token, public_key, host_info}  │
     │                        │                                   │
     │                        ├──(Validate: Not Expired, Not Revoked,
     │                        │             Tenant Exists)        │
     │                        ├──(Bind Gateway to Tenant & Site)  │
     │                        ├──(Mark Token as REDEEMED)         │
     │                        ├──(Generate Gateway Identity Credentials)
     │                        │                                   │
     │                        ├──(3. Return Enrollment Response)─►│
     │                        │   {gateway_id, signed_cert, config}│
     │                        │                                   │
     │                        │<──(4. Connect WSS with Mutual Auth)─┤
     │                        │                                   │
     │                        ├──(5. Connection Authenticated)────►│
```

### 2.2 Enrollment Security Rules
1. **Single-Use Guarantee:** Enrollment tokens are invalidated in the database immediately upon first redemption within an atomic transaction.
2. **Short Lifetime:** Enrollment tokens expire 15 minutes after creation.
3. **Strict Tenant & Site Scope:** A token created for Tenant A cannot be redeemed by Tenant B or bound to a site in another tenant.
4. **No Plaintext Secret Storage:** Token secrets are generated with cryptographic entropy (`secrets.token_urlsafe(32)`) and stored hashed (SHA-256).

---

## 3. Communication Protocol & Telemetry Envelopes

The Edge Gateway maintains a persistent WebSocket connection over TLS 1.3 to Central NOC.

### 3.1 Telemetry Envelope Format
```json
{
  "envelope_id": "env_9a8b7c6d5e",
  "gateway_id": "gw_c1a2_site1_9f3b",
  "tenant_id": "tenant_c1a2",
  "site_id": "site_jakarta_hq",
  "sequence_number": 10425,
  "sent_at_utc": "2026-11-04T03:30:00Z",
  "telemetry_type": "INTERFACE_METRICS",
  "payload": {
    "device_id": "dev_c1a2_site1_r1",
    "interface_name": "ether1-wan",
    "rx_bytes": 104857600,
    "tx_bytes": 52428800,
    "rx_errors": 0,
    "tx_errors": 0,
    "status": "UP"
  }
}
```

### 3.2 Heartbeat & Health Monitoring
- The gateway sends a heartbeat ping every **30 seconds**:
  `{"type": "heartbeat", "gateway_id": "...", "timestamp": 1730700000, "buffer_depth": 0}`.
- If Central NOC receives no heartbeat for **90 seconds** (3 missed cycles), the gateway is flagged `OFFLINE` and a `P3_MEDIUM` operational alert is queued.

---

## 4. Offline Resiliency & Bounded Buffering

During internet service provider disruptions or central WAN maintenance, the Edge Gateway cannot reach Central NOC.
1. **Local SQLite Queue:** Telemetry samples are buffered into a local lightweight SQLite queue (`edge_buffer.db`).
2. **Buffer Limits:** Capped at **5,000 samples** or **24 hours retention** (consuming $< 2$ MB on disk).
3. **Backpressure & Drop Policy:** If the buffer fills beyond 5,000 samples, oldest non-critical telemetry samples are dropped first (`FIFO`), and a buffer-overflow diagnostic record is logged.
4. **Replay-Safe Reconnection:** When WAN connectivity is restored, the gateway flushes the buffer in chronologically ordered batches (max 100 samples per batch) with monotonic sequence numbers, preventing duplicate metric writes at Central NOC.

---

## 5. Gateway Command Security & Zero Mutation Boundary

**Absolute Constraint:** Central NOC operators cannot dispatch arbitrary shell commands or router configuration modifications through the Edge Gateway.

Allowed Gateway Commands:
- `PROBE_PING`: Run ICMP ping to a local subnet device.
- `PROBE_PORT`: Check TCP port reachability (e.g. port 8728 / 22).
- `COLLECT_TELEMETRY`: Trigger immediate read-only telemetry poll.
- `GATEWAY_HEALTH`: Report CPU, memory, and buffer depth.

Any command containing shell characters (`|`, `;`, `&`, `$`, `>`, `<`) or mutating verbs (`add`, `set`, `remove`, `disable`) is rejected by the Edge Gateway's local command sanitizer with an alert logged to Central NOC.
