# AIRA OS — ENTITLEMENT AND TOKEN POLICY SYSTEM
## Tiered Plans, Independent Networking++, and Atomic Token Accounting

**Version:** 1.0.0  
**Status:** Canonical Entitlement Specification  

---

## 1. Product Tiers & Entitlements Architecture

AIRA OS decouples base workspace capabilities from specialized infrastructure features through an entitlement engine.

```
+-------------------------------------------------------------------------------+
|                            BASE SUBSCRIPTION TIERS                            |
|                                                                               |
|   ┌──────────────────────────┐             ┌──────────────────────────────┐   |
|   |         FREE             |             |             PRO              |   |
|   | • 100,000 Tokens/Month   |             | • 2,000,000 Tokens/Month     |   |
|   | • 10,000 Daily Limit     |             | • 200,000 Daily Limit        |   |
|   | • Basic AI Reasoning     |             | • Advanced Models & Files    |   |
|   | • Networking: LOCKED     |             | • Networking: Add-on         |   |
|   └──────────────────────────┘             └──────────────────────────────┘   |
+-------------------------------------------------------------------------------+
                                        │
                                        ▼
+-------------------------------------------------------------------------------+
|                    SPECIALIZED ADD-ON: NETWORKING++                           |
|                                                                               |
|   • Device Inventory & Credential Vault                                       |
|   • Recursive Single-Seed Discovery (LLDP/MNDP/CDP/ARP/Route)                |
|   • Device-Centric Multi-Interface Topology Graph                             |
|   • Real-Time NMS Telemetry & Accurate Delta Bandwidth                        |
|   • Network Automations & Event-Driven Triggers                               |
|   • Can be granted independently to Free, Pro, or Enterprise tenants          |
+-------------------------------------------------------------------------------+
```

---

## 2. Admin-Configurable Token Policies

Token limits and costs are managed centrally via `operational_token_policies` in SQLite, allowing runtime adjustment without code redeployment:

### 2.1 Default Policy Matrix

| Parameter | Free Tier | Pro Tier | Enterprise Tier |
|---|---|---|---|
| Monthly Token Allocation | 100,000 | 2,000,000 | 10,000,000 |
| Daily Token Limit | 10,000 | 200,000 | 1,000,000 |
| Rate Limit (RPM) | 30 requests/min | 120 requests/min | 300 requests/min |
| Max Request Size | 16,384 tokens | 65,536 tokens | 131,072 tokens |
| Networking++ Default | Disabled (Locked) | Add-on (Optional) | Enabled (Included) |

### 2.2 Tool Execution Costs (in Credits/Tokens)
Tools consume a base cost in addition to prompt/completion tokens:
- **Ping / Reachability Probe:** 5 credits
- **Diagnostic Inspection:** 50 credits
- **Configuration Analysis & Diff:** 100 credits
- **Recursive Network Discovery:** 150 credits
- **Configuration Push:** 200 credits
- **Document / Artifact Generation:** 100 credits

---

## 3. Atomic Token Accounting & Metering

### 3.1 Metering Categories
To ensure honest accounting:
- **Input Tokens:** Actual prompt tokens evaluated by the underlying model provider.
- **Output Tokens:** Tokens generated in the AI response stream.
- **Cached Tokens:** In-memory or prompt-cached tokens (billed at discounted rate if supported).
- **Tool Credits:** Execution costs applied when authorized tools are dispatched.

### 3.2 Anti-Bypass Concurrency Enforcement
1. **Pre-flight Budget Check:** Before dispatching an inference or tool request, `can_consume(tenant_id, estimated_tokens)` validates that the remaining balance is greater than zero and can accommodate the task.
2. **Atomic Ledger Insertion:** Upon request completion, actual token consumption is recorded in `operational_token_usage_ledger` and subtracted from `operational_token_balances` within a serialized SQLite transaction (`topology_transaction(write=True)`).
3. **Monthly Rollover:** If the current date exceeds `period_reset_utc`, the balance is automatically refreshed to the monthly allocated quota.

---

## 4. User and Admin Transparency Interfaces

### 4.1 User View (`/app/settings` -> Subscription & Quotas)
- Active Plan: `FREE`, `PRO`, or `ENTERPRISE`.
- Networking++ Status: `ACTIVE` (with green badge) or `DISABLED` (with upgrade prompt).
- Usage Progress Bar: Visual display of used vs. allocated tokens for the active cycle.
- Reset Countdown: Date and time of next quota renewal.
- Historical Ledger: Recent requests with model, tool, and token breakdown.

### 4.2 Administrator Controls (`/admin` -> Plan & Token Management)
- Manual Plan Assignment: Admins can assign tiers and toggle Networking++ with custom expiration dates.
- Policy Editor: Adjust default allocations, daily limits, and tool costs.
- Organization Ledger: View and export aggregated token usage across all customer tenants.
