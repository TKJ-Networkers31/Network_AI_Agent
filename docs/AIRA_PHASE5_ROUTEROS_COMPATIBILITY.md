# AIRA OS — Phase 5 RouterOS v6 & v7 Compatibility Report

**Tanggal Audit:** 2026-10-29  
**Domain:** Network Engineering, MikroTik RouterOS v6/v7 Syntax & Parser Compatibility  
**Auditor:** Antigravity AI Engineering Assistant  
**Workspace:** `D:\data\agent_ai`

---

## 1. Ringkasan Eksekutif

MikroTik RouterOS versi 7 memperkenalkan perombakan arsitektur kernel Linux 5.x dan stack routing (OSPF, BGP, Routing Filter, dan Routing Rules). Perubahan ini menimbulkan perbedaan format output CLI yang signifikan dibandingkan RouterOS versi 6.

AIRA OS Phase 5 mengaudit dan memverifikasi parser deterministik serta generator perintah untuk memastikan kompatibilitas penuh tanpa mencampuradukkan flag atau asumsi antarmuka.

---

## 2. Matriks Perbedaan Sintaks CLI & Command Mapping

AIRA secara dinamis memetakan perintah investigasi berdasarkan `ros_major_version` (v6 vs v7):

| Kategori Investigasi | RouterOS v6 Command | RouterOS v7 Command | Catatan Perbedaan Arsitektur |
| :--- | :--- | :--- | :--- |
| **System Identity** | `/system identity print` | `/system identity print` | Identik |
| **IP Addresses** | `/ip address print detail` | `/ip address print detail` | Format kolom v7 menyertakan header `Columns:` |
| **IP Routing Table** | `/ip route print detail` | `/ip route print detail` | v6: Flag spasi (`A S`, `ADC`); v7: Flag majemuk (`As`, `DAc`) |
| **Policy Routing Rules** | `/ip route rule print detail` | `/routing rule print detail` | Di v7 dipindahkan dari `/ip route rule` ke `/routing rule` |
| **Firewall Filter** | `/ip firewall filter print detail` | `/ip firewall filter print detail` | FastTrack dan invalid-drop identik |
| **Firewall NAT** | `/ip firewall nat print detail` | `/ip firewall nat print detail` | Masquerade dan dst-nat to-ports identik |
| **Bridge VLAN** | `/interface bridge vlan print detail` | `/interface bridge vlan print detail` | v7 menyertakan dynamic hardware offload VLANs |
| **OSPF Neighbors** | `/routing ospf neighbor print` | `/routing ospf neighbor print` | Format tabular v7 menyertakan kolom `instance` |
| **OSPF Instance** | `/routing ospf instance print detail` | `/routing ospf instance print` | Di v7 opsi `distribute-default` diganti template & out-filter |
| **BGP Peers/Sessions** | `/routing bgp peer print detail` | `/routing bgp connection print detail` | v6: `remote-address`, `remote-as`; v7: `remote.address`, `remote.as` |
| **BGP Dynamic Sessions**| N/A | `/routing bgp session print detail` | v7 memisahkan deklarasi *connection* dari runtime *session* |

---

## 3. Analisis Flag Routing Table (v6 vs v7)

### 3.1 RouterOS v6 Flags
Pada v6, flag ditampilkan dengan spasi individual untuk setiap karakteristik rute:
- `A` = Active
- `S` = Static
- `D` = Dynamic
- `C` = Connect (Directly connected interface)
- `b` = BGP
- `o` = OSPF
- Contoh: `# 0 A S 0.0.0.0/0 192.168.1.1 1`

### 3.2 RouterOS v7 Flags
Pada v7, flag digabungkan dalam format akronim huruf besar/kecil majemuk:
- `As` = Active, Static
- `DAc` = Dynamic, Active, Connect
- `DAo` = Dynamic, Active, OSPF
- `DAb` = Dynamic, Active, BGP
- Contoh: `# 0 As 0.0.0.0/0 192.168.1.1 1`

Parser `agents/akane/reasoning_engine.py::parse_routeros_routes` telah diverifikasi mendukung kedua format secara transparan melalui normalisasi regex toleran spasi dan pemeriksaan flag case-insensitive.

---

## 4. Perbedaan BGP & Routing Filter

1. **Struktur Parameter BGP:**
   - v6 menggunakan penamaan flat: `remote-address=x.x.x.x remote-as=65000`.
   - v7 menggunakan notasi hierarkis bertitik: `remote.address=x.x.x.x/32 remote.as=65000`.
   - Parser `_parse_bgp_peers` di `evidence.py` menangani kedua sintaks dengan regex ganda:
     `r"remote\.address=([0-9\.]+)"` dan `r"remote-address=([0-9\.]+)"`.

2. **Routing Filters:**
   - v6 menggunakan list rule sekuensial sederhana: `/routing filter add chain=ISP_IN action=accept`.
   - v7 menggunakan bahasa script filter ekspresif baru: `/routing filter rule add chain=ISP_IN rule="if (dst in 10.0.0.0/8) { accept; }"`.

---

## 5. Keterbatasan Parser & Mitigasi (*Parser Limitations & Mitigations*)

1. **Wrapped Lines / Output Terpotong:**
   - Pada terminal SSH dengan dimensi kolom sempit (misal 80 kolom), MikroTik dapat melipat baris (*line wrapping*).
   - *Mitigasi:* AIRA mengutamakan perintah `print detail` atau parsing berbasis regex multi-line token sehingga pemotongan baris di terminal tidak merusak hasil ekstraksi.
2. **Missing Flags pada Custom Scripts:**
   - Jika router mengembalikan output non-standar atau terinterupsi buffer, parser menandai status bukti sebagai `INVALID` atau `PARTIAL`, bukan berasumsi nilai default.
3. **Pemberian Skor / Probabilitas:**
   - Sesuai prinsip *Evidence-driven*, AIRA tidak mengarang persentase probabilitas numerik (misal "87.3%"), melainkan menggunakan tingkat keyakinan kualitatif (`HIGH`, `MEDIUM`, `LOW`, `INSUFFICIENT_EVIDENCE`) yang berdasar langsung pada jumlah dan kepastian bukti observasi.

---

## 6. Bukti Pengujian Fixture (test_phase5_ros_compatibility.py)

Pengujian fixture terpisah telah dijalankan terhadap direktori `AIRA_ECOSYSTEM/tests/fixtures/ros_v6/` dan `ros_v7/`:

- `test_command_maps_distinguish_v6_and_v7_syntax` -> **PASS**
- `test_parse_routeros_v6_routes` -> **PASS**
- `test_parse_routeros_v7_routes` -> **PASS**
- `test_parse_ip_addresses_v6_and_v7` -> **PASS**
- `test_parse_firewall_filter_v6_and_v7` -> **PASS**
- `test_parse_firewall_nat_v6_and_v7` -> **PASS**
- `test_parse_bridge_vlan_v6_and_v7` -> **PASS**
- `test_parse_ospf_neighbor_v6_and_v7` -> **PASS**
- `test_parse_bgp_peers_v6_and_v7` -> **PASS**
