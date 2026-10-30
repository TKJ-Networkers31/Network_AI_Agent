# AIRA OS — Phase 5 Static Simulator & Validator Limitations

**Tanggal Audit:** 2026-10-29  
**Domain:** Network Engineering, Forwarding Simulation, Dataplane Boundary Analysis  
**Auditor:** Antigravity AI Engineering Assistant  
**Workspace:** `D:\data\agent_ai`

---

## 1. Ringkasan Eksekutif

Static Forwarding Simulator pada AIRA OS berfungsi mengevaluasi dampak rute dan konfigurasi yang diusulkan secara *control plane* menggunakan algoritma Longest Prefix Match (LPM) deterministik. 

Sebagai prinsip rekayasa yang jujur (*evidence-authoritative*), AIRA secara eksplisit mengungkapkan bahwa **simulasi statis bukanlah emulasi full data-plane hardware**. Simulator tidak boleh mengklaim dapat memprediksi perilaku paket secara 100% tanpa pengujian trafik end-to-end langsung pada router nyata.

---

## 2. Status Keputusan Deterministik: PASS, FAIL, UNKNOWN

Untuk mencegah false confidence (rasa aman semu), validator dan simulator AIRA membedakan tiga status hasil evaluasi:

| Status Evaluasi | Arti Semantik | Kondisi Pemicu |
| :--- | :--- | :--- |
| **`PASS`** | Terverifikasi Aman | Seluruh aturan, subnet non-overlap, interface terkonfirmasi, dan next-hop terbukti reachable di baseline data. |
| **`FAIL`** | Terbukti Melanggar Aturan | Terdeteksi tabrakan subnet (*subnet overlap*), interface tidak ditemukan, VLAN ID di luar batas, atau paket rute mengalami blackholing. |
| **`UNKNOWN`** | Bukti Tidak Lengkap / Asumsi Tak Terbukti | Bukti baseline tidak dapat diambil (SSH disconnect, timeout), topologi upstream tidak diketahui, atau gateway belum terkonfirmasi aktif. **Dilarang keras mengubah status ini menjadi `PASS`**. |

---

## 3. Enam Keterbatasan Pemodelan Forwarding Data-Plane

Simulator statis AIRA secara transparan mendokumentasikan 6 keterbatasan yang tidak dimodelkan (*unmodeled behaviors*):

### 3.1 FastTrack Connection Offload (Kernel Linux / RouterOS)
- **Keterbatasan:** Paket dari koneksi yang telah berstatus `established` atau `related` diproses langsung melalui FastTrack bypass di driver network, melewati inspeksi tabel routing standar dan firewall filter.
- **Dampak Lapangan:** Jika rule FastTrack aktif (`action=fasttrack-connection`), perubahan routing atau firewall baru mungkin tidak langsung berpengaruh pada koneksi TCP yang sedang aktif berjalan sampai koneksi tersebut ditutup/dibuat ulang.

### 3.2 Hardware Offload (Switch Chip / ASIC L2/L3)
- **Keterbatasan:** Pada perangkat MikroTik Cloud Router Switch (CRS3xx series) atau RouterBOARD dengan chip switch berkemampuan L3HW, frame Layer 2 (VLAN) dan routing Layer 3 di-offload langsung ke tabel ASIC switch chip.
- **Dampak Lapangan:** Forwarding L2/L3 dilakukan oleh ASIC dengan batas ukuran memori hardware (TCAM). Simulator statis AIRA mengevaluasi aturan di CPU host, bukan keterbatasan kapasitas TCAM switch chip.

### 3.3 Connection Tracking (Conntrack) Table State & Timeouts
- **Keterbatasan:** Tabel `ip_conntrack` memiliki siklus hidup dinamis (misal: TCP timeout 1 hari, UDP timeout 30-180 detik, status SYN_SENT vs ESTABLISHED).
- **Dampak Lapangan:** Simulator tidak memprediksi apakah *state table* penuh (*table exhaustion*) atau apakah trafik asimetris (kembali via interface berbeda) akan di-drop oleh conntrack.

### 3.4 Multi-Gateway ECMP Hashing Non-Deterministik
- **Keterbatasan:** Ketika terdapat beberapa default gateway dengan cost/distance sama (Equal-Cost Multi-Path), MikroTik mendistribusikan aliran paket menggunakan algoritma hash 5-tuple (`src-ip, dst-ip, src-port, dst-port, protocol`).
- **Dampak Lapangan:** Simulator statis memvalidasi keberadaan jalur multi-hop, namun tidak dapat memprediksi gateway spesifik mana yang akan dilewati oleh paket individual tertentu pada waktu berjalan.

### 3.5 Overhead Enkapsulasi Tunnel & Penurunan MTU (IPsec/GRE/WireGuard)
- **Keterbatasan:** Terowongan VPN menambahkan header tambahan (misal: IPsec ESP 50–70 byte, GRE 24 byte, WireGuard 32 byte), menurunkan effective path MTU dari 1500 menjadi 1420–1450.
- **Dampak Lapangan:** Simulator statis mengevaluasi rute prefix, namun tidak mengukur degradasi fragmentasi paket atau kegagalan TCP handshake akibat ketiadaan rule `change-mss` pada paket SYN dengan flag DF (*Don't Fragment*).

### 3.6 Konvergensi Dynamic Routing (OSPF / BGP Latency)
- **Keterbatasan:** Protokol routing dinamis memerlukan pertukaran paket kontrol (Hello, LSA update, BGP Keepalive) dan waktu perhitungan Dijkstra SPF / BGP Best Path.
- **Dampak Lapangan:** Simulator memodelkan rute akhir yang diharapkan, tetapi tidak memodelkan jeda waktu konvergensi (*convergence flap/blackhole window*) yang terjadi selama beberapa detik setelah perubahan diterapkan.

---

## 4. Bukti Verifikasi Unit Test (test_phase5_simulator_correctness.py)

Kebenaran semantik dan pengungkapan keterbatasan diuji secara otomatis:
- `test_validator_emits_fail_on_blocking_error` -> **PASS (Status: FAIL)**
- `test_validator_emits_unknown_when_baseline_evidence_incomplete` -> **PASS (Status: UNKNOWN)**
- `test_validator_emits_pass_with_warnings_on_mgmt_risk` -> **PASS (Status: PASS_WITH_WARNINGS)**
- `test_simulator_emits_unknown_when_baseline_routes_missing` -> **PASS (Status: UNKNOWN)**
- `test_simulator_emits_pass_when_forwarding_modeled_successfully` -> **PASS (Status: PASS)**
- `test_simulator_discloses_all_six_unmodeled_behaviors` -> **PASS (6 Disclosures Terverifikasi)**
