# Networking VI: Network Intelligence Core — API Reference

## Document Information
- **Document Version:** 1.0.0
- **Status:** APPROVED & IMPLEMENTED
- **Module:** `AIRA_ECOSYSTEM/api/routers/network_intelligence.py`
- **Base Route Prefix:** `/api/intelligence`
- **Security Boundary:** 100% Read-Only; no state-modifying or mutating CLI commands are ever executed.

---

## 1. Overview
The Network Intelligence Core REST API provides comprehensive endpoints for natural-language investigations, 8-dimensional health evaluations, anomaly detection, hop-by-hop path tracing, cross-device correlation, 14-step root-cause analysis (RCA), change impact analysis, non-destructive failure simulation, knowledge graph exploration, and canonical evidence retrieval.

---

## 2. Authentication & Authorization
- **Read-Only Endpoints** (`GET /overview`, `GET /graph`, `GET /paths`, `GET /correlations`, `GET /rca`, `GET /anomalies`, `GET /health`, `GET /history`, `GET /evidence/{id}`, `GET /investigations`):
  Available to standard authenticated operators.
- **Diagnostic & Simulation Execution Endpoints** (`POST /investigate`, `POST /investigations/{id}/cancel`, `POST /impact`, `POST /simulations`):
  Protected by `require_topology_admin` dependency.

---

## 3. Endpoints Specification

### 3.1 Network Intelligence Overview
- **Method & Path:** `GET /api/intelligence/overview`
- **Summary:** Retrieve high-level network intelligence summary including health status, dimension scores, active incidents, recent changes, anomalies, and evidence freshness.
- **Query Parameters:** None.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "overview": {
    "network_condition": "HEALTHY",
    "health_score": 96.5,
    "dimension_scores": {
      "CONNECTIVITY": 100.0,
      "REACHABILITY": 100.0,
      "INTERFACE_HEALTH": 95.0,
      "BANDWIDTH_LOAD": 92.0,
      "DEVICE_RESOURCES": 98.0,
      "ROUTING_STABILITY": 100.0,
      "PROTOCOL_HEALTH": 95.0,
      "CONFIGURATION_CONSISTENCY": 92.0
    },
    "device_health": {
      "R1": {"score": 96.5, "status": "HEALTHY"}
    },
    "active_incidents_count": 0,
    "recent_incidents": [],
    "major_anomalies": [],
    "recurring_incidents": [],
    "evidence_freshness": {
      "FRESH": 18,
      "AGING": 2,
      "STALE": 0,
      "EXPIRED": 0
    },
    "total_evidence_records": 20,
    "observed_devices": ["R1", "R2"]
  }
}
```

---

### 3.2 Natural-Language Investigation
- **Method & Path:** `POST /api/intelligence/investigate`
- **Summary:** Submit a natural-language query to the 12-step Network Investigator.
- **Request Body (`application/json`):**
```json
{
  "question": "Mengapa klien di VLAN 20 tidak bisa akses internet?",
  "session_id": "sess_f8a92b",
  "user_context": {
    "scoped_devices": ["R1"],
    "target_ip": "192.168.20.50"
  },
  "timeout_sec": 30.0
}
```
- **Success Response (200 OK):**
```json
{
  "success": true,
  "investigation": {
    "investigation_id": "inv_a8b9c0d1e2",
    "session_id": "sess_f8a92b",
    "question": "Mengapa klien di VLAN 20 tidak bisa akses internet?",
    "intent": "LAN_INTERNET_REACHABILITY",
    "status": "COMPLETED",
    "plan": {
      "plan_id": "plan_12345",
      "intent": "LAN_INTERNET_REACHABILITY",
      "scope_devices": ["R1"],
      "required_evidence": ["ip_addresses", "routes", "nat_rules", "firewall_filter", "interfaces"]
    },
    "rca": {
      "report_id": "rca_7890",
      "leading_hypothesis": {
        "hypothesis_id": "hyp_1",
        "title": "NAT Masquerade Mismatch",
        "confidence": "HIGH"
      }
    },
    "path": null,
    "health": {...},
    "anomalies": [],
    "correlations": [],
    "explanation": {
      "summary": "Berdasarkan bukti observasi, rule NAT masquerade tidak mencakup subnet 192.168.20.0/24.",
      "confidence_assessment": "HIGH",
      "recommended_actions": ["Tambahkan rule NAT masquerade untuk out-interface WAN."]
    },
    "evidence_items": [
      {
        "evidence_id": "cli:R1:nat_rules:123",
        "device_id": "R1",
        "observation_type": "nat_rules",
        "freshness": "FRESH",
        "confidence": "HIGH",
        "limitations": ["Static CLI snapshot"]
      }
    ],
    "missing_evidence": [],
    "duration_sec": 1.24,
    "created_at": 1730700000.0
  }
}
```

---

### 3.3 List Investigations
- **Method & Path:** `GET /api/intelligence/investigations`
- **Summary:** Retrieve paginated historical natural language investigations.
- **Query Parameters:**
  - `session_id` (optional string): Filter by conversational session ID.
  - `limit` (optional integer, default 50, range 1..200).
- **Success Response (200 OK):**
```json
{
  "success": true,
  "investigations": [
    {
      "investigation_id": "inv_a8b9c0d1e2",
      "session_id": "sess_f8a92b",
      "question": "Mengapa klien di VLAN 20 tidak bisa akses internet?",
      "intent": "LAN_INTERNET_REACHABILITY",
      "status": "COMPLETED",
      "duration_sec": 1.24,
      "created_at": 1730700000.0
    }
  ]
}
```

---

### 3.4 Retrieve Investigation by ID
- **Method & Path:** `GET /api/intelligence/investigations/{investigation_id}`
- **Summary:** Retrieve complete investigation result record.
- **Error Response (404 Not Found):** If ID does not exist.

---

### 3.5 Cancel Investigation
- **Method & Path:** `POST /api/intelligence/investigations/{investigation_id}/cancel`
- **Summary:** Signals an active investigation to abort cleanly without corrupting state.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "message": "Penyelidikan 'inv_a8b9c0d1e2' berhasil dibatalkan."
}
```

---

### 3.6 Knowledge Graph Query
- **Method & Path:** `GET /api/intelligence/graph`
- **Summary:** Query Network Knowledge Graph nodes and edges across 5 layers.
- **Query Parameters:**
  - `layer` (optional string): `PHYSICAL`, `L2`, `L3`, `PROTOCOL`, `DEPENDENCY`.
  - `entity_type` (optional string): e.g. `DEVICE`, `INTERFACE`, `VLAN`, `ROUTE`, `PEER`.
  - `device_id` (optional string): Filter subgraph around a specific device.
  - `limit` (optional int, default 200, range 1..1000).
  - `offset` (optional int, default 0).
- **Success Response (200 OK):**
```json
{
  "success": true,
  "graph": {
    "total_nodes": 45,
    "total_edges": 62,
    "nodes": [...],
    "edges": [...],
    "layers_available": ["PHYSICAL", "L2", "L3", "PROTOCOL", "DEPENDENCY"]
  }
}
```

---

### 3.7 Path Analysis
- **Method & Path:** `GET /api/intelligence/paths`
- **Summary:** Perform hop-by-hop path tracing, longest-prefix match, recursive next-hop resolution, ECMP, and loop detection.
- **Query Parameters:**
  - `destination_ip` (required string): Destination IPv4 address or CIDR.
  - `source_device_id` (optional string): Starting device.
  - `source_ip` (optional string): Starting source IP.
  - `routing_table` (optional string, default `"main"`).
- **Success Response (200 OK):**
```json
{
  "success": true,
  "path_analysis": {
    "classification": "RIB_INFERRED",
    "hops": [...],
    "has_loop": false,
    "is_ecmp": false,
    "confidence": "HIGH"
  }
}
```

---

### 3.8 Cross-Device Correlations
- **Method & Path:** `GET /api/intelligence/correlations`
- **Summary:** Discover multi-device correlated event clusters within an observation window.
- **Query Parameters:**
  - `window_sec` (optional float, default 300.0, range 10.0..3600.0).

---

### 3.9 Root Cause Analysis (RCA)
- **Method & Path:** `GET /api/intelligence/rca`
- **Summary:** Execute the 14-step deterministic RCA engine over current evidence.
- **Query Parameters:**
  - `scope` (optional string, default `"network"`).

---

### 3.10 Anomaly Detection
- **Method & Path:** `GET /api/intelligence/anomalies`
- **Summary:** Retrieve detected anomalies across bandwidth rates, error counters, interface flaps, and CPU/memory.
- **Query Parameters:**
  - `severity` (optional string): `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
  - `device_id` (optional string): Scope to device.

---

### 3.11 Multi-Dimensional Health
- **Method & Path:** `GET /api/intelligence/health`
- **Summary:** Evaluates 8 transparent network and device health dimensions.

---

### 3.12 Change Impact Analysis
- **Method & Path:** `POST /api/intelligence/impact`
- **Summary:** Evaluates blast radius, affected downstream devices, and alternate path redundancy.
- **Request Body:**
```json
{
  "target_entity_id": "R1:ether1",
  "target_entity_type": "INTERFACE",
  "scope": "POTENTIAL_IMPACT"
}
```

---

### 3.13 Failure Simulation
- **Method & Path:** `POST /api/intelligence/simulations`
- **Summary:** Performs in-memory non-destructive failure simulation (`is_simulation=true`).
- **Request Body:**
```json
{
  "failure_type": "DEVICE_DOWN",
  "entity_id": "R1"
}
```

---

### 3.14 Historical Intelligence
- **Method & Path:** `GET /api/intelligence/history`
- **Summary:** Queries historical snapshot differences, metric acceleration trends, and recurring incidents.
- **Query Parameters:**
  - `older_snapshot_id` (optional string).
  - `newer_snapshot_id` (optional string).

---

### 3.15 Canonical Evidence Inspector
- **Method & Path:** `GET /api/intelligence/evidence/{evidence_id}`
- **Summary:** Retrieves full details of a specific canonical evidence artifact.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "evidence": {
    "evidence_id": "cli:R1:routes:a8c1",
    "device_id": "R1",
    "observation_type": "routes",
    "source_command": "/ip/route/print",
    "timestamp": 1730700000.0,
    "freshness": "FRESH",
    "confidence": "HIGH",
    "limitations": ["Static CLI snapshot"],
    "normalized_payload": {...}
  }
}
```
