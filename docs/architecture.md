# Architecture

## Layers

```
AIRA_ECOSYSTEM/
├── app/        PWA frontend — render + call api/, no business logic
├── api/        FastAPI: REST routers + WebSocket, thin HTTP layer only
├── core/       brain, orchestrator, memory, persona, logger, scheduler
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
- All persistent storage is SQLite in `database/`. No JSON files, no
  ad-hoc flat files for state.

## Request flow (chat)

```
User message
  -> api/routers/chat.py (REST) or api/routers/ws.py (WebSocket)
  -> core/brain.py :: Brain.think()
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

## Realtime streaming (WebSocket)

`api/routers/ws.py` runs the exact same `Brain.think()` used by REST — it
is **not** a second chatbot. The only difference is transport: `Planner.run()`
accepts an `on_event` callback that emits `thinking` / `tool_start` /
`tool_finish` / `response` / `error` events. Because `Brain.think()` is
synchronous (blocking HTTP/SSH calls), the WS handler runs it in a worker
thread via `asyncio.to_thread` and relays events back through a
thread-safe `queue.Queue` drained by an async loop (`_drain_queue_to_socket`).

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

## Auto memory extraction

After every assistant turn, `agents/rei/auto_extract.py` runs a background
thread that asks the LLM whether anything in that turn is worth
remembering long-term (name preferences, thresholds, standing
instructions). It explicitly skips extraction when the turn's answer is
the `EMPTY_RESPONSE_MARKER` placeholder, to avoid wasting a provider call
and spamming logs when the provider itself was rate-limited.
