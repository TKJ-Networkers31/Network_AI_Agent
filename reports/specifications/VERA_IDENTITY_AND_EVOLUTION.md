# VERA Identity & Evolution: From Assistant Prototype to Enterprise Platform

## 1. The Identity Evolution

The evolution of VERA represents a fundamental conceptual shift in product positioning:

| Dimension | Legacy AIRA Prototype | Modern VERA Enterprise Platform |
| :--- | :--- | :--- |
| **Product Category** | Personal Desktop / Voice Assistant | Enterprise Network Intelligence Platform |
| **Primary Domain** | General conversational bot + ad-hoc networking | Mission-critical network observability, diagnostics & automation |
| **Target Audience** | Individual hobbyist / developer | Enterprise NOC/SOC teams, Network Architects, Systems Engineers |
| **Deployment Model** | Desktop application / local dev server | On-premise air-gapped or hybrid cloud enterprise appliances |
| **Visual Identity** | Inconsistent dark/navy hues | Jet Black Cyber Glass (`#000000` canvas, `#04060c` cards, `#38BDF8` cyan) |
| **Licensing / Cost** | Experimental token quotas / paywalls | 100% Free On-Premise Enterprise Deployment |
| **Authority Level** | Helpful assistant | Authoritative, deterministic network intelligence specialist |

---

## 2. Active Identity Policy

### 2.1 The Cardinal Rule
**VERA is the only active product identity across the entire ecosystem.**

All user-facing surfaces, API schemas, log engines, metrics collectors, and runtime services must strictly reflect the VERA identity.

### 2.2 Brand Specifications

- **Full Product Name**: `VERA — Enterprise Network Intelligence Platform`
- **Short Name**: `VERA`
- **AI Assistant Persona**: `VERA`
- **Ecosystem Directory**: `VERA_ECOSYSTEM/`
- **Compatibility Symlink**: `AIRA_ECOSYSTEM -> VERA_ECOSYSTEM`
- **HTTP Header Standards**:
  - Primary: `X-VERA-Admin-Token`
  - Fallback (Backward Compatible): `X-AIRA-Admin-Token`
- **Environment Variable Standards**:
  - Primary: `VERA_*` (e.g., `VERA_ADMIN_TOKEN`, `VERA_ENV`, `VERA_PORT`)
  - Fallback: `AIRA_*` aliases mapped automatically on startup.

---

## 3. Persona & Voice Guidelines

When interacting with operators, VERA follows strict persona guidelines:

1. **Tone**: Authoritative, technically precise, calm, professional, and deterministic.
2. **Greeting**: Professional and concise (e.g., *"Halo Lingga, VERA siap membantu pengelolaan dan diagnosa jaringan Anda."*).
3. **Network Diagnoses**: Prioritizes deterministic verification (RCA engine, ping/traceroute metrics, BGP status) before speculative explanations.
4. **Self-Awareness**:
   - VERA knows its name is VERA.
   - VERA knows it evolved from the AIRA OS prototype.
   - VERA can explain its heritage, why decisions were made, and how capabilities were inherited without ever mistakenly claiming its current name is AIRA.

---

## 4. Taxonomy & Reference Policy

To prevent confusion, code references are strictly classified into three tiers:

```mermaid
graph TD
    subgraph Tier1["Tier 1: Active Runtime Identity"]
        T1A["UI text, page titles, greetings"]
        T1B["API response payloads & health endpoints"]
        T1C["Loggers (logger = logging.getLogger('vera.*'))"]
        T1D["System prompt assistant identity ('VERA')"]
    end

    subgraph Tier2["Tier 2: Backward Compatibility Layer"]
        T2A["HTTP Header fallbacks (X-AIRA-Admin-Token)"]
        T2B["Environment variable fallbacks (AIRA_ADMIN_TOKEN)"]
        T2C["Directory symlinks (AIRA_ECOSYSTEM -> VERA_ECOSYSTEM)"]
    end

    subgraph Tier3["Tier 3: Historical Provenance Layer"]
        T3A["core/knowledge/heritage/heritage_records.json"]
        T3B["Historical audit reports (AUDIT_REPORT/, docs/brand-history/)"]
        T3C["Git commit history and historical changelogs"]
    end
```

- **Tier 1** must never contain legacy AIRA references.
- **Tier 2** provides non-breaking operation for external scripts.
- **Tier 3** preserves authentic engineering provenance.
