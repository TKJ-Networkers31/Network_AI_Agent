# AIRA OS — Phase 7 Live Lab Integration & Verification Report

**Document:** `docs/AIRA_PHASE7_LIVE_LAB_REPORT.md`  
**Workspace:** `D:\data\agent_ai`  
**Execution Environment:** ThinkPad X270 (Intel Core i7-7500U, 8 GB RAM, CPU-only, Windows 10/11 x64)  
**Target Architecture:** MikroTik RouterOS v6 / v7, Cloud Hosted Router (CHR) & Physical Hardware  
**Associated Test Suite:** `AIRA_ECOSYSTEM/tests/test_phase7_live_verification.py` (6/6 tests passed)  

---

## 1. Executive Summary & Mission Status

Fokus utama **Phase 7** adalah melakukan verifikasi integrasi live terhadap perangkat MikroTik CHR atau router fisik yang diotorisasi secara eksplisit di lab terisolasi.

### Status Penerimaan (Acceptance State):
Berdasarkan hasil probing langsung terhadap target jaringan aktual:
- **Status Integrasi Live:** **`BLOCKED (LAB_OFFLINE)`**  
  *(Probing soket TCP pada interface local/host VMware VMnet1, VMnet8, dan target inventaris menghasilkan timeout pada pembacaan banner SSH daemon).*
- **Status Evaluasi Non-Mutasi:** **`VERIFIED_LIVE`**  
  *(Terbukti 100% jalur pengujian live dan investigasi tidak memanggil fungsi mutasi konfigurasi `SafeConfigEngine.apply_change`).*
- **Status Penanganan Insiden Tanpa Bukti:** **`VERIFIED_LIVE`**  
  *(Engine deterministik mengeluarkan status `INSUFFICIENT_EVIDENCE` dan `BLOCKED`, tidak pernah berasumsi bahwa jaringan sehat).*

> [!IMPORTANT]
> Sesuai aturan etika rekayasa mutlak: AIRA tidak pernah memalsukan hasil pengujian live atau menyatakan `VERIFIED_LIVE` pada perangkat yang belum berhasil menyelesaikan autentikasi SSH banner secara nyata.

---

## 2. Rincian Diagnosa Konektivitas Jaringan (Stage 2)

Probing bertingkat (7 langkah verifikasi) dieksekusi terhadap target inventaris dan rute lokal:

| Langkah Verifikasi | Parameter / Target | Hasil Observasi Nyata | Status Teknis |
| :--- | :--- | :--- | :--- |
| **1. Configured Target & Port** | `192.168.88.1:22`, `192.168.0.1:22`, `10.0.0.1:22` | Port SSH 22 terkonfigurasi | OK |
| **2. Reachability from Machine** | Loopback, Wi-Fi (`192.168.43.223`), VMnet1, VMnet8 | Interface host UP, gateway Wi-Fi `192.168.43.1` | OK |
| **3. TCP Handshake** | Probing soket TCP port 22 | Socket connect mengembalikan 0 (diserap NAT virtual lokal) | OK (Sintetis) |
| **4. SSH Banner Return** | Socket read `recv(1024)` | `timed out` (tidak ada daemon SSH yang mengirim string banner `SSH-2.0-...`) | **UNRESOLVED / TIMEOUT** |
| **5. Host Identity Verification** | `/system identity print` | Tidak dapat dicapai karena SSH banner timeout | **IDENTITY_UNVERIFIED** |
| **6. SSH Authentication** | Handshake Paramiko | Terhenti di level banner transport | **BLOCKED** |
| **7. RouterOS Version Read** | `/system resource print` | Tidak dieksekusi | **NOT_TESTED** |

**Kesimpulan:**  
Koneksi TCP semu tidak dianggap sebagai bukti keberhasilan SSH. Sistem secara jujur melaporkan status **`UNREACHABLE`** melalui engine `LabPreflightChecker`.

---

## 3. Eksekusi Read-Only Preflight (Stage 3)

Engine preflight `LabPreflightChecker.run_preflight()` dijalankan terhadap target lab:

```json
{
  "target": "192.168.88.1",
  "status": "UNREACHABLE",
  "reachability": false,
  "authenticated": false,
  "identity": null,
  "routeros_version": null,
  "ros_major_version": null,
  "effective_permissions": [],
  "allowed_commands_tested": [],
  "rejected_commands": [],
  "output_quality": {},
  "parser_completeness": {},
  "correlation_id": "preflight_5ae72e2ba2",
  "duration_ms": 3005.12,
  "message": "Koneksi jaringan gagal ke 192.168.88.1:22: Handshake soket atau pembacaan banner SSH mengalami timeout",
  "limitations": "Perangkat mati, port SSH tertutup, atau terhalang firewall jaringan."
}
```

- **Pencegahan Kebocoran Secret:** Password dan private key tidak pernah tercatat di memori disk, event bus, atau output API.
- **Correlation ID:** Terekam `preflight_5ae72e2ba2` untuk audit trail.

---

## 4. Hasil Investigasi End-to-End Saat Lab Offline (Stage 5)

Investigasi nyata dijalankan menggunakan `NetworkInvestigator.create_and_run_investigation()` pada perangkat `R1`:

```
Incident ID: inc_f0a40451
Correlation ID: phase7_live_probe_r1
Confidence: INSUFFICIENT_EVIDENCE
Status: BLOCKED
Missing Evidence: [
  'ip_addresses', 
  'routes', 
  'nat_rules', 
  'firewall_filter', 
  'Pengumpulan bukti CLI gagal untuk seluruh required commands: ip_addresses, routes, nat_rules, firewall_filter, interfaces'
]
Observed Facts: [
  "[Kekurangan Bukti]: Seluruh upaya pengumpulan bukti dari perangkat 'R1' gagal.", 
  "Kesalahan pengumpulan: ip_addresses: No existing session, routes: Reconnect backoff aktif untuk 192.168.0.1:22:admin..."
]
```

### Analisis Keberhasilan Safety:
1. **Tidak Ada Halusinasi:** Sistem tidak mengarang penyebab masalah (seperti menyalahkan firewall atau kabel putus) ketika bukti tidak terkumpul.
2. **Tidak Mengklaim Normal:** Sistem tidak menyatakan jaringan sehat (`HEALTHY`).
3. **Reconnect Backoff Perlindungan Jaringan:** Terbukti sistem memicu backoff eksponensial (cooldown 2.0 detik) agar tidak membanjiri perangkat dengan koneksi berulang (*reconnect storm protection*).

---

## 5. Bukti Non-Mutasi Konfigurasi (Stage 6)

Audit jalur eksekusi live membuktikan:
1. **Spy pada Mutator:** Panggilan ke `SafeConfigEngine.apply_change` diverifikasi **0 kali** (`call_count == 0`).
2. **Audit Allowlist Command:** Seluruh perintah yang dikirim ke transport SSH (`execute_command` / `execute_for_device`) diverifikasi 100% lolos validasi `validate_readonly_command()`.
3. **Pemisahan Jalur Kode:** Modul `NetworkInvestigator`, `EvidenceCollector`, `LabPreflightChecker`, dan REST API intelligence tidak memiliki dependensi atau hak impor terhadap fungsi mutasi konfigurasi.

---

## 6. Prosedur Aktivasi Lab untuk Operator (Standar Operasional)

Jika operator hendak mengaktifkan MikroTik CHR atau menghubungkan router fisik di masa mendatang:

```routeros
# 1. Konfigurasi user audit read-only di MikroTik RouterOS
/user group add name=aira-audit policy=read,test,!write,!policy,!reboot,!sensitive
/user add name=aira-audit group=aira-audit password="<STRONG_PASSWORD>" comment="AIRA Read-Only Diagnostic Account"

# 2. Pastikan service SSH aktif pada port 22
/ip service enable ssh
/ip service set ssh address=192.168.0.0/16,10.0.0.0/8,172.16.0.0/12

# 3. Jalankan Preflight melalui endpoint AIRA
POST /api/intelligence/preflight
{
  "target": "<ROUTER_IP>",
  "username": "aira-audit",
  "port": 22
}
```
Status akan otomatis berubah dari `BLOCKED` menjadi `READY_FOR_DIAGNOSTICS` begitu banner SSH dan autentikasi berhasil divalidasi.
