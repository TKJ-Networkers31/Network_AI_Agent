# AIRA OS — Automatic Orchestration Architecture Specification

**Dokumen:** `docs/STABILIZATION/AUTOMATIC_ORCHESTRATION_ARCHITECTURE.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:**  
- `AIRA_ECOSYSTEM/core/network_intelligence/auto_orchestrator.py`  
- `AIRA_ECOSYSTEM/api/routers/network_intelligence.py`  
- `AIRA_ECOSYSTEM/agents/akane/network_tools.py`  
- `AIRA_ECOSYSTEM/app/frontend/src/pages/NetworkIntelligencePage.jsx`

---

## 1. Arsitektur Pipeline Otonom

```
                     [ Operator Prompt / Web UI Trigger ]
                                     │
                                     ▼
                     [ AutomaticNetworkOrchestrator ]
                                     │
       ┌─────────────────────────────┴─────────────────────────────┐
       ▼                                                           ▼
[ 1. Target Resolution ]                                [ 2. Evidence Collection ]
• Query inventory & canonical                           • Concurrently collect CLI
• Single-device auto-pick                               • Identity, Resource, Ifaces,
• Multi-device resolution                                 IP, Route, ARP, Firewall
       │                                                           │
       └─────────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
                       [ 3. Cross-Device Correlation ]
                       • Match shared subnets & links
                       • Trace routing next-hops
                       • Build topology relationships
                                     │
                                     ▼
                   [ 4. Autonomous Hypothesis Ranking ]
                   • Evaluate observed facts deterministically
                   • Disclose confidence & explicit uncertainty
                   • Separate proven facts from inferences
                                     │
                                     ▼
                   [ 5. Safe Configuration Planning ]
                   • 100% Read-Only / Non-mutating
                   • Generate desired state remediation
                   • Compute CLI diff & rollback script
                                     │
                                     ▼
                   [ 6. Consolidated Unified Output ]
                   • Executive summary in chat & dashboard
                   • Direct link to review plan in Planner
```

---

## 2. Kontrak Data API (`POST /api/intelligence/auto-diagnose`)

### Input Payload (`AutoDiagnoseIn`):
```json
{
  "target_devices": ["CHR"],
  "symptom": "Koneksi gateway terputus atau paket hilang",
  "target_ip": "192.168.43.1",
  "auto_plan": true
}
```

### Output Response:
```json
{
  "success": true,
  "pipeline_id": "auto_f3b890a12e",
  "status": "completed",
  "timestamp": 1793368200.0,
  "duration_ms": 3120,
  "primary_device": "CHR",
  "target_devices": ["CHR"],
  "symptom": "Koneksi gateway terputus atau paket hilang",
  "incident": { "incident_id": "inc_901a", "confidence": "HIGH", "..." : "..." },
  "evidence_count": 8,
  "observed_facts": [
    "Perangkat CHR online dengan IP 192.168.43.30.",
    "Default route 0.0.0.0/0 mengarah ke gateway 192.168.43.1."
  ],
  "top_hypothesis": {
    "hypothesis_id": "hyp_01",
    "title": "Default Route Reachable via ether1",
    "confidence": "HIGH"
  },
  "ranked_hypotheses": [ ... ],
  "correlation_relationships": [ ... ],
  "recommended_plan": null,
  "summary": "Diagnostik otomatis selesai untuk 1 perangkat: CHR.\nFakta observasi terkumpul: 8 item bukti.\nKesimpulan utama: Normal Health (Keyakinan: HIGH).",
  "read_only": true,
  "safety_disclosure": "Pemeriksaan dan simulasi bersifat 100% Read-Only. Tidak ada perintah mutasi yang dijalankan ke perangkat jaringan."
}
```

---

## 3. Integrasi Agen AKANE & REI

Tool baru `auto_diagnose_network` didaftarkan pada:
- `agents/akane/network_tools.py::auto_diagnose_network`
- `agents/akane/registry.py::AKANE_TOOLS["auto_diagnose_network"]`
- Kategori: `"network"`
- Skema fungsi OpenAI-compatible di `AKANE_TOOL_SCHEMAS`.

Dengan integrasi ini, saat pengguna mengirim prompt chat seperti:
> *"Tolong diagnosa router CHR sekarang"*

Agen REI langsung memanggil `auto_diagnose_network(device_name="CHR")` dan membalas dengan ringkasan diagnosis lengkap tanpa meminta operator membuka tab lain.
