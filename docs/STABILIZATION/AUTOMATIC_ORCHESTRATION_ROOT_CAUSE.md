# AIRA OS — Automatic Orchestration Root Cause Analysis

**Dokumen:** `docs/STABILIZATION/AUTOMATIC_ORCHESTRATION_ROOT_CAUSE.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:** `core/network_intelligence/`, `core/orchestrator.py`, `app/frontend/src/pages/NetworkIntelligencePage.jsx`

---

## 1. Pernyataan Masalah

Sebelum implementasi ini, alur kerja diagnostik jaringan tingkat lanjut di AIRA OS terpecah ke dalam beberapa tab manual independen:
1. Pengguna harus membuka tab **Overview**, menekan tombol "Investigasi Baru", mengisi form, dan menunggu insiden selesai.
2. Pengguna harus berpindah ke tab **Hypotheses** secara manual untuk melihat analisis akar masalah.
3. Pengguna harus berpindah ke tab **Configuration Planner** secara manual, mengisi formulir perubahan yang diinginkan (*desired state*), lalu meninjau simulasi diff.
4. Pada antarmuka percakapan (Chat Copilot), agen REI tidak memiliki satu tool terpadu untuk mengeksekusi pipeline investigasi end-to-end secara otonom.

Pemisahan ini membebani operator dan bertentangan dengan visi AIRA sebagai asisten otomatis cerdas (*Autonomous Network Intelligence Copilot*).

---

## 2. Analisis Kesenjangan Arsitektural (Gap Analysis)

1. **Komponen Backend Terisolasi:**
   `MultiDeviceEvidenceOrchestrator`, `CrossDeviceEvidenceCorrelator`, `NetworkInvestigator`, dan `ConfigurationPlanner` telah dibuat pada fase Networking III, namun masing-masing hanya beroperasi sebagai endpoint REST individual tanpa sebuah *master pipeline orchestrator*.
2. **Ketiadaan Tool Agent Terpadu:**
   Agen AKANE memiliki tool-tool granular seperti `ping`, `get_routes`, dan `audit_network_firewall`, tetapi tidak memiliki tool tingkat tinggi seperti `auto_diagnose_network` yang dapat merangkai investigasi, korelasi, perankingan hipotesis, dan rekomendasi konfigurasi dalam satu langkah.
3. **Ketiadaan Trigger Satu Klik pada Frontend:**
   Halaman `NetworkIntelligencePage.jsx` tidak memiliki aksi terpadu (*unified action trigger*) yang menjalankan investigasi dan langsung menampilkan seluruh temuan terpadu.

---

## 3. Desain Solusi Terpadu

Dibangun modul baru:
`core/network_intelligence/auto_orchestrator.py` yang menyediakan kelas `AutomaticNetworkOrchestrator`:
- **Langkah 1:** Resolusi target perangkat otomatis dari inventaris/topologi (auto-select jika hanya 1 router).
- **Langkah 2:** Pengumpulan bukti multi-perangkat read-only secara paralel.
- **Langkah 3:** Korelasi topologi dan dependensi upstream.
- **Langkah 4:** Evaluasi hipotesis deterministik dengan pengungkapan keyakinan & ketidakpastian.
- **Langkah 5:** Penyusunan rencana konfigurasi mitigasi aman (read-only diff & rollback script).
- **Langkah 6:** Ringkasan eksekutif dan integrasi ke Chat Agent serta Web Workspace.
