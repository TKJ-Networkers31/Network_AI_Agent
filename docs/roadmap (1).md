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
- **Worker 1 — Event Bus foundation** (decision recorded here per
  `constitution.md` §3/§10)
  - `core/events.py` is the single internal event system: sync subscribers
    dispatched inline, async subscribers scheduled on the bound main loop
    (no more `asyncio.run()` per event), `contextvars`-based `event_scope`
    for `correlation_id` / `session_id` / `run_id`, JSON-safe serialization,
    complete `EventNames`
  - WebSocket realtime events now flow `Planner/Brain -> Event Bus ->
    api/ws_bridge.py -> client`; the old `on_event` -> `queue.Queue` ->
    `_drain_queue_to_socket` path in `ws.py` is removed (wire protocol
    unchanged)
  - `Brain` publishes `chat.received`, `thinking.start/finish`,
    `task.started/finished`, `response.ready`; `Planner` publishes
    `thinking.start`, `tool.start/progress/finish`, `system.error`
  - Tests: `tests/test_events.py`, `tests/test_ws_bridge.py`

## In progress / known gaps

- `agents/hikari/vision.py::recognize_object` — schema exists, always
  returns "not implemented." Not a regression; it was never implemented
  even in the legacy system.
- `core/scheduler.py` — background/periodic job runner is a stub
  (`start()`/`stop()` raise `NotImplementedError`). Intended for periodic
  MikroTik polling + anomaly events into `core.memory.log_event()`. It
  should be built as an Event Bus publisher/subscriber, not a new event
  mechanism.
- **Event Bus — remaining publishers.** Defined in `EventNames` but not yet
  published by any module: `model.started` / `model.finished` (should be
  published by `provider_client.call_model`), `memory.saved` (should be
  published by `core.memory.remember_fact`), `model.switched`, and
  `interaction.requested` (DIO currently publishes `interaction.started` /
  `interaction.generated`; a `requested` alias/rename must be decided
  deliberately since existing subscribers/tests use the current names).
- **REST `/api/chat`** does not open an `event_scope` with `session_id`, so
  its events carry only a per-turn `correlation_id` and no `session_id`
  metadata.

## Next steps (proposed, not yet scheduled)

1. Add the remaining Event Bus publishers listed above (small, additive
   `publish` calls in `provider_client.py`, `core/memory.py`,
   `agents/rei/dio_tools.py`).
2. Implement `core/scheduler.py` and wire it to AKANE for periodic device
   polling + threshold alerts (`long_term_memory.db.events`).
3. Implement `recognize_object` in HIKARI, or remove the schema if it
   will not be built, to avoid an always-failing tool being offered to
   the planner.
4. Decide and document a license (currently unspecified).
