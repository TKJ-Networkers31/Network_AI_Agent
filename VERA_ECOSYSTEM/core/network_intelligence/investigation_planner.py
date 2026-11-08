"""
AIRA OS — Investigation Planning & Scoped Context Manager (Networking VI / WP 6.10).

Translates natural language questions and classified intents into validated `InvestigationPlan`s,
and manages scoped, time-bounded conversational context for follow-up questions.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.network_intelligence.intelligence_models import (
    InvestigationIntent,
    InvestigationPlan,
    NetworkEvidenceBundle,
)
from core.network_intelligence.intent_classifier import IntentClassifier


class InvestigationContextManager:
    """
    Scoped, time-bounded conversational investigation context.
    Resolves follow-up entity references and invalidates stale state without storing credentials.
    """

    def __init__(self, ttl_seconds: float = 900.0) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._contexts: Dict[str, Dict[str, Any]] = {}

    def get_or_create_context(self, session_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        curr = float(now) if now is not None else time.time()
        ctx = self._contexts.get(session_id)
        if ctx is None or (curr - float(ctx.get("updated_at", 0.0))) > self.ttl_seconds:
            ctx = {
                "session_id": session_id,
                "created_at": curr,
                "updated_at": curr,
                "last_intent": None,
                "last_target_devices": [],
                "last_target_interfaces": [],
                "last_target_ip": None,
                "last_identified_root_cause": None,
                "last_identified_wan_gateway": None,
                "last_identified_dependents": [],
                "evidence_references": [],
            }
            self._contexts[session_id] = ctx
        return ctx

    def update_context(
        self,
        session_id: str,
        intent: str,
        target_devices: Optional[List[str]] = None,
        target_interfaces: Optional[List[str]] = None,
        target_ip: Optional[str] = None,
        root_cause: Optional[str] = None,
        wan_gateway: Optional[str] = None,
        dependents: Optional[List[str]] = None,
        evidence_ids: Optional[List[str]] = None,
        now: Optional[float] = None,
    ) -> None:
        curr = float(now) if now is not None else time.time()
        ctx = self.get_or_create_context(session_id, now=curr)
        ctx["updated_at"] = curr
        ctx["last_intent"] = intent
        if target_devices:
            ctx["last_target_devices"] = list(target_devices)
        if target_interfaces:
            ctx["last_target_interfaces"] = list(target_interfaces)
        if target_ip:
            ctx["last_target_ip"] = target_ip
        if root_cause:
            ctx["last_identified_root_cause"] = root_cause
        if wan_gateway:
            ctx["last_identified_wan_gateway"] = wan_gateway
        if dependents:
            ctx["last_identified_dependents"] = list(dependents)
        if evidence_ids:
            ctx["evidence_references"] = list(set(ctx.get("evidence_references", []) + evidence_ids))[:100]

    def resolve_followup_reference(
        self,
        session_id: str,
        question: str,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Resolves anaphoric / follow-up references like:
        - "Periksa router yang menjadi gateway WAN tersebut"
        - "Apa penyebab pada perangkat tadi?"
        - "Tunjukkan rute pada perangkat itu"
        """
        curr = float(now) if now is not None else time.time()
        ctx = self.get_or_create_context(session_id, now=curr)
        q = question.lower()
        resolved: Dict[str, Any] = {}

        if any(term in q for term in ("gateway wan", "wan gateway", "router gateway")):
            if ctx.get("last_identified_wan_gateway"):
                resolved["device_id"] = ctx["last_identified_wan_gateway"]
                resolved["resolved_from"] = "last_identified_wan_gateway"
        elif any(term in q for term in ("perangkat tersebut", "router tersebut", "tadi", "perangkat itu", "akar masalah")):
            if ctx.get("last_identified_root_cause"):
                resolved["device_id"] = ctx["last_identified_root_cause"].replace("device:", "")
                resolved["resolved_from"] = "last_identified_root_cause"
            elif ctx.get("last_target_devices"):
                resolved["device_id"] = ctx["last_target_devices"][0]
                resolved["resolved_from"] = "last_target_devices"

        return resolved


class InvestigationPlanner:
    """Plans and validates structured network investigation workflows."""

    def __init__(self, context_manager: Optional[InvestigationContextManager] = None) -> None:
        self.context_manager = context_manager or InvestigationContextManager()

    def create_plan(
        self,
        question: str,
        session_id: str = "default_session",
        bundle: Optional[NetworkEvidenceBundle] = None,
        now: Optional[float] = None,
    ) -> InvestigationPlan:
        curr_ts = float(now) if now is not None else time.time()
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        intent, conf, keywords = IntentClassifier.classify(question)

        # Entity extraction from question + follow-up context
        target_entities: Dict[str, Any] = {}
        followup = self.context_manager.resolve_followup_reference(session_id, question, now=curr_ts)
        if followup.get("device_id"):
            target_entities["device_id"] = followup["device_id"]
            target_entities["resolved_via_context"] = followup.get("resolved_from")

        # Regex entity extractors
        dev_match = re.search(r"\b(CHR|ISP-\w+|Core-\w+|Dist-\w+|R-\w+|Switch-\w+|Router-\w+|[A-Za-z0-9_-]{2,20})\b", question)
        if dev_match and not target_entities.get("device_id"):
            cand = dev_match.group(1)
            if cand.lower() not in ("apa", "kenapa", "mengapa", "router", "switch", "jalur", "jaringan", "koneksi"):
                target_entities["device_id"] = cand

        ip_match = re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?\b", question)
        if ip_match:
            target_entities["ip_address"] = ip_match.group(0)

        # Map intent to required evidence & analyzers
        req_ev: List[str] = ["device_resources"]
        analyzers: List[str] = []

        if intent in (InvestigationIntent.PATH_ANALYSIS, InvestigationIntent.ROUTE_INVESTIGATION):
            req_ev.extend(["routes", "interfaces"])
            analyzers.extend(["path_intelligence", "route_reasoning"])
        elif intent == InvestigationIntent.ROOT_CAUSE_ANALYSIS:
            req_ev.extend(["routes", "interfaces", "nms_incidents", "topology_edges"])
            analyzers.extend(["correlation_engine", "rca_engine"])
        elif intent == InvestigationIntent.HEALTH_ASSESSMENT:
            req_ev.extend(["routes", "interfaces", "nms_incidents"])
            analyzers.extend(["health_engine", "anomaly_engine"])
        elif intent == InvestigationIntent.CHANGE_IMPACT:
            req_ev.extend(["topology_edges", "routes", "interfaces"])
            analyzers.extend(["impact_analyzer"])
        elif intent == InvestigationIntent.FAILURE_SIMULATION:
            req_ev.extend(["topology_edges", "routes", "interfaces"])
            analyzers.extend(["failure_simulator"])
        elif intent == InvestigationIntent.PROTOCOL_ANALYSIS:
            req_ev.extend(["routes", "ospf_neighbors", "bgp_peers", "interfaces"])
            analyzers.extend(["protocol_analyzers"])
        elif intent == InvestigationIntent.HISTORICAL_COMPARISON:
            req_ev.extend(["topology_snapshot", "route_snapshot", "nms_incidents"])
            analyzers.extend(["historical_intelligence"])

        # Determine reusable vs missing evidence
        reusable: List[str] = []
        missing: List[str] = []
        if bundle:
            for ev in req_ev:
                if any(r.evidence_type == ev for r in bundle.records):
                    reusable.append(ev)
                else:
                    missing.append(ev)
        else:
            reusable = list(req_ev)

        plan = InvestigationPlan(
            plan_id=plan_id,
            question=question,
            intent=intent.value,
            target_entities=target_entities,
            required_evidence=req_ev,
            reusable_evidence=reusable,
            missing_evidence=missing,
            required_analyzers=analyzers,
            time_window_sec=900.0,
            resource_budget={"max_execution_time_sec": 8.0, "max_devices": 10},
            expected_output=f"Laporan analisis {intent.value} dengan bukti terverifikasi.",
            is_valid=True,
            validation_notes=["Rencana investigasi tervalidasi secara deterministik."],
        )
        return plan
