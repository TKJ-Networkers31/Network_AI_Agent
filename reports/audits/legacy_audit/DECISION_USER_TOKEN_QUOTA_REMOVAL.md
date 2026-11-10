# AIRA OS — OWNER DECISION: COMPLETE REMOVAL OF PER-USER AI TOKENIZATION
(`DECISION_USER_TOKEN_QUOTA_REMOVAL.md`)

**Date**: 2026-11-08  
**Status**: APPROVED & MANDATORY  
**Decision Authority**: System Owner  
**Supersedes**: `REC-10` ("Refactor Token Quota Calculation and Column Naming"), Phase E.1 Section 2 Quota Governance, and previous token quota deduction plans.

---

## 1. PURPOSE AND RATIONALE

AIRA OS is an internal/enterprise-grade AI-native Network Engineering Workspace. In the target operational deployment model:
1. AIRA is deployed for authenticated internal operators, network engineers, and tenant administrators.
2. Per-user artificial token quotas, remaining balance checks, and per-turn token deductions introduce unnecessary operational friction, state complexity, SQLite write lock contention during chat streaming, and schema maintenance burdens.
3. Provider API credentials and model routing are governed at the platform/tenant infrastructure level, not metered as consumer credit balances per engineer.

Therefore, the owner has explicitly ordered the **complete removal of all per-user AI token quota, remaining balance counters, and token accounting subsystems**.

---

## 2. SCOPE OF ELIMINATION

The following components and behaviors are **permanently removed**:

### 2.1 Backend Services & Endpoints
- `core/tenant/token_quota_service.py` (and all classes: `TokenQuotaService`, `QuotaTierSpec`, `TokenPolicy`, `TokenBalance`, etc.).
- Admin token policy and adjustment endpoints in `api/routers/admin_platform.py`:
  - `GET /api/v1/admin/token-policy`
  - `PUT /api/v1/admin/token-policy`
  - `POST /api/v1/admin/tokens/adjust`
  - `POST /api/v1/admin/tokens/reset`
  - `POST /api/v1/admin/tokens/sweep`
  - `PUT /api/v1/admin/tokens/plan-policy`
- User token usage endpoint:
  - `GET /api/token-usage` in `api/routers/chat.py`
- Token quota checks and post-generation deductions in:
  - `api/routers/chat.py` (`POST /api/chat`, `GET /api/chat/stream`)
  - `api/routers/ws.py` (`WebSocket /ws/chat/{session_id}`)

### 2.2 Database Structures (DDL & Schema)
The following tables, indexes, and constraints in `core/tenant/db.py` and `topology.db` are removed:
- `operational_token_balances`
- `operational_token_usage_ledger`
- `operational_token_quota_adjustments`
- `operational_token_policies` (confirmed exclusively related to the removed AI token quota system)
- Associated SQLite indexes: `idx_token_balance_tenant`, `idx_token_ledger_user`, `idx_quota_adj_user`.
- Default policy seeding routines (`pol_global_free`, `pol_global_pro`, `pol_global_enterprise`).

### 2.3 Frontend UI Components
- Token balance badges (`TokenUsageBadge.jsx`) and token quota indicators.
- "Tokens" tab in `AdminPlatformPage.jsx`.
- Remaining token alerts and warning banners in `ChatPage.jsx`.
- Quota models and API clients in `api.js`.

---

## 3. STRICT PRESERVATION INVARIANTS

The removal of AI token quotas **must NOT compromise authentication or security tokens**:
1. **User Login & Session Tokens**: `operational_user_sessions` and JWT/Bearer session validation tokens must remain 100% intact.
2. **Session Lifetimes & Revocation**: Token expiration, idle timeout, session revocation, and logout flows must remain intact.
3. **Gateway M2M Tokens**: Appliance enrollment tokens (`operational_gateway_tokens`) and M2M bearer tokens must remain intact.
4. **Provider Credentials**: LLM provider API keys (OpenAI, Gemini, Anthropic, NVIDIA, Groq) and vault encryption keys must remain intact.
5. **Model Governance**: Model catalog, enabled status, provider selection, and RBAC permissions (`models.read`, `models.manage`) must remain intact.

---

## 4. ACCEPTANCE CRITERIA

1. Any authenticated user can interact with AI chat without requiring a token balance row in SQLite.
2. No token deduction SQL statements execute during or after chat generation.
3. Chat streaming (SSE and WebSocket) functions without quota exhaustion barriers.
4. The database schema has zero `operational_token_*` tables.
5. All tests verify that chat functions cleanly and no broken imports remain.
