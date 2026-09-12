# AIRA OS Documentation

This folder is the **single source of truth** for AIRA OS documentation.
No other `.md` file elsewhere in the repository should describe project
architecture, agents, database schema, API behavior, or roadmap — if you
find one, it is stale and should be merged here or removed (see
[`archive/`](archive/) for superseded documents kept for history).

## Index

| Document | Covers |
|---|---|
| [architecture.md](architecture.md) | System layers, folder boundaries, request/response flow, logging |
| [agents.md](agents.md) | AIRA identity + AKANE/REI/HIKARI/YUKI responsibilities and tool registries |
| [database.md](database.md) | SQLite schemas: memory, chat sessions, logs, vision snapshots |
| [api_guideline.md](api_guideline.md) | REST endpoints, WebSocket protocol, slash commands |
| [ui_ux.md](ui_ux.md) | Frontend structure, design tokens, pages, voice UI |
| [development.md](development.md) | Local setup, environment variables, conventions |
| [roadmap.md](roadmap.md) | Completed phases, known gaps, next steps |
| [constitution.md](constitution.md) | Binding rules for anyone (human or AI) working on this repo |
| [archive/](archive/) | Superseded documents kept for historical context |

## Contribution rule for docs

- New documentation goes in this folder, in the file that already owns the
  topic. Don't create a new top-level `.md` file for a one-off note.
- If a document in `archive/` needs to be revived, promote it back into the
  index above and delete the archived copy — don't keep two live copies.
