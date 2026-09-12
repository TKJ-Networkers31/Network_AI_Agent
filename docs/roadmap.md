# Roadmap

This is the **only** official roadmap for AIRA OS. `MIGRATION_PLAN.md` has
been archived (see [`archive/MIGRATION_PLAN.md`](archive/MIGRATION_PLAN.md))
because the migration it describes (legacy `agent/`/`tools/`/`backend/` ->
`AIRA_ECOSYSTEM/`) is complete, evidenced by `consolidate_to_aira.ps1`
having already run and the legacy tree existing only under
`_legacy_backup_*/`.

## Done

- **Migration to `AIRA_ECOSYSTEM/`** — legacy flat structure fully
  consolidated into the layered `app/api/core/agents/tools/database` model.
- **Phase 0 — Stabilization**
  - `provider_client.py`: explicit provider-type whitelist, JSON decode
    error handling on both Ollama and OpenRouter paths, `tool_calls`
    always normalized to a list
  - `TokenTracker` restored per-session (was dropped in an earlier pass)
  - `auto_extract.py`: skips extraction when the turn's answer is the
    empty-response marker, avoiding wasted provider calls and log noise
  - `traceroute` vs `get_routes` schema disambiguation to stop the
    planner mixing up external traceroute with internal routing tables
  - `traceroute` diagnostic: capped hop count, disabled reverse-DNS,
    captures partial output on timeout instead of discarding it
- **Phase 0.5 — Realtime WebSocket streaming** (`/ws/chat/{session_id}`),
  running the same `Brain.think()` as REST, with live `thinking` /
  `tool_start` / `tool_finish` events
- **Structured logging** — console + rotating file + per-category file +
  SQLite (`logs.db`), queryable via `/api/logs` and rendered in the PWA's
  Logs page

## In progress / known gaps

- `agents/hikari/vision.py::recognize_object` — schema exists, always
  returns "not implemented." Not a regression; it was never implemented
  even in the legacy system.
- `core/scheduler.py` — background/periodic job runner is a stub
  (`start()`/`stop()` raise `NotImplementedError`). Intended for periodic
  MikroTik polling + anomaly events into `core.memory.log_event()`.
- **Event Bus** — `constitution.md` states that inter-module communication
  should go through an event bus. Today this is approximated by the
  Orchestrator's direct calls plus the WebSocket `on_event` callback
  mechanism. Formalizing a real internal event bus (so agents can publish
  events without the orchestrator manually wiring every callback) is not
  yet done.

## Next steps (proposed, not yet scheduled)

1. Implement `core/scheduler.py` and wire it to AKANE for periodic device
   polling + threshold alerts (`long_term_memory.db.events`).
2. Implement `recognize_object` in HIKARI, or remove the schema if it
   will not be built, to avoid an always-failing tool being offered to
   the planner.
3. Introduce a minimal internal event bus so HIKARI/YUKI fusion and
   future scheduler events don't need to be manually threaded through
   `core/orchestrator.py`.
4. Decide and document a license (currently unspecified).
