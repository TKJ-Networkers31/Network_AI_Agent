# PHASE 5 — FRONTEND & UI/UX DEEP AUDIT (`05_FRONTEND_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Directory**: `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/`  
**Scope**: All 223 files in `src/` plus `package.json`, `vite.config.js`, `tailwind.config.js`, `jsconfig.json`, `index.html`, and `public/` (`manifest.json`, `service-worker.js`).

---

## 1. Pages & Routing Audit (Section A)

### 1.1 Absence of URL Routing (`CONFIRMED`)
- **Finding**: `package.json:11-28` does **not** install `react-router` or `react-router-dom`. Instead, [`src/App.jsx:209`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/App.jsx#L209) stores the active page in React state (`const [active, setActive] = useState("workspace")`) and listens for custom DOM events (`window.addEventListener("aira:navigate", onNavigate)` at `src/App.jsx:250-261`).
- **Operational Impact**:
  1. Browser Back/Forward buttons do not navigate between pages.
  2. Pressing `F5` (page reload) always resets the operator to `"workspace"` (`ChatPage.jsx`).
  3. Deep-linking or sharing URLs to specific incidents, topology nodes, or admin tabs is impossible.
  4. Cross-page context handoff relies on fragile `sessionStorage` keys (`"aira_topology_focus_device"`, `"aira_infra_initial_tab"`, `"aira_settings_tab"`).

### 1.2 Complete Page & Route Registry (`src/App.jsx:74-97`)
- **Active Reachable Pages (14 pages via Sidebar, Sub-tabs, TopBar, or Voice)**:
  1. `src/pages/ChatPage.jsx` (`"workspace"`, `"chat"`) — Default landing page.
  2. `src/pages/InfrastructurePage.jsx` (`"infrastructure"`) — Wrapper with sub-tabs `"topology"`, `"devices"`, `"nms"`.
  3. `src/pages/TopologyPage.jsx` (`"topology"`).
  4. `src/pages/DevicesPage.jsx` (`"devices"`).
  5. `src/pages/NmsPage.jsx` (`"nms"`).
  6. `src/pages/NetworkIntelligencePage.jsx` (`"intelligence"`).
  7. `src/pages/AutomationsPage.jsx` (`"automations"`).
  8. `src/pages/WorkspacePage.jsx` (`"files"`).
  9. `src/pages/ModelsPage.jsx` (`"models"`, `superAdminOnly: true`).
  10. `src/pages/LogsPage.jsx` (`"logs"`).
  11. `src/pages/AdminPlatformPage.jsx` (`"admin"`, `adminOnly: true`).
  12. `src/pages/SettingsPage.jsx` (`"settings"` — via Sidebar footer).
  13. `src/pages/PersonaPage.jsx` (`"persona"` — embedded in `SettingsPage.jsx:670` and reachable via voice).
  14. `src/pages/AkaneWorkspace.jsx` (`"akane"` — reachable via `TopBar` `<ConnectionIndicator>` / `<ConnectionDock>` or voice).
  15. `src/pages/MemoryPage.jsx` (`"memory"` — reachable **only** via voice command `"buka halaman memori"` in `voiceCommandRouter.js:68`; not linked in Sidebar or Settings).
  16. `src/pages/LoginPage.jsx` — Rendered by `AuthenticatedGate` (`src/App.jsx:319`) when unauthenticated.
- **Orphaned Pages Registered in `App.jsx` `PAGES` Without Any UI Navigation (`CONFIRMED`)**:
  17. [`src/pages/OperationsPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/OperationsPage.jsx#L1-L364) (`PAGES["operations"]` at `App.jsx:92`) — Zero Sidebar link, zero MobileNav link, zero `aira:navigate` dispatch, zero voice command. Also hardcodes `const API_BASE = "http://127.0.0.1:8000/api/operations"` (`L38`).
  18. [`src/pages/GatewaysPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/GatewaysPage.jsx#L1-L336) (`PAGES["gateways"]` at `App.jsx:93`) — Zero UI navigation entry anywhere in the app.
  19. [`src/pages/DecisionsPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/DecisionsPage.jsx#L1-L396) (`PAGES["decisions"]` at `App.jsx:94`) — Zero UI navigation entry anywhere in the app.
  20. [`src/pages/CustomerPortalPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/CustomerPortalPage.jsx#L1-L507) (`PAGES["portal"]` at `App.jsx:95`) — Zero UI navigation entry anywhere in the app.
- **Shadowed / Unreachable Page in `App.jsx` (`CONFIRMED`)**:
  21. [`src/pages/AdminLoginPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/AdminLoginPage.jsx#L1-L267) — At [`src/App.jsx:215-217, 282`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/App.jsx#L215-L217), when `active === "admin"` and `!isAdmin`, both `isDenied` and `isBlockedAdmin` evaluate to `true`. Because line `282` renders `{isDenied ? <AccessDeniedView ... /> : <Page ... />}`, `AccessDeniedView` always takes precedence and `AdminLoginPage` can **never** render!
- **Unimported Dead Page Files (`CONFIRMED`)**:
  22. [`src/pages/dio/DioPreviewPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/dio/DioPreviewPage.jsx#L1-L113) — Never imported anywhere; has broken relative imports (`../components/TopBar.jsx` at `L2-3`).
  23. [`src/components/workspace/WorkspacePage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/workspace/WorkspacePage.jsx#L1-L1860) — Never imported anywhere; legacy duplicate of `src/pages/WorkspacePage.jsx` with 9 broken relative imports (`L2-10`).

### 1.3 Route Protection & Navigation RBAC Flaws (`CONFIRMED`)
1. **Mobile Bottom Navigation Ignores RBAC (`src/components/MobileNav.jsx:12, 50-52`)**:
   - `PRIMARY_ITEMS` (`["workspace", "infrastructure", "automations", "files"]`) in `MobileNav.jsx` does **not** filter by `hasPermission(item.requiredPermission)`, exposing restricted tabs on mobile devices.
2. **One-Way Permission Alias Bug Hides `NetworkIntelligencePage` (`src/components/navConfig.js:21` vs `src/context/AuthContext.jsx:285-322`)**:
   - `navConfig.js:21` sets `requiredPermission: "nms.read"` for `intelligence`.
   - `AuthContext.jsx:289` defines `"nms.view": ["nms.read", ...]`, and `hasPermission(perm)` (`L314-322`) looks up `PERMISSION_ALIASES[perm]`. Because `"nms.read"` is a value (not a key) in `PERMISSION_ALIASES`, a user whose group grants `"nms.view"` fails `hasPermission("nms.read")`!
3. **Incomplete `PAGE_PERMISSIONS` Map (`src/App.jsx:192-205`)**:
   - `PAGE_PERMISSIONS` has no entries for `"intelligence"`, `"operations"`, `"gateways"`, `"decisions"`, `"portal"`, `"akane"`, `"persona"`, or `"memory"`.

---

## 2. Duplicate UI Components & Views Audit (Section B — 7-Point Analysis)

### Duplicate Group 1: `BootScreen` Components
1. **Path file masing-masing**:
   - [`src/components/BootScreen.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/BootScreen.jsx#L1-L167) (167 lines)
   - [`src/components/boot/BootScreen.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/boot/BootScreen.jsx#L1-L131) (131 lines)
2. **Komponen mana yang benar-benar digunakan**: **Both** are imported (`src/components/BootScreen.jsx` in `src/App.jsx:22` as the `<Suspense>` fallback; `src/components/boot/BootScreen.jsx` in `src/components/boot/BootGate.jsx:5` for initial session boot).
3. **Komponen mana yang lama atau yatim**: `src/components/BootScreen.jsx` is the older `/api/health` polling screen now repurposed as a `<Suspense fallback={<BootScreen ready={true} />}>` chunk loader.
4. **Perbedaan perilaku dan tampilan**: `src/components/BootScreen.jsx` accepts `{ ready, attempts }` and renders an orbital spinner; `src/components/boot/BootScreen.jsx` accepts `{ onComplete }` and runs a multi-step progress bar sequence (`bootSequence.js`).
5. **Risiko kebingungan saat maintenance**: High — two files with the exact same component name `BootScreen` and different prop contracts.
6. **Komponen mana yang sebaiknya dipertahankan**: Keep `src/components/boot/BootScreen.jsx` for boot sequence and rename `src/components/BootScreen.jsx` to `SuspenseFallbackLoader.jsx`.
7. **Rencana konsolidasi**: Rename `src/components/BootScreen.jsx` -> `src/components/SuspenseLoader.jsx` and remove dead `/api/health` polling visuals from the Suspense fallback.

### Duplicate Group 2: `CapabilityHeroRow` Components
1. **Path file masing-masing**:
   - [`src/components/capabilities/CapabilityHeroRow.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/capabilities/CapabilityHeroRow.jsx#L1-L50) (50 lines)
   - [`src/capabilities/CapabilityHeroRow (1).jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/capabilities/CapabilityHeroRow%20(1).jsx#L1-L50) (50 lines)
2. **Komponen mana yang benar-benar digunakan**: `src/components/capabilities/CapabilityHeroRow.jsx` (used by `src/Hero.jsx:2` and `src/components/cockpit/DynamicHero.jsx:2`).
3. **Komponen mana yang lama atau yatim**: `src/capabilities/CapabilityHeroRow (1).jsx` is 100% orphaned and has broken relative imports (`./CapabilityChip.jsx`).
4. **Perbedaan perilaku dan tampilan**: Identical code, except `src/capabilities/CapabilityHeroRow (1).jsx` is in the wrong directory depth.
5. **Risiko kebingungan saat maintenance**: Accidental OS file copy (`(1)`) pollutes search results and fails static analysis if imported.
6. **Komponen mana yang sebaiknya dipertahankan**: `src/components/capabilities/CapabilityHeroRow.jsx`.
7. **Rencana konsolidasi**: Delete `src/capabilities/CapabilityHeroRow (1).jsx` and the empty `src/capabilities/` directory.

### Duplicate Group 3: `WorkspacePage` Components
1. **Path file masing-masing**:
   - [`src/pages/WorkspacePage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/WorkspacePage.jsx#L1-L1860) (1,860 lines)
   - [`src/components/workspace/WorkspacePage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/workspace/WorkspacePage.jsx#L1-L1860) (1,860 lines)
2. **Komponen mana yang benar-benar digunakan**: `src/pages/WorkspacePage.jsx` (imported by `src/App.jsx:50` for `PAGES["files"]`).
3. **Komponen mana yang lama atau yatim**: `src/components/workspace/WorkspacePage.jsx` is 100% orphaned.
4. **Perbedaan perilaku dan tampilan**: `src/pages/WorkspacePage.jsx` uses non-blocking `useModalDialog()` modals, whereas `src/components/workspace/WorkspacePage.jsx` has 9 broken imports (`L2-10`) and still calls blocking `window.prompt()` / `window.confirm()` (`L428, 439, 535, 557`).
5. **Risiko kebingungan saat maintenance**: High — 1,860 lines of duplicated code where edits to the wrong file have zero effect.
6. **Komponen mana yang sebaiknya dipertahankan**: `src/pages/WorkspacePage.jsx`.
7. **Rencana konsolidasi**: Delete `src/components/workspace/WorkspacePage.jsx`.

### Duplicate Group 4: `Hero` vs `DynamicHero` & `WorkspaceCockpit` vs `ComposerCockpit`
1. **Path file masing-masing**:
   - [`src/Hero.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/Hero.jsx#L1-L154) vs [`src/components/cockpit/DynamicHero.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/cockpit/DynamicHero.jsx#L1-L110)
   - [`src/components/cockpit/WorkspaceCockpit.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/cockpit/WorkspaceCockpit.jsx#L1-L147) vs [`src/components/cockpit/ComposerCockpit.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/cockpit/ComposerCockpit.jsx#L1-L92)
2. **Komponen mana yang benar-benar digunakan**: `src/Hero.jsx` is rendered at `ChatPage.jsx:572`; `ComposerCockpit.jsx` is rendered at `ChatPage.jsx:755`.
3. **Komponen mana yang lama atau yatim**: `DynamicHero.jsx` is imported in `ChatPage.jsx:77` (and `heroModel` is computed via `useCockpitData()` at `L239`), **but never rendered in JSX**! `WorkspaceCockpit.jsx` is completely unimported.
4. **Perbedaan perilaku dan tampilan**: `Hero.jsx` shows a static greeting (`"Halo, aku AIRA"`) and 4 hardcoded prompt cards; `DynamicHero.jsx` shows time-of-day and connection-state-aware greetings.
5. **Risiko kebingungan saat maintenance**: `ChatPage.jsx` runs `useCockpitData()` (polling `/api/connections` every 5s) to compute `heroModel` that is never used.
6. **Komponen mana yang sebaiknya dipertahankan**: Either render `DynamicHero` in `ChatPage.jsx:572` (replacing `Hero.jsx`) or remove `DynamicHero` + `WorkspaceCockpit`.
7. **Rencana konsolidasi**: Replace `<Hero>` with `<DynamicHero>` in `ChatPage.jsx:572` and delete `src/Hero.jsx` and `src/components/cockpit/WorkspaceCockpit.jsx`.

### Duplicate Group 5: Login & Registration Views (`LoginPage`, `AdminLoginPage`, `LoginModal`, `LoginRequiredModal`, `RegisterModal`)
1. **Path file masing-masing**:
   - [`src/pages/LoginPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/LoginPage.jsx#L1-L297)
   - [`src/pages/AdminLoginPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/AdminLoginPage.jsx#L1-L267)
   - [`src/components/auth/LoginModal.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/auth/LoginModal.jsx#L1-L149)
   - [`src/components/auth/LoginRequiredModal.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/auth/LoginRequiredModal.jsx#L1-L104)
   - [`src/components/auth/RegisterModal.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/auth/RegisterModal.jsx#L1-L167)
2. **Komponen mana yang benar-benar digunakan**: Only `src/pages/LoginPage.jsx` (rendered by `AuthenticatedGate` in `App.jsx:319`).
3. **Komponen mana yang lama atau yatim**: `LoginRequiredModal.jsx` and `RegisterModal.jsx` are completely unimported; `AdminLoginPage.jsx` is shadowed by `AccessDeniedView` (`App.jsx:282`); `LoginModal.jsx` is mounted inside `AuthenticatedGate` where the user is already authenticated.
4. **Perbedaan perilaku dan tampilan**: `LoginRequiredModal` and `RegisterModal` reference removed guest/registration methods (`continueAsGuest`, `POST /api/v1/auth/register`).
5. **Risiko kebingungan saat maintenance**: Five separate auth UIs when only `LoginPage.jsx` is active.
6. **Komponen mana yang sebaiknya dipertahankan**: `src/pages/LoginPage.jsx`.
7. **Rencana konsolidasi**: Delete `LoginRequiredModal.jsx`, `RegisterModal.jsx`, `LoginModal.jsx`, and `AdminLoginPage.jsx`.

### Duplicate Group 6: Voice Overlays & Hooks (3 Competing Voice Subsystems)
1. **Path file masing-masing**:
   - Inline Chat Voice: [`src/components/VoiceControls.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/VoiceControls.jsx) + [`src/hooks/useVoice.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/hooks/useVoice.js)
   - Dead Call Overlay: [`src/components/VoiceOverlay.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/VoiceOverlay.jsx) + [`src/hooks/useVoiceCall.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/hooks/useVoiceCall.js)
   - Global Companion: [`src/components/voice/VoiceCompanionHost.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/voice/VoiceCompanionHost.jsx) (`VoiceCompanionPill.jsx`, `VoiceCompanionOverlay.jsx`) + [`src/hooks/useVoiceCompanion.js`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/hooks/useVoiceCompanion.js)
2. **Komponen mana yang benar-benar digunakan**: `VoiceControls.jsx` (in `ChatPage.jsx:741`) and `VoiceCompanionHost.jsx` (in `App.jsx:334`).
3. **Komponen mana yang lama atau yatim**: `VoiceOverlay.jsx` and `useVoiceCall.js` are mounted in `ChatPage.jsx:536` but `voiceCall.startCall` has **zero call sites**, so it can never open!
4. **Perbedaan perilaku dan tampilan**: All 3 hooks duplicate browser `SpeechRecognition` and call non-existent `/api/voice/synthesize` or `/api/voice/tts`.
5. **Risiko kebingungan saat maintenance**: High — two active voice loops (`useVoice` and `useVoiceCompanion`) can compete for the browser microphone simultaneously.
6. **Komponen mana yang sebaiknya dipertahankan**: `VoiceControls.jsx` (`useVoice.js`) + `VoiceCompanionHost.jsx` (`useVoiceCompanion.js`) sharing a single unified voice service hook.
7. **Rencana konsolidasi**: Remove `VoiceOverlay.jsx` and `useVoiceCall.js` from `ChatPage.jsx` and delete them.

### Duplicate Group 7: Memory & Persona Settings Views (`SettingsPage.jsx` vs `MemoryPage.jsx` & `PersonaPage.jsx`)
1. **Path file masing-masing**:
   - [`src/pages/SettingsPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/SettingsPage.jsx#L520-L675) (`Memory` tab & ~250 lines of dead `Persona` modal code at `L83-110, 288-380, 1262-1415`)
   - [`src/pages/MemoryPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/MemoryPage.jsx#L1-L492) & [`src/pages/PersonaPage.jsx`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/pages/PersonaPage.jsx#L1-L399)
2. **Komponen mana yang benar-benar digunakan**: `SettingsPage.jsx` embeds `<PersonaPanel />` (`PersonaPage.jsx`) at `L670`, while rendering its own inline Memory UI (`L520-665`). `MemoryPage.jsx` is only reachable via voice command.
3. **Komponen mana yang lama atau yatim**: Lines `83-110, 288-380, 1262-1415` in `SettingsPage.jsx` (dead persona modal) and standalone `MemoryPage.jsx`.
4. **Perbedaan perilaku dan tampilan**: `SettingsPage.jsx:256` sends `importance` as `1–100` (`{m.importance}/100`), whereas `MemoryPage.jsx:119` sends `0.1–1.0` and displays `Math.round(m.importance * 100)%` (causing `70` to display as `7000%`!).
5. **Risiko kebingungan saat maintenance**: Data scale corruption between the two Memory UIs and 250+ lines of dead persona code inside `SettingsPage.jsx`.
6. **Komponen mana yang sebaiknya dipertahankan**: `PersonaPage.jsx` and a single unified Memory component using a normalized `0.0–1.0` (or `1–100`) scale.
7. **Rencana konsolidasi**: Delete dead persona state/modals from `SettingsPage.jsx` and embed a single unified `MemoryPanel` component.

---

## 3. UI Interaction Audit (Section C)

1. **Uncaught `ReferenceError` Crash on SNMP Wizard Completion (`src/pages/NmsPage.jsx:972` — `CONFIRMED`)**:
   - `<SnmpSetupWizardModal>` (`NmsPage.jsx:968-975`) defines `onSuccess={() => { setShowWizardModal(false); refreshAll(); }}`.
   - `refreshAll` does **not** exist in `NmsPage.jsx` (the function is named `fetchAllData` at `L232`). Completing the wizard crashes the page!
2. **Broken Mobile Menu Button on `TopologyPage` (`src/pages/TopologyPage.jsx:833` — `CONFIRMED`)**:
   - Passes `onOpenMenu={onOpenMenu}` to `<TopBar>`, whereas `src/components/TopBar.jsx:36,41` expects `onMenuClick`.
3. **Double Header Bar in `InfrastructurePage` (`src/pages/InfrastructurePage.jsx:130-197` — `CONFIRMED`)**:
   - `InfrastructurePage.jsx` renders its own header bar (`L130-191`) AND renders `<TopologyPage>`, `<DevicesPage>`, or `<NmsPage>` (`L195-197`), each of which renders its own `<TopBar>`, stacking two top bars vertically.
4. **Missing SVG Gradient `#link-gradient-physical` (`src/pages/TopologyPage.jsx:1341` vs `src/components/topology/topologyConstants.js:368` — `CONFIRMED`)**:
   - `topologyConstants.js:368` sets `strokeColor = "url(#link-gradient-physical)"`, which is never defined in `<defs>` in `TopologyPage.jsx:1341`.
5. **Blank Badge & Wrong Direction Label in `TopologyEdgeInspector` (`src/components/topology/TopologyEdgeInspector.jsx:153, 221` — `CONFIRMED`)**:
   - Reads `vis.label` and `vis.directional` from `getMultiLayerEdgeVisualConfig()`, which only returns `badge` and `markerEnd`.
6. **Broken Slider State Key Typo in `DecisionsPage` (`src/pages/DecisionsPage.jsx:30` vs `119, 262` — `CONFIRMED`)**:
   - State is initialized with `rollback_Readiness: 2` (capital `R` at `L30`), while the slider (`L262`) and submit handler (`L119`) read `simForm.rollback_readiness` (`undefined`).
7. **Unreachable `"subscription"` and `"token_usage"` Tabs in `SettingsPage` (`src/pages/SettingsPage.jsx:468-475, 961-1093` — `CONFIRMED`)**:
   - Both tabs are fully written in JSX (`L961-1093`) and fetched on mount (`L195-197`), but omitted from `RAW_TABS` (`L468-475`).
8. **Button Without Handler in `CustomerPortalPage` (`src/pages/CustomerPortalPage.jsx:297` — `CONFIRMED`)**:
   - The `<Filter /> Filter` button in the Devices tab has no `onClick` prop.

---

## 4. State Management & Data Synchronization Audit (Section D)

1. **Unread Chat Session Badge Permanently Broken (`src/App.jsx:332` & `src/context/ChatRuntimeContext.jsx:280` — `CONFIRMED`)**:
   - `App.jsx:332` mounts `<ChatRuntimeProvider isOnChatPage={true}>` above `AppShell`. Because `isOnChatPage` is hardcoded to `true`, `ChatRuntimeContext.jsx:280` (`if (!isOnChatPageRef.current || activeIdRef.current !== sid)`) never marks the active session as unread when the user is on another page.
2. **Duplicate 5-Second Polling of `/api/connections` (`CONFIRMED`)**:
   - `src/components/connection/ConnectionIndicator.jsx:33` (in `TopBar`) and `src/hooks/useCockpitData.js:90` (in `ChatPage`) both independently poll `api.connections.list()` every 5,000 ms.
3. **Global `window.fetch` Monkey-Patch Token Leak (`src/api.js:3-20` — `CONFIRMED`)**:
   - `src/api.js:3-20` monkey-patches `window.fetch` to inject `localStorage.getItem("aira_auth_token")` into all `/api` requests, contaminating `CustomerPortalPage.jsx` when `aira_portal_token` is unset.

---

## 5. Frontend Runtime, Bundle & Performance Audit (Section E)

1. **`streamBatcher` Instantiated But Never Used (`src/context/ChatRuntimeContext.jsx:43, 203-209, 253-270` — `CONFIRMED`)**:
   - `ChatRuntimeContext.jsx` creates a `requestAnimationFrame` token batcher (`batcherRef.current = createStreamBatcher(...)` at `L203`), **but never calls `batcherRef.current.push()`**! Every incoming WebSocket `stream_chunk` triggers a synchronous React state update across the chat tree.
2. **Eager Main Bundle Bloat (`src/App.jsx:23` -> `ChatPage.jsx` -> `Markdown.jsx`)**:
   - Because `ChatPage.jsx` is imported eagerly and statically imports `MessageBubble.jsx` -> `Markdown.jsx`, heavy libraries (`mermaid`, `katex`, `leaflet`, `dompurify`) are bundled into the initial synchronous load instead of being lazy-loaded when code/map/math blocks appear.
3. **PWA Service Worker Stale Cache-First Trap (`public/service-worker.js:1-38` — `CONFIRMED`)**:
   - Uses Cache-First (`caches.match(event.request).then((cached) => cached || fetch(event.request))`) for `/` and `/index.html`, serving stale HTML referencing deleted Vite chunk hashes after deployments.

---

## 6. Visual Consistency & UX Audit (Section F)

- **Three Competing Theme Token Definitions**:
  1. `src/index.css:6-52` + `tailwind.config.js:10-49` (Active cyan/purple dark glassmorphism `--bg-main: #03060c`, `--accent-primary: #38bdf8`).
  2. `src/components/cockpit/tokens.js` (`COCKPIT_VARS` inline styles `--ck-bg`, `--ck-text`).
  3. `src/theme/{colors,radius,shadow,spacing,typography,index}.js` (5 unused JS files defining a completely different `#FF4D8D` pink sakura theme).
