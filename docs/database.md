# Database

AIRA OS uses **SQLite exclusively** for persistence. No JSON files, no
external database server. All files live under `AIRA_ECOSYSTEM/database/`.

| File | Owner module | Purpose |
|---|---|---|
| `long_term_memory.db` | `core/memory.py` | Durable facts (`facts` table) + observation log (`events` table) |
| `chat_sessions.db` | `core/chat_sessions.py` | Raw LLM conversation history + UI transcript per session |
| `logs.db` | `core/log_store.py` | Structured application logs, queried by `/api/logs` |
| `vision_snapshots/` | `tools/vision/detector.py` | JPEG snapshots saved when `detect_objects` finds something |

## `long_term_memory.db`

```sql
CREATE TABLE facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    device TEXT,
    message TEXT NOT NULL,
    severity TEXT DEFAULT 'info',
    created_at REAL NOT NULL
);
```

- `facts` is a simple key-value store, upserted via `remember_fact()`
  (`ON CONFLICT(key) DO UPDATE`). Populated either explicitly by the
  `remember` tool or automatically by `agents/rei/auto_extract.py`.
- `recall_facts(query)` does a naive `LIKE`-based keyword search — no
  embeddings/vector search.
- `events` is append-only, intended for observation/alert logging
  (currently only has a write path; `core/scheduler.py` — the intended
  producer of periodic events — is still a stub, see
  [`roadmap.md`](roadmap.md)).
- `build_context_snippet()` renders the top facts + recent events as a
  text block injected into the system prompt on every turn.

## `chat_sessions.db`

```sql
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    raw_history TEXT NOT NULL DEFAULT '[]',   -- JSON blob, full LLM messages
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE chat_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    steps_json TEXT,     -- JSON blob, tool-call timeline for UI replay
    created_at REAL NOT NULL
);
```

`raw_history` is deliberately overwritten in full on every turn rather
than appended incrementally — simplicity is preferred over write
efficiency at this data scale. `chat_turns` is the UI-facing transcript
used to repaint a session when the person reopens it.

## `logs.db`

```sql
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,
    logger_name TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT,          -- JSON, includes auto-attached _source (file/line/function)
    duration_ms REAL,
    success INTEGER
);
```

Indexed on `category`, `level`, `created_at`. Every category has a static
label/description/trigger-condition registered in
`core/log_store.py::CATEGORY_INFO`, surfaced in the PWA's Logs page legend.

## `vision_snapshots/`

Not a database — plain JPEG files, one per successful `detect_objects`
call with at least one detection, named `snapshot_<unix_ts>.jpg`.
