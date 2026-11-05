# AIRA OS — WebSocket Disconnection Root Cause Analysis

**Dokumen:** `docs/STABILIZATION/WEBSOCKET_ROOT_CAUSE_ANALYSIS.md`  
**Status:** DIVERIFIKASI & SELESAI  
**Komponen:** `app/frontend/src/hooks/useAiraSocket.js`, `app/frontend/src/hooks/useAiraSocketPool.js`, `api/routers/ws.py`  
**Gejala:** Koneksi WebSocket chat terputus secara reguler setelah ~45–47 detik hening.

---

## 1. Analisis Gejala

Pengguna melaporkan bahwa saat sesi chat berada dalam kondisi idle atau proses inferensi/pembacaan jaringan memakan waktu lebih dari 40 detik, koneksi WebSocket tiba-tiba beralih ke status `closed`, memicu reconnect banner ("Menyambungkan kembali...").

Investigasi jaringan mengonfirmasi waktu pemutusan koneksi terjadi secara konsisten pada rentang 45–60 detik sejak paket terakhir dikirimkan.

---

## 2. Identifikasi Akar Masalah (Root Cause)

### 2.1 Ketiadaan Client-Side Heartbeat Ping
- **Backend `api/routers/ws.py`:**
  Backend FastAPI telah memiliki penanganan pesan ping:
  ```python
  if msg_type == "ping":
      await websocket.send_json({"type": "pong"})
      continue
  ```
- **Frontend Hooks (`useAiraSocket.js` dan `useAiraSocketPool.js`):**
  Frontend **TIDAK PERNAH** mengirimkan payload `{"type": "ping"}` secara berkala.
- **Mekanisme TCP / NAT Timeout:**
  Banyak browser, proxy lokal (Vite dev server / reverse proxy), dan stack TCP OS secara otomatis menutup koneksi WebSocket yang berada dalam keadaan diam (*idle connection timeout*) setelah 45 hingga 60 detik tanpa lalu lintas frame.

### 2.2 Isolasi Lifecycle WebSocket vs SSH
Terdapat kekhawatiran bahwa pemutusan WebSocket dapat merusak koneksi SSH router.
- Hasil audit terhadap `api/routers/ws.py` menunjukkan bahwa blok `except WebSocketDisconnect:` hanya menjalankan:
  ```python
  await manager.disconnect(session_id, websocket)
  ```
  Ini hanya melepaskan websocket client dari memory manager. Task turn yang sedang berjalan dan koneksi SSH persisten di `agents/akane/connection_manager.py` tetap berjalan di background dan tidak dimatikan.
- Namun, pemutusan WebSocket pada client menyebabkan hilangnya token streaming secara realtime dan memicu ketidaknyamanan antarmuka.

---

## 3. Strategi Solusi

1. Menerapkan interval pengiriman heartbeat ping berkala (15 detik) pada sisi client saat socket berada dalam status `WebSocket.OPEN`.
2. Menyaring frame respons `{"type": "pong"}` pada `onmessage` agar tidak mengganggu parser streaming chat.
3. Membersihkan timer heartbeat secara deterministik saat socket ditutup atau komponen unmount.
