# VERA Architectural Decision History (ADR Log)

## Executive Summary

This document consolidates the key Architectural Decision Records (ADRs) that governed the evolution of the platform from its early exploratory stages through its stabilization, remediation, and final transformation into VERA.

---

## ADR Index

| ADR ID | Decision Title | Status | Historical Origin |
| :--- | :--- | :--- | :--- |
| **ADR-001** | Decentralized SQLite Domain Storage Architecture | ACCEPTED / ACTIVE | 2026-09 (AIRA Genesis) |
| **ADR-002** | 14-Step Deterministic Root Cause Analysis (RCA) Engine | ACCEPTED / ACTIVE | 2026-10 (Networking VI) |
| **ADR-003** | The Dude Native Protocol Topology Discovery | ACCEPTED / ACTIVE | 2026-10 (Networking VII) |
| **ADR-004** | Complete Removal of Token Quotas, Paywalls & Stripe Billing | ACCEPTED / ACTIVE | 2026-11 (Stage 13 Remediation) |
| **ADR-005** | Zero-Trust SecretVault with AES-256-GCM Encryption | ACCEPTED / ACTIVE | 2026-10 (Stage 03 Remediation) |
| **ADR-006** | VERA Adaptive Experience (VAE) Protocol & Streaming UI | ACCEPTED / ACTIVE | 2026-11 (VAE Architecture) |
| **ADR-007** | Restoration of Jet Black Cyber Glass Design Language | ACCEPTED / ACTIVE | 2026-11 (Design Baseline Restoration) |
| **ADR-008** | Full Platform Identity & Ecosystem Migration to VERA | ACCEPTED / ACTIVE | 2026-11 (Current Transformation) |

---

### ADR-001: Decentralized SQLite Domain Storage Architecture

- **Context**: The platform requires persistent storage across heterogeneous domains: network device inventory, continuous telemetry metrics, topology graph adjacencies, chat session logs, user memory, and access control policies. Traditional monolithic databases (PostgreSQL, MySQL) introduce substantial deployment overhead for on-premise edge appliances.
- **Decision**: Partition storage into domain-isolated SQLite databases (`devices.db`, `metrics.db`, `topology.db`, `persona.db`, `auth.db`, `vault.db`), all operating in Write-Ahead Logging (WAL) mode with busy timeouts configured to 5000ms.
- **Consequences**:
  - Positive: Zero external database dependencies; trivial automated file-level backups; domain fault isolation; sub-millisecond read latencies.
  - Negative: Requires careful foreign-key decoupling across separate database files.

---

### ADR-002: 14-Step Deterministic Root Cause Analysis (RCA) Engine

- **Context**: Relying exclusively on Large Language Models (LLMs) to diagnose critical network failures risks hallucinations, incorrect configuration suggestions, and non-deterministic troubleshooting.
- **Decision**: Implement a pure Python, deterministic 14-step RCA engine (`core/diagnostics/rca_engine.py`) that evaluates network metrics, physical link states, gateway reachability, ARP tables, DNS resolution, and MTU states sequentially. LLMs are used solely to format human-readable explanations of the deterministic findings.
- **Consequences**:
  - Positive: 100% reproducible diagnoses; zero risk of AI hallucinating phantom link states or erroneous subnets; high operational trust.
  - Negative: Engine rules must be updated whenever new network protocol edge cases are introduced.

---

### ADR-003: The Dude Native Protocol Topology Discovery

- **Context**: Discovering network topology in heterogeneous MikroTik and third-party environments requires protocol resilience without installing heavy SNMP agents on every host.
- **Decision**: Directly parse RouterOS native discovery protocols (MikroTik Neighbor Discovery Protocol - MNDP, Cisco Discovery Protocol - CDP, Link Layer Discovery Protocol - LLDP, and dynamic ARP caches) to recursively map L2/L3 adjacencies.
- **Consequences**:
  - Positive: Discovers routers, switches, access points, and edge gateways automatically with zero extra software required on nodes.
  - Negative: Requires valid API or SSH credentials on seed devices.

---

### ADR-004: Complete Removal of Token Quotas, Paywalls & Stripe Billing

- **Context**: Early prototypes explored consumer SaaS mechanics, including AI token accounting, wallet balances, Stripe webhook handlers, and paywall gates. However, enterprise network intelligence requires continuous, uninterrupted operations (24/7 monitoring, telemetry analysis, emergency RCA). Imposing token quotas on mission-critical network diagnostics is dangerous and unacceptable to enterprise operators.
- **Decision**: Permanently excise all token debiting logic, billing tables, Stripe subscription verifications, and paywall checks (documented in `HERITAGE-04-BILLING-REMOVAL`). Transition VERA to a 100% free, unlimited, on-premise enterprise model.
- **Consequences**:
  - Positive: Zero diagnostic interruptions; eliminates commercial cloud vendor dependencies; ensures reliable air-gapped on-premise deployment.
  - Negative: Any future commercialization must occur at the enterprise appliance/support tier rather than per-token microtransactions.

---

### ADR-005: Zero-Trust SecretVault with AES-256-GCM Encryption

- **Context**: Storing router administrative credentials, SSH private keys, and API tokens in plaintext or reversible base64 constitutes a critical security vulnerability.
- **Decision**: Build an enterprise SecretVault using AES-256-GCM authenticated encryption. Master keys are derived via PBKDF2 with 100,000 iterations and salt, backed by OS keystores or platform master secrets. Credential access is restricted by RBAC permissions and logged to audit trails.
- **Consequences**:
  - Positive: FIPS-compliant encryption for all stored credentials; tamper detection via GCM authentication tags; zero credential leakage in logs.
  - Negative: Loss of master key renders credentials unrecoverable (requires proper master key backup policies).

---

### ADR-006: VERA Adaptive Experience (VAE) Protocol & Generative UI

- **Context**: Traditional chat interfaces are inadequate for network operations. Operators need dynamic charts, interactive topology sub-panels, ping latency sparklines, and structured confirmation dialogs rendered inline.
- **Decision**: Implement the VERA Adaptive Experience (VAE) protocol: a JSON-over-SSE/WebSocket protocol that streams generative UI components, interactive forms (Dynamic Interaction Orchestration - DIO), and adaptive side panels directly to the PWA frontend.
- **Consequences**:
  - Positive: Rich, responsive observability interface; deep human-in-the-loop safety for dangerous network commands.
  - Negative: Frontend components must conform strictly to the VAE schema catalog.

---

### ADR-007: Restoration of Jet Black Cyber Glass Design Language

- **Context**: A previous commit introduced an accidental design drift towards an unintended deep navy blue theme (`#071426`), deviating from the authoritative high-contrast dark cyberpunk palette established in commit `a6eb27f`.
- **Decision**: Formally lock and restore the Jet Black Cyber Glass palette:
  - Base Canvas: `#000000` (True OLED Black).
  - Surface Glass: `#04060c` / `#080d19` with subtle borders (`rgba(56, 189, 248, 0.1)`).
  - Primary Accent: `#38BDF8` (Electric Cyan).
  - Secondary Accent: `#8B5CF6` (Cyber Violet).
  - Layout: Single centered Hero greeting (eliminated duplicate top-left corner greeting).
- **Consequences**:
  - Positive: Authoritative, visually striking, high-contrast NOC/SOC display aesthetic; reduced OLED monitor power draw.
  - Negative: None.

---

### ADR-008: Full Platform Identity & Ecosystem Migration to VERA

- **Context**: The platform outgrew its "AIRA" prototype name. Maintaining dual naming or incomplete rebranding created cognitive friction and confusion in production deployments.
- **Decision**: Perform a total, P0 engineering migration: establish VERA as the sole active runtime identity across UI, backend, APIs, logs, and documentation, while retaining historical knowledge in a dedicated heritage engine (`core/knowledge/heritage/`).
- **Consequences**:
  - Positive: Unified, professional enterprise identity; complete historical self-awareness.
  - Negative: External automation scripts targeting legacy HTTP headers must be transitioned to `X-VERA-*` (supported via fallback headers).
