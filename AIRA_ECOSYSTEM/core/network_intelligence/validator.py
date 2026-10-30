"""
core/network_intelligence/validator.py — Static Configuration Validation & Risk Assessment.

Performs deterministic static validation on proposed configuration plans:
- Subnet overlap and prefix sanity
- Interface existence verification
- VLAN ID boundary and consistency checks
- Dependency graph acyclicity and topological ordering
- Management connectivity risk assessment
- Deterministic blast radius and risk scoring
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.canonical_network import get_canonical_registry
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.models import (
    ConfigurationPlan,
    PlanStatus,
    ValidationFinding,
    ValidationSeverity,
)

logger = logging.getLogger("aira.network_intelligence.validator")


class StaticValidator:
    """Deterministic validator for RouterOS configuration plans."""

    def __init__(self):
        self.collector = EvidenceCollector()
        self.registry = get_canonical_registry()

    def validate_plan(self, plan: ConfigurationPlan) -> ConfigurationPlan:
        """
        Runs comprehensive deterministic checks against current device state evidence.
        Updates validation_results, risk_level, management_connectivity_risk, and plan_status.
        """
        findings: List[ValidationFinding] = []
        target = plan.target_devices[0] if plan.target_devices else "unknown"

        # 1. Gather baseline evidence for validation
        evidence_bundle = self.collector.collect_evidence_bundle(
            target,
            ["interfaces", "ip_addresses", "routes", "bridge"],
        )
        evidence_map = {
            it.observation_type: it.normalized_value
            for it in evidence_bundle["evidence_items"]
            if it.collection_status == "SUCCESS"
        }

        # Check for incomplete baseline evidence
        if not evidence_map or any(it.collection_status != "SUCCESS" for it in evidence_bundle["evidence_items"]):
            findings.append(ValidationFinding(
                severity=ValidationSeverity.UNKNOWN.value,
                rule_id="INCOMPLETE_BASELINE_EVIDENCE",
                description="Bukti baseline interface/rute/IP tidak lengkap atau tidak dapat diakses; keabsahan konfigurasi tidak dapat dibuktikan secara pasti.",
                affected_object=target,
                suggested_resolution="Pastikan router terhubung via SSH untuk melengkapi bukti baseline.",
                is_blocking=False,
            ))

        existing_ifaces: Set[str] = set()
        if "interfaces" in evidence_map:
            for ifc in evidence_map["interfaces"].get("interfaces", []):
                if ifc.get("name"):
                    existing_ifaces.add(ifc["name"])

        existing_subnets: List[ipaddress.IPv4Network] = []
        if "ip_addresses" in evidence_map:
            for addr_rec in evidence_map["ip_addresses"].get("addresses", []):
                try:
                    net = ipaddress.ip_network(addr_rec.get("address", ""), strict=False)
                    if isinstance(net, ipaddress.IPv4Network):
                        existing_subnets.append(net)
                except Exception:
                    pass

        # 2. Check Management IP and Interface Protection
        dev = self.registry.resolve_device(target)
        mgmt_ip = dev.management_ip if dev else ""
        mgmt_risk = False
        mgmt_risk_expl = ""

        # 3. Validate Proposed Commands
        d_state = plan.desired_state.get("parameters", {})
        c_type = plan.desired_state.get("change_type", "").upper()

        # Check VLAN ID
        if "vlan_id" in d_state:
            try:
                vid = int(d_state["vlan_id"])
                if vid < 1 or vid > 4094:
                    findings.append(ValidationFinding(
                        severity=ValidationSeverity.ERROR.value,
                        rule_id="VLAN_ID_OUT_OF_RANGE",
                        description=f"VLAN ID {vid} di luar rentang valid 1 - 4094.",
                        affected_object=f"vlan_id={vid}",
                        suggested_resolution="Gunakan VLAN ID antara 1 sampai 4094.",
                        is_blocking=True,
                    ))
            except ValueError:
                findings.append(ValidationFinding(
                    severity=ValidationSeverity.ERROR.value,
                    rule_id="VLAN_ID_NON_NUMERIC",
                    description=f"VLAN ID '{d_state['vlan_id']}' bukan angka integer valid.",
                    affected_object="vlan_id",
                    is_blocking=True,
                ))

        # Check Subnet and Overlap
        if "subnet" in d_state:
            sub_str = d_state["subnet"]
            try:
                cand_net = ipaddress.ip_network(sub_str, strict=False)
                # Check overlap with existing subnets
                for ex_net in existing_subnets:
                    if cand_net.overlaps(ex_net):
                        findings.append(ValidationFinding(
                            severity=ValidationSeverity.ERROR.value,
                            rule_id="SUBNET_OVERLAP",
                            description=f"Subnet yang diusulkan {cand_net} bertabrakan (overlap) dengan subnet yang sudah ada {ex_net}.",
                            evidence_references=["/ip address print detail"],
                            affected_object=str(cand_net),
                            suggested_resolution="Pilih prefix subnet yang belum terpakai di router.",
                            is_blocking=True,
                        ))
                        break
            except ValueError as exc:
                findings.append(ValidationFinding(
                    severity=ValidationSeverity.ERROR.value,
                    rule_id="INVALID_IP_PREFIX",
                    description=f"Alamat IP/prefix '{sub_str}' tidak valid: {exc}.",
                    affected_object=sub_str,
                    is_blocking=True,
                ))

        # Check Interface Existence
        for key in ("interface", "out_interface", "in_interface", "bridge"):
            if key in d_state and d_state[key]:
                if_name = d_state[key]
                # If existing_ifaces is known and the interface is not in it (and not a list/all)
                if existing_ifaces and if_name not in existing_ifaces and if_name not in ("all", "WAN", "LAN"):
                    findings.append(ValidationFinding(
                        severity=ValidationSeverity.ERROR.value,
                        rule_id="INTERFACE_NOT_FOUND",
                        description=f"Interface '{if_name}' tidak ditemukan pada router {target}.",
                        evidence_references=["/interface print detail"],
                        affected_object=if_name,
                        suggested_resolution=f"Pilih interface fisik atau bridge yang aktif dari: {', '.join(sorted(existing_ifaces))}.",
                        is_blocking=True,
                    ))

        # Check Default Route impact on management
        if c_type == "ADD_STATIC_ROUTE":
            dst = d_state.get("dst_address", "")
            gw = d_state.get("gateway", "")
            if dst == "0.0.0.0/0":
                mgmt_risk = True
                mgmt_risk_expl = (
                    f"Rencana ini memodifikasi default route (0.0.0.0/0 via {gw}). "
                    f"Jika gateway tidak dapat dijangkau, konektivitas SSH manajemen ke {mgmt_ip} dapat terputus."
                )
                findings.append(ValidationFinding(
                    severity=ValidationSeverity.WARNING.value,
                    rule_id="MGMT_CONNECTIVITY_DEFAULT_ROUTE_RISK",
                    description=mgmt_risk_expl,
                    affected_object="0.0.0.0/0",
                    suggested_resolution="Pastikan gateway ISP UP sebelum menerapkan perubahan rute default.",
                    is_blocking=False,
                ))

        # 4. Dependency Ordering Analysis
        ordered_deps = self._order_dependencies(plan.dependencies)

        # 5. Determine Overall Risk and Plan Status
        has_blocking = any(f.is_blocking for f in findings)
        has_unknown = any(f.severity == ValidationSeverity.UNKNOWN.value for f in findings)
        has_warnings = any(f.severity == ValidationSeverity.WARNING.value for f in findings)

        if has_blocking:
            v_status = "FAIL"
            p_status = PlanStatus.INVALID.value
            risk = "CRITICAL"
        elif has_unknown:
            v_status = "UNKNOWN"
            p_status = PlanStatus.VALID_WITH_WARNINGS.value
            risk = "MEDIUM"
        elif has_warnings or mgmt_risk:
            v_status = "PASS_WITH_WARNINGS"
            p_status = PlanStatus.VALID_WITH_WARNINGS.value
            risk = "HIGH" if mgmt_risk else "MEDIUM"
        else:
            v_status = "PASS"
            p_status = PlanStatus.READY_FOR_REVIEW.value
            risk = "LOW"

        # Record findings and summary status
        findings_dicts = [f.to_dict() for f in findings]
        plan.validation_results = findings_dicts
        plan.dependencies = ordered_deps
        plan.management_connectivity_risk = mgmt_risk
        plan.management_risk_explanation = mgmt_risk_expl
        plan.risk_level = risk
        plan.plan_status = p_status
        plan.desired_state["validation_status"] = v_status

        return plan

    def _order_dependencies(self, raw_deps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Topologically sorts proposed change dependencies and detects cycles."""
        adj: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}
        nodes: Set[str] = set()

        for d in raw_deps:
            p = d.get("parent", "")
            c = d.get("child", "")
            if p and c:
                nodes.add(p)
                nodes.add(c)
                adj.setdefault(p, []).append(c)
                in_degree[c] = in_degree.get(c, 0) + 1
                in_degree.setdefault(p, 0)

        # Kahn's algorithm
        queue = [n for n in nodes if in_degree.get(n, 0) == 0]
        order = []
        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        has_cycle = len(order) < len(nodes)
        return [
            {
                "topological_order": order,
                "has_dependency_cycle": has_cycle,
                "graph_edges": raw_deps,
            }
        ]
