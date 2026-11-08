# AIRA OS — MASTER DECISION & COMPLETE REMEDIATION EXECUTION PLAN
## Dokumen Keputusan Utama untuk Menyelesaikan Temuan Audit, Menstabilkan Runtime, dan Meningkatkan Kesiapan Operasional

**Versi dokumen:** 1.0  
**Tanggal keputusan:** 8 November 2026  
**Workspace yang dilaporkan:** `/home/Lingga/Documents/project/Network_AI_Agent`  
**Application root yang dilaporkan:** `AIRA_ECOSYSTEM/`  
**Baseline Git yang dilaporkan Stage 0:** `e324caa875ab163be23bb6321f330c1fe79d40f1`  
**Status dokumen:** Keputusan arsitektur dan instruksi implementasi  
**Target pembaca:** Pemilik proyek AIRA, siswa SMK TJKT, dan AI coding agent (Google Antigravity)

> **Penting:** Dokumen ini adalah keputusan dan rencana kerja berdasarkan laporan audit, Stage 0, CI log, dan runtime log yang diberikan. Dokumen ini bukan bukti bahwa source code sudah diperbaiki. Antigravity wajib memeriksa kembali source code aktual sebelum mengubah file apa pun.

---

# BAGIAN I — RINGKASAN UNTUK PEMILIK AIRA

## 1. Apa tujuan pekerjaan besar ini?

AIRA tidak cukup hanya bisa dibuka, menampilkan dashboard, atau menjawab chat. AIRA harus menjadi aplikasi yang:

1. **Berfungsi:** setiap fitur benar-benar melakukan pekerjaan sesuai tujuan dan nama fungsinya.
2. **Terintegrasi:** frontend, backend, AI, database, WebSocket, dan perangkat jaringan berkomunikasi dengan kontrak yang konsisten.
3. **Aman:** pengguna hanya dapat mengakses data dan tindakan yang memang menjadi haknya.
4. **Konsisten:** data dinamis memiliki sumber kebenaran (Single Source of Truth/SSOT) yang jelas.
5. **Teruji:** klaim bahwa fitur bekerja didukung pengujian yang dapat diulang.
6. **Mudah dirawat:** tidak dipenuhi implementasi ganda, dead code, konfigurasi yang bertabrakan, atau dependency yang tidak jelas.
7. **Tahan terhadap kegagalan:** provider AI timeout, OCR gagal, traceroute tidak tersedia, atau database sibuk tidak boleh membuat seluruh aplikasi ikut gagal.
8. **Siap dioperasikan:** Docker, CI, backup, restore, logging, dan konfigurasi deployment sesuai dengan source code yang sebenarnya.

Targetnya bukan sekadar “semua file rapi”. Targetnya adalah **seluruh fitur yang dipertahankan mempunyai alur kerja yang benar, data yang benar, batas keamanan yang benar, dan bukti test yang benar**.

Tidak ada rekayasa perangkat lunak yang dapat menjamin “perfect” atau tidak akan pernah memiliki bug. Target profesional yang bisa dibuktikan adalah: tidak ada blocker yang diketahui dan belum ditangani, seluruh fitur yang dinyatakan selesai telah diuji, risiko yang tersisa dicatat, serta proses pemulihan tersedia.

## 2. Sumber informasi yang menjadi dasar keputusan

Master plan ini menggunakan empat kelompok informasi:

- Hasil audit repository AIRA yang dilaporkan mencakup 1.180 file project, 62 fitur, 45 bug fungsional, 28 temuan keamanan, 26 rekomendasi, dan 13 stage roadmap.
- Hasil Stage 0 yang merekonsiliasi rekomendasi, path, Docker, CI, database, autentikasi, dan ketergantungan.
- Log CI Python dan frontend yang menunjukkan kegagalan dependency, error import/type annotation, dan perintah test yang tidak valid.
- Log runtime VPS dan pengujian langsung AIRA untuk provider AI, classifier, auto-memory, polling, session heartbeat, Vision/OCR, ping, dan traceroute.

Angka-angka audit di atas adalah **angka yang dilaporkan oleh audit**, bukan hasil penghitungan ulang dalam dokumen ini. Antigravity harus mengonfirmasi bahwa source tree yang sekarang dikerjakan masih cocok dengan baseline audit.

## 3. Kondisi awal berdasarkan audit

| Area | Kondisi yang dilaporkan | Makna sederhana |
|---|---|---|
| File project | 1.180 file | Banyak bagian project harus ditelusuri, bukan hanya file utama |
| Fitur | 62 fitur | Setiap fitur perlu status dan bukti |
| Fitur COMPLETE | 8 | Baru sebagian kecil yang dinyatakan lengkap oleh audit awal |
| Fitur PARTIAL | 24 | Ada fungsi yang belum tersambung atau belum selesai |
| Fitur BROKEN | 14 | Ada implementasi yang dilaporkan gagal |
| Fitur STATIC/MOCK | 7 | Sebagian data/aksi masih simulasi |
| Fitur DUPLICATED | 5 | Ada fungsi yang tumpang tindih |
| Bug fungsional | 45 | Perlu diperbaiki dan dites |
| Temuan keamanan | 28 | Perlu penutupan dan pengujian akses |
| Test files | 201 | Banyak test tersedia, tetapi baseline CI masih gagal |
| Database | 18 skema/80+ tabel menurut audit | Perlu kejelasan kepemilikan dan integritas data |

**Makna untuk Lingga:** angka “1.180 file diaudit” tidak sama dengan “1.180 file sudah terbukti benar saat aplikasi berjalan”. Audit statis membaca dan menganalisis kode; runtime test membuktikan perilaku ketika program dieksekusi. Keduanya dibutuhkan.

---

# BAGIAN II — KEPUTUSAN ARSITEKTUR YANG TIDAK BOLEH BERUBAH SEMBARANGAN

## 4. Keputusan BD-01 — Billing dihapus sepenuhnya

**Keputusan pemilik proyek:** sistem billing AIRA tidak dipertahankan dan tidak diperbaiki untuk digunakan kembali. Sistem tersebut harus dihapus dari aplikasi.

Ini menggantikan rekomendasi awal REC-03 yang sebelumnya menyarankan pengamanan webhook billing dan simulasi pembayaran. Antigravity tidak boleh menjalankan REC-03 versi lama sebagai pekerjaan “mengamankan billing”.

### 4.1 Komponen yang harus ditelusuri dan dihapus

- Billing API router dan seluruh endpoint billing.
- Payment webhook handlers dan signature verification khusus pembayaran.
- Payment provider integrations.
- Payment simulation/mock payment.
- Subscription purchase, upgrade, renewal, cancellation, dan invoice flows.
- Billing service dan billing-specific controllers/repositories.
- Halaman, tab, menu, tombol, modal, form, route, dan komponen frontend khusus billing.
- Billing-specific background tasks, schedulers, workers, notifications, dan event handlers.
- Billing-only configuration, environment variables, secrets, dependency, dokumentasi, dan deployment settings.
- Billing-only database tables, indexes, triggers, foreign keys, model, migration, dan seed data setelah semua referensi diverifikasi.
- Billing-only tests. Ganti dengan tests yang membuktikan billing routes/UI/service sudah tidak tersedia dan tidak ada import yatim.

### 4.2 Yang tidak boleh ikut terhapus

Jangan menghapus fitur hanya karena namanya mempunyai kata “plan”, “limit”, “token”, atau “usage”.

Tetap pertahankan jika masih diperlukan:

- Token quota dan token usage metering.
- Model routing dan model governance.
- Permission/RBAC.
- Organization, user, group, dan tenant management.
- Audit logs yang tidak khusus billing.
- Operational policy yang tidak bergantung pada transaksi pembayaran.
- Admin-managed quota/entitlements jika memang dibutuhkan untuk mengatur kemampuan sistem tanpa payment/subscription.

### 4.3 Pemisahan quota dari billing

AIRA tetap boleh mempunyai batas penggunaan model/AI. Namun batas itu harus menjadi **operational quota policy**, bukan bukti bahwa pengguna telah membayar.

Periksa semua hubungan:
`billing plan -> subscription -> entitlement -> token quota -> model access`.

Lepaskan ketergantungan billing. Rancang sumber kebijakan baru yang eksplisit, misalnya policy yang dikelola administrator organisasi/platform sesuai desain role AIRA. Jangan membuat self-upgrade, mock purchase, atau jalur pembayaran pengganti.

### 4.4 Database dan data billing

- Identifikasi seluruh tabel dan kolom yang benar-benar khusus billing.
- Pastikan tabel/kolom itu tidak dipakai quota, user, tenant, audit, atau fitur lain.
- Buat backup yang dapat diverifikasi sebelum migrasi.
- Hapus billing schema dari database aktif melalui migration terkontrol.
- Jangan menghapus database operasional atau data non-billing.
- Data billing historis tidak boleh ikut terhapus secara tidak sengaja. Catat dengan jelas apa yang dihapus dari database aktif, apa yang disimpan sementara dalam backup terbatas untuk rollback, dan kapan backup lama boleh dipurge sesuai kebijakan pemilik proyek.
- Setelah penerimaan akhir, tidak boleh ada billing flow yang dapat dipanggil atau ditampilkan dari aplikasi.

### 4.5 Kriteria selesai penghapusan billing

- Tidak ada billing route yang terdaftar.
- Tidak ada payment webhook yang aktif.
- Tidak ada payment simulation atau self-upgrade.
- Tidak ada billing UI/navigation.
- Tidak ada billing worker/scheduler.
- Tidak ada import billing yang rusak.
- Tidak ada billing-only environment variable yang masih diwajibkan.
- Tidak ada billing-only tabel aktif yang tidak disengaja.
- Token quota dan RBAC tetap bekerja.
- CI dan seluruh test yang relevan lulus.
- Laporan penghapusan berisi daftar file, route, schema, dan dependency yang dihapus.

## 5. Keputusan BD-02 — Organization, User, Group, Permission

Arsitektur akses yang dituju:

`Organization -> Users -> Groups -> Permissions`

Arti sederhananya:
- **Organization:** pemilik ruang kerja dan data operasional bersama.
- **User:** akun orang yang masuk ke AIRA.
- **Group:** pengelompokan user untuk mengelola akses.
- **Permission:** tindakan yang boleh dilakukan, misalnya membaca device atau menjalankan perintah.

Aturan wajib:
- Backend harus memeriksa permission. Menyembunyikan tombol pada frontend tidak cukup.
- Setiap data organisasi harus memiliki organization/tenant ownership yang jelas.
- User tidak boleh membaca data user lain yang bersifat privat.
- User dari organisasi A tidak boleh membaca atau mengubah data organisasi B.
- Role internal/platform tidak boleh otomatis membuat setiap internal viewer menjadi superadmin.
- DENY harus dievaluasi dengan aturan yang konsisten dan tidak boleh dilewati oleh ALLOW lain tanpa keputusan desain yang eksplisit.
- Semua operasi sensitif harus mencatat actor, target, hasil, dan correlation/request ID tanpa mencatat secret.

## 6. Keputusan BD-03 — Private user data berbeda dari organization shared data

### Private per user
- Chat history pribadi.
- Long-term memory pribadi.
- Persona/preferensi pribadi.
- Pengaturan personal.
- Konteks dan dokumen personal jika fiturnya memang privat.

Semua query harus di-scope dengan identitas user yang didapat dari session/token terverifikasi. Jangan mempercayai `user_id` dari body/header/query secara langsung.

### Shared per organization
- Device inventory.
- Network topology.
- NMS/monitoring data.
- Incident/alert organisasi.
- Shared network configuration.
- Operasional gateway organisasi.

Semua query harus di-scope dengan organization/tenant yang sah.

## 7. Keputusan BD-04 — Guest mode aman, bukan bypass frontend

`?guest=1`, localStorage flag, atau nilai dari browser tidak boleh dianggap sebagai autentikasi.

Jika Guest Mode dipertahankan:
- Backend menerbitkan identitas/session guest sementara.
- Guest memiliki permission terbatas.
- Guest tidak punya akses ke data organisasi.
- Guest tidak dapat membaca memory, persona, chat, atau data privat user lain.
- Guest data bersifat sementara dan memiliki kebijakan cleanup.
- Frontend tidak dapat mengubah dirinya menjadi authenticated guest hanya dengan query parameter atau localStorage.

Jika Guest Mode belum dapat diamankan, nonaktifkan jalur akses tersebut sampai implementasi resmi siap. Jangan mempertahankan bypass demi membuat UI terlihat bisa dibuka.

## 8. Keputusan BD-05 — Database menjadi SSOT, tetapi tidak semua data harus berada dalam satu file

Single Source of Truth berarti setiap domain data memiliki sumber kebenaran yang jelas. Ini **tidak berarti semua database harus digabung menjadi satu file SQLite besar**.

Batas awal yang harus dievaluasi:
- `topology.db`: sumber data inti multi-tenant seperti user, tenant, role, session, device/operasional sesuai schema yang telah diverifikasi.
- Database metrik NMS terpisah dapat dipertahankan jika volume telemetry tinggi dan pemisahan memang mengurangi write-lock.
- Chat dan private memory harus memiliki ownership yang tegas.
- Model/provider configuration harus mempunyai sumber data yang jelas dan secret yang terlindungi.
- Edge gateway boleh memiliki local buffer untuk offline store-and-forward; sinkronisasi harus aman dan terukur.

Jangan membuat database baru atau menggabungkan database hanya berdasarkan nama. Petakan dulu tabel, query, migration, dan data flow.

## 9. Keputusan BD-06 — Working tree dan data pengguna harus dipertahankan

Stage 0 melaporkan:
- Branch `main`.
- Commit baseline `e324caa875ab163be23bb6321f330c1fe79d40f1`.
- 13 file tracked yang sudah dimodifikasi.
- 2 direktori untracked, termasuk komponen frontend dan `AUDIT_REPORT/`.

Perubahan itu harus diperlakukan sebagai pekerjaan pemilik proyek, bukan sampah.

**Dilarang:**
- `git reset --hard`.
- `git checkout -- .`.
- Menghapus direktori untracked.
- Menimpa file modified tanpa membaca diff.
- Mengganti file database aktif tanpa backup dan verifikasi.
- Menjalankan migration ke production selama test.
- Menghapus file hanya karena tidak ditemukan import langsung.

Sebelum implementasi:
1. Catat `git status --short`.
2. Simpan baseline diff binary di lokasi aman di luar repository.
3. Catat daftar file untracked dan checksum-nya.
4. Buat branch kerja baru tanpa kehilangan perubahan.
5. Pastikan branch kerja masih membawa seluruh perubahan awal.
6. Buat backup database menggunakan SQLite Online Backup API atau mekanisme yang sesuai dengan database aktif.
7. Verifikasi integrity backup dan lakukan restore test pada salinan sementara.
8. Jangan menampilkan secret atau data pribadi dalam log checkpoint.

---

# BAGIAN III — HASIL CI DAN RUNTIME YANG WAJIB DITANGANI

## 10. Keputusan BD-07 — Perbaiki baseline CI sebelum mengukur kualitas

### 10.1 Python CI: FastAPI tidak ditemukan

Log:
```text
ModuleNotFoundError: No module named 'fastapi'
```

Terjadi ketika mengumpulkan:
- `test_phase_g_network_intelligence.py`
- `test_phase_f1_all.py`
- `test_phase_f2_dynamic_ui_rbac.py`

Diagnosis Stage 0: dependency workflow memasang `requirements.txt`, sementara FastAPI/Uvicorn berada di manifest lain (`requirements-web.txt`).

Tindakan:
- Inventarisasi semua dependency yang dipakai runtime, test, CLI, AI, vision, dan NMS.
- Tetapkan dependency manifest yang dapat direproduksi.
- Pisahkan core/runtime, web API, test, dan optional/heavy extras bila memang dibutuhkan.
- Pastikan Docker dan CI memasang kumpulan dependency yang tepat.
- Jangan menginstal semua dependency optional secara membabi buta jika memperbesar image atau membuat konflik.
- Tambahkan pemeriksaan versi dan dependency consistency.

### 10.2 Python CI: Optional tidak dikenal

Log:
```text
NameError: name 'Optional' is not defined
```

Lokasi yang dilaporkan:
`AIRA_ECOSYSTEM/core/filesystem/history.py:117`

Tindakan:
- Periksa import di file aktual.
- Tambahkan `from typing import Optional`, atau gunakan annotation modern yang cocok dengan versi Python minimum project.
- Jalankan test module tersebut secara terpisah.
- Jalankan test collection keseluruhan setelah perbaikan.

### 10.3 Frontend CI: flag --run tidak valid

Log:
```text
> node --test --run
node: bad option: --run
```

Script `package.json` menggunakan Node built-in test runner (`node --test`).

Tindakan:
- Perbaiki workflow agar menggunakan command yang cocok, umumnya `npm test` tanpa flag `--run`.
- Jangan mengganti ke Vitest/Jest hanya demi menghilangkan error kecuali ada alasan teknis dan rencana migrasi yang jelas.
- Jalankan command yang sama persis seperti CI secara lokal/CI.

### 10.4 Arti hasil baseline

`pytest` berhenti pada collection dengan empat error. Artinya test belum mencapai tahap eksekusi normal untuk keseluruhan suite. Jangan melaporkan “52 test lulus” hanya dari angka 56 items/4 errors. Setelah collection bersih, catat jumlah collected, passed, failed, skipped, xfailed, dan durasi.

## 11. Keputusan BD-08 — AI provider, classifier, fallback, dan auto-memory harus tahan gagal

### 11.1 Temuan runtime log

Log yang diberikan menunjukkan:
- Request chat ke provider NVIDIA mengalami timeout.
- Model Router mengeluarkan pesan fallback dari model utama ke model lain.
- Request berikutnya ke provider NVIDIA mendapat HTTP 404.
- Task classifier mengeluarkan warning bahwa model `qwen/qwen-2.5-7b-instruct` tidak tersedia/tidak dikenali; teks log terpotong sehingga penyebab pastinya belum diketahui.
- Setelah error classifier, label `general` dengan confidence `0.50` digunakan.
- Auto memory gagal menghubungi URL yang log-nya terpotong (`https://integra...`).
- Runtime Brain berpindah `IDLE -> THINKING -> IDLE`.
- Planner kemudian tercatat dihentikan oleh user melalui `cancel_event`.
- Heartbeat session berulang kali mendapat HTTP 200.
- `/api/connections` terlihat dipanggil berulang sekitar setiap lima detik pada beberapa rentang waktu.

### 11.2 Yang dapat dan tidak dapat disimpulkan

Dapat disimpulkan:
- Provider utama setidaknya mengalami timeout pada request yang tercatat.
- Percobaan fallback menghasilkan 404 pada request berikutnya.
- Classifier memiliki warning konfigurasi/availability.
- Auto-memory mengalami kegagalan koneksi.
- Heartbeat endpoint memberi status 200.
- Beberapa polling connections berulang.

Belum dapat disimpulkan:
- API key pasti salah.
- Provider NVIDIA sedang down secara global.
- Model fallback pasti sudah dihapus.
- Auto-memory selalu gagal.
- Chat response pasti sukses hanya karena state kembali ke IDLE.
- Semua polling berasal dari satu komponen.
- Heartbeat 200 membuktikan seluruh autentikasi aman.

Antigravity harus menemukan log lengkap, request ID, provider config, model catalog, dan call path tanpa menampilkan API key.

### 11.3 Rancangan provider reliability

Audit dan implementasikan:
1. Provider registry yang memetakan provider, base URL, API protocol, model ID, dan capability.
2. Validasi model ID terhadap provider yang dipilih.
3. Configuration validation saat startup dan saat model diubah.
4. Timeout terpisah untuk connect, read, dan total request.
5. Retry terbatas dengan exponential backoff dan jitter untuk error yang retryable.
6. Jangan retry tanpa batas untuk 400/401/403/404.
7. Circuit breaker atau mekanisme cooldown jika provider berkali-kali gagal.
8. Fallback hanya ke model yang telah diverifikasi tersedia dan cocok dengan capability tugas.
9. Catat primary provider, fallback reason, selected model, status code, latency, dan correlation ID.
10. Jangan catat API key, Authorization header, prompt privat, atau isi memory sensitif.
11. Jika semua provider gagal, berikan error yang jujur dan dapat dipahami, bukan jawaban palsu.
12. Streaming harus menangani partial output, disconnect, cancellation, dan timeout secara benar.

### 11.4 Classifier

- Verifikasi `AIRA_CLASSIFIER_MODEL` terhadap provider dan model catalog.
- Bedakan model ID provider-specific dari display name.
- Sediakan classifier fallback yang benar-benar teruji.
- Jika confidence rendah, gunakan fallback deterministic/rule-based atau label umum sesuai desain.
- Jangan menganggap confidence `0.50` sebagai hasil kuat.
- Log alasan model tidak tersedia tanpa secret.

### 11.5 Auto-memory

- Pastikan URL yang dipakai benar dan tidak terpotong dalam konfigurasi/log.
- Validasi DNS, TLS, HTTP status, timeout, dan autentikasi layanan.
- Jangan jadikan auto-extraction sebagai ketergantungan wajib untuk mengirim jawaban chat.
- Terapkan queue/retry terbatas jika desain sesuai.
- Pastikan memory write user-scoped dan terisolasi.
- Jangan menyimpan memory lintas-user ketika extraction gagal atau session ID tidak cocok.
- Tampilkan status “memory extraction failed/deferred” pada log internal, bukan mengklaim data tersimpan.
- Uji chat tetap berhasil ketika auto-memory service tidak tersedia.

### 11.6 Runtime state dan cancellation

- Pastikan setiap jalur sukses, gagal, timeout, dan cancellation menutup state dengan benar.
- Pastikan `cancel_event` milik satu request tidak membatalkan request user lain.
- Pastikan planner menghentikan task dan membersihkan resource.
- Simpan respons hanya jika status dan ownership valid.
- Buat E2E test untuk chat success, provider timeout, fallback success, fallback failure, user cancellation, disconnect, dan memory failure.

## 12. Keputusan BD-09 — Vision dan OCR harus menjadi subsystem yang benar-benar teruji

### 12.1 Tujuan

AIRA harus mampu:
- Memahami isi gambar melalui model Vision.
- Membaca teks yang ada pada gambar melalui OCR.
- Membaca screenshot terminal/configuration/dashboard.
- Membaca diagram dan tabel dengan mempertahankan urutan informasi sebisa mungkin.
- Mengambil teks dari scanned PDF jika text layer tidak tersedia.
- Menyatakan dengan jujur bila gambar buram, teks tidak terbaca, OCR engine gagal, atau format tidak didukung.

OCR dan Vision adalah dua kemampuan yang saling melengkapi:
- OCR menemukan teks dan posisi teks.
- Vision memahami konteks visual, objek, diagram, dan hubungan antarbagian.
- Hasil gabungan dapat membantu AIRA menjelaskan gambar dengan lebih lengkap.

### 12.2 Audit sebelum memilih teknologi

Jangan langsung menginstal library baru. Periksa:
- Vision routes dan service.
- Upload/attachment pipeline.
- Image validation.
- Existing OCR library/model.
- PDF text extraction dan PDF rendering.
- Vision provider integration.
- `VisionResult` model/constructor dan semua call site.
- Resource limits di VPS/container.
- CPU/RAM yang tersedia.
- Bahasa OCR yang tersedia.
- Dependency dan Docker image size.
- Apakah OCR diproses synchronous atau background worker.

Perbaiki terlebih dahulu bug `VisionResult` argument mismatch yang telah dilaporkan pada audit, jika masih ada di source saat ini.

### 12.3 Pipeline target

`Upload -> Validate -> Decode -> Preprocess -> OCR and/or Vision -> Normalize -> Merge Context -> Response`

**Input validation**
- Validasi MIME type dan magic bytes, bukan hanya file extension.
- Batasi file size, dimensi gambar, jumlah halaman PDF, dan total pixel.
- Tolak file corrupt/unsupported dengan error yang jelas.
- Lindungi dari decompression bomb, path traversal, dan nama file berbahaya.
- Jangan membuka arbitrary server path dari user input.

**Preprocessing**
- Correct image orientation.
- Resize sesuai batas model/engine.
- Grayscale/contrast/denoise hanya bila membantu; jangan merusak gambar.
- Deskew/rotation detection bila didukung.
- Simpan koordinat bounding box dengan transformasi yang benar.
- Hindari preprocessing berlebihan yang menghilangkan karakter kecil.

**OCR**
- Gunakan engine yang memang tersedia/layak untuk environment AIRA.
- Verifikasi language packs untuk Indonesia dan English sesuai kebutuhan.
- Simpan teks, confidence, page number, bounding boxes, dan urutan blok.
- Tangani hasil kosong, parsial, low-confidence, dan error secara berbeda.
- Jangan menyatakan “berhasil membaca” jika hasil hanya tebakan model.

**PDF**
- Coba ekstraksi text layer lebih dahulu.
- Jalankan OCR pada halaman yang berupa scan atau text layer kosong/tidak memadai.
- Batasi halaman, resolusi render, ukuran file, waktu proses, dan memory.
- Pertahankan page number dan urutan teks.

**Vision**
- Gunakan Vision untuk konteks visual yang tidak dapat dijelaskan OCR, misalnya objek, ikon, diagram, layout, relasi antarbagian.
- Jangan memaksa OCR untuk gambar tanpa teks.
- Gabungkan hasil OCR dan Vision dengan provenance: informasi mana berasal dari OCR dan mana dari deskripsi visual.

**Result contract**
Setiap proses harus mengembalikan status terstruktur seperti:
- `success`
- `partial`
- `no_text_detected`
- `unsupported_format`
- `input_rejected`
- `engine_unavailable`
- `timeout`
- `failed`

Sertakan metadata yang aman: engine, bahasa, halaman, confidence, durasi, dan error code. Jangan memasukkan data sensitif ke log.

### 12.4 Dataset dan test OCR wajib

Buat fixture lokal tanpa data pribadi/rahasia:
1. Gambar teks Indonesia yang jelas.
2. Gambar teks English yang jelas.
3. Screenshot terminal dengan command dan output.
4. Screenshot konfigurasi jaringan dengan IP/subnet/VLAN.
5. Tabel.
6. Diagram jaringan dengan label.
7. Gambar berotasi.
8. Gambar low contrast atau sedikit blur.
9. Gambar tanpa teks.
10. Gambar corrupt.
11. Scanned PDF.
12. PDF yang sudah memiliki text layer.

Untuk fixture dengan ground truth:
- Bandingkan hasil terhadap teks yang diharapkan.
- Ukur Character Error Rate (CER) atau Word Error Rate (WER) bila cocok.
- Tetapkan baseline dan threshold yang realistis berdasarkan fixture dan hardware.
- Pisahkan kegagalan engine dengan kesalahan pembacaan karena kualitas gambar.

Acceptance criteria:
- OCR dapat membaca fixture teks jelas dengan hasil sesuai threshold yang disepakati.
- Nomor IP, subnet, interface, VLAN ID, dan angka tidak dinormalisasi secara salah.
- Page number dan urutan blok benar.
- Gambar tanpa teks tidak dianggap OCR failure yang fatal.
- File corrupt/oversized ditolak secara aman.
- OCR engine unavailable menghasilkan pesan jelas.
- Vision dan OCR tidak saling menggandakan teks secara tidak masuk akal.
- Frontend menampilkan hasil, status, dan error dengan benar.
- Test berjalan di environment CI yang realistis tanpa perlu mengunduh model tidak terkendali.

## 13. Keputusan BD-10 — Traceroute harus berfungsi di environment backend yang sebenarnya

### 13.1 Temuan

Pengujian AIRA:
- Ping ke `8.8.8.8` berhasil: 10/10 packet received, 0% loss, RTT min/avg/max 13.558/13.710/14.002 ms, jitter 0.119 ms, TTL 115.
- Traceroute gagal dengan error: `No such file or directory: 'traceroute'`.

Interpretasi:
- Ping menunjukkan ICMP echo berhasil dari environment tempat ping itu dijalankan.
- Traceroute gagal karena executable `traceroute` tidak ditemukan oleh proses.
- Ini bukan bukti bahwa jaringan atau semua protokol traceroute diblokir.
- Ping tidak menunjukkan rute hop, sehingga tidak dapat menggantikan hasil traceroute sepenuhnya.

### 13.2 Implementasi wajib

1. Temukan tool runner/command registry yang sebenarnya dipakai AIRA.
2. Temukan fungsi traceroute dan seluruh call site.
3. Periksa environment proses backend (host, container, service path), bukan hanya laptop developer.
4. Gunakan `shutil.which()` atau mekanisme executable discovery yang sesuai.
5. Periksa tool yang didukung environment: `traceroute`, `tracepath`, atau `busybox traceroute` bila tersedia.
6. Sesuaikan instalasi package sistem dengan base image Docker yang benar. Jangan menulis perintah `apt-get` sebelum memastikan image berbasis Debian/Ubuntu.
7. Gunakan argument list subprocess, bukan `shell=True`.
8. Validasi target hostname/IP; batasi command options yang boleh diberikan.
9. Terapkan timeout, hop limit, probe limit, dan output size limit.
10. Parse output menjadi struktur hop: hop number, hostname/IP, RTT probe, timeout/`*`, dan status.
11. Bedakan error `binary_missing`, `permission_denied`, `dns_failed`, `timeout`, `network_unreachable`, `unsupported_mode`, dan `command_failed`.
12. Jika alternatif digunakan, laporkan metode yang benar-benar digunakan. Jangan menyebut output `tracepath` sebagai output `traceroute` tanpa label.
13. Jangan menghasilkan hop palsu ketika executable tidak ada.
14. Pastikan frontend menampilkan status, hop, RTT, timeout, dan error dengan benar.

### 13.3 Test traceroute wajib

Unit tests dengan mocked subprocess:
- Binary tersedia dan command sukses.
- Binary tidak tersedia.
- Output berisi beberapa hop.
- Hop timeout (`*`).
- DNS gagal.
- Permission error.
- Process timeout.
- Exit code non-zero.
- Target tidak valid.
- Input mengandung shell metacharacters.
- Parser menerima format output yang berbeda sesuai tool yang didukung.

Integration test:
- Jalankan dari container/backend environment yang benar bila network policy mengizinkan.
- Jika ICMP/UDP/TCP probe diblokir environment, hasil harus dinyatakan sebagai keterbatasan jaringan/probe, bukan kesalahan parser.
- Tidak perlu mengulang request jaringan yang tidak diperlukan.

## 14. Keputusan BD-11 — Polling dan UI tidak boleh menggandakan request

Log memperlihatkan `GET /api/connections` pada interval sekitar lima detik di beberapa rentang.

Audit dan perbaiki:
- Semua komponen yang melakukan polling connections.
- Polling interval dan visibility behavior.
- Duplicate fetch saat mount/re-render.
- Polling ketika tab tidak aktif.
- Cleanup timer ketika component unmount.
- Race condition antara fetch lama dan fetch baru.
- Cache invalidation.
- WebSocket versus polling.
- Request yang tidak diperlukan setelah event diterima.

Gunakan satu sumber polling/cache bersama jika arsitektur mendukung. Jangan memindahkan semua polling ke WebSocket tanpa memastikan server mendukung event dan reconnection yang benar.

Kriteria:
- Satu kebutuhan data tidak ditembak oleh beberapa poller identik.
- Polling berhenti saat tidak dibutuhkan.
- Error dan retry tidak membuat request storm.
- UI tetap memperbarui data.
- Test menghitung jumlah request pada periode tertentu.

---

# BAGIAN IV — CAKUPAN PERBAIKAN SELURUH AUDIT

## 15. Daftar kerja rekomendasi REC-01 sampai REC-26

Nomor REC tetap dipertahankan untuk melacak audit lama, tetapi REC-03 diganti sesuai keputusan penghapusan billing.

| ID | Fokus yang harus diselesaikan | Keputusan pelaksanaan |
|---|---|---|
| REC-01 | Authentication dan RBAC router + WebSocket | Wajib; susun matrix endpoint dan identitas |
| REC-02 | Privilege escalation dan RBAC bypass | Wajib; internal viewer tidak otomatis admin |
| REC-03 | Billing | **JANGAN implementasi judul lama; hapus seluruh sistem billing sesuai BD-01** |
| REC-04 | SQLite schema collision | Wajib; backup/restore gate sebelum migration |
| REC-05 | NAT rollback, config snapshot, SSH security | Wajib; jangan menghapus konfigurasi router yang tidak dibuat AIRA |
| REC-06 | Runtime crash Vision, intelligence, gateway | Wajib; perbaiki berdasarkan call site/test |
| REC-07 | NMS frontend crash dan API contract mismatch | Wajib; selaraskan endpoint dan response |
| REC-08 | Docker, dependency, `.dockerignore`, CI | Wajib sebelum test/build lanjutan |
| REC-09 | Isolasi private memory/persona/GPS | Wajib; user ownership backend enforced |
| REC-10 | Token quota dan plan catalogs | Pertahankan quota, lepaskan semua ketergantungan billing |
| REC-11 | Unifikasi device inventory/incidents/models | Wajib; SSOT per domain |
| REC-12 | Enkripsi secret at rest | Wajib; gunakan master key dari secret manager/env, rotasi dan migration aman |
| REC-13 | SQLite write-on-read contention/N+1 | Wajib; ukur sebelum/sesudah |
| REC-14 | Orphan pages, navigation, RBAC guards | Wajib; jangan hanya menambahkan menu, periksa route dan permission |
| REC-15 | NMS scheduler dan alert engine | Wajib; jalankan scheduler yang benar, bukan mock |
| REC-16 | Circular dependency/layer inversion | Wajib; core tidak mengimpor layer API/MCP/agent |
| REC-17 | URL routing frontend | Terapkan jika kompatibel; deep link dan back/forward dites |
| REC-18 | Stream batcher dan duplicate polling | Wajib; ukur request dan render |
| REC-19 | Simulated playbook/ZTP executor | Ganti simulasi dengan implementasi nyata hanya dengan approval, dry-run, dan lab device tests |
| REC-20 | Generational triplication network intelligence | Konsolidasi setelah behavior existing dipetakan |
| REC-21 | X-Forwarded-For dan SSRF | Wajib; hanya trusted proxy yang boleh mengatur client IP |
| REC-22 | FastAPI TestClient dan frontend tests | Wajib; auth, tenant, CRUD, error path |
| REC-23 | 42 unused/dead source candidates dan legacy backups | Hapus hanya setelah dynamic reference, runtime registration, import, dan build diverifikasi |
| REC-24 | Duplicate frontend components | Konsolidasi dengan visual/interaction regression tests |
| REC-25 | PWA cache dan lazy-load markdown renderers | Terapkan dengan offline/online, navigation, dan cache tests |
| REC-26 | SQLite Online Backup API dan retention pruning | Backup wajib sebelum migrations; retention pada tahap tersendiri |

Tambahan baru yang wajib:
- **NEW-01:** AI provider timeout, fallback 404, classifier model availability, dan auto-memory connectivity.
- **NEW-02:** Vision/OCR reliability dan fixture-based accuracy tests.
- **NEW-03:** Traceroute dependency discovery, structured parser, dan real container tests.
- **NEW-04:** Runtime log quality, request correlation, dan redaction.
- **NEW-05:** End-to-end chat reliability dan cancellation.
- **NEW-06:** Repeated `/api/connections` polling consolidation.

## 16. Backend — standar perbaikan

Untuk setiap endpoint:
- Method/path terdaftar hanya sekali kecuali ada alasan kompatibilitas.
- Authentication dan authorization diterapkan pada server.
- Input divalidasi dengan tipe/range/format yang tepat.
- Service logic tidak tersebar atau diduplikasi.
- Database access melalui layer yang sesuai.
- Transaction digunakan pada operasi multi-write.
- Error response konsisten dan tidak membocorkan stack/secret.
- Response schema cocok dengan frontend.
- Timeout dan cancellation ditangani.
- Logging memiliki correlation ID.

Periksa seluruh CRUD:
- Create benar-benar menyimpan.
- Read benar-benar membaca data authorized.
- Update mengubah record yang benar.
- Delete hanya menghapus data yang berhak dihapus dan memiliki audit/confirmation sesuai risiko.

## 17. Frontend — standar perbaikan

Audit seluruh halaman, route, button, form, table, modal, dropdown, tab, action menu, hook, state, dan API client.

Setiap tindakan yang ditampilkan harus:
- Memiliki handler nyata.
- Menggunakan endpoint yang benar.
- Mengirim payload yang benar.
- Menampilkan loading.
- Menampilkan success/failure.
- Menghindari double submit.
- Memperbarui state/cache setelah response.
- Menangani permission.
- Memiliki confirmation untuk operasi destruktif.

Konsolidasi komponen identik, tetapi jangan gabungkan dua UI yang tampak sama jika behavior/permission/ownership berbeda.

Selesaikan mismatch SSE/REST dengan contract tests. Jangan mengubah frontend hanya agar sesuai dengan response salah dari backend; tentukan kontrak API yang benar terlebih dahulu.

## 18. Database dan data centralization — standar perbaikan

Untuk setiap domain data, buat tabel:
- Domain.
- Authoritative store.
- Owner (user/organization/system/device).
- Read path.
- Write path.
- Cache.
- Retention.
- Migration.
- Tests.

Periksa bentrokan yang dilaporkan:
- `nms_raw_metrics` dari edge gateway versus NMS metrics.
- `nms_device_metrics` timestamp/polled_at.
- `operational_token_policies` nama kolom/created_at.
- obsolete `pol_global_guest` seed yang tidak sesuai CHECK constraint.
- Device inventory yang tersimpan di lebih dari satu store.
- Incident model yang terpecah.

Sebelum migration:
1. Online backup.
2. Integrity check.
3. Schema snapshot.
4. Migration rehearsal pada copy.
5. Data validation.
6. Foreign-key check.
7. Restore rehearsal.
8. Rollback plan.
9. Maintenance window untuk production.
10. Post-migration smoke/integration tests.

Jangan menjalankan migration pada database production dari test suite.

## 19. Security — standar perbaikan

Periksa:
- Unauthenticated command execution.
- Workspace file read/write/delete.
- Settings exposure/mutation.
- WebSocket access.
- Header spoofing (`X-User-ID`, `X-User-Role`, `X-Tenant-ID`).
- Guest bypass.
- Privilege escalation.
- IDOR dan tenant isolation.
- SSRF.
- Trusted proxy handling.
- SSH password fallback.
- Plaintext API keys/router credentials/MFA seed.
- Secret leakage in logs/build context/Git.
- Unsafe file upload.
- Command injection.
- CORS/session/token handling.
- Rate limits.

Gateway endpoints harus memisahkan identity:
- Enrollment: single-use enrollment token.
- Heartbeat/ingestion: gateway M2M credential/token hash.
- Operator portal management: user session + RBAC.

Jangan menaruh autentikasi user pada router-level dependency jika itu akan memblokir machine-to-machine endpoints. Terapkan dependency per endpoint sesuai identity type.

## 20. Network engineering — standar perbaikan

- Device inventory memiliki ownership organisasi yang jelas.
- Credential disimpan terenkripsi.
- SSH connection dibatasi ke device yang terdaftar dan authorized.
- RouterOS command execution tidak menerima raw command tanpa policy/authorization.
- NAT rollback hanya membatalkan rule yang dibuat oleh operation AIRA tersebut, bukan semua rule masquerade.
- Config snapshot harus mask secret.
- OS RouterOS v6/v7 capability dideteksi dan ditest.
- NMS scheduler mempunyai lifecycle dan cleanup.
- Monitoring data membedakan live, stale, simulated, dan unavailable.
- Alert hanya dibuat dari data yang dapat diverifikasi.
- ZTP/firmware/security playbook tidak boleh mengklaim sukses bila hanya menjalankan `asyncio.sleep()` atau mock.
- Operasi nyata ke router fisik harus memakai lab/staging, dry-run, explicit approval, rollback, dan maintenance window.

---

# BAGIAN V — URUTAN IMPLEMENTASI WAJIB

## 21. Strategi pengerjaan

Jangan mengerjakan seluruh source tree dalam satu giant edit. Kerjakan **seluruh scope** secara berurutan, dengan satu batch kecil yang selesai dan dites sebelum batch berikutnya.

Setiap batch harus mempunyai:
- Baseline.
- Daftar file yang akan diubah.
- Reason per file.
- Implementation.
- Tests.
- Regression checks.
- Git diff review.
- Checkpoint report.
- Rollback instructions.

Jika satu tahap gagal, perbaiki tahap tersebut sebelum meneruskan perubahan yang bergantung padanya.

## 22. Master execution stages

### STAGE 0 — Baseline protection and source verification
- Pastikan workspace dan commit cocok.
- Lindungi 13 modified files dan 2 untracked directories.
- Simpan baseline diff dan checksum.
- Buat branch kerja.
- Identifikasi database aktif dan backup aman.
- Jangan membersihkan working tree secara destruktif.

**Gate:** tidak ada pekerjaan pemilik yang hilang.

### STAGE 1 — Build, dependency, and CI foundation
- Perbaiki dependency manifests.
- Pastikan FastAPI/Uvicorn tersedia pada environment yang membutuhkannya.
- Perbaiki `Optional` import/type annotation.
- Perbaiki `npm test -- --run`.
- Pastikan Docker dan CI menggunakan dependency policy konsisten.
- Exclude database dan backup sensitif dari Docker build context.
- Untrack backup DB lama tanpa menghapus salinan lokal.
- Pisahkan core helper dari MCP layer inversion.
- Build dan test smoke.

**Gate:** Python test collection bersih, frontend test command valid, backend import, Docker build berhasil.

### STAGE 2 — Critical security and full billing removal
- Tutup command execution tanpa authorization.
- Proteksi file workspace.
- Proteksi settings.
- Amankan WebSocket chat/NMS.
- Terapkan privilege/RBAC correction.
- Hilangkan header spoofing.
- Hapus client-side guest auth bypass; implementasikan guest resmi atau nonaktifkan.
- Pisahkan user session dan gateway M2M.
- Perbaiki SSH credential fallback dan NAT rollback.
- Implementasikan seluruh penghapusan billing sesuai BD-01.
- Pastikan token quota tetap bekerja tanpa billing.
- Tambahkan tests negative/positive untuk semua identity type.

**Gate:** no unauthenticated sensitive operation; billing absent; gateway M2M masih berjalan; user/org isolation tests lulus.

### STAGE 3 — Secret security and database safety
- Online backup API.
- Restore tests.
- Secret vault/encryption.
- Key rotation/recovery policy.
- Encrypt credentials/API keys/MFA secrets.
- Audit Git history dan Docker exposure.
- Redact logs.

**Gate:** backup dapat direstore, data sensitif tidak plaintext pada store yang ditetapkan, kehilangan master key mempunyai recovery policy yang jelas.

### STAGE 4 — Database schema reconciliation and SSOT
- Reconcile SQLite schema collisions.
- Device inventory unification.
- Incident schema consistency.
- Token policy column naming.
- Remove obsolete guest seed only setelah memastikan replacement.
- Separate NMS time-series storage where justified.
- Migrations rehearsed on copy.
- Verify all domain ownership.

**Gate:** integrity, FK check, data counts/reconciliation, read/write tests, restore tests.

### STAGE 5 — User data, memory, persona, and quota
- User-scoped memory/persona/chat/GPS.
- Organization shared data.
- Guest stateless policy.
- Token quota check/deduction.
- Unify quota catalog independent of billing.
- Cross-user and cross-tenant negative tests.

**Gate:** no cross-user or cross-tenant data exposure in tests.

### STAGE 6 — Core backend functional bugs
- Fix all remaining confirmed/likely bugs by severity.
- Verify all call sites and contracts.
- Fix API endpoint shadowing/duplicate mounting.
- Fix controller/service/async/database errors.
- Fix VisionResult constructor mismatch if still present.
- Fix edge gateway timestamp/ping flags.
- Fix network intelligence attribute/type mismatch.
- Track each BUG ID to test ID.

**Gate:** no open P0/P1 confirmed bugs; remaining findings have explicit acceptance/waiver.

### STAGE 7 — AI runtime and provider reliability
- Provider configuration/model validation.
- NVIDIA timeout handling.
- Investigate fallback model 404.
- Validate classifier model availability.
- Add verified classifier fallback.
- Auto-memory external endpoint and resilient queue/retry.
- Chat stream correctness.
- Runtime state/cancellation handling.
- Logging/correlation.

**Gate:** primary failure + fallback success, all-provider failure, auto-memory failure, and cancellation tests produce correct states and honest UI.

### STAGE 8 — Vision and OCR
- Audit existing pipeline and dependency.
- Fix runtime constructor/schema issues.
- Implement or repair OCR and PDF path.
- Combine OCR and Vision appropriately.
- Add fixture dataset and CER/WER checks.
- Validate output and resource limits.
- Verify UI upload/result/error state.

**Gate:** OCR/vision acceptance tests pass within measured hardware limits.

### STAGE 9 — Network tools, NMS, and traceroute
- Fix traceroute executable discovery/installation.
- Structured parsing and error categories.
- Ping/traceroute tool contract.
- NMS scheduler/alert integration.
- Network discovery/inventory.
- Simulated executor review.
- Real RouterOS actions only with explicit safety approval and lab tests.

**Gate:** traceroute reports real hops or honest environment error; NMS status is source-labeled; no unsafe real-device operation in CI.

### STAGE 10 — Frontend integration, UX, and routing
- Fix all endpoint/response mismatches.
- Fix NmsPage and related page crashes.
- Orphan pages and route/nav integration.
- URL routing if adopted.
- Design system/theme consolidation.
- Duplicate component groups.
- Disabled/dead buttons.
- Loading/error/empty states.
- SSE streaming parser and frontend/backend contract tests.

**Gate:** all user-visible actions have verified behavior and correct authorization.

### STAGE 11 — Network intelligence and simulated feature replacement
- Consolidate overlapping intelligence generations.
- Connect scheduler and alert engine.
- Replace fake/synthetic executors only where a safe real implementation is available.
- Add dry-run and approval for destructive operations.
- Add equipment-version compatibility tests.

**Gate:** no feature reports a simulated result as real execution.

### STAGE 12 — Dead code, duplicates, and maintainability
- Revalidate 42 unused candidates.
- Revalidate legacy backups.
- Check dynamic imports, plugin registration, CLI entry points, framework discovery.
- Remove only high-confidence unused code.
- Consolidate repeated services/hooks/components.
- Update references/docs/tests.

**Gate:** build, imports, route registry, test suite, and runtime smoke pass after cleanup.

### STAGE 13 — Performance
- Fix write-on-read SQLite contention.
- Optimize `score_tenant()` request writes.
- Remove duplicate polling.
- N+1 and index analysis.
- Stream token batching.
- Lazy-load heavy markdown renderers.
- PWA cache strategy.
- Benchmark before and after.

**Gate:** measurable improvement and no correctness regression.

### STAGE 14 — Full test and production-readiness verification
- Unit, integration, API, auth/RBAC, database, WebSocket, Vision/OCR, network tool, frontend component, and E2E tests.
- Docker clean build.
- CI on exact commit.
- Security regression.
- Backup/restore drill.
- Monitoring/logging/health checks.
- Deployment staging rehearsal.
- Update docs and operational runbook.

**Gate:** readiness report with evidence and all residual risks listed.

---

# BAGIAN VI — TESTING DAN DEFINISI SELESAI

## 23. Wajib ada test matrix

| Area | Minimal verifikasi |
|---|---|
| Python dependency | import dan test collection bersih |
| Backend | unit, service, API contract |
| Frontend | `npm test`, build, component behavior |
| Auth/RBAC | allow, deny, expired, revoked, wrong tenant |
| WebSocket | unauthenticated reject, authorized connection, disconnect/cancel |
| M2M gateway | enroll, heartbeat, ingest, revoke |
| Billing removal | route/UI/service/schema tidak aktif |
| Database | migration rehearsal, integrity, FK, backup/restore |
| Memory | private user isolation |
| Organization | shared data tenant isolation |
| AI provider | timeout, 404, valid fallback, total failure |
| Auto-memory | success, unavailable, retry/deferred |
| Vision/OCR | fixture accuracy, corrupt input, no text, PDF scan |
| Traceroute | binary missing, parse hops, timeout, invalid target |
| NMS | real/stale/unavailable distinction |
| RouterOS | mock/lab, dry-run, rollback isolation |
| Security | command auth, file auth, secret redaction |
| Performance | request rate, DB lock, latency before/after |
| Docker/CI | exact clean build and pipeline |

## 24. Definisi “Done”

Pekerjaan baru boleh dinyatakan selesai apabila:

1. Semua rekomendasi audit mempunyai status: fixed, not applicable with evidence, deferred with owner/reason, atau accepted risk.
2. Semua 62 fitur diperbarui statusnya berdasarkan implementasi dan test terbaru.
3. Semua 45 bug fungsional direkonsiliasi terhadap code terbaru.
4. Semua 28 temuan security direkonsiliasi dan diuji.
5. REC-03 lama ditandai superseded dan full billing removal selesai.
6. Tidak ada route billing/payment yang aktif.
7. Python test collection berhasil.
8. Frontend test command berhasil.
9. CI lulus pada commit yang sama dengan hasil final.
10. Docker image build dari clean context.
11. Test database migration dan restore lulus.
12. Private memory dan organization data isolation lulus.
13. Provider fallback tidak lagi mengarah ke model/endpoint yang tidak valid.
14. OCR mempunyai evidence dari fixture, bukan hanya klaim “OCR berjalan”.
15. Traceroute benar-benar menemukan executable di runtime atau mengembalikan error yang tepat dan terdokumentasi.
16. Semua operasi jaringan yang berisiko mempunyai approval/dry-run/rollback.
17. Dead code hanya dihapus setelah verifikasi.
18. Perubahan pada working tree awal tetap dipertahankan atau dipadukan dengan sengaja.
19. Semua residual risk dicatat.
20. Tidak ada klaim “100% perfect”; laporan menyatakan batas pengujian secara jujur.

---

# BAGIAN VII — PANDUAN MEMAHAMI ISTILAH TEKNIS

## 25. Glosarium singkat untuk siswa SMK

- **Repository:** seluruh folder dan file source project.
- **Backend:** bagian server yang menjalankan business logic dan API.
- **Frontend:** tampilan dan interaksi yang digunakan user.
- **API:** jalur komunikasi antara frontend, backend, atau service lain.
- **Endpoint:** alamat API tertentu, misalnya `POST /api/connections/execute`.
- **Dependency:** library/package yang dibutuhkan agar program berjalan.
- **CI:** proses otomatis untuk menjalankan test/build saat ada perubahan kode.
- **Docker image:** paket aplikasi beserta runtime/dependency untuk dijalankan dalam container.
- **Database schema:** rancangan tabel, kolom, index, dan relasi.
- **Migration:** perubahan schema/data database yang dilakukan secara terkontrol.
- **SSOT:** sumber data resmi yang menjadi acuan utama.
- **RBAC:** akses berdasarkan role dan permission.
- **Tenant isolation:** pemisahan data antara organisasi/tenant.
- **WebSocket:** koneksi dua arah yang tetap terbuka untuk komunikasi real-time.
- **SSE:** server mengirim event/teks secara streaming melalui HTTP.
- **OCR:** teknologi untuk membaca tulisan dalam gambar.
- **Vision model:** AI yang memahami isi gambar, objek, dan konteks visual.
- **Traceroute:** tool untuk memeriksa jalur hop jaringan menuju tujuan.
- **RTT:** waktu pergi-pulang paket.
- **Packet loss:** persentase paket yang tidak mendapat balasan.
- **Fallback:** pilihan cadangan ketika provider/model utama gagal.
- **Circuit breaker:** mekanisme sementara menghentikan request ke layanan yang terus gagal agar sistem tidak membebani diri sendiri.
- **Dead code:** kode yang tidak lagi digunakan setelah seluruh cara pemanggilannya diperiksa.
- **Regression test:** test untuk memastikan perbaikan baru tidak merusak fitur lama.
- **Rollback:** cara mengembalikan kondisi sebelumnya ketika perubahan gagal.
- **Acceptance criteria:** syarat terukur yang harus dipenuhi sebelum pekerjaan dinyatakan selesai.

---

# BAGIAN X — KEPUTUSAN AKHIR

## 29. Keputusan proyek

AIRA akan diperbaiki berdasarkan prinsip berikut:

1. Pertahankan identitas dan fungsi utama AIRA sebagai AI Network Engineering Assistant.
2. Pertahankan pemisahan private user data dan organization shared data.
3. Pertahankan token quota dan model governance, tetapi lepaskan dari billing.
4. Hapus sistem billing sepenuhnya.
5. Perbaiki seluruh bug yang dapat dibuktikan.
6. Selesaikan autentikasi, authorization, dan tenant isolation.
7. Jadikan database sumber kebenaran untuk data operasional dinamis.
8. Pastikan Vision/OCR dapat diuji dengan ground truth.
9. Pastikan traceroute berjalan di environment backend yang sebenarnya.
10. Pastikan AI provider failure tidak merusak keseluruhan pengalaman chat.
11. Hilangkan duplikasi dan dead code hanya setelah verifikasi.
12. Pertahankan seluruh perubahan pengguna yang telah ada.
13. Setiap tahap wajib lulus test sebelum melanjutkan.
14. Tidak boleh ada klaim selesai tanpa bukti.

**Definisi keberhasilan AIRA bukan jumlah file yang diubah. Keberhasilan AIRA adalah setiap fitur yang dipertahankan benar-benar berfungsi, data tidak tertukar, operasi jaringan aman, dan seluruh hasil dapat diverifikasi.**

---

**END OF MASTER DECISION DOCUMENT**
