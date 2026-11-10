# VERA Model Classification Architecture & Category Taxonomy
**Classification:** System Architecture Specification  
**Date:** 2026-11-10  
**Target:** 28 Unified Task Categories & Multi-Layer Classification Pipeline  
**Module:** `VERA_ECOSYSTEM/core/task_classifier.py`  
**Data Contracts:** `VERA_ECOSYSTEM/core/model_types.py`

---

## 1. Classification Philosophy & Pipeline

VERA utilizes a two-tier, high-reliability classification engine:
1. **Tier 1 (Zero-Shot LLM Intent Classification):** Uses `VERA_CLASSIFIER_MODEL` (`nvidia/nemotron-3.5-bolt-e4b`) to extract intent, confidence, required tools, modality requirements, and map to one of 28 discrete categories in <800ms.
2. **Tier 2 (Deterministic Heuristic Fallback Engine):** When the LLM provider is offline, experiencing read timeouts, or during cold starts, the deterministic regex/keyword analyzer classifies input across all 28 categories with >=0.75 confidence.

---

## 2. The 28 Unified Task Categories & Routing Map

| # | Task Category Key | Category Description | Primary Routing Label | Required Tools | Required Modalities | Example Query / Trigger |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `subnetting` | IP subnetting, VLSM, CIDR | `networking` | Yes | `["text"]` | "Hitung subnet /28 untuk 192.168.10.0" |
| 2 | `routing_protocols` | BGP, OSPF, MPLS, VRRP | `networking` | Yes | `["text"]` | "Konfigurasi BGP peer dengan AS 65001" |
| 3 | `network_configuration` | RouterOS / MikroTik setup | `networking` | Yes | `["text"]` | "Buat bridge VLAN filtering di RouterOS" |
| 4 | `network_troubleshooting` | Ping, trace, packet loss, RCA | `networking` | Yes | `["text"]` | "Diagnosa latency tinggi ke gateway" |
| 5 | `network_topology` | Topology, LLDP, CDP, neighbors | `networking` | Yes | `["text"]` | "Tampilkan topologi jaringan core" |
| 6 | `terminal_operations` | Shell, SSH, Linux sysadmin | `coding` | Yes | `["text"]` | "Jalankan script bash untuk cek disk space" |
| 7 | `data_manipulation` | JSON, CSV, Regex, parse | `coding` | False | `["text"]` | "Ekstrak IP dari log firewall dengan regex" |
| 8 | `coding` | Python, JS, Go, refactor | `coding` | False | `["text"]` | "Tulis fungsi async fetch telemetry" |
| 9 | `vision_analysis` | Multimodal diagram, image, OCR | `vision` | False | `["text", "image"]` | "Analisis gambar diagram topologi ini" |
| 10 | `voice_generation` | TTS, STT, audio dialogue | `voice` | False | `["text", "audio"]` | "Ubah teks laporan insiden ke suara" |
| 11 | `automation` | Scheduled cron, automated tasks | `automation` | Yes | `["text"]` | "Jadwalkan backup router setiap minggu" |
| 12 | `mathematics` | Formula, calculus, algebra | `reasoning` | False | `["text"]` | "Hitung MTBF dan availability 99.999%" |
| 13 | `general_reasoning` | Multi-step logic, proof | `reasoning` | False | `["text"]` | "Analisis perbandingan routing distance" |
| 14 | `retrieval` | Information search, fact lookup | `retrieval` | Yes | `["text"]` | "Cari dokumentasi RFC 4271 BGP" |
| 15 | `general_chat` | Conversational dialogue, greeting | `general` | False | `["text"]` | "Halo VERA, apa yang bisa kamu bantu?" |
| 16 | `network_diagnostics` | In-depth hardware telemetry | `networking` | Yes | `["text"]` | "Cek CPU load dan memory usage Mikrotik" |
| 17 | `incident_rca` | Post-mortem root cause analysis | `reasoning` | True | `["text"]` | "Buat RCA dari insiden fiber cut tadi malam" |
| 18 | `policy_audit` | Security audit & compliance | `reasoning` | True | `["text"]` | "Audit rule firewall terhadap standar CIS" |
| 19 | `scripting_shell` | Shell/Bash network automation | `coding` | False | `["text"]` | "Buat script auto-failover link WAN" |
| 20 | `chart_understanding` | Graph & metrics interpretation | `vision` | False | `["text", "image"]` | "Interpretasikan grafik traffic MRTG ini" |
| 21 | `topology_rendering` | Visual diagram synthesis | `vision` | False | `["text", "image"]` | "Buat skematik visual dari koneksi edge" |
| 22 | `audio_processing` | Audio stream analysis | `voice` | False | `["text", "audio"]` | "Analisis rekaman suara panggilan support" |
| 23 | `document_qa` | Manuals, runbooks, documentation| `retrieval` | False | `["text"]` | "Jawab berdasarkan SOP penanganan link down"|
| 24 | `long_context_rag` | Deep vector search over 1M tokens| `retrieval` | False | `["text"]` | "Ringkas riwayat perubahan config 6 bulan"|
| 25 | `workflow_dag` | Multi-step orchestrated workflows| `automation` | Yes | `["text"]` | "Jalankan pipeline zero-touch provisioning"|
| 26 | `multi_step_planning`| Complex network migration plans| `networking` | True | `["text"]` | "Susun tahapan migrasi IPv4 ke IPv6" |
| 27 | `content_safety` | Threat mitigation, safe sandbox | `general` | False | `["text"]` | "Deteksi percobaan bypass privilege" |
| 28 | `configuration_synthesis`| Config template compilation | `networking` | True | `["text"]` | "Generate konfigurasi BGP full-mesh" |

---

## 3. Data Contracts & Serialization

Classification events are published across the VERA EventBus via `task.classified`:

```json
{
  "primary_label": "networking",
  "confidence": 0.89,
  "requires_tools": true,
  "requires_vision": false,
  "requires_voice": false,
  "task_category": "network_configuration",
  "required_capabilities": ["conversation", "network_engineering", "tool_calling"],
  "required_modalities": ["text"],
  "rationale": "Detected RouterOS VLAN configuration keywords"
}
```

The payload preserves exact backwards compatibility with legacy consumers expecting `{"label": ..., "confidence": ...}` while offering rich capability contracts for the Model Router.
