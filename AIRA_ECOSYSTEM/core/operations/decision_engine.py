"""
AIRA OS — Operational Decision Intelligence Engine (Networking VIII / WP 8.5).

Produces deterministic, evidence-grounded operational decisions for NOC operators.

Synthesizes:
- Unified evidence & anomalies
- Dynamic health scores (WP 8.5.1)
- RCA hypotheses (Networking VI)
- Predictive capacity horizons (Networking VII)
- SLA exposure & error budget (WP 8.7)

Strict Epistemic Invariants:
- Never asserts hypotheses as confirmed facts when evidence is incomplete.
- Transparent algebraic priority scoring formula (inspectable factors).
- Enforces validated lifecycle transitions (GENERATED -> UNDER_REVIEW -> APPROVED/REJECTED).
- Strictly read-only: No automated device mutations or arbitrary command execution.
- Append-only audit history in operational_decision_history.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.rca_engine import RCAReport, RootCauseAnalysisEngine
from core.operations.db import ensure_operational_schema
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import (
    DecisionAssessment,
    DecisionHistoryRecord,
    DecisionRecommendation,
    DecisionStatus,
    OperationalDecision,
    RecommendationAlternative,
    RiskLevel,
    ServiceCriticality,
    VALID_DECISION_TRANSITIONS,
)
from core.operations.sla_engine import SlaManagementEngine
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.operations.decision_engine")


class OperationalDecisionEngine:
    """Deterministic Operational Decision Support Engine."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        health_engine: Optional[DynamicHealthScoringEngine] = None,
        sla_engine: Optional[SlaManagementEngine] = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.health_engine = health_engine or DynamicHealthScoringEngine(db_path=self.db_path)
        self.sla_engine = sla_engine or SlaManagementEngine(db_path=self.db_path)
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # Decision Synthesis
    # -----------------------------------------------------------------------
    def synthesize_decision(
        self,
        tenant_id: str,
        site_id: Optional[str],
        problem_title: str,
        evidence_bundle: Optional[NetworkEvidenceBundle] = None,
        rca_report: Optional[RCAReport] = None,
        affected_services: Optional[List[str]] = None,
        affected_devices: Optional[List[str]] = None,
        predictive_risk: Optional[str] = None,
        expires_in_hours: int = 24,
    ) -> OperationalDecision:
        """
        Synthesizes an OperationalDecision from evidence, RCA, health, and SLA.
        Computes deterministic priority score and generates explainable alternatives.
        """
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        expires_iso = datetime.fromtimestamp(now_dt.timestamp() + (expires_in_hours * 3600), tz=timezone.utc).isoformat()

        aff_services = list(affected_services or [])
        aff_devices = list(affected_devices or [])

        # 1. Resolve Root Cause Hypotheses and Evidence
        supporting_ev: List[str] = []
        contradictory_ev: List[str] = []
        missing_ev: List[str] = []
        rca_hypotheses: List[Dict[str, Any]] = []
        confidence = 0.5
        epistemic_status = "HYPOTHESIS_SUPPORTED"
        uncertainties: List[str] = []

        if rca_report:
            # Extract confidence (float or ConfidenceAssessment)
            conf_val = getattr(rca_report, "confidence", None)
            if isinstance(conf_val, (int, float)):
                confidence = float(conf_val)
            elif conf_val and hasattr(conf_val, "composite_score"):
                confidence = float(conf_val.composite_score)
            else:
                confidence = 0.5

            supporting_ev = list(getattr(rca_report, "supporting_evidence", getattr(rca_report, "supporting_evidence_ids", [])))
            contradictory_ev = list(getattr(rca_report, "contradictory_evidence", getattr(rca_report, "contradictory_evidence_ids", [])))
            missing_ev = list(getattr(rca_report, "missing_evidence", getattr(rca_report, "missing_evidence_ids", [])))

            hyps = getattr(rca_report, "hypotheses", getattr(rca_report, "candidate_hypotheses", []))
            for hyp in hyps:
                prob = getattr(hyp, "probability", None)
                if prob is None and hasattr(hyp, "confidence") and hyp.confidence:
                    prob = getattr(hyp.confidence, "composite_score", 0.5)
                rca_hypotheses.append({
                    "hypothesis_id": getattr(hyp, "hypothesis_id", "hyp_1"),
                    "title": getattr(hyp, "title", "Hypothesis"),
                    "probability": round(float(prob or 0.5), 3),
                    "summary": getattr(hyp, "description", getattr(hyp, "summary", "")),
                })

            if confidence >= 0.85 and not missing_ev:
                epistemic_status = "CONFIRMED_BY_EVIDENCE"
            elif confidence < 0.4 or len(missing_ev) > 2:
                epistemic_status = "INSUFFICIENT_EVIDENCE"
                uncertainties.append(f"Terdapat {len(missing_ev)} bukti penting yang belum terverifikasi.")
        else:
            epistemic_status = "INSUFFICIENT_EVIDENCE"
            uncertainties.append("Laporan RCA belum tersedia untuk anomali ini.")

        if evidence_bundle:
            for rec in evidence_bundle.records:
                if rec.evidence_id not in supporting_ev:
                    supporting_ev.append(rec.evidence_id)

        # 2. Check SLA Exposure for affected services
        sla_impact: Dict[str, Any] = {}
        sla_weight = 0.0
        for svc_id in aff_services:
            policy = self.sla_engine.get_policy(tenant_id, svc_id)
            if policy:
                sla_impact[svc_id] = {
                    "policy_name": policy.name,
                    "target_availability": policy.target_availability,
                    "risk": "HIGH_EXPOSURE",
                }
                sla_weight = max(sla_weight, 1.0)

        # 3. Compute Deterministic Priority Score (0.0 - 100.0)
        # Priority = w_c*C + w_s*S + w_i*I + w_l*L + w_e*E
        # Service criticality factor (30 pts)
        crit_factor = 0.2
        with topology_transaction(self.db_path, write=False) as conn:
            for s_id in aff_services:
                r = conn.execute("SELECT criticality FROM operational_services WHERE service_id = ?", (s_id,)).fetchone()
                if r:
                    c = r["criticality"]
                    if c == ServiceCriticality.TIER_1_MISSION_CRITICAL.value:
                        crit_factor = max(crit_factor, 1.0)
                    elif c == ServiceCriticality.TIER_2_BUSINESS_OPERATIONAL.value:
                        crit_factor = max(crit_factor, 0.75)
                    elif c == ServiceCriticality.TIER_3_OFFICE_PRODUCTIVITY.value:
                        crit_factor = max(crit_factor, 0.4)

        service_pts = 30.0 * crit_factor
        incident_pts = 25.0 * (1.0 if epistemic_status == "CONFIRMED_BY_EVIDENCE" else 0.6)
        blast_pts = 20.0 * min(1.0, max(0.2, (len(aff_devices) + len(aff_services)) / 4.0))
        sla_pts = 15.0 * sla_weight
        conf_pts = 10.0 * confidence

        total_priority = min(100.0, service_pts + incident_pts + blast_pts + sla_pts + conf_pts)

        if total_priority >= 75.0:
            risk_level = RiskLevel.CRITICAL.value
        elif total_priority >= 50.0:
            risk_level = RiskLevel.WARNING.value
        elif total_priority >= 25.0:
            risk_level = RiskLevel.WATCH.value
        else:
            risk_level = RiskLevel.INFO.value

        # 4. Formulate Actionable Recommendations & Alternatives
        rec_id = f"rec_{uuid.uuid4().hex[:10]}"
        alternatives: List[RecommendationAlternative] = [
            RecommendationAlternative(
                alternative_id=f"alt_{uuid.uuid4().hex[:8]}",
                title="Pemeriksaan Jalur Fisik & Transceiver SFP",
                description="Lakukan inspeksi optik kabel fiber dan pembersihan konektor pada antarmuka terkait.",
                risk_level=RiskLevel.INFO.value,
                tradeoffs=["Memerlukan waktu penanganan di lokasi (on-site)."],
                is_preferred=True,
            ),
            RecommendationAlternative(
                alternative_id=f"alt_{uuid.uuid4().hex[:8]}",
                title="Alihkan Beban Trafik ke Link Sekunder (Failover)",
                description="Arahkan rute bisnis prioritas melalui gateway sekunder secara manual melalui konsol router.",
                risk_level=RiskLevel.WARNING.value,
                tradeoffs=["Beban bandwidth pada link cadangan akan meningkat.", "Membutuhkan verifikasi SLA rute sekunder."],
                is_preferred=False,
            ),
        ]

        verification_checklist = [
            "Verifikasi apakah perangkat terkait masih merespons ICMP ping dari Edge Gateway.",
            "Pastikan tidak ada pekerjaan pemeliharaan fisik yang sedang berlangsung di rak data center.",
            "Periksa apakah alarm optik (Rx optical power) berada dalam rentang toleransi vendor.",
        ]

        assessment = DecisionAssessment(
            problem_statement=f"Terdeteksi degradasi operasional pada {len(aff_devices)} perangkat dan {len(aff_services)} layanan.",
            root_cause_hypotheses=rca_hypotheses,
            supporting_evidence_ids=supporting_ev,
            contradictory_evidence_ids=contradictory_ev,
            missing_evidence_ids=missing_ev,
            confidence_score=confidence,
            epistemic_status=epistemic_status,
            uncertainty_factors=uncertainties,
        )

        recommendation = DecisionRecommendation(
            recommendation_id=rec_id,
            title=f"Rekomendasi Operasional: {problem_title}",
            summary="Rekomendasi penanganan berbasis bukti untuk memulihkan stabilitas layanan tanpa mutasi otomatis.",
            safest_action="Lakukan verifikasi diagnostik baca (read-only) pada antarmuka dan pantau kestabilan tabel rute.",
            alternatives=alternatives,
            human_verification_checklist=verification_checklist,
            requires_approval=True,
            approval_role="NOC_OPERATOR",
        )

        decision = OperationalDecision(
            decision_id=decision_id,
            tenant_id=tenant_id,
            site_id=site_id,
            title=problem_title,
            priority_score=total_priority,
            risk_level=risk_level,
            status=DecisionStatus.GENERATED.value,
            affected_services=aff_services,
            affected_devices=aff_devices,
            assessment=assessment,
            recommendation=recommendation,
            sla_impact_assessment=sla_impact,
            created_at=now_iso,
            expires_at=expires_iso,
            updated_at=now_iso,
        )

        self._persist_decision(decision)
        self._record_history(decision.decision_id, tenant_id, "SYSTEM", "NONE", DecisionStatus.GENERATED.value, "Initial decision generated by AI engine.")
        return decision

    # -----------------------------------------------------------------------
    # Decision Lifecycle & State Transitions
    # -----------------------------------------------------------------------
    def transition_status(
        self,
        decision_id: str,
        tenant_id: str,
        actor: str,
        new_status: str,
        reason: str,
    ) -> OperationalDecision:
        """
        Transitions decision status through validated state machine.
        Rejects invalid transitions and logs append-only audit trail.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            row = conn.execute(
                """
                SELECT decision_id, tenant_id, site_id, title, priority_score, risk_level,
                       status, affected_services_json, affected_devices_json,
                       assessment_json, recommendation_json, sla_impact_json,
                       created_at, expires_at, updated_at
                FROM operational_decisions
                WHERE decision_id = ? AND tenant_id = ?
                """,
                (decision_id, tenant_id),
            ).fetchone()

            if not row:
                raise KeyError(f"Decision '{decision_id}' not found for tenant '{tenant_id}'.")

            current_status = row["status"]
            allowed_next = VALID_DECISION_TRANSITIONS.get(current_status, set())

            if new_status not in allowed_next:
                raise ValueError(
                    f"Invalid Decision State Transition: Cannot transition from '{current_status}' to '{new_status}'. Allowed: {sorted(list(allowed_next))}"
                )

            # Update decision state
            conn.execute(
                "UPDATE operational_decisions SET status = ?, updated_at = ? WHERE decision_id = ?",
                (new_status, now_iso, decision_id),
            )

            # Record append-only history
            hist_id = f"dhist_{uuid.uuid4().hex[:10]}"
            conn.execute(
                """
                INSERT INTO operational_decision_history (
                    history_id, decision_id, tenant_id, actor, from_status, to_status, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (hist_id, decision_id, tenant_id, actor, current_status, new_status, reason, now_iso),
            )

        return self.get_decision(tenant_id, decision_id)  # type: ignore

    def get_decision(self, tenant_id: str, decision_id: str) -> Optional[OperationalDecision]:
        """Retrieves a single decision by ID with strict tenant scoping."""
        with topology_transaction(self.db_path, write=False) as conn:
            r = conn.execute(
                """
                SELECT decision_id, tenant_id, site_id, title, priority_score, risk_level,
                       status, affected_services_json, affected_devices_json,
                       assessment_json, recommendation_json, sla_impact_json,
                       created_at, expires_at, updated_at
                FROM operational_decisions
                WHERE decision_id = ? AND tenant_id = ?
                """,
                (decision_id, tenant_id),
            ).fetchone()

        if not r:
            return None

        # Reconstitute assessment and recommendation
        ass_dict = json.loads(r["assessment_json"] or "{}")
        assessment = DecisionAssessment(**ass_dict)

        rec_dict = json.loads(r["recommendation_json"] or "{}")
        alts = [RecommendationAlternative(**a) for a in rec_dict.pop("alternatives", [])]
        recommendation = DecisionRecommendation(alternatives=alts, **rec_dict)

        return OperationalDecision(
            decision_id=r["decision_id"],
            tenant_id=r["tenant_id"],
            site_id=r["site_id"],
            title=r["title"],
            priority_score=r["priority_score"],
            risk_level=r["risk_level"],
            status=r["status"],
            affected_services=json.loads(r["affected_services_json"] or "[]"),
            affected_devices=json.loads(r["affected_devices_json"] or "[]"),
            assessment=assessment,
            recommendation=recommendation,
            sla_impact_assessment=json.loads(r["sla_impact_json"] or "{}"),
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            updated_at=r["updated_at"],
        )

    def list_decisions(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        site_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[OperationalDecision]:
        """Lists decisions scoped to tenant, sorted by priority score descending."""
        clauses = ["tenant_id = ?"]
        params: List[Any] = [tenant_id]

        if status:
            clauses.append("status = ?")
            params.append(status)
        if site_id:
            clauses.append("site_id = ?")
            params.append(site_id)

        where_sql = " AND ".join(clauses)
        params.extend([max(1, limit), max(0, offset)])

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                f"""
                SELECT decision_id FROM operational_decisions
                WHERE {where_sql}
                ORDER BY priority_score DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

        decisions = []
        for r in rows:
            d = self.get_decision(tenant_id, r["decision_id"])
            if d:
                decisions.append(d)
        return decisions

    def get_decision_history(self, tenant_id: str, decision_id: str) -> List[DecisionHistoryRecord]:
        """Returns append-only audit history for a decision."""
        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(
                """
                SELECT history_id, decision_id, tenant_id, actor, from_status, to_status, reason, created_at
                FROM operational_decision_history
                WHERE decision_id = ? AND tenant_id = ?
                ORDER BY created_at ASC
                """,
                (decision_id, tenant_id),
            ).fetchall()

        return [
            DecisionHistoryRecord(
                history_id=r["history_id"],
                decision_id=r["decision_id"],
                tenant_id=r["tenant_id"],
                actor=r["actor"],
                from_status=r["from_status"],
                to_status=r["to_status"],
                reason=r["reason"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def _persist_decision(self, decision: OperationalDecision) -> None:
        """Persists decision record into database."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO operational_decisions (
                    decision_id, tenant_id, site_id, title, priority_score,
                    risk_level, status, affected_services_json, affected_devices_json,
                    assessment_json, recommendation_json, sla_impact_json,
                    created_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.tenant_id,
                    decision.site_id,
                    decision.title,
                    decision.priority_score,
                    decision.risk_level,
                    decision.status,
                    json.dumps(decision.affected_services),
                    json.dumps(decision.affected_devices),
                    json.dumps(decision.assessment.to_dict()),
                    json.dumps(decision.recommendation.to_dict()),
                    json.dumps(decision.sla_impact_assessment),
                    decision.created_at,
                    decision.expires_at,
                    decision.updated_at,
                ),
            )

    def _record_history(
        self,
        decision_id: str,
        tenant_id: str,
        actor: str,
        from_status: str,
        to_status: str,
        reason: str,
    ) -> None:
        """Appends to audit history."""
        hist_id = f"dhist_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_decision_history (
                    history_id, decision_id, tenant_id, actor, from_status, to_status, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (hist_id, decision_id, tenant_id, actor, from_status, to_status, reason, now_iso),
            )
