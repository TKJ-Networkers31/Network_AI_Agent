# AIRA OS — NMS Background Scheduler Root Cause Analysis

**Dokumen:** `docs/STABILIZATION/NMS_ROOT_CAUSE_ANALYSIS.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:** `AIRA_ECOSYSTEM/core/nms_engine.py`, `AIRA_ECOSYSTEM/core/nms_models.py`  
**Target:** MikroTik CHR v7 (`192.168.43.30:22`)

---

## 1. Ringkasan Eksekutif

Pemeriksaan komprehensif terhadap modul Network Management System (NMS) AIRA OS mengidentifikasi empat anomali mendasar pada siklus hidup dan eksekusi background scheduler:
1. Tidak adanya *formal finite-state machine (FSM)* untuk siklus hidup scheduler (`STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `FAILED`).
2. Ketergantungan pada `asyncio.sleep(interval)` yang menyebabkan keterlambatan respon pembatalan/shutdown hingga 15 detik.
3. Ketiadaan mitigasi perulangan tanpa delay (*busy-spinning*) saat database inventaris tidak memiliki perangkat aktif untuk dipantau.
4. Potensi *concurrency race condition* ketika API atau thread eksternal memanggil `start_monitoring()` berulang kali.

---

## 2. Analisis Akar Masalah (Root Cause)

### 2.1 Ketiadaan Formal State Machine
Pada implementasi sebelumnya, status berjalannya scheduler hanya dideteksi secara pasif melalui pemeriksaan objek `self._scheduler_task is not None and not self._scheduler_task.done()`. 
- **Dampak:** Saat `start_monitoring()` dipanggil, terdapat celah waktu mikrodetik di mana task baru dibuat namun belum mulai dieksekusi oleh event loop. Jika pemanggil memeriksa `is_running()`, nilai `False` palsu dapat dikembalikan.
- **Risiko Re-entrancy:** Panggilan ganda dari startup FastAPI dan thread pengujian berisiko memicu inisialisasi ganda jika tidak dilindungi kunci re-entrant (`threading.RLock`).

### 2.2 Penundaan Terminasi (Laggy Shutdown)
Scheduler sebelumnya menggunakan:
```python
await asyncio.sleep(interval)
```
- **Dampak:** Ketika `stop_monitoring()` dipanggil dan event stop diset, perulangan `while` masih tertahan di `asyncio.sleep()` selama sisa durasi interval (hingga 15 detik), kecuali jika task dibatalkan secara paksa melalui `task.cancel()`.
- **Anomali Shutdown:** Pada proses graceful shutdown server, keterlambatan ini dapat memicu timeout SIGTERM atau unhandled `CancelledError` log spam.

### 2.3 Perulangan Tanpa Delay (Zero-Device Spin Loop)
Saat dilakukan pembersihan database perangkat uji coba (mock devices dihapus dan hanya menyisakan router fisik), query inventaris menghasilkan daftar kosong jika perangkat belum berstatus aktif.
- **Dampak:** Siklus polling terus menjalankan gather kosong dan query database berulang tanpa jeda adaptif, membebani IO SQLite dan log engine.

---

## 3. Rencana Tindakan Perbaikan

1. **Implementasi `NmsSchedulerState` Enum:** Mendefinisikan status eksplisit: `STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, dan `FAILED` di `core/nms_models.py`.
2. **Atomic State Transition & Locking:** Mengintegrasikan `self._state_lock = threading.RLock()` di `core/nms_engine.py` untuk mengunci setiap transisi status.
3. **Responsive Wake-up Event:** Mengganti `asyncio.sleep(interval)` dengan:
   ```python
   await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
   ```
   Pola ini memastikan scheduler langsung berhenti saat `stop_monitoring()` dipanggil tanpa menunggu timer interval selesai.
4. **Zero-Device Early Return:** Menghentikan polling siklus lebih awal jika daftar perangkat kosong dengan tetap memperbarui timestamp siklus berikutnya secara teratur.

---

## 4. Hasil Verifikasi

- Seluruh 37 pengujian unit pada `test_nms.py` lulus 100%.
- Pengujian siklus hidup idempoten `test_scheduler_start_stop_idempotent` terverifikasi lulus tanpa race condition.
