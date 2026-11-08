# PHASE 6 — DATABASE & DATA CENTRALIZATION DEEP AUDIT (`06_DATABASE_AND_DATA_CENTRALIZATION_AUDIT.md`)

**Audit Date**: 2026-11-08  
**Target Directory**: `/home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM`  
**Audit Mode**: Read-Only Schema, Storage & Data Centralization Audit (Zero Operational DB Mutation)

---

## 1. Database Discovery & Schema Map (Section A)

### 1.1 Complete Inventory of All 18 SQLite Databases in AIRA OS
Instead of a single centralized relational database, AIRA OS fragments its persistence across **18 separate SQLite database files** (17 configured under `AIRA_ECOSYSTEM/database/` via [`core/config.py:114-130`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/config.py#L114-L130) plus `edge_buffer.db` in `core/edge_gateway/buffer.py:30`, and 2 tracked `.db.old` backup files):

| # | Database File (`database/`) | Primary Owner Module(s) | Present on Disk? | Table Count | Tables Defined in Schema |
|---:|---|---|---|---:|---|
| 1 | `topology.db` (1.28 MB) | `core/topology_db.py` + 20+ modules (`topology_engine`, `nms_engine`, `core/nms`, `core/routing`, `core/tenant`, `core/billing`, `core/operations`, `core/edge_gateway`, `core/playbooks`, `core/scheduler`, `core/governance`) | **YES** | **58** | **Topology (12)**: `topology_nodes`, `topology_links`, `topology_evidence`, `topology_policy`, `topology_discovery_jobs`, `topology_conflicts`, `topology_audit_log`, `topology_edges`, `topology_edge_evidence`, `topology_snapshots`, `topology_changes`, `topology_schema_version`<br>**Routing (2)**: `route_snapshots`, `route_changes`<br>**NMS v1 & v2 (8)**: `nms_settings`, `nms_device_profiles`, `nms_device_metrics`, `nms_interface_metrics`, `nms_incidents`, `nms_raw_metrics` *(collides!)*, `nms_5m_rollups`, `nms_1h_rollups`<br>**Tenant/Auth/RBAC/Personalization (19)**: `operational_tenants`, `operational_sites`, `operational_users`, `operational_user_sessions`, `operational_devices`, `operational_audit_log`, `operational_pending_approvals`, `operational_approval_preferences`, `rbac_groups`, `rbac_permissions`, `rbac_group_permissions`, `rbac_user_groups`, `rbac_user_permission_overrides`, `user_activity_audit_logs`, `user_memories`, `user_personas`, `user_preferences`, `chat_sessions` *(duplicate!)*, `operational_support_tickets`, `operational_notification_preferences`<br>**Quotas & Billing (8)**: `operational_user_subscriptions`, `operational_token_policies`, `operational_token_balances`, `operational_token_usage_ledger`, `operational_token_adjustments`, `billing_invoices`, `billing_payment_transactions`, `billing_webhook_events`<br>**Operations, Intelligence, Gateways, Playbooks, Automations (20)**: `operational_services`, `operational_service_endpoints`, `operational_jobs`, `operational_job_runs`, `operational_maintenance_windows`, `operational_incidents`, `operational_notifications`, `operational_decisions`, `operational_decision_history`, `operational_health_scores`, `operational_sla_policies`, `operational_sla_reports`, `operational_action_records`, `operational_security_findings`, `operational_security_posture`, `operational_gateways`, `operational_gateway_tokens`, `operational_gateway_sequences`, `operational_gateway_heartbeats`, `operational_playbooks`, `automation_jobs`, `automation_executions`, `data_retention_policies` |
| 2 | `chat_sessions.db` (200 KB) | `core/chat_sessions.py` | **YES** | **3** | `sessions` (`id`, `title`, `created_at`, `updated_at`, `pinned`, `archived`, `user_id`), `messages` (`id`, `session_id`, `turn_index`, `role`, `content`, `raw_json`, `meta_json`, `created_at`), `session_state` (`key`, `value`) |
| 3 | `long_term_memory.db` (24 KB) | `core/memory.py` | **YES** | **3** | `facts` (`key PRIMARY KEY`, `value`, `updated_at` — **NO `user_id`!**), `events` (`id`, `ts`, `kind`, `detail` — **NO `user_id`!**), `preferences` (`key PRIMARY KEY`, `value`, `updated_at`) |
| 4 | `model_router.db` (48 KB) | `core/model_store.py` | **YES** | **4** | `models` (`id`, `name`, `provider`, `model_id`, `base_url`, `api_key`, `enabled`, ...), `routing_map` (`task_type PRIMARY KEY`, `model_id`), `routing_policy` (`id CHECK(id=1)`, `fallback_chain`, ...), `session_model_map` (`session_id PRIMARY KEY`, `model_id`) |
| 5 | `logs.db` (328 KB) | `core/log_store.py` | **YES** | **1** | `logs` (`id`, `ts`, `level`, `category`, `source`, `message`, `detail_json`, `session_id`, `device_name`) |
| 6 | `inventory.db` | `core/inventory_store.py` | Created on demand | **3** | `devices` (`id`, `name UNIQUE`, `host`, `port`, `username`, `device_type`, `os_version`, `tags`, `notes` — **NO `tenant_id`!**), `credentials` (`id`, `name UNIQUE`, `type`, `secret`, `note` — **plaintext `secret`!**), `device_credentials` (`device_name`, `credential_name`) |
| 7 | `global_settings.db` | `core/global_settings.py` | Created on demand | **1** | `settings` (`key PRIMARY KEY`, `value`, `updated_at`) |
| 8 | `semantic_memory.db` | `core/memory_system/semantic_store.py` | Created on demand | **3** | `memories` (with `user_id`, `embedding_json`), `memories_fts` (FTS5 virtual table), `memory_audit_log` — **Never written to in production!** |
| 9 | `interaction_memory.db` | `core/memory_system/interaction_memory.py` | Created on demand | **3** | `interaction_logs`, `behavioral_patterns`, `workflow_habits` — **NO `user_id` column!** |
| 10 | `persona.db` | `core/persona/store.py` | Created on demand | **2** | `active_persona` (`id INTEGER PRIMARY KEY CHECK (id = 1)`, `data TEXT` — **global singleton!**), `custom_presets` (`id`, `name`, `data`, `created_at` — **NO `user_id`!**) |
| 11 | `model_registry.db` | `core/model_registry.py` | Created on demand | **4** | Same schema as `model_router.db` due to `model_store.set_db_path()` poisoning (`model_registry.py:47`) |
| 12 | `attachments.db` | `core/attachment/store.py` | Created on demand | **1** | `attachments` (`id PRIMARY KEY`, `session_id`, `filename`, `mime_type`, `size_bytes`, `storage_path`, `extracted_text`, `metadata_json`, `created_at` — **NO `user_id`!**) |
| 13 | `artifacts.db` | `core/artifacts/store.py` | Created on demand | **1** | `artifacts` (`id PRIMARY KEY`, `title`, `kind`, `language`, `content`, `session_id`, `created_at` — **NO `user_id`!**) |
| 14 | `workspace_links.db` | `core/workspace_links/store.py` | Created on demand | **1** | `workspace_links` (`id`, `session_id`, `relative_path`, `mode`, `created_at` — **NO `user_id`!**) |
| 15 | `location.db` | `core/location/store.py` | Created on demand | **3** | `host_location` (`id CHECK(id=1)`), `access_locations` (`session_id PRIMARY KEY`, `lat`, `lon`, ...), `geocode_cache` (`query_key PRIMARY KEY`, `response_json`) |
| 16 | `selection_context.db` | `core/selection/service.py` | Created on demand | **1** | `selections` (`id PRIMARY KEY`, `session_id`, `source_type`, `selected_text`, ...) |
| 17 | `network_intelligence.db` | `core/network_intelligence/store.py` | Created on demand | **5** | `incidents`, `evidence_items`, `playbook_runs`, `configuration_plans`, `intelligence_investigations` — **NO `tenant_id`!** |
| 18 | `edge_buffer.db` | `core/edge_gateway/buffer.py` | Created on edge | **2** | `edge_telemetry_buffer`, `edge_buffer_meta` |

*(Plus `database/chat_sessions.db.old` and `database/long_term_memory.db.old` tracked in Git, and JSON files in `database/config_snapshots/*.json`.)*

---

## 2. Database Integrity, Schema Collisions & Consistency Audit (Section B)

### 2.1 Confirmed SQL Schema Collisions & Runtime `OperationalError` Crashes
1. **`nms_raw_metrics` Table Schema Collision in `topology.db` (`CONFIRMED` via Runtime Execution)**:
   - [`core/edge_gateway/db.py:85-100`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/edge_gateway/db.py#L85-L100) creates `nms_raw_metrics` with columns `(id, device_id, interface_name, metric_name, metric_value, unit, semantic_type, source_protocol, quality, measured_at, collected_at)`.
   - [`core/nms/metrics_store.py:41-58`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/nms/metrics_store.py#L41-L58) creates the **exact same table name `nms_raw_metrics`** with incompatible columns `(id, device_id, entity_type, entity_id, metric_name, timestamp, value, unit, collection_method, quality_flag)`.
   - **Impact**: `EdgeGatewayManager` runs `ensure_gateway_schema()` when `api/routers/gateways.py` is imported at startup. Subsequent calls to `GET /api/nms/metrics/query` (`api/routers/nms.py:265`) or `init_metrics_tables()` fail with `sqlite3.OperationalError: no such column: timestamp` (or `no such table: nms_1h_rollups`)!
2. **`nms_device_metrics` & `nms_interface_metrics` Column Collision (`CONFIRMED`)**:
   - [`core/nms_engine.py:168-221`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/nms_engine.py#L168-L221) creates `nms_device_metrics` and `nms_interface_metrics` with timestamp column `polled_at TEXT NOT NULL`.
   - [`core/network_intelligence/metrics_service.py:96-148`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/metrics_service.py#L96-L148) (`NmsHistoricalMetricsService._ensure_tables`) defines those same tables with `timestamp REAL NOT NULL` and executes `CREATE INDEX IF NOT EXISTS idx_nms_dev_metrics_ts ON nms_device_metrics(device_id, timestamp)` (`L138`), crashing with `sqlite3.OperationalError: no such column: timestamp`!
3. **`operational_token_policies` Non-Existent Column in `update_plan_policy()` (`CONFIRMED` via Runtime Execution)**:
   - [`core/tenant/db.py:210-226`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/db.py#L210-L226) defines `operational_token_policies` with column `model_cost_mult_json TEXT DEFAULT '{}'` and **no** `created_at` column.
   - [`core/tenant/token_quota_service.py:630-660`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/token_quota_service.py#L630-L660) (`update_plan_policy`) executes `INSERT INTO operational_token_policies (..., model_cost_multiplier_json, created_at, updated_at)`, crashing with `sqlite3.OperationalError: table operational_token_policies has no column named model_cost_multiplier_json` whenever `PUT /api/v1/admin/tokens/plan-policy` is called!
4. **`pol_global_guest` Seed Row Violates `CHECK` Constraint (`CONFIRMED` via Runtime Execution)**:
   - [`core/tenant/db.py:212`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/db.py#L212) defines `tier TEXT CHECK(tier IN ('FREE', 'PRO', 'ENTERPRISE', 'CUSTOM'))`.
   - [`core/tenant/db.py:753`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/db.py#L753) attempts to seed `('pol_global_guest', 'GLOBAL', 'GUEST', 'GUEST', 1000, ...)` using `INSERT OR IGNORE`, which silently fails the `CHECK` constraint so `pol_global_guest` never exists in the database!
5. **Queries Referencing Non-Existent Columns Across Network Intelligence & NMS (`CONFIRMED`)**:
   - `nms_incidents.started_at` (actual column is `opened_at` in `core/nms_engine.py:239`) is queried in `core/network_intelligence/evidence_service.py:1166`, `correlation_engine.py:80,425`, `historical_intelligence.py:92,97,112`, and `rca_engine.py:119`.
   - `topology_snapshots.snapshot_data`, `payload`, `timestamp` (actual columns are `nodes_json`, `edges_json`, `created_at` in `core/topology_engine.py:348-360`) are indexed in `core/network_intelligence/historical_intelligence.py:204,211`.
   - `topology_edges.source, target` (actual columns are `source_node_id, target_node_id` in `core/topology_engine.py:293-294`) are queried in `core/nms/alerts.py:373-380`.
   - `nms_alerts` (table does not exist; actual table is `nms_incidents`) is queried in `core/routing/route_history.py:1378`.

### 2.2 Missing Foreign Keys, Missing Indexes & Unbounded Table Growth
- **`PRAGMA foreign_keys = ON` Not Enabled Globally**:
  - While `core/topology_db.py:173` sets `PRAGMA foreign_keys=ON` for `topology.db` connections via `get_topology_connection()`, direct `sqlite3.connect()` calls in `core/inventory_store.py`, `core/chat_sessions.py`, `core/memory.py`, `core/model_store.py`, `core/log_store.py`, and `core/network_intelligence/store.py` **do not enable `PRAGMA foreign_keys = ON`**, so SQLite foreign key constraints are ignored in those stores.
- **Unindexed & Unbounded Tables (`CONFIRMED`)**:
  - `operational_health_scores` (`core/operations/db.py:182-198`) and `operational_gateway_heartbeats` (`core/edge_gateway/db.py:69-82`) append rows on every dashboard load or heartbeat without any retention policy or cleanup job.

---

## 3. Static / Hardcoded / Local Data Audit (Section C — All 9 Required Points)

### Item 1: Built-in LLM Model Seed (`_BUILTIN_SEED`) with 13 Fictional Models
1. **Lokasi file dan baris**: [`core/model_store.py:42-198`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/model_store.py#L42-L198) (`_BUILTIN_SEED`).
2. **Data apa yang disimpan**: 15 LLM model configurations, including 13 fictional future model IDs (`deepseek-v4.1-flash`, `gemma-4-31b-it`, `mistral-large-4-1t-a52b`, `glm-5.1-air`, `minimax-m3.2`, `nemotron-4-super-120b-a12b`, `qwen3.6-plus`, etc.).
3. **Bagaimana data itu dipakai saat ini**: Seeded into `model_router.db` (`models` table) on first initialization and displayed in `ModelsPage.jsx`.
4. **Mengapa hal ini bermasalah**: Selecting any of these 13 non-existent model IDs causes OpenRouter/provider API calls to fail with `404 Model not found`. Also `model_store.py` vs `model_registry.py` splits model persistence across two `.db` files.
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Keep only verified real default models in a single database seed migration, managed in the centralized database.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: Centralized `ai_models` table in the unified database.
7. **Struktur kolom yang direkomendasikan**: `id TEXT PK`, `tenant_id TEXT FK`, `name TEXT`, `provider TEXT`, `model_id TEXT`, `base_url TEXT`, `api_key_encrypted TEXT`, `capabilities_json TEXT`, `enabled INTEGER`, `is_default INTEGER`, `updated_at TEXT`.
8. **Endpoint atau service yang harus disesuaikan**: `core/model_store.py`, `core/model_registry.py` (decommission), `api/routers/models.py`.
9. **Strategi migrasi tanpa merusak fitur yang ada**: Replace fictional model IDs in `_BUILTIN_SEED` with real OpenRouter/Ollama model IDs, remove `set_db_path` override in `model_registry.py`, and encrypt `api_key` using `Fernet`/AES-GCM.

### Item 2: Contradictory Hardcoded Plan Catalogs (`DEFAULT_PLAN_LIMITS` vs `PLAN_CATALOG`)
1. **Lokasi file dan baris**: [`core/tenant/entitlements.py:21-98`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/entitlements.py#L21-L98) vs [`core/tenant/user_subscription.py:26-79`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/user_subscription.py#L26-L79) and [`core/tenant/db.py:749-755`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/tenant/db.py#L749-L755).
2. **Data apa yang disimpan**: Subscription tier limits (daily/monthly token quotas, max devices, prices, feature flags).
3. **Bagaimana data itu dipakai saat ini**: `EntitlementManager` reads `DEFAULT_PLAN_LIMITS` (`FREE` = 100,000 monthly tokens; `PRO` = 2,000,000), while `UserSubscriptionService` and `BillingService` read `PLAN_CATALOG` (`FREE` = 10,000 monthly tokens; `PRO` = 100,000)!
4. **Mengapa hal ini bermasalah**: Depending on which endpoint the UI calls (`/api/v1/auth/me` vs `/api/v1/portal/subscription`), the same user sees completely different token limits (10x–20x discrepancy).
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Move to database (`subscription_plans` + `operational_token_policies`) as the Single Source of Truth, seeded once at migration time.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: `subscription_plans` and `operational_token_policies` in the central DB.
7. **Struktur kolom yang direkomendasikan**: `plan_code TEXT PK`, `display_name TEXT`, `price_idr INTEGER`, `daily_token_limit INTEGER`, `monthly_token_limit INTEGER`, `max_devices INTEGER`, `features_json TEXT`, `updated_at TEXT`.
8. **Endpoint atau service yang harus disesuaikan**: `core/tenant/entitlements.py`, `core/tenant/user_subscription.py`, `core/billing/service.py`, `api/routers/billing.py`.
9. **Strategi migrasi tanpa merusak fitur yang ada**: Seed `subscription_plans` from unified constants and refactor `EntitlementManager` and `BillingService` to query the DB table with a short TTL cache.

### Item 3: Synthetic 3-Router Default Evidence Bundle (`_build_default_bundle`)
1. **Lokasi file dan baris**: [`api/routers/network_intelligence.py:98-244`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/api/routers/network_intelligence.py#L98-L244).
2. **Data apa yang disimpan**: Hardcoded 3-router topology (`Core-Router-1`, `Dist-Switch-1`, `ISP-Edge`) with fake OSPF/BGP drops, 145 interface errors on `ether1`, and 88% CPU load.
3. **Bagaimana data itu dipakai saat ini**: Automatically returned by `_get_bundle_from_request_or_live()` (`L247-273`) across 10 `/api/intelligence/*` endpoints whenever no live devices are returned by `UnifiedEvidenceService`.
4. **Mengapa hal ini bermasalah**: Operators viewing `NetworkIntelligencePage` on an empty or unreachable inventory are shown fabricated production incidents and router anomalies without clear warning that the data is synthetic mock data!
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Should **not** be returned in production runtime unless an explicit `demo_mode=true` query flag is requested; real data must come from `topology.db` and `inventory.db`.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: Real tables `operational_devices`, `topology_nodes`, `topology_edges`, `nms_device_metrics`, `route_snapshots`.
7. **Struktur kolom yang direkomendasikan**: Existing telemetry/topology tables (with `is_demo INTEGER DEFAULT 0` if demo seeding is desired).
8. **Endpoint atau service yang harus disesuaikan**: `api/routers/network_intelligence.py:247-273` (change default `strict_live: bool = True`).
9. **Strategi migrasi tanpa merusak fitur yang ada**: Default `strict_live=True` in production and return an explicit empty state `{devices: [], is_empty: true}` to the UI when no devices are configured.

### Item 4: Hardcoded `"ISP-Edge"` Node ID & Synthetic Traffic Loads in Simulation Engines
1. **Lokasi file dan baris**: [`core/network_intelligence/failure_simulator.py:74`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/failure_simulator.py#L74), [`core/network_intelligence/impact_analyzer.py:108`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/network_intelligence/impact_analyzer.py#L108), [`core/operations/change_impact_engine.py:174, 202-218`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/core/operations/change_impact_engine.py#L174).
2. **Data apa yang disimpan**: Hardcoded uplink router name `"ISP-Edge"` and hardcoded traffic loads (`45_000_000.0` bps, `30_000_000.0` bps, `100_000_000.0` bps capacity).
3. **Bagaimana data itu dipakai saat ini**: Used during blast-radius and change-impact simulations to check uplink reachability and post-failover link utilization.
4. **Mengapa hal ini bermasalah**: Fails on any real network where the edge router is not literally named `"ISP-Edge"`, and reports a fake `75.0%` post-change utilization regardless of actual link speed or traffic!
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Dynamically query nodes with `role IN ('EDGE', 'GATEWAY', 'CORE')` from `topology_nodes` and actual `rx_bps`/`tx_bps`/`speed_bps` from `nms_interface_metrics`.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: `topology_nodes` (`role` column) and `nms_interface_metrics` (`rx_bps`, `tx_bps`, `speed_bps`).
7. **Struktur kolom yang direkomendasikan**: Existing columns in `topology_nodes` and `nms_interface_metrics`.
8. **Endpoint atau service yang harus disesuaikan**: `failure_simulator.py`, `impact_analyzer.py`, `change_impact_engine.py`.
9. **Strategi migrasi tanpa merusak fitur yang ada**: Resolve gateway nodes from `topology_nodes WHERE role IN ('edge', 'gateway')` (with fallback to default route `0.0.0.0/0` next-hop routers from `route_snapshots`).

### Item 5: Config Snapshots Stored as Unmasked Local JSON Files
1. **Lokasi file dan baris**: [`agents/akane/config_engine.py:135-149`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/agents/akane/config_engine.py#L135-L149) (`database/config_snapshots/{operation_id}.json` and `.raw.json`).
2. **Data apa yang disimpan**: Before/after RouterOS configuration snapshots, planned commands, rollback commands, and verification status.
3. **Bagaimana data itu dipakai saat ini**: Written to loose JSON files on disk (`database/config_snapshots/`) with unmasked secrets in both `.json` and `.raw.json`.
4. **Mengapa hal ini bermasalah**: Cannot be queried relationally by tenant/user/device, lacks retention enforcement, and writes unmasked secrets to `.json` (`L147`).
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Move into a relational table in `topology.db` with encrypted raw config and masked preview JSON.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: `device_config_snapshots` in `topology.db`.
7. **Struktur kolom yang direkomendasikan**: `operation_id TEXT PK`, `tenant_id TEXT`, `device_id TEXT`, `actor_user_id TEXT`, `status TEXT`, `masked_snapshot_json TEXT`, `encrypted_raw_snapshot BLOB`, `created_at TEXT`.
8. **Endpoint atau service yang harus disesuaikan**: `agents/akane/config_engine.py`, `agents/rei/dio_tools.py`.
9. **Strategi migrasi tanpa merusak fitur yang ada**: Add `device_config_snapshots` table and import existing `database/config_snapshots/*.json` files on startup while fixing `L147` to use `masked_data`.

### Item 6: Frontend `Hero.jsx` Hardcoded Prompts & `sessionStorage` Navigation Handoff
1. **Lokasi file dan baris**: [`src/Hero.jsx:6-27`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/Hero.jsx#L6-L27), [`src/components/cockpit/mockData.js:6-36`](file:///home/Lingga/Documents/project/Network_AI_Agent/AIRA_ECOSYSTEM/app/frontend/src/components/cockpit/mockData.js#L6-L36), and `sessionStorage` keys in `NmsPage.jsx:1412`, `TopologyPage.jsx:200`, `SettingsPage.jsx:51`.
2. **Data apa yang disimpan**: Hardcoded `QUICK_PROMPTS` and cross-page navigation target state (`aira_topology_focus_device`, `aira_infra_initial_tab`, `aira_settings_tab`).
3. **Bagaimana data itu dipakai saat ini**: `Hero.jsx` renders static prompt cards instead of capability-driven prompts; `sessionStorage` passes parameters during `aira:navigate` custom events.
4. **Mengapa hal ini bermasalah**: `mockData.js` is dead code; `sessionStorage` navigation state breaks browser history and deep linking.
5. **Apakah data ini seharusnya tetap statis atau dipindahkan ke database**: Replace `sessionStorage` navigation state with URL query/path parameters (`react-router-dom`), and drive hero prompts from `/api/capabilities`.
6. **Tabel database yang sebaiknya menyimpan data tersebut**: N/A (URL router state + `/api/capabilities`).
7. **Struktur kolom yang direkomendasikan**: N/A.
8. **Endpoint atau service yang harus disesuaikan**: `src/App.jsx`, `src/pages/ChatPage.jsx`, `src/pages/InfrastructurePage.jsx`, `src/pages/TopologyPage.jsx`, `src/pages/NmsPage.jsx`.
9. **Strategi migrasi tanpa merusak fitur yang ada**: Introduce URL routing (`react-router-dom`) while keeping `aira:navigate` event listener as a backward-compatible bridge that calls `navigate()`.

---

## 4. Single Source of Truth (SSOT) Audit (Section D)

| Domain Entity | Competing Storage Locations (Split-Brain) | SSOT Verdict & Conflict Impact |
|---|---|---|
| **1. User Profile** | `topology.db:operational_users` vs `topology.db:user_preferences` | **Split**: Core identity in `operational_users`; personalization identity in `user_preferences`. Acceptable if joined by `user_id` FK. |
| **2. Groups & Roles** | `topology.db:operational_users.roles_json` vs `topology.db:rbac_groups` + `rbac_user_groups` | **CONFLICT (`CONFIRMED`)**: `IdentityManager.validate_session_token()` (`manager.py:1054-1068`) unions legacy `ROLE_PERMISSIONS` from `roles_json` with `rbac_groups`, overriding group `DENY` rules! |
| **3. Permissions** | `core/tenant/models.py` (`ROLE_PERMISSIONS`, `PERMISSION_ALIASES`), `core/tenant/rbac_service.py` (`rbac_permissions`), `app/frontend/src/context/AuthContext.jsx` (`PERMISSION_ALIASES`) | **CONFLICT (`CONFIRMED`)**: Frontend and backend define different `PERMISSION_ALIASES` maps, breaking `"nms.read"` vs `"nms.view"` in `Sidebar.jsx`. |
| **4. Chat History** | `chat_sessions.db` (`sessions`, `messages`) vs `topology.db:chat_sessions` (`core/tenant/memory_service.py:106`, `api/routers/personalization.py:432`) | **SPLIT-BRAIN (`CONFIRMED`)**: Active chat writes to `chat_sessions.db`, while `personalization.py` creates a separate `chat_sessions` table in `topology.db`! |
| **5. User Memory** | 1. `long_term_memory.db:facts` (`core/memory.py`)<br>2. `topology.db:user_memories` (`core/tenant/memory_service.py`)<br>3. `semantic_memory.db:memories` (`core/memory_system/semantic_store.py`)<br>4. `interaction_memory.db` (`core/memory_system/interaction_memory.py`) | **SEVERE SPLIT-BRAIN (`CONFIRMED`)**: Auto-extracted chat facts go to unscoped `long_term_memory.db` (leaking across all users), Settings UI edits `topology.db:user_memories`, and `semantic_memory.db` is always empty! |
| **6. AI Persona** | `persona.db:active_persona` (`core/persona/store.py`, singleton `id=1`) vs `topology.db:user_personas` (`core/tenant/persona_service.py`) | **SPLIT-BRAIN (`CONFIRMED`)**: `PersonaPage.jsx` mutates `/api/persona` (`persona.db`), while `/api/v1/personalization/persona` mutates `topology.db:user_personas`. |
| **7. AI Model Config** | `model_router.db` (`core/model_store.py`) vs `model_registry.db` (`core/model_registry.py`) | **SPLIT-BRAIN (`CONFIRMED`)**: `model_registry.py:47` calls `model_store.set_db_path()`, redirecting `model_store` from `model_router.db` to `model_registry.db` at runtime! |
| **8. System Settings** | `global_settings.db:settings` vs `topology.db:nms_settings` vs `topology.db:topology_policy` vs `topology.db:operational_approval_preferences` | **Fragmented**: Spread across 2 DB files and 4 tables without unified auth (`settings.py` has zero auth). |
| **9. Network Device Inventory** | 1. `inventory.db:devices` (`core/inventory_store.py`)<br>2. `topology.db:operational_devices` (`core/tenant/inventory_manager.py`)<br>3. `topology.db:topology_nodes` (`core/topology_engine.py`)<br>4. `topology.db:nms_device_profiles` (`core/nms_engine.py`) | **SEVERE SPLIT-BRAIN (`CONFIRMED`)**: `/api/devices` writes to `inventory.db` (global, no `tenant_id`), whereas Edge Gateway and Customer Portal read `topology.db:operational_devices` (tenant-scoped)! |
| **10. Device Credentials** | `inventory.db:credentials` (plaintext `secret`) vs `.env` (`SSH_USERNAME`, `SSH_PASSWORD`, `SNMP_COMMUNITY`) | **INSECURE**: Stored in plaintext in `inventory.db`, with global `.env` fallback leak in `connection_manager.py:200`. |
| **11. Topology Nodes & Links** | `topology.db`: `topology_nodes` + `topology_links` (v1) vs `topology_edges` + `topology_edge_evidence` (v2 Phase 4.1) | **Dual Tables in `topology.db`**: Maintained together by `TopologyEngine`, but lacking `tenant_id`. |
| **12. NMS Metrics & Alerts** | `topology.db`: `nms_device_metrics` + `nms_interface_metrics` (`polled_at TEXT`) vs `nms_raw_metrics` + `nms_5m_rollups` + `nms_1h_rollups` (`core/nms/metrics_store.py` vs `core/edge_gateway/db.py`) | **SCHEMA COLLISION (`CONFIRMED`)**: Two incompatible DDL definitions of `nms_raw_metrics` and two incompatible definitions of `nms_device_metrics` in `topology.db`. |
| **13. Incidents** | 1. `topology.db:nms_incidents` (`NmsEngine`)<br>2. `network_intelligence.db:incidents` (`NetworkIntelligenceStore`)<br>3. `topology.db:operational_incidents` (`ProactiveIncidentEngine` vs `MultiTenantIncidentEngine`) | **3-WAY SPLIT-BRAIN (`CONFIRMED`)**: NMS incidents, Intelligence incidents, and Operational incidents are stored in 3 separate tables across 2 DB files! |
| **14. Logs & Audit Trails** | `logs.db:logs`, `topology.db:user_activity_audit_logs`, `topology.db:operational_audit_log`, `topology.db:topology_audit_log`, `semantic_memory.db:memory_audit_log` | **5 Separate Audit Tables** across 3 DB files. |
| **15. Automations & Scheduled Tasks** | `topology.db:automation_jobs` (`core/scheduler.py`) vs `topology.db:operational_jobs` (`core/operations/scheduler.py`) | **DUPLICATED**: Two separate scheduler engines and two separate job tables in `topology.db`. |

---

## 5. Database Access Flow Audit (Section E)

1. **Write-on-Read Lock Contention on Every Authenticated API Call (`core/tenant/manager.py:1032-1035` — `CONFIRMED`)**:
   - `IdentityManager.validate_session_token()` executes `UPDATE operational_user_sessions SET last_active_at = ? WHERE session_id = ?` inside `topology_transaction()` on **every single authenticated HTTP request**, serializing all concurrent GET requests behind SQLite's single-writer lock on `topology.db`!
2. **N+1 Query Loops in Operations & Portal (`CONFIRMED`)**:
   - `DynamicHealthScoringEngine.score_tenant()` (`core/operations/health_scoring_engine.py:299-330`) executes synchronous `SELECT` + `INSERT INTO operational_health_scores` transactions in a loop for every device, site, service, and gateway during `GET /api/v1/portal/dashboard/overview`.
   - `ServiceIntelligenceEngine.list_services()` (`core/operations/service_intelligence.py:153-167`), `ProactiveIncidentEngine.list_incidents()` (`core/operations/incident_engine.py:117-147`), and `OperationalSchedulerEngine.list_jobs()` (`core/operations/scheduler.py:300-316`) fetch IDs first and then call `get_*()` in a loop (opening a new connection per row).
3. **Raw String Concatenation in SQL (`core/network_intelligence/historical_intelligence.py:142-157` — `CONFIRMED`)**:
   - Interpolates `metric_name` directly into the `SELECT` clause (`"SELECT timestamp, " + metric_name + " FROM nms_interface_metrics ..."`).

---

## 6. Database Schema & Centralization Recommendations (Section F — 8-Point Specification)

To eliminate the 18-DB fragmentation and split-brain conflicts, consolidate all operational and relational data into **one primary database** (`aira_core.db` for single-node SQLite with WAL or PostgreSQL for multi-node production) plus **one dedicated time-series telemetry database** (`aira_telemetry.db` or TimescaleDB).

| 1. Nama Tabel | 2. Tujuan Tabel | 3. Kolom & Tipe Data Utama | 4. Primary Key | 5. Foreign Keys | 6. Indexes | 7. Aturan Kepemilikan Data | 8. Rencana Migrasi |
|---|---|---|---|---|---|---|---|
| **`tenants` (`operational_tenants`)** | Master organization/tenant registry | `tenant_id TEXT`, `name TEXT`, `slug TEXT UNIQUE`, `status TEXT`, `plan_code TEXT`, `created_at TEXT` | `tenant_id` | `plan_code -> subscription_plans(plan_code)` | `idx_tenants_slug` | **Organization** | Retain `operational_tenants` in central DB; enforce FK from all tenant-scoped tables. |
| **`users` (`operational_users`)** | Unified user identity & MFA state | `user_id TEXT`, `tenant_id TEXT NOT NULL`, `username TEXT UNIQUE`, `email TEXT`, `password_hash TEXT`, `mfa_enabled INTEGER`, `mfa_secret_encrypted BLOB`, `must_change_password INTEGER`, `account_enabled INTEGER`, `created_at TEXT` | `user_id` | `tenant_id -> tenants(tenant_id)` | `idx_users_tenant`, `idx_users_username` | **Organization / User** | Encrypt existing `mfa_secret` values in-place; drop legacy `roles_json` in favor of `rbac_user_groups`. |
| **`devices`** | Single Source of Truth for all network devices (merging `inventory.db:devices`, `operational_devices`, `nms_device_profiles`) | `device_id TEXT`, `tenant_id TEXT NOT NULL`, `site_id TEXT`, `name TEXT NOT NULL`, `host TEXT NOT NULL`, `ssh_port INTEGER`, `snmp_port INTEGER`, `device_type TEXT`, `os_version TEXT`, `credential_id TEXT`, `polling_enabled INTEGER`, `polling_protocol TEXT`, `last_status TEXT`, `updated_at TEXT` | `device_id` | `tenant_id -> tenants(tenant_id)`, `credential_id -> credentials(credential_id)` | `UNIQUE(tenant_id, name)`, `idx_devices_tenant_host` | **Organization** (`tenant_id`) | Migrate rows from `inventory.db:devices` and `nms_device_profiles` into `operational_devices`; update `InventoryStore`, `NmsEngine`, and `TopologyEngine` to use this single table. |
| **`credentials`** | Encrypted SSH/SNMP/API device secrets | `credential_id TEXT`, `tenant_id TEXT NOT NULL`, `name TEXT NOT NULL`, `cred_type TEXT`, `username TEXT`, `secret_encrypted BLOB NOT NULL`, `created_at TEXT` | `credential_id` | `tenant_id -> tenants(tenant_id)` | `UNIQUE(tenant_id, name)` | **Organization** (`tenant_id`) | Migrate `inventory.db:credentials`, encrypting plaintext `secret` with `AIRA_MASTER_KEY` (AES-GCM/Fernet). |
| **`user_memories`** | Unified per-user long-term & semantic memory (merging `long_term_memory.db`, `semantic_memory.db`, `topology.db:user_memories`) | `memory_id TEXT`, `tenant_id TEXT NOT NULL`, `user_id TEXT NOT NULL`, `category TEXT`, `content TEXT NOT NULL`, `importance REAL CHECK(importance BETWEEN 0.0 AND 1.0)`, `embedding_blob BLOB`, `source TEXT`, `is_enabled INTEGER`, `created_at TEXT`, `updated_at TEXT` | `memory_id` | `user_id -> users(user_id) ON DELETE CASCADE` | `idx_mem_user_cat`, FTS5 virtual index on `content` | **User Private** (`user_id`) | Redirect `agents/rei/auto_extract.py` and `core/brain.py` from `long_term_memory.db` to `user_memories`; normalize `importance` to `0.0–1.0`; decommission `long_term_memory.db`, `semantic_memory.db`, `interaction_memory.db`. |
| **`user_personas`** | Unified per-user and system preset personas (merging `persona.db` and `topology.db:user_personas`) | `persona_id TEXT`, `user_id TEXT` (NULL for system presets), `name TEXT`, `response_style TEXT`, `language TEXT`, `technical_depth INTEGER`, `behavior_json TEXT`, `custom_instructions TEXT`, `is_system INTEGER` | `persona_id` | `user_id -> users(user_id) ON DELETE CASCADE` | `idx_personas_user` | **User Private** (or **Global Read-Only** when `is_system=1`) | Point `/api/persona` and `PersonaEngine` to `UserPersonaService` (`user_personas` + `user_preferences.active_persona_id`); retire `persona.db`. |
| **`chat_sessions` & `chat_messages`** | Unified multi-user conversation store | `session_id TEXT`, `tenant_id TEXT NOT NULL`, `user_id TEXT NOT NULL`, `title TEXT`, `pinned INTEGER`, `archived INTEGER`, `model_id TEXT`, `created_at TEXT`, `updated_at TEXT` | `session_id` | `user_id -> users(user_id) ON DELETE CASCADE` | `idx_chat_user_updated` | **User Private** (`user_id`) | Consolidate `chat_sessions.db` and `topology.db:chat_sessions` into one schema with mandatory `user_id` FK. |
| **`nms_edge_raw_metrics` vs `nms_raw_metrics`** | Separate Edge Gateway raw telemetry from NMS v2 rollup telemetry (resolving `nms_raw_metrics` collision) | `nms_raw_metrics`: `(id, tenant_id, device_id, entity_type, entity_id, metric_name, timestamp REAL, value REAL, ...)`<br>`nms_edge_raw_metrics`: `(id, tenant_id, gateway_id, device_id, interface_name, metric_name, metric_value REAL, measured_at TEXT, ...)` | `id` | `device_id -> devices(device_id)` | `idx_raw_dev_metric_ts(device_id, metric_name, timestamp)` | **Organization** (`tenant_id`) | Rename `nms_raw_metrics` in `core/edge_gateway/db.py:85` to `nms_edge_raw_metrics` (or unify column names to `timestamp REAL`, `value REAL`) and unify `nms_device_metrics` timestamp column (`polled_at`). |
| **`incidents` (`operational_incidents`)** | Single unified incident table (merging `nms_incidents`, `network_intelligence.db:incidents`, `operational_incidents`) | `incident_id TEXT`, `tenant_id TEXT NOT NULL`, `site_id TEXT`, `device_id TEXT`, `source_subsystem TEXT`, `severity TEXT`, `status TEXT`, `fingerprint TEXT`, `title TEXT`, `summary TEXT`, `opened_at TEXT NOT NULL`, `updated_at TEXT`, `resolved_at TEXT` | `incident_id` | `tenant_id -> tenants(tenant_id)`, `device_id -> devices(device_id)` | `idx_inc_tenant_status`, `idx_inc_fingerprint` | **Organization** (`tenant_id`) | Decommission `ProactiveIncidentEngine` (`incident_engine.py`) in favor of `MultiTenantIncidentEngine`; route NMS and Network Intelligence alerts into `MultiTenantIncidentEngine`. |
