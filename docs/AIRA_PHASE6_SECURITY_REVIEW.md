# AIRA OS — Phase 6 Security & Data Handling Review

**Document:** `docs/AIRA_PHASE6_SECURITY_REVIEW.md`  
**Workspace:** `D:\data\agent_ai`  
**Target Hardware:** ThinkPad X270 (Intel i7-7500U, 8 GB RAM, CPU-only)  
**Security Policy Enforcement:** `AIRA_ECOSYSTEM/core/network_intelligence/security.py`  
**Associated Test Suite:** `AIRA_ECOSYSTEM/tests/test_phase6_observability_and_security.py`  

---

## 1. Executive Summary

AIRA dirancang untuk beroperasi di lingkungan jaringan ISP dan enterprise, di mana integritas konfigurasi perangkat dan kerahasiaan kredensial adalah persyaratan mutlak.

Review keamanan Phase 6 mengaudit delapan (8) lapisan kontrol keamanan:
1. **Zero-Mutation Enforcement:** Pembuktian backend bahwa command diagnostik tidak memodifikasi router.
2. **Command Allowlist & Injection Prevention:** Validasi regex ketat dan penolakan karakter injeksi shell (`\n`, `;`, `|`, `&`, `<`, `>`, `` ` ``, `$`).
3. **Secret Redaction & Output Sanitization:** Pembersihan password, passphrase, token, dan private key sebelum persistensi atau presentasi UI.
4. **Data Isolation:** Isolasi rekaman investigasi antar-perangkat target.
5. **Endpoint Authentication & Authorization:** Proteksi endpoint intelligence melalui dependensi `require_topology_admin`.
6. **Execution & Buffer Constraints:** Pembatasan ukuran request, panjang command, dan pemotongan buffer output.
7. **Database & Audit Protection:** WAL mode SQLite, parameterized SQL queries, dan integritas foreign keys.
8. **Threat Model Disclosure:** Transparansi terhadap ancaman yang diuji vs ancaman yang berada di luar cakupan pengujian unit.

---

## 2. Lapisan Kontrol Keamanan

### 2.1 Backend Read-Only Command Allowlist
Seluruh command yang dieksekusi melalui `EvidenceCollector` atau `LabPreflightChecker` wajib divalidasi oleh `validate_readonly_command()`.

```python
# Mutating verbs yang langsung diblokir di level parser token:
MUTATING_VERBS = {
    "add", "set", "remove", "enable", "disable", "reset", "reboot",
    "shutdown", "edit", "comment", "export", "import", "run",
    "delete", "install", "upgrade", "downgrade", "uninstall",
    "format", "flash", "restore"
}
```

- **Injection Prevention:** Karakter `;`, `&`, `|`, `\n`, `\r`, `` ` ``, `$`, `<`, `>` langsung ditolak sebelum command diproses ke regex allowlist.
- **Batas Panjang:** Maksimum `MAX_COMMAND_LENGTH = 512` karakter.

### 2.2 Sanitasi Output & Redaksi Rahasia
Fungsi `sanitize_raw_output()` dan `mask_sensitive_data()` membersihkan teks mentah:
- Menghapus string pola:
  - `password=...` / `passphrase=...`
  - `wpa-pre-shared-key=...` / `wpa2-pre-shared-key=...`
  - `token=...` / `Authorization: Bearer ...`
  - `private-key=...` / `secret=...`
  - `community=...` (SNMP)
- Membatasi panjang potongan mentah maksimum 1200–1500 karakter untuk mencegah memory exhaust atau crash rendering UI.

### 2.3 Penyimpanan Kredensial
- **Ephemeral Session Secrets:** Password untuk sesi manual atau ephemeral preflight disimpan hanya di RAM proses (`_manual_secrets`), tidak pernah ditulis ke SQLite, file log, atau Event Bus.
- **Inventory Secrets:** Kredensial inventaris router disimpan terenkripsi dengan kunci `.inventory.key`.
- **Preflight Result Safety:** Struktur data `PreflightResult` tidak memiliki field password dan seluruh representasi dictionary diverifikasi bebas secret.

### 2.4 Autentikasi & Otorisasi API
Endpoint Network Intelligence:
- `POST /api/intelligence/preflight`
- `POST /api/intelligence/incidents`
- `POST /api/intelligence/incidents/{id}/playbook/start`
- `POST /api/intelligence/playbooks/runs/{id}/advance`
- `POST /api/intelligence/plans`

Seluruh endpoint mutatif/operasional di atas dilindungi oleh FastAPI dependency:
```python
_auth = Depends(require_topology_admin)
```
- Jika environment variable `AIRA_TOPOLOGY_ADMIN_TOKEN` atau `AIRA_ADMIN_TOKEN` dikonfigurasi, request wajib menyertakan token yang cocok via header `Authorization: Bearer <token>` atau `X-AIRA-Admin-Token` (menggunakan perbandingan waktu-konstan `hmac.compare_digest`). Request tanpa token ditolak dengan HTTP 401/403.
- Pada local deployment tanpa konfigurasi token, endpoint dibatasi hanya untuk pemanggil loopback.

### 2.5 Isolasi Data Investigasi
- Setiap target perangkat memiliki namespace record tersendiri di SQLite (`idx_incidents_device`).
- Endpoint `GET /api/intelligence/incidents?device_identity=<target>` hanya mengembalikan rekaman milik perangkat tersebut.
- Uji adversarial pada `test_target_investigation_isolation` membuktikan insiden target `R1` tidak pernah bocor ke query target `R2`.

---

## 3. Matriks Pengujian Ancaman Keamanan (Threat Matrix)

| Kategori Ancaman | Status Pengujian | Mekanisme Pertahanan | Catatan / Batasan |
| :--- | :--- | :--- | :--- |
| **Command Injection (Shell chaining `;`, `&`, `|`)** | **VERIFIED** | Ditolak oleh `validate_readonly_command()` pada pre-parser. | Diuji pada `test_phase6_observability_and_security.py`. |
| **Konfigurasi Router Berubah via Diagnostik** | **VERIFIED** | Zero-call ke `SafeConfigEngine.apply_change` dibuktikan via mock/spy. | Investigasi bersifat murni observasi read-only. |
| **Bocoran Password di Log / Output API** | **VERIFIED** | Sanitasi regex `mask_sensitive_data` + `redact_sensitive_values`. | Diuji dengan string password mentah. |
| **Bypass Otorisasi Endpoint Intelligence** | **VERIFIED** | Guard `require_topology_admin` menolak request tanpa token valid. | Menghasilkan status HTTP 401/403. |
| **Pencemaran Data Antar-Perangkat (Cross-Tenant Leak)** | **VERIFIED** | Query filter terisolasi pada `store.py` dengan parameter bind. | Diuji isolasi target R1 vs R2. |
| **SQL Injection pada Database Record** | **VERIFIED** | Semua query menggunakan parameterized SQL (`?`), bukan string formatting. | SQLite WAL mode dengan integrity check. |
| **Buffer Overflow / Denial-of-Service via Output Raksasa** | **VERIFIED** | Pembatasan `MAX_COMMAND_LENGTH` (512) dan `MAX_OUTPUT_CHARACTERS` (8000). | Buffer dipotong aman dengan flag `[truncated]`. |
| **Man-in-the-Middle (MitM) pada SSH Transport** | **PARTIAL** | Menggunakan `AIRA_KNOWN_HOSTS_FILE` jika tersedia. | Belum menguji rotasi host key otomatis di lab aktif. |
| **Bypass Autentikasi RouterOS Level Privilege** | **NOT TESTED** | Bergantung pada konfigurasi user group RouterOS (`group=read`). | Operator lab wajib mengonfigurasi user audit `group=read`. |

---

## 4. Rekomendasi Hardening Operasional untuk Deployment

1. **Konfigurasi Admin Token di Produksi:**  
   Pastikan variabel `AIRA_ADMIN_TOKEN` dan `AIRA_TOPOLOGY_ADMIN_TOKEN` diisi dengan token dengan entropi tinggi (minimal 32 karakter acak).
2. **Enforce Strict Known Hosts File:**  
   Set path `AIRA_KNOWN_HOSTS_FILE` di `.env` dan tambahkan sidik jari host router resmi untuk mencegah serangan ARP/DNS spoofing transit.
3. **Akun RouterOS Khusus:**  
   Gunakan user `aira-audit` dengan kebijakan `read,test,!write,!policy,!password,!sensitive,!reboot`.
