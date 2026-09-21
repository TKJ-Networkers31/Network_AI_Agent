# API Guideline

Base URL: `/api` (REST) and `/ws` (WebSocket). Server: FastAPI, entry point
`api/main.py`.

## REST Endpoints

| Method | Path | Router | Purpose |
|---|---|---|---|
| POST | `/api/chat` | `chat.py` | Send a message, get a full answer (creates a session if none given) |
| POST | `/api/reset` | `chat.py` | Clear a session's in-memory + persisted history |
| GET | `/api/token-usage` | `chat.py` | Global (cross-session) token usage counters |
| GET | `/api/providers` | `providers.py` | List available LLM providers + active one |
| POST | `/api/providers/select` | `providers.py` | Switch active provider |
| GET | `/api/providers/credits` | `providers.py` | OpenRouter balance (only for `openai`-type providers) |
| GET | `/api/memory/facts` | `memory.py` | List all long-term facts |
| POST | `/api/memory/facts` | `memory.py` | Add/overwrite a fact |
| DELETE | `/api/memory/facts/{key}` | `memory.py` | Delete a fact |
| GET | `/api/memory/events` | `memory.py` | Recent observation events |
| GET | `/api/devices` | `devices.py` | Inventory device list |
| GET | `/api/tools` | `tools.py` | All registered tool schemas (name, description, category, params) |
| GET/POST | `/api/sessions` | `sessions.py` | List / create chat sessions |
| GET | `/api/sessions/{id}/messages` | `sessions.py` | Full transcript for a session |
| PATCH | `/api/sessions/{id}` | `sessions.py` | Rename a session |
| DELETE | `/api/sessions/{id}` | `sessions.py` | Delete a session |
| GET | `/api/logs` | `logs.py` | Query structured logs (filters: category, level, search, since_minutes) |
| GET | `/api/logs/categories` | `logs.py` | Category list with counts + descriptions |
| GET | `/api/logs/stats` | `logs.py` | Log counts grouped by level |
| DELETE | `/api/logs` | `logs.py` | Clear logs (optionally by category / age) |
| GET | `/api/health` | `main.py` | Liveness check |

### `POST /api/chat` request/response

```json
// request
{ "message": "cek resource R1", "session_id": "abc123" }

// response
{
  "answer": "...",
  "steps": [ { "type": "tool_call", "name": "get_resources", "category": "mikrotik",
               "arguments": {"device_name": "R1"}, "success": true,
               "duration": 0.42, "result_preview": "..." } ],
  "duration": 1.9,
  "token_usage": { "prompt_tokens": 1200, "completion_tokens": 80, "total_tokens": 1280 },
  "error": false,
  "session_id": "abc123",
  "session_title": "cek resource R1"
}
```

## Slash commands

A message starting with `/` is treated as an explicit tool directive.
`chat.py::_apply_slash_command()` (mirrored identically in `ws.py`) parses
`/toolname rest of the message`, validates `toolname` against
`AGENT_TOOL_MAP`, and rewrites the message into an instruction the planner
is told it is **required** to fulfil with that exact tool. Unknown tool
names fall through unchanged (treated as a normal message starting with
`/`).

## WebSocket protocol

`ws://<host>/ws/chat/{session_id}`

Client sends:
```json
{ "message": "ping ke google", "run_id": "a1b2c3", "stream": true }
```

`run_id` (optional, client-generated) is echoed on every event of the turn so
the client can drop stale events after **Stop**. `stream` (optional, default
`true`) — see [Streaming](#streaming-sprint-25) below.

Server emits a stream of typed events for the same request:

| Event type | When | Payload |
|---|---|---|
| `ack` | Immediately on receipt | `{ "message": "<echoed input>" }` |
| `thinking` | Before/after each LLM call | `{ "message": "..." }` |
| `tool_start` | Before a tool executes | `{ "name", "category", "arguments" }` |
| `tool_finish` | After a tool executes | `{ "name", "category", "success", "duration" }` |
| `stream_start` | A request to the LLM provider begins (also on retry / fallback / the next LLM call after a tool) | `{ "call", "attempt", "model": {id, display_name, provider, fallback_from} }` |
| `stream_delta` | A piece of text just received from the provider | `{ "call", "attempt", "seq", "text" }` |
| `response` | **Complete** — final answer for this turn | same shape as REST `/api/chat` response, plus `"streamed": bool` |
| `error` | Failure this turn | `{ "message": "...", "fatal"?: true }` |
| `cancelled` | Turn stopped by the user | `{}` |

Every event's `data` also carries `session_id` and `run_id`.

The WebSocket path calls the exact same `core.brain.Brain.think()` as the
REST path — it is a transport-only addition, not a parallel chat engine.
Reconnection with exponential backoff is handled client-side
(`useAiraSocket.js`); the server does not queue events across
disconnects.

## Streaming (Sprint 2.5)

Real provider streaming, not a sliced full response. A chunk is forwarded to
the client the moment the provider sends it (verified against a local
chunked HTTP server that withholds the rest of the body until the first chunk
has arrived).

### Provider capability

| Provider | Wire format | Streamed content | Tool calls | Usage |
|---|---|---|---|---|
| `ollama` (`/api/chat`, `stream: true`) | NDJSON, one JSON object per line | `message.content` per line (`message.thinking` is **not** forwarded) | delivered whole in one line | final line (`prompt_eval_count`, `eval_count`) |
| `openrouter`, `gemini`, `nvidia` (OpenAI-compatible, `stream: true`) | SSE `data: {...}` … `data: [DONE]` | `choices[0].delta.content` | fragments merged per `index` (or per `id` when `index` is missing) | last chunk via `stream_options.include_usage`; `null` if the provider ignores it |

Fallbacks inside the provider client (`agents/rei/provider_client.py`):
a provider that answers plain JSON instead of a stream → treated as
non-streaming (`streamed: false`, no fake deltas); HTTP 4xx that mentions
"stream" → same model is retried **non-streaming**; `stream_options`
rejected → retried without it; Ollama "does not support tools" → retried
without tools; stream cut before `finish_reason`/`[DONE]`/`done: true` →
`connection` error (transient → retry, then policy fallback model). A cut
stream is never accepted as a partial answer.

### Contract

Event order for one turn (all events carry `session_id`, `run_id`):

```
ack
thinking
stream_start   { call: 1, attempt: 1, model }
stream_delta   { call: 1, attempt: 1, seq: 1, text }
stream_delta   { call: 1, attempt: 1, seq: 2, text }
…                                  ← LLM asked for tools:
tool_start / tool_progress / tool_finish
thinking
stream_start   { call: 2, attempt: 1, model }
stream_delta   …
response       { answer, steps, streamed: true, … }     ← COMPLETE
```

| Contract name | WS event | Notes |
|---|---|---|
| start | `stream_start` | Begins a **fresh** text buffer for the assistant bubble. Sent once per provider request: a retry or fallback model produces another `stream_start` (`attempt` +1, `seq` restarts at 1, `model.fallback_from` set on fallback) — the client must **clear** its buffer. |
| delta / chunk | `stream_delta` | Append `text` to the buffer. `seq` is 1-based and gapless within one `(call, attempt)`. |
| complete | `response` | Authoritative. `answer` always replaces whatever was streamed. `streamed` says whether any provider call really streamed. |
| error | `error` (`system.error` → `error`, or `fatal: true`) | If a `response` with `error: true` follows, its `answer` replaces the buffer. On a fatal `error` discard the buffer. |
| stop | `cancelled` | Discard the buffer. |

Rules a client can rely on:

- One turn can contain several LLM **calls** (`call` = 1, 2, …): LLM → tools →
  LLM. Text from a call that is followed by `tool_start` is only a preamble;
  the final answer is the text of the last call, i.e. `response.answer`.
- A turn where the provider does not stream (or `stream: false`) emits **no**
  `stream_*` events; the client just receives `response`. Clients must
  therefore render `response.answer` even if no delta arrived.
- All `stream_delta`/`tool_*` events of a turn arrive **before** its `response`
  (`ws.py` awaits `bridge.flush()` first); order within a session is FIFO.
- Events of different sessions never mix (bridge filters on `session_id` +
  `run_id`; REST turns have no `run_id` and never reach a socket).
- Clients that do not know `stream_*` ignore them (unknown types are dropped),
  so existing frontends keep working unchanged.
- Rendering of Markdown / SVG / images / DIO forms stays entirely in the
  frontend; `stream_delta.text` is raw model text. DIO `interaction_schema`
  still arrives only in `response`.

### Switches

| Switch | Effect |
|---|---|
| `{"stream": false}` in the client message | That turn is non-streaming |
| `AIRA_STREAMING=0` (env, server) | Streaming disabled for every WebSocket turn (kill switch) |
| Voice turns (`voice_audio`) | Never stream (TTS reads the full answer) |
| REST `POST /api/chat` | Always non-streaming; response unchanged |

### Internal flow

```
ws.py  --think(msg, cancel_event, stream=True)-->  Brain  --route(..., stream=True)-->  Orchestrator
   --> Planner.run(stream=True) --> call_model(stream=sink, cancel_event)
   --> ProviderClient.chat_stream(on_delta)   (NDJSON / SSE)
sink.start / sink.delta --> Event Bus: stream.start / stream.delta (+ session_id, run_id, correlation_id)
   --> api/ws_bridge.py (STREAM_WS_EVENT_MAP) --> WebSocket
```

Retry, provider fallback (Model Policy), context check, Stop (`cancel_event`
is checked on every chunk and closes the connection; no retry/fallback
afterwards) and Runtime State (`thinking.start` … `thinking.finish` only —
`stream.*` are not state events) behave as before.

## Error conventions

- REST errors use standard FastAPI `HTTPException` (`400`, `404`, `500`)
  with `detail` as a plain string.
- Provider-level errors (LLM unreachable, rate-limited, bad JSON) are
  **not** raised as exceptions — they're returned as
  `{"answer": "Terjadi error saat menghubungi model: ...", "error": true}`
  so the chat UI can render them as a normal assistant bubble rather than
  a hard failure.
