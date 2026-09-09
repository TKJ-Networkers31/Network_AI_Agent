# api/routers/

TODO (Tahap 2 migrasi): pindahkan isi `backend/routers/*.py` ke sini,
dengan perubahan berikut per file:

- `chat.py`      -> panggil `core.brain.Brain(memory).think(message)`,
                    BUKAN `agent.core.engine_web.run_web(...)` lagi.
- `devices.py`   -> panggil `agents.akane.network_tools.list_devices()`,
                    BUKAN `tools.inventory.list_devices()` langsung.
- `memory.py`    -> panggil fungsi di `core.memory` (facts/events),
                    BUKAN `agent.memory_store.long_term` langsung.
- `providers.py` -> panggil `agents.rei.provider_client`, BUKAN
                    `agent.core.providers` langsung.
- `sessions.py`  -> panggil helper sesi chat di `core.memory` (setelah
                    chat_sessions.py dipindah ke sana).
- `tools.py`     -> baca skema dari `core.orchestrator.AGENT_TOOL_MAP` +
                    `agents/*/registry.py`, bukan `agent.core.engine.TOOLS`.

Tambahkan `ws.py` baru untuk WebSocket streaming step tool-call (belum ada
di backend/routers/ lama - REST only).
