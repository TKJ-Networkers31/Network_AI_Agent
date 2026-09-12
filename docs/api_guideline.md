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
{ "message": "ping ke google" }
```

Server emits a stream of typed events for the same request:

| Event type | When | Payload |
|---|---|---|
| `ack` | Immediately on receipt | `{ "message": "<echoed input>" }` |
| `thinking` | Before/after each LLM call | `{ "message": "..." }` |
| `tool_start` | Before a tool executes | `{ "name", "category", "arguments" }` |
| `tool_finish` | After a tool executes | `{ "name", "category", "success", "duration" }` |
| `response` | Final answer for this turn | same shape as REST `/api/chat` response |
| `error` | Unrecoverable failure this turn | `{ "message": "..." }` |

The WebSocket path calls the exact same `core.brain.Brain.think()` as the
REST path — it is a transport-only addition, not a parallel chat engine.
Reconnection with exponential backoff is handled client-side
(`useAiraSocket.js`); the server does not queue events across
disconnects.

## Error conventions

- REST errors use standard FastAPI `HTTPException` (`400`, `404`, `500`)
  with `detail` as a plain string.
- Provider-level errors (LLM unreachable, rate-limited, bad JSON) are
  **not** raised as exceptions — they're returned as
  `{"answer": "Terjadi error saat menghubungi model: ...", "error": true}`
  so the chat UI can render them as a normal assistant bubble rather than
  a hard failure.
