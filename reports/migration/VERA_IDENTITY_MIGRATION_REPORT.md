# VERA Identity Migration Report
## Phase 1: Establishing VERA as the Authoritative and Sole Active Product Identity

**Document Version:** 1.0.0  
**Authority:** Principal Software Architect, Frontend Platform Architect, Application Security Engineer  
**Date:** 2026-11-09  
**Target Identity:** VERA — Enterprise Network Intelligence Platform  
**Legacy Identity:** AIRA OS / Network AI Agent  

---

## 1. Executive Summary

This report establishes the complete identity migration policy transforming the legacy AIRA product identity into VERA. 

Under the **Non-Negotiable Principle**:
> **AIRA must cease to be the active product identity, but its development history must remain accessible to VERA.**

All user-facing interfaces, AI persona definitions, service headers, backend health endpoints, and runtime event emitters are transitioned to VERA. Historical engineering documentation, remediation stage reports, commit histories, and legacy capability maps are preserved as immutable historical records.

---

## 2. Identity Audit & Classification Taxonomy

Every reference to `AIRA` across the entire codebase has been audited and cataloged into one of 13 architectural categories:

| Category | Description | Migration Action |
|---|---|---|
| **1. Active Product Identity** | Application titles, headers, brand emblems, UI navigation | Replaced with **VERA** |
| **2. Active AI Assistant Persona** | Persona engine default names, greeting prompts, role descriptions | Replaced with **VERA — Enterprise Network Intelligence Platform** |
| **3. Backend Service Identity** | Service metadata, OpenAPI documentation, health endpoints | Migrated to **VERA** (`{"status": "ok", "ecosystem": "VERA"}`) |
| **4. AI Provider Request Context** | OpenRouter/NVIDIA HTTP headers (`X-Title`) | Updated to `VERA Platform` |
| **5. Runtime Event Agent** | Event bus emitter name (`EVENT_AGENT`) | Updated to `VERA` |
| **6. API Contracts & Headers** | Admin authentication tokens, actor headers | Dual-support: `X-VERA-*` (primary) + `X-AIRA-*` (fallback) |
| **7. Configuration & Environment** | Environment variables (`VERA_*` vs `AIRA_*`) | Dual-lookup with graceful fallback |
| **8. Voice Companion Wake-Word** | Speech recognition trigger & UI captions | Updated to `VERA` (phonetic matches: "vera", "ve-ra", "wera") |
| **9. Database Namespace** | Internal SQLite filenames, table names | Preserved (abstracted via VERA services) to avoid data corruption |
| **10. Historical Provenance** | Stage 01–14 reports, audit files, ADRs | **Strictly Preserved** as immutable historical archive |
| **11. Project Heritage** | New historical knowledge engine | Implemented in `core/knowledge/heritage/` |
| **12. Test Fixtures & Assertions** | Unit, integration, and e2e test suites | Updated active tests to assert VERA; preserved historical tests |
| **13. Deployment Infrastructure** | Docker containers, compose services, systemd units | Authoritative VERA naming with legacy aliases |

---

## 3. Active vs. Historical Identity Matrix

| Subsystem / Surface | Legacy Active Identity | New Authoritative VERA Identity | Historical Continuity Strategy |
|---|---|---|---|
| **Platform Name** | AIRA OS | VERA | Preserved in `VERA_PROJECT_HISTORY.md` |
| **Tagline** | Adaptive Intelligent Reasoning Assistant | Enterprise Network Intelligence Platform | Preserved in Project Heritage |
| **AI Assistant Persona** | AIRA (Akane / Sensei / Companion) | VERA (Akane / Sensei / Companion) | Persona styles retain character flavor under VERA identity |
| **Assistant Greeting** | "Halo! Aku AIRA. Ada yang mau kita bangun hari ini? 🌸" | "Halo! Saya VERA, asisten intelijen jaringan Anda. Ada yang bisa saya bantu hari ini?" | Configurable per persona preset |
| **Selection Action** | "Tanya AIRA" | "Tanya VERA" | Retains seamless contextual prompt injection |
| **Loading Indicator** | "Menyiapkan AIRA..." | "Menyiapkan VERA..." | High-contrast glassmorphic loader |
| **Error Boundary** | "AIRA mengalami error tidak terduga" | "VERA mengalami error tidak terduga" | Retains automatic bug reporting and session recovery |
| **Voice Status** | "AIRA Menjawab..." / "AIRA Siap" | "VERA Menjawab..." / "VERA Siap" | Dual-chime acoustic notification |
| **Health API** | `{"ecosystem": "AIRA"}` | `{"ecosystem": "VERA", "platform": "VERA Enterprise Network Intelligence Platform"}` | Backward-compatible JSON response |
| **Outbound LLM Title** | `X-Title: AIRA Ecosystem` | `X-Title: VERA Platform` | Verified with OpenRouter & NVIDIA NIM |
| **Event Bus Agent** | `EVENT_AGENT = "AIRA"` | `EVENT_AGENT = "VERA"` | Normalized across all telemetry events |

---

## 4. Identity Policy Enforcement Rules

1. **Rule 1 (Zero Active AIRA Branding):** No user-facing UI screen, button, tooltip, modal, or toast may display "AIRA" as the active platform or assistant name.
2. **Rule 2 (Immunity for Historical Archives):** Files in `AUDIT_REPORT/`, `docs/brand-history/`, `PHASE_*_COMPLETION_REPORT.txt`, and git logs are historical records and must never be altered or purged to fake brand continuity.
3. **Rule 3 (Backward-Compatible Runtime):** All environment variables and HTTP headers must accept `VERA_*` as primary while silently supporting `AIRA_*` for legacy external scripts.
4. **Rule 4 (Heritage Availability):** VERA must natively answer user questions regarding its AIRA origin through its historical knowledge retrieval engine.

**Phase 1 Status:** POLICY ESTABLISHED & MAPPED.
