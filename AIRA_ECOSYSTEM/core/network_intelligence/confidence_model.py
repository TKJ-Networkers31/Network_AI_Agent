"""
AIRA OS — Explainable Deterministic Confidence Scoring Model (Networking VI / WP 6.5).

Computes transparent, reproducible evidence-support scores across 8 explicit factors:
1. `evidence_quality` (weight 0.20)
2. `evidence_freshness` (weight 0.15)
3. `independent_corroboration` (weight 0.20)
4. `topology_consistency` (weight 0.15)
5. `protocol_consistency` (weight 0.15)
6. `historical_consistency` (weight 0.15)
7. `contradiction_penalty` (subtractive 0.0 .. -0.45)
8. `missing_observation_penalty` (subtractive 0.0 .. -0.40)

Important Epistemic Disclosure:
Scores produced by `ConfidenceScorer` represent deterministic multi-factor evidentiary
strength (`is_calibrated_probability = False`), NOT statistically calibrated probabilities.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from core.network_intelligence.intelligence_models import (
    CanonicalEvidenceRecord,
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceQuality,
    IntelligenceFreshness,
)

FRESHNESS_NUMERIC_MAP: Dict[str, float] = {
    IntelligenceFreshness.FRESH.value: 1.00,
    IntelligenceFreshness.AGING.value: 0.80,
    IntelligenceFreshness.STALE.value: 0.45,
    IntelligenceFreshness.EXPIRED.value: 0.20,
    IntelligenceFreshness.UNKNOWN.value: 0.15,
}

QUALITY_NUMERIC_MAP: Dict[str, float] = {
    EvidenceQuality.GOOD.value: 1.00,
    EvidenceQuality.PARTIAL.value: 0.65,
    EvidenceQuality.DISCONTINUOUS.value: 0.50,
    EvidenceQuality.UNCERTAIN.value: 0.40,
    EvidenceQuality.CONTRADICTORY.value: 0.30,
    EvidenceQuality.MISSING.value: 0.00,
    EvidenceQuality.INVALID.value: 0.00,
}


class ConfidenceScorer:
    """Deterministic multi-factor confidence evaluator for correlation and RCA hypotheses."""

    @staticmethod
    def evaluate(
        supporting_records: Sequence[CanonicalEvidenceRecord],
        contradictory_count: int = 0,
        missing_count: int = 0,
        topology_consistent: Optional[bool] = True,
        protocol_consistent: Optional[bool] = True,
        historical_consistent: Optional[bool] = None,
        independent_source_count: Optional[int] = None,
    ) -> ConfidenceAssessment:
        if not supporting_records:
            return ConfidenceAssessment(
                score=0.10,
                label=ConfidenceLabel.INSUFFICIENT.value,
                factors={
                    "evidence_quality": 0.0,
                    "evidence_freshness": 0.0,
                    "independent_corroboration": 0.0,
                    "topology_consistency": 0.0,
                    "protocol_consistency": 0.0,
                    "historical_consistency": 0.0,
                    "contradiction_penalty": 0.0,
                    "missing_observation_penalty": -min(0.40, 0.10 * max(1, missing_count)),
                },
                rationale=[
                    "Tidak ada bukti pendukung langsung yang tervalidasi untuk hipotesis ini.",
                    "Skor merupakan kekuatan dukungan bukti deterministik (bukan probabilitas terkalibrasi statistik).",
                ],
                is_calibrated_probability=False,
            )

        rationale: List[str] = []

        # 1. Evidence quality (0.20)
        q_vals = [QUALITY_NUMERIC_MAP.get(r.quality, 0.60) for r in supporting_records]
        q_score = sum(q_vals) / len(q_vals)

        # 2. Evidence freshness (0.15)
        f_vals = [FRESHNESS_NUMERIC_MAP.get(r.freshness, 0.30) for r in supporting_records]
        f_score = sum(f_vals) / len(f_vals)
        any_stale_or_expired = any(
            r.freshness in (IntelligenceFreshness.STALE.value, IntelligenceFreshness.EXPIRED.value, IntelligenceFreshness.UNKNOWN.value)
            for r in supporting_records
        )
        if any_stale_or_expired:
            rationale.append("Sebagian bukti pendukung berstatus STALE/EXPIRED/UNKNOWN sehingga membatasi tingkat keyakinan.")

        # 3. Independent corroboration across distinct subsystems or devices (0.20)
        if independent_source_count is None:
            distinct_sources = {(r.source_subsystem, r.device_id, r.evidence_type) for r in supporting_records}
            independent_source_count = len(distinct_sources)
        if independent_source_count >= 3:
            ind_score = 1.00
            rationale.append(f"Didukung oleh {independent_source_count} sumber bukti independen.")
        elif independent_source_count == 2:
            ind_score = 0.80
            rationale.append("Didukung oleh 2 sumber observasi independen.")
        else:
            ind_score = 0.45
            rationale.append("Hanya didukung oleh 1 sumber observasi tunggal (belum ada koroborasi silang).")

        # 4. Topology consistency (0.15)
        if topology_consistent is True:
            topo_score = 0.95
        elif topology_consistent is False:
            topo_score = 0.20
            rationale.append("Tidak konsisten dengan ketergantungan topologi yang teramati.")
        else:
            topo_score = 0.60

        # 5. Protocol consistency (0.15)
        if protocol_consistent is True:
            proto_score = 0.95
        elif protocol_consistent is False:
            proto_score = 0.20
            rationale.append("Bertentangan dengan state protokol/routing yang teramati.")
        else:
            proto_score = 0.60

        # 6. Historical consistency (0.15)
        if historical_consistent is True:
            hist_score = 0.90
        elif historical_consistent is False:
            hist_score = 0.35
        else:
            hist_score = 0.65  # Neutral when historical baseline/snapshot is neutral or absent

        # 7. Subtractive penalties
        contra_pen = min(0.45, 0.18 * max(0, contradictory_count))
        if contradictory_count > 0:
            rationale.append(f"Penalti kontradiksi (-{contra_pen:.2f}) akibat {contradictory_count} bukti yang bertentangan.")

        miss_pen = min(0.40, 0.08 * max(0, missing_count))
        if missing_count > 0:
            rationale.append(f"Penalti ketidaklengkapan (-{miss_pen:.2f}) akibat {missing_count} observasi yang belum tersedia.")

        weighted = (
            0.20 * q_score
            + 0.15 * f_score
            + 0.20 * ind_score
            + 0.15 * topo_score
            + 0.15 * proto_score
            + 0.15 * hist_score
            - contra_pen
            - miss_pen
        )
        final_score = max(0.05, min(0.98, weighted))

        # Determine discrete label with guardrails
        if (
            final_score >= 0.85
            and ind_score >= 0.75
            and contradictory_count == 0
            and not any_stale_or_expired
        ):
            label = ConfidenceLabel.VERY_HIGH.value
        elif final_score >= 0.70 and contradictory_count == 0:
            label = ConfidenceLabel.HIGH.value
        elif final_score >= 0.50:
            label = ConfidenceLabel.MODERATE.value
        elif final_score >= 0.30:
            label = ConfidenceLabel.LOW.value
        else:
            label = ConfidenceLabel.INSUFFICIENT.value

        rationale.append("Catatan epistemik: skor ini adalah indeks dukungan bukti deterministik, bukan probabilitas statistik.")

        return ConfidenceAssessment(
            score=final_score,
            label=label,
            factors={
                "evidence_quality": q_score,
                "evidence_freshness": f_score,
                "independent_corroboration": ind_score,
                "topology_consistency": topo_score,
                "protocol_consistency": proto_score,
                "historical_consistency": hist_score,
                "contradiction_penalty": -contra_pen,
                "missing_observation_penalty": -miss_pen,
            },
            rationale=rationale,
            is_calibrated_probability=False,
        )
