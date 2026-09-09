# AIRA Ecosystem

**One Intelligence. Multiple Specialists.**

Pengguna hanya berinteraksi dengan **AIRA** (Adaptive Intelligent Reasoning
Assistant). Semua kemampuan spesifik (network, vision, voice, reasoning)
dikerjakan oleh internal agent yang TIDAK berbicara langsung ke user:

| Agent  | Nama Lengkap                                          | Domain                                   |
|--------|--------------------------------------------------------|-------------------------------------------|
| AKANE  | Adaptive Knowledge & Autonomous Network Engine          | SSH, SNMP, MikroTik, Cisco, Linux, monitoring |
| REI    | Reasoning & Executive Intelligence                      | Planning, tool selection, multi-step reasoning, report generation |
| HIKARI | Hybrid Intelligent Knowledge & Augmented Recognition    | YOLO, OCR, screenshot/camera/diagram understanding |
| YUKI   | Your Unified Knowledge Interface                        | Whisper (STT), Kokoro (TTS), wake word, voice pipeline |

## Flow

```
User -> AIRA -> Detect Intent -> REI (Planning) -> Agent yang diperlukan -> AIRA -> User
```

Contoh: "Cek interface R1" => AIRA -> REI -> AKANE -> AIRA -> User

## Struktur

```
AIRA_ECOSYSTEM/
├── app/            # PWA frontend (eks frontend/)
├── api/            # FastAPI + WebSocket (eks backend/)
├── core/           # brain, orchestrator, memory, persona, scheduler
├── agents/         # akane, rei, hikari, yuki (internal, tidak bicara ke user)
├── tools/          # low-level utility (ssh client, snmp client, dsb) - dipanggil HANYA oleh agents/
├── database/       # SQLite (satu-satunya storage)
├── inventory/      # router.yaml, device inventory
└── logs/
```

## Aturan Keras (jangan dilanggar)

- Jangan membuat chatbot kedua selain AIRA — semua agent internal, balasan akhir selalu lewat `core/brain.py`.
- Jangan memanggil OpenRouter/Ollama langsung dari `tools/` atau `agents/akane|hikari|yuki` — HANYA `agents/rei/provider_client.py` yang boleh.
- Jangan mencampur SSH dengan UI — `api/` tidak boleh import `tools/ssh` langsung, harus lewat `agents/akane`.
- Jangan menyimpan memory di file JSON — semua lewat `core/memory.py` (SQLite, di `database/`).
- Jangan membuat logic besar di frontend (`app/`) — cuma render + panggil `api/`.

Lihat `MIGRATION_PLAN.md` untuk pemetaan file lama -> baru.
