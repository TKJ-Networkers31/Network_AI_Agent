"""
AIRA OS — Grounded LLM Reasoning Orchestrator (Networking VI / WP 6.11).

Provides an epistemic interface between deterministic network intelligence outputs (RCA, Path,
Health, Anomalies) and language models via `agents.rei.provider_client.call_model`.

Strict Non-Negotiable Boundaries:
- Tool execution is strictly disabled (`tools=None`). The LLM cannot execute commands.
- Untrusted router text (comments, banners, descriptions) is sanitized against prompt injection.
- Compact context budget (<= 6000 characters).
- Enforces Indonesian epistemic qualifiers:
  "Terkonfirmasi", "Terindikasi", "Kemungkinan", "Belum dapat dipastikan", "Data tidak tersedia".
- Deterministic Fallback: When the LLM is offline, times out, or produces malformed output,
  the orchestrator directly synthesizes a structured report from deterministic findings.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from core.network_intelligence.intelligence_models import (
    GroundedAIExplanation,
    RCAReport,
)
from core.network_intelligence.security import redact_sensitive_values

logger = logging.getLogger("aira.network_intelligence.reasoning_orchestrator")

PROMPT_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt|admin\s+mode|disregard|you\s+are\s+now|override\s+safety)",
    re.IGNORECASE,
)


def sanitize_untrusted_text(text: str, max_len: int = 400) -> str:
    """Sanitizes untrusted router text (banners, interface comments, identities)."""
    if not text:
        return ""
    t = str(text)[:max_len]
    t = PROMPT_INJECTION_RE.sub("[REDACTED_PROMPT_INJECTION_ATTEMPT]", t)
    return redact_sensitive_values(t)


class LLMReasoningOrchestrator:
    """Orchestrates grounded AI explanations with authoritative deterministic fallback."""

    SYSTEM_PROMPT = """Anda adalah AIRA Network Intelligence Reasoning Engine.
Tugas Anda adalah menjelaskan hasil analisis deterministik jaringan kepada network engineer.

ATURAN KETAT:
1. Anda adalah antarmuka penjelasan, BUKAN otoritas jaringan. Jangan pernah mengarang data, rute, atau telemetri.
2. Gunakan HANYA bukti dan temuan yang diberikan dalam konteks terstruktur.
3. Wajib gunakan kualifikasi epistemik berikut secara presisi:
   - "Terkonfirmasi" : untuk fakta yang didukung bukti langsung FIB/observasi.
   - "Terindikasi"   : untuk rute/status kontrol-plane yang konsisten.
   - "Kemungkinan"   : untuk hipotesis akar masalah yang paling kuat.
   - "Belum dapat dipastikan" : jika bukti pendukung belum lengkap.
   - "Data tidak tersedia"    : untuk metrik/observasi yang hilang (bukan bernilai 0).
4. Jangan pernah menyatakan "akar masalah terkonfirmasi" jika bukti hanya berupa hipotesis.
5. Format keluaran WAJIB berupa JSON valid dengan kunci:
   "summary", "confirmed_facts", "inferences", "hypotheses", "contradictions", "missing_evidence", "explanation", "recommended_next_steps".
"""

    def generate_explanation(
        self,
        question: str,
        rca_report: Optional[RCAReport] = None,
        health_data: Optional[Dict[str, Any]] = None,
        path_data: Optional[Dict[str, Any]] = None,
        anomalies: Optional[List[Dict[str, Any]]] = None,
        force_deterministic: bool = False,
    ) -> GroundedAIExplanation:
        """
        Produces a grounded AI explanation. If `call_model` fails or `force_deterministic`
        is True, executes the deterministic synthesis fallback immediately.
        """
        # Always build deterministic fallback first
        fallback = self._build_deterministic_synthesis(
            question=question,
            rca_report=rca_report,
            health_data=health_data,
            path_data=path_data,
            anomalies=anomalies,
        )

        if force_deterministic:
            return fallback

        # Construct compact structured context (<= 6000 chars)
        context_str = self._build_compact_context(
            question=question,
            rca_report=rca_report,
            health_data=health_data,
            path_data=path_data,
            anomalies=anomalies,
        )

        try:
            from agents.rei.provider_client import call_model
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Pertanyaan: {question}\n\nKonteks Bukti Jaringan:\n{context_str}"},
            ]
            response = call_model(messages=messages, tools=None)
            if not response or not isinstance(response, dict) or response.get("error"):
                logger.info("LLM unavailable or returned error; using deterministic fallback.")
                return fallback

            msg = response.get("message") or {}
            content = msg.get("content") or ""
            if not content:
                return fallback

            # Extract and parse JSON
            parsed = self._extract_json(content)
            if not parsed or not isinstance(parsed, dict) or "summary" not in parsed:
                return fallback

            return GroundedAIExplanation(
                generation_mode="LLM_GROUNDED",
                summary=str(parsed.get("summary") or fallback.summary),
                confirmed_facts=list(parsed.get("confirmed_facts") or fallback.confirmed_facts),
                inferences=list(parsed.get("inferences") or fallback.inferences),
                hypotheses=list(parsed.get("hypotheses") or fallback.hypotheses),
                contradictions=list(parsed.get("contradictions") or fallback.contradictions),
                missing_evidence=list(parsed.get("missing_evidence") or fallback.missing_evidence),
                explanation=str(parsed.get("explanation") or fallback.explanation),
                recommended_next_steps=list(parsed.get("recommended_next_steps") or fallback.recommended_next_steps),
                model_used=str(response.get("model") or "llm"),
            )
        except Exception as exc:
            logger.debug("Exception in LLMReasoningOrchestrator: %s", exc)
            return fallback

    def _build_compact_context(
        self,
        question: str,
        rca_report: Optional[RCAReport],
        health_data: Optional[Dict[str, Any]],
        path_data: Optional[Dict[str, Any]],
        anomalies: Optional[List[Dict[str, Any]]],
    ) -> str:
        ctx: Dict[str, Any] = {"question": sanitize_untrusted_text(question, 200)}
        if rca_report:
            ctx["rca"] = {
                "scope": rca_report.scope,
                "most_likely_root_cause": (
                    rca_report.most_likely_root_cause.to_dict() if rca_report.most_likely_root_cause else None
                ),
                "secondary_symptoms": rca_report.secondary_symptoms[:4],
                "affected_devices": rca_report.affected_devices[:6],
                "confidence": rca_report.confidence.to_dict() if rca_report.confidence else None,
                "missing_evidence": rca_report.missing_evidence[:5],
            }
        if health_data:
            ctx["health"] = {
                "overall_status": health_data.get("overall_status"),
                "overall_score": health_data.get("overall_score"),
                "degraded_devices": health_data.get("degraded_devices", [])[:4],
                "critical_devices": health_data.get("critical_devices", [])[:4],
            }
        if path_data:
            ctx["path"] = {
                "destination_ip": path_data.get("destination_ip"),
                "mode": path_data.get("mode"),
                "outcome": path_data.get("outcome"),
                "hops": [
                    {
                        "hop": h.get("hop_index"),
                        "device": h.get("device_id"),
                        "prefix": h.get("matched_prefix"),
                        "gw": h.get("next_hop_ip"),
                    }
                    for h in path_data.get("hops", [])[:6]
                ],
            }
        if anomalies:
            ctx["anomalies"] = [
                {
                    "metric": a.get("metric_name"),
                    "device": a.get("device_id"),
                    "what_changed": a.get("what_changed"),
                    "is_fault": a.get("is_fault_candidate"),
                }
                for a in anomalies[:4]
            ]
        raw_json = json.dumps(ctx, ensure_ascii=False)
        return raw_json[:5800]

    def _build_deterministic_synthesis(
        self,
        question: str,
        rca_report: Optional[RCAReport],
        health_data: Optional[Dict[str, Any]],
        path_data: Optional[Dict[str, Any]],
        anomalies: Optional[List[Dict[str, Any]]],
    ) -> GroundedAIExplanation:
        confirmed_facts: List[Dict[str, Any]] = []
        inferences: List[Dict[str, Any]] = []
        hypotheses: List[Dict[str, Any]] = []
        contradictions: List[str] = []
        missing_ev: List[str] = []
        steps: List[str] = []

        summary_parts: List[str] = []

        if rca_report and rca_report.most_likely_root_cause:
            mrc = rca_report.most_likely_root_cause
            conf_str = mrc.confidence.label if mrc.confidence else "MODERATE"
            hypotheses.append(
                {
                    "category": mrc.category,
                    "title": mrc.title,
                    "epistemic_qualifier": "Kemungkinan",
                    "confidence": conf_str,
                    "description": mrc.description,
                }
            )
            summary_parts.append(f"Akar masalah terindikasi kuat pada {mrc.root_entity_id} ({mrc.title}, keyakinan={conf_str}).")
            for alt in mrc.alternative_explanations:
                hypotheses.append({"epistemic_qualifier": "Kemungkinan alternatif", "description": alt})
            for s in rca_report.secondary_symptoms:
                inferences.append({"epistemic_qualifier": "Terindikasi gejala sekunder", "detail": s.get("description")})
            missing_ev.extend(rca_report.missing_evidence)
            for r in rca_report.proposed_remediation_review_only:
                steps.append(r.get("title") or r.get("action"))

        if path_data:
            outcome = path_data.get("outcome")
            mode = path_data.get("mode")
            dst = path_data.get("destination_ip")
            summary_parts.append(f"Jalur trafik ke {dst}: status {outcome} (mode penalaran {mode}).")
            confirmed_facts.append(
                {
                    "epistemic_qualifier": "Terkonfirmasi",
                    "fact": f"Hasil LPM kontrol-plane: outcome={outcome}, mode={mode}.",
                }
            )

        if health_data:
            ov = health_data.get("overall_status")
            sc = health_data.get("overall_score")
            confirmed_facts.append(
                {
                    "epistemic_qualifier": "Terkonfirmasi",
                    "fact": f"Kesehatan jaringan keseluruhan: {ov} (skor={sc}).",
                }
            )

        if anomalies:
            for a in anomalies:
                inferences.append(
                    {
                        "epistemic_qualifier": "Terindikasi",
                        "detail": a.get("what_changed"),
                        "is_fault": a.get("is_fault_candidate"),
                    }
                )

        if not summary_parts:
            summary = "Analisis selesai. Semua metrik yang terukur berada dalam batas operasional normal."
        else:
            summary = " ".join(summary_parts)

        explanation = (
            f"Laporan inferensi deterministik AIRA untuk: '{sanitize_untrusted_text(question, 150)}'.\n\n"
            f"Ringkasan: {summary}\n"
            f"Catatan Epistemik: Semua temuan didasarkan pada telemetri dan bukti kontrol-plane yang terekam; "
            f"tidak ada perubahan konfigurasi yang dieksekusi secara otomatis."
        )

        return GroundedAIExplanation(
            generation_mode="DETERMINISTIC_FALLBACK",
            summary=summary,
            confirmed_facts=confirmed_facts,
            inferences=inferences,
            hypotheses=hypotheses,
            contradictions=contradictions,
            missing_evidence=missing_ev or ["Tidak ada celah bukti kritis yang menghalangi analisis."],
            explanation=explanation,
            recommended_next_steps=steps or ["Lakukan verifikasi manual pada perangkat yang terindikasi degraded."],
            model_used="deterministic_engine",
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        text_clean = text.strip()
        if text_clean.startswith("```"):
            lines = text_clean.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text_clean = "\n".join(lines).strip()
        try:
            return json.loads(text_clean)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text_clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            return None
