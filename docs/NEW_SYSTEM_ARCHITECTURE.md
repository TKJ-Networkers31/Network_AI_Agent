# AIRA OS — NEW SYSTEM ARCHITECTURE
## AI-Native Network Engineer Workspace & Hybrid Network Operations Platform

**Architecture Version:** 2.0.0  
**Status:** Approved for Implementation  
**Target Codename:** AIRA AI-Native Workspace

---

## 1. Architectural Philosophy & Vision

AIRA OS is re-architected from a traditional, complex operational cockpit into an **AI-native engineering workspace**. 

```
+-----------------------------------------------------------------------------------+
|                                 USER / ENGINEER                                   |
|                "Cek mengapa router cabang tidak dapat akses internet"             |
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|                         MINIMALIST AI WORKSPACE (/app)                            |
|    • Natural Language Conversation               • Contextual Prompt Composer     |
|    • Unified Dynamic Interaction (DIO)           • Interactive Topology / SVG     |
|    • Real-time Activity & Tool Execution         • Downloadable Output Artifacts  |
+-----------------------------------------------------------------------------------+
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
+-----------------------------------+           +-----------------------------------+
|  AIRA REASONING & ORCHESTRATION   |           |    PLATFORM ADMINISTRATION        |
|  • Task Classifier & Model Router |           |    (/admin)                       |
|  • Unified Context Builder        |           |    • Tenant & User Management     |
|  • Dynamic Interaction (DIO)      |           |    • Plan & Entitlement Policy    |
|  • Tool Registry (Cat A/B/C)      |           |    • Token Metering & Allocations |
|  • Centralized Approval Engine    |           |    • Security & Audit Logs        |
+-----------------------------------+           +-----------------------------------+
                  │
                  ▼
+-----------------------------------------------------------------------------------+
|                         CORE DOMAIN SERVICE FABRIC                                |
|  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────────────────┐ |
|  |    UNIFIED        |  |     TOPOLOGY      |  |           REAL-TIME            | |
|  |  INFRASTRUCTURE   |  |     ENGINE        |  |              NMS               | |
|  |  • Single Device  |  |  • 1 Node / Dev   |  |  • SNMP / SSH / API Polling    | |
|  |    Data Model     |  |  • Multi-Interface|  |  • Bandwidth Counter Delta     | |
|  |  • Encrypted Vault|  |    Links          |  |  • Push Telemetry / WS         | |
|  |  • Pending States |  |  • L2/L3/Logical  |  |  • Auto-updating Charts        | |
|  └───────────────────┘  └───────────────────┘  └────────────────────────────────┘ |
|  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────────────────┐ |
|  |    DISCOVERY      |  |    AUTOMATION     |  |          FILES &               | |
|  |     ENGINE        |  |      ENGINE       |  |         ARTIFACTS              | |
|  |  • Single Seed    |  |  • Interval-based |  |  • Safe ZIP Create/Extract     | |
|  |  • LLDP/MNDP/CDP  |  |  • Event-driven   |  |  • Multi-format Parsers        | |
|  |  • ARP & Routing  |  |  • Action Catalog |  |  • Downloadable Artifact Panel | |
|  └───────────────────┘  └───────────────────┘  └────────────────────────────────┘ |
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|                         DATA & ACCESS GOVERNANCE LAYER                            |
|  • AAA Foundation (Authn, Authrz, Accounting)  • Server-Side Tenant Scoping       |
|  • RBAC & Granular Permission Checks           • Free / Pro / Networking++ Quotas |
|  • Secret Redaction & Token Metering           • SQLite WAL Multi-Database        |
+-----------------------------------------------------------------------------------+
```

---

## 2. Navigation & Experience Architecture

### 2.1 Customer Workspace (`/app`)
The primary engineering interface is streamlined into 5 intuitive destinations:
1. **Workspace (`/app` or `/app/workspace`):** Unified natural language conversation with AIRA, session history, contextual file attachments, DIO prompt forms, tool execution traces, and inline rich output (SVG, network topologies, charts, syntax-highlighted configs).
2. **Infrastructure (`/app/infrastructure`):** Integrated device inventory, recursive discovery control, dynamic multi-layer network topology, and real-time NMS telemetry in one consolidated infrastructure view.
3. **Automations (`/app/automations`):** Intuitive automation builder supporting interval-based and event-driven workflows, execution history, and approval triggers.
4. **Files (`/app/files`):** Workspace file browser, secure upload/download, ZIP archive operations, document reading/parsing, and generated downloadable artifact panel.
5. **Settings (`/app/settings`):** Account profile, subscription tier, token quota and usage transparency, security preferences, and approval policies.

### 2.2 Platform Administration (`/admin`)
An isolated, secure administrative cockpit accessible strictly to users with `PLATFORM_SUPER_ADMIN` or `NOC_ADMIN` roles:
- **User & Organization Management:** Tenant onboarding, membership, roles assignment.
- **Entitlement & Subscription Plans:** Free, Pro, and Networking++ tier assignments and grace period configuration.
- **Token Policies & Metering:** Global and tenant-specific token allocations, cost matrix per model/tool, rate limits.
- **Audit & Security Accounting:** Tamper-evident audit logs of all security-sensitive actions and operational executions.
- **System Health:** Gateway connectivity, background poller status, database WAL metrics.

---

## 3. AIRA Reasoning, DIO, and Tool Registry

### 3.1 Central Orchestrator
AIRA acts as the primary brain. It receives user prompts, retrieves context (persona, active devices, topology state, conversation memory), classifies user intent, routes execution, and dynamically interacts with the user when information is missing.

### 3.2 Dynamic Interaction Orchestrator (DIO)
When required parameters are missing (e.g. OSPF area, device target, interface name):
- DIO dynamically renders structured input fields (text, number, single-choice, multiple-choice, boolean, secure credentials, date-time).
- Context awareness: DIO never asks for information already known in the active session, device inventory, or topology context.
- Multi-step wizards maintain parent conversation state and resume execution immediately upon form submission.

### 3.3 Autonomy Policy & Centralized Approval
Every tool registered in AIRA is classified into three explicit risk categories:
- **Category A (Automatic):** Non-destructive, read-only operations (inventory lookup, telemetry polling, configuration parsing, diagram generation). Executed immediately without interruption.
- **Category B (Confirmation Required):** Potentially disruptive or state-changing operations (configuration deployment, service restart, firewall mutation, credential changes, automation activation). Triggers a structured confirmation modal explaining:
  - Intended action and reason.
  - Affected device(s) and resources.
  - Diff or parameter preview.
  - Potential risks and rollback availability.
- **Category C (Restricted):** Actions outside authorized tenant scope, unauthorized infrastructure, or exceeding the user's RBAC role. Strictly rejected at the backend API boundary.

---

## 4. Unified Infrastructure & Topology Engine

### 4.1 Device-Centric Topology Model
A physical or virtual device is represented as **one node** in the graph, regardless of interface count.
- **Node:** Represents the device entity (hostname, IP, vendor, model, device type, management status).
- **Interfaces:** Owned child entities of the device node (e.g., `ether1`, `sfp-sfpplus1`, `wlan1`).
- **Links/Edges:** Independent connection objects connecting a specific `(source_device, source_interface)` to `(target_device, target_interface)`.
- Multiple links between the same pair of devices (e.g. LAG, dual physical trunks) are represented as distinct multi-interface edges, retaining their individual operational status, bandwidth, and protocol evidence.

### 4.2 Progressive Single-Seed Discovery
1. The engineer designates an authorized seed device.
2. The discovery engine queries neighbor protocols (LLDP, CDP, MNDP), ARP tables, and routing tables.
3. Reachable neighboring devices are discovered and deduplicated using MAC, IP, and Chassis IDs.
4. **Pending Device Workflow:** Discovered devices lacking valid credentials are kept in a pending state (`Discovered — SNMP available — Credentials required`) with an action to "Add to Inventory / Configure Access". They are not silently converted to managed devices with dummy passwords.
5. Recursion is strictly bounded by depth limits, approved IP subnets, and loop detection.

---

## 5. Real-Time NMS Architecture

- **Data Pipeline:** Continuous background collection via SNMP, RouterOS API/SSH, and ICMP health checks.
- **Accurate Bandwidth Counter Deltas:**
  $$\text{Bandwidth (bps)} = \frac{(\text{Current Octets} - \text{Previous Octets}) \times 8}{\text{Elapsed Seconds}}$$
  Handles counter resets, 32-bit and 64-bit rollover, and device reboots without generating false zero lines or artificial spikes.
- **Live WebSocket Push:** Telemetry updates (CPU, memory, interface rates) are pushed directly to the frontend via `/ws/nms` and `/ws/bridge`, updating open modals and cards in real time.

---

## 6. Automation & Scheduler Engine

Replaces the legacy stub with a production-grade automation orchestrator:
- **Trigger Types:**
  - *Interval-based:* cron expressions or recurring frequencies (1m, 5m, 1h, 1d, 1w).
  - *Event-driven:* reactive triggers on device state changes (`device_down`, `cpu_threshold_exceeded`, `new_device_discovered`, `monitoring_failed`).
- **Action Catalog:** Parameterized automation tasks (Connectivity probe, telemetry snapshot, configuration backup, topology report, diagnostic run).
- **Safe Execution:** Idempotency keys, duplicate prevention, concurrency throttling, and full execution audit history.

---

## 7. Files, Artifacts, and Archive Security

- **Safe Archive Operations:** ZIP creation and decompression protected against Zip-Slip, directory traversal, decompression bombs, and symlink exploits.
- **Downloadable Output Panel:** Distinguishes temporary chat artifacts from permanent workspace project files.
- **Multi-Format Parsers:** Structured parsing and AI context ingestion for TXT, MD, JSON, YAML, CSV, PDF, DOCX, XLSX, and configuration scripts.

---

## 8. Multi-Tenancy, AAA, and Entitlement System

- **Identity & Authentication:** Email/password authentication with verification tokens, password reset, configurable Google OAuth 2.0 integration, and secure session management.
- **Tenant Isolation:** Every device, topology edge, telemetry sample, automation, and file is strictly scoped by `tenant_id` at the database and API query layer.
- **Product Tiers & Entitlements:**
  - **Free:** Base AI workspace, limited token quota, basic files, networking capabilities locked unless granted.
  - **Pro:** Expanded AI capabilities, larger token quota, advanced file operations.
  - **Networking++:** Independent entitlement add-on granting access to infrastructure inventory, recursive discovery, topology engine, real-time NMS, and network automations.
- **Accurate Token Metering:** Centralized policy engine tracking input, output, cached tokens, and tool charges with atomic balance checking.
