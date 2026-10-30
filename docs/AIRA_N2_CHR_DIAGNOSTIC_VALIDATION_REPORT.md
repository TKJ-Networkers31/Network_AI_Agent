# AIRA OS — Phase N2.4: End-to-End Live Diagnostic Investigation Report

**Status:** `VERIFIED_LIVE`  
**Timestamp:** 2026-10-30T17:58:02+07:00  
**Target:** `CHR` (`192.168.43.30:22`, MikroTik RouterOS v7.23.8)  
**Investigator:** `NetworkInvestigator` (`AIRA_ECOSYSTEM/core/network_intelligence/investigator.py`)  
**Operator:** Automated Acceptance Engineer (AIRA OS)

---

## 1. Executive Summary

Phase N2.4 performed end-to-end live diagnostic investigations against the MikroTik Cloud Hosted Router (CHR) v7. Two distinct network scenarios were executed through `NetworkInvestigator.create_and_run_investigation()`:

1. **Scenario A (`DEFAULT_ROUTE_FAILS`):** Verification of upstream default route integrity towards public internet DNS (`8.8.8.8`).
2. **Scenario B (`LAN_NO_INTERNET`):** Root-cause analysis of simulated client connectivity failure from IP `192.168.1.100`.

The diagnostic engine executed deterministically, gathering live observations across 5 real RouterOS v7 tables, establishing ranked hypotheses with explicit evidentiary provenance, and disclosing analytical limitations without hallucination.

---

## 2. Investigation Scenarios & Live Results

### Scenario A — Default Route Health Verification (`DEFAULT_ROUTE_FAILS`)

- **Incident ID:** Dynamic tracking
- **User Query:** *"Uji rute default CHR ke internet 8.8.8.8"*
- **Target IP:** `8.8.8.8`
- **Investigation Status:** `ANALYZING` / `HEALTHY`
- **Observed Facts:**
  1. `Ditemukan 1 default route: 1 aktif, 0 inaktif.` (Gateway: `192.168.43.1` via `ether1`).
- **Hypotheses Formulated:** `0` (Zero defect hypotheses).
- **Engine Behavior:** The engine correctly observed that an active `0.0.0.0/0` route exists via `192.168.43.1` (flag `DAd`). Consequently, it did **not** fabricate a routing failure or invent speculative issues.

---

### Scenario B — Root-Cause Isolation (`LAN_NO_INTERNET`)

- **Incident ID:** `inc_2e176993`
- **Correlation ID:** `corr_471314ddbee9`
- **User Description:** *"Klien 192.168.1.100 melaporkan tidak bisa akses internet melalui CHR"*
- **Investigation Status:** `DIAGNOSIS_READY`
- **Confidence:** `HIGH`
- **Confidence Explanation:** *"Diverifikasi terhadap 5 sumber bukti observasi."*

#### Observed Facts:
1. `Klien IP yang dievaluasi: 192.168.1.100.`
2. `Default route aktif ditemukan via gateway 192.168.43.1.`

#### Ranked Hypotheses:

| Rank | Hypothesis ID | Title | Confidence | Key Evidence | Alternative Hypotheses |
|---|---|---|---|---|---|
| **#1 (Leading)** | `hyp_1` | Klien dikonfigurasi dengan subnet/gateway yang salah atau berada di segmen VLAN lain | HIGH | • IP `192.168.1.100` tidak cocok dengan subnet lokal router (`192.168.43.0/24`).<br>• Tidak ditemukan rule NAT masquerade aktif. | Paket diteruskan tanpa translasi NAT (`hyp_2`). |
| **#2 (Secondary)** | `hyp_2` | Paket dari IP privat klien diteruskan ke internet tanpa translasi NAT publik sehingga didrop oleh ISP | HIGH | • Subnet mismatch.<br>• Zero NAT rules present on router. | Subnet/VLAN mismatch (`hyp_1`). |

#### Recommended Tests & Operator Guidance:
1. **Operator Verification:** Check static IP or DHCP lease on client `192.168.1.100`. (Risk: LOW, Safety: Read-only inspection).
2. **Planned Remediation:** Add NAT masquerade rule: `/ip firewall nat add chain=srcnat action=masquerade out-interface-list=WAN` (Safety: Planned change requiring administrative approval).

#### Live Telemetry Sources:
- `/ip address print detail`
- `/ip route print detail`
- `/ip firewall nat print detail`
- `/ip firewall filter print detail`
- `/interface print detail`

---

## 3. Truthful Uncertainty & Boundary Enforcement

1. **Zero Hallucination:** The diagnostic engine strictly derives hypotheses from concrete observations. If facts indicate health (as in Scenario A), no spurious warnings are injected.
2. **Limitations Disclosure:** Every report concludes with an explicit disclaimer:
   > *"Analisis ini bersifat statis dan berbasis bukti observasi terbaca. Perilaku dinamik (FastTrack, hardware offload, enkapsulasi terowongan) memerlukan pengujian trafik end-to-end langsung."*
3. **Audit Trail:** Incident record `inc_2e176993` and all associated `EvidenceItem` records were committed to `AIRA_ECOSYSTEM/database/chat_sessions.db` with full correlation IDs.
