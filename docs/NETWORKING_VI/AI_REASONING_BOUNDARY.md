# AIRA OS — AI REASONING BOUNDARY & ANTI-HALLUCINATION CONTRACT
## Deterministic Authority vs. Grounded LLM Explanation (WP 6.0 / WP 6.11)

**Document Status:** WP 6.0 Accepted Specification

---

## 1. Fundamental Separation of Authority

In AIRA OS Networking VI, **deterministic Python reasoning engines are the sole authority on network facts, path classifications, correlations, root-cause rankings, and confidence scores**.

The Large Language Model (`agents.rei.provider_client.call_model` — supporting local Ollama and configured cloud providers) acts **strictly** as a grounded explanation, translation, and summarization interface over pre-computed structured findings.

| Capability | Deterministic Core (Authoritative) | LLM Orchestrator (Explanatory Only) |
|---|---|---|
| Resolve device/interface identities | **YES** (`EntityResolver`) | **FORBIDDEN** |
| Evaluate LPM, recursive next hops & path mode | **YES** (`NetworkPathIntelligenceEngine`) | **FORBIDDEN** |
| Correlate multi-device symptoms & rank RCA | **YES** (`MultiDeviceCorrelationEngine`, `RootCauseAnalysisEngine`) | **FORBIDDEN** |
| Compute confidence score & label | **YES** (`ConfidenceScorer`) | **FORBIDDEN** (must echo deterministic label) |
| Execute or select CLI commands on routers | **YES** (Read-only allowlisted collectors only) | **FORBIDDEN** |
| Summarize findings in natural Indonesian/English | Structured template synthesis | **ALLOWED** (grounded in `evidence_ids`) |
| Explain networking concepts & compare hypotheses | Rule-based technical rationale | **ALLOWED** (must preserve uncertainty) |

---

## 2. Prompt-Injection & Untrusted Device Text Defense

RouterOS banners, interface comments, neighbor identities, BGP communities, and log lines originate from external network devices and **must be treated as untrusted input**.

Before constructing structured LLM input in `LLMReasoningOrchestrator` (`core/network_intelligence/reasoning_orchestrator.py`):
1. **Secret Redaction:** Every string passes through `redact_sensitive_values`.
2. **Control & Injection Stripping:** `sanitize_untrusted_device_text()` strips control bytes, role-spoofing markers (`system:`, `<|im_start|>`, `IGNORE PREVIOUS INSTRUCTIONS`, markdown code-fence escapes), and truncates free-text comments to $\le 160$ characters.
3. **Explicit Data-Only Envelope:** Untrusted device strings are serialized inside JSON values under `untrusted_device_metadata` with a system directive instructing the model to treat all JSON field contents strictly as passive network telemetry data, never as instructions.
4. **Zero Tool/Command Authority:** `LLMReasoningOrchestrator` invokes `call_model(..., tools=None)` — the LLM has **no tool-calling binding** to SSH, SNMP, shell, or database mutation functions.

---

## 3. Compact Bounded Input & Validated Structured Output

### 3.1 Bounded Context Budget (8 GB RAM / CPU Ollama Constraint)
Raw CLI exports (`/export`, 5,000-line route tables, raw ARP dumps) are **never** sent to the LLM. Instead, `build_compact_llm_context()` constructs a JSON payload capped at **6,000 characters (~1,500 tokens)** containing:
- `question` & `intent`
- `scope_summary` (device count, freshness, completeness)
- `confirmed_facts` (top $\le 12$ deterministic facts with `evidence_id`s)
- `ranked_hypotheses` (top $\le 5$ hypotheses with deterministic `confidence_label`, `supporting_evidence_ids`, `contradictory_evidence_ids`)
- `missing_evidence` & `known_limitations`

### 3.2 Mandatory Output Schema & Validation
The LLM is instructed to emit a strict JSON object matching `GroundedAIExplanation`:
- `summary` (`str`)
- `confirmed_facts` (`List[Dict[statement, evidence_refs]]`)
- `inferences` (`List[Dict[statement, evidence_refs, epistemic_level]]`)
- `hypotheses` (`List[Dict[hypothesis_id, explanation, confidence_label]]`)
- `contradictions` (`List[str]`)
- `missing_evidence` (`List[str]`)
- `explanation` (`str`)
- `recommended_next_steps` (`List[str]`)

### 3.3 Post-Generation Anti-Hallucination Validator
`validate_llm_explanation(raw_output, bundle, rca_result)` enforces:
1. Valid JSON parsing (extracting JSON block safely; rejecting malformed text).
2. Every cited `evidence_ref` in `confirmed_facts` / `inferences` **must exist** in the investigation's deterministic `evidence_ids` set (hallucinated IDs are stripped or trigger fallback).
3. Forbidden over-claim phrases (`"root cause confirmed"`, `"dipastikan 100%"`, `"terbukti pasti"`) are rejected whenever deterministic confidence is below `VERY_HIGH` or contradictory/missing evidence exists.
4. Required Indonesian epistemic qualifiers are enforced according to confidence level:
   - `"Terkonfirmasi"` — Direct `FRESH`/`AGING` `GOOD` observation (`VERY_HIGH` fact).
   - `"Terindikasi"` — High-confidence multi-source inference (`HIGH`).
   - `"Kemungkinan"` — Plausible hypothesis (`MODERATE` / `LOW`).
   - `"Belum dapat dipastikan"` — Insufficient/ambiguous evidence (`INSUFFICIENT` / `UNKNOWN`).
   - `"Data tidak tersedia"` — Missing or uncollected telemetry (`TELEMETRY_GAP`).

---

## 4. Deterministic Fallback Guarantee

Whenever:
- Local Ollama (`localhost:11434`) or external AI providers are offline (`ConnectTimeout` / `ProviderError`),
- `enable_llm_explanation=False` is requested for fast deterministic mode,
- LLM latency exceeds the bounded timeout (`8.0s` default), or
- Output fails JSON or anti-hallucination validation,

`LLMReasoningOrchestrator` seamlessly returns `synthesize_deterministic_explanation()`, generating a complete, accurate, epistemic-qualifier-compliant report directly from the deterministic findings with `generation_mode="DETERMINISTIC_FALLBACK"`. Investigations **never** fail or degrade their core conclusions when no LLM is running.
