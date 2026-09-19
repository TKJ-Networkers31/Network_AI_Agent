# Development Guide

## Prerequisites

- Python 3.11+ with a virtualenv
- Node.js (for `app/frontend/`)
- Ollama running locally if you intend to use a local model
  (`qwen3:1.7b` or `qwen3:4b`)
- An OpenRouter API key if you intend to use a hosted free-tier model

## Environment variables (`.env`)

Loaded from repo root **and** `AIRA_ECOSYSTEM/.env` (root loads first,
`AIRA_ECOSYSTEM/.env` does not override existing values):

| Variable | Required | Used by |
|---|---|---|
| `SSH_PASSWORD` | Yes, for any MikroTik tool | `tools/ssh/client.py` |
| `OPENROUTER_API` | Only if using an OpenRouter provider | `agents/rei/provider_client.py` |
| `SNMP_COMMUNITY` | No (defaults to `public`) | `tools/snmp/client.py` |
| `GOOGLE_CSE_API_KEY` | No — enables Google Images in `web_image_search` | `tools/web/search.py` |
| `GOOGLE_CSE_ID` | No — Programmable Search Engine ID (image search enabled), pair with the key above | `tools/web/search.py` |

Without the two `GOOGLE_CSE_*` variables, `web_image_search` transparently
uses DuckDuckGo Images. If Google is configured but errors or returns
nothing, it also falls back to DuckDuckGo.

## Backend

```bash
cd AIRA_ECOSYSTEM
pip install -r ../requirements.txt
uvicorn api.main:app --reload --port 8000
```

Terminal-only smoke test (no HTTP server, no frontend needed):

```bash
python run_chat.py
```

## Frontend

```bash
cd AIRA_ECOSYSTEM/app/frontend
npm install
npm run dev       # http://localhost:5173, proxies /api to :8000
npm run build     # outputs dist/, served automatically by FastAPI
```

## Adding a new tool

1. Implement the low-level client in the correct `tools/` subfolder
   (never add reasoning logic there).
2. Add a thin wrapper function in the owning agent's module
   (`agents/<agent>/*_tools.py` or `vision.py` / `research_tools.py`).
3. Register it in that agent's `registry.py`:
   - add to `<AGENT>_TOOLS` (name -> callable)
   - add to `<AGENT>_TOOL_CATEGORY` (name -> UI category label)
   - add a schema entry to `<AGENT>_TOOL_SCHEMAS` (OpenAI function-calling format)
   - if it mutates state, add its name to `<AGENT>_DANGEROUS_TOOLS`
4. Do **not** touch `core/orchestrator.py` — it auto-aggregates every
   agent's registry.
5. Write the schema `description` defensively: if a new tool could be
   confused with an existing one (see the `traceroute` vs `get_routes`
   fix in `agents/akane/registry.py`), cross-reference them explicitly in
   both descriptions.
6. If the model must know *how to present* the result (e.g. images), add
   a rule to `core/persona/prompt_builder.py` — a tool the model has no
   instructions for is effectively invisible.

## Adding a new agent

Only do this for a genuinely new domain (not a variant of an existing
one). An agent needs: its own folder under `agents/`, a `registry.py`
following the `<AGENT>_TOOLS` / `_TOOL_CATEGORY` / `_TOOL_SCHEMAS` /
`_DANGEROUS_TOOLS` naming convention, and an entry merged into
`core/orchestrator.py`'s aggregation. It must never import another
agent's internals directly — inject callbacks from `core/` instead (see
how HIKARI's fusion callback is wired into YUKI's `VoiceIO`).

## Logging conventions

Use `core/logger.py::get_logger("<category>")` and, where duration/success
matter, `log_event(logger, level, message, category=..., context=..., duration_ms=..., success=...)`
instead of raw `logging.getLogger(...).info(...)`. This ensures the entry
is queryable from `/api/logs` with structured filters instead of being
plain text.

## Known constraints / gotchas

- `call_model()` in `provider_client.py` resolves models through the Model
  Router (`core/model_router.py`, `core/model_store.py`); provider names are
  validated against `VALID_PROVIDERS` in `core/model_types.py` — never add a
  provider without updating that tuple and the adapters in `provider_client.py`.
- Every tool result **must** be JSON-serializable — it's stored as-is in
  `chat_sessions.db` and streamed over WebSocket.
- Windows has no native `traceroute` binary; `tools/network/diagnostics.py`
  shells out to `tracert` on Windows, `traceroute` elsewhere, and captures
  partial output on timeout rather than discarding it.