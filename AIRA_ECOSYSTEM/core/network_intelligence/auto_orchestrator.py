"""
core/network_intelligence/auto_orchestrator.py — Unified Automatic Network & Route Intelligence Pipeline (WP 4.6.6).

Orchestrates:
  User Request / Trigger -> Intent Recognition -> Device/Network Resolution ->
  Requirement Validation (DIO if required) -> Single-Pass Evidence Collection (with TTL reuse) ->
  UnifiedRouteParser Normalization -> Route Intelligence & LPM -> Topology Correlation ->
  Historical Route & NMS Correlation -> Cross-Device Analysis -> Dependency Evaluation ->
  Root Cause & Confidence Synthesis -> Read-Only Verification & Planning -> Frontend Payload.

Strict Guarantees:
- Reuses existing NetworkInvestigator, DIOAnalyzer, CrossDeviceEvidenceCorrelator, TopologyEngine,
  MultiDeviceRouteCollector, RouteHistoryStore, and ConfigurationPlanner (no parallel orchestrator).
- Collects MultiDeviceEvidenceBundle at most ONCE per diagnosis run and reuses fresh cached bundles.
- 100% Read-Only live boundary: every verification CLI command is checked via `validate_readonly_command`.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.canonical_network import get_canonical_registry
from core.dio.analyzer import DIOAnalyzer
from core.inventory_store import get_inventory_store
from core.network_intelligence.correlation import CrossDeviceEvidenceCorrelator
from core.network_intelligence.investigator import (
    INCIDENT_EVIDENCE_REQUIREMENTS,
    NetworkInvestigator,
)
from core.network_intelligence.models import (
    ConfigurationPlan,
    IncidentRecord,
    IncidentType,
)
from core.network_intelligence.multi_device_collector import (
    MultiDeviceEvidenceBundle,
    MultiDeviceEvidenceOrchestrator,
)
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.security import validate_readonly_command
from core.routing.cross_device_routing import CrossDeviceRouteIntelligenceEngine
from core.routing.route_analytics import (
    RouteFindingType,
    RoutePathEvaluator,
    RouteTableAnalyzer,
    build_ip_owner_index,
    evaluate_route_lookup,
)
from core.routing.route_collector import (
    RouteCollectionResult,
    RouteCompleteness,
    get_route_collector,
)
from core.routing.route_dependency import (
    DependencyResolutionState,
    FailurePropagationAnalyzer,
    HypotheticalFailureType,
    RouteDependencyAnalyzer,
)
from core.routing.route_history import get_route_history_store

logger = logging.getLogger("aira.network_intelligence.auto_orchestrator")

_CIDR_OR_IPV4_RE = re.compile(
    r"\b((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?:/(?:3[0-2]|[12]?\d))?)\b"
)
_VRF_EXTRACT_RE = re.compile(r"\b(?:vrf|routing[-_\s]?table|tabel)\s+([a-zA-Z0-9_.-]+)\b", re.IGNORECASE)


class RoutingDiagnosisIntent:
    ANALYZE_ALL_ROUTERS = "ANALYZE_ALL_ROUTERS"
    LAN_INTERNET_REACHABILITY = "LAN_INTERNET_REACHABILITY"
    UPSTREAM_DEPENDENCY_ANALYSIS = "UPSTREAM_DEPENDENCY_ANALYSIS"
    DEFAULT_ROUTE_VERIFICATION = "DEFAULT_ROUTE_VERIFICATION"
    SPECIFIC_PREFIX_PATH_ANALYSIS = "SPECIFIC_PREFIX_PATH_ANALYSIS"
    GATEWAY_REACHABILITY_ANALYSIS = "GATEWAY_REACHABILITY_ANALYSIS"
    CROSS_DEVICE_INCONSISTENCY_SCAN = "CROSS_DEVICE_INCONSISTENCY_SCAN"
    HISTORICAL_SNAPSHOT_COMPARISON = "HISTORICAL_SNAPSHOT_COMPARISON"
    PRE_FAILURE_CHANGE_CORRELATION = "PRE_FAILURE_CHANGE_CORRELATION"
    GENERAL_NETWORK_DIAGNOSIS = "GENERAL_NETWORK_DIAGNOSIS"


def filter_safe_readonly_commands(commands: Sequence[str]) -> List[str]:
    """Ensures every recommended verification CLI command passes the 10-layer read-only allowlist."""
    safe: List[str] = []
    for cmd in commands:
        cleaned = str(cmd or "").strip()
        if not cleaned:
            continue
        ok, _ = validate_readonly_command(cleaned)
        if ok and cleaned not in safe:
            safe.append(cleaned)
    return safe


class AutomaticNetworkOrchestrator:
    """
    Unified end-to-end automation engine for network & multi-device routing diagnostics.
    Combines Investigation, Evidence Reuse, Cross-Device Route Intelligence, Dependency Analysis,
    Historical Route Comparison, Root Cause Synthesis, and Non-Mutating Planning in a single pipeline.
    """

    def __init__(self) -> None:
        self.investigator = NetworkInvestigator()
        self.planner = ConfigurationPlanner()
        self.inv_store = get_inventory_store()
        self.registry = get_canonical_registry()
        self.correlator = CrossDeviceEvidenceCorrelator()
        self.dio_analyzer = DIOAnalyzer()
        self.route_table_analyzer = RouteTableAnalyzer()
        self.route_path_evaluator = RoutePathEvaluator()
        self.route_dep_analyzer = RouteDependencyAnalyzer()
        self.failure_prop_analyzer = FailurePropagationAnalyzer()
        self.cross_device_engine = CrossDeviceRouteIntelligenceEngine()

        self._lock = threading.Lock()
        self._active_pipelines: Dict[str, threading.Event] = {}
        # Single-pass TTL bundle cache: key -> (timestamp, MultiDeviceEvidenceBundle)
        self._bundle_cache: Dict[Tuple[Tuple[str, ...], Tuple[str, ...]], Tuple[float, MultiDeviceEvidenceBundle]] = {}
        self.last_collection_executions: int = 0

    # ------------------------------------------------------------------
    # Intent Recognition (Section 10.2)
    # ------------------------------------------------------------------

    def classify_routing_intent(
        self,
        symptom: Optional[str],
        *,
        target_ip: Optional[str] = None,
        routing_table: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deterministically extracts routing intent, target IP/prefix, and VRF table
        from natural-language operator queries (English & Indonesian) without hardcoding prompts.
        """
        text = (symptom or "").strip()
        low = text.lower()

        extracted_ips = _CIDR_OR_IPV4_RE.findall(text)
        vrf_match = _VRF_EXTRACT_RE.search(text)
        resolved_table = routing_table or (vrf_match.group(1) if vrf_match else "main")
        resolved_dest = target_ip or (extracted_ips[0] if extracted_ips else None)

        intent = RoutingDiagnosisIntent.GENERAL_NETWORK_DIAGNOSIS
        needs_explicit_destination = False

        if any(k in low for k in ["what changed", "apa yang berubah", "before", "sebelum"]) and any(
            k in low for k in ["unreachable", "putus", "mati", "down", "hilang", "route", "rute"]
        ):
            intent = RoutingDiagnosisIntent.PRE_FAILURE_CHANGE_CORRELATION
        elif any(k in low for k in ["compare", "bandingkan", "previous snapshot", "snapshot sebelumnya", "history", "riwayat"]):
            intent = RoutingDiagnosisIntent.HISTORICAL_SNAPSHOT_COMPARISON
        elif any(k in low for k in ["inconsisten", "inkonsistensi", "mismatch", "konflik rute", "between routers", "antar router"]):
            intent = RoutingDiagnosisIntent.CROSS_DEVICE_INCONSISTENCY_SCAN
        elif any(k in low for k in ["upstream dependency", "dependensi upstream", "upstream of", "recursive", "rekursif"]):
            intent = RoutingDiagnosisIntent.UPSTREAM_DEPENDENCY_ANALYSIS
        elif any(k in low for k in ["default route", "rute default", "0.0.0.0/0", "default gateway"]):
            intent = RoutingDiagnosisIntent.DEFAULT_ROUTE_VERIFICATION
            resolved_dest = resolved_dest or "8.8.8.8"
        elif any(k in low for k in ["lan", "klien", "client", "users"]) and any(
            k in low for k in ["internet", "tidak bisa", "cannot reach", "can this lan not reach", "no internet"]
        ):
            intent = RoutingDiagnosisIntent.LAN_INTERNET_REACHABILITY
            resolved_dest = resolved_dest or "8.8.8.8"
        elif any(k in low for k in ["gateway is reachable", "whether this gateway", "gateway dapat dijangkau", "cek gateway"]):
            intent = RoutingDiagnosisIntent.GATEWAY_REACHABILITY_ANALYSIS
            if not resolved_dest:
                needs_explicit_destination = True
        elif any(k in low for k in ["route to", "rute ke", "jalur ke", "path to", "menuju"]):
            intent = RoutingDiagnosisIntent.SPECIFIC_PREFIX_PATH_ANALYSIS
            if not resolved_dest:
                needs_explicit_destination = True
        elif any(k in low for k in ["all registered routers", "all routers", "semua router", "analyze routing", "analisis routing"]):
            intent = RoutingDiagnosisIntent.ANALYZE_ALL_ROUTERS

        return {
            "intent": intent,
            "destination": resolved_dest,
            "routing_table": resolved_table,
            "extracted_ips": extracted_ips,
            "needs_explicit_destination": needs_explicit_destination,
        }

    # ------------------------------------------------------------------
    # Target Resolution & Pipeline Cancellation
    # ------------------------------------------------------------------

    def resolve_target_devices(self, target_devices: Optional[List[str]] = None) -> List[str]:
        """
        Resolves and validates target devices against authorized inventory and CanonicalDevice registry.
        Never scans or accepts unauthorized external public hosts when inventory is empty.
        """
        inv_res = self.inv_store.list_devices()
        devices = inv_res.get("devices", []) if inv_res.get("success") else []
        enabled_devices = [d["name"] for d in devices if d.get("enabled", 1)]

        if not target_devices:
            if not enabled_devices:
                # Fallback to CanonicalDevice managed inventory if populated in isolated test contexts
                managed_canon = [d.device_id for d in self.registry.list_devices() if d.is_managed]
                if managed_canon:
                    return managed_canon
                raise ValueError("Inventory kosong. Daftarkan minimal 1 router di tab Devices.")
            if len(enabled_devices) == 1:
                return [enabled_devices[0]]
            return enabled_devices

        available_names = {d["name"].lower(): d["name"] for d in devices}
        resolved: List[str] = []
        for t in target_devices:
            cleaned = str(t).strip()
            if not cleaned:
                continue
            if cleaned.lower() in available_names:
                resolved.append(available_names[cleaned.lower()])
            else:
                cdev = self.registry.resolve_device(cleaned)
                resolved.append(cdev.display_name if (cdev and cdev.display_name in devices) else cleaned)

        if not resolved:
            raise ValueError(f"Tidak ada perangkat valid yang ditemukan dari target: {target_devices}")
        return list(dict.fromkeys(resolved))

    def cancel_pipeline(self, pipeline_id: str) -> bool:
        """Signals cooperative cancellation to an in-flight automatic diagnosis pipeline."""
        with self._lock:
            evt = self._active_pipelines.get(pipeline_id)
            if evt is not None:
                evt.set()
                return True
        return False

    def clear_evidence_cache(self) -> None:
        with self._lock:
            self._bundle_cache.clear()

    # ------------------------------------------------------------------
    # Main Unified Pipeline (Sections 10.1–10.7)
    # ------------------------------------------------------------------

    def execute_auto_diagnosis(
        self,
        target_devices: Optional[List[str]] = None,
        symptom: Optional[str] = None,
        target_ip: Optional[str] = None,
        auto_plan: bool = True,
        *,
        routing_table: str = "main",
        require_dio_validation: bool = False,
        reuse_fresh_sec: float = 30.0,
        persist_route_snapshot: bool = False,
        precollected_routes: Optional[Dict[str, RouteCollectionResult]] = None,
        prebuilt_bundle: Optional[MultiDeviceEvidenceBundle] = None,
        topology_edges_override: Optional[Sequence[Dict[str, Any]]] = None,
        device_oper_states_override: Optional[Dict[str, str]] = None,
        device_ips_override: Optional[Dict[str, List[str]]] = None,
        route_history_store_override: Optional[Any] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full automated multi-device network & routing diagnostic pipeline end-to-end.
        """
        t_start = time.time()
        pipeline_id = f"auto_{uuid.uuid4().hex[:10]}"
        own_cancel = cancel_event or threading.Event()
        with self._lock:
            self._active_pipelines[pipeline_id] = own_cancel

        try:
            intent_meta = self.classify_routing_intent(
                symptom, target_ip=target_ip, routing_table=routing_table
            )
            effective_table = intent_meta["routing_table"]
            effective_dest = intent_meta["destination"]
            routing_intent = intent_meta["intent"]
            symptom_text = symptom or "Pemeriksaan kesehatan, topologi & integritas routing otomatis"

            # 1. Requirement Validation & DIO (Section 10.1 & 10.3)
            missing_fields_spec: List[Dict[str, Any]] = []
            available_choices: List[Dict[str, str]] = []
            try:
                inv_res = self.inv_store.list_devices()
                for d in inv_res.get("devices", []) if inv_res.get("success") else []:
                    if d.get("enabled", 1):
                        available_choices.append({"value": d["name"], "label": f"{d['name']} ({d.get('host', '')})"})
            except Exception:
                pass

            if require_dio_validation and intent_meta["needs_explicit_destination"] and not effective_dest:
                missing_fields_spec.append({
                    "key": "target_ip",
                    "label": "Alamat IP / Prefix Tujuan atau Gateway",
                    "required": True,
                    "placeholder": "Contoh: 10.10.10.0/24 atau 192.168.1.1",
                    "helper_text": "Masukkan prefix tujuan atau IP gateway yang ingin dianalisis jalurnya.",
                })

            targets: List[str] = []
            if precollected_routes:
                targets = list(target_devices) if target_devices else list(precollected_routes.keys())
            else:
                try:
                    targets = self.resolve_target_devices(target_devices)
                except ValueError as ve:
                    if require_dio_validation:
                        missing_fields_spec.append({
                            "key": "target_devices",
                            "label": "Perangkat Router Target",
                            "required": True,
                            "options": available_choices,
                            "helper_text": str(ve),
                        })
                    else:
                        raise

            if require_dio_validation and missing_fields_spec:
                dio_plan = self.dio_analyzer.analyze(
                    user_message=symptom_text,
                    planner_output={
                        "intent": routing_intent,
                        "confidence": 0.65,
                        "known_data": {
                            "target_devices": targets,
                            "routing_table": effective_table,
                        },
                        "missing_data": missing_fields_spec,
                        "choices": available_choices,
                        "source_agent": "AKANE",
                    },
                    available_capability={"name": "auto_diagnose_network", "danger": False},
                )
                return {
                    "success": True,
                    "pipeline_id": pipeline_id,
                    "status": "needs_input",
                    "routing_intent": routing_intent,
                    "dio_required": True,
                    "dio_interaction_plan": dio_plan.to_dict() if hasattr(dio_plan, "to_dict") else dio_plan.model_dump(),
                    "read_only": True,
                    "safety_disclosure": "Pemeriksaan bersifat 100% Read-Only. Menunggu kelengkapan parameter dari operator.",
                }

            if own_cancel.is_set():
                return self._build_cancelled_response(pipeline_id, t_start, targets, symptom_text, routing_intent)

            primary_device = targets[0]
            related_devices = targets[1:] if len(targets) > 1 else []

            # 2. Evidence-Driven Planning & Single-Pass Evidence Reuse (Section 10.3)
            resolved_inc_type = self.investigator.classify_symptom(symptom_text)
            req_types = list(
                dict.fromkeys(
                    INCIDENT_EVIDENCE_REQUIREMENTS.get(
                        resolved_inc_type,
                        ["identity", "interfaces", "ip_addresses", "routes", "arp"],
                    )
                    + ["routes", "ip_addresses", "interfaces"]
                )
            )
            cache_key = (tuple(sorted(targets)), tuple(sorted(req_types)))
            evidence_reused = False
            mbundle: Optional[MultiDeviceEvidenceBundle] = prebuilt_bundle

            if mbundle is None and precollected_routes is None:
                now = time.time()
                with self._lock:
                    cached_entry = self._bundle_cache.get(cache_key)
                    if cached_entry and reuse_fresh_sec > 0 and (now - cached_entry[0]) <= reuse_fresh_sec:
                        mbundle = cached_entry[1]
                        evidence_reused = True
                        self.last_collection_executions = 0

                if mbundle is None:
                    # N5-C3: Check UnifiedEvidenceService before opening live SSH connections
                    try:
                        from core.network_intelligence.evidence_service import get_unified_evidence_service
                        unified_svc = get_unified_evidence_service()
                        u_bundle = unified_svc.assemble_evidence_bundle(
                            device_ids=targets,
                            required_types=req_types,
                            allow_cli_fallback=False,
                        )
                        target_coverage = set(u_bundle.device_records.keys())
                        if set(targets).issubset(target_coverage) and len(u_bundle.records) >= len(targets):
                            from core.network_intelligence.models import EvidenceItem
                            from core.network_intelligence.multi_device_collector import MultiDeviceCollectionSummary
                            dev_bundles = {}
                            for dev_id in targets:
                                recs = u_bundle.device_records.get(dev_id, [])
                                dev_items = [
                                    EvidenceItem(
                                        evidence_id=r.evidence_id,
                                        device_identity=dev_id,
                                        observation_type=r.observation_type,
                                        source_command=r.source_command,
                                        collection_timestamp=r.timestamp,
                                        collection_status="SUCCESS",
                                        normalized_value=r.normalized_payload,
                                        freshness=r.freshness.value if hasattr(r.freshness, "value") else str(r.freshness),
                                    )
                                    for r in recs
                                ]
                                dev_bundles[dev_id] = {
                                    "target": dev_id,
                                    "display_name": dev_id,
                                    "ros_version": "v7",
                                    "evidence_items": dev_items,
                                    "status": "SUCCESS",
                                    "missing_evidence": [],
                                    "contradictions": [],
                                }
                            mbundle = MultiDeviceEvidenceBundle(
                                bundle_id=u_bundle.bundle_id,
                                timestamp=u_bundle.created_at,
                                device_bundles=dev_bundles,
                                summary=MultiDeviceCollectionSummary(
                                    total_devices=len(targets),
                                    successful_devices=len(targets),
                                    failed_devices=0,
                                    unreachable_devices=0,
                                    execution_duration_sec=0.01,
                                    device_statuses={d: "SUCCESS" for d in targets},
                                ),
                                cross_device_contradictions=list(u_bundle.cross_source_contradictions),
                            )
                            evidence_reused = True
                            self.last_collection_executions = 0
                            logger.info("Auto-Diagnosis reused %d fresh unified records from NMS/database without SSH.", len(u_bundle.records))
                    except Exception as e_nms:
                        logger.debug("UnifiedEvidenceService preflight lookup before SSH yielded: %s", e_nms)

                if mbundle is None:
                    orchestrator = MultiDeviceEvidenceOrchestrator(self.investigator.collector)
                    mbundle = orchestrator.collect_multi_device_bundle(
                        targets=targets,
                        required_types=req_types,
                        max_concurrency=min(3, max(1, len(targets))),
                    )
                    with self._lock:
                        self._bundle_cache[cache_key] = (time.time(), mbundle)
                        self.last_collection_executions = 1
            else:
                self.last_collection_executions = 0
                evidence_reused = prebuilt_bundle is not None or precollected_routes is not None

            if own_cancel.is_set():
                return self._build_cancelled_response(pipeline_id, t_start, targets, symptom_text, routing_intent)

            # 3. Run Investigator & Correlator REUSING the single mbundle (Zero duplicate SSH!)
            relationships = []
            if mbundle is not None:
                incident: IncidentRecord = self.investigator.run_multi_device_investigation(
                    primary_device=primary_device,
                    related_devices=related_devices,
                    symptom_description=symptom_text,
                    target_ip=effective_dest,
                    prebuilt_bundle=mbundle,
                )
                relationships = self.correlator.correlate_bundles(mbundle.device_bundles)
            else:
                # Controlled route-fixture mode (e.g., unit/acceptance tests supplying RouteCollectionResult directly)
                incident = IncidentRecord(
                    incident_id=f"inc_{uuid.uuid4().hex[:8]}",
                    device_identity=primary_device,
                    related_devices=related_devices,
                    incident_type=resolved_inc_type.value,
                    severity="MEDIUM",
                    symptoms=[symptom_text],
                    user_description=symptom_text,
                    observed_facts=[f"Evaluated route evidence across {len(targets)} devices."],
                    inferred_hypotheses=[],
                    missing_evidence=[],
                    recommended_tests=[],
                    confidence="MEDIUM",
                    investigation_status="DIAGNOSIS_READY",
                )

            if own_cancel.is_set():
                return self._build_cancelled_response(pipeline_id, t_start, targets, symptom_text, routing_intent)

            # 4. Route Normalization & Multi-Device Route Intelligence (WP 4.6.1 – 4.6.5)
            route_collector = get_route_collector()
            if precollected_routes is not None:
                route_collections: Dict[str, RouteCollectionResult] = dict(precollected_routes)
            elif mbundle is not None:
                ingested = route_collector.ingest_bundle_routes(mbundle)
                route_collections = dict(ingested)
                # Include any fresh cached device routes if already collected via MultiDeviceRouteCollector
                for t in targets:
                    c_res = route_collector.get_latest_result(t)
                    if c_res and c_res.device_id not in route_collections:
                        route_collections[c_res.device_id] = c_res
            else:
                route_collections = route_collector.list_latest_results()

            # Resolve CanonicalDevice IDs for primary device & IP ownership
            c_prim = self.registry.resolve_device(primary_device)
            primary_canon_id = (
                primary_device
                if primary_device in route_collections
                else (c_prim.device_id if c_prim and c_prim.device_id in route_collections else primary_device)
            )

            dev_ips: Dict[str, List[str]] = dict(device_ips_override or {})
            if not dev_ips:
                for d in self.registry.list_devices():
                    if d.all_ips:
                        dev_ips[d.device_id] = list(d.all_ips)
            # Also enrich dev_ips from mbundle ip_addresses observations!
            if mbundle is not None:
                for b_dev, b_data in mbundle.device_bundles.items():
                    c_b = self.registry.resolve_device(b_dev)
                    cid = b_dev if b_dev in route_collections else (c_b.device_id if c_b else b_dev)
                    for it in b_data.get("evidence_items", []):
                        if getattr(it, "observation_type", "") == "ip_addresses" and getattr(it, "collection_status", "") == "SUCCESS":
                            nv = getattr(it, "normalized_value", {}) or {}
                            for addr_obj in nv.get("addresses", []):
                                raw_addr = str(addr_obj.get("address") or "").split("/")[0].strip()
                                if raw_addr:
                                    dev_ips.setdefault(cid, [])
                                    if raw_addr not in dev_ips[cid]:
                                        dev_ips[cid].append(raw_addr)

            # Topology & NMS operational context
            topo_edges: List[Dict[str, Any]] = list(topology_edges_override or [])
            oper_states: Dict[str, str] = dict(device_oper_states_override or {})
            if topology_edges_override is None or device_oper_states_override is None:
                try:
                    from core.topology_engine import get_topology_engine
                    topo = get_topology_engine().get_topology()
                    if topology_edges_override is None:
                        topo_edges = topo.get("edges", [])
                    if device_oper_states_override is None:
                        for n in topo.get("nodes", []):
                            nid = str(n.get("id") or "")
                            if nid:
                                oper_states[nid] = str(n.get("status") or "online")
                except Exception:
                    pass

            # Historical Route Correlation (WP 4.6.4)
            hist_store = route_history_store_override or get_route_history_store()
            historical_comparison: Dict[str, Any] = {
                "persisted_snapshot": None,
                "recent_changes": [],
                "analytics": {},
            }
            try:
                if persist_route_snapshot and route_collections:
                    historical_comparison["persisted_snapshot"] = hist_store.create_multi_device_snapshots(
                        route_collections,
                        trigger_type="auto_diagnosis",
                        description=f"Auto-diagnosis ({routing_intent})",
                    )
                recent_chgs, total_chgs = hist_store.list_changes(limit=25, offset=0)
                historical_comparison["recent_changes"] = [c.to_dict() for c in recent_chgs]
                historical_comparison["total_recorded_changes"] = total_chgs
                historical_comparison["analytics"] = hist_store.get_historical_analytics(limit=50)
            except Exception as hist_exc:
                logger.debug("Historical route lookup skipped/degraded: %s", hist_exc)

            # Single/Multi-Device Table Findings (WP 4.6.2)
            table_findings = self.route_table_analyzer.analyze_multi_device_routes(
                route_collections,
                device_ips=dev_ips,
                target_destination=effective_dest,
            )

            # Cross-Device Route Correlation & Path Reconstruction (WP 4.6.5)
            path_dest = effective_dest or "8.8.8.8"
            xdev_report = self.cross_device_engine.analyze_network_routing(
                route_collections,
                device_ips=dev_ips,
                topology_edges=topo_edges,
                device_oper_states=oper_states,
                registered_device_ids=list(route_collections.keys()) or targets,
                source_device=primary_canon_id if primary_canon_id in route_collections else (next(iter(route_collections), None)),
                destination=path_dest,
                routing_table=effective_table,
                recent_route_changes=historical_comparison.get("recent_changes", []),
            )

            # Dependency & Recursive Graph Evaluation (WP 4.6.3)
            dep_graph = self.route_dep_analyzer.build_dependency_graph(
                route_collections,
                device_ips=dev_ips,
                routing_table=effective_table,
            )

            if own_cancel.is_set():
                return self._build_cancelled_response(pipeline_id, t_start, targets, symptom_text, routing_intent)

            # 5. Root Cause & Epistemic Confidence Synthesis (Section 10.4)
            root_causes, partial_warnings, all_verif_cmds = self._synthesize_root_causes(
                targets=targets,
                primary_device=primary_canon_id,
                effective_dest=effective_dest,
                effective_table=effective_table,
                route_collections=route_collections,
                table_findings=table_findings,
                xdev_report=xdev_report,
                dep_graph=dep_graph,
                historical_comparison=historical_comparison,
                incident=incident,
            )

            # Merge synthesized root causes into incident ranked hypotheses if incident had only generic fallback
            def _get_h_field(h: Any, field_name: str, default: Any = "") -> Any:
                if isinstance(h, dict):
                    return h.get(field_name, default)
                return getattr(h, field_name, default)

            def _to_h_dict(h: Any) -> Dict[str, Any]:
                if isinstance(h, dict):
                    return h
                return h.to_dict() if hasattr(h, "to_dict") else vars(h)

            ranked_hyps = [_to_h_dict(h) for h in incident.inferred_hypotheses]
            for rc in root_causes:
                if rc["epistemic_tier"] != "Insufficient evidence":
                    ranked_hyps.insert(0, {
                        "hypothesis_id": rc["root_cause_id"],
                        "title": rc["description"][:110],
                        "explanation": rc["description"],
                        "epistemic_tier": rc["epistemic_tier"],
                        "confidence": rc["confidence"],
                        "supporting_evidence": rc["evidence_ids"],
                        "alternative_explanations": rc["alternative_explanations"],
                        "missing_evidence": rc["missing_evidence"],
                        "recommended_test": (
                            rc["recommended_verification_steps"][0]
                            if rc["recommended_verification_steps"]
                            else ""
                        ),
                    })

            # 6. Safe Non-Mutating Configuration Proposal & Rollback Planning (Section 10.5)
            recommended_plan: Optional[ConfigurationPlan] = None
            plan_reason: str = ""
            rollback_proposal: Optional[Dict[str, Any]] = None

            if auto_plan:
                top_title_blob = " ".join(
                    [str(_get_h_field(h, "title", "")) for h in ranked_hyps[:3]]
                    + [rc["description"] for rc in root_causes[:3]]
                ).lower()
                if "missing_default_route" in top_title_blob or "kehilangan rute default" in top_title_blob or "tidak memiliki rute default" in top_title_blob:
                    desired_state = {
                        "dst_address": "0.0.0.0/0",
                        "gateway": effective_dest if (effective_dest and "/" not in effective_dest and effective_dest != "8.8.8.8") else "192.168.43.1",
                        "comment": "AIRA Proposal Default Route (Manual Review Required)",
                    }
                    plan_obj = self.planner.generate_plan(
                        target_device=primary_device,
                        change_type="ADD_STATIC_ROUTE",
                        parameters=desired_state,
                        incident_id=incident.incident_id,
                    )
                    if plan_obj:
                        recommended_plan = plan_obj
                        plan_reason = "Terdeteksi ketiadaan default route aktif; proposal rencana konfigurasi disusun secara non-mutating."
                        rollback_proposal = {
                            "description": "Hapus static default route yang diusulkan apabila menyebabkan konflik rute.",
                            "auto_executed": False,
                            "requires_manual_operator_approval": True,
                        }
                elif "nat" in top_title_blob or "masquerade" in top_title_blob:
                    desired_state = {
                        "chain": "srcnat",
                        "out_interface": "ether1",
                        "action": "masquerade",
                        "comment": "AIRA Proposal NAT Masquerade (Manual Review Required)",
                    }
                    plan_obj = self.planner.generate_plan(
                        target_device=primary_device,
                        change_type="CONFIGURE_NAT",
                        parameters=desired_state,
                        incident_id=incident.incident_id,
                    )
                    if plan_obj:
                        recommended_plan = plan_obj
                        plan_reason = "Terdeteksi ketiadaan NAT Masquerade; proposal disusun secara non-mutating."
                        rollback_proposal = {
                            "description": "Nonaktifkan atau hapus aturan srcnat masquerade baru jika tidak sesuai kebijakan.",
                            "auto_executed": False,
                            "requires_manual_operator_approval": True,
                        }

            # Overall epistemic tier & summary
            lead_rc = root_causes[0] if root_causes else None
            overall_tier = lead_rc["epistemic_tier"] if lead_rc else "Confirmed finding"
            top_h_title = (
                lead_rc["description"]
                if lead_rc
                else (str(_get_h_field(ranked_hyps[0], "title", "")) if ranked_hyps else "Tidak ada anomali kritis")
            )
            top_conf = lead_rc["confidence"] if lead_rc else 0.85

            summary_lines = [
                f"Diagnostik otomatis ({routing_intent}) selesai untuk {len(targets)} perangkat: {', '.join(targets)}.",
                f"Bukti observasi: {len(incident.observed_facts)} fakta, {len(route_collections)} tabel rute router dinormalisasi (Evidence Reused: {evidence_reused}).",
                f"Korelasi lintas perangkat: {len(xdev_report.verified_relationships)} relasi rute terverifikasi, {len(xdev_report.inconsistencies)} inkonsistensi.",
                f"Kesimpulan utama [{overall_tier}]: {top_h_title} (Keyakinan: {float(top_conf) * 100:.0f}%).",
            ]
            if partial_warnings:
                summary_lines.append(f"Peringatan bukti parsial: {'; '.join(partial_warnings[:2])}")
            if recommended_plan:
                summary_lines.append(f"Rekomendasi rencana (Non-Mutating): {plan_reason} (Plan ID: {recommended_plan.plan_id}).")
            else:
                summary_lines.append("Tidak ada mutasi konfigurasi otomatis yang dijalankan (100% Read-Only).")

            duration_ms = int((time.time() - t_start) * 1000)

            collection_status_map = {
                dev_id: {
                    "status": col.status,
                    "completeness": col.completeness,
                    "route_count": col.route_count,
                    "active_route_count": col.active_route_count,
                    "routing_tables": list(col.routing_tables),
                    "evidence_id": col.evidence_id,
                }
                for dev_id, col in route_collections.items()
            }

            return {
                "success": True,
                "pipeline_id": pipeline_id,
                "status": "completed",
                "cancelled": False,
                "routing_intent": routing_intent,
                "routing_table": effective_table,
                "destination": path_dest,
                "timestamp": time.time(),
                "duration_ms": duration_ms,
                "evidence_reused": evidence_reused,
                "collection_executions": self.last_collection_executions,
                "primary_device": primary_device,
                "target_devices": targets,
                "symptom": symptom_text,
                "incident": incident.to_dict(),
                "evidence_count": len(incident.observed_facts),
                "observed_facts": incident.observed_facts,
                "collection_status": collection_status_map,
                "partial_evidence_warnings": partial_warnings,
                "root_causes": root_causes,
                "epistemic_classification": overall_tier,
                "top_hypothesis": ranked_hyps[0] if ranked_hyps else None,
                "ranked_hypotheses": ranked_hyps,
                "correlation_relationships": [r.to_dict() if hasattr(r, "to_dict") else r for r in relationships],
                "route_intelligence": {
                    "table_findings": [f.to_dict() for f in table_findings],
                    "cross_device": xdev_report.to_dict(),
                    "path_evaluation": xdev_report.path_evaluation,
                    "topology_overlay": xdev_report.topology_overlay,
                    "dependency_summary": {
                        "nodes_count": len(dep_graph.nodes),
                        "edges_count": len(dep_graph.edges),
                        "unresolved_routes": [
                            r.to_dict()
                            for r in dep_graph.resolutions
                            if r.state not in (
                                DependencyResolutionState.DIRECTLY_CONNECTED.value,
                                DependencyResolutionState.RECURSIVE_RESOLVED.value,
                                DependencyResolutionState.MULTI_PATH_RESOLVED.value,
                            )
                        ][:25],
                        "resolutions_count": len(dep_graph.resolutions),
                        "persisted_as_topology_edges": False,
                    },
                    "historical_comparison": historical_comparison,
                },
                "verification_recommendations": all_verif_cmds,
                "recommended_plan": recommended_plan.to_dict() if recommended_plan else None,
                "rollback_proposal": rollback_proposal,
                "summary": "\n".join(summary_lines),
                "read_only": True,
                "auto_remediation_executed": False,
                "limitations": [
                    "Evaluasi jalur rute berbasis RIB control-plane read-only; LPM terhitung bukan bukti instalasi FIB kernel.",
                    "Policy routing / firewall mangle prerouting tidak disimulasikan tanpa paket trafik nyata.",
                    "Jalur routing terinferensi (inferred path) bukan bukti paket data-plane terobservasi.",
                ],
                "safety_disclosure": "Pemeriksaan dan simulasi bersifat 100% Read-Only. Tidak ada perintah mutasi yang dijalankan ke perangkat jaringan.",
            }
        finally:
            with self._lock:
                self._active_pipelines.pop(pipeline_id, None)

    # ------------------------------------------------------------------
    # Structured Root Cause & Confidence Evaluation (Section 10.4 & 10.5)
    # ------------------------------------------------------------------

    def _synthesize_root_causes(
        self,
        *,
        targets: Sequence[str],
        primary_device: str,
        effective_dest: Optional[str],
        effective_table: str,
        route_collections: Dict[str, RouteCollectionResult],
        table_findings: Sequence[Any],
        xdev_report: Any,
        dep_graph: Any,
        historical_comparison: Dict[str, Any],
        incident: IncidentRecord,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        root_causes: List[Dict[str, Any]] = []
        partial_warnings: List[str] = []
        verif_commands_raw: List[str] = [
            "/routing route print",
            "/ip route print detail",
            "/ip address print",
            "/interface print",
        ]

        route_chain = [
            f"{h['device_id']}({h.get('matched_prefix') or 'no-match'} -> {h.get('gateway') or h.get('hop_state')})"
            for h in (xdev_report.path_evaluation or {}).get("primary_hops", [])
        ]

        # Check collection completeness first
        complete_devs = [
            d for d, c in route_collections.items() if c.completeness == RouteCompleteness.COMPLETE.value
        ]
        missing_ev_global: List[str] = []
        for d in targets:
            col = route_collections.get(d)
            if col is None:
                msg = f"Bukti tabel rute untuk '{d}' tidak tersedia."
                partial_warnings.append(msg)
                missing_ev_global.append(msg)
            elif col.completeness != RouteCompleteness.COMPLETE.value:
                msg = f"Pengumpulan rute pada '{d}' tidak lengkap (status={col.status}, completeness={col.completeness})."
                partial_warnings.append(msg)
                missing_ev_global.append(msg)

        if not complete_devs:
            safe_cmds = filter_safe_readonly_commands(verif_commands_raw)
            root_causes.append({
                "root_cause_id": f"rc_{uuid.uuid4().hex[:8]}",
                "epistemic_tier": "Insufficient evidence",
                "description": "Bukti routing tidak mencukupi karena seluruh perangkat target gagal atau tidak lengkap saat pengumpulan data read-only.",
                "affected_device": primary_device,
                "affected_prefix": effective_dest or "0.0.0.0/0",
                "evidence_ids": [c.evidence_id for c in route_collections.values() if c.evidence_id],
                "route_chain": route_chain,
                "related_topology": {"unavailable_devices": list(xdev_report.unavailable_devices)},
                "confidence": 0.15,
                "alternative_explanations": [
                    "Koneksi manajemen SSH ke router terputus atau diblokir firewall.",
                    "Perangkat sedang reboot atau mengalami gangguan daya.",
                ],
                "missing_evidence": missing_ev_global or ["Tabel rute aktif dari minimal satu router yang dikelola."],
                "recommended_verification_steps": safe_cmds,
            })
            return root_causes, partial_warnings, [
                {"command": c, "read_only_verified": True, "purpose": "Verifikasi manual tabel rute & antarmuka"}
                for c in safe_cmds
            ]

        def _add_rc(
            *,
            tier: str,
            desc: str,
            dev: str,
            pfx: str,
            evs: Sequence[str],
            topo_info: Dict[str, Any],
            conf: float,
            alts: Sequence[str],
            missing: Sequence[str],
            cmds: Sequence[str],
        ) -> None:
            checked_cmds = filter_safe_readonly_commands(cmds)
            for c in checked_cmds:
                if c not in verif_commands_raw:
                    verif_commands_raw.append(c)
            # Cap confidence if partial evidence warnings exist on related routers
            adj_conf = min(conf, 0.78) if (missing_ev_global and tier == "Confirmed finding") else conf
            adj_tier = "Strong hypothesis" if (missing_ev_global and tier == "Confirmed finding") else tier
            root_causes.append({
                "root_cause_id": f"rc_{uuid.uuid4().hex[:8]}",
                "epistemic_tier": adj_tier,
                "description": desc,
                "affected_device": dev,
                "affected_prefix": pfx,
                "evidence_ids": list(dict.fromkeys(e for e in evs if e)),
                "route_chain": list(route_chain),
                "related_topology": topo_info,
                "confidence": round(adj_conf, 3),
                "alternative_explanations": list(alts),
                "missing_evidence": list(dict.fromkeys([*missing, *missing_ev_global])),
                "recommended_verification_steps": checked_cmds,
            })

        # A. Single-device RouteTableAnalyzer findings (missing default, unreachable gateway, broken recursion, ECMP ambiguity)
        conf_str_map = {
            "CONFIRMED": 0.94,
            "HIGH": 0.88,
            "MEDIUM": 0.72,
            "LOW": 0.55,
            "HYPOTHESIS": 0.45,
        }
        for tf in table_findings:
            ft = tf.finding_type
            raw_conf = conf_str_map.get(str(tf.confidence).upper())
            if raw_conf is None:
                try:
                    raw_conf = float(tf.confidence)
                except (TypeError, ValueError):
                    raw_conf = 0.85

            if ft in (
                RouteFindingType.MISSING_DEFAULT_ROUTE.value,
                RouteFindingType.MISSING_DESTINATION_ROUTE.value,
                RouteFindingType.UNREACHABLE_NEXT_HOP.value,
                RouteFindingType.UNEXPECTED_ROUTING_TABLE_ASSIGNMENT.value,
                RouteFindingType.CONFLICTING_ROUTE_ADVERTISEMENTS.value,
            ):
                _add_rc(
                    tier="Confirmed finding",
                    desc=f"[{ft}] {tf.explanation}",
                    dev=tf.device_id,
                    pfx=tf.dst_prefix or effective_dest or "0.0.0.0/0",
                    evs=tf.evidence_ids,
                    topo_info={"routing_table": tf.routing_table},
                    conf=max(0.88, raw_conf),
                    alts=[
                        "Dynamic routing adjacency (OSPF/BGP) sedang konvergensi ulang.",
                        "Antarmuka egress lokal mengalami link-down.",
                    ],
                    missing=[],
                    cmds=["/routing route print", "/ip address print", "/interface print", "/ip arp print"],
                )
            elif ft in (
                RouteFindingType.ECMP_CONFIGURATION.value,
                RouteFindingType.DUPLICATE_ROUTE_CANDIDATES.value,
                RouteFindingType.OVERLAPPING_PREFIXES.value,
                RouteFindingType.ASYMMETRIC_ROUTE_HYPOTHESIS.value,
            ):
                _add_rc(
                    tier="Weak hypothesis",
                    desc=f"[{ft}] {tf.explanation}",
                    dev=tf.device_id,
                    pfx=tf.dst_prefix or effective_dest or "0.0.0.0/0",
                    evs=tf.evidence_ids,
                    topo_info={"routing_table": tf.routing_table, "is_ecmp": ft == RouteFindingType.ECMP_CONFIGURATION.value},
                    conf=min(0.68, raw_conf),
                    alts=[
                        "Load-balancing ECMP atau backup kandidat disengaja oleh operator.",
                        "Salah satu jalur ECMP memiliki gangguan upstream hilir.",
                    ],
                    missing=["Telemetri flow hash per-koneksi (data-plane)."],
                    cmds=["/routing route print", "/ip route print detail"],
                )

        # B. Dependency & Recursive Resolution failures (WP 4.6.3)
        for res in dep_graph.resolutions:
            if res.state in (
                DependencyResolutionState.UNRESOLVED_MISSING_ROUTE.value,
                DependencyResolutionState.GATEWAY_UNREACHABLE.value,
                DependencyResolutionState.DEPTH_LIMIT_EXCEEDED.value,
                DependencyResolutionState.CYCLE_DETECTED.value,
            ):
                already_has_recursive = any(
                    res.dst_prefix == rc["affected_prefix"]
                    and res.device_id == rc["affected_device"]
                    and ("rekursif" in rc["description"].lower() or "recursive" in rc["description"].lower())
                    for rc in root_causes
                )
                if not already_has_recursive:
                    res_evs = [
                        str(step.get("evidence_id"))
                        for step in getattr(res, "evidence_chain", [])
                        if isinstance(step, dict) and step.get("evidence_id")
                    ]
                    if not res_evs and res.device_id in route_collections and route_collections[res.device_id].evidence_id:
                        res_evs = [route_collections[res.device_id].evidence_id]
                    _add_rc(
                        tier="Confirmed finding",
                        desc=f"Kegagalan resolusi dependensi rute rekursif ({res.state}) pada '{res.device_id}' untuk {res.dst_prefix}: {res.explanation}",
                        dev=res.device_id,
                        pfx=res.dst_prefix,
                        evs=res_evs,
                        topo_info={"routing_table": res.routing_table, "recursion_depth": res.max_depth_reached},
                        conf=0.91,
                        alts=["Rute IGP pendukung terhapus atau memiliki target-scope terlalu kecil."],
                        missing=[],
                        cmds=["/routing route print", "/ip route print detail"],
                    )

        # C. Cross-device inconsistencies (WP 4.6.5: VRF mismatch, route mismatch, upstream unavailable, topology conflict, missing return)
        for inc in xdev_report.inconsistencies:
            tier_map = {
                "OBSERVED_FACT": "Confirmed finding",
                "STRONG_HYPOTHESIS": "Strong hypothesis",
                "HYPOTHESIS": "Weak hypothesis",
            }
            mapped_tier = tier_map.get(inc.epistemic_class, "Strong hypothesis")
            _add_rc(
                tier=mapped_tier,
                desc=f"[{inc.inconsistency_type}] {inc.explanation}",
                dev=inc.affected_devices[0] if inc.affected_devices else primary_device,
                pfx=inc.dst_prefix or effective_dest or "0.0.0.0/0",
                evs=inc.evidence_ids,
                topo_info={
                    "affected_devices": inc.affected_devices,
                    "unavailable_devices": xdev_report.unavailable_devices,
                },
                conf=float(inc.confidence),
                alts=[
                    "NAT masquerade pada router transit menyamarkan kebutuhan return route langsung.",
                    "Pemisahan VRF dikonfigurasi sengaja untuk isolasi tenant.",
                ],
                missing=[
                    f"Bukti rute lengkap dari {d}" for d in xdev_report.incomplete_devices
                ],
                cmds=["/routing route print", "/ip neighbor print detail", "/ip firewall nat print"],
            )

        # D. Historical Route Changes & Pre-Failure Correlation (WP 4.6.4)
        recent_changes = historical_comparison.get("recent_changes") or []
        critical_hist = [
            c for c in recent_changes
            if c.get("change_type") in ("ROUTE_REMOVED", "GATEWAY_CHANGED", "BECAME_INACTIVE", "INTERFACE_CHANGED", "VRF_TABLE_CHANGED")
        ]
        if critical_hist:
            top_chg = critical_hist[0]
            corr_events = (historical_comparison.get("analytics") or {}).get("temporal_correlations") or []
            _add_rc(
                tier="Strong hypothesis",
                desc=(
                    f"Perubahan historis rute terdeteksi sebelum/saat gangguan: {top_chg.get('change_type')} "
                    f"pada '{top_chg.get('device_id')}' untuk prefix {top_chg.get('dst_prefix')} "
                    f"(snapshot {top_chg.get('snapshot_id')})."
                ),
                dev=str(top_chg.get("device_id") or primary_device),
                pfx=str(top_chg.get("dst_prefix") or effective_dest or "0.0.0.0/0"),
                evs=[str(top_chg.get("snapshot_id") or "")],
                topo_info={
                    "temporal_correlations_count": len(corr_events),
                    "epistemic_note": "TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION",
                },
                conf=0.82,
                alts=[
                    "Perubahan rute merupakan dampak hilir dari flapping link fisik atau sesi OSPF/BGP.",
                    "Perubahan dilakukan secara terencana oleh administrator.",
                ],
                missing=[],
                cmds=["/routing route print", "/log print without-paging"],
            )

        # E. Healthy / Clean Multi-Device State when no anomalies exist
        if not root_causes:
            evs_all = [c.evidence_id for c in route_collections.values() if c.evidence_id]
            _add_rc(
                tier="Confirmed finding" if not missing_ev_global else "Strong hypothesis",
                desc=(
                    f"Jalur dan tabel routing pada {', '.join(complete_devs)} konsisten untuk target "
                    f"{effective_dest or '0.0.0.0/0'} (state={(xdev_report.path_evaluation or {}).get('state', 'EVALUATED')})."
                ),
                dev=primary_device,
                pfx=effective_dest or "0.0.0.0/0",
                evs=evs_all,
                topo_info={"verified_relationships": len(xdev_report.verified_relationships)},
                conf=0.90 if not missing_ev_global else 0.72,
                alts=["Gangguan aplikasi/firewall L4-L7 di luar tabel routing RIB."],
                missing=[],
                cmds=["/routing route print", "/ip firewall filter print"],
            )

        safe_verif_list = [
            {
                "command": cmd,
                "read_only_verified": True,
                "purpose": "Verifikasi manual status routing, alamat IP, dan antarmuka secara aman (Read-Only).",
            }
            for cmd in filter_safe_readonly_commands(verif_commands_raw)
        ]
        return root_causes, partial_warnings, safe_verif_list

    def _build_cancelled_response(
        self,
        pipeline_id: str,
        t_start: float,
        targets: Sequence[str],
        symptom_text: str,
        routing_intent: str,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "pipeline_id": pipeline_id,
            "status": "cancelled",
            "cancelled": True,
            "routing_intent": routing_intent,
            "duration_ms": int((time.time() - t_start) * 1000),
            "target_devices": list(targets),
            "symptom": symptom_text,
            "read_only": True,
            "auto_remediation_executed": False,
            "safety_disclosure": "Pipeline diagnostik dibatalkan dengan aman (100% Read-Only).",
        }


_AUTO_ORCHESTRATOR_INSTANCE: Optional[AutomaticNetworkOrchestrator] = None


def get_auto_orchestrator() -> AutomaticNetworkOrchestrator:
    global _AUTO_ORCHESTRATOR_INSTANCE
    if _AUTO_ORCHESTRATOR_INSTANCE is None:
        _AUTO_ORCHESTRATOR_INSTANCE = AutomaticNetworkOrchestrator()
    return _AUTO_ORCHESTRATOR_INSTANCE
