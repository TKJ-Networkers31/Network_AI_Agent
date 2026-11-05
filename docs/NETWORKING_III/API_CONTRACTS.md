# AIRA OS — Phase Networking III
# Multi-Device REST API Contracts

## 1. Overview

This document specifies the REST API endpoints introduced in Phase Networking III under `AIRA_ECOSYSTEM/api/routers/network_intelligence.py`.

All endpoints require topology admin authentication (`X-Topology-Admin: true` or equivalent session cookie).

---

## 2. API Endpoints

### 2.1 Batch Evidence Collection

`POST /api/intelligence/devices/batch-collect`

**Request Body (`BatchCollectIn`):**
```json
{
  "targets": ["Router-1", "Router-2", "ISP-1"],
  "required_types": ["interfaces", "ip_addresses", "routes", "arp"]
}
```

**Response Body:**
```json
{
  "success": true,
  "bundle_id": "mbundle_a8f910cd",
  "summary": {
    "total_devices": 3,
    "successful_devices": 3,
    "partial_devices": 0,
    "failed_devices": 0,
    "total_commands": 12,
    "successful_commands": 12,
    "failed_commands": 0,
    "unsupported_commands": 0,
    "total_duration_ms": 340.5,
    "device_summaries": {
      "Router-1": {
        "device_id": "Router-1",
        "status": "SUCCESS",
        "total_commands": 4,
        "successful_commands": 4
      }
    }
  },
  "total_devices": 3,
  "cross_device_contradictions": []
}
```

---

### 2.2 Cross-Device Correlation

`POST /api/intelligence/correlation`

**Request Body (`CorrelationIn`):**
```json
{
  "targets": ["Router-1", "Router-2"]
}
```

**Response Body:**
```json
{
  "success": true,
  "count": 1,
  "relationships": [
    {
      "source_device_id": "Router-1",
      "target_device_id": "Router-2",
      "correlation_rule": "MUTUAL_ARP_AND_SUBNET_MATCH",
      "confidence": "HIGH",
      "confidence_score": 0.9,
      "link_type": "layer2_adjacency",
      "evidence_summary": "Mutual ARP match on subnet 192.168.1.0/24",
      "matching_ip": "192.168.1.2",
      "matching_mac": "08:00:27:01:02:03",
      "source_interface": "ether2",
      "target_interface": "ether1"
    }
  ],
  "cross_device_contradictions": []
}
```

---

### 2.3 Multi-Device Investigation

`POST /api/intelligence/multi-device-investigation`

**Request Body (`MultiDeviceInvestigationIn`):**
```json
{
  "primary_device": "Core-1",
  "related_devices": ["ISP-1"],
  "symptom_description": "Klien tidak dapat menjangkau internet melalui Core-1",
  "incident_type": "DEFAULT_ROUTE_FAILS",
  "severity": "HIGH",
  "target_ip": "8.8.8.8"
}
```

**Response Body:**
```json
{
  "success": true,
  "incident": {
    "incident_id": "inc_a1b2c3d4",
    "device_identity": "Core-1",
    "related_devices": ["ISP-1"],
    "incident_type": "DEFAULT_ROUTE_FAILS",
    "severity": "HIGH",
    "investigation_status": "DIAGNOSIS_READY",
    "observed_facts": [
      "Multi-device evidence collected across 2 devices: Core-1, ISP-1.",
      "Cross-device relationships identified: 1 link/routing correlations.",
      "Primary device Core-1 default gateway: 10.0.0.1.",
      "Perangkat upstream ISP-1 TIDAK memiliki rute default aktif ke internet."
    ],
    "inferred_hypotheses": [
      {
        "hypothesis_id": "hyp_up_1",
        "title": "Kegagalan Dependensi Upstream: Router transit ISP-1 kehilangan rute default",
        "confidence": "HIGH",
        "confidence_explanation": "Diverifikasi langsung melalui telemetri routing multi-perangkat."
      }
    ],
    "limitations_disclosure": "Analisis multi-perangkat ini berbasis korelasi snapshot observasi terbaca. Perilaku dinamik multi-hop memerlukan pengujian end-to-end langsung."
  }
}
```

---

### 2.4 Historical Metrics Query

`GET /api/intelligence/metrics/history?device_id=Core-1&limit=100&downsample_points=50`

**Response Body:**
```json
{
  "success": true,
  "device_id": "Core-1",
  "interface_name": null,
  "count": 50,
  "metrics": [
    {
      "id": 1,
      "device_id": "Core-1",
      "timestamp": 1730300000.0,
      "cpu_load_percent": 15.0,
      "memory_used_percent": 42.1,
      "latency_ms": 2.1
    }
  ]
}
```

---

## 3. Verification Evidence

- Implemented in: `AIRA_ECOSYSTEM/api/routers/network_intelligence.py`.
- Automated Integration Tests: `AIRA_ECOSYSTEM/tests/test_networking_iii_api.py` (4 tests passed).
- Frontend Client: `AIRA_ECOSYSTEM/app/frontend/src/api.js` methods (`batchCollect`, `correlateDevices`, `createMultiDeviceInvestigation`, `getMetricsHistory`).
