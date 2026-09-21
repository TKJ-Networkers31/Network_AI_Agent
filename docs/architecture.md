# Architecture

## Layers

```
AIRA_ECOSYSTEM/
├── app/        PWA frontend — render + call api/, no business logic
├── api/        FastAPI: REST routers + WebSocket, thin HTTP layer only
├── core/       brain, orchestrator, memory, persona, logger, events, scheduler
├── agents/     akane, rei, hikari, yuki — internal specialists
├── tools/      low-level clients only (paramiko, pysnmp, requests, cv2)
├── database/   SQLite files + vision_snapshots (only persistence layer)
└── inventory/  router.yaml device inventory
```

## Hard boundaries (do not violate)

These rules originate from the project's migration plan and are now
permanent (see [`constitution.md`](constitution.md)):

- `app/` may only render UI and call `api/` endpoints. No parsing of tool
  results or business decisions in the frontend.
- `api/` never imports `tools/*` directly. It only calls `core.brain` /
  `core.orchestrator` and per-agent `registry.py` modules.
- `tools/*` contains **only** low-level clients (SSH, SNMP, HTTP, camera).
  No reasoning, no decision logic. Each subfolder has exactly one legal
  caller:

  | `tools/` subfolder | Only called by |
  |---|---|
  | `ssh/`, `snmp/`, `mikrotik/`, `network/`, `inventory.py` | `agents/akane/network_tools.py` |
  | `vision/` | `agents/hikari/vision.py` |
  | `web/` | `agents/rei/research_tools.py` |

- `agents/rei/provider_client.py` is the **only** file allowed to call an
  LLM provider (Ollama or OpenRouter). No other module may issue HTTP
  requests to a model endpoint.
- There is **one** internal event system: `core/events.py`. No module may
  introduce a second callback/queue mechanism for internal communication.
- All persistent storage is SQLite in `database/`. No JSON files, no
  ad-hoc flat files for state.

## Request flow (chat)

```
User message
  -> api/routers/chat.py (REST) or api/routers/ws.py (WebSocket)
  -> core/brain.py :: Brain.think()
      -> core/task_classifier.py -> core/model_router.py  (choose model)
      -> core/orchestrator.py :: Orchestrator.route()
          -> agents/rei/planner.py :: Planner.run()
              -> agents/rei/provider_client.py :: call_model()  (LLM call)
              -> tool_executor callback -> Orchestrator._execute_tool()
                  -> AGENT_TOOL_MAP[name](**arguments)   (AKANE / HIKARI / REI tools)
  <- BrainResponse(answer, steps, token_usage, ...)
  -> persisted to core/chat_sessions.py (SQLite)
  -> returned to caller (REST response or WebSocket "response" event)
```

`core/orchestrator.py` aggregates each agent's registry into three global
maps used by the planner:

- `AGENT_TOOL_MAP` — name -> callable
- `AGENT_TOOL_CATEGORY` — name -> category label (network, mikrotik, snmp,
  web, memory, vision, inventory)
- `AGENT_TOOL_SCHEMAS` — OpenAI-style function-calling schemas sent to the
  LLM

## Event Bus (`core/events.py`)

The single internal communication layer:

```
Publisher (Brain, Planner, classifier, DIO, FSE, AKANE, ...)
      |
      v
   Event Bus
      +--> Logger
      +--> WebSocket subscriber (api/ws_bridge.py)
      +--> Memory / Scheduler / other subscribers
```

**Event contract** (`Event`, immutable): `event_id`, `correlation_id`,
`event`, `source`, `agent`, `tool`, UTC ISO `timestamp`, `data`, `metadata`.
`Event.to_json_dict()` returns a JSON-safe copy (non-serializable values
become `str`). `Event.child()` keeps the `correlation_id`.

**API:** `subscribe(event, callback) -> token`, `unsubscribe(event, token)`,
`publish(...)`, `publish_async(...)`, wildcard `"*"`, `bind_loop(loop)`,
`stats()`.

**Dispatch rules**

- Sync subscribers run inline in the publisher's thread, isolated by
  try/except, before `publish()` returns (deterministic order). They must be
  fast and non-blocking.
- Async subscribers are scheduled onto the loop registered with
  `bind_loop()` (`run_coroutine_threadsafe` from other threads,
  `create_task` from the loop's own thread). `asyncio.run()` is only a last
  resort when no loop exists at all (terminal mode, plain tests) — never
  once per event on the normal server path.
- A failing subscriber never breaks the publisher or other subscribers; it
  is logged and counted in `stats()["failed_callbacks"]`.

**Event context.** `event_scope(correlation_id=..., session_id=..., run_id=...)`
(a `contextvars`-based context manager) stamps every event published inside
the block — including events published from worker threads started with
`asyncio.to_thread`. `correlation_id` comes from the scope when not given
explicitly; the other keys land in `Event.metadata`. `Brain.think()` opens a
scope if none is active, so one chat turn = one `correlation_id`.

**Standard events** (`EventNames`): `chat.received`, `thinking.start/finish`,
`task.classified/started/finished`, `model.started/finished/failed/switched/
selected/fallback`, `tool.start/progress/finish`, `response.ready`,
`stream.start/delta` (Sprint 2.5), `memory.saved`, `interaction.requested/started/generated/completed/cancelled`,
`location.updated/cleared`, `system.error`.

Currently published: `chat.received`, `thinking.start/finish`,
`task.classified/started/finished`, `tool.*`, `response.ready`,
`system.error` (planner errors), `stream.start/delta` (Planner, only when the
turn streams), `model.selected/fallback/failed`,
`interaction.started/generated/completed/cancelled`, `location.*`,
`connection.*`, `file.*`. Defined but not yet published by anyone:
`model.started/finished/switched`, `memory.saved`, `interaction.requested`
(see [`roadmap.md`](roadmap.md)).

## Realtime streaming (WebSocket)

`api/routers/ws.py` runs the exact same `Brain.think()` used by REST — it
is **not** a second chatbot. The only difference is transport.

```
Planner/Brain --publish--> Event Bus --subscriber--> api/ws_bridge.py
                                                       |  asyncio.Queue (FIFO)
                                                       v
                                            api/ws_manager.py -> client
```

- Each turn runs inside `event_scope(correlation_id, session_id, run_id)`.
  `Brain.think()` is synchronous (blocking HTTP/SSH), so `ws.py` runs it in
  a worker thread via `asyncio.to_thread`; the context follows the thread.
- `WebSocketEventBridge` is a single wildcard subscriber, started in
  `api/main.py` startup (idempotently re-ensured when a socket connects).
  It only forwards events that carry **both** `session_id` and `run_id`
  (REST turns have no `run_id`, so they never leak into an open socket) and
  only those in `DEFAULT_WS_EVENT_MAP` + `STREAM_WS_EVENT_MAP`:

  | Event Bus | WebSocket `type` |
  |---|---|
  | `thinking.start` | `thinking` |
  | `tool.start` | `tool_start` |
  | `tool.progress` | `tool_progress` |
  | `tool.finish` | `tool_finish` |
  | `system.error` | `error` |
  | `stream.start` | `stream_start` |
  | `stream.delta` | `stream_delta` |

  The existing wire protocol is unchanged; `stream_*` are additive and
  ignored by clients that do not know them.
- Protocol events owned by `ws.py` itself (`ack`, `transcript`,
  `transcript_empty`, `response`, `cancelled`, fatal `error`) are still sent
  directly. Before `response` / `cancelled` / fatal `error`, `ws.py` awaits
  `bridge.flush()` so every tool event already published arrives first.
- `Brain.think(on_event=...)` / `Planner.run(on_event=...)` still accept the
  legacy callback for callers that have not migrated; `ws.py` no longer
  uses it.

### LLM streaming (Sprint 2.5)

Provider streaming is real end to end and rides the same path as the tool
events, so ordering and session isolation come for free:

```
ProviderClient.chat_stream (NDJSON / SSE)  -- on_delta -->  call_model(stream=sink)
   --> Planner _StreamPublisher --> Event Bus stream.start / stream.delta
   --> WebSocketEventBridge (same FIFO queue as tool.*) --> client
```

- `Brain.think(..., stream=True)` → `Orchestrator.route(..., stream=True)` →
  `Planner.run(..., stream=True)` → `call_model(..., stream=sink, cancel_event=...)`.
  `stream` defaults to `False` at every layer; with `False` the code path is
  the previous non-streaming one. Brain only forwards `stream` when it is
  `True`, so an orchestrator/test double without that parameter still works.
- Retry, Model Policy fallback and context check are unchanged; every
  request to a provider (including retry/fallback) calls `sink.start()`, which
  the client treats as "clear the buffer".
- The final `BrainResponse` / WS `response` is still complete (`answer`
  whole, plus `streamed`); it is the authoritative "complete" event.
- Runtime State is untouched: it only reacts to `thinking.*`, `speech.*`,
  `voice.listening.*` and `response.ready`, never to `stream.*`.
- Kill switch: `AIRA_STREAMING=0`. Per-turn opt-out: `{"stream": false}`.

Client-facing contract and provider capability table: see
[`api_guideline.md`](api_guideline.md#streaming-sprint-25).

`api/ws_manager.py` tracks live connections per `session_id` and is
intentionally separate from `api/state.py` (which caches `ConversationMemory`
per session) — connection lifecycle and conversation state are different
concerns.

## Memory model

Two independent SQLite databases, on purpose (different lifecycles):

- `database/long_term_memory.db` — durable facts/events the assistant
  should recall across sessions (`core/memory.py`). See
  [`database.md`](database.md).
- `database/chat_sessions.db` — raw conversation history + UI transcript
  per session (`core/chat_sessions.py`).

`ConversationMemory` (in-process, cached in `api/state.py`) also carries a
per-session `TokenTracker`, restored during Phase 0 stabilization after it
was accidentally dropped in an earlier refactor.

## Logging

`core/logger.py` sets up one root logger (`"aira"`) that fans out to four
sinks simultaneously:

1. Colored console output
2. `logs/aira.log` (rotating, all categories combined)
3. `logs/categories/<category>.log` (rotating, one file per category)
4. `database/logs.db` (queryable via `/api/logs`, powers the Logs page in
   the PWA)

Category is inferred from the last segment of the logger name
(`aira.tools.ssh` -> `ssh`), or explicitly passed via `extra={"category": ...}`
using the `log_event()` helper.

The Event Bus logs every event at `DEBUG` (category `eventbus`); the payload
is only built when `DEBUG` is enabled.

## Auto memory extraction

After every assistant turn, `agents/rei/auto_extract.py` runs a background
thread that asks the LLM whether anything in that turn is worth
remembering long-term (name preferences, thresholds, standing
instructions). It explicitly skips extraction when the turn's answer is
the `EMPTY_RESPONSE_MARKER` placeholder, to avoid wasting a provider call
and spamming logs when the provider itself was rate-limited.
