# AIRA OS — NETWORKING VIII: WORK PACKAGE 8.4
# HYBRID EDGE GATEWAY PROTOCOL SPECIFICATION

**Project:** AIRA OS — AI Network Engineering Assistant  
**Milestone:** Networking VIII  
**Work Package:** WP 8.4 — Edge Gateway Communication Protocol  
**Organization:** LS Technology  
**Workspace:** `D:\data\agent_ai`  

---

## 1. PROTOCOL ARCHITECTURE

The AIRA OS Edge Gateway Protocol defines the wire contract between Central NOC and remote Customer Edge Gateways.

All communications are initiated **outbound** from the Customer Edge Gateway to the Central NOC over HTTPS (TLS 1.3). The Edge Gateway requires zero inbound open firewall ports at customer premises.

---

## 2. ENROLLMENT & AUTHENTICATION PROTOCOL

### 2.1 Token Generation (NOC to Database)
- **Initiator:** NOC Operator or System Administrator with `TenantAdmin` or `SuperAdmin` privileges.
- **Endpoint:** `POST /api/v1/gateways/tokens`
- **Payload:**
```json
{
  "tenant_id": "tenant_a1b2c3d4",
  "site_id": "site_e5f6g7h8",
  "expires_in_minutes": 15
}
```
- **Response:**
```json
{
  "token_id": "tok_9f8e7d6c",
  "raw_token": "aira_enroll_X8f9A1...32bytes",
  "tenant_id": "tenant_a1b2c3d4",
  "site_id": "site_e5f6g7h8",
  "expires_at_utc": "2026-11-04T12:15:00Z"
}
```
- **Security Properties:**
  * Raw token is high entropy (256-bit URL-safe string).
  * Central NOC stores only `SHA-256(raw_token)`.
  * Single-use only: Redemption atomically updates status to `REDEEMED`. Replays fail immediately.

### 2.2 Token Redemption (Edge Gateway to Central NOC)
- **Initiator:** Freshly installed Edge Gateway agent during initialization.
- **Endpoint:** `POST /api/v1/gateways/enroll`
- **Payload:**
```json
{
  "enrollment_token": "aira_enroll_X8f9A1...32bytes",
  "gateway_name": "Acme-HQ-Gateway-01",
  "version": "1.0.0",
  "certificate_fingerprint": "SHA256:4a6b8c...",
  "metadata": {
    "arch": "x86_64",
    "os": "Linux 6.1"
  }
}
```
- **Response (200 OK):**
```json
{
  "gateway_id": "gw_tenant_a1_site_e5_12ab34cd",
  "auth_token": "aira_gw_Z9y8X7...32bytes",
  "tenant_id": "tenant_a1b2c3d4",
  "site_id": "site_e5f6g7h8",
  "status": "ACTIVE"
}
```
- **Security Invariant:** Central NOC stores `SHA-256(auth_token)`. Gateway must store `auth_token` securely in local configuration (`edge_config.json`, mode 0600).

---

## 3. HEARTBEAT PROTOCOL

Edge Gateways submit periodic heartbeats to maintain active liveness registration and transmit local daemon telemetry.

- **Cadence:** Default 30 seconds (configurable 15s–60s).
- **Endpoint:** `POST /api/v1/gateways/heartbeat`
- **Headers:** `Authorization: Bearer <auth_token>`
- **Payload:**
```json
{
  "timestamp_utc": "2026-11-04T12:00:00Z",
  "cpu_utilization": 12.4,
  "memory_utilization": 35.8,
  "queue_depth": 0,
  "collector_status": "HEALTHY",
  "extra_json": "{}"
}
```
- **Liveness & Timeout Semantics:**
  * Missing heartbeats for > 180 seconds transitions gateway status to `OFFLINE`.
  * Central NOC raises a system alert upon `OFFLINE` transition.
  * Resumption of heartbeats automatically transitions status back to `ACTIVE`.

---

## 4. TELEMETRY INGESTION PROTOCOL

Edge Gateways batch local telemetry samples and transmit them to Central NOC.

- **Cadence:** Batch interval default 10 seconds or when queue reaches 25 samples.
- **Endpoint:** `POST /api/v1/gateways/telemetry`
- **Headers:** `Authorization: Bearer <auth_token>`
- **Request Envelope Format:**
```json
[
  {
    "envelope_id": "smp_1234abcd5678",
    "sequence_number": 1045,
    "telemetry_type": "INTERFACE_METRICS",
    "payload": {
      "device_id": "dev_rtr_core_01",
      "interface_name": "sfp-sfpplus1",
      "rx_utilization": 42.15,
      "tx_utilization": 28.60,
      "link_status": "UP"
    },
    "source_timestamp": 1793793600.0
  }
]
```

### 4.1 Ingestion Processing Rules
1. **Authentication:** Bearer token is validated; gateway status must be `ACTIVE`.
2. **Device Ownership Check:** `payload.device_id` is queried against `operational_devices`. If device belongs to another tenant or site, envelope is rejected as a security violation.
3. **Monotonic Sequence Rule:**
   $$\text{sequence\_number} > \text{last\_sequence\_number}$$
   Any envelope where $\text{sequence\_number} \le \text{last\_sequence\_number}$ is categorized as duplicate/replay and discarded without updating state or metrics table.
4. **Payload Size Guard:** Each envelope payload must be $\le 512\text{ KB}$.
5. **Atomic Sequence Advance:** The gateway's sequence cursor advances to the highest accepted sequence number within a single transaction.

- **Response (200 OK):**
```json
{
  "accepted_count": 25,
  "duplicate_count": 0,
  "error_count": 0,
  "last_sequence_number": 1069,
  "errors": []
}
```

---

## 5. LOCAL BUFFER & RECONNECTION PROTOCOL

When the WAN link between Customer Edge Gateway and Central NOC is interrupted, local telemetry continues without loss.

1. **Local Enqueue:** New telemetry points are committed to `edge_buffer.db` with an incremented sequence number.
2. **Capacity Cap:** Buffer enforces bounded capacity ($N = 5,000$ samples / $\approx 1.2\text{ MB}$).
3. **FIFO Drop on Overflow:** If queue depth reaches capacity, oldest un-transmitted samples are dropped, and `dropped_total` counter increments.
4. **Reconnection Drain:**
   - Once HTTPS connection to Central NOC succeeds, gateway fetches up to 100 samples via `peek_batch()`.
   - Gateway POSTs batch to `/api/v1/gateways/telemetry`.
   - Upon receiving `200 OK`, gateway invokes `acknowledge_batch(sample_ids)` which deletes the acknowledged samples from `edge_buffer.db`.
   - Process repeats until `queue_depth == 0`.
