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
| Settings | `pages/SettingsPage.jsx` | Switch active LLM provider, view token usage / OpenRouter credits |

Navigation: `Sidebar.jsx` (desktop drawer) and `MobileNav.jsx` (bottom tab
bar on small screens).

## State/context

- `context/SessionsContext.jsx` — session list, active session id, rename/delete
- `context/ChatRuntimeContext.jsx` — mounted at the **App level** (not inside
  ChatPage) so the WebSocket connection and message state survive
  navigating away from the Chat page (e.g. to Settings) and back
- `hooks/useAiraSocket.js` — WebSocket client with exponential backoff reconnect
- `hooks/useVoice.js` — Web Speech API wrapper (STT via `SpeechRecognition`,
  TTS via `speechSynthesis`) — this is browser-native and **separate** from
  the backend YUKI voice pipeline (which is for the terminal/local
  microphone flow, not the web client)

## Design tokens

Defined in `tailwind.config.js`:

- Background: `app` (`#070b14`), `panel` (`#0c1220`), `card` (`#101a2c`)
- Accent: blue-tech gradient, `accent.DEFAULT` (`#2563eb`), `accent.light`
  (`#38bdf8`), `accent.soft` (`#1e3a8a`)
- Border radius: `xl2` (`1rem`) used consistently for cards
- Category colors for tool steps (`ToolStep.jsx`, `LiveSteps.jsx`):
  network=sky, mikrotik=emerald, snmp=amber, web=fuchsia, memory=violet,
  inventory=cyan, vision=pink

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

- `VoiceControls.jsx` — mic toggle (pulses red while listening) and
  speaker toggle (pulses blue while speaking)
- `VoiceOverlay.jsx` — full-screen "listening" overlay with live interim
  transcript, shown while the mic is active

## Conventions

- No business logic in `app/` — components call `api.js` and render
  results; parsing/decision logic belongs in `core/`.
- All new pages must go through `Sidebar.jsx` **and** `MobileNav.jsx` nav
  lists together, or mobile users lose access to the page.
