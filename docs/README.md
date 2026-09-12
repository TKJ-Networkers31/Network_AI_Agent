# AIRA OS

**One Intelligence. Multiple Specialists.**

AIRA (Adaptive Intelligent Reasoning Assistant) is a modular, multi-agent AI
system for network operations, built around a single public-facing
assistant backed by internal specialist agents. The user never talks to
"AKANE" or "REI" directly — they talk to AIRA, and AIRA quietly delegates
work to the right specialist.

## What is AIRA OS?

AIRA OS is a self-hosted assistant that can:

- Monitor and diagnose network devices (MikroTik RouterOS, SSH, SNMP)
- Search the web and summarize current information
- See through a webcam (object detection)
- Listen and speak (offline STT/TTS)
- Remember facts across sessions (long-term memory)
- Stream its reasoning live to a PWA frontend over WebSocket

It runs entirely on local hardware, using either a local LLM (Ollama) or a
free-tier hosted model (OpenRouter) as its reasoning engine.

## Philosophy

- **One face, many specialists.** The person interacts with a single
  assistant identity (AIRA). Internal agents do the work but never
  self-identify to the user.
- **Strict boundaries.** Each internal agent owns a domain and is the only
  caller allowed to touch its underlying low-level tools (see
  [`docs/architecture.md`](docs/architecture.md)).
- **SQLite only.** No JSON files, no external database. Everything
  persistent lives in `database/*.db`.
- **Documentation lives in one place.** See [`docs/`](docs/) — this file is
  the entry point, not the source of truth for internals.

## Project Structure

```
AIRA_ECOSYSTEM/
├── app/            # PWA frontend (React + Vite + Tailwind)
├── api/            # FastAPI app: REST routers + WebSocket
├── core/           # brain, orchestrator, memory, persona, logging
├── agents/         # akane, rei, hikari, yuki (internal specialists)
├── tools/          # low-level clients (ssh, snmp, mikrotik, vision, web)
├── database/       # SQLite files + vision snapshots (only persistence layer)
├── inventory/      # router.yaml device inventory
├── docs/           # ← all official documentation lives here
└── logs/           # structured logs (console + file + SQLite)
```

## Agent Architecture (short version)

```
User -> AIRA -> REI (planning/reasoning) -> AKANE / HIKARI / REI-tools -> AIRA -> User
```

| Agent  | Full name                                             | Domain |
|--------|--------------------------------------------------------|--------|
| AKANE  | Adaptive Knowledge & Autonomous Network Engine          | SSH, SNMP, MikroTik, network diagnostics |
| REI    | Reasoning & Executive Intelligence                      | LLM planning, tool orchestration, web research, memory |
| HIKARI | Hybrid Intelligent Knowledge & Augmented Recognition    | Webcam / object detection (vision) |
| YUKI   | Your Unified Knowledge Interface                        | Speech-to-text, text-to-speech, voice pipeline |

Full details: [`docs/agents.md`](docs/agents.md) and
[`docs/architecture.md`](docs/architecture.md).

## Running the Backend

```bash
cd AIRA_ECOSYSTEM
pip install -r ../requirements.txt
uvicorn api.main:app --reload --port 8000
```

Requires a `.env` file (root or `AIRA_ECOSYSTEM/`) with at least:

```
SSH_PASSWORD=...
OPENROUTER_API=...        # only needed if using an OpenRouter model
SNMP_COMMUNITY=public     # optional, defaults to "public"
```

Terminal-only test mode (no web server needed):

```bash
python run_chat.py
```

## Running the Frontend

```bash
cd AIRA_ECOSYSTEM/app/frontend
npm install
npm run dev
```

Dev server proxies `/api` to `http://127.0.0.1:8000`. For production, run
`npm run build` — FastAPI serves the resulting `dist/` automatically.

## Roadmap (short version)

Full roadmap: [`docs/roadmap.md`](docs/roadmap.md).

- ✅ Phase 0 — Stabilization (provider error handling, memory/token tracking, tool registries)
- ✅ Phase 0.5 — Realtime WebSocket streaming for chat
- ✅ Structured logging (console + rotating files + SQLite + `/api/logs`)
- 🚧 `recognize_object` (HIKARI) — not yet implemented
- 🚧 `core/scheduler.py` — background polling/alerts — not yet implemented
- 🚧 Event Bus formalization between core and agents (see
  [`docs/constitution.md`](docs/constitution.md))

## License

Not yet specified. Treat as internal/private until a license file is added.

---

For contribution guidelines, coding conventions, and environment setup
details, see [`docs/development.md`](docs/development.md). For the binding
rules of this project, see [`docs/constitution.md`](docs/constitution.md).
