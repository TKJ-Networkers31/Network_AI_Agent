# Documentation Audit Report — AIRA OS

Scope: all `.md` / `.txt` / migration / roadmap / notes / README-style files
found in the repository. No source code (`.py`, `.jsx`, `.ts/.tsx`) was
inspected for restructuring — only read for context.

| File | Status | Reason |
|---|---|---|
| `AIRA_ECOSYSTEM/README.md` | MERGE | Project overview, folder structure, and hard rules absorbed into the new root `README.md` + `docs/architecture.md` + `docs/constitution.md`. |
| `AIRA_ECOSYSTEM/app/README.md` | DELETE | Contained only a one-line TODO ("git mv frontend AIRA_ECOSYSTEM/app") for a migration step that is already done — no remaining information value. |
| `AIRA_ECOSYSTEM/tools/README.md` | MERGE | The `tools/*` access-boundary table is now part of `docs/architecture.md` ("Hard boundaries"). |
| `AIRA_ECOSYSTEM/database/README.md` | MERGE | Migration TODO absorbed into `docs/roadmap.md` (marked done); schema/ownership content rewritten into `docs/database.md`. |
| `AIRA_ECOSYSTEM/api/routers/README.md` | DELETE | Listed TODOs for router migration (chat.py, devices.py, memory.py, providers.py, sessions.py, tools.py to stop importing `agent.*`/`tools.*` directly) — verified complete in current router source, so nothing left to track. |
| `AIRA_ECOSYSTEM/MIGRATION_PLAN.md` | ARCHIVE | Migration is complete (confirmed by `consolidate_to_aira.ps1` having run and legacy code existing only under `_legacy_backup_*/`), but the staged plan has historical/decision value explaining current folder boundaries. Moved to `docs/archive/MIGRATION_PLAN.md`. |
| `consolidate_to_aira.ps1` | KEEP (out of scope) | Operational script, not documentation. Left untouched per the "no source/script changes" rule. |

## Notes

- No duplicate roadmaps existed beyond `MIGRATION_PLAN.md` — it was the
  closest thing to a roadmap and has been superseded by the new
  `docs/roadmap.md`, which also documents Phase 0 / Phase 0.5 work that
  had no roadmap entry anywhere before this audit.
- No dedicated agents/database/API/UI documentation existed prior to this
  audit; those `docs/*.md` files are new, derived directly from source
  code behavior (registries, schemas, SQLite schemas, routers, frontend
  structure) rather than from any prior doc.
