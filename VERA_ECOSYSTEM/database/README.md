# database/

Satu-satunya lokasi penyimpanan persistent AIRA (SQLite only, sesuai
master prompt - "SQLite adalah satu-satunya database").

TODO migrasi (Tahap 5):
    git mv data/long_term_memory.db  database/long_term_memory.db
    git mv data/chat_sessions.db     database/chat_sessions.db
    git mv data/vision_snapshots     database/vision_snapshots   # (bukan SQLite, tapi file blob hasil snapshot - taruh di sini juga biar satu tempat)

Kode akses (init_db, remember_fact, dsb) tinggal di `core/memory.py`,
BUKAN lagi di `agent/memory_store/*.py`.
