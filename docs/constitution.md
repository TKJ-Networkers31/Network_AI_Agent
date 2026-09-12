# AIRA OS Constitution

This document is the binding set of rules for AIRA OS. Every contributor
— human or AI — must follow these before writing code, tools, or docs.
When any other document in this repository conflicts with this one, this
document wins.

## 1. AIRA is the public assistant

The user only ever talks to **AIRA**. Internal agents (AKANE, REI, HIKARI,
YUKI) never introduce themselves, never claim to be "a different AI," and
are never named to the user unless the user explicitly asks about
internal architecture. See `core/persona.py`.

## 2. AKANE, REI, HIKARI, YUKI are internal agents only

Each agent owns exactly one domain (network, reasoning/LLM, vision, voice)
and exposes its capabilities only through its `registry.py`. No agent may
import another agent's internal modules directly. Cross-agent needs
(e.g. HIKARI describing what it sees to YUKI's voice pipeline) are wired
from `core/`, not agent-to-agent.

## 3. All inter-module communication goes through an event-oriented boundary

Modules do not reach into each other's internals. `core/orchestrator.py`
is the single aggregation and dispatch point between REI's planner and
every agent's tools; realtime updates flow through the `on_event`
callback mechanism (`Planner.run(..., on_event=...)`), which is the
current implementation of this principle. Any future formal event bus
(see `roadmap.md`) must preserve this boundary, not bypass it.

## 4. Provider access is exclusive to REI

`agents/rei/provider_client.py` is the **only** file in the entire
ecosystem permitted to make a network call to an LLM provider (Ollama or
OpenRouter). No tool, no router, no other agent may call a model
directly. New providers must be added to the explicit type whitelist in
that file.

## 5. The PWA is the primary interface

`app/` (React + Vite + Tailwind, installable as a PWA) is the primary way
people interact with AIRA. It must remain thin: render UI, call `api/`,
nothing else. `run_chat.py` (terminal mode) exists only for local
testing/debugging and is not a supported alternative interface.

## 6. SQLite is the only local database

All persistence lives under `database/*.db`. No JSON files for state, no
alternative database engines. Each `.db` file has one clear owner module
(see `docs/database.md`) — do not let two modules write to the same
table.

## 7. Documentation lives only in `docs/`

`docs/` is the single source of truth for architecture, agents, database
schema, API behavior, UI/UX, development setup, and roadmap. A `README.md`
elsewhere (e.g. inside `tools/` or `api/routers/`) is a smell — either its
content belongs in `docs/` or it should not exist. Historical documents
that are no longer current but still have research/decision value go in
`docs/archive/`, never left scattered across the codebase.

## 8. Tools are dumb, agents are smart

`tools/*` contains only low-level clients (SSH, SNMP, HTTP, camera).
Reasoning, validation, and decision-making belong in `agents/*`. If you
find yourself writing an `if` statement that changes behavior based on
business logic inside `tools/`, move it up to the agent layer.

## 9. Dangerous tools require confirmation

Any tool that mutates device state, external systems, or user data must
be added to its agent's `_DANGEROUS_TOOLS` set so the planner can require
manual confirmation before execution. As of this writing, every
registered tool is read-only and every `_DANGEROUS_TOOLS` set is empty —
this must change the moment a mutating tool is introduced.

## 10. Amending this document

Changes to this constitution must be deliberate and documented in
`docs/roadmap.md` as a decision, not silently edited. Source code changes
are never sufficient justification to change this document — the
document sets the rule; code must conform to it.
