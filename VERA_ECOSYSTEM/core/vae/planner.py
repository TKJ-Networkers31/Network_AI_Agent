"""
core/vae/planner.py — VERA Adaptive Experience (VAE) Experience Planner.

Analyzes user intent, query semantics, active tool execution steps,
and network context to produce an optimal ExperiencePlan specifying
which visual components, layouts, and evidence references to generate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional


class VaeIntent(str, Enum):
    RESOURCE_INSPECTION = "resource_inspection"
    INTERFACE_INSPECTION = "interface_inspection"
    NETWORK_DIAGNOSTICS = "network_diagnostics"
    ROUTING_ANALYSIS = "routing_analysis"
    INCIDENT_INVESTIGATION = "incident_investigation"
    CONFIGURATION_AUDIT = "configuration_audit"
    REMEDIATION_PROPOSAL = "remediation_proposal"
    GENERAL_EXPLANATION = "general_explanation"


@dataclass
class PlannedBlock:
    block_type: str
    target_data_source: str
    priority: int = 1
    layout_hint: str = "full-width"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperiencePlan:
    intent: VaeIntent
    confidence: float
    planned_blocks: List[PlannedBlock]
    primary_device: Optional[str] = None
    requires_approval: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExperiencePlanner:
    """
    Determines the appropriate VAE representation for a given query,
    session context, and set of tool execution steps.
    """

    # Keyword mappings for intent detection
    INTENT_KEYWORDS = {
        VaeIntent.RESOURCE_INSPECTION: [
            "resource", "cpu", "ram", "memory", "memori", "hdd", "disk", "uptime", "beban", "load",
            "kesehatan", "health", "suhu", "temperature", "voltase", "voltage"
        ],
        VaeIntent.INTERFACE_INSPECTION: [
            "interface", "antarmuka", "ether", "sfp", "wlan", "port", "bandwidth", "traffic",
            "kecepatan", "tx", "rx", "packet", "status port", "link up", "link down"
        ],
        VaeIntent.NETWORK_DIAGNOSTICS: [
            "ping", "traceroute", "latensi", "latency", "rtt", "packet loss", "rto", "hop",
            "jalur", "trace", "reachability", "terhubung", "koneksi"
        ],
        VaeIntent.ROUTING_ANALYSIS: [
            "route", "routing", "rute", "gateway", "bgp", "ospf", "metric", "dst-address",
            "nexthop", "next-hop", "tabel routing", "prefix"
        ],
        VaeIntent.INCIDENT_INVESTIGATION: [
            "incident", "insiden", "alarm", "alert", "rca", "root cause", "penyebab", "down",
            "putus", "gangguan", "mati", "investigasi", "outage"
        ],
        VaeIntent.CONFIGURATION_AUDIT: [
            "config", "konfigurasi", "diff", "perbedaan", "audit", "perubahan", "change",
            "rollback", "compare", "backup"
        ],
        VaeIntent.REMEDIATION_PROPOSAL: [
            "remediasi", "perbaiki", "fix", "restart", "reboot", "disable", "enable",
            "remediation", "action", "tindakan", "jalankan playbook", "playbook"
        ],
    }

    # Tool name mappings to intents
    TOOL_INTENT_MAP = {
        "mikrotik_get_resources": VaeIntent.RESOURCE_INSPECTION,
        "get_resources": VaeIntent.RESOURCE_INSPECTION,
        "mikrotik_get_interfaces": VaeIntent.INTERFACE_INSPECTION,
        "get_interfaces": VaeIntent.INTERFACE_INSPECTION,
        "network_ping": VaeIntent.NETWORK_DIAGNOSTICS,
        "network_traceroute": VaeIntent.NETWORK_DIAGNOSTICS,
        "mikrotik_ping": VaeIntent.NETWORK_DIAGNOSTICS,
        "mikrotik_traceroute": VaeIntent.NETWORK_DIAGNOSTICS,
        "mikrotik_get_routes": VaeIntent.ROUTING_ANALYSIS,
        "get_routes": VaeIntent.ROUTING_ANALYSIS,
        "route_lookup": VaeIntent.ROUTING_ANALYSIS,
        "route_analytics": VaeIntent.ROUTING_ANALYSIS,
        "incident_analysis": VaeIntent.INCIDENT_INVESTIGATION,
        "root_cause_analysis": VaeIntent.INCIDENT_INVESTIGATION,
        "nms_incidents": VaeIntent.INCIDENT_INVESTIGATION,
        "config_diff": VaeIntent.CONFIGURATION_AUDIT,
        "apply_config": VaeIntent.REMEDIATION_PROPOSAL,
        "execute_remediation": VaeIntent.REMEDIATION_PROPOSAL,
    }

    def plan(
        self,
        query: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        interaction_schema: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExperiencePlan:
        """
        Plans the visual blocks and structure based on evidence and user intent.
        """
        steps = steps or []
        context = context or {}
        q_lower = (query or "").lower()

        # Step 1: Detect intent from tool executions (highest fidelity signal)
        intent = None
        primary_tool = None
        evidence_device = None

        for step in reversed(steps):
            t_name = step.get("tool") or step.get("name") or ""
            if t_name in self.TOOL_INTENT_MAP:
                intent = self.TOOL_INTENT_MAP[t_name]
                primary_tool = t_name
                # Check tool arguments for device name
                args = step.get("args") or step.get("parameters") or {}
                evidence_device = args.get("device_name") or args.get("device") or args.get("host")
                break

        # Step 2: Fall back to semantic keyword analysis if no tool matched
        if not intent:
            scores: Dict[VaeIntent, int] = {}
            for cand_intent, keywords in self.INTENT_KEYWORDS.items():
                score = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', q_lower))
                if score > 0:
                    scores[cand_intent] = score

            if scores:
                intent = max(scores, key=scores.get)
            else:
                intent = VaeIntent.GENERAL_EXPLANATION

        # Step 3: Handle explicit interaction schemas (Forms / Action confirmations)
        if interaction_schema and isinstance(interaction_schema, dict):
            mode = interaction_schema.get("mode", "form")
            if mode in ("action", "approval", "danger_confirm"):
                intent = VaeIntent.REMEDIATION_PROPOSAL

        # Step 4: Assemble planned blocks
        planned_blocks: List[PlannedBlock] = [
            # Narrative block is always first (Narrative-First policy)
            PlannedBlock(
                block_type="markdown",
                target_data_source="narrative_text",
                priority=0,
                layout_hint="full-width",
            )
        ]

        confidence = 0.95 if primary_tool else 0.80

        if intent == VaeIntent.RESOURCE_INSPECTION:
            planned_blocks.append(
                PlannedBlock(
                    block_type="resource-gauge",
                    target_data_source="system_resources",
                    priority=1,
                    layout_hint="grid",
                    metadata={"visual_type": "gauge"},
                )
            )
            planned_blocks.append(
                PlannedBlock(
                    block_type="metric-grid",
                    target_data_source="hardware_metrics",
                    priority=2,
                    layout_hint="grid",
                )
            )

        elif intent == VaeIntent.INTERFACE_INSPECTION:
            planned_blocks.append(
                PlannedBlock(
                    block_type="interface-status",
                    target_data_source="interface_list",
                    priority=1,
                    layout_hint="full-width",
                )
            )

        elif intent == VaeIntent.NETWORK_DIAGNOSTICS:
            planned_blocks.append(
                PlannedBlock(
                    block_type="hop-by-hop-traceroute",
                    target_data_source="diagnostic_hops",
                    priority=1,
                    layout_hint="full-width",
                )
            )

        elif intent == VaeIntent.ROUTING_ANALYSIS:
            planned_blocks.append(
                PlannedBlock(
                    block_type="route-table-view",
                    target_data_source="routing_table",
                    priority=1,
                    layout_hint="full-width",
                )
            )

        elif intent == VaeIntent.INCIDENT_INVESTIGATION:
            planned_blocks.append(
                PlannedBlock(
                    block_type="incident-summary",
                    target_data_source="incident_report",
                    priority=1,
                    layout_hint="full-width",
                )
            )
            planned_blocks.append(
                PlannedBlock(
                    block_type="root-cause-panel",
                    target_data_source="rca_findings",
                    priority=2,
                    layout_hint="full-width",
                )
            )

        elif intent == VaeIntent.CONFIGURATION_AUDIT:
            planned_blocks.append(
                PlannedBlock(
                    block_type="config-diff",
                    target_data_source="configuration_diff",
                    priority=1,
                    layout_hint="full-width",
                )
            )

        elif intent == VaeIntent.REMEDIATION_PROPOSAL:
            planned_blocks.append(
                PlannedBlock(
                    block_type="action-card",
                    target_data_source="action_payload",
                    priority=1,
                    layout_hint="full-width",
                    metadata={"requires_confirmation": True},
                )
            )

        return ExperiencePlan(
            intent=intent,
            confidence=confidence,
            planned_blocks=planned_blocks,
            primary_device=evidence_device,
            requires_approval=intent == VaeIntent.REMEDIATION_PROPOSAL,
            metadata={
                "detected_via_tool": bool(primary_tool),
                "primary_tool": primary_tool,
            },
        )
