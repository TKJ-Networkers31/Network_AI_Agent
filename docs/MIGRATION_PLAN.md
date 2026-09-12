<!--
ARCHIVED — this document is historical, not authoritative.
Original location: AIRA_ECOSYSTEM/MIGRATION_PLAN.md
Reason: the migration it describes (legacy agent/tools/backend -> AIRA_ECOSYSTEM/)
is complete. Kept here for context on why the current folder boundaries
(see docs/architecture.md) exist. Do not treat anything below as current
instructions — see docs/roadmap.md for what is actually pending.
-->

# Migration Plan: repo lama -> struktur AIRA Ecosystem

Refactor IN-PLACE di repo `D:\data\agent_ai\` yang sama (bukan repo baru).
Karena file-file lama sudah di-track git, WAJIB pakai `git mv` (bukan copy
manual) supaya history tetap nyambung. Kalau ada file yang belum ter-track,
`git add` dulu sebelum `git mv` (lihat catatan lama kamu soal ini).

## Tahap 0 — Skeleton (SELESAI di paket ini)
Folder `AIRA_ECOSYSTEM/{core,agents,api,app,tools,database}` + file skeleton
sudah dibuat.

## Tahap 1 — Frontend -> app/
```
git mv frontend AIRA_ECOSYSTEM/app
```

## Tahap 2 — Backend -> api/
```
git mv backend/main.py         AIRA_ECOSYSTEM/api/main.py
git mv backend/routers         AIRA_ECOSYSTEM/api/routers
git mv backend/schemas.py      AIRA_ECOSYSTEM/api/schemas.py
git mv backend/state.py        AIRA_ECOSYSTEM/api/state.py
```

## Tahap 3 — Tools network -> agents/akane/
```
git mv tools/ssh        AIRA_ECOSYSTEM/tools/ssh
git mv tools/snmp       AIRA_ECOSYSTEM/tools/snmp
git mv tools/mikrotik   AIRA_ECOSYSTEM/tools/mikrotik
git mv tools/network    AIRA_ECOSYSTEM/tools/network
git mv tools/inventory.py AIRA_ECOSYSTEM/tools/inventory.py
```

## Tahap 4 — Vision -> agents/hikari/, Voice -> agents/yuki/
```
git mv tools/vision            AIRA_ECOSYSTEM/tools/vision
git mv agent/voice/stt.py      AIRA_ECOSYSTEM/agents/yuki/stt_engine.py
git mv agent/voice/tts.py      AIRA_ECOSYSTEM/agents/yuki/tts_engine.py
git mv agent/voice/voice_io.py AIRA_ECOSYSTEM/agents/yuki/voice_io.py
git mv agent/core/multimodal.py AIRA_ECOSYSTEM/agents/hikari/fusion.py
```

## Tahap 5 — Providers -> agents/rei/, Engine -> core/
```
git mv agent/core/providers.py AIRA_ECOSYSTEM/agents/rei/provider_client.py
git mv agent/core/engine.py    (logic dipecah ke core/orchestrator.py + agents/rei/planner.py)
git mv agent/core/engine_web.py (dihapus setelah orchestrator.py menggantikan keduanya)
git mv agent/core/memory.py    AIRA_ECOSYSTEM/core/memory.py (digabung dgn agent/memory_store/*)
git mv agent/memory_store      AIRA_ECOSYSTEM/database/  (isi .db pindah ke sini, kode akses tetap di core/memory.py)
git mv data                    AIRA_ECOSYSTEM/database/data
```

## Tahap 6 — Cleanup
Hapus `agent/` dan `backend/` dan `tools/registry.py` versi lama setelah semua
import di atas sudah dipindah dan aplikasi jalan normal.

## Import alias sementara (opsional)
`agent/core/engine.py` bisa sementara jadi thin-wrapper yang import dari
`AIRA_ECOSYSTEM.core.orchestrator` sampai semua caller lama dipindah.
