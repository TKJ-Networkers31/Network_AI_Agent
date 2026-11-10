# VERA Adaptive Experience (VAE) — Test Execution Report

**Execution Date:** 2026-11-08  
**Test Harness:** Node.js v26.13.0 (`node --test`), Python 3.15.0 (`pytest 9.2.0`), Vite 6.4.1  
**Total Tests Executed:** 390 (296 Frontend Unit Tests + 8 Backend VAE Tests + 86 Regression Tests)  
**Pass Rate:** 100% (0 Failures, 0 Regressions)  

---

## 1. Test Execution Summary

| Domain | Test Suite | Framework | Total Tests | Passed | Failed | Status |
|---|---|---|---|---|---|---|
| Frontend Protocol | `vaeProtocol.test.js` | Node.js Test Runner | 6 | 6 | 0 | PASSED |
| Frontend Registry Core | `registryCore.test.js` | Node.js Test Runner | 4 | 4 | 0 | PASSED |
| Frontend Mermaid Engine | `mermaidParser.test.js` | Node.js Test Runner | 4 | 4 | 0 | PASSED |
| Frontend Image Policy | `imagePolicy.test.js` | Node.js Test Runner | 4 | 4 | 0 | PASSED |
| Frontend Telemetry | `experienceTelemetry.test.js`| Node.js Test Runner | 3 | 3 | 0 | PASSED |
| Frontend Full Baseline | `npm test` (All 296 tests) | Node.js Test Runner | 296 | 296 | 0 | PASSED |
| Backend VAE Protocol | `test_vae_protocol.py` | Pytest | 5 | 5 | 0 | PASSED |
| Backend Security & RBAC | `test_vae_security_and_action_card.py`| Pytest | 3 | 3 | 0 | PASSED |
| Backend DIO & Streaming | `test_dio_*.py` + `test_streaming.py`| Pytest | 86 | 86 | 0 | PASSED |
| Production Build | `npm run build` | Vite 6 / Rolldown | 1 | 1 | 0 | PASSED (1.74s) |

---

## 2. Backend Test Results (`pytest`)

```text
============================= test session starts ==============================
platform linux -- Python 3.15.0, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/Lingga/Documents/project/Network_AI_Agent
configfile: pytest.ini

VERA_ECOSYSTEM/tests/test_vae_protocol.py::TestVaeProtocol::test_brain_response_adapter_generates_markdown_and_dio_blocks PASSED [ 12%]
VERA_ECOSYSTEM/tests/test_vae_protocol.py::TestVaeProtocol::test_supported_block_types PASSED [ 25%]
VERA_ECOSYSTEM/tests/test_vae_protocol.py::TestVaeProtocol::test_validate_unsupported_block_falls_back_to_unknown PASSED [ 37%]
VERA_ECOSYSTEM/tests/test_vae_protocol.py::TestVaeProtocol::test_validate_vae_payload_tolerates_corrupted_blocks PASSED [ 50%]
VERA_ECOSYSTEM/tests/test_vae_protocol.py::TestVaeProtocol::test_validate_valid_block PASSED [ 62%]
VERA_ECOSYSTEM/tests/test_vae_security_and_action_card.py::TestVaeSecurityAndActionCard::test_admin_can_simulate_user_in_same_tenant PASSED [ 75%]
VERA_ECOSYSTEM/tests/test_vae_security_and_action_card.py::TestVaeSecurityAndActionCard::test_simulate_without_user_id_derives_authenticated_caller PASSED [ 87%]
VERA_ECOSYSTEM/tests/test_vae_security_and_action_card.py::TestVaeSecurityAndActionCard::test_unauthenticated_simulation_rejected PASSED [100%]

======================== 8 passed, 33 warnings in 3.45s ========================
```

---

## 3. Frontend Unit & Integration Results (`npm test`)

```text
✔ normalizeToVaeBlocks: wraps plain string into single markdown block
✔ normalizeToVaeBlocks: separates content and interaction_schema into markdown and dio blocks
✔ normalizeToVaeBlocks: tolerates missing content with only interaction_schema
✔ normalizeToVaeBlocks: passes through already valid VAE blocks array
✔ normalizeToVaeBlocks: converts unsupported block types to fallback unknown blocks
✔ isVaePayload & createVaePayload: validates payload structure
✔ registryCore: registers and retrieves components
✔ registryCore: returns fallback for unregistered types
✔ registryCore: lists all registered types
✔ registryCore: prevents duplicate registration without explicit override
✔ Mermaid Parser: parses basic graph TD with directional nodes
✔ Mermaid Parser: parses graph LR with edge labels and styles
✔ Mermaid Parser: generates valid SVG output
✔ Mermaid Parser: gracefully handles empty or invalid code
✔ Remote Image Policy: allows valid public HTTPS and HTTP URLs
✔ Remote Image Policy: rejects dangerous protocol schemes
✔ Remote Image Policy: blocks SSRF / loopback / private IP addresses
✔ Remote Image Policy: exposes standard security attributes
✔ Experience Telemetry: tracks block rendered events
✔ Experience Telemetry: tracks interaction submitted events
✔ Experience Telemetry: honors setTelemetryEnabled(false)

ℹ tests 296
ℹ suites 0
ℹ pass 296
ℹ fail 0
ℹ duration_ms 2209.42ms
```

---

## 4. Frontend Production Build Performance (`npm run build`)

- **Build Duration:** 1.74s - 2.24s (sub-3-second production build target met).
- **Code-Splitting Verification:**
  - `dist/assets/UnifiedActionCard-CjhkkcKY.js` — **6.70 kB** (gzip: 2.39 kB)
  - `dist/assets/MermaidBlock-CdUfPMuj.js` — **7.83 kB** (gzip: 3.45 kB)
  - `dist/assets/GraphBlock-vJhoS3Rt.js` — **5.38 kB** (gzip: 2.28 kB)
  - `dist/assets/MapBlock-CPPW_KDb.js` — **10.86 kB** (gzip: 4.29 kB)
- Zero warnings or errors relating to dynamic import ineffectiveness.
