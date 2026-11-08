# VERA Ecosystem

> **One Platform. Unified Network Intelligence.**

Users and NOC engineers interact with **VERA** (Enterprise Network Intelligence Platform). All specialized domain capabilities (network telemetry, topology, reasoning, vision, voice) are coordinated by internal specialist agents:

| Agent  | Full Designation                                       | Domain                                   |
|--------|--------------------------------------------------------|-------------------------------------------|
| **AKANE**  | Autonomous Knowledge & Action Network Engine           | SSH, SNMP, RouterOS, Cisco, Linux, persistent execution |
| **REI**    | Reasoning & Executive Intelligence                     | Planning, tool selection, multi-step correlation, diagnostic reports |
| **HIKARI** | Hybrid Image & Knowledge Recognition                   | Vision, OCR, topology diagram parsing, screenshot understanding |
| **YUKI**   | Voice & Audio Telemetry Pipeline                       | Speech recognition (STT), voice synthesis (TTS), audio companion |

## Interaction Flow

```
Engineer -> VERA Core -> Intent & Policy -> REI (Planner) -> AKANE (Network) -> Deterministic Telemetry -> VERA -> Engineer
```

Example: `"Audit BGP and interface errors on Spine-1"` => VERA -> REI -> AKANE (read-only SSH/SNMP) -> Telemetry Correlation -> VERA Dashboard

## Core Invariants
- All actions require authentication; no guest mode or billing bypass.
- Mutating commands require explicit approval gates.
- Database integrity: SQLite WAL mode with zero schema loss.
- High-contrast WCAG 2.2 compliant dark navy UI.
