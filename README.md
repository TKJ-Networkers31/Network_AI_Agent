# VERA — Enterprise Network Intelligence Platform

> **Understand. Monitor. Automate.**

[![CI/CD Pipeline](https://github.com/Lingga/Network_AI_Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Lingga/Network_AI_Agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Enterprise-blue.svg)](#)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.15-blue.svg)](#)
[![Node](https://img.shields.io/badge/node-20%2B-green.svg)](#)

---

## 1. Overview

**VERA** is an Enterprise Network Intelligence Platform that unifies real-time telemetry monitoring, multi-layer topology discovery (L1 Physical, L2 Data Link, L3 Routing, and Overlays), AI-assisted root-cause diagnostics, and safe, approval-gated network automation into a coherent operational ecosystem.

VERA is engineered for Network Reliability Engineers (NREs), Network Operations Centers (NOCs), and infrastructure architects.

### Brand Personality & Core Tenets
- **Intelligent**: Automated correlation, cross-device path reasoning, and predictive anomaly forecasting.
- **Precise**: Exact telemetry units, sub-second polling, and zero fabricated topology edges.
- **Reliable**: Read-only boundaries for diagnostics, strict RBAC, and approval gates for changes.
- **Futuristic & Enterprise-Oriented**: Dark navy, high-density telemetry console built for 24/7 mission-critical operations.

> **Historical Note:** VERA evolved from the original AIRA research project into a full-scale Enterprise Network Intelligence Platform. Detailed historical provenance and architectural decisions are preserved in [`docs/brand-history/AIRA_TO_VERA.md`](docs/brand-history/AIRA_TO_VERA.md).

---

## 2. Architecture & Specialist Agents

Within the VERA ecosystem, user requests and autonomous triggers are processed through specialized internal domain agents:

| Specialist Agent | Subsystem | Domain & Responsibilities |
|---|---|---|
| **AKANE** | Autonomous Knowledge & Action Network Engine | SSH preflight, RouterOS/Cisco/VyOS execution, persistent session management, configuration safety review |
| **REI** | Reasoning & Executive Intelligence | Investigation planning, multi-step correlation, diagnostic report generation |
| **HIKARI** | Hybrid Image & Knowledge Recognition | Multimodal network diagram analysis, topology OCR, visual schematics |
| **YUKI** | Voice & Telemetry Speech Engine | Real-time speech-to-text, low-latency audio telemetry, voice companion |

```
Engineers / NOC
      │
      ▼
┌──────────────┐
│  VERA Core   │ ◄─── REST & WebSocket Gateway (FastAPI)
└──────┬───────┘
       │
  ┌────┴───────────────────────────┐
  ▼                                ▼
┌──────────────────────┐    ┌──────────────────────┐
│  Topology & NMS      │    │  Reasoning Engine    │
│  - Multi-layer graph │    │  - AKANE & REI       │
│  - Telemetry poller  │    │  - Deterministic RCA │
│  - SQLite SSD SSOT   │    │  - Guarded Playbooks │
└──────────────────────┘    └──────────────────────┘
```

---

## 3. Directory Layout

```
.
├── VERA_ECOSYSTEM/               # Primary tracked backend & frontend source
│   ├── api/                      # FastAPI routers, OpenAPI schemas, WebSocket managers
│   ├── core/                     # NMS poller, topology engine, RBAC, tenant manager, crypto
│   ├── agents/                   # Specialist agents (akane, rei, hikari, yuki)
│   ├── database/                 # SQLite storage (topology, inventory, logs, memory)
│   ├── app/frontend/             # React 18, Vite 8, Tailwind CSS v4 web application
│   └── tests/                    # Pytest test suite (>2,000 tests)
├── AIRA_ECOSYSTEM -> VERA_ECOSYSTEM # Backward compatibility symlink
├── deploy/                       # Nginx reverse proxy configs & systemd services
├── docs/                         # Architecture blueprints, specifications, and brand history
│   ├── branding/                 # VERA brand guidelines & SVG vector assets
│   ├── brand-history/            # Historical record from AIRA to VERA
│   └── migration/                # Baseline, rename manifest, and rollback plan
├── reports/                      # Forensic audits, engineering reports, and specifications
│   ├── audits/                   # Network, UX, and security forensic audits
│   ├── engineering/              # Technical implementation & reliability reports
│   ├── migration/                # Migration phase completion reports & plans
│   ├── specifications/           # VAE protocols, UI component catalogs & specs
│   └── README.md                 # Complete index and navigation catalog
├── Dockerfile                    # Multi-stage production container build
├── docker-compose.yml            # Container deployment orchestration
└── pytest.ini                    # Pytest test paths & configuration
```

---

## 4. Quickstart

### Prerequisites
- Python 3.12+ (or 3.15)
- Node.js 20+ and npm 10+
- SQLite 3

### Running the Backend
```bash
# Activate virtual environment
source .venv/bin/activate

# Launch VERA API server
cd VERA_ECOSYSTEM
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running the Frontend
```bash
cd VERA_ECOSYSTEM/app/frontend
npm install
npm run dev
```

### Running with Docker Compose
```bash
docker compose up -d
```

---

## 5. Verification & Tests

### Backend Unit & Integration Tests
```bash
pytest VERA_ECOSYSTEM/tests/test_phase_h_security_and_governance.py -v
pytest VERA_ECOSYSTEM/tests/test_global_settings.py -v
```

### Frontend Production Build & Unit Tests
```bash
cd VERA_ECOSYSTEM/app/frontend
npm test          # 275 passing unit tests
npm run build     # Production Vite bundle
```

---

## 6. Security & Governance Invariants
- **No Guest Mode**: Anonymous access is prohibited. All actions require authenticated user or machine identity.
- **No Per-User Token Quotas or Billing**: VERA is an enterprise infrastructure tool, not a metered chatbot.
- **Read-Only Diagnostics**: Automated diagnostic playbooks cannot execute mutating configuration commands without explicit two-stage approval.
- **Isolated User Contexts**: Operator personal notes and memory remain isolated while network topology and inventory are shared across organization boundaries.
