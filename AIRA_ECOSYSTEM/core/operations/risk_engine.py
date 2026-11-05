"""
AIRA OS — Risk and Operational Impact Assessment Engine (Networking VIII / WP 8.6).

Features:
1. Deterministic algebraic risk scoring with inspectable factors.
2. Non-destructive Virtual Graph Simulation over NetworkKnowledgeGraph:
   Simulates device failure, interface down, gateway outage, or link cuts
   WITHOUT mutating the original graph or cloning memory copies.
3. Multi-scenario counterfactual comparison in memory.
4. Strict multi-tenant boundaries (RFC 1918 overlap safe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from core.network_intelligence.intelligence_models import GraphEntityType
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.db import ensure_operational_schema
from core.operations.models import RiskLevel, ServiceCriticality
from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.operations.risk_engine")


@dataclass
class ScenarioImpactAssessment:
    """Evaluated blast radius and impact for a specific scenario."""
    scenario_id: str
    scenario_name: str
    tenant_id: str
    risk_score: float                       # 0.0 - 100.0
    risk_level: str                         # RiskLevel (INFO, WATCH, WARNING, CRITICAL)
    directly_affected_devices: List[str]
    transit_dependent_devices: List[str]
    affected_services: List[str]
    affected_sites: List[str]
    has_redundancy: bool
    assumptions: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    factors: Dict[str, float] = field(default_factory=dict)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "tenant_id": self.tenant_id,
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "directly_affected_devices": self.directly_affected_devices,
            "transit_dependent_devices": self.transit_dependent_devices,
            "affected_services": self.affected_services,
            "affected_sites": self.affected_sites,
            "has_redundancy": self.has_redundancy,
            "assumptions": self.assumptions,
            "uncertainties": self.uncertainties,
            "factors": self.factors,
            "evaluated_at": self.evaluated_at,
        }


class RiskAssessmentEngine:
    """Non-destructive failure simulator and blast-radius evaluator."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        ensure_operational_schema(self.db_path)

    # -----------------------------------------------------------------------
    # Virtual Graph Traversal Simulation
    # -----------------------------------------------------------------------
    def simulate_failure(
        self,
        tenant_id: str,
        graph: NetworkKnowledgeGraph,
        failed_devices: Optional[List[str]] = None,
        failed_interfaces: Optional[List[str]] = None,
        scenario_name: str = "Failure Simulation",
    ) -> ScenarioImpactAssessment:
        """
        Simulates network failure non-destructively using virtual exclusions.
        Does NOT alter graph.nodes or graph.edges.
        """
        scenario_id = f"sim_{uuid.uuid4().hex[:10]}"
        excluded_devs: Set[str] = set(failed_devices or [])
        excluded_ifaces: Set[str] = set(failed_interfaces or [])

        directly_affected: List[str] = sorted(list(excluded_devs))
        transit_dependent: Set[str] = set()
        affected_services: Set[str] = set()
        affected_sites: Set[str] = set()
        assumptions: List[str] = []
        uncertainties: List[str] = []

        # 1. Query tenant inventory from database
        with topology_transaction(self.db_path, write=False) as conn:
            # Load tenant devices
            dev_rows = conn.execute(
                "SELECT device_id, site_id, name FROM operational_devices WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()
            tenant_dev_map = {r["device_id"]: r["site_id"] for r in dev_rows}

            # Load business services & endpoints
            svc_rows = conn.execute(
                "SELECT s.service_id, s.criticality, ep.target_device_id, ep.target_interface, ep.is_primary "
                "FROM operational_services s "
                "JOIN operational_service_endpoints ep ON s.service_id = ep.service_id "
                "WHERE s.tenant_id = ?",
                (tenant_id,),
            ).fetchall()

        # Map affected sites directly
        for did in directly_affected:
            sid = tenant_dev_map.get(did)
            if sid:
                affected_sites.add(sid)

        # 2. Virtual Reachability Simulation
        # Traverse graph for transit dependencies (downstream nodes whose paths only go through excluded nodes)
        for dev_id in tenant_dev_map:
            if dev_id in excluded_devs:
                continue

            # Check if this node has outgoing path to default gateway or uplink
            # Virtual BFS ignoring excluded nodes & edges
            has_valid_path = self._virtual_path_exists(
                graph=graph,
                start_node=dev_id,
                excluded_nodes=excluded_devs,
                excluded_interfaces=excluded_ifaces,
            )

            if not has_valid_path:
                transit_dependent.add(dev_id)
                sid = tenant_dev_map.get(dev_id)
                if sid:
                    affected_sites.add(sid)

        # 3. Check Service Dependencies
        max_criticality_weight = 0.2
        for r in svc_rows:
            svc_id = r["service_id"]
            crit = r["criticality"]
            tgt_dev = r["target_device_id"]
            tgt_iface = r["target_interface"]
            is_pri = bool(r["is_primary"])

            if tgt_dev in excluded_devs or tgt_dev in transit_dependent or tgt_iface in excluded_ifaces:
                affected_services.add(svc_id)
                if crit == ServiceCriticality.TIER_1_MISSION_CRITICAL.value:
                    max_criticality_weight = max(max_criticality_weight, 1.0)
                elif crit == ServiceCriticality.TIER_2_BUSINESS_OPERATIONAL.value:
                    max_criticality_weight = max(max_criticality_weight, 0.75)
                elif crit == ServiceCriticality.TIER_3_OFFICE_PRODUCTIVITY.value:
                    max_criticality_weight = max(max_criticality_weight, 0.4)

        has_redundancy = len(transit_dependent) == 0 and len(affected_services) == 0

        # 4. Deterministic Risk Score Computation
        # Risk = 100 * (P * S * B * C * (1 - 0.5 * Redundancy))
        prob = 0.95  # Simulated deterministic failure probability
        severity = 1.0 if len(affected_services) > 0 or len(directly_affected) > 0 else 0.2
        total_affected_count = len(directly_affected) + len(transit_dependent)
        blast_factor = min(1.0, max(0.1, total_affected_count / 5.0))
        redundancy_factor = 1.0 if has_redundancy else 0.0

        raw_risk = 100.0 * (prob * severity * blast_factor * max_criticality_weight * (1.0 - 0.5 * redundancy_factor))
        risk_score = min(100.0, max(0.0, raw_risk))

        if risk_score >= 80.0:
            risk_level = RiskLevel.CRITICAL.value
        elif risk_score >= 50.0:
            risk_level = RiskLevel.WARNING.value
        elif risk_score >= 25.0:
            risk_level = RiskLevel.WATCH.value
        else:
            risk_level = RiskLevel.INFO.value

        assumptions.append(f"Simulasi kegagalan deterministik untuk {len(directly_affected)} perangkat dan {len(excluded_ifaces)} antarmuka.")
        if not has_redundancy:
            assumptions.append("Jalur alternatif (failover) tidak tersedia atau ikut terputus.")
        else:
            assumptions.append("Tersedia jalur redundan aktif yang menyerap beban trafik.")

        factors = {
            "failure_probability": prob,
            "failure_severity": severity,
            "blast_radius_factor": round(blast_factor, 3),
            "criticality_weight": round(max_criticality_weight, 2),
            "redundancy_mitigation": 0.5 if has_redundancy else 0.0,
        }

        return ScenarioImpactAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            tenant_id=tenant_id,
            risk_score=risk_score,
            risk_level=risk_level,
            directly_affected_devices=directly_affected,
            transit_dependent_devices=sorted(list(transit_dependent)),
            affected_services=sorted(list(affected_services)),
            affected_sites=sorted(list(affected_sites)),
            has_redundancy=has_redundancy,
            assumptions=assumptions,
            uncertainties=uncertainties,
            factors=factors,
        )

    def _virtual_path_exists(
        self,
        graph: NetworkKnowledgeGraph,
        start_node: str,
        excluded_nodes: Set[str],
        excluded_interfaces: Set[str],
    ) -> bool:
        """
        Performs a virtual breadth-first search on NetworkKnowledgeGraph
        skipping excluded nodes and edges dynamically.
        """
        if start_node in excluded_nodes:
            return False

        visited: Set[str] = {start_node}
        queue: List[str] = [start_node]

        while queue:
            curr = queue.pop(0)

            # Check neighbors
            out_edge_ids = graph.out_edges.get(curr, [])
            for eid in out_edge_ids:
                edge = graph.edges.get(eid)
                if not edge:
                    continue

                tgt = edge.target_id
                if tgt in excluded_nodes or tgt in visited:
                    continue

                # Check edge interface attribute
                if edge.attributes.get("interface") in excluded_interfaces:
                    continue

                visited.add(tgt)
                queue.append(tgt)

        # If more than 1 node reached without traversing exclusions, alternate path exists
        return len(visited) > 1

    # -----------------------------------------------------------------------
    # Multi-Scenario Comparison
    # -----------------------------------------------------------------------
    def compare_scenarios(
        self,
        tenant_id: str,
        graph: NetworkKnowledgeGraph,
        scenarios: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compares multiple failure or maintenance scenarios side-by-side."""
        results = []
        for sc in scenarios:
            name = sc.get("name", "Unnamed Scenario")
            devs = sc.get("failed_devices", [])
            ifaces = sc.get("failed_interfaces", [])
            assessment = self.simulate_failure(
                tenant_id=tenant_id,
                graph=graph,
                failed_devices=devs,
                failed_interfaces=ifaces,
                scenario_name=name,
            )
            results.append(assessment.to_dict())

        # Sort scenarios by risk score descending
        results.sort(key=lambda r: r["risk_score"], reverse=True)

        return {
            "tenant_id": tenant_id,
            "compared_scenarios_count": len(results),
            "highest_risk_scenario": results[0]["scenario_name"] if results else None,
            "scenarios": results,
            "compared_at": datetime.now(timezone.utc).isoformat(),
        }
