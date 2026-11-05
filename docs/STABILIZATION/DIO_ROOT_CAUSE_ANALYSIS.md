# AIRA OS — DIO Form Orchestration Root Cause Analysis

**Dokumen:** `docs/STABILIZATION/DIO_ROOT_CAUSE_ANALYSIS.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:** `AIRA_ECOSYSTEM/core/dio/`, `AIRA_ECOSYSTEM/agents/rei/dio_tools.py`, `AIRA_ECOSYSTEM/core/orchestrator.py`  
**Target:** Dynamic Interaction Orchestration (DIO)

---

## 1. Latar Belakang

Modul DIO (Dynamic Interaction Orchestration) bertanggung jawab untuk menyajikan formulir interaktif dan dialog konfirmasi kepada operator ketika informasi jaringan yang diminta ambigu, tidak lengkap, atau berpotensi destruktif (memerlukan persetujuan manusia).

---

## 2. Analisis Masalah

### 2.1 Ketiadaan Lifecycle State Tracking pada Schema
Sebelum stabilisasi, objek `InteractionSchema` hanya menyimpan metadata statis dan definisi form (`sections`, `actions`, `fields`). Tidak terdapat atribut status formal yang merefleksikan posisi interaksi dalam alur kerja sistem.
- **Risiko Replay / Double Submission:** Pengguna atau pengujian yang mengeksekusi submission berulang kali dengan `schema_id` yang sama akan memicu pemrosesan efek samping berkali-kali tanpa penjagaan status (`already_processed`).

### 2.2 Fragmentasi Resolusi Perangkat Jaringan
Ketika perintah diagnostik atau analisis dijalankan tanpa menyebutkan nama perangkat secara spesifik (misalnya: *"tolong cek kondisi router"*):
- Jika terdapat lebih dari 1 perangkat, AI Planner terkadang bingung atau memunculkan pesan error teks statis alih-alih menyajikan form pemilihan perangkat interaktif (`request_device_choice`).
- Sebaliknya, jika hanya ada satu router riil di inventaris (seperti pada lab fisik yang hanya memiliki router `CHR`), sistem sebelumnya tidak secara otomatis memilih perangkat tunggal tersebut, melainkan dapat meminta input redundan.

---

## 3. Rencana Perbaikan

1. Menambahkan enum `InteractionState` (`PENDING_INPUT`, `FORM_PRESENTED`, `SUBMITTED`, `VALIDATING`, `READY_TO_CONTINUE`, `COMPLETED`, `CANCELLED`) pada `core/dio/models.py`.
2. Menyematkan atribut `state` pada `InteractionSchema` dan merekam transisi status di `InteractionMemory`.
3. Memperkuat fungsi `submit_structured_input()` agar menolak submission ganda dan mengembalikan `already_processed: True`.
4. Memastikan orchestrator secara otomatis mendeteksi perangkat tunggal (`CHR`) tanpa membebani operator dengan pertanyaan yang tidak perlu.
