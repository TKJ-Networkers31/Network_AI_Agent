# AIRA OS — Phase 7 Remaining Risks & Operational Boundaries

**Document:** `docs/AIRA_PHASE7_REMAINING_RISKS.md`  
**Workspace:** `D:\data\agent_ai`  
**Target Architecture:** ThinkPad X270 (Intel i7-7500U, 8 GB RAM, CPU-only)  
**Scope:** Keterbatasan Sistem, Risiko Operasional, dan Rekomendasi Production Staging  

---

## 1. Executive Summary

Phase 7 telah berhasil membuktikan keamanan non-mutasi, efisiensi resource CPU-only ThinkPad X270, serta ketepatan algoritma deterministik dalam menangani kegagalan bukti (`INSUFFICIENT_EVIDENCE`).

Namun, untuk memastikan ekspektasi teknis tetap realistis dan tidak terjadi overclaiming, dokumen ini merinci risiko tersisa, batasan model, serta prasyarat sebelum sistem dipromosikan ke tahap staging atau produksi.

---

## 2. Matriks Risiko Tersisa (Remaining Risks Matrix)

| No | Risiko Teknis | Dampak | Probabilitas | Mitigasi yang Tersedia | Status Risiko |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Integrasi Live Hardware Belum Tersambung** | Validasi live terhenti di level transport karena tidak ada router live di lab lokal saat ini. | Tinggi | Engine preflight mendeteksi `UNREACHABLE` dan menghentikan investigasi secara aman. | **TERKELOLA** (Status: `BLOCKED`) |
| **2** | **Bypass FastTrack & HW Offload pada Data-Plane** | Simulator statis tidak memodelkan ASIC hardware offload atau bypass paket FastTrack. | Sedang | Pengungkapan wajib (*mandatory limitations disclosure*) disertakan di setiap laporan investigasi. | **TERDOKUMENTASI** |
| **3** | **Saturasi Conntrack Table pada Trafik Nyata** | Tabel conntrack router penuh (DoS) tidak terdeteksi hanya dari rule firewall filter count. | Rendah | Menggunakan rule check `connection-limit` dan pelaporan counter drop interface saat diperluas. | **MEMBUTUHKAN SENSOR TELEMETRI** |
| **4** | **Konvergensi Rute Dinamis (OSPF/BGP)** | Waktu konvergensi LSA/BGP update membutuhkan waktu beberapa detik setelah link pulih. | Sedang | Kebijakan `freshness` mengklasifikasikan bukti < 60s sebagai `FRESH`, mewajibkan refresh sebelum penutupan insiden. | **TERKELOLA** |
| **5** | **Man-in-the-Middle (MitM) jika Host Key Belum Didaftarkan** | Potensi spoofing router jika parameter `AIRA_KNOWN_HOSTS_FILE` kosong di jaringan publik. | Rendah | Standard Operating Procedure (SOP) mewajibkan pendaftaran host key resmi sebelum aktivasi di jaringan ISP. | **MEMBUTUHKAN KONFIGURASI OPERATOR** |
| **6** | **Batasan Multi-Vendor** | Normalizer saat ini dioptimalkan khusus untuk MikroTik RouterOS v6 dan v7 (belum mendukung Cisco IOS/Juniper JunOS). | Rendah | Registry canonical menandai perangkat non-RouterOS sebagai tidak didukung untuk playbook MikroTik. | **DISCLOSED SCOPE BOUNDARY** |

---

## 3. Batasan Pemodelan Forwarding Data-Plane

Enam (6) batasan pemodelan yang secara transparan diungkapkan oleh simulator dan investigator:
1. **ASIC Hardware Offload:** Forwarding pada switch chip (CRS/CCR series) melewati CPU RouterOS.
2. **Conntrack Translation Timing:** Timeout tabel translasi NAT tidak dapat dimodelkan secara statis tanpa trafik nyata.
3. **FastTrack Packet Bypass:** Paket yang ter-FastTrack mem-bypass firewall filter chain mangle dan forward.
4. **Dynamic Route Reconvergence:** Dampak transisi flap rute dinamis (BGP hold timer, OSPF dead timer).
5. **ECMP Hash Polarization:** Distribusi beban hashing paket multi-gateway per-koneksi.
6. **IPsec/Tunnel Overhead:** Fragmentasi MTU paket terenkapsulasi (EoIP, GRE, WireGuard, IPsec) yang melampaui MTU 1500.

---

## 4. Rekomendasi Sebelum Peluncuran Produksi (Pre-Production Checklist)

1. **Aktivasi Lab Staging Terisolasi:**  
   Jalankan satu instance MikroTik CHR v7 pada VirtualBox / VMware Workstation / GNS3. Hubungkan interface management ke subnet host-only (`192.168.111.x` atau `192.168.172.x`).
2. **Provisioning Akun Audit Terpisah:**  
   Buat akun `/user add name=aira-audit group=read` secara manual di RouterOS. Jangan pernah menggunakan akun `admin` bawaan.
3. **Audit Token API Terpusat:**  
   Pastikan variabel `AIRA_ADMIN_TOKEN` dan `AIRA_TOPOLOGY_ADMIN_TOKEN` di file `.env` diisi dengan token rahasia yang kuat.
4. **Pertahankan Kebijakan Read-Only:**  
   Tetap pertahankan larangan auto-remediation otonom. Setiap rencana perubahan konfigurasi wajib melalui review manusia (*human approval gate*).
