# UI / UX

Frontend: React + Vite + Tailwind, located at `app/frontend/`. Installed as
a PWA (`manifest.json`, `service-worker.js`, install icons).

## Pages

| Page | File | Purpose |
|---|---|---|
| Chat | `pages/ChatPage.jsx` | Main conversation UI, voice controls, slash-command menu |
| Devices | `pages/DevicesPage.jsx` | Read-only view of `inventory/router.yaml` |
| Memory | `pages/MemoryPage.jsx` | View/add/delete long-term facts |
| Logs | `pages/LogsPage.jsx` | Filterable structured log viewer with per-entry detail panel |
| Settings | `pages/SettingsPage.jsx` | Token usage / OpenRouter credits |

Navigation: `Sidebar.jsx` (desktop drawer) and `MobileNav.jsx` (bottom tab
bar on small screens).

## State/context

- `context/SessionsContext.jsx` — session list, active session id, rename/delete
- `context/ChatRuntimeContext.jsx` — mounted at the **App level** (not inside
  ChatPage) so the WebSocket connection and message state survive
  navigating away from the Chat page (e.g. to Settings) and back
- `hooks/useAiraSocketPool.js` — one WebSocket per needed session, exponential backoff reconnect
- `hooks/useVoiceCall.js` — client-side mic capture + VAD; STT/TTS run on the server

## Design tokens

Defined in `src/theme/*` and consumed by `tailwind.config.js`.
Category colors for tool steps (`ToolStep.jsx`, `LiveSteps.jsx`):
network=sky, mikrotik=emerald, snmp=amber, web=fuchsia, memory=violet,
inventory=cyan, vision=pink

## Markdown & illustration rendering (`components/Markdown.jsx`)

Assistant messages are rendered as GFM Markdown. Two illustration paths:

- **SVG diagrams.** A fenced ```` ```svg ```` block (also ```` ```xml ````/
  ```` ```html ````/unlabeled blocks whose content is a complete
  `<svg>...</svg>`) is rendered as a card:
  DOMPurify (svg profile) -> viewBox normalisation -> XML re-serialisation
  (adds `xmlns`) -> `<img src="data:image/svg+xml,...">`. Rendering through
  `<img>` isolates the SVG (no scripts, no CSS leaking into the app, no
  external requests). The card has a light background because models draw
  for white paper. Actions: click to enlarge, view code, download `.svg`,
  copy. Invalid/truncated SVG falls back to a normal code block with a note.
- **Photos.** Markdown `![alt](url)` (the model emits these from
  `web_image_search` results) renders as a small gallery: lazy-loaded,
  `referrerPolicy="no-referrer"`, click to enlarge, and a link fallback if
  the image fails to load.

The model is taught both paths in `core/persona/prompt_builder.py`
(`ILLUSTRATION_RULES`); the SVG contract there must stay in sync with
`buildSvg()`.

## Realtime feedback components

- `LiveSteps.jsx` — shows the live "thinking" bubble and in-flight tool
  cards (spinning ring while running, check/cross when done) while a
  WebSocket response is streaming in
- `MessageBubble.jsx` — collapsible "N tools used" summary under each
  assistant message, expandable into per-tool `ToolStep.jsx` rows
- `Toast.jsx` — global notification system (`useToast()`), used for
  success/error/warning feedback across all pages
- `WsStatusBadge.jsx` — small live/connecting/disconnected indicator next
  to the page title

## Voice UI

- `VoiceControls.jsx` — mic toggle and speaker toggle (voice call mode)
- `VoiceOverlay.jsx` — full-screen "listening" overlay, shown while a voice call is active

## Conventions

- No business logic in `app/` — components call `api.js` and render
  results; parsing/decision logic belongs in `core/`.
- All new pages must go through `Sidebar.jsx` **and** `MobileNav.jsx` nav
  lists together, or mobile users lose access to the page.