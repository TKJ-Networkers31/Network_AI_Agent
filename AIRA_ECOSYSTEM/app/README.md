# app/

PWA frontend AIRA. Ini adalah `frontend/` lama, dipindah 1:1 tanpa ubah
logic (React + Vite + Tailwind tetap dipakai) — cuma folder-nya di-rename
jadi `app/` sesuai struktur AIRA Ecosystem.

TODO migrasi (Tahap 1):
    git mv frontend AIRA_ECOSYSTEM/app

Setelah dipindah, cek `vite.config.js` (proxy `/api` ke `http://127.0.0.1:8000`
tetap valid karena backend juga sudah pindah ke `api/main.py` di port yang
sama) dan `package.json` scripts tidak perlu berubah.

Aturan: `app/` hanya boleh render UI + panggil endpoint REST/WebSocket di
`api/`. Tidak ada logic besar (parsing tool result kompleks, keputusan
bisnis) di sisi frontend — itu tanggung jawab `core/brain.py`.
