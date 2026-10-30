# AIRA OS — Phase 5 Read-Only Security Audit Report

**Tanggal Audit:** 2026-10-29  
**Domain:** Security Architecture, Read-Only Enforcement & Mutation Isolation  
**Auditor:** Antigravity AI Engineering Assistant  
**Workspace:** `D:\data\agent_ai`

---

## 1. Ringkasan Eksekutif

Dalam pengembangan sistem otomasi jaringan berbasis AI, risiko terbesar adalah terjadinya eksekusi perintah mutatif (*state-changing configuration*) yang tidak disengaja ke router produksi. 

Audit Phase 5 ini membuktikan secara empiris bahwa seluruh jalur investigasi insiden, playbook diagnostik, perencanaan desired-state, validasi statis, simulasi forwarding, dan endpoint REST API `/api/intelligence/*` **100% terisolasi dari eksekusi mutasi**. 

Sistem menerapkan validasi berlapis di sisi backend (*defense-in-depth*), pemisahan hak akses, sanitasi data sensitif, batas timeout serta pemutusan loop jika terjadi kegagalan.

---

## 2. Arsitektur Pemisahan Read-Only vs State-Changing

AIRA OS membagi domain eksekusi router menjadi 3 jalur yang terpisah secara fisik dan logis:

```
[ Operator / Prompt ]
         │
         ▼
┌─────────────────────────────────┐
│   Backend Security Classifier   │
│  core/network_intelligence/     │
│          security.py            │
└────────────────┬────────────────┘
                 │
       Is strictly Read-Only?
        ├── YES ──► [ Pure Read-Only Diagnostic Path ]
        │                 │
        │                 ▼
        │           APCE ConnectionManager (Paramiko Persistent Session)
        │                 │ (Hanya menjalankan perintah allowlist /print)
        │                 ▼
        │           [ Router CLI ]
        │
        └── NO ───► [ Hard Rejection: Security Policy Violation ]
                          │
                          ▼
                    (BLOCKED: Tidak pernah diteruskan ke transport)

═══════════════════════════════════════════════════════════════════════════
[ Jalur Terpisah: Configuration Change Lifecycle (Hanya melalui Persetujuan) ]
  SafeConfigEngine (agents/akane/config_engine.py)
  READ -> PLAN -> VALIDATE -> PREVIEW -> [ APPROVAL TOKEN GUARD ] -> APPLY
  (Hanya dapat dipicu melalui otorisasi token eksplisit operator manusia)
```

---

## 3. Implementasi Kebijakan Keamanan (core/network_intelligence/security.py)

### 3.1 Allowlist Perintah Diagnostik Eksplisit
AIRA menolak model *denylist* (daftar hitam) yang rentan terhadap bypass sintaks. Sebagai gantinya, AIRA menggunakan **Allowlist Positif** yang terkompilasi melalui regex deterministik untuk RouterOS v6 dan v7:
- `/system identity print`
- `/system resource print`
- `/system routerboard print`
- `/interface print detail`
- `/interface bridge (print|port print|vlan print) detail`
- `/ip address print detail`
- `/ip route print detail (where ...)?`
- `/ip route rule print detail`
- `/ip firewall (filter|nat|mangle|raw|connection) print detail`
- `/ip arp print detail`
- `/ip dns print`
- `/routing rule print detail`
- `/routing ospf (neighbor|instance|interface) print`
- `/routing bgp (peer|connection|session) print detail`
- `/ping <target> count=[1-5]` (dengan batas hitungan ketat)
- `/tool traceroute <target> count=[1-3]`

### 3.2 Penolakan Kata Kerja Mutasi (*Mutating Verbs Rejection*)
Setiap token perintah diurai secara leksikal. Jika ditemukan kata kerja mutasi berikut dalam posisi kata kerja:
`add`, `set`, `remove`, `enable`, `disable`, `reset`, `reboot`, `shutdown`, `edit`, `comment`, `export`, `import`, `run`, `delete`, `install`, `upgrade`, `downgrade`, `restore`
Maka perintah **langsung diblokir** dengan pesan penolakan keamanan formal sebelum menyentuh koneksi SSH router.

### 3.3 Pencegahan Command Injection
Perintah diperiksa terhadap karakter injeksi shell atau multiline:
- Newline (`\n`, `\r`) — mencegah eksekusi beruntun di CLI.
- Titik koma (`;`) — mencegah *command chaining*.
- Pipe (`|`) — mencegah redirect atau subshell execution.
- Backtick (`` ` ``) dan tanda Dollar (`$`) — mencegah *command substitution* RouterOS scripting (`$system ...`).
- Batas panjang perintah maksimum: 512 karakter.

### 3.4 Redaksi Rahasia & Kredensial (*Secret Redaction*)
Sebelum hasil perintah ditampilkan di antarmuka pengguna atau disimpan ke audit log SQLite, seluruh nilai sensitif disanitasi:
- `password="..."` -> `password="******"`
- `wpa2-pre-shared-key="..."` -> `wpa2-pre-shared-key="******"`
- `secret="..."` -> `secret="******"`
- `community="..."` -> `community="******"`
- `token="..."` -> `token="******"`
- `private-key="..."` -> `private-key="******"`

---

## 4. Bukti Verifikasi Spy / Mock (test_phase5_read_only_enforcement.py)

Pengujian unit dan integrasi dilakukan dengan mock dan spy untuk membuktikan ketiadaan efek samping mutatif:

| Skenario Pengujian | Target Komponen | Ekspektasi | Hasil Uji |
| :--- | :--- | :--- | :--- |
| **Uji Allowlist Perintah Diagnostik** | `validate_readonly_command()` | 21 perintah diagnostik sah RouterOS diizinkan | **PASS (100%)** |
| **Uji Penolakan Mutasi** | `validate_readonly_command()` | 13 perintah mutatif (`add`, `reboot`, `remove`, `disable`, dsb.) ditolak | **PASS (100%)** |
| **Uji Penolakan Injeksi Shell** | `validate_readonly_command()` | Semicolon, newline, pipe, backtick ditolak | **PASS (100%)** |
| **Uji Redaksi Kredensial** | `redact_sensitive_values()` | Password, WiFi PSK, SNMP community diganti `******` | **PASS (100%)** |
| **Spy Investigasi Insiden** | `NetworkInvestigator` | `SafeConfigEngine.apply_change` call count == 0 | **PASS (0 call)** |
| **Spy Playbook Stepping** | `PlaybookEngine` | `SafeConfigEngine.apply_change` call count == 0 | **PASS (0 call)** |
| **Spy Perencanaan & Simulasi** | `ConfigurationPlanner`, `StaticSimulator` | `SafeConfigEngine.apply_change` call count == 0 | **PASS (0 call)** |
| **Spy REST API Endpoints** | `/api/intelligence/*` | `SafeConfigEngine.apply_change` call count == 0 | **PASS (0 call)** |

---

## 5. Batasan Jaminan Keamanan (*Limitations of Guarantee*)

1. **Jaminan Perangkat Lunak vs Jaminan Firmware:**
   Kebijakan allowlist berjalan pada layer aplikasi Python (AIRA backend). Jika operator secara manual menggunakan aplikasi eksternal (misal: Winbox, PuTTY langsung) di luar AIRA, AIRA tidak dapat mencegah mutasi yang dilakukan oleh software eksternal tersebut.
2. **Kredensial Akun SSH Router:**
   Sebagai *best practice* keamanan jaringan, disarankan agar akun SSH yang digunakan oleh AIRA di MikroTik dikonfigurasi dengan grup hak akses `read` saja pada menu `/user group add name=readonly policy=read,test,sniff,api,ssh`. Dengan demikian, bahkan jika terjadi kegagalan software AIRA, firmware RouterOS tetap menolak perintah penulisan di level kernel.
3. **Penyalahgunaan Perintah /ping dan /tool traceroute:**
   Meskipun perintah `/ping` diizinkan, AIRA membatasi `count=1-5` untuk mencegah dampak DoS terhadap CPU router pada perangkat berdaya rendah (MIPSBE/SMIPS).
