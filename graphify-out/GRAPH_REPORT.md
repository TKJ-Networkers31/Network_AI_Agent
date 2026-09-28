# Graph Report - agent_ai  (2026-09-27)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 5518 nodes · 13241 edges · 232 communities (186 shown, 46 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 729 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f5a8862e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- VisionResult
- attachments/engine.py
- Attachment
- EventBus
- cockpitContracts.js
- validate_manifest_data
- test_runtime_state.py
- react
- host/detector.py
- ChatPage.jsx
- dataclasses
- pathlib
- RuntimeStateEngine
- .stream
- location.py
- test_streaming.py
- TaskClassification
- CapabilityDiscovery
- runLifecycle.js
- GoogleMapsProvider
- Event
- cockpitAdapter.js
- ExternalContextError
- test_context_semantic_memory.py
- greetingResolver.js
- artifacts/tests/test_engine.py
- provider_client.py
- ProviderCapabilities
- GoogleMapsConfig
- brain.py
- FieldRenderer.jsx
- test_manifest_loader.py
- api/main.py
- conversation_context.py
- load_manifest
- AttachmentEngine
- core/chat_sessions.py
- files.py
- event_scope
- CapabilityRegistry
- SelectionContext
- test_semantic_memory.py
- rec
- IncrementalResponseParser
- Artifact
- network_tools.py
- AttachmentEngineTestBase
- validate_plugin_manifest
- unified_context/builder.py
- App.jsx
- artifacts/__init__.py
- typing
- Sidebar.jsx
- Capability
- InteractionMemory
- QueryResult
- test_workspace_and_operations.py
- _builder
- ContextBuilder
- InteractionSchema
- core/providers.py
- capability/__init__.py
- persona/engine.py
- plugins/loader.py
- time
- call_model
- VoiceIO
- plugins/validator.py
- MemoryRecord
- ImageVisionEngine
- make_builder
- ConversationMemory
- unittest
- persona/context.py
- SelectionBuilder
- extract_image_dimensions
- .session
- list_capabilities
- _cap
- WorkspaceIntegrationService
- .memory
- artifacts.py
- DocumentSpec
- ModelStore
- chat.py
- workspace/WorkspacePage.jsx
- Plugin
- long_term.py
- routers/models.py
- test_frontend_and_integration.py
- load_persona_config
- AIRA_ECOSYSTEM/core/memory.py
- routers/persona.py
- WebSocketEventBridge
- LocationPanel.jsx
- context/builder.py
- persona/loader.py
- connection_manager.py
- package.json
- Markdown.jsx
- MessageBubble.jsx
- .store
- TestBrainIntegration
- vision/detector.py
- InvalidRequestError
- attachments.py
- AIRAContext
- core/dio/__init__.py
- model_registry.py
- test_persona_engine.py
- ConnectionManager
- WorkspacePage
- test_conversation_context.py
- test_location_flow.py
- GlobalSettingsStore
- test_context_builder.py
- TestRetriever
- log_store.py
- ConversationMemory
- ArtifactEngine
- WorkspaceLink
- TestCallModelStreaming
- global_settings.py
- workspace_links.py
- ModelsPage.jsx
- DefaultEmbeddingProvider
- semantic_memory/models.py
- _FakeAttachment
- TestRealIncrementalDelivery
- EventNames
- importance_score
- agent/main.py
- createStreamBatcher
- HistoryEngine
- FileOperations
- setup_logging
- snmp/client.py
- PersistentShell
- dio_tools.py
- InteractionPlan
- fs_tools.py
- ToolBinding
- SemanticMemory
- run_chat.py
- UnifiedContext
- workspace_links/models.py
- workspace_links/service.py
- WorkspaceLinkStore
- connections.py
- tts.py
- ws.py
- BootGate.jsx
- SpreadsheetSpec
- DIOAnalyzer
- logging
- TempStoreCase
- ctx_for
- routeros.py
- memory_store/chat_sessions.py
- Renderer.jsx
- Brain
- select_mode
- TestNoDuplicateInjection
- run
- theme/index.js
- WorkspaceManager
- TrashEngine
- build_context_packet
- make_builder
- manifest.json
- GraphBlock.jsx
- TestSessionIsolation
- TestSummary
- selection.py
- routers/vision.py
- modelRouter.d.ts
- validate_name
- format_semantic_memories
- TestBrainStreamFlag
- compilerOptions
- cosine_similarity
- settings.py
- stream_enabled_for_turn
- _clean
- TestSerialization
- TestWorkspaceToConversation
- TestSeparationOfConcerns
- Scheduler
- Timer
- dependencies
- DIO
- TestWindowsAdapter
- SelectionResult
- ChatInput
- ConnectionManager
- devDependencies
- TestPublicApiAndConstraints
- ConnectionSession
- LocationPermissionField.jsx
- replace_capability
- CapabilityHeroRow (1).jsx
- WorkspaceToolbar.jsx
- SearchResult
- core/persona.py
- FakeClock
- useAiraSocket.js
- service-worker.js
- AIRA_ECOSYSTEM/tests/__init__.py
- d_data_agent_ai_tools_memory_store_py
- test_ssh.py

## God Nodes (most connected - your core abstractions)
1. `EventBus` - 85 edges
2. `validate_manifest_data()` - 78 edges
3. `Attachment` - 74 edges
4. `GoogleMapsProvider` - 73 edges
5. `Capability` - 63 edges
6. `valid()` - 63 edges
7. `react` - 59 edges
8. `SelectionContext` - 55 edges
9. `fields()` - 55 edges
10. `CapabilityRegistry` - 50 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `VoiceIO`  [INFERRED]
  _legacy_backup_20260910_143345/agent/main.py → AIRA_ECOSYSTEM/agents/yuki/voice_io.py
- `ImageVisionEngine` --uses--> `ImageMetadata`  [INFERRED]
  AIRA_ECOSYSTEM/core/vision/engine.py → AIRA_ECOSYSTEM/core/vision/models.py
- `TestGetImageMetadata` --uses--> `ImageMetadata`  [INFERRED]
  AIRA_ECOSYSTEM/core/vision/tests/test_engine.py → AIRA_ECOSYSTEM/core/vision/models.py
- `ImageVisionEngine` --uses--> `VisionResult`  [INFERRED]
  AIRA_ECOSYSTEM/core/vision/engine.py → AIRA_ECOSYSTEM/core/vision/models.py
- `FakeAvailableProvider` --uses--> `VisionResult`  [INFERRED]
  AIRA_ECOSYSTEM/core/vision/tests/test_engine.py → AIRA_ECOSYSTEM/core/vision/models.py

## Import Cycles
- 3-file cycle: `AIRA_ECOSYSTEM/core/persona/__init__.py -> AIRA_ECOSYSTEM/core/persona/context.py -> AIRA_ECOSYSTEM/core/persona/loader.py -> AIRA_ECOSYSTEM/core/persona/__init__.py`
- 4-file cycle: `AIRA_ECOSYSTEM/core/persona/__init__.py -> AIRA_ECOSYSTEM/core/persona/engine.py -> AIRA_ECOSYSTEM/core/persona/presets.py -> AIRA_ECOSYSTEM/core/persona/loader.py -> AIRA_ECOSYSTEM/core/persona/__init__.py`
- 5-file cycle: `AIRA_ECOSYSTEM/core/persona/__init__.py -> AIRA_ECOSYSTEM/core/persona/engine.py -> AIRA_ECOSYSTEM/core/persona/prompt_builder.py -> AIRA_ECOSYSTEM/core/persona/context.py -> AIRA_ECOSYSTEM/core/persona/loader.py -> AIRA_ECOSYSTEM/core/persona/__init__.py`

## Communities (232 total, 46 thin omitted)

### Community 0 - "VisionResult"
Cohesion: 0.06
Nodes (43): build_visual_context_packet(), image_metadata_from_attachment(), Any, core/vision/context.py — visual context packet untuk Image & Visual Input…, Attachment (+ key 'image' pada metadata bag-nya, diisi…, Satu baris, aman dimasukkan ke `text` ContextSection JIKA caller memilih…, Payload siap-pakai untuk ContextSection(**packet), begitu caller memutuskan…, visual_placeholder_text() (+35 more)

### Community 1 - "attachments/engine.py"
Cohesion: 0.05
Nodes (43): core/attachments/constants.py - Universal Attachment vocabulary (Sprint 2.7 /…, core/attachments/context.py - Context boundary for Universal Attachment (Sprint…, AttachmentAccessError, _default_trash_delete(), Exception, core/attachments/engine.py - AttachmentEngine (Sprint 2.7 / Wave 1 / W2).…, Raised (caught internally, never propagated past AttachmentResult call sites…, Move a file the engine itself materialized into Trash (never a permanent… (+35 more)

### Community 2 - "Attachment"
Cohesion: 0.05
Nodes (24): Insert or update (id is the natural key - re-saving the same id overwrites;…, attachment_to_context_dict(), attachments_context_section(), attachments_context_summary_text(), Any, Attachment -> metadata/reference dict, safe to place in a ContextSection's…, Optional short human-readable line per attachment (name + type + status) - for…, Ready-to-use payload for a ContextSection: {"data": {...}, "text": "..."}.… (+16 more)

### Community 3 - "EventBus"
Cohesion: 0.04
Nodes (25): current_event_context(), EventBus, AbstractEventLoop, Salinan konteks event aktif ({} kalau tidak ada)., Publish/subscribe Event Bus yang thread-safe. Tanggung jawab: publish,…, Daftarkan event loop utama (FastAPI). Subscriber async akan dijadwalkan ke loop…, Lepas binding (hanya kalau `loop` cocok, atau loop=None)., Hapus subscriber berdasarkan token. True kalau ada yang dihapus. (+17 more)

### Community 4 - "cockpitContracts.js"
Cohesion: 0.07
Nodes (55): ActivityChip(), ACTIVITY_STATE, activityFromConnections(), buildHeroContext(), CONNECTION_STATUS, connectionsFromApi(), DEFAULT_WORKSPACE_LABEL, deriveActivityState() (+47 more)

### Community 5 - "validate_manifest_data"
Cohesion: 0.07
Nodes (18): Return pesan error, atau None kalau valid. Lihat tata bahasa di docstring modul., Validasi OTORITATIF atas raw mapping (mis. ManifestLoadResult.raw). strict=True…, validate_manifest_data(), validate_version_constraint(), fields(), Salinan VALID dengan override. Nilai _DROP menghapus key., TestValidatorApiVersion, TestValidatorAuthor (+10 more)

### Community 6 - "test_runtime_state.py"
Cohesion: 0.09
Nodes (23): assert_invariant(), listen_start(), listen_stop(), make(), tests/test_runtime_state.py — unit test Runtime State Engine (Sprint 2 / Worker…, state resmi HARUS sama dengan hasil prioritas dari jumlah aktivitas., Urutan event NYATA satu giliran (Brain + Planner), satu correlation_id., (bus, engine, clock, events) - engine sudah start; events =… (+15 more)

### Community 7 - "react"
Cohesion: 0.06
Nodes (34): api, ConnectionIndicator(), formatDuration(), ConnectionCard(), ConnectionPanel(), handleClose(), load(), formatClock() (+26 more)

### Community 8 - "host/detector.py"
Cohesion: 0.06
Nodes (32): detect_host(), _detect_os_name(), get_default_adapter(), get_host_adapter(), get_host_info(), core/host/detector.py — deteksi otomatis host (Windows/Linux) untuk HAL. SATU-…, Kembalikan adapter (Windows/Linux) sesuai HostInfo (Dependency Injection) -…, Singleton - deteksi host sekali per proses. (+24 more)

### Community 9 - "ChatPage.jsx"
Cohesion: 0.06
Nodes (34): BootScreen(), CapabilityButton(), CapabilityDock(), CapabilityHeroRow(), CapabilityIcon(), ICONS, CapabilityInputSlot(), FileCapabilityActions() (+26 more)

### Community 10 - "dataclasses"
Cohesion: 0.08
Nodes (19): core/location/ — lokasi HOSTING (tempat AIRA berjalan) dan lokasi AKSES (tempat…, compose_label(), LocationContext, _num(), core/location/models.py — bentuk data lokasi AIRA. Dua peran lokasi: host ->…, _ClientState, LocationService, core/location/service.py — LocationService: lokasi HOSTING + lokasi AKSES.… (+11 more)

### Community 11 - "pathlib"
Cohesion: 0.08
Nodes (40): core/artifacts/engine.py - ArtifactEngine (Sprint 2.7 / W5). LLM -> structured…, ensure_parent(), GenerationError, Exception, Path, core/artifacts/generators/base.py - shared contract for artifact generators., Raised by a generator when it cannot produce output for an otherwise validated…, generate_csv() (+32 more)

### Community 12 - "RuntimeStateEngine"
Cohesion: 0.07
Nodes (30): get_runtime_state(), Any, core/runtime_state/engine.py — Runtime State Engine (Sprint 2 / Worker 3).…, Dependency Injection: bus, clock, dan batas kedaluwarsa bisa disuntik (test…, Subscribe ke Event Bus. Idempotent., Lepas semua subscription. State & owner dibiarkan apa adanya., Potret state saat ini (sekaligus membuang aktivitas yang kedaluwarsa)., Buang semua aktivitas dan paksa IDLE (mis. sesudah error tak terduga). (+22 more)

### Community 13 - ".stream"
Cohesion: 0.09
Nodes (16): Streaming NYATA. on_delta(text) dipanggil untuk tiap potongan teks yang BARU…, Collector, FakeStreamResponse, nd(), oa(), patch_post(), SSE OpenAI-compatible: 'data: {...}' + baris kosong; opsional [DONE]., Satu chunk chat.completion.chunk. (+8 more)

### Community 14 - "location.py"
Cohesion: 0.06
Nodes (50): agents/rei/research_tools.py — wrapper tipis di atas tools/web.…, web_fetch(), web_image_search(), web_search(), AccessReportRequest, _client_ip(), detect_host(), get_host() (+42 more)

### Community 15 - "test_streaming.py"
Cohesion: 0.07
Nodes (18): Planner, BusRecorder, fail_with(), step(), FakeMemory, FakeTracker, tests/test_streaming.py — unit test backend streaming (Sprint 2.5). Cakupan: 1.…, Langkah call_model palsu yang bersikap seperti provider streaming. (+10 more)

### Community 16 - "TaskClassification"
Cohesion: 0.07
Nodes (18): Hasil aman kalau parsing/panggilan classifier gagal., TaskClassification, parse_classification(), Parse output LLM. Tidak pernah raise., TaskClassifier, _to_bool(), FakeClassifier, EventCapture (+10 more)

### Community 17 - "CapabilityDiscovery"
Cohesion: 0.06
Nodes (15): Every param the frontend already sends must be accepted without raising, even…, _registry_with_ui_areas(), TestAcceptsFrontendQueryParams, TestEmptyRegistry, CapabilityDiscovery, DiscoverySettings, Compute effective state for every REGISTERED capability (optionally pre-…, True only if the capability resolves all the way to ENABLED. (+7 more)

### Community 18 - "runLifecycle.js"
Cohesion: 0.09
Nodes (40): ChatRuntimeContext, ChatRuntimeProvider(), makeRunId(), buildWsUrl(), useAiraSocketPool(), appendChunk(), applyAck(), applyChunkToRun() (+32 more)

### Community 19 - "GoogleMapsProvider"
Cohesion: 0.11
Nodes (18): GoogleMapsProvider, GoogleMapsTimeout, Exception, Raised by a fetcher to signal a timeout distinctly from other transport…, Google Maps Platform adapter. Construction never raises - an unconfigured…, Read-only access for callers that want to display configuration state (e.g. a…, _config(), core/external_context/tests/test_google_maps.py — unit tests for the Google… (+10 more)

### Community 20 - "Event"
Cohesion: 0.07
Nodes (31): Event bus -> (session_id, payload WebSocket), atau None kalau event ini tidak…, Subscriber sync: cepat, tidak pernah blocking., Event, json_safe(), publish_event(), publish_event_async(), Any, Kembalikan salinan `value` yang PASTI bisa di-JSON-kan. Objek yang tidak… (+23 more)

### Community 21 - "cockpitAdapter.js"
Cohesion: 0.08
Nodes (38): FIELDS, GlobalSettingsPanel(), commit(), useCockpitData(), applyGlobalSettingsUpdate(), EMPTY, ensureLoaded(), fetchSnapshot (+30 more)

### Community 22 - "ExternalContextError"
Cohesion: 0.08
Nodes (15): _clean(), ExternalContextError, NormalizedPlace, NormalizedRoute, One leg/step of a route. Kept intentionally small (provider-neutral turn-by-…, Provider-agnostic route shape. `origin`/`destination` are echoed back as given…, Provider-agnostic error shape. `code` MUST be one of…, Drop None-valued keys - consistent with core/dio/models.py::_clean and… (+7 more)

### Community 23 - "test_context_semantic_memory.py"
Cohesion: 0.10
Nodes (16): Base, BrokenProvider, bullets(), FakeClock, KeywordProvider, make_builder(), tests/test_context_semantic_memory.py — integrasi Semantic Memory ->…, Embedding palsu 4-dimensi: jumlah kemunculan kata kunci. Hasil bisa dihitung… (+8 more)

### Community 24 - "greetingResolver.js"
Cohesion: 0.10
Nodes (40): buildGreeting(), resolveHour(), seedIndex(), TEMPLATES, ACTIVITY_STATE, buildGreetingContext(), cleanText(), DEFAULT_GREETING_SETTINGS (+32 more)

### Community 25 - "artifacts/tests/test_engine.py"
Cohesion: 0.08
Nodes (17): ArtifactStatus, ArtifactType, Enum, str, core/artifacts/models.py - data contract for the Artifact & Document Engine…, SlideSection, ArtifactEngineTestBase, _doc_spec() (+9 more)

### Community 26 - "provider_client.py"
Cohesion: 0.10
Nodes (41): _attempt(), call(), _call_sink(), _cancelled_result(), _chat_ollama(), _chat_ollama_stream(), _chat_openai_compatible(), _chat_openai_stream() (+33 more)

### Community 27 - "ProviderCapabilities"
Cohesion: 0.06
Nodes (16): ProviderCapabilities, ProviderIdentity, Who a provider is. `name` is the stable machine id (e.g. 'google_maps') used as…, What capability names (constants.CAPABILITY_*) a provider implements.…, TestProviderCapabilities, TestProviderIdentity, BrokenProvider, DummyProvider (+8 more)

### Community 28 - "GoogleMapsConfig"
Cohesion: 0.08
Nodes (24): capability_from_provider(), capability_id_for(), Remove every Capability previously registered for this provider. Returns the…, e.g. ('google_maps', 'location.search') ->…, One provider capability name -> one W1 Capability. Pure - does not touch the…, Register one Capability per capability the provider declares…, register_provider_capabilities(), unregister_provider_capabilities() (+16 more)

### Community 29 - "brain.py"
Cohesion: 0.09
Nodes (20): Dry-run: klasifikasi + pilih model untuk sebuah prompt (memanggil LLM…, route_preview(), core/brain.py — satu-satunya pintu masuk publik ke AIRA. Flow: prompt ->…, Ringkasan tool (nama + kategori) untuk tool_context - bukan skema penuh., Snapshot Runtime State (JSON-safe) untuk section runtime_state di konteks., _runtime_snapshot(), _tool_summary(), get_model_policy() (+12 more)

### Community 30 - "FieldRenderer.jsx"
Cohesion: 0.06
Nodes (21): ButtonField(), STYLE_CLASSES, CheckboxField(), DateField(), DividerField(), FileField(), GalleryField(), ImageField() (+13 more)

### Community 31 - "test_manifest_loader.py"
Cohesion: 0.10
Nodes (30): core/plugins/ — Phase 1 Plugin Foundation (AKANE_PLUGIN_SPEC.md, Phase 1).…, _author_from_dict(), _compatibility_from_dict(), _dependencies_from_list(), _dependency_from_dict(), load_and_validate_manifest(), Any, core/plugins/manifest.py — Phase 1 Plugin Foundation: manifest parsing.… (+22 more)

### Community 32 - "api/main.py"
Cohesion: 0.08
Nodes (35): health(), get, on_event, api/main.py — entry point FastAPI untuk AIRA. Jalankan dari root…, (SPRINT 2.7.1 P0.1) Populate the Capability Registry so GET /api/capabilities…, _shutdown_connections(), _shutdown_event_bridge(), _startup_capability_registry() (+27 more)

### Community 33 - "conversation_context.py"
Cohesion: 0.09
Nodes (27): _clean_limit(), _clean_session_id(), ConversationContext, item(), _default_connect(), _digest(), _keywords(), Any (+19 more)

### Community 34 - "load_manifest"
Cohesion: 0.12
Nodes (7): load_manifest(), File YAML -> raw mapping + PluginManifest. Tidak pernah raise; tidak…, TempCase, TestLoaderDoesNotValidate, TestLoaderStructuredErrors, TestLoaderSuccess, TestLoaderThenValidator

### Community 35 - "AttachmentEngine"
Cohesion: 0.08
Nodes (20): Lazy import - default only. Resolves through the REAL AIRA Workspace sandbox…, Best-effort publish to the EXISTING Event Bus. Never raises - same defensive…, AttachmentEngine, _default_resolve_path(), _publish(), Any, Path, User-uploaded file: bytes are written into the AIRA Workspace (under… (+12 more)

### Community 36 - "core/chat_sessions.py"
Cohesion: 0.10
Nodes (40): SATU-SATUNYA jalur memproses submission form/izin: efek samping + penyusunan…, resolve_submission(), chat(), get_active_session(), get_messages(), list_sessions(), get, Mengembalikan sesi yang terakhir dipakai (sudah urut by updated_at DESC di… (+32 more)

### Community 37 - "files.py"
Cohesion: 0.11
Nodes (38): CopyRequest, DeleteRequest, files_copy(), files_delete(), files_history(), files_history_restore(), files_mkdir(), files_move() (+30 more)

### Community 38 - "event_scope"
Cohesion: 0.09
Nodes (12): event_scope(), Tempelkan konteks ke semua event yang dipublish di dalam blok ini. with…, TestToolAdapter, FakeSender, make_bridge(), tests/test_ws_bridge.py — unit test bridge Event Bus -> WebSocket (Worker 1).…, TestDelivery, worker() (+4 more)

### Community 39 - "CapabilityRegistry"
Cohesion: 0.07
Nodes (20): capability_from_tool_schema(), core/capability/integration.py — integration boundary between the Capability…, One OpenAI-style tool schema entry (the shape AGENT_TOOL_SCHEMAS already uses:…, Bridge AGENT_TOOL_SCHEMAS (+ AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS from…, register_tool_capabilities(), tool_capability_id(), CapabilityUIMetadata, Presentation hints only - the frontend is never the source of truth for what a… (+12 more)

### Community 40 - "SelectionContext"
Cohesion: 0.09
Nodes (10): Satu 'seleksi' user atas sebagian teks pesan/percakapan., SelectionContext, Connection, Path, Row, SelectionStore, TestSelectionStore, TestSerialization (+2 more)

### Community 41 - "test_semantic_memory.py"
Cohesion: 0.10
Nodes (26): core/semantic_memory/defaults.py — konstanta & bobot bawaan Semantic Memory…, EmbeddingProvider, ABC, core/semantic_memory/embedder.py — antarmuka embedding + implementasi bawaan…, Kontrak provider embedding: teks -> vektor float., Ubah `text` menjadi vektor. Panjang vektor harus konsisten per provider., core/semantic_memory/ — Semantic Memory (Sprint 2.4). Menyimpan fakta penting…, Satu hasil retrieval. similarity : cosine similarity query vs record (-1..1)… (+18 more)

### Community 42 - "rec"
Cohesion: 0.11
Nodes (5): session_id & text wajib; field lain memakai default kalau hilang., rec(), TestModels, TestStore, worker()

### Community 43 - "IncrementalResponseParser"
Cohesion: 0.12
Nodes (18): BLOCK_KIND, blockKindOf(), canSplit(), definitelySplits(), detectFenceKind(), holdPartial(), IncrementalResponseParser, indentOf() (+10 more)

### Community 44 - "Artifact"
Cohesion: 0.10
Nodes (12): Artifact, One generated file. `storage_reference` is a path RELATIVE to the AIRA…, ArtifactStore, get_artifact_store(), Connection, Path, Row, core/artifacts/store.py - SQLite persistence for Artifact metadata (Sprint 2.7… (+4 more)

### Community 45 - "network_tools.py"
Cohesion: 0.09
Nodes (30): get_arp(), get_dhcp_client(), get_dhcp_server(), get_dns(), get_firewall(), get_identity(), get_interfaces(), get_ip_addresses() (+22 more)

### Community 46 - "AttachmentEngineTestBase"
Cohesion: 0.06
Nodes (7): AttachmentEngineTestBase, TestAssociateAndDelete, TestCreateExternal, TestCreateFromArtifact, TestCreateFromWorkspace, TestMarkFailed, TestReadAndAccessControl

### Community 47 - "validate_plugin_manifest"
Cohesion: 0.11
Nodes (7): manifest_from_dict(), dict -> PluginManifest. Toleran: field hilang/rusak -> default aman, tidak…, Validasi objek PluginManifest (representasi kanonik) dengan skema yang sama…, validate_plugin_manifest(), PluginManifest = representasi kanonik: api_version/capabilities/permissions…, TestManifestAlignment, TestValidatePluginManifestObject

### Community 48 - "unified_context/builder.py"
Cohesion: 0.11
Nodes (19): _artifact_item(), _attachment_item(), _default_attachments(), _default_context_builder(), get_unified_context_builder(), Any, core/unified_context/builder.py — UnifiedContextBuilder (Sprint 2.7 / Wave 2 /…, Dependency Injection, same convention as core.context.builder.ContextBuilder… (+11 more)

### Community 49 - "App.jsx"
Cohesion: 0.07
Nodes (17): App(), FIXED_HEIGHT_PAGES, PAGES, readCollapsed(), ErrorBoundary, SessionsProvider(), aira_ecosystem_app_frontend_src_index, ChatPage() (+9 more)

### Community 50 - "artifacts/__init__.py"
Cohesion: 0.12
Nodes (14): core/artifacts/ - Artifact & Document Engine (Sprint 2.7 / W5). LLM ->…, CsvSpec, PresentationSpec, TestCsvGenerator, TestCsvValidation, TestPresentationValidation, core/artifacts/validator.py - structural validation for artifact specs (Sprint…, Dispatch by artifact_type family - used by ArtifactEngine before it ever calls… (+6 more)

### Community 51 - "typing"
Cohesion: 0.10
Nodes (19): agents/akane/session_state.py — struktur data untuk satu sesi koneksi SSH…, load_google_maps_config(), core/external_context/config.py — provider configuration loading (Sprint 2.7 /…, Build a GoogleMapsConfig from the process environment (or an injected mapping,…, _read_timeout(), core/external_context/constants.py — External Context Layer constants (Sprint…, core/external_context/factory.py — provider singleton accessors (Sprint 2.7 /…, _default_fetcher() (+11 more)

### Community 52 - "Sidebar.jsx"
Cohesion: 0.08
Nodes (21): BrandEmblem(), EMBLEM_SCALE, EMBLEM_SRC, MobileNav(), PRIMARY_IDS, PRIMARY_ITEMS, ALL_NAV_ITEMS, NAV_GROUPS (+13 more)

### Community 53 - "Capability"
Cohesion: 0.11
Nodes (11): Capability, Canonical capability representation. See core/capability/constants.py for the…, True if this capability applies to ANY of the given context types.…, Structural validation, same split as core/dio (models build tolerant objects; a…, validate_capability(), Register a new capability. New registrations always start at STATE_REGISTERED…, TestCapabilityDefaults, TestSerializationRoundTrip (+3 more)

### Community 54 - "InteractionMemory"
Cohesion: 0.08
Nodes (7): InteractionMemory, Any, Connection, Path, TestResolveSubmission, TestSensitiveKeys, TestInteractionMemory

### Community 55 - "QueryResult"
Cohesion: 0.14
Nodes (8): One HTTP call -> (json_data, None) on success, or (None, error) on any failure…, Best-effort "what's around here" summary: reverse-geocodes the coordinate for…, QueryResult, Envelope every ExternalContextProvider method returns. Exactly one of (places /…, ExternalContextProvider, Generic dispatcher: capability name -> the matching public method. Used by…, Base class. Public methods (search/lookup/nearby/route/context/execute) are the…, True iff this provider is currently usable (has credentials, etc.) - never…

### Community 56 - "test_workspace_and_operations.py"
Cohesion: 0.11
Nodes (14): PermissionLevel, Enum, str, core/filesystem/models.py — dataclass untuk File System Engine (FSE). Semua…, _normalize(), PermissionEngine, core/filesystem/permissions.py — Permission Engine untuk File System Engine…, Resolusi: cari folder terdaftar PALING SPESIFIK yang menjadi ancestor (atau… (+6 more)

### Community 57 - "_builder"
Cohesion: 0.10
Nodes (14): _builder(), _make_context_builder(), core/unified_context/tests/test_unified_context.py — unit tests for Unified…, core.context.ContextBuilder itself must be completely untouched - building an…, A caller that never passes attachments/selections/artifacts/ permissions (i.e.…, _stub_persona_state(), _stub_prompt_composer(), TestArtifactSourceOnly (+6 more)

### Community 58 - "ContextBuilder"
Cohesion: 0.14
Nodes (16): ContextBuilder, Any, Semua argumen opsional. None = pakai default AIRA. Untuk MEMATIKAN satu sumber,…, task: dict, atau objek dengan .to_dict() (mis. TaskClassification), atau None.…, SATU section memory dari DUA sumber independen (long_term_memory.db dan…, (SPRINT 2.7.1 P0 FIX) Reuse penuh core.attachments.context - tidak ada logic…, Tempelkan snapshot Runtime State ke section runtime_state sebagai DATA. -…, Delegasi ke PersonaEngine (satu-satunya penyusun system prompt). Kalau gagal:… (+8 more)

### Community 59 - "InteractionSchema"
Cohesion: 0.20
Nodes (8): Any, SchemaBuilder, Action, Field, InteractionSchema, Section, core/dio/tests/dio/test_validator.py — unit test SchemaValidator (Phase 2.5).…, TestSchemaValidator

### Community 60 - "core/providers.py"
Cohesion: 0.16
Nodes (26): _preview(), Versi "web" dari agent/core/engine.py. KENAPA FILE TERPISAH, BUKAN EDIT…, Ringkasan singkat hasil tool untuk ditampilkan di timeline frontend (bukan…, Sama seperti run() di engine.py, tapi: - Tidak print apa pun / tidak pernah…, run_web(), _track_usage(), log_error(), log_llm_request() (+18 more)

### Community 61 - "capability/__init__.py"
Cohesion: 0.13
Nodes (18): api/routers/tests/test_capabilities.py — regression tests for GET…, core/capability/constants.py — Capability Layer constants (Sprint 2.7 / W1).…, _AlwaysContains, get_capability_discovery(), core/capability/discovery.py — CapabilityDiscovery (Sprint 2.7 / W1). Turns the…, Sentinel used when available_tools=None: tool_binding checks should pass…, core/capability/ — Capability Layer (Sprint 2.7 / Worker 1). Capability = WHAT…, core/capability/models.py — Capability Layer data contract (Sprint 2.7 / W1).… (+10 more)

### Community 62 - "persona/engine.py"
Cohesion: 0.14
Nodes (16): _connect(), _init_db(), PersonaEngine, Connection, core/persona/engine.py — Persona Engine (Phase 1.3). Satu-satunya modul yang…, Satu-satunya pembuat System Prompt AIRA. REI/planner TIDAK boleh menyusun…, Bentuk gabungan untuk GET /persona - profile + behavior., Dipanggil oleh Chat Session (lewat agents/rei/planner.py) tiap giliran… (+8 more)

### Community 63 - "plugins/loader.py"
Cohesion: 0.12
Nodes (25): _attach_manifest(), _error(), _fail(), _load(), load_manifest_raw(), load_manifest_text(), ManifestErrorCode, ManifestLoadError (+17 more)

### Community 64 - "time"
Cohesion: 0.14
Nodes (16): build_action_request(), _default_message_lookup(), core/selection/builder.py — SelectionBuilder: input mentah -> SelectionContext,…, (request, None) kalau sukses, (None, error) kalau aksi tidak dikenal., message_id di sini adalah id baris chat_turns (lihat…, validate_action(), core/selection/constants.py — konstanta Selection Intelligence (Sprint 2.7 /…, core/selection/ — Selection Intelligence (Sprint 2.7 / Worker 3, W4). Public… (+8 more)

### Community 65 - "call_model"
Cohesion: 0.09
Nodes (19): _extract(), extract_and_save_facts_async(), _safe_run(), agents/rei/auto_extract.py — ekstraksi memori otomatis di background. FIX…, call(), cancelled_result(), emit(), new_stream_sink() (+11 more)

### Community 66 - "VoiceIO"
Cohesion: 0.09
Nodes (14): _get_model(), log_error(), Speech-to-text via faster-whisper (lokal, offline, CPU-only). Kenapa faster-…, audio_int16: numpy array int16 mono (hasil rekaman VAD). Return: string teks…, transcribe(), agents/yuki/stt.py — wrapper Speech-to-Text (faster-whisper)., transcribe(), _frame_rms() (+6 more)

### Community 67 - "plugins/validator.py"
Cohesion: 0.17
Nodes (27): Any, Return pesan error, atau None kalau valid., Return pesan error, atau None kalau valid (semver inti: MAJOR.MINOR.PATCH)., validate_plugin_id(), validate_version(), _check_author(), _check_compatibility(), _check_declarations() (+19 more)

### Community 68 - "MemoryRecord"
Cohesion: 0.13
Nodes (16): MemoryRecord, Satu fakta yang diingat. session_id : pemilik fakta (isolasi sesi). Untuk fakta…, _check_limit(), _load_json(), MemoryStore, Any, Connection, Path (+8 more)

### Community 69 - "ImageVisionEngine"
Cohesion: 0.13
Nodes (9): ImageVisionEngine, Dependency Injection: `attachment_engine` dan `vision_provider` bisa diganti…, _always_true(), FakeAvailableProvider, FakeBoomProvider, ImageVisionEngineTestBase, TestCreateImageAttachment, TestGetImageMetadata (+1 more)

### Community 70 - "make_builder"
Cohesion: 0.10
Nodes (8): FakeTask, make_builder(), wrap(), Mirip TaskClassification: cukup punya to_dict()., Builder dengan semua sumber dipalsukan. overrides: nama sumber -> nilai (None =…, TestBuilderFull, TestBuilderMinimal, TestMissingOptionalContext

### Community 71 - "ConversationMemory"
Cohesion: 0.09
Nodes (15): ConversationMemory, Mencari titik potong yang aman, yaitu tepat sebelum sebuah pesan role="user".…, message: dict lengkap dari respons LLM (bisa berisi role=assistant, content,…, tool_call_id wajib diisi kalau provider yang dipakai adalah API eksternal…, Menyimpan riwayat percakapan (messages) selama satu sesi agar agent bisa…, Mengembalikan messages lengkap (system prompt + history) yang siap dikirim ke…, format_datetime_id(), now() (+7 more)

### Community 72 - "unittest"
Cohesion: 0.08
Nodes (11): core/dio/tests/dio/test_dio_tools_security.py — test validator di…, TestValidatorWired, core/dio/tests/dio/test_interaction_memory.py — unit test InteractionMemory…, tests/test_chat_sessions.py — Sprint 2.5 (Session): isolasi sesi & tidak ada…, SessionStoreCase, TestNoImplicitCreation, TestSessionIsolation, tests/test_global_settings.py — unit tests for the Global Settings Engine… (+3 more)

### Community 73 - "persona/context.py"
Cohesion: 0.14
Nodes (22): _behavior_narrative(), build_persona_context(), _clean(), PersonaContext, Any, core/persona/context.py — PersonaContext: hasil deterministik Persona Engine.…, Isi {placeholder} dalam SATU putaran - nilai user yang memuat "{...}" tidak…, render_template() (+14 more)

### Community 74 - "SelectionBuilder"
Cohesion: 0.14
Nodes (6): SelectionBuilder, fake_lookup(), TestSelectionCreation, fake_lookup(), TestSelectionCreation, MessageLookup

### Community 75 - "extract_image_dimensions"
Cohesion: 0.11
Nodes (11): extract_image_dimensions(), core/vision/metadata.py — ekstraksi dimensi piksel untuk Image & Visual Input…, (width, height) hasil parse header file, atau (None, None) kalau mime_type…, _svg_dimensions(), _make_gif(), _make_jpeg(), _make_png(), _make_svg() (+3 more)

### Community 76 - ".session"
Cohesion: 0.14
Nodes (4): chat(), n giliran bergantian user/assistant: 'pesan-1', 'pesan-2', ..., TestRecent, TestSearch

### Community 77 - "list_capabilities"
Cohesion: 0.09
Nodes (17): _available_tools(), get_capabilities(), build_context_signals(), list_capabilities(), Any, Compute the frontend-facing capability list for one W8 area. message_id /…, Capability signals (from CapabilityContext.jsx / per-message / per-file hooks)…, get (+9 more)

### Community 78 - "_cap"
Cohesion: 0.09
Nodes (5): _cap(), TestDuplicateHandling, TestListFiltering, TestRegisterAndLookup, TestRemoval

### Community 79 - "WorkspaceIntegrationService"
Cohesion: 0.12
Nodes (11): Dependency Injection: every collaborator can be swapped - tests inject fakes so…, Remove CONVERSATION-kind links for a path (e.g. right before…, WorkspaceIntegrationService, _always_false(), _always_true(), _fail_write(), _ok_write(), TestConversationToWorkspace (+3 more)

### Community 80 - ".memory"
Cohesion: 0.11
Nodes (6): FakeClock, KeywordProvider, Provider palsu dengan 4 dimensi (jumlah kemunculan kata kunci) - hasil bisa…, Basis: satu folder sementara + database sementara per test., TempCase, TestSemanticMemory

### Community 81 - "artifacts.py"
Cohesion: 0.15
Nodes (16): create_artifact(), CreateArtifactRequest, download_artifact(), get_artifact(), list_artifacts(), BaseModel, get, post (+8 more)

### Community 82 - "DocumentSpec"
Cohesion: 0.20
Nodes (10): bullet_list(), DocumentBlock, DocumentSpec, heading(), paragraph(), One content block. `type` discriminates which fields apply: heading -> text,…, table_block(), _doc_spec() (+2 more)

### Community 83 - "ModelStore"
Cohesion: 0.17
Nodes (10): ModelStore, _now_iso(), Connection, Path, Row, core/model_store.py — pemilik database/model_router.db (Sprint 1). Tabel…, Return (clean, error). partial=True -> hanya field yang ada divalidasi., _slugify() (+2 more)

### Community 84 - "chat.py"
Cohesion: 0.14
Nodes (21): get, post, api/routers/chat.py Endpoint /api/chat menangani: 1. Chat teks biasa (dan slash…, reset(), token_usage(), create_session(), post, rename() (+13 more)

### Community 85 - "workspace/WorkspacePage.jsx"
Cohesion: 0.08
Nodes (15): parentOf(), WorkspacePage(), handleRename(), DioPreviewPage(), EXAMPLES, ref_api_js, ref_components_dio_renderer_jsx, ref_components_toast_jsx (+7 more)

### Community 86 - "Plugin"
Cohesion: 0.09
Nodes (16): Plugin, PluginContext, ABC, core/plugins/interface.py — Phase 1 Plugin Foundation: abstract Plugin…, Aktifkan plugin (mis. mulai berpartisipasi dalam alur AIRA). Boleh dipanggil…, Nonaktifkan plugin tanpa membongkarnya - kebalikan dari enable()., Bongkar plugin secara permanen (lepas resource, dst). Setelah ini plugin tidak…, Konteks minimal yang diteruskan ke Plugin.initialize(). plugin_id : id plugin… (+8 more)

### Community 87 - "long_term.py"
Cohesion: 0.14
Nodes (21): snmp_get_interface_traffic(), snmp_get_system_info(), build_context_snippet(), _connect(), forget_fact(), get_all_facts(), get_recent_events(), init_db() (+13 more)

### Community 88 - "routers/models.py"
Cohesion: 0.18
Nodes (24): Dipanggil api/routers/models.py (tombol Test Connection)., test_connection(), create_model(), DefaultModelRequest, delete_model(), _dump(), get_model(), get_routing() (+16 more)

### Community 89 - "test_frontend_and_integration.py"
Cohesion: 0.17
Nodes (12): discovered_to_payload(), api/routers/capabilities_logic.py — pure, framework-free logic behind GET…, _reason_label(), resolve_action(), resolve_area(), DiscoveredCapability, capabilities_to_frontend_list(), capability_to_frontend_dict() (+4 more)

### Community 90 - "load_persona_config"
Cohesion: 0.16
Nodes (7): load_persona_config(), Muat konfigurasi persona dari base_dir (default: core/persona/). Tidak pernah…, make_config_dir(), Path, Salin config bawaan ke tmp lalu timpa/hapus file. value None = hapus., TestLoaderResilience, TestShippedConfig

### Community 91 - "AIRA_ECOSYSTEM/core/memory.py"
Cohesion: 0.17
Nodes (20): agents/rei/registry.py — pintu masuk kemampuan riset, memori, dan File System…, recall(), add_fact(), delete_fact(), events(), facts(), get, post (+12 more)

### Community 92 - "routers/persona.py"
Cohesion: 0.17
Nodes (23): apply_preset(), ApplyPresetRequest, BehaviorUpdateRequest, clone_preset(), ClonePresetRequest, _dump(), get_persona(), get_preset() (+15 more)

### Community 93 - "WebSocketEventBridge"
Cohesion: 0.12
Nodes (7): AbstractEventLoop, Idempotent. Panggil dari thread event loop (startup FastAPI atau awal koneksi…, Tunggu sampai semua event yang sudah masuk antrean terkirim. True kalau tuntas…, WebSocketEventBridge, FakeSender, TestBridgeProtocol, Sender

### Community 94 - "LocationPanel.jsx"
Cohesion: 0.20
Nodes (18): AccessLocationReporter(), report(), LocationPanel(), disableGps(), enableGps(), reportAccess(), run(), saveHost() (+10 more)

### Community 95 - "context/builder.py"
Cohesion: 0.11
Nodes (19): _default_attachments_for_session(), _default_location_text(), _default_runtime_state(), _default_runtime_text(), get_context_builder(), core/context/builder.py — Context Builder (Sprint 2 / Worker 1). Pipeline: User…, Snapshot Runtime State Engine global. Dipakai get_context_builder()., (SPRINT 2.7.1 P0 FIX) Lazy import - hanya dipakai kalau tidak di-inject.… (+11 more)

### Community 96 - "persona/loader.py"
Cohesion: 0.17
Nodes (21): _find_forbidden(), _load_behavior(), _load_identity(), _load_styles(), _load_tone(), _normalize_scale(), _overlay_scales(), _overlay_strings() (+13 more)

### Community 97 - "connection_manager.py"
Cohesion: 0.14
Nodes (20): agents/akane/connection_manager.py — AKANE Persistent Connection Engine (APCE),…, get_logger(), log_event(), core/logger.py — sistem logging terstruktur AIRA Ecosystem. Setiap…, logging.getLogger('aira.<category>') - nama logger jadi sumber kategori., Log terstruktur: context/duration/success masuk kolom terpisah di logs.db…, _get_device(), close_all_connections() (+12 more)

### Community 98 - "package.json"
Cohesion: 0.09
Nodes (20): allowScripts, esbuild@0.21.5, name, private, scripts, build, dev, preview (+12 more)

### Community 99 - "Markdown.jsx"
Cohesion: 0.13
Nodes (14): CopyButton(), handleClick(), buildSvg(), CodeBlock(), components, downloadSvg(), InlineCode(), handleCopy() (+6 more)

### Community 100 - "MessageBubble.jsx"
Cohesion: 0.11
Nodes (12): EditBox(), isDioSubmissionText(), MessageBubble(), ACTIONS, SelectionToolbar(), CATEGORY_COLOR, ToolStep(), extractSurrounding() (+4 more)

### Community 102 - "TestBrainIntegration"
Cohesion: 0.21
Nodes (6): FakeClassifier, FakeRouter, make_orchestrator(), Regresi: thinking.start sudah terbit tapi try/finally Brain belum tercapai., Kelas Orchestrator palsu; sink (list) merekam panggilan route()., TestBrainIntegration

### Community 103 - "vision/detector.py"
Cohesion: 0.13
Nodes (16): _describe_detections(), fuse_voice_and_vision(), log_error(), Fusion konteks multi-sumber (suara + visual) menjadi SATU pesan user sebelum…, Jalankan tracking singkat (durasi lebih pendek dari tool call manual, supaya…, agents/hikari/registry.py — pintu masuk resmi ke HIKARI (vision)., detect_objects(), agents/hikari/vision.py — HIKARI (Hybrid Intelligent Knowledge & Augmented… (+8 more)

### Community 104 - "InvalidRequestError"
Cohesion: 0.17
Nodes (21): _active_session_id(), _coerce_int(), conversation_history_recent(), conversation_history_search(), conversation_history_summary(), Any, agents/rei/conversation_tools.py — adapter tool "conversation_history" untuk…, Giliran terbaru di sesi aktif, urut kronologis. (+13 more)

### Community 105 - "attachments.py"
Cohesion: 0.19
Nodes (21): associate_attachment(), AssociateRequest, attach_external_file(), attach_workspace_file(), delete_attachment(), ExternalAttachmentRequest, get_attachment(), get_attachment_reference() (+13 more)

### Community 106 - "AIRAContext"
Cohesion: 0.13
Nodes (7): AIRAContext, Final Context untuk satu giliran percakapan., Section yang ADA, urut kanonik., Teks tambahan untuk system prompt: HANYA PROMPT_SECTIONS yang punya teks, urut…, Ringkasan aman untuk log (tanpa isi memori/lokasi)., Toleran: field hilang/rusak jadi default, tidak pernah raise., TestContextModels

### Community 107 - "core/dio/__init__.py"
Cohesion: 0.23
Nodes (5): core/dio/ — Dynamic Interaction Orchestrator (DIO), Phase 2.0. Public API: from…, _new_id(), ValidationIssue, ValidationResult, SchemaValidator

### Community 108 - "model_registry.py"
Cohesion: 0.20
Nodes (21): _connect(), create_model(), delete_model(), get_default_model(), get_fallback_model(), get_model(), init_db(), list_models() (+13 more)

### Community 109 - "test_persona_engine.py"
Cohesion: 0.12
Nodes (9): core/persona/defaults.py — nilai bawaan (fallback) Persona Engine. Ini adalah…, build_prompt(), Dipanggil HANYA oleh core/persona/engine.py::PersonaEngine.build()/preview().…, tests/test_persona_engine.py — unit test Persona Engine (Sprint 2 / Worker 2).…, TestContextBuilderIntegration, composer(), TestEngineIntegration, TestPromptAssembly (+1 more)

### Community 110 - "ConnectionManager"
Cohesion: 0.16
Nodes (6): ConnectionManager, Dipanggil oleh network_tools.py. Auto-open session kalau device ini belum punya…, Dipanggil dari FastAPI shutdown event (lihat api/main.py) - tutup semua session…, Singleton. Ambil instance lewat get_connection_manager()., new_session_id(), Lock

### Community 111 - "WorkspacePage"
Cohesion: 0.14
Nodes (10): FileGrid(), FileRow(), formatBytes(), formatDate(), icon(), PropertyPanel(), resolvePermission(), parentOf() (+2 more)

### Community 112 - "test_conversation_context.py"
Cohesion: 0.11
Nodes (9): session_id valid secara bentuk, tetapi tidak ada di chat_sessions., SessionNotFoundError, Base, tests/test_conversation_context.py — unit test Conversation Context (Sprint 2.6…, Isi mentah kedua tabel (untuk memastikan tidak ada yang berubah)., TestInvalidSession, TestReadOnly, ast (+1 more)

### Community 113 - "test_location_flow.py"
Cohesion: 0.11
Nodes (6): _make_env(), core/dio/tests/dio/test_location_flow.py — unit test alur DIO…, Tool lokasi murni opt-in oleh LLM (dipanggil hanya lewat tool-call eksplisit) -…, TestLocationEventPublication, TestLocationPermissionRequest, TestNormalChatDoesNotTriggerLocation

### Community 114 - "GlobalSettingsStore"
Cohesion: 0.18
Nodes (11): GlobalSettingsStore, _publish_settings_changed(), Any, Connection, Path, Return (nilai bersih, error). Salah satu selalu None., Dependency Injection: db_path bisa disuntik (unit test memakai file sementara)…, Isi HANYA key yang belum ada - tidak pernah menimpa nilai yang sudah diset user… (+3 more)

### Community 115 - "test_context_builder.py"
Cohesion: 0.13
Nodes (6): _BrainTestBase, FakeOrchestrator, FakeRouter, tests/test_context_builder.py — unit test Context Builder (Sprint 2 / Worker…, Merekam argumen route(); tidak menjalankan Planner., TestBrainIntegration

### Community 117 - "log_store.py"
Cohesion: 0.18
Nodes (18): delete_artifact(), clear_access(), categories(), clear(), get_log_detail(), list_logs(), get, stats() (+10 more)

### Community 118 - "ConversationMemory"
Cohesion: 0.12
Nodes (6): SessionMemory, ConversationMemory, Port 1:1 dari agent/core/memory.py, dengan dua perbedaan: 1. system prompt…, Cari titik potong aman: tepat sebelum pesan role="user", supaya tidak memotong…, Pelacak token untuk SATU sesi percakapan (satu instance ConversationMemory).…, TokenTracker

### Community 119 - "ArtifactEngine"
Cohesion: 0.19
Nodes (9): ArtifactEngine, _default_resolve_path(), _publish(), Any, Path, Dependency Injection: `store` and `resolve_path` can both be swapped - tests…, ArtifactResult, Any (+1 more)

### Community 120 - "WorkspaceLink"
Cohesion: 0.14
Nodes (5): One ownership record: `relative_path` (Workspace-sandboxed path) belongs to…, WorkspaceLink, Given a Workspace path, answer "whose is this, conversationally?". Lookup order…, Every Workspace path this session is associated with, across all three flows,…, TestWorkspaceLinkStore

### Community 121 - "TestCallModelStreaming"
Cohesion: 0.18
Nodes (7): RecordingSink, scripted_stream(), fake(), stream_fail(), stream_ok(), step(), TestCallModelStreaming

### Community 122 - "global_settings.py"
Cohesion: 0.16
Nodes (13): get_setting(), list_settings(), agents/rei/settings_tools.py — future AI-tool contract for the Global Settings…, update_setting(), get_global_settings_store(), core/global_settings.py — Global Settings Engine (Sprint 2.6, Worker 1). SATU-…, settings.read(key) - dipakai api/routers/settings.py dan…, settings.write(key, value) - tervalidasi lewat SETTINGS_SCHEMA. (+5 more)

### Community 123 - "workspace_links.py"
Cohesion: 0.18
Nodes (18): adopt_workspace_file(), AdoptWorkspaceFileRequest, get_owner(), list_session_links(), BaseModel, get, post, _raise_for_errors() (+10 more)

### Community 124 - "ModelsPage.jsx"
Cohesion: 0.11
Nodes (12): aira_ecosystem_app_frontend_src_components_models_badges, aira_ecosystem_app_frontend_src_components_models_badges_labelbadge, aira_ecosystem_app_frontend_src_components_models_badges_providerbadge, aira_ecosystem_app_frontend_src_components_models_badges_statusbadge, aira_ecosystem_app_frontend_src_components_models_constants, aira_ecosystem_app_frontend_src_components_models_constants_formatcontext, aira_ecosystem_app_frontend_src_components_models_constants_label_options, aira_ecosystem_app_frontend_src_components_models_defaultroutingcard (+4 more)

### Community 125 - "DefaultEmbeddingProvider"
Cohesion: 0.17
Nodes (3): DefaultEmbeddingProvider, Feature hashing deterministik. Tiap teks: huruf kecil -> token kata -> fitur…, TestEmbedder

### Community 126 - "semantic_memory/models.py"
Cohesion: 0.16
Nodes (10): clamp_unit(), _clean_embedding(), _finite_float(), MemoryCategory, Any, Enum, str, core/semantic_memory/models.py — bentuk data Semantic Memory (Sprint 2.4).… (+2 more)

### Community 127 - "_FakeAttachment"
Cohesion: 0.15
Nodes (6): _FakeArtifact, _FakeAttachment, TestAttachmentSourceOnly, provider(), provider(), TestMixedSources

### Community 128 - "TestRealIncrementalDelivery"
Cohesion: 0.13
Nodes (4): GatedServer, Server chunked 127.0.0.1. Item `script` berupa bytes (dikirim sebagai satu HTTP…, Bukti bahwa chunk sampai ke client SELAGI respons masih berjalan., TestRealIncrementalDelivery

### Community 129 - "EventNames"
Cohesion: 0.20
Nodes (13): EventNames, Nama event standar AIRA OS. Konvensi: <domain>.<action> SATU sumber kebenaran:…, async_handler(), broken_handler(), handler(), main(), test_events_manual.py — validasi cepat core/events.py. CARA PAKAI: 1. Taruh…, test_1_subscribe_publish_wildcard() (+5 more)

### Community 130 - "importance_score"
Cohesion: 0.17
Nodes (7): category_weight(), importance_score(), 1.0 untuk yang baru, 0.5 setelah satu half-life, mendekati 0 untuk yang lama., Bobot kategori 0..1; kategori tak terdaftar memakai bobot bawaan., Importance 0..1 = rata-rata berbobot dari tiga faktor: manual -…, recency_score(), TestImportance

### Community 131 - "agent/main.py"
Cohesion: 0.16
Nodes (13): agent_voice_voice_io, get_active_provider(), get_active_provider_key(), get_openrouter_credits(), list_providers(), Ambil sisa saldo/kredit dari OpenRouter lewat endpoint terpisah /credits (bukan…, Provider aktif disimpan di long-term memory (tabel facts), jadi pilihan model…, set_active_provider_key() (+5 more)

### Community 132 - "createStreamBatcher"
Cohesion: 0.17
Nodes (10): createStreamBatcher(), drain(), flush(), flushAll(), onTimer(), push(), DEFAULT_MIN_INTERVAL_MS, fakeClock() (+2 more)

### Community 133 - "HistoryEngine"
Cohesion: 0.19
Nodes (9): _checksum(), HistoryEngine, Path, Tulis ulang isi snapshot ke path aslinya. False kalau snapshot_id tidak…, Snapshot disimpan sebagai file biner di:…, Dipanggil SEBELUM overwrite file yang sudah ada., _safe_folder_name(), HistorySnapshot (+1 more)

### Community 134 - "FileOperations"
Cohesion: 0.27
Nodes (6): core/filesystem/ — File System Engine (FSE) untuk AIRA OS (Sprint 02). Public…, OperationResult, ReadResult, WriteResult, FileOperations, Dependency Injection untuk workspace/permissions/history/trash - kalau tidak…

### Community 135 - "setup_logging"
Cohesion: 0.14
Nodes (12): CategoryFileHandler, ColorConsoleFormatter, _infer_category(), Menulis tiap log record ke database/logs.db supaya bisa di-query dari API dan…, Router dinamis: tiap kategori otomatis punya file rotating sendiri di…, Setup sekali untuk seluruh ekosistem AIRA. Idempotent., aira.tools.ssh' -> 'ssh', 'aira.rei.planner' -> 'planner', 'aira' -> 'system'., Formatter berwarna detail: [LEVEL][kategori] HH:MM:SS | file.py:line (fungsi) |… (+4 more)

### Community 136 - "snmp/client.py"
Cohesion: 0.21
Nodes (13): _get_community(), Menjalankan beberapa operasi GET/WALK sekaligus secara CONCURRENT dalam satu…, Menjalankan beberapa operasi SNMP GET/WALK sekaligus terhadap satu device dalam…, _run_batch(), snmp_batch(), snmp_get(), _snmp_get_async(), snmp_walk() (+5 more)

### Community 137 - "PersistentShell"
Cohesion: 0.16
Nodes (7): PersistentShell, Exception, tools/ssh/shell.py — PersistentShell: satu channel invoke_shell() paramiko yang…, Return: {"output": str, "prompt_matched": bool} prompt_matched=False artinya…, Wrapper tipis di atas paramiko SSHClient + invoke_shell(). Satu instance = satu…, ShellNotConnectedError, paramiko

### Community 138 - "dio_tools.py"
Cohesion: 0.19
Nodes (15): build_submission_message(), _handle_location_grant(), _is_sensitive(), agents/rei/dio_tools.py — wrapper tipis REI di atas Dynamic Interaction…, Dipanggil LLM saat permintaan user butuh lokasi presisi SEKARANG dan lokasi…, Validasi koordinat lalu simpan sebagai lokasi akses sesi lewat LocationService.…, Menjalankan efek samping submission. SINKRON dan bisa melakukan HTTP…, Return (display_message, llm_message). display_message disimpan ke chat_turns… (+7 more)

### Community 139 - "InteractionPlan"
Cohesion: 0.33
Nodes (6): _to_missing_field(), ChoiceOption, InteractionPlan, MissingField, core/dio/tests/dio/test_builder.py — unit test SchemaBuilder (Phase 2.3).…, TestSchemaBuilder

### Community 140 - "fs_tools.py"
Cohesion: 0.21
Nodes (15): copy_file(), create_folder(), delete_file(), list_trash(), list_workspace(), move_file(), _ops(), agents/rei/fs_tools.py — wrapper tipis REI di atas File System Engine… (+7 more)

### Community 141 - "ToolBinding"
Cohesion: 0.17
Nodes (4): available_tools: any container supporting `in` (set/list/dict keys/sentinel)., HOW a capability is executed, referenced by NAME only (never a callable) -…, ToolBinding, TestToolBinding

### Community 142 - "SemanticMemory"
Cohesion: 0.17
Nodes (6): Any, Fasad tunggal. Semua argumen opsional: SemanticMemory() ->…, Buat fakta baru: validasi -> embed -> simpan. Return record tersimpan., Simpan record yang sudah dibuat; kalau belum punya embedding, di-embed dulu., Seperti MemoryStore.update, tapi `text` baru otomatis di-embed ulang., SemanticMemory

### Community 143 - "run_chat.py"
Cohesion: 0.19
Nodes (8): core/ui.py — util tampilan terminal untuk run_chat.py (mode testing). Port…, Timer, _extract_error_reason(), main(), _print_step(), run_chat.py — entrypoint terminal sederhana untuk AIRA (khusus testing). INI…, result_preview adalah JSON string (kadang dipotong dengan '...(truncated)' di…, sys

### Community 144 - "UnifiedContext"
Cohesion: 0.19
Nodes (7): _json_dict(), Any, The single composed context packet for one turn - REI and Capability Discovery…, Source names that actually contributed something this turn, canonical order., Capability-Layer context vocabulary for the sources actually PRESENT this turn…, Ready-to-spread kwargs: CapabilityDiscovery.discover(**unified.for_discovery())., UnifiedContext

### Community 145 - "workspace_links/models.py"
Cohesion: 0.16
Nodes (9): core/workspace_links/ - Workspace Integration (Sprint 2.7 / Wave 2 / W6).…, LinkKind, Any, Enum, str, core/workspace_links/models.py - data contract for Workspace Integration…, Where a workspace item's ownership record originates from., get_workspace_link_store() (+1 more)

### Community 146 - "workspace_links/service.py"
Cohesion: 0.17
Nodes (10): LinkResult, Return value of every WorkspaceIntegrationService mutation call - never raises…, _default_attachments_for_session(), _default_write_text(), _is_reserved(), _publish(), Any, core/workspace_links/service.py - WorkspaceIntegrationService (Sprint 2.7 /… (+2 more)

### Community 147 - "WorkspaceLinkStore"
Cohesion: 0.22
Nodes (6): Connection, Path, Row, Most recent CONVERSATION-kind link for this path, if any., Remove ALL conversation-links for a path (e.g. right before the path itself is…, WorkspaceLinkStore

### Community 148 - "connections.py"
Cohesion: 0.26
Nodes (14): get_connection_manager(), close_connection(), CloseConnectionRequest, execute_command(), ExecuteCommandRequest, get_connection(), list_connections(), open_connection() (+6 more)

### Community 149 - "tts.py"
Cohesion: 0.27
Nodes (13): _get_kokoro(), log_error(), speak(), synthesize_bytes(), _get_kokoro(), log_error(), Text-to-speech via Kokoro (lokal/offline, ONNX runtime). Model file…, Sama seperti speak(), tapi TIDAK memutar audio di server - hanya mengembalikan… (+5 more)

### Community 150 - "ws.py"
Cohesion: 0.18
Nodes (12): chat_ws(), _cleanup_run(), _decode_voice_audio(), _emit(), websocket, api/routers/ws.py — WebSocket realtime streaming untuk AIRA. Menjalankan…, Event protokol milik ws.py sendiri (bukan event domain Event Bus)., _run_turn() (+4 more)

### Community 151 - "BootGate.jsx"
Cohesion: 0.25
Nodes (9): BootGate(), BootScreen(), FirstBoot(), SplashScreen(), useChatRuntime(), hasBootedThisSession(), hasSeenFirstBoot(), markBootedThisSession() (+1 more)

### Community 152 - "SpreadsheetSpec"
Cohesion: 0.33
Nodes (6): SpreadsheetSpec, WorksheetSpec, _sheet_spec(), TestSpreadsheetValidation, TestValidateForType, validate_spreadsheet_spec()

### Community 153 - "DIOAnalyzer"
Cohesion: 0.19
Nodes (4): DIOAnalyzer, Any, core/dio/tests/dio/test_analyzer.py — unit test DIOAnalyzer (Phase 2.1).…, TestDIOAnalyzer

### Community 154 - "logging"
Cohesion: 0.22
Nodes (11): AIRA OS — Internal Event Bus ============================ File:…, core/filesystem/history.py — History Engine untuk File System Engine (FSE),…, core/filesystem/operations.py — CRUD File Operations untuk File System Engine…, core/filesystem/trash.py — Trash System untuk File System Engine (FSE), Sprint…, contextvars, hashlib, inspect, logging (+3 more)

### Community 155 - "TempStoreCase"
Cohesion: 0.15
Nodes (5): default_settings(), TempStoreCase, TestDefaults, TestMissingKeysAndReset, TestRead

### Community 156 - "ctx_for"
Cohesion: 0.19
Nodes (3): ctx_for(), TestPersonaContext, TestSeparationFromReasoning

### Community 157 - "routeros.py"
Cohesion: 0.36
Nodes (13): execute_mikrotik_tool(), get_arp(), get_dhcp_client(), get_dhcp_server(), get_dns(), get_firewall(), get_identity(), get_interfaces() (+5 more)

### Community 158 - "memory_store/chat_sessions.py"
Cohesion: 0.26
Nodes (14): add_turn(), _connect(), create_session(), delete_session(), get_session_row(), get_turns(), init_db(), list_sessions() (+6 more)

### Community 159 - "Renderer.jsx"
Cohesion: 0.23
Nodes (9): ActionBar(), STYLE_CLASSES, FieldRenderer(), Renderer(), SectionRenderer(), defaultValues(), flattenFields(), useInteractionState() (+1 more)

### Community 160 - "Brain"
Cohesion: 0.23
Nodes (5): Brain, BrainResponse, Engine harus sudah subscribe SEBELUM Brain mempublish event pertama., Publish ke Event Bus; kegagalan apa pun tidak boleh menjatuhkan giliran., Builder hanya menggabungkan konteks; gagal -> None, Planner memakai builder…

### Community 161 - "select_mode"
Cohesion: 0.34
Nodes (4): select_mode(), _plan(), core/dio/tests/dio/test_reasoning.py — unit test mode selection (Phase 2.2).…, TestModeSelection

### Community 163 - "run"
Cohesion: 0.23
Nodes (6): _call_model_with_retry(), Beberapa provider gratis (terutama OpenRouter free tier) kadang balas HTTP 200…, Catat token usage dari satu respons LLM ke token tracker milik sesi ini.…, run(), _track_usage(), UI

### Community 164 - "theme/index.js"
Cohesion: 0.28
Nodes (5): colors, radius, shadow, spacing, typography

### Community 165 - "WorkspaceManager"
Cohesion: 0.27
Nodes (7): FileEntry, TreeNode, Path, Dependency Injection: adapter HAL diterima lewat konstruktor (default:…, Buat root workspace + subfolder standar. Idempotent., Terjemahkan path relatif jadi Path absolut di dalam workspace. SATU-SATUNYA…, WorkspaceManager

### Community 166 - "TrashEngine"
Cohesion: 0.28
Nodes (5): TrashEntry, _checksum(), Path, SATU-SATUNYA jalur penghapusan permanen di seluruh FSE., TrashEngine

### Community 167 - "build_context_packet"
Cohesion: 0.23
Nodes (5): build_context_packet(), Packet siap-kirim ke Capability Layer / Planner. Tidak menyentuh ContextBuilder…, SelectionContextPacket, TestContextPacket, TestContextPacket

### Community 168 - "make_builder"
Cohesion: 0.24
Nodes (3): make_builder(), TestContextBuilderIntegration, rusak()

### Community 169 - "manifest.json"
Cohesion: 0.17
Nodes (11): background_color, description, display, icons, id, name, orientation, scope (+3 more)

### Community 170 - "GraphBlock.jsx"
Cohesion: 0.29
Nodes (11): assignLayers(), resolve(), colorForGroup(), edgePath(), estimateNodeWidth(), GraphBlock(), GROUP_COLORS, hashString() (+3 more)

### Community 173 - "selection.py"
Cohesion: 0.31
Nodes (10): ActionRequestPayload, create_selection(), CreateSelectionRequest, get_selection(), BaseModel, get, post, api/routers/selection.py — REST endpoint tipis untuk Selection Intelligence… (+2 more)

### Community 174 - "routers/vision.py"
Cohesion: 0.33
Nodes (10): get_visual_context(), get, post, UploadFile, _raise_for_errors(), api/routers/vision.py — REST endpoint tipis untuk Image & Visual Input (Sprint…, _upload(), upload_image() (+2 more)

### Community 175 - "modelRouter.d.ts"
Cohesion: 0.18
Nodes (10): ModelInput, ModelPolicy, ModelRecord, Provider, RoutePreview, RoutingMap, RoutingResponse, SelectedModel (+2 more)

### Community 176 - "validate_name"
Cohesion: 0.31
Nodes (3): TestValidateName, Filename/path safety. Returns the cleaned name, or None if rejected., validate_name()

### Community 177 - "format_semantic_memories"
Cohesion: 0.25
Nodes (5): _default_semantic_memory(), format_semantic_memories(), Singleton SemanticMemory (dibuat lazy). Tidak membuat DB baru per request., RetrievalResult -> (teks ringkas, jumlah baris). Deterministik, hanya membaca…, TestFormatter

### Community 178 - "TestBrainStreamFlag"
Cohesion: 0.31
Nodes (4): FakeRouter, make_orchestrator(), route(), TestBrainStreamFlag

### Community 179 - "compilerOptions"
Cohesion: 0.20
Nodes (9): compilerOptions, allowJs, checkJs, jsx, module, moduleResolution, target, exclude (+1 more)

### Community 180 - "cosine_similarity"
Cohesion: 0.33
Nodes (3): cosine_similarity(), Cosine similarity a·b / (|a||b|), hasil -1..1. - Panjang berbeda -> ValueError.…, TestCosine

### Community 181 - "settings.py"
Cohesion: 0.28
Nodes (8): get_all_settings(), get_setting(), BaseModel, get, put, api/routers/settings.py — REST endpoint for the Global Settings Engine (Sprint…, SettingUpdateRequest, update_setting()

### Community 182 - "stream_enabled_for_turn"
Cohesion: 0.33
Nodes (3): Apakah giliran WebSocket ini boleh streaming? - AIRA_STREAMING=0|false|off|no…, stream_enabled_for_turn(), TestStreamFlag

### Community 186 - "TestSeparationOfConcerns"
Cohesion: 0.28
Nodes (3): _imports(), Path, TestSeparationOfConcerns

### Community 187 - "Scheduler"
Cohesion: 0.25
Nodes (3): core/scheduler.py — scheduled/background task untuk AIRA (stub). Di repo lama…, Daftarkan job berkala. TODO: implementasi loop (threading/asyncio)., Scheduler

### Community 189 - "dependencies"
Cohesion: 0.29
Nodes (7): dependencies, dompurify, lucide-react, react, react-dom, react-markdown, remark-gfm

### Community 192 - "SelectionResult"
Cohesion: 0.29
Nodes (5): _extract_surrounding(), Any, Ambil teks di sekitar selection, TANPA menyertakan selected_text itu sendiri…, Hasil pembangunan SelectionContext - tidak pernah raise (pola core/dio)., SelectionResult

### Community 193 - "ChatInput"
Cohesion: 0.33
Nodes (4): ChatInput(), handleKeyDown(), submit(), ref_slashmenu_jsx

### Community 195 - "devDependencies"
Cohesion: 0.33
Nodes (6): devDependencies, autoprefixer, postcss, tailwindcss, vite, @vitejs/plugin-react

### Community 199 - "replace_capability"
Cohesion: 0.40
Nodes (4): Any, dataclasses.replace() wrapper so callers don't need `dataclasses` themselves;…, Return a NEW Capability with state replaced (registry callers use this rather…, replace_capability()

### Community 203 - "core/persona.py"
Cohesion: 0.50
Nodes (3): build_system_prompt(), Persona & identitas AIRA (Adaptive Intelligent Reasoning Assistant). AIRA BUKAN…, Menyusun system prompt final yang dikirim ke model reasoning (via REI), yaitu…

## Knowledge Gaps
- **127 isolated node(s):** `ModelInput`, `ModelPolicy`, `ModelRecord`, `Provider`, `RoutePreview` (+122 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1574 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **46 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EventBus` connect `EventBus` to `api/main.py`, `test_runtime_state.py`, `event_scope`, `RuntimeStateEngine`, `test_streaming.py`, `Event`, `logging`, `WebSocketEventBridge`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `ContextBuilder` connect `ContextBuilder` to `make_builder`, `test_runtime_state.py`, `make_builder`, `TestBrainIntegration`, `AIRAContext`, `test_persona_engine.py`, `format_semantic_memories`, `test_context_builder.py`, `test_context_semantic_memory.py`, `_builder`, `brain.py`, `context/builder.py`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `Attachment` connect `Attachment` to `WorkspaceLink`, `attachments/engine.py`, `AttachmentEngine`, `VisionResult`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `EventBus` (e.g. with `WebSocketEventBridge` and `RuntimeStateEngine`) actually correct?**
  _`EventBus` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Attachment` (e.g. with `attachment_to_context_dict()` and `attachments_context_section()`) actually correct?**
  _`Attachment` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelInput`, `ModelPolicy`, `ModelRecord` to the rest of the system?**
  _127 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `VisionResult` be split into smaller, more focused modules?**
  _Cohesion score 0.059370725034199726 - nodes in this community are weakly interconnected._